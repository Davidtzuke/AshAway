"""XGBoost training, evaluation, FWI baseline and model persistence."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, fbeta_score, roc_auc_score
from xgboost import XGBClassifier

from .data import LABEL

log = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path("models/xgb_fire_danger.json")
LEAKAGE_AUROC = 0.92

DEFAULT_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.05,
    "max_depth": 4,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "early_stopping_rounds": 50,
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "random_state": 42,
}


def train_xgb(train: pd.DataFrame, val: pd.DataFrame, features: list[str], params: dict | None = None) -> XGBClassifier:
    """Fit XGBoost with scale_pos_weight from the train class ratio and early stopping on val."""
    y = train[LABEL].to_numpy()
    n_pos = int(y.sum())
    if n_pos == 0:
        raise ValueError("training set has no positives")
    cfg = {**DEFAULT_PARAMS, "scale_pos_weight": (len(y) - n_pos) / n_pos, **(params or {})}
    model = XGBClassifier(**cfg)
    model.fit(train[features], y, eval_set=[(val[features], val[LABEL])], verbose=False)
    return model


def choose_threshold_f2(y: np.ndarray, p: np.ndarray) -> float:
    """Threshold in [0, 1] that maximises F2 on (y, p). Pick on validation only."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    candidates = np.unique(np.concatenate([p, [0.0, 1.0]]))
    if len(candidates) > 500:
        candidates = np.unique(np.quantile(p, np.linspace(0, 1, 501)))
    best_t, best_f = 0.5, -1.0
    for t in candidates:
        f = fbeta_score(y, (p >= t).astype(int), beta=2, zero_division=0)
        if f > best_f:
            best_t, best_f = float(t), f
    return float(np.clip(best_t, 0.0, 1.0))


def _metrics(y: np.ndarray, p: np.ndarray, threshold: float, probabilistic: bool) -> dict:
    y = np.asarray(y).astype(int)
    out = {
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "pr_auc": float(average_precision_score(y, p)),
        "auroc": float(roc_auc_score(y, p)),
        "threshold": float(threshold),
        "f2": float(fbeta_score(y, (p >= threshold).astype(int), beta=2, zero_division=0)),
        # Brier only makes sense for calibrated-ish probabilities, not raw FWI ranks.
        "brier": float(brier_score_loss(y, p)) if probabilistic else None,
    }
    if out["auroc"] > LEAKAGE_AUROC:
        log.warning("AUROC %.3f > %.2f: suspiciously high for cell-level fire danger, check for leakage",
                    out["auroc"], LEAKAGE_AUROC)
    return out


def evaluate(model: XGBClassifier, df: pd.DataFrame, features: list[str], threshold: float) -> dict:
    """PR-AUC, AUROC, F2 at a fixed threshold and Brier score for the model on df."""
    p = model.predict_proba(df[features])[:, 1]
    return _metrics(df[LABEL].to_numpy(), p, threshold, probabilistic=True)


def fwi_baseline_scores(df: pd.DataFrame) -> np.ndarray:
    """FWI-only baseline: the fire weather index is the score, rescaled to [0, 1] by percentile."""
    return df["fwi"].rank(pct=True).to_numpy()


def evaluate_scores(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    """Metrics for a non-probabilistic score such as the FWI baseline (no Brier)."""
    return _metrics(y, scores, threshold, probabilistic=False)


def save_model(model: XGBClassifier, path: str | Path = DEFAULT_MODEL_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(path)
    return path


def load_model(path: str | Path = DEFAULT_MODEL_PATH) -> XGBClassifier:
    model = XGBClassifier()
    model.load_model(Path(path))
    return model
