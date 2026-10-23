"""Data loading, synthetic generation and temporal splitting for the XGBoost model.

Real data: Mesogeos Track A (Kondylatos et al., Orion Lab NOA). Download
`ml_tracks/a.fire_danger/positives.csv` and `negatives.csv` from the Google
Drive folder linked in https://github.com/Orion-AI-Lab/mesogeos (rclone works
best, see mesogeos issue #4) and place them in data/raw/mesogeos/.

Track A stores each sample as 30 consecutive daily rows (column `sample`,
`time`, dynamic + static features). The label refers to the day after the
last row, so we keep the last row of each sample as one tabular cell-day.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_MESOGEOS_DIR = Path("data/raw/mesogeos")

# Core features shared by real and synthetic data (names follow our schema).
BASE_FEATURES = [
    "t2m_max",
    "rh_min",
    "wind_speed",
    "tp",
    "ndvi",
    "lai",
    "fwi",
    "roads_distance",
    "population",
]
# Extra Mesogeos columns used when present in the real files.
EXTRA_REAL_FEATURES = [
    "d2m", "lst_day", "lst_night", "smi", "sp", "ssrd", "dem", "slope",
    "lc_agriculture", "lc_forest", "lc_grassland", "lc_settlement",
    "lc_shrubland", "lc_sparse_vegetation", "lc_water_bodies", "lc_wetland",
]
# Mesogeos column name -> our column name.
MESOGEOS_RENAME = {"t2m": "t2m_max", "rh": "rh_min"}

ID_COLUMNS = ["date", "cell_id", "lon", "lat"]
LABEL = "label"

TRAIN_YEARS = range(2006, 2020)  # 2006-2019 inclusive
VAL_YEARS = (2020,)
TEST_YEARS = (2021, 2022)


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model features available in df, in a stable order. Never includes ids or label."""
    return [c for c in BASE_FEATURES + EXTRA_REAL_FEATURES if c in df.columns]


def fire_danger_proxy(df: pd.DataFrame) -> pd.Series:
    """Rank-based hot/dry/windy index used when no FWI column exists.

    Mesogeos Track A ships no FWI, so the baseline on real data uses this
    proxy: mean percentile of t2m (up), rh (down), wind (up), tp (down).
    """
    parts = [
        df["t2m_max"].rank(pct=True),
        1 - df["rh_min"].rank(pct=True),
        df["wind_speed"].rank(pct=True),
        1 - df["tp"].rank(pct=True),
    ]
    return sum(parts) / len(parts)


def load_mesogeos_track_a(root: str | Path = DEFAULT_MESOGEOS_DIR) -> pd.DataFrame:
    """Load Track A positives/negatives into one row per sample (last day of the window)."""
    root = Path(root)
    pos_path, neg_path = root / "positives.csv", root / "negatives.csv"
    if not pos_path.exists() or not neg_path.exists():
        raise FileNotFoundError(
            f"Mesogeos Track A files not found in {root}/. Download positives.csv and "
            "negatives.csv (ml_tracks/a.fire_danger) from the Google Drive linked at "
            "https://github.com/Orion-AI-Lab/mesogeos and place them there, "
            "or run with --synthetic."
        )
    frames = []
    for path, label in ((pos_path, 1), (neg_path, 0)):
        raw = pd.read_csv(path)
        raw["time"] = pd.to_datetime(raw["time"])
        last = raw.sort_values(["sample", "time"]).groupby("sample", as_index=False).tail(1).copy()
        last[LABEL] = label
        last["cell_id"] = f"{'p' if label else 'n'}" + last["sample"].astype(str)
        frames.append(last)
    df = pd.concat(frames, ignore_index=True).rename(columns=MESOGEOS_RENAME)
    df = df.rename(columns={"time": "date", "x": "lon", "y": "lat"})
    for col in ("lon", "lat"):
        if col not in df.columns:
            df[col] = np.nan
    if "fwi" not in df.columns:
        df["fwi"] = fire_danger_proxy(df)
    # Drop columns that describe the fire outcome itself (leakage).
    df = df.drop(columns=[c for c in ("burned_area_has", "burned_areas", "ignition_points") if c in df.columns])
    return df.reset_index(drop=True)


