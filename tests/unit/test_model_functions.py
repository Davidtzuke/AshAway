import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import fbeta_score

from ashaway.model.bundle import fit_calibration, high_threshold
from ashaway.model.data import BASE_FEATURES, LABEL, feature_columns, make_synthetic_cell_days, temporal_split
from ashaway.model.xgb import choose_threshold_f2, evaluate_scores


def test_U7_threshold_maximises_f2_on_toy_case():
    y = np.array([0, 0, 0, 0, 1, 0, 1, 1])
    p = np.array([0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 0.9])
    t = choose_threshold_f2(y, p)
    best = max(fbeta_score(y, (p >= c).astype(int), beta=2) for c in p)
    assert fbeta_score(y, (p >= t).astype(int), beta=2) == pytest.approx(best)
    assert t == pytest.approx(0.4)


def test_U7_calibration_is_monotonic_and_bounded():
    y = np.array([0, 0, 1, 0, 1, 1])
    raw = np.array([0.1, 0.2, 0.3, 0.4, 0.8, 0.9])
    xs, ys = fit_calibration(y, raw)
    assert xs == sorted(xs)
    assert ys == sorted(ys)
    assert min(ys) >= 0 and max(ys) <= 1


def test_U7_high_threshold_is_the_lowest_score_reaching_the_target_precision():
    y = np.array([0, 0, 1, 0, 1, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    # From 0.3: 4 of 5 alerts are fires (0.8). Lower scores do not reach 0.8.
    assert high_threshold(y, p, target_precision=0.8, floor=0.0) == pytest.approx(0.3)
    assert high_threshold(y, p, target_precision=0.8, floor=0.45) == pytest.approx(0.5)
    assert high_threshold(np.array([0, 0]), np.array([0.2, 0.4]), target_precision=0.8, floor=0.0) == 1.0


def test_metrics_stay_defined_for_a_single_class_subset():
    m = evaluate_scores(np.array([0, 0]), np.array([0.1, 0.9]), 0.5, probabilistic=True)
    assert m["n"] == 2 and m["auroc"] is None and m["recall"] is None


def test_synthetic_generator_schema_and_positive_rate():
    synth = make_synthetic_cell_days(n=5000, seed=1)
    for col in BASE_FEATURES + ["date", "cell_id", "lon", "lat", LABEL]:
        assert col in synth.columns
    assert 0.02 <= synth[LABEL].mean() <= 0.05
    assert set(feature_columns(synth)) == set(BASE_FEATURES)
    assert make_synthetic_cell_days(500, seed=3).equals(make_synthetic_cell_days(500, seed=3))


def test_temporal_split_years_and_no_overlap():
    synth = make_synthetic_cell_days(n=5000, seed=1)
    train, val, test = temporal_split(synth)
    years = [set(pd.to_datetime(p["date"]).dt.year) for p in (train, val, test)]
    assert years[0] <= set(range(2006, 2020))
    assert years[1] == {2020}
    assert years[2] <= {2021, 2022}
    assert len(train) + len(val) + len(test) == len(synth)
