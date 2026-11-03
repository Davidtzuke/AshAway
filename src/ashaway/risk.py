"""Turn a calibrated score into words a traveller can use (FR2, FR4, NFR6)."""
from __future__ import annotations

from typing import Callable

import pandas as pd

LOW, MEDIUM, HIGH = "low", "medium", "high"
LEVEL_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

LEVEL_TEXT = {
    LOW: "LOW: conditions look unfavourable for wildfire compared with past fire days.",
    MEDIUM: "MEDIUM: conditions resemble past fire days. Check official sources before you travel.",
    HIGH: "HIGH: conditions closely match past fire days. Consider other dates or places.",
}
DISCLAIMER = (
    "AshAway supports travel planning only. It does not replace official safety advice, "
    "and a lower risk level is not proof that a place is safe."
)

_KELVIN = 273.15

# Feature -> how to say it. The value shown is the input the model really used.
_SIGNALS: dict[str, Callable[[float], str]] = {
    "t2m_max": lambda v: f"High temperature the day before ({v - _KELVIN:.0f} C)",
    "t2m_max_7d": lambda v: f"Hottest day of the past week ({v - _KELVIN:.0f} C)",
    "rh_min": lambda v: f"Dry air the day before ({100 * v:.0f}% humidity)",
    "rh_min_7d": lambda v: f"Driest air of the past week ({100 * v:.0f}% humidity)",
    "wind_speed": lambda v: f"Wind the day before ({v:.1f} m/s)",
    "tp": lambda v: f"Rain the day before ({1000 * v:.1f} mm)",
    "rain_7d": lambda v: f"Rain over the past week ({1000 * v:.1f} mm)",
    "days_since_rain": lambda v: f"Days since the last rain ({v:.0f})",
    "dem": lambda v: f"Elevation ({v:.0f} m)",
    "slope": lambda v: f"Steepness of the terrain ({v:.1f})",
    "roads_distance": lambda v: f"Distance to roads ({v:.1f} km)",
    "population": lambda v: f"Population density ({v:.0f})",
    "lc_agriculture": lambda v: f"Farmland share of the area ({100 * v:.0f}%)",
    "lc_forest": lambda v: f"Forest share of the area ({100 * v:.0f}%)",
    "lc_grassland": lambda v: f"Grassland share of the area ({100 * v:.0f}%)",
    "lc_settlement": lambda v: f"Built-up share of the area ({100 * v:.0f}%)",
    "lc_shrubland": lambda v: f"Shrubland share of the area ({100 * v:.0f}%)",
    "lc_sparse_vegetation": lambda v: f"Sparse vegetation share of the area ({100 * v:.0f}%)",
    "lc_water_bodies": lambda v: f"Water share of the area ({100 * v:.0f}%)",
    "lc_wetland": lambda v: f"Wetland share of the area ({100 * v:.0f}%)",
}


def risk_level(probability: float, medium_from: float, high_from: float) -> str:
    """Map a score to a level. A score equal to a cut-off counts as the higher level."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {probability}")
    if medium_from > high_from:
        raise ValueError("medium_from must not exceed high_from")
    if probability >= high_from:
        return HIGH
    return MEDIUM if probability >= medium_from else LOW


def highest_level(levels: list[str]) -> str:
    return max(levels, key=LEVEL_ORDER.__getitem__)


def explain(contributions: pd.Series, values: pd.Series, top_n: int = 3) -> list[str]:
    """The inputs that pushed the score up most, in plain words, largest first (FR4)."""
    pushing_up = contributions[contributions > 0].sort_values(ascending=False, kind="stable").head(top_n)
    reasons = [_SIGNALS[name](float(values[name])) for name in pushing_up.index]
    return reasons or ["No input pushed the risk up for this day."]
