import json
from pathlib import Path

import numpy as np
import pytest

from ashaway.model.bundle import ModelBundle, fit_calibration, high_threshold, load_bundle
from ashaway.model.data import LIVE_FEATURES, load_mesogeos_track_a, temporal_split
from ashaway.model.train import build_live_bundle, evaluation_subsets, format_table, run_real
from ashaway.model.xgb import evaluate_scores

SAMPLE_DIR = Path(__file__).parent / "data" / "track_a_sample"


@pytest.fixture(scope="module")
def splits():
    return temporal_split(load_mesogeos_track_a(SAMPLE_DIR))


@pytest.fixture(scope="module")
def bundle(splits) -> ModelBundle:
    train, val, _ = splits
    return build_live_bundle(train, val, version="test")


def test_calibration_is_monotonic_and_bounded():
    y = np.array([0, 0, 1, 0, 1, 1])
    raw = np.array([0.1, 0.2, 0.3, 0.4, 0.8, 0.9])
    xs, ys = fit_calibration(y, raw)
    assert xs == sorted(xs)
    assert ys == sorted(ys)
    assert min(ys) >= 0 and max(ys) <= 1


def test_high_threshold_is_lowest_score_reaching_target_precision():
    y = np.array([0, 0, 1, 0, 1, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    # From 0.4: 3 of 4 alerts are fires (0.75). From 0.3: 4 of 5 (0.8), which reaches the target first.
    assert high_threshold(y, p, target_precision=0.8, floor=0.0) == pytest.approx(0.3)
    assert high_threshold(y, p, target_precision=0.8, floor=0.45) == pytest.approx(0.5)
    assert high_threshold(np.array([0, 0]), np.array([0.2, 0.4]), target_precision=0.8, floor=0.0) == 1.0


def test_metrics_stay_defined_for_a_single_class_subset():
    m = evaluate_scores(np.array([0, 0]), np.array([0.1, 0.9]), 0.5, probabilistic=True)
    assert m["n"] == 2 and m["auroc"] is None and m["recall"] is None


def test_bundle_saved_and_reloaded_gives_identical_predictions(bundle, splits, tmp_path):
    _, _, test = splits
    again = load_bundle(bundle.save(tmp_path / "v"))
    np.testing.assert_array_equal(bundle.predict(test), again.predict(test))
    assert again.features == LIVE_FEATURES
    assert again.medium_from == bundle.medium_from and again.high_from == bundle.high_from


def test_bundle_outputs_probabilities_and_contributions(bundle, splits):
    _, _, test = splits
    p = bundle.predict(test)
    assert ((p >= 0) & (p <= 1)).all()
    assert bundle.medium_from <= bundle.high_from
    contrib = bundle.contributions(test)
    assert list(contrib.columns) == LIVE_FEATURES
    assert len(contrib) == len(test)


def test_real_run_writes_a_complete_training_record(tmp_path):
    report = tmp_path / "record.json"
    results = run_real(SAMPLE_DIR, report, tmp_path / "live-test")
    saved = json.loads(report.read_text())
    assert saved["splits"]["train_2006_2019"] == {"n": 36, "percent": 33.3, "positives": 12}
    assert {"raw_rows", "clean_samples", "missing_rate", "feature_count", "file_size_mb"} <= set(saved["data_report"])
    assert {
        "baseline_fwi_proxy", "logistic_regression", "random_forest", "xgboost_all_features", "xgboost_live",
    } == set(saved["models"])
    xgb_record = saved["models"]["xgboost_live"]
    assert {"train_seconds", "latency_ms_per_1000", "boosting_rounds", "features", "threshold"} <= set(xgb_record)
    assert {"recall", "precision", "f2", "pr_auc", "auroc", "brier"} <= set(xgb_record["metrics"]["test"])
    assert load_bundle(tmp_path / "live-test").version == "live-test"
    assert "xgboost_live" in format_table(results, splits=("val", "test"))


def test_evaluation_subsets_keep_only_greece_and_season(splits):
    _, _, test = splits
    parts = evaluation_subsets(test)
    assert len(parts["test"]) == len(test)
    assert pd_months(parts["test_may_oct"]) <= set(range(5, 11))
    assert len(parts["test_greece_may_oct"]) <= min(len(parts["test_greece"]), len(parts["test_may_oct"]))


def pd_months(df) -> set[int]:
    return set(df["target_date"].dt.month)
