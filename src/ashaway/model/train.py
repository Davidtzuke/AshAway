"""Train, compare and record the fire-danger models.

    python -m ashaway.model.train --synthetic
    python -m ashaway.model.train --data-dir data/raw/mesogeos

On real data this compares the proxy baseline, logistic regression, random forest
and XGBoost (AI1), writes the training record (NFR8) and saves the calibrated
weather + static model the product uses.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..geo import in_greece
from .bundle import DEFAULT_BUNDLE_DIR, ModelBundle, fit_calibration, high_threshold
from .data import (
    DEFAULT_MESOGEOS_DIR,
    LABEL,
    LIVE_FEATURES,
    feature_columns,
    load_track_a_with_report,
    make_synthetic_cell_days,
    temporal_split,
)
from .xgb import (
    DEFAULT_MODEL_PATH,
    DEFAULT_PARAMS,
    choose_threshold_f2,
    evaluate,
    evaluate_scores,
    fwi_baseline_scores,
    save_model,
    train_xgb,
)

log = logging.getLogger("ashaway.model.train")

SYNTHETIC_BANNER = "SYNTHETIC DATA: these numbers test the pipeline only. They are NOT model results."
HIGH_RISK_PRECISION = 0.75  # at least 3 in 4 validation "high" results should be real fires
SEASON_MONTHS = (5, 6, 7, 8, 9, 10)  # AshAway's scope is May to October
LATENCY_ROWS = 1000


def evaluation_subsets(test: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The test years as a whole and the parts AshAway actually advises on (AI4)."""
    season = pd.to_datetime(test["target_date"]).dt.month.isin(SEASON_MONTHS).to_numpy()
    greece = in_greece(test["lon"].to_numpy(), test["lat"].to_numpy())
    return {
        "test": test,
        "test_may_oct": test[season],
        "test_greece": test[greece],
        "test_greece_may_oct": test[greece & season],
    }


def _sklearn_models() -> dict[str, object]:
    return {
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        ),
        "random_forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=400, min_samples_leaf=5, class_weight="balanced", n_jobs=-1, random_state=42
            ),
        ),
    }


def _latency_ms(predict, df: pd.DataFrame) -> float:
    batch = df.sample(LATENCY_ROWS, replace=True, random_state=0)
    start = time.perf_counter()
    predict(batch)
    return round(1000 * (time.perf_counter() - start), 2)


