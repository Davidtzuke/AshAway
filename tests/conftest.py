"""Shared test data. Everything here runs offline, so the tests can run in CI."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ashaway.assess import Assessor
from ashaway.model.bundle import load_bundle
from ashaway.replay import DEFAULT_DIR as FEEDS_DIR, ReplayFetch  # noqa: F401  (tests import both from here)

TESTS_DIR = Path(__file__).parent
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
