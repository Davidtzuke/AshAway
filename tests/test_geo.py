import pandas as pd
import pytest

from ashaway import geo


def test_lau_codes_group_by_first_four_chars():
    assert geo.municipality_code_from_lau("01010101") == "0101"
    assert geo.municipality_code_from_lau(" 0101 0202") == "0101"
    with pytest.raises(ValueError):
        geo.municipality_code_from_lau("01")


def test_mount_athos_excluded_by_default():
    laus = ["01010101", "01010102", "01020101", geo.MOUNT_ATHOS_CODE + "0101"]
    assert geo.municipality_codes_from_lau(laus) == ["0101", "0102"]
    assert geo.MOUNT_ATHOS_CODE in geo.municipality_codes_from_lau(laus, exclude_athos=False)
    assert geo.N_LAU_GROUPS == geo.N_MUNICIPALITIES + 1


def test_laea_matches_epsg_reference_point():
    # IOGP Guidance Note 7-2 worked example for EPSG:3035: 50N 5E.
    x, y = geo._laea_forward(5.0, 50.0)
    assert x == pytest.approx(3962799.45, abs=0.01)
    assert y == pytest.approx(2999718.85, abs=0.01)


def test_cell_id_is_1km_and_deterministic():
    assert geo.cell_id(5400000.0, 1800000.0) == "1kmE5400N1800"
    assert geo.cell_id(5400999.9, 1800999.9) == "1kmE5400N1800"
    assert geo.cell_id(5401000.0, 1800000.0) == "1kmE5401N1800"
    athens = geo.cell_of_point(23.7275, 37.9838)
    assert athens == geo.cell_of_point(23.7275, 37.9838)
    assert athens.startswith("1kmE") and "N" in athens


def test_aggregate_cells_max_and_mean():
    df = pd.DataFrame(
        {
            "cell_id": ["a", "b", "c", "a"],
            "date": pd.to_datetime(["2021-08-01"] * 3 + ["2021-08-02"]),
            "prob": [0.1, 0.5, 0.9, 0.2],
        }
    )
    out = geo.aggregate_cells_to_municipality(df, {"a": "M1", "b": "M1", "c": "M2"})
    row = out[(out.municipality_code == "M1") & (out.date == "2021-08-01")].iloc[0]
    assert row.prob_max == pytest.approx(0.5)
    assert row.prob_mean == pytest.approx(0.3)
    assert row.n_cells == 2
    assert len(out) == 3
