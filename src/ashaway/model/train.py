"""Train and evaluate the initial XGBoost fire-danger model.

    python3 -m ashaway.model.train --synthetic
    python3 -m ashaway.model.train --data-dir data/raw/mesogeos
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .data import DEFAULT_MESOGEOS_DIR, LABEL, feature_columns, load_mesogeos_track_a, make_synthetic_cell_days, temporal_split
from .xgb import DEFAULT_MODEL_PATH, DEFAULT_PARAMS, choose_threshold_f2, evaluate, evaluate_scores, fwi_baseline_scores, save_model, train_xgb

log = logging.getLogger("ashaway.model.train")

SYNTHETIC_BANNER = "SYNTHETIC DATA: these numbers test the pipeline only. They are NOT model results."


def run(synthetic: bool, data_dir: Path, report_path: Path, model_path: Path, n: int, seed: int) -> dict:
    if synthetic:
        log.warning(SYNTHETIC_BANNER)
        df = make_synthetic_cell_days(n=n, seed=seed)
    else:
        df = load_mesogeos_track_a(data_dir)
    features = feature_columns(df)
    train, val, test = temporal_split(df)
    for name, part in (("train", train), ("val", val), ("test", test)):
        log.info("%s: %d rows, %.2f%% positive", name, len(part), 100 * part[LABEL].mean())

    model = train_xgb(train, val, features)
    p_val = model.predict_proba(val[features])[:, 1]
    thr = choose_threshold_f2(val[LABEL].to_numpy(), p_val)

    base_val = fwi_baseline_scores(val)
    base_thr = choose_threshold_f2(val[LABEL].to_numpy(), base_val)

    results = {
        "data": "synthetic" if synthetic else f"mesogeos_track_a:{data_dir}",
        "note": SYNTHETIC_BANNER if synthetic else "Real Mesogeos Track A data.",
        "features": features,
        "params": {**DEFAULT_PARAMS, "best_iteration": int(model.best_iteration)},
        "splits": {"train": "2006-2019", "val": "2020", "test": "2021-2022"},
        "fwi_baseline": {
            "val": evaluate_scores(val[LABEL].to_numpy(), base_val, base_thr),
            "test": evaluate_scores(test[LABEL].to_numpy(), fwi_baseline_scores(test), base_thr),
        },
        "xgboost": {
            "val": evaluate(model, val, features, thr),
            "test": evaluate(model, test, features, thr),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    save_model(model, model_path)
    return results


def format_table(results: dict) -> str:
    rows = [f"{'model':<14}{'split':<6}{'PR-AUC':>8}{'AUROC':>8}{'F2':>8}{'Brier':>8}{'pos%':>7}"]
    for model in ("fwi_baseline", "xgboost"):
        for split in ("val", "test"):
            m = results[model][split]
            brier = f"{m['brier']:.4f}" if m["brier"] is not None else "-"
            rows.append(f"{model:<14}{split:<6}{m['pr_auc']:>8.3f}{m['auroc']:>8.3f}{m['f2']:>8.3f}"
                        f"{brier:>8}{100 * m['positive_rate']:>6.1f}%")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", action="store_true", help="use the synthetic generator (pipeline test only)")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_MESOGEOS_DIR)
    ap.add_argument("--report", type=Path, default=Path("reports/xgb_metrics.json"))
    ap.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--n", type=int, default=25722, help="synthetic sample count")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    results = run(args.synthetic, args.data_dir, args.report, args.model_out, args.n, args.seed)
    if args.synthetic:
        print(SYNTHETIC_BANNER)
    print(format_table(results))
    print(f"best_iteration={results['params']['best_iteration']}  report={args.report}  model={args.model_out}")


if __name__ == "__main__":
    main()
