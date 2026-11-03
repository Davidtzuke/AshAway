"""Shared test data. Everything here runs offline, so the tests can run in CI."""
import json
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ashaway.assess import Assessor, load_destinations
from ashaway.model.bundle import load_bundle

TESTS_DIR = Path(__file__).parent
FEEDS_DIR = TESTS_DIR / "data" / "feeds"
BUNDLE_DIR = TESTS_DIR.parent / "models" / "live-v1"
FIXED_NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
FIRMS_TEST_KEY = "test-key"


def pytest_collection_modifyitems(items):
    """The folder decides the level: tests/unit or tests/integration."""
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "unit" in parts:
            item.add_marker("unit")
        elif "integration" in parts:
            item.add_marker("integration")


class ReplayFetch:
    """Stands in for the network and replays recorded responses for a URL.

    `down` holds sources that fail like a broken service: "weather", "air" or "firms".
    """

    def __init__(self, down=(), firms_file="rhodes_firms.csv"):
        self.down = set(down)
        self.firms_file = firms_file
        self.ids = {
            (round(float(d["lat"]), 5), round(float(d["lon"]), 5)): dest_id
            for dest_id, d in load_destinations().iterrows()
        }

    def _fail(self, url):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", None, None)

    def __call__(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if "firms" in parsed.netloc:
            if "firms" in self.down:
                self._fail(url)
            return (FEEDS_DIR / self.firms_file).read_text(encoding="utf-8")
        q = urllib.parse.parse_qs(parsed.query)
        dest_id = self.ids[(round(float(q["latitude"][0]), 5), round(float(q["longitude"][0]), 5))]
        if "air-quality" in parsed.netloc:
            path = FEEDS_DIR / f"{dest_id}_air.json"
            if "air" in self.down or not path.exists():
                self._fail(url)
            return path.read_text(encoding="utf-8")
        if "weather" in self.down:
            self._fail(url)
        data = json.loads((FEEDS_DIR / f"{dest_id}_weather.json").read_text(encoding="utf-8"))
        days = data["daily"]["time"]
        keep = [i for i, d in enumerate(days) if q["start_date"][0] <= d <= q["end_date"][0]]
        data["daily"] = {name: [values[i] for i in keep] for name, values in data["daily"].items()}
        return json.dumps(data)


@pytest.fixture(scope="session")
def bundle():
    return load_bundle(BUNDLE_DIR)


@pytest.fixture
def make_assessor(bundle, tmp_path):
    """Assessor wired to recorded feeds and a fixed clock. Pass firms_key=None for no key."""

    def _make(down=(), firms_key=FIRMS_TEST_KEY, firms_file="rhodes_firms.csv"):
        return Assessor(
            bundle,
            fetch=ReplayFetch(down, firms_file),
            clock=lambda: FIXED_NOW,
            firms_key=firms_key if firms_key else "",
            log_path=tmp_path / "updates.jsonl",
        )

    return _make
