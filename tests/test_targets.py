import pandas as pd
import pytest

from ashaway.targets import PredictionTarget, haversine_km, label_affected, temporal_split

MUNIS = pd.DataFrame({"municipality_code": ["M1"], "lon": [23.0], "lat": [38.0]})
D = pd.Timestamp("2021-08-10")
EMPTY_FIRMS = pd.DataFrame(columns=["lon", "lat", "date"])
EMPTY_EFFIS = pd.DataFrame(columns=["municipality_code", "fire_start"])
EMPTY_HFS = pd.DataFrame(columns=["municipality_code", "date", "severity"])


def _label(firms=EMPTY_FIRMS, effis=EMPTY_EFFIS, hfs=EMPTY_HFS, config=PredictionTarget()):
    return label_affected(MUNIS, [D], firms, effis, hfs, config).iloc[0]


def _lat_offset(km):
    # degrees of latitude for a north offset of `km` along the meridian
    return km / haversine_km(0.0, 0.0, 0.0, 1.0)


@pytest.mark.parametrize("offset,expected", [(0, False), (1, True), (7, True), (8, False)])
def test_horizon_window_is_d_plus_1_to_d_plus_7(offset, expected):
    effis = pd.DataFrame({"municipality_code": ["M1"], "fire_start": [D + pd.Timedelta(days=offset)]})
    assert bool(_label(effis=effis).affected) is expected


def test_firms_radius_boundary():
    def firms_at(km):
        return pd.DataFrame({"lon": [23.0], "lat": [38.0 + _lat_offset(km)], "date": [D + pd.Timedelta(days=2)]})

    assert bool(_label(firms=firms_at(19.9)).cond_firms)
    assert not bool(_label(firms=firms_at(20.1)).cond_firms)


def test_each_condition_alone_triggers():
    day = D + pd.Timedelta(days=3)
    firms = pd.DataFrame({"lon": [23.0], "lat": [38.0], "date": [day]})
    effis = pd.DataFrame({"municipality_code": ["M1"], "fire_start": [day]})
    hfs = pd.DataFrame({"municipality_code": ["M1"], "date": [day], "severity": [3]})

    for kwargs, col in [({"firms": firms}, "cond_firms"), ({"effis": effis}, "cond_effis"), ({"hfs": hfs}, "cond_hfs")]:
        row = _label(**kwargs)
        assert bool(row.affected)
        assert bool(row[col])
        others = {"cond_firms", "cond_effis", "cond_hfs"} - {col}
        assert not any(bool(row[c]) for c in others)

    assert not bool(_label().affected)


def test_hfs_severity_threshold():
    hfs = pd.DataFrame({"municipality_code": ["M1"], "date": [D + pd.Timedelta(days=1)], "severity": [2]})
    assert bool(_label(hfs=hfs, config=PredictionTarget(min_severity=2)).cond_hfs)
    assert not bool(_label(hfs=hfs, config=PredictionTarget(min_severity=3)).cond_hfs)


def test_other_municipality_events_do_not_leak():
    effis = pd.DataFrame({"municipality_code": ["M2"], "fire_start": [D + pd.Timedelta(days=1)]})
    assert not bool(_label(effis=effis).affected)


def test_temporal_split_has_no_date_overlap():
    df = pd.DataFrame({"date": pd.date_range("2005-12-25", "2023-01-05", freq="D")})
    train, val, test = temporal_split(df)
    assert train.date.min() == pd.Timestamp("2006-01-01")
    assert train.date.max() == pd.Timestamp("2019-12-31")
    assert val.date.min() == pd.Timestamp("2020-01-01") and val.date.max() == pd.Timestamp("2020-12-31")
    assert test.date.min() == pd.Timestamp("2021-01-01") and test.date.max() == pd.Timestamp("2022-12-31")
    sets = [set(s.date) for s in (train, val, test)]
    assert not (sets[0] & sets[1]) and not (sets[1] & sets[2]) and not (sets[0] & sets[2])
