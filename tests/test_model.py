import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score, fbeta_score

from ashaway.model.data import BASE_FEATURES, LABEL, feature_columns, make_synthetic_cell_days, temporal_split
from ashaway.model.xgb import (
    choose_threshold_f2,
    evaluate,
    evaluate_scores,
    fwi_baseline_scores,
    load_model,
    save_model,
    train_xgb,
)

FAST = {"n_estimators": 150, "early_stopping_rounds": 20}


@pytest.fixture(scope="module")
def synth():
    return make_synthetic_cell_days(n=12000, seed=1)


@pytest.fixture(scope="module")
def trained(synth):
    train, val, test = temporal_split(synth)
    features = feature_columns(synth)
    return train_xgb(train, val, features, FAST), train, val, test, features


def test_synthetic_schema_and_positive_rate(synth):
    for col in BASE_FEATURES + ["date", "cell_id", "lon", "lat", LABEL]:
        assert col in synth.columns
    assert 0.02 <= synth[LABEL].mean() <= 0.05
    assert synth["lon"].between(19, 30).all() and synth["lat"].between(34, 42).all()
    assert set(feature_columns(synth)) == set(BASE_FEATURES)
    assert make_synthetic_cell_days(500, seed=3).equals(make_synthetic_cell_days(500, seed=3))


def test_temporal_split_years_and_no_overlap(synth):
    train, val, test = temporal_split(synth)
    years = [set(pd.to_datetime(p["date"]).dt.year) for p in (train, val, test)]
    assert years[0] <= set(range(2006, 2020))
    assert years[1] == {2020}
    assert years[2] <= {2021, 2022}
    assert pd.to_datetime(train["date"]).max() < pd.to_datetime(val["date"]).min()
    assert pd.to_datetime(val["date"]).max() < pd.to_datetime(test["date"]).min()
    assert len(train) + len(val) + len(test) == len(synth)


def test_threshold_maximises_f2_on_toy_case():
    y = np.array([0, 0, 0, 0, 1, 0, 1, 1])
    p = np.array([0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 0.9])
    t = choose_threshold_f2(y, p)
    assert 0.0 <= t <= 1.0
    best = max(fbeta_score(y, (p >= c).astype(int), beta=2) for c in p)
    assert fbeta_score(y, (p >= t).astype(int), beta=2) == pytest.approx(best)
    assert t == pytest.approx(0.4)


def test_evaluate_returns_valid_metrics(trained):
    model, _, _, test, features = trained
    m = evaluate(model, test, features, threshold=0.5)
    for key in ("pr_auc", "auroc", "f2", "brier", "threshold", "n", "positive_rate"):
        assert key in m
    for key in ("pr_auc", "auroc", "f2", "brier", "positive_rate"):
        assert 0.0 <= m[key] <= 1.0
    b = evaluate_scores(test[LABEL].to_numpy(), fwi_baseline_scores(test), 0.5)
    assert b["brier"] is None and 0.0 <= b["auroc"] <= 1.0


def test_xgb_beats_random_on_pr_auc(trained):
    model, _, _, test, features = trained
    p = model.predict_proba(test[features])[:, 1]
    rng = np.random.default_rng(0)
    random_pr = average_precision_score(test[LABEL], rng.random(len(test)))
    assert average_precision_score(test[LABEL], p) > 2 * random_pr


def test_save_load_roundtrip(trained, tmp_path):
    model, _, _, test, features = trained
    path = save_model(model, tmp_path / "m.json")
    again = load_model(path)
    np.testing.assert_allclose(
        model.predict_proba(test[features])[:, 1], again.predict_proba(test[features])[:, 1], rtol=0, atol=1e-7
    )
