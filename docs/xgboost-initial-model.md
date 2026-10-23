# Initial XGBoost fire-danger model

Trello card: "Implement initial XGBoost model, if data supports it".
Code: `src/ashaway/model/` (data, xgb, train). Tests: `tests/test_model.py`.

## Data status

The pipeline currently runs on **synthetic data only**. The real training set is Mesogeos Track A (Kondylatos et al., Orion Lab NOA), and its CSVs sit in a Google Drive folder with no direct download URL, so we could not fetch them from a script within the time box.

To use the real data:

1. Open the Drive folder linked in the README of https://github.com/Orion-AI-Lab/mesogeos (rclone is the recommended client, see mesogeos issue #4).
2. Download `ml_tracks/a.fire_danger/positives.csv` and `negatives.csv`.
3. Put both files in `data/raw/mesogeos/` (git-ignored) and run `python3 -m ashaway.model.train --data-dir data/raw/mesogeos`.

`load_mesogeos_track_a` follows the schema in the official Track A loader: every sample is 30 daily rows (`sample`, `time`, features), and the label applies to the day after the window. We keep the last row of each sample as one cell-day, rename `t2m` and `rh` to our names, and drop `burned_area_has` because it describes the fire outcome. Track A has no FWI column, so on real data the baseline uses a rank-based hot/dry/windy proxy (`fire_danger_proxy`). The loader has not yet run against the real files; expect small column-name fixes on first contact.

`make_synthetic_cell_days(n, seed)` produces Greek cell-days for May to October, 2006 to 2022, with a 3.5% expected positive rate driven by heat, low humidity, wind, vegetation and road proximity. FWI in the synthetic set is a noisy function of the same weather, so a model with access to the raw drivers can beat it by construction. **Synthetic numbers measure nothing about real-world skill.**

## Features

Core: `t2m_max`, `rh_min`, `wind_speed`, `tp`, `ndvi`, `lai`, `fwi`, `roads_distance`, `population`. With real data the model also uses any Mesogeos columns present from `d2m`, `lst_day`, `lst_night`, `smi`, `sp`, `ssrd`, `dem`, `slope` and the `lc_*` land-cover fractions. Date, cell id, lon and lat are never features.

## Split

Temporal only, by calendar year: train 2006 to 2019, validation 2020, test 2021 to 2022. This matches the Mesogeos Track A split. No random shuffling across years.

## Model and parameters

`XGBClassifier` with hist trees, `max_depth=4`, `learning_rate=0.05`, up to 600 trees, `subsample=0.8`, `colsample_bytree=0.8`, `min_child_weight=5`, `scale_pos_weight` set from the train negative/positive ratio, and early stopping after 50 rounds without validation PR-AUC gain. The F2 threshold is chosen on validation and applied unchanged to test. The model saves as JSON to `models/xgb_fire_danger.json` and metrics go to `reports/xgb_metrics.json`.

## Metrics (SYNTHETIC run, seed 0, n = 25,722; NOT model results)

| Model | Split | PR-AUC | AUROC | F2 | Brier | Positive rate |
|---|---|---|---|---|---|---|
| FWI baseline | val 2020 | 0.097 | 0.705 | 0.257 | n/a | 3.0% |
| FWI baseline | test 2021-22 | 0.150 | 0.732 | 0.256 | n/a | 3.3% |
| XGBoost | val 2020 | 0.297 | 0.835 | 0.347 | 0.140 | 3.0% |
| XGBoost | test 2021-22 | 0.243 | 0.861 | 0.312 | 0.138 | 3.3% |

Early stopping picked 107 trees. These numbers only show that the pipeline trains, evaluates and beats a weak baseline on data built to allow it.

For reference, Kondylatos et al. (2022, Greece, 1 km) report FWI AUROC 0.693 (2020) and 0.794 (2021), and XGBoost 0.822 and 0.874. The evaluation code logs a leakage warning when any AUROC exceeds 0.92.

The Brier score is high because `scale_pos_weight` inflates predicted probabilities. Those scores rank well but are not calibrated risk.

## Next steps

1. Download Track A, run the real-data path, and fix any schema mismatches in the loader.
2. Compare against the published FWI and XGBoost AUROC figures; investigate anything above 0.92.
3. Add lagged aggregates from the 30-day window (7-day rain total, days since rain, max temperature trend).
4. Calibrate probabilities (isotonic on validation) before showing risk levels to travellers.
5. Report metrics per region and month to catch tourist-season blind spots.
