import pandas as pd
import pytest

from ashaway.risk import HIGH, LOW, MEDIUM, explain, highest_level, risk_level


@pytest.mark.parametrize(
    "probability, expected",
    [(0.0, LOW), (0.199, LOW), (0.2, MEDIUM), (0.499, MEDIUM), (0.5, HIGH), (1.0, HIGH)],
)
def test_U2_risk_level_at_the_cut_offs(probability, expected):
    assert risk_level(probability, medium_from=0.2, high_from=0.5) == expected


@pytest.mark.parametrize("probability", [-0.01, 1.01, float("nan")])
def test_U2_risk_level_rejects_a_value_that_is_not_a_probability(probability):
    with pytest.raises(ValueError):
        risk_level(probability, medium_from=0.2, high_from=0.5)


def test_U2_risk_level_rejects_cut_offs_in_the_wrong_order():
    with pytest.raises(ValueError):
        risk_level(0.3, medium_from=0.5, high_from=0.2)


def test_highest_level_picks_the_worst_day():
    assert highest_level([LOW, HIGH, MEDIUM]) == HIGH


def test_explain_lists_what_raised_the_risk_largest_first():
    contributions = pd.Series({"t2m_max": 0.2, "wind_speed": 0.9, "tp": -0.5, "rh_min": 0.4})
    values = pd.Series({"t2m_max": 313.15, "wind_speed": 9.6, "tp": 0.0, "rh_min": 0.15})
    assert explain(contributions, values, top_n=2) == [
        "Wind the day before (9.6 m/s)",
        "Dry air the day before (15% humidity)",
    ]


def test_explain_says_so_when_nothing_raised_the_risk():
    contributions = pd.Series({"tp": -0.5})
    assert explain(contributions, pd.Series({"tp": 0.01})) == ["No input pushed the risk up for this day."]
