"""Geographic units for AshAway.

Two spatial units are used:

* Training unit: a 1 km cell of the EEA reference grid (EPSG:3035, ETRS89-LAEA)
  per day, following Kondylatos et al. (2022) and the Mesogeos datacube.
* Product and evaluation unit: a Greek municipality (dimos) per day. Greece has
  332 municipalities under Kleisthenis I (L.4555/2018, in force since September
  2019). Cell probabilities are aggregated to municipality-day.

Eurostat/GISCO LAU units for Greece are local communities, not municipalities.
The first four characters of LAU_CODE identify the parent municipality, which
gives 333 groups: the 332 municipalities plus Mount Athos. Mount Athos is an
autonomous monastic state with no tourist accommodation market, so AshAway
excludes it from the product.

geopandas and pyproj are optional. Import them lazily so the core package works
with pandas and numpy alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

N_MUNICIPALITIES = 332
N_LAU_GROUPS = 333  # 332 municipalities + Mount Athos

# LAU_CODE[:4] prefix of the Mount Athos group in GISCO LAU data. Confirm against
# the GISCO release in use; override via the `athos_code` arguments if it differs.
MOUNT_ATHOS_CODE = "1001"
MOUNT_ATHOS_NAMES = ("Άγιο Όρος", "Agio Oros", "Mount Athos")

CRS_WGS84 = "EPSG:4326"
CRS_GRID = "EPSG:3035"  # ETRS89 / LAEA Europe
CELL_SIZE_M = 1000

# EPSG:3035 projection parameters (GRS80 ellipsoid)
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)
_LAT0 = math.radians(52.0)
_LON0 = math.radians(10.0)
_FE = 4321000.0
_FN = 3210000.0


@dataclass(frozen=True)
class GeoUnit:
    """A spatial unit an AshAway prediction refers to."""

    kind: str  # "cell" or "municipality"
    code: str  # cell id like "1kmE5400N1800", or 4-char municipality code
    name: str | None = None


def municipality_code_from_lau(lau_code: str) -> str:
    """Return the municipality code (first 4 characters) of a GISCO LAU code."""
    code = str(lau_code).strip()
    if len(code) < 4:
        raise ValueError(f"LAU code too short to contain a municipality prefix: {lau_code!r}")
    return code[:4]


def is_mount_athos(muni_code: str, athos_code: str = MOUNT_ATHOS_CODE) -> bool:
    return str(muni_code)[:4] == athos_code


def municipality_codes_from_lau(
    lau_codes, exclude_athos: bool = True, athos_code: str = MOUNT_ATHOS_CODE
) -> list[str]:
    """Group LAU codes into sorted unique municipality codes, dropping Athos by default."""
    codes = {municipality_code_from_lau(c) for c in lau_codes}
    if exclude_athos:
        codes.discard(athos_code)
    return sorted(codes)


def _q(sin_phi: float) -> float:
    es = _E * sin_phi
    return (1 - _E2) * (sin_phi / (1 - es * es) - (1 / (2 * _E)) * math.log((1 - es) / (1 + es)))


_QP = _q(1.0)
_Q0 = _q(math.sin(_LAT0))
_BETA0 = math.asin(_Q0 / _QP)
_RQ = _A * math.sqrt(_QP / 2)
_D = _A * math.cos(_LAT0) / (math.sqrt(1 - _E2 * math.sin(_LAT0) ** 2) * _RQ * math.cos(_BETA0))


def _laea_forward(lon: float, lat: float) -> tuple[float, float]:
    """Ellipsoidal Lambert Azimuthal Equal Area forward projection for EPSG:3035.

    Formula from IOGP Guidance Note 7-2, section 3.2.3 (EPSG method 9820).
    Returns (easting, northing) in metres.
    """
    phi = math.radians(lat)
    dlam = math.radians(lon) - _LON0
    beta = math.asin(_q(math.sin(phi)) / _QP)
    b = _RQ * math.sqrt(
        2 / (1 + math.sin(_BETA0) * math.sin(beta) + math.cos(_BETA0) * math.cos(beta) * math.cos(dlam))
    )
    x = _FE + b * _D * math.cos(beta) * math.sin(dlam)
    y = _FN + (b / _D) * (
        math.cos(_BETA0) * math.sin(beta) - math.sin(_BETA0) * math.cos(beta) * math.cos(dlam)
    )
    return x, y


def to_laea(lon: float, lat: float) -> tuple[float, float]:
    """Project WGS84 lon/lat to EPSG:3035 metres, using pyproj when installed."""
    try:
        from pyproj import Transformer
    except ImportError:
        return _laea_forward(lon, lat)
    t = Transformer.from_crs(CRS_WGS84, CRS_GRID, always_xy=True)
    return t.transform(lon, lat)


def cell_id(x: float, y: float) -> str:
    """EEA reference grid id of the 1 km cell containing EPSG:3035 point (x, y).

    The id encodes the lower-left corner in km, e.g. "1kmE5400N1800".
    """
    return f"1kmE{math.floor(x / CELL_SIZE_M)}N{math.floor(y / CELL_SIZE_M)}"


def cell_of_point(lon: float, lat: float) -> str:
    """EEA 1 km grid cell id for a WGS84 lon/lat point."""
    return cell_id(*to_laea(lon, lat))


def aggregate_cells_to_municipality(
    df: pd.DataFrame,
    cell_to_muni: pd.DataFrame | dict,
    prob_col: str = "prob",
    date_col: str = "date",
    cell_col: str = "cell_id",
) -> pd.DataFrame:
    """Aggregate cell-day probabilities to municipality-day.

    `cell_to_muni` maps cell ids to municipality codes, as a dict or a DataFrame
    with columns [cell_col, "municipality_code"]. A cell spanning a border may
    appear under several municipalities. Returns columns municipality_code, date,
    prob_max (the headline score), prob_mean, n_cells.
    """
    if isinstance(cell_to_muni, dict):
        mapping = pd.DataFrame(
            {cell_col: list(cell_to_muni.keys()), "municipality_code": list(cell_to_muni.values())}
        )
    else:
        mapping = cell_to_muni[[cell_col, "municipality_code"]]
    merged = df[[cell_col, date_col, prob_col]].merge(mapping, on=cell_col, how="inner")
    out = (
        merged.groupby(["municipality_code", date_col])[prob_col]
        .agg(prob_max="max", prob_mean="mean", n_cells="count")
        .reset_index()
    )
    return out


def load_municipalities_from_gisco(
    path: str,
    lau_col: str = "LAU_ID",
    country_col: str = "CNTR_CODE",
    exclude_athos: bool = True,
    athos_code: str = MOUNT_ATHOS_CODE,
):
    """Load GISCO LAU polygons and dissolve them into Greek municipalities.

    Requires geopandas (optional extra `geo`). LAU units are grouped by the first
    four characters of the LAU code. Mount Athos is dropped by default. Returns a
    GeoDataFrame in EPSG:3035 with municipality_code, geometry, and centroid
    lon/lat columns in WGS84.
    """
    import geopandas as gpd  # lazy: optional dependency

    gdf = gpd.read_file(path)
    if country_col in gdf.columns:
        gdf = gdf[gdf[country_col] == "EL"]
    gdf = gdf.copy()
    gdf["municipality_code"] = gdf[lau_col].map(municipality_code_from_lau)
    if exclude_athos:
        gdf = gdf[gdf["municipality_code"] != athos_code]
    munis = gdf[["municipality_code", "geometry"]].dissolve(by="municipality_code").reset_index()
    munis = munis.to_crs(CRS_GRID)
    centroids = munis.geometry.centroid.to_crs(CRS_WGS84)
    munis["lon"] = centroids.x
    munis["lat"] = centroids.y
    return munis
