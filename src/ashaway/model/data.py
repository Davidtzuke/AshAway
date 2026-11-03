"""Data loading, synthetic generation and temporal splitting for the XGBoost model.

Real data: Mesogeos Track A (Kondylatos et al., Orion Lab NOA, CC BY 4.0).
`scripts/download_mesogeos.py` fetches `ml_tracks/a.danger_forecasting/`
positives.csv and negatives.csv from the Google Drive folder linked in
https://github.com/Orion-AI-Lab/mesogeos into data/raw/mesogeos/.

Track A stores each sample as 30 consecutive daily rows (column `sample`,
`time_idx` 0-29, dynamic + static features). Row 29 is the labelled day: for
positives it is the fire day itself (burned_areas > 0 in 67% of them), so it
must not be a model input. We issue the forecast on row 28 and build features
only from rows 0-28, which gives a true next-day forecast.
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
# Aggregates over the 7 days up to the issue day (built from rows <= ISSUE_TIME_IDX).
WINDOW_FEATURES = ["rain_7d", "days_since_rain", "t2m_max_7d", "rh_min_7d"]
# Weather inputs a live feed can supply; the deployable model is limited to these.
LIVE_FEATURES = ["t2m_max", "rh_min", "wind_speed", "tp"] + WINDOW_FEATURES
# Mesogeos column name -> our column name.
MESOGEOS_RENAME = {"t2m": "t2m_max", "rh": "rh_min"}

ID_COLUMNS = ["date", "cell_id", "lon", "lat"]
LABEL = "label"
OUTCOME_COLUMNS = ("burned_area_has", "burned_areas", "ignition_points")

WINDOW_ROWS = 30
LABEL_TIME_IDX = 29  # the labelled day (the fire day for positives)
ISSUE_TIME_IDX = 28  # last day whose values the model may see
RAIN_DAY_M = 0.001  # 1 mm in Mesogeos' metres of precipitation
# The official Track A loader keeps 2 negatives per positive in each split.
NEG_POS_RATIO = 2
SAMPLE_SEED = 12345

TRAIN_YEARS = range(2006, 2020)  # 2006-2019 inclusive
VAL_YEARS = (2020,)
TEST_YEARS = (2021, 2022)


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model features available in df, in a stable order. Never includes ids or label."""
    return [c for c in BASE_FEATURES + EXTRA_REAL_FEATURES + WINDOW_FEATURES if c in df.columns]


def percentile_of(values, reference) -> np.ndarray:
    """Percentile in [0, 1] of each value within a fixed reference sample."""
    ordered = np.sort(np.asarray(reference, dtype=float))
    return np.searchsorted(ordered, np.asarray(values, dtype=float), side="right") / len(ordered)


def fire_danger_proxy(df: pd.DataFrame, reference: pd.DataFrame | None = None) -> np.ndarray:
    """Rank-based hot/dry/windy index used when no FWI column exists.

    Mesogeos Track A ships no FWI, so the baseline on real data uses this
    proxy: mean percentile of t2m (up), rh (down), wind (up), tp (down).
    Percentiles are taken within `reference`. Pass the training split so that
    validation and test values never shape the scale.
    """
    ref = df if reference is None else reference
    parts = [
        percentile_of(df["t2m_max"], ref["t2m_max"]),
        1 - percentile_of(df["rh_min"], ref["rh_min"]),
        percentile_of(df["wind_speed"], ref["wind_speed"]),
        1 - percentile_of(df["tp"], ref["tp"]),
    ]
    return sum(parts) / len(parts)


def window_features(tp_m: np.ndarray, t2m: np.ndarray, rh: np.ndarray) -> dict[str, np.ndarray]:
    """7-day weather aggregates for arrays of shape (samples, days), oldest day first.

    `days_since_rain` counts back from the last day: 0 means it rained on the
    last day, and the full window length means no rain day in the window.
    """
    rainy = tp_m >= RAIN_DAY_M
    n_days = tp_m.shape[1]
    days_back = np.argmax(rainy[:, ::-1], axis=1)
    return {
        "rain_7d": tp_m[:, -7:].sum(axis=1),
        "days_since_rain": np.where(rainy.any(axis=1), days_back, n_days).astype(float),
        "t2m_max_7d": t2m[:, -7:].max(axis=1),
        "rh_min_7d": rh[:, -7:].min(axis=1),
    }