def _record(model, cols: list[str], fit_seconds: float, val: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Tune the F2 threshold on validation, then score the validation and test parts with it."""
    score = lambda part: model.predict_proba(part[cols])[:, 1]  # noqa: E731
    thr = choose_threshold_f2(val[LABEL].to_numpy(), score(val))
    parts = {"val": val, **evaluation_subsets(test)}
    return {
        "features": cols,
        "threshold": thr,
        "train_seconds": round(fit_seconds, 2),
        "latency_ms_per_1000": _latency_ms(score, test),
        "metrics": {
            name: evaluate_scores(part[LABEL].to_numpy(), score(part), thr, probabilistic=True)
            for name, part in parts.items()
        },
    }


def compare_models(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict:
    """Fit every candidate on train, tune on val and report on the held-out test years."""
    results: dict[str, dict] = {}

    base_thr = choose_threshold_f2(val[LABEL].to_numpy(), fwi_baseline_scores(val, train))
    results["baseline_fwi_proxy"] = {
        "features": ["t2m_max", "rh_min", "wind_speed", "tp"],
        "threshold": base_thr,
        "metrics": {
            name: evaluate_scores(part[LABEL].to_numpy(), fwi_baseline_scores(part, train), base_thr)
            for name, part in {"val": val, **evaluation_subsets(test)}.items()
        },
    }

    for name, model in _sklearn_models().items():
        start = time.perf_counter()
        model.fit(train[features], train[LABEL])
        results[name] = _record(model, features, time.perf_counter() - start, val, test)

    for name, cols in (("xgboost_all_features", features), ("xgboost_live", LIVE_FEATURES)):
        start = time.perf_counter()
        model = train_xgb(train, val, cols)
        results[name] = _record(model, cols, time.perf_counter() - start, val, test)
        results[name]["boosting_rounds"] = int(model.best_iteration) + 1
    return results


def build_live_bundle(train: pd.DataFrame, val: pd.DataFrame, version: str) -> ModelBundle:
    """Train the weather + static model, calibrate it and tune the risk cut-offs on validation."""
    model = train_xgb(train, val, LIVE_FEATURES)
    y_val = val[LABEL].to_numpy()
    raw_val = model.predict_proba(val[LIVE_FEATURES])[:, 1]
    cal_x, cal_y = fit_calibration(y_val, raw_val)
    p_val = np.interp(raw_val, cal_x, cal_y)
    medium_from = choose_threshold_f2(y_val, p_val)
    return ModelBundle(
        version=version,
        features=list(LIVE_FEATURES),
        model=model,
        calibration_x=cal_x,
        calibration_y=cal_y,
        medium_from=medium_from,
        high_from=high_threshold(y_val, p_val, HIGH_RISK_PRECISION, floor=medium_from),
    )


def split_counts(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> dict:
    total = len(train) + len(val) + len(test)
    return {
        name: {"n": len(part), "percent": round(100 * len(part) / total, 1), "positives": int(part[LABEL].sum())}
        for name, part in (("train_2006_2019", train), ("val_2020", val), ("test_2021_2022", test))
    }


def run_real(data_dir: Path, report_path: Path, bundle_dir: Path) -> dict:
    df, data_report = load_track_a_with_report(data_dir)
    train, val, test = temporal_split(df)
    parts = {"val": val, **evaluation_subsets(test)}

    bundle = build_live_bundle(train, val, version=bundle_dir.name)
    bundle.save(bundle_dir)

    results = {
        "data": "mesogeos_track_a",
        "note": "Real Mesogeos Track A data. The 1:2 class ratio is by construction, so precision and "
        "calibrated probabilities are higher than at the real rate of fire days.",
        "data_report": data_report,
        "splits": split_counts(train, val, test),
        "subset_sizes": {name: len(part) for name, part in parts.items()},
        "xgboost_params": DEFAULT_PARAMS,
        "models": compare_models(train, val, test, feature_columns(df)),
        "live_bundle": {
            "version": bundle.version,
            "medium_from": bundle.medium_from,
            "high_from": bundle.high_from,
            "high_risk_precision_target": HIGH_RISK_PRECISION,
            "calibrated_metrics": {
                name: evaluate_scores(part[LABEL].to_numpy(), bundle.predict(part), bundle.medium_from, True)
                for name, part in parts.items()
            },
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    return results


def run_synthetic(report_path: Path, model_path: Path, n: int, seed: int) -> dict:
    log.warning(SYNTHETIC_BANNER)
    df = make_synthetic_cell_days(n=n, seed=seed)
    features = feature_columns(df)
    train, val, test = temporal_split(df)
    model = train_xgb(train, val, features)
    y_val = val[LABEL].to_numpy()
    thr = choose_threshold_f2(y_val, model.predict_proba(val[features])[:, 1])
    base_thr = choose_threshold_f2(y_val, fwi_baseline_scores(val, train))
    results = {
        "data": "synthetic",
        "note": SYNTHETIC_BANNER,
        "features": features,
        "params": {**DEFAULT_PARAMS, "best_iteration": int(model.best_iteration)},
        "fwi_baseline": {
            "val": evaluate_scores(y_val, fwi_baseline_scores(val, train), base_thr),
            "test": evaluate_scores(test[LABEL].to_numpy(), fwi_baseline_scores(test, train), base_thr),
        },
        "xgboost": {"val": evaluate(model, val, features, thr), "test": evaluate(model, test, features, thr)},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    save_model(model, model_path)
    return results


def format_table(results: dict, splits: tuple[str, ...] = ("val", "test", "test_greece_may_oct")) -> str:
    rows = [f"{'model':<24}{'split':<22}{'n':>6}{'PR-AUC':>8}{'AUROC':>8}{'recall':>8}{'prec':>7}{'F2':>7}{'Brier':>8}"]
    for name, entry in results["models"].items():
        for split in splits:
            m = entry["metrics"][split]
            brier = f"{m['brier']:.3f}" if m["brier"] is not None else "-"
            rows.append(
                f"{name:<24}{split:<22}{m['n']:>6}{m['pr_auc']:>8.3f}{m['auroc']:>8.3f}{m['recall']:>8.3f}"
                f"{m['precision']:>7.3f}{m['f2']:>7.3f}{brier:>8}"
            )
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", action="store_true", help="use the synthetic generator (pipeline test only)")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_MESOGEOS_DIR)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH, help="synthetic run only")
    ap.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    ap.add_argument("--n", type=int, default=25722, help="synthetic sample count")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.synthetic:
        report = args.report or Path("reports/xgb_metrics.json")
        run_synthetic(report, args.model_out, args.n, args.seed)
        print(SYNTHETIC_BANNER)
    else:
        report = args.report or Path("reports/training_record.json")
        results = run_real(args.data_dir, report, args.bundle_dir)
        print(format_table(results))
        print(json.dumps(results["live_bundle"], indent=2))
    print(f"report={report}")


if __name__ == "__main__":
    main()
