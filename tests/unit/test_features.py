from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ashaway.assess import HISTORY_DAYS, daily_feature_rows, lower_risk_alternatives
from ashaway.model.data import STATIC_FEATURES, fire_danger_proxy, percentile_of, window_features
from ashaway.model.xgb import fwi_baseline_scores


def test_U5_window_features_on_hand_computed_case():
    # 8 days, oldest first. 2 mm falls 2 days before the last day; 0.5 mm is below the rain-day limit.
    tp = np.array([[0.005, 0, 0, 0, 0, 0.002, 0.0005, 0]])
    t2m = np.array([[300.0, 301, 302, 303, 310, 305, 304, 303]])
    rh = np.array([[0.1, 0.5, 0.5, 0.4, 0.3, 0.2, 0.3, 0.4]])
    out = window_features(tp, t2m, rh)
    assert out["rain_7d"][0] == pytest.approx(0.0025)  # the first day is outside the 7-day window
    assert out["days_since_rain"][0] == 2
    assert out["t2m_max_7d"][0] == 310
    assert out["rh_min_7d"][0] == 0.2  # 0.1 on the first day is outside the window


def test_U5_window_features_with_no_rain_returns_the_window_length():
    dry = np.zeros((1, 29))
    out = window_features(dry, dry + 300, dry + 0.3)
    assert out["days_since_rain"][0] == 29
    assert out["rain_7d"][0] == 0


def test_U5_percentile_of_uses_only_the_reference():
    np.testing.assert_allclose(percentile_of([0, 25, 100], [10, 20, 30, 40]), [0.0, 0.5, 1.0])


def test_U5_baseline_scale_ignores_rows_outside_the_reference():
    # Regression test: the proxy used to rank over all years, so test data shaped the training features.
    train = pd.DataFrame({"t2m_max": [300.0, 310], "rh_min": [0.2, 0.4], "wind_speed": [2.0, 4], "tp": [0.0, 0.001]})
    test = train.iloc[[0]]
    extreme = pd.concat([test, train.assign(t2m_max=999.0)])
    assert fire_danger_proxy(test, train)[0] == fire_danger_proxy(extreme, train)[0]
    assert fwi_baseline_scores(test, train)[0] == fire_danger_proxy(test, train)[0]


def _weather(first: date, n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [first + timedelta(days=i) for i in range(n)],
        "t2m_max": [300.0 + i for i in range(n)],
        "rh_min": [0.3] * n,
        "wind_speed": [4.0] * n,
        "tp": [0.0] * n,
    })


STATIC = pd.Series({"cell_id": "c", **{c: 1.0 for c in STATIC_FEATURES}})


def test_U5_daily_row_uses_the_day_before_and_nothing_later():
    day = date(2023, 7, 30)
    weather = _weather(day - timedelta(days=HISTORY_DAYS), HISTORY_DAYS + 3)  # includes the day itself and later
    row = daily_feature_rows(weather, STATIC, [day]).iloc[0]
    assert row["date"] == day
    assert row["t2m_max"] == 300.0 + HISTORY_DAYS - 1  # value of the day before
    assert row["t2m_max_7d"] == 300.0 + HISTORY_DAYS - 1


def test_U5_day_with_a_gap_in_its_history_gets_no_row():
    day = date(2023, 7, 30)
    weather = _weather(day - timedelta(days=HISTORY_DAYS), HISTORY_DAYS)
    weather.loc[5, "tp"] = np.nan
    assert daily_feature_rows(weather, STATIC, [day]).empty


def candidate(name, level, peak, comparable=True):
    return {"id": name, "name": name, "level": level, "peak_probability": peak, "comparable": comparable}


def test_U6_alternatives_are_lower_risk_comparable_and_ranked():
    candidates = [
        candidate("same_level", "high", 0.6),
        candidate("medium", "medium", 0.4),
        candidate("low", "low", 0.1),
        candidate("poor_coverage", "low", 0.01, comparable=False),
    ]
    assert [c["id"] for c in lower_risk_alternatives("high", candidates)] == ["low", "medium"]


def test_U6_alternatives_stop_at_the_limit():
    candidates = [candidate(f"p{i}", "low", i / 10) for i in range(5)]
    assert [c["id"] for c in lower_risk_alternatives("high", candidates)] == ["p0", "p1", "p2"]


def test_U6_no_alternative_is_offered_when_nothing_is_lower():
    assert lower_risk_alternatives("medium", [candidate("a", "medium", 0.3), candidate("b", "high", 0.9)]) == []