def _samples_to_cell_days(raw: pd.DataFrame, label: int) -> tuple[pd.DataFrame, int]:
    """One row per complete sample, with rows <= ISSUE_TIME_IDX as the only inputs."""
    sizes = raw.groupby("sample")["time_idx"].transform("size")
    complete = raw[sizes == WINDOW_ROWS].sort_values(["sample", "time_idx"])
    n_incomplete = raw["sample"].nunique() - complete["sample"].nunique()

    issue = complete[complete["time_idx"] == ISSUE_TIME_IDX].reset_index(drop=True)
    target = complete[complete["time_idx"] == LABEL_TIME_IDX].reset_index(drop=True)
    history = complete[complete["time_idx"] <= ISSUE_TIME_IDX]
    shape = (-1, ISSUE_TIME_IDX + 1)
    windows = window_features(
        history["tp"].to_numpy().reshape(shape),
        history["t2m"].to_numpy().reshape(shape),
        history["rh"].to_numpy().reshape(shape),
    )

    out = issue.assign(**windows)
    out["target_date"] = pd.to_datetime(target["time"])
    out[LABEL] = label
    out["cell_id"] = f"{'p' if label else 'n'}" + out["sample"].astype(str)
    return out, n_incomplete


def _downsample_negatives(df: pd.DataFrame, ratio: int, seed: int) -> pd.DataFrame:
    """Keep `ratio` negatives per positive within each split, as the official loader does."""
    rng = np.random.default_rng(seed)
    year = df["target_date"].dt.year
    keep = df[LABEL] == 1
    for years in (list(TRAIN_YEARS), list(VAL_YEARS), list(TEST_YEARS)):
        in_split = year.isin(years)
        negatives = df.index[in_split & (df[LABEL] == 0)]
        wanted = min(len(negatives), int((in_split & (df[LABEL] == 1)).sum()) * ratio)
        keep.loc[rng.choice(negatives, wanted, replace=False)] = True
    return df[keep].reset_index(drop=True)


def load_track_a_with_report(
    root: str | Path = DEFAULT_MESOGEOS_DIR, neg_pos_ratio: int = NEG_POS_RATIO, seed: int = SAMPLE_SEED
) -> tuple[pd.DataFrame, dict]:
    """Load Track A into one row per sample and the data-quality report NFR2 asks for."""
    root = Path(root)
    pos_path, neg_path = root / "positives.csv", root / "negatives.csv"
    if not pos_path.exists() or not neg_path.exists():
        raise FileNotFoundError(
            f"Mesogeos Track A files not found in {root}/. Run scripts/download_mesogeos.py, "
            "or run with --synthetic."
        )
    frames, raw_rows, raw_samples, duplicates, incomplete = [], 0, 0, 0, 0
    for path, label in ((pos_path, 1), (neg_path, 0)):
        raw = pd.read_csv(path)
        raw_rows += len(raw)
        raw_samples += raw["sample"].nunique()
        duplicates += int(raw.duplicated(["sample", "time_idx"]).sum())
        raw = raw.drop_duplicates(["sample", "time_idx"])
        raw["time"] = pd.to_datetime(raw["time"])
        cell_days, n_incomplete = _samples_to_cell_days(raw, label)
        incomplete += n_incomplete
        frames.append(cell_days)
    df = pd.concat(frames, ignore_index=True).rename(columns=MESOGEOS_RENAME)
    df = df.rename(columns={"time": "date", "x": "lon", "y": "lat"})
    # Drop columns that describe the fire outcome itself (leakage).
    df = df.drop(columns=[c for c in OUTCOME_COLUMNS if c in df.columns])
    n_before = len(df)
    df = _downsample_negatives(df, neg_pos_ratio, seed)

    features = feature_columns(df)
    report = {
        "raw_rows": raw_rows,
        "raw_samples": raw_samples,
        "removed_duplicate_rows": duplicates,
        "removed_incomplete_samples": incomplete,
        "removed_surplus_negatives": n_before - len(df),
        "clean_samples": len(df),
        "positives": int(df[LABEL].sum()),
        "negatives": int((df[LABEL] == 0).sum()),
        "feature_count": len(features),
        "missing_rate": {c: round(float(df[c].isna().mean()), 4) for c in features if df[c].isna().any()},
        "file_size_mb": round((pos_path.stat().st_size + neg_path.stat().st_size) / 1e6, 1),
    }
    return df, report


def load_mesogeos_track_a(root: str | Path = DEFAULT_MESOGEOS_DIR) -> pd.DataFrame:
    """Load Track A into one row per sample (see load_track_a_with_report)."""
    return load_track_a_with_report(root)[0]


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
    """Split by calendar year only: train 2006-2019, val 2020, test 2021-2022.

    Real samples are assigned by the year of their labelled day, like the official loader.
    """
    year = pd.to_datetime(df["target_date"] if "target_date" in df.columns else df["date"]).dt.year
    train = df[year.isin(list(TRAIN_YEARS))].reset_index(drop=True)
    val = df[year.isin(VAL_YEARS)].reset_index(drop=True)
    test = df[year.isin(TEST_YEARS)].reset_index(drop=True)
    return train, val, test
