"""Recorded feed responses in place of the internet, for tests and offline demos.

The recordings are real Open-Meteo responses from 2023 (weather from 25 April to
31 July for all 11 destinations; air quality for two short periods). The FIRMS
files are hand-written in NASA's format, so they are only served when a test
asks for one by name; otherwise FIRMS counts as unavailable.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
from pathlib import Path

from .assess import load_destinations

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "tests" / "data" / "feeds"


class ReplayFetch:
    """Stands in for the network and replays recorded responses for a URL.

    `down` holds sources that fail like a broken service: "weather", "air" or "firms".
    `firms_file=None` makes FIRMS fail too, since there are no real recordings of it.
    """

    def __init__(self, down=(), firms_file: str | None = "rhodes_firms.csv", directory: str | Path = DEFAULT_DIR):
        self.down = set(down)
        self.firms_file = firms_file
        self.directory = Path(directory)
        self.ids = {
            (round(float(d["lat"]), 5), round(float(d["lon"]), 5)): dest_id
            for dest_id, d in load_destinations().iterrows()
        }

    def _fail(self, url):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", None, None)

    def __call__(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if "firms" in parsed.netloc:
            if "firms" in self.down or self.firms_file is None:
                self._fail(url)
            return (self.directory / self.firms_file).read_text(encoding="utf-8")
        q = urllib.parse.parse_qs(parsed.query)
        dest_id = self.ids[(round(float(q["latitude"][0]), 5), round(float(q["longitude"][0]), 5))]
        if "air-quality" in parsed.netloc:
            path = self.directory / f"{dest_id}_air.json"
            if "air" in self.down or not path.exists():
                self._fail(url)
            return path.read_text(encoding="utf-8")
        if "weather" in self.down:
            self._fail(url)
        data = json.loads((self.directory / f"{dest_id}_weather.json").read_text(encoding="utf-8"))
        days = data["daily"]["time"]
        keep = [i for i, d in enumerate(days) if q["start_date"][0] <= d <= q["end_date"][0]]
        data["daily"] = {name: [values[i] for i in keep] for name, values in data["daily"].items()}
        return json.dumps(data)
