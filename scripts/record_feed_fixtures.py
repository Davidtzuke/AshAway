"""Record the real Open-Meteo responses the integration tests replay (CC BY 4.0).

Weather covers each pilot destination for the 2023 test dates. Air quality covers
the days before the test trips. The FIRMS file is hand-written, because a FIRMS
key is not set up yet (T12); it follows the documented area-API CSV columns.
"""
import urllib.parse
from datetime import date
from pathlib import Path

from ashaway.assess import load_destinations
from ashaway.feeds import DAILY_FIELDS, air_url, http_get

OUT = Path("tests/data/feeds")
WEATHER_START, WEATHER_END = date(2023, 4, 25), date(2023, 7, 31)
AIR_WINDOWS = {("rhodes", date(2023, 7, 15), date(2023, 7, 17)), ("chania", date(2023, 5, 29), date(2023, 5, 31))}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    destinations = load_destinations()
    for dest_id, dest in destinations.iterrows():
        query = urllib.parse.urlencode({
            "latitude": dest["lat"], "longitude": dest["lon"], "start_date": WEATHER_START, "end_date": WEATHER_END,
            "daily": DAILY_FIELDS, "wind_speed_unit": "ms", "timezone": "UTC",
        })
        text = http_get(f"https://archive-api.open-meteo.com/v1/archive?{query}")
        (OUT / f"{dest_id}_weather.json").write_text(text, encoding="utf-8")
    for dest_id, start, end in AIR_WINDOWS:
        dest = destinations.loc[dest_id]
        (OUT / f"{dest_id}_air.json").write_text(http_get(air_url(dest["lat"], dest["lon"], start, end)), encoding="utf-8")
