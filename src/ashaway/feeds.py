"""External feeds. A failed feed is reported as unavailable, never filled in (FR3, NFR3, NFR5).

`fetch` is any function from URL to response text, so tests can replay recorded responses.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .evidence import EvidenceItem, EvidenceKind, SourceStatus
from .targets import PredictionTarget, haversine_km

log = logging.getLogger(__name__)

Fetch = Callable[[str], str]

WEATHER, FIRES, AIR, DISRUPTION = "Open-Meteo weather", "NASA FIRMS fire detections", "Open-Meteo air quality (CAMS)", "Disruption news"
ARCHIVE_DELAY_DAYS = 6  # the reanalysis archive lags real time by about this much
FIRMS_NRT_DAYS = 60  # older detections come from the standard processing archive
FIRMS_LOOKBACK_DAYS = 5
AIR_LOOKBACK_DAYS = 2
WHO_PM25_24H = 15.0  # ug/m3, WHO 2021 guideline
DAILY_FIELDS = "temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum"
KELVIN = 273.15


def http_get(url: str, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "AshAway/0.1 (student project)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


@dataclass(frozen=True)
class FeedResult:
    status: SourceStatus
    data: pd.DataFrame | None = None
    items: list[EvidenceItem] = field(default_factory=list)
    detections: int = 0


def _unavailable(name: str, critical: bool, retrieved_at: str, error: str) -> FeedResult:
    log.info("%s unavailable: %s", name, error)
    return FeedResult(SourceStatus(name, critical, False, retrieved_at, error=error))


def weather_url(lat: float, lon: float, start: date, end: date, today: date) -> str:
    host = "archive-api" if end <= today - timedelta(days=ARCHIVE_DELAY_DAYS) else "api"
    path = "archive" if host == "archive-api" else "forecast"
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "daily": DAILY_FIELDS, "wind_speed_unit": "ms", "timezone": "UTC",
    })
    return f"https://{host}.open-meteo.com/v1/{path}?{query}"


def parse_weather(text: str) -> pd.DataFrame:
    """Open-Meteo daily JSON to Mesogeos units: kelvin, humidity 0-1, m/s, metres of rain.

    A null stays NaN. Raises ValueError when the response has the wrong shape.
    """
    try:
        daily = json.loads(text)["daily"]
        frame = pd.DataFrame({
            "date": pd.to_datetime(daily["time"]).date,
            "t2m_max": pd.to_numeric(pd.Series(daily["temperature_2m_max"], dtype=float)) + KELVIN,
            "rh_min": pd.to_numeric(pd.Series(daily["relative_humidity_2m_min"], dtype=float)) / 100,
            "wind_speed": pd.to_numeric(pd.Series(daily["wind_speed_10m_max"], dtype=float)),
            "tp": pd.to_numeric(pd.Series(daily["precipitation_sum"], dtype=float)) / 1000,
        })
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unexpected weather response: {exc}") from exc
    return frame


def get_weather(lat: float, lon: float, start: date, end: date, as_of: date, today: date, fetch: Fetch, retrieved_at: str) -> FeedResult:
    try:
        frame = parse_weather(fetch(weather_url(lat, lon, start, end, today)))
    except (OSError, ValueError) as exc:
        return _unavailable(WEATHER, True, retrieved_at, str(exc))
    known = frame.dropna()
    known = known[known["date"] <= as_of]
    latest = known["date"].max() if len(known) else None
    return FeedResult(SourceStatus(WEATHER, True, True, retrieved_at, latest_observation=latest), data=frame)


def air_url(lat: float, lon: float, start: date, end: date) -> str:
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "hourly": "pm2_5", "timezone": "UTC",
    })
    return f"https://air-quality-api.open-meteo.com/v1/air-quality?{query}"


def parse_air(text: str) -> pd.Series:
    """Hourly PM2.5 JSON to a daily mean per date. Hours with no value are left out, not zeroed."""
    try:
        hourly = json.loads(text)["hourly"]
        values = pd.Series(hourly["pm2_5"], index=pd.to_datetime(hourly["time"]), dtype=float).dropna()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unexpected air quality response: {exc}") from exc
    return values.groupby(values.index.date).mean()


def get_air(lat: float, lon: float, as_of: date, fetch: Fetch, retrieved_at: str) -> FeedResult:
    try:
        daily = parse_air(fetch(air_url(lat, lon, as_of - timedelta(days=AIR_LOOKBACK_DAYS), as_of)))
    except (OSError, ValueError) as exc:
        return _unavailable(AIR, False, retrieved_at, str(exc))
    if daily.empty:
        return _unavailable(AIR, False, retrieved_at, "no values for these dates")
    latest = max(daily.index)
    guideline = "above" if daily[latest] > WHO_PM25_24H else "within"
    item = EvidenceItem(
        EvidenceKind.OBSERVATION, AIR, latest,
        f"PM2.5 averaged {daily[latest]:.1f} ug/m3, {guideline} the WHO 24-hour guideline of {WHO_PM25_24H:.0f}. "
        "This is a modelled estimate and does not identify the cause, which may not be smoke.",
    )
    return FeedResult(SourceStatus(AIR, False, True, retrieved_at, latest_observation=latest), items=[item])


def firms_url(key: str, lat: float, lon: float, as_of: date, today: date, radius_km: float) -> str:
    # Roughly radius_km in degrees, padded. The exact distance is checked after download.
    d_lat = radius_km / 110.0 + 0.05
    d_lon = radius_km / (110.0 * max(np.cos(np.radians(lat)), 0.1)) + 0.05
    area = f"{lon - d_lon:.3f},{lat - d_lat:.3f},{lon + d_lon:.3f},{lat + d_lat:.3f}"
    product = "VIIRS_SNPP_NRT" if (today - as_of).days <= FIRMS_NRT_DAYS else "VIIRS_SNPP_SP"
    first_day = as_of - timedelta(days=FIRMS_LOOKBACK_DAYS - 1)
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{area}/{FIRMS_LOOKBACK_DAYS}/{first_day}"


def parse_firms(text: str, lat: float, lon: float, radius_km: float, as_of: date) -> pd.DataFrame:
    """FIRMS area CSV to the detections within radius_km, up to as_of. FIRMS reports errors as plain text."""
    if not text.lstrip().startswith("latitude"):
        raise ValueError(f"unexpected FIRMS response: {text[:80]}")
    frame = pd.DataFrame(list(csv.DictReader(io.StringIO(text))), columns=["latitude", "longitude", "acq_date"])
    frame["latitude"] = pd.to_numeric(frame["latitude"])
    frame["longitude"] = pd.to_numeric(frame["longitude"])
    frame["acq_date"] = pd.to_datetime(frame["acq_date"]).dt.date
    frame["km"] = haversine_km(frame["longitude"].to_numpy(), frame["latitude"].to_numpy(), lon, lat)
    return frame[(frame["km"] <= radius_km) & (frame["acq_date"] <= as_of)].reset_index(drop=True)


def get_fires(lat: float, lon: float, as_of: date, today: date, fetch: Fetch, retrieved_at: str, key: str | None = None) -> FeedResult:
    key = key if key is not None else os.environ.get("FIRMS_MAP_KEY")
    if not key:
        return _unavailable(FIRES, True, retrieved_at, "no FIRMS_MAP_KEY configured")
    radius = PredictionTarget().fire_radius_km
    try:
        fires = parse_firms(fetch(firms_url(key, lat, lon, as_of, today, radius)), lat, lon, radius, as_of)
    except (OSError, ValueError) as exc:
        # The URL holds the key, so the message must not repeat it.
        return _unavailable(FIRES, True, retrieved_at, str(exc).replace(key, "***"))
    status = SourceStatus(FIRES, True, True, retrieved_at, latest_observation=as_of)
    if fires.empty:
        return FeedResult(status)
    item = EvidenceItem(
        EvidenceKind.OBSERVATION, FIRES, max(fires["acq_date"]),
        f"{len(fires)} satellite heat detection(s) within {radius:.0f} km, the closest {fires['km'].min():.1f} km away. "
        "Some detections can be farm burning or industrial heat.",
    )
    return FeedResult(status, items=[item], detections=len(fires))


def get_disruption(retrieved_at: str) -> FeedResult:
    """News of evacuations and closures is not connected yet (T13), and the result says so."""
    return _unavailable(DISRUPTION, False, retrieved_at, "feed not connected yet")


def log_update(path: str | Path, statuses: list[SourceStatus], destination_id: str) -> None:
    """Append one line per source: retrieval time, result and any failure (NFR3). No user data (NFR7)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        for status in statuses:
            out.write(json.dumps({"destination": destination_id, **asdict(status)}, default=str) + "\n")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
