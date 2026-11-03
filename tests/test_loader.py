from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ashaway.model.data import (
    LABEL,
    OUTCOME_COLUMNS,
    feature_columns,
    fire_danger_proxy,
    load_track_a_with_report,
    percentile_of,
    temporal_split,
    window_features,
)
from ashaway.model.xgb import fwi_baseline_scores

SAMPLE_DIR = Path(__file__).parent / "data" / "track_a_sample"


@pytest.fixture(scope="module")
def loaded():
    return load_track_a_with_report(SAMPLE_DIR)


def test_window_features_on_hand_computed_case():
    # 8 days, oldest first. Rain of 2 mm falls 2 days before the last day; 0.5 mm is below the rain-day limit.
    tp = np.array([[0.005, 0, 0, 0, 0, 0.002, 0.0005, 0]])
    t2m = np.array([[300.0, 301, 302, 303, 310, 305, 304, 303]])
    rh = np.array([[0.1, 0.5, 0.5, 0.4, 0.3, 0.2, 0.3, 0.4]])
    out = window_features(tp, t2m, rh)
    assert out["rain_7d"][0] == pytest.approx(0.0025)
    assert out["days_since_rain"][0] == 2
    assert out["t2m_max_7d"][0] == 310
    assert out["rh_min_7d"][0] == 0.2


def test_window_features_with_no_rain_returns_window_length():
    dry = np.zeros((1, 29))
    out = window_features(dry, dry + 300, dry + 0.3)
    assert out["days_since_rain"][0] == 29
    assert out["rain_7d"][0] == 0


def test_percentile_of_uses_only_the_reference():
    np.testing.assert_allclose(percentile_of([0, 25, 100], [10, 20, 30, 40]), [0.0, 0.5, 1.0])


def test_baseline_scale_ignores_rows_outside_the_reference():
    # Regression test: the proxy used to rank over all years, so test data shaped the training features.
    train = pd.DataFrame({"t2m_max": [300.0, 310], "rh_min": [0.2, 0.4], "wind_speed": [2.0, 4], "tp": [0.0, 0.001]})
    test = train.iloc[[0]]
    extreme = pd.concat([test, train.assign(t2m_max=999.0)])
    assert fire_danger_proxy(test, train)[0] == fire_danger_proxy(extreme, train)[0]
    assert fwi_baseline_scores(test, train)[0] == fire_danger_proxy(test, train)[0]


def test_loader_never_shows_the_labelled_day_to_the_model(loaded):
    df, _ = loaded
    raw = pd.read_csv(SAMPLE_DIR / "positives.csv")
    sample_id = int(raw["sample"].iloc[0])
    row = df[df["cell_id"] == f"p{sample_id}"].iloc[0]
    issue_day = raw[(raw["sample"] == sample_id) & (raw["time_idx"] == 28)].iloc[0]
    fire_day = raw[(raw["sample"] == sample_id) & (raw["time_idx"] == 29)].iloc[0]
    assert row["t2m_max"] == issue_day["t2m"]
    assert row["date"] == pd.Timestamp(issue_day["time"])
    assert row["target_date"] == pd.Timestamp(fire_day["time"])
    assert (pd.to_datetime(df["target_date"]) - pd.to_datetime(df["date"])).dt.days.eq(1).all()
    assert not set(OUTCOME_COLUMNS) & set(df.columns)
    assert not set(OUTCOME_COLUMNS + ("target_date", "date", "cell_id", "lon", "lat", LABEL)) & set(feature_columns(df))


def test_loader_split_and_report_on_real_sample(loaded):
    df, report = loaded
    train, val, test = temporal_split(df)
    # 12 positives and 26 negatives per split in the sample; negatives are cut to 2:1.
    assert (len(train), len(val), len(test)) == (36, 36, 36)
    for part in (train, val, test):
        assert part[LABEL].sum() == 12
    assert set(pd.to_datetime(val["target_date"]).dt.year) == {2020}
    assert report["raw_samples"] == 114
    assert report["raw_rows"] == 114 * 30
    assert report["removed_surplus_negatives"] == 6
    assert report["clean_samples"] == 108
    assert report["feature_count"] == len(feature_columns(df))
    assert report["file_size_mb"] > 0
    assert set(report["missing_rate"]) <= set(feature_columns(df))


def test_loader_drops_incomplete_samples_and_reports_them(tmp_path):
    for name in ("positives.csv", "negatives.csv"):
        raw = pd.read_csv(SAMPLE_DIR / name)
        first = raw["sample"].iloc[0]
        raw[~((raw["sample"] == first) & (raw["time_idx"] == 5))].to_csv(tmp_path / name, index=False)
    df, report = load_track_a_with_report(tmp_path)
    assert report["removed_incomplete_samples"] == 2
    assert df[LABEL].sum() == 35


def test_loader_names_the_fix_when_files_are_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_mesogeos"):
        load_track_a_with_report(tmp_path)
