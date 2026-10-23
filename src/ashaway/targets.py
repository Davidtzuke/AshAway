"""Prediction targets and temporal split for AshAway.

Product target: binary `affected` for a (municipality, issue date d) row. The row
is positive if at least one of these holds during days d+1 .. d+7 (inclusive):

  (a) firms: a NASA FIRMS VIIRS active-fire detection lies within
      `fire_radius_km` of the municipality centroid;
  (b) effis: the municipality intersects an EFFIS burnt-area perimeter whose
      fire start date falls in the window;
  (c) hfs: the Hellenic Fire Service recorded an incident in that municipality
      with severity >= `min_severity`.

TODO(smoke): a fourth condition based on PM2.5 smoke exposure (e.g. CAMS
forecasts above a threshold) is deferred. Add it as another boolean column
OR-ed into `affected` once the data source is chosen.

Training target (cell level, Mesogeos convention): `ignition` = any fire in the
1 km cell on day d+1. Cell labels are built during feature engineering from the
same fire sources; this module only fixes the name and horizon.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088

CELL_TARGET = "ignition"
CELL_HORIZON_DAYS = 1

# Mesogeos Track A temporal split, by calendar year of the issue date.
TRAIN_YEARS = (2006, 2019)
VAL_YEARS = (2020, 2020)
TEST_YEARS = (2021, 2022)


@dataclass(frozen=True)
class PredictionTarget:
    """Configuration of the municipality-day `affected` label."""

    horizon_days: int = 7
    fire_radius_km: float = 20.0
    # HFS severity threshold, on the ordinal scale produced by HFS ingestion.
    # None counts every recorded incident.
    min_severity: float | None = None

    def __post_init__(self):
        if self.horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")
        if self.fire_radius_km <= 0:
            raise ValueError("fire_radius_km must be > 0")


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle distance in km. Broadcasts over numpy arrays."""
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def _mark_windows(
    grid: pd.DataFrame, events: pd.DataFrame, horizon_days: int
) -> pd.Series:
    """Flag grid rows (municipality_code, date d) with an event in d+1..d+horizon.

    `events` has columns municipality_code, event_date. An event on day e marks
    issue dates e-horizon .. e-1.
    """
    if events.empty:
        return pd.Series(False, index=grid.index)
    ev = events[["municipality_code", "event_date"]].drop_duplicates()
    offsets = pd.DataFrame({"offset": range(1, horizon_days + 1)})
    expanded = ev.merge(offsets, how="cross")
    expanded["date"] = expanded["event_date"] - pd.to_timedelta(expanded["offset"], unit="D")
    hits = expanded[["municipality_code", "date"]].drop_duplicates()
    hits["_hit"] = True
    merged = grid[["municipality_code", "date"]].merge(hits, on=["municipality_code", "date"], how="left")
    return pd.Series(merged["_hit"].notna().to_numpy(), index=grid.index)


def _firms_events(municipalities: pd.DataFrame, firms_df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    if firms_df is None or firms_df.empty:
        return pd.DataFrame(columns=["municipality_code", "event_date"])
    m = municipalities[["municipality_code", "lon", "lat"]].reset_index(drop=True)
    f = firms_df[["lon", "lat", "date"]].reset_index(drop=True)
    dist = haversine_km(
        m["lon"].to_numpy()[:, None], m["lat"].to_numpy()[:, None],
        f["lon"].to_numpy()[None, :], f["lat"].to_numpy()[None, :],
    )
    mi, fi = np.nonzero(dist <= radius_km)
    return pd.DataFrame(
        {
            "municipality_code": m["municipality_code"].to_numpy()[mi],
            "event_date": pd.to_datetime(f["date"]).dt.normalize().to_numpy()[fi],
        }
    )


def label_affected(
    municipalities: pd.DataFrame,
    dates,
    firms_df: pd.DataFrame | None,
    effis_df: pd.DataFrame | None,
    hfs_df: pd.DataFrame | None,
    config: PredictionTarget = PredictionTarget(),
) -> pd.DataFrame:
    """Build municipality-day `affected` labels.

    Inputs (plain DataFrames):
      municipalities: municipality_code, lon, lat (centroid, WGS84)
      dates: iterable of issue dates d
      firms_df: lon, lat, date (detection date)
      effis_df: municipality_code, fire_start (perimeters pre-intersected
        with municipality polygons)
      hfs_df: municipality_code, date, severity

    Returns one row per (municipality_code, date) with boolean columns
    cond_firms, cond_effis, cond_hfs and affected (their OR).
    """
    h = config.horizon_days
    grid = municipalities[["municipality_code"]].drop_duplicates().merge(
        pd.DataFrame({"date": pd.to_datetime(pd.Series(list(dates))).dt.normalize()}), how="cross"
    )

    firms_ev = _firms_events(municipalities, firms_df, config.fire_radius_km)
    grid["cond_firms"] = _mark_windows(grid, firms_ev, h)

    if effis_df is None or effis_df.empty:
        effis_ev = pd.DataFrame(columns=["municipality_code", "event_date"])
    else:
        effis_ev = pd.DataFrame(
            {
                "municipality_code": effis_df["municipality_code"].to_numpy(),
                "event_date": pd.to_datetime(effis_df["fire_start"]).dt.normalize().to_numpy(),
            }
        )
    grid["cond_effis"] = _mark_windows(grid, effis_ev, h)

    if hfs_df is None or hfs_df.empty:
        hfs_ev = pd.DataFrame(columns=["municipality_code", "event_date"])
    else:
        hfs = hfs_df
        if config.min_severity is not None:
            hfs = hfs[hfs["severity"] >= config.min_severity]
        hfs_ev = pd.DataFrame(
            {
                "municipality_code": hfs["municipality_code"].to_numpy(),
                "event_date": pd.to_datetime(hfs["date"]).dt.normalize().to_numpy(),
            }
        )
    grid["cond_hfs"] = _mark_windows(grid, hfs_ev, h)

    grid["affected"] = grid["cond_firms"] | grid["cond_effis"] | grid["cond_hfs"]
    return grid


def temporal_split(df: pd.DataFrame, date_col: str = "date"):
    """Split rows into (train, val, test) by the calendar year of `date_col`.

    Uses the Mesogeos Track A years. Rows outside 2006-2022 are dropped. Never
    shuffles: a date belongs to exactly one split.

    Caveat: labels look 7 days ahead, so issue dates in the last week of a split
    see events from the next split's first days. Purge those rows if leakage
    matters for a given experiment.
    """
    years = pd.to_datetime(df[date_col]).dt.year

    def _sel(bounds):
        lo, hi = bounds
        return df[(years >= lo) & (years <= hi)]

    return _sel(TRAIN_YEARS), _sel(VAL_YEARS), _sel(TEST_YEARS)
