"""I2: real sample data through training, calibration, saving and reloading."""
import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from ashaway.model.bundle import ModelBundle, load_bundle
from ashaway.model.data import LABEL, LIVE_FEATURES, feature_columns, load_mesogeos_track_a, make_synthetic_cell_days, temporal_split
from ashaway.model.train import build_live_bundle, evaluation_subsets, format_table, run_real
from ashaway.model.xgb import evaluate, load_model, save_model, train_xgb

SAMPLE_DIR = Path(__file__).parent.parent / "data" / "track_a_sample"
FAST = {"n_estimators": 150, "early_stopping_rounds": 20}


@pytest.fixture(scope="module")
def splits():
    return temporal_split(load_mesogeos_track_a(SAMPLE_DIR))


@pytest.fixture(scope="module")
def trained_bundle(splits) -> ModelBundle:
    train, val, _ = splits
    return build_live_bundle(train, val, version="test")


def test_I2_saved_bundle_reproduces_identical_predictions(trained_bundle, splits, tmp_path):
    _, _, test = splits
    again = load_bundle(trained_bundle.save(tmp_path / "v"))
    np.testing.assert_array_equal(trained_bundle.predict(test), again.predict(test))
    assert again.features == LIVE_FEATURES
    assert again.medium_from == trained_bundle.medium_from and again.high_from == trained_bundle.high_from


def test_I2_bundle_outputs_probabilities_and_contributions(trained_bundle, splits):
    _, _, test = splits
    p = trained_bundle.predict(test)
    assert ((p >= 0) & (p <= 1)).all()
    assert trained_bundle.medium_from <= trained_bundle.high_from
    contrib = trained_bundle.contributions(test)
    assert list(contrib.columns) == LIVE_FEATURES
    assert len(contrib) == len(test)


def test_I2_real_run_writes_a_complete_training_record(tmp_path):
    report = tmp_path / "record.json"
    results = run_real(SAMPLE_DIR, report, tmp_path / "live-test")
    saved = json.loads(report.read_text())
    assert saved["splits"]["train_2006_2019"] == {"n": 36, "percent": 33.3, "positives": 12}
    assert {"raw_rows", "clean_samples", "missing_rate", "feature_count", "file_size_mb"} <= set(saved["data_report"])
    assert set(saved["models"]) == {
        "baseline_fwi_proxy", "logistic_regression", "random_forest", "xgboost_all_features", "xgboost_live",
    }
    record = saved["models"]["xgboost_live"]
    assert {"train_seconds", "latency_ms_per_1000", "boosting_rounds", "features", "threshold"} <= set(record)
    assert {"recall", "precision", "f2", "pr_auc", "auroc", "brier"} <= set(record["metrics"]["test"])
    assert load_bundle(tmp_path / "live-test").version == "live-test"
    assert "xgboost_live" in format_table(results, splits=("val", "test"))


def test_I2_evaluation_subsets_keep_only_greece_and_season(splits):
    _, _, test = splits
    parts = evaluation_subsets(test)
    assert len(parts["test"]) == len(test)
    assert set(parts["test_may_oct"]["target_date"].dt.month) <= set(range(5, 11))
    assert len(parts["test_greece_may_oct"]) <= min(len(parts["test_greece"]), len(parts["test_may_oct"]))


def test_I2_model_learns_a_known_signal_on_synthetic_data(tmp_path):
    # Synthetic data has a signal by construction, so this checks the pipeline and not real skill.
    synth = make_synthetic_cell_days(n=12000, seed=1)
    train, val, test = temporal_split(synth)
    features = feature_columns(synth)
    model = train_xgb(train, val, features, FAST)
    p = model.predict_proba(test[features])[:, 1]
    random_scores = np.random.default_rng(0).random(len(test))
    assert average_precision_score(test[LABEL], p) > 2 * average_precision_score(test[LABEL], random_scores)
    for key in ("pr_auc", "auroc", "f2", "brier"):
        assert 0.0 <= evaluate(model, test, features, threshold=0.5)[key] <= 1.0
    again = load_model(save_model(model, tmp_path / "m.json"))
    np.testing.assert_allclose(p, again.predict_proba(test[features])[:, 1], rtol=0, atol=1e-7)
