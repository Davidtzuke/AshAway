"""A versioned model the product can use: XGBoost, its calibration and its risk cut-offs.

Everything is stored as JSON, so a prediction can be reproduced from the version
directory alone (NFR4).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

DEFAULT_BUNDLE_DIR = Path("models/live-v1")


@dataclass(frozen=True)
class ModelBundle:
    version: str
    features: list[str]
    model: XGBClassifier
    calibration_x: list[float]
    calibration_y: list[float]
    medium_from: float  # tuned on validation for F2, so recall comes first (NFR9)
    high_from: float  # lowest score that reaches the target precision on validation

    def raw_scores(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(df[self.features])[:, 1]

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Calibrated fire probability per row."""
        return np.interp(self.raw_scores(df), self.calibration_x, self.calibration_y)

    def contributions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Per-row SHAP contribution of each feature, in log-odds (positive raises the risk)."""
        matrix = xgb.DMatrix(df[self.features], feature_names=self.features)
        values = self.model.get_booster().predict(matrix, pred_contribs=True)
        return pd.DataFrame(values[:, :-1], columns=self.features, index=df.index)

    def save(self, directory: str | Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save_model(directory / "model.json")
        card = {
            "version": self.version,
            "features": self.features,
            "calibration_x": self.calibration_x,
            "calibration_y": self.calibration_y,
            "medium_from": self.medium_from,
            "high_from": self.high_from,
        }
        (directory / "card.json").write_text(json.dumps(card, indent=2))
        return directory


def load_bundle(directory: str | Path = DEFAULT_BUNDLE_DIR) -> ModelBundle:
    directory = Path(directory)
    card = json.loads((directory / "card.json").read_text())
    model = XGBClassifier()
    model.load_model(directory / "model.json")
    return ModelBundle(model=model, **card)


def fit_calibration(y: np.ndarray, raw: np.ndarray) -> tuple[list[float], list[float]]:
    """Isotonic calibration on validation scores, as (x, y) points for interpolation (AI5)."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw, y)
    return [float(v) for v in iso.X_thresholds_], [float(v) for v in iso.y_thresholds_]


def high_threshold(y: np.ndarray, p: np.ndarray, target_precision: float, floor: float) -> float:
    """Lowest score, no lower than `floor`, whose alerts reach `target_precision`."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    for t in np.unique(p):
        if t < floor:
            continue
        if y[p >= t].mean() >= target_precision:
            return float(t)
    return 1.0