def make_synthetic_cell_days(n: int = 25722, seed: int = 0, positive_rate: float = 0.035) -> pd.DataFrame:
    """Synthetic Greek 1 km cell-days, 2006-2022 fire season (May-Oct).

    Fire probability rises with heat, dryness, wind and vegetation and falls
    with rain and distance to roads. FWI is a noisy function of the weather,
    so a model that sees the raw drivers can beat an FWI-only ranking.
    THIS IS NOT REAL DATA. Results on it say nothing about real skill.
    """
    rng = np.random.default_rng(seed)
    n_cells = max(50, n // 100)
    cell_lon = rng.uniform(20.0, 28.0, n_cells)
    cell_lat = rng.uniform(35.0, 41.7, n_cells)
    cell_veg = rng.beta(2, 2, n_cells)
    cell_roads = rng.gamma(2.0, 1.5, n_cells)  # km
    cell_pop = rng.lognormal(3.0, 1.5, n_cells)

    cell = rng.integers(0, n_cells, n)
    year = rng.integers(2006, 2023, n)
    doy = rng.integers(121, 305, n)  # May-Oct
    date = pd.to_datetime(year.astype(str), format="%Y") + pd.to_timedelta(doy - 1, unit="D")
    season = np.sin((doy - 121) / 184 * np.pi)  # peaks mid-summer

    t2m = 24 + 10 * season + rng.normal(0, 3.5, n) - 0.8 * (cell_lat[cell] - 38)
    rh = np.clip(55 - 1.6 * (t2m - 28) + rng.normal(0, 8, n), 5, 100)
    wind = rng.gamma(3.0, 4.0, n)  # km/h
    rain_day = rng.random(n) < (0.25 - 0.18 * season)
    tp = np.where(rain_day, rng.exponential(4.0, n), 0.0)
    ndvi = np.clip(0.2 + 0.5 * cell_veg[cell] - 0.1 * season + rng.normal(0, 0.05, n), 0, 1)
    lai = np.clip(ndvi * 4 + rng.normal(0, 0.3, n), 0, None)
    fwi = np.clip(0.9 * (t2m - 15) - 0.35 * (rh - 30) + 0.6 * wind - 2.5 * tp + rng.normal(0, 8, n), 0, None)

    logit = (
        0.22 * (t2m - 30)
        - 0.04 * (rh - 30)
        + 0.08 * (wind - 12)
        - 0.6 * tp
        + 2.0 * (ndvi - 0.4)
        - 0.25 * cell_roads[cell]
        + 0.15 * np.log1p(cell_pop[cell])
    )
    # Pick the intercept so the expected positive rate matches the target.
    lo, hi = -20.0, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if (1 / (1 + np.exp(-(logit + mid)))).mean() > positive_rate:
            hi = mid
        else:
            lo = mid
    p = 1 / (1 + np.exp(-(logit + lo)))
    label = (rng.random(n) < p).astype(int)

    df = pd.DataFrame({
        "date": date,
        "cell_id": cell.astype(str),
        "lon": cell_lon[cell],
        "lat": cell_lat[cell],
        "t2m_max": t2m,
        "rh_min": rh,
        "wind_speed": wind,
        "tp": tp,
        "ndvi": ndvi,
        "lai": lai,
        "fwi": fwi,
        "roads_distance": cell_roads[cell],
        "population": cell_pop[cell],
        LABEL: label,
    })
    return df.sort_values("date").reset_index(drop=True)


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split by calendar year only: train 2006-2019, val 2020, test 2021-2022."""
    year = pd.to_datetime(df["date"]).dt.year
    train = df[year.isin(list(TRAIN_YEARS))].reset_index(drop=True)
    val = df[year.isin(VAL_YEARS)].reset_index(drop=True)
    test = df[year.isin(TEST_YEARS)].reset_index(drop=True)
    return train, val, test
