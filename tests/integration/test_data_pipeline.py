"""I1: real Track A CSV files through the loader, the split and the data report."""
from pathlib import Path

import pandas as pd
import pytest

from ashaway.model.data import LABEL, OUTCOME_COLUMNS, feature_columns, load_track_a_with_report, temporal_split

SAMPLE_DIR = Path(__file__).parent.parent / "data" / "track_a_sample"


@pytest.fixture(scope="module")
def loaded():
    return load_track_a_with_report(SAMPLE_DIR)


def test_I1_model_never_sees_the_labelled_day(loaded):
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


def test_I1_split_and_report_match_the_known_sample(loaded):
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


def test_I1_incomplete_samples_are_dropped_and_reported(tmp_path):
    for name in ("positives.csv", "negatives.csv"):
        raw = pd.read_csv(SAMPLE_DIR / name)
        first = raw["sample"].iloc[0]
        raw[~((raw["sample"] == first) & (raw["time_idx"] == 5))].to_csv(tmp_path / name, index=False)
    df, report = load_track_a_with_report(tmp_path)
    assert report["removed_incomplete_samples"] == 2
    assert df[LABEL].sum() == 35


def test_I1_missing_files_name_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_mesogeos"):
        load_track_a_with_report(tmp_path)
