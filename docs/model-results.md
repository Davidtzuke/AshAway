# Model results on real data

First run on Mesogeos Track A, 3 November 2026. Reproduce with `python -m ashaway.model.train`. The full record, including latency and missing-value rates, is in `reports/training_record.json`.

## Data

| Split | Samples | Share | Positives |
|---|---|---|---|
| Train 2006-2019 | 19,353 | 75.2% | 6,451 |
| Validation 2020 | 2,262 | 8.8% | 754 |
| Test 2021-2022 | 4,107 | 16.0% | 1,369 |

The files hold 25,916 samples (777,480 rows, 217.8 MB). We remove 194 surplus negatives to keep 2 negatives per positive in each split, as the official loader does, which leaves 25,722. There are no duplicate rows or incomplete samples. Missing values are highest in `lst_night` (32.9%), `lst_day` (28.6%) and `smi` (12.2%).

## Results on the held-out test years

F2 thresholds are tuned on validation and applied unchanged. PR-AUC is also called AUPRC.

| Model | Mediterranean 2021-22 (n = 4,107) | | | Greece, May-Oct 2021-22 (n = 201) | | |
|---|---|---|---|---|---|---|
| | PR-AUC | AUROC | Recall | PR-AUC | AUROC | Recall |
| Baseline (hot/dry/windy proxy) | 0.505 | 0.723 | 0.961 | **0.698** | **0.883** | 0.979 |
| Logistic regression | 0.706 | 0.821 | 0.836 | 0.489 | 0.809 | 0.957 |
| Random forest | 0.801 | 0.888 | 0.936 | 0.557 | 0.862 | 0.979 |
| XGBoost, all 28 features | **0.838** | **0.906** | 0.922 | 0.658 | 0.872 | 0.936 |
| XGBoost, product inputs (20 features) | 0.806 | 0.888 | 0.949 | 0.595 | 0.840 | 0.936 |

The product model can't use the all-features version, because `ndvi`, `lai`, `smi` and land-surface temperature have no live feed yet. It uses weather and 7-day aggregates plus stored terrain, land cover, road and population values. After calibration it scores PR-AUC 0.788 and recall 0.946 on the Mediterranean test years, and PR-AUC 0.553 and recall 0.936 on the Greek subset.

## Checking the acceptance criteria (SRS AI3)

| Criterion | Product model | Result |
|---|---|---|
| Recall ≥ 0.80 on test years | 0.949 Mediterranean, 0.936 Greece | Met |
| AUPRC above the baseline | 0.806 vs 0.505 Mediterranean | Met |
| | 0.595 vs 0.698 Greece May-Oct | **Not met** |
| AUROC near published Greek results (0.82-0.87) | 0.840 Greece, 0.888 Mediterranean | Met in Greece, above the range overall |
| AUROC ≤ 0.92 (leakage check) | 0.888 | Met |

**Why the Greek result stands as it is.** We chose the product inputs on validation, where the model narrowly beat the baseline in Greece (PR-AUC 0.558 vs 0.539, on 90 samples and 16 fires). We then did not change anything after seeing the test years, since that would make the test score meaningless. With only 47 fires in the Greek test subset the gap is uncertain, but it counts as a failed criterion until more Greek data says otherwise.

## Limits of these numbers

- **The class ratio is artificial.** Track A has 1 positive per 2 negatives, while real fire days are far rarer. Real-world precision will be much lower than shown, and probabilities are relative scores rather than real chances of fire (T16).
- **Season helps the model.** Negatives are spread across the year, and fires cluster in summer. The May-October results are the fairer view: they are lower, and that is what AshAway's scope covers.
- **This is a cell-day score.** The SRS success metric for FR2 is recall on affected destinations at municipality level, and that has not been measured yet (T15).
- **Weather inputs in replay runs are reanalysis, not forecasts.** Real forecast weather is less accurate, so live skill will be lower.
