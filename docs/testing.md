# Test catalogue

```
pytest                 # everything
pytest -m unit         # one function at a time, no files or network
pytest -m integration  # several components working together
```

GitHub Actions runs both on every push and pull request (`.github/workflows/tests.yml`) and keeps the JUnit results. The tests need no network and no large download. Tests for a case below carry its id in their name, for example `test_U1_rejects_with_the_correct_reason`. Other tests cover smaller helpers.

## Test data

| Data | Where | Used by | Why |
|---|---|---|---|
| Small hand-computed values, written in the test | `tests/unit/` | U1-U8 | The expected answer can be checked by hand |
| 114 real Track A samples (3,420 rows): 12 positive and 26 negative per split | `tests/data/track_a_sample/` | I1, I2 | Real column names, gaps and fire-day rows, small enough for CI. Mesogeos, CC BY 4.0 |
| Recorded Open-Meteo weather and air quality responses, 2023 | `tests/data/feeds/` | I3-I6 | Real responses, including the July 2023 Rhodes heatwave. Open-Meteo, CC BY 4.0 |
| Hand-written FIRMS CSV files | `tests/data/feeds/*firms*.csv`, `no_fires.csv` | I3, I4 | **Not real detections.** They follow NASA's documented columns, because the FIRMS key isn't set up yet (T12) |
| Simulated HTTP 500 and missing key | `tests/conftest.py` | I4, I6 | A failing service on demand, which real feeds can't give |

## Unit tests

| ID | Unit | Input | Expected output | Requirement |
|---|---|---|---|---|
| U1 | `validate_request` | `atlantis`; `2-7-2026`; end before start; `2026-10-31` to `2026-11-01`; `2005-07-01`; end 15 days ahead | Rejected with `unsupported_place`, `invalid_date`, `reversed_dates`, `out_of_season`, `before_coverage`, `beyond_horizon` | FR1, FR9 |
| | | `rhodes`, 2 to 4 July, today 1 July | Accepted, with 3 days | FR1 |
| U2 | `risk_level` (cut-offs 0.2 and 0.5) | 0.199; 0.2; 0.499; 0.5 | low; medium; medium; high | FR2 |
| | | 1.01, or NaN | `ValueError` | FR2 |
| U3 | `is_stale`, `check_evidence` | Newest value 2 days old; 3 days old; none | Current; stale; stale | FR5 |
| | | Low forecast and 3 detections near the place | Conflict flagged | FR5 |
| U4 | `parse_weather` | 30 °C, 40%, 5 mm of rain | 303.15 K, 0.40, 0.005 m | NFR5 |
| | | Rain is `null` | NaN, not 0 | NFR5 |
| | | `{"error": true}`, or HTML | `ValueError` | NFR5 |
| U5 | `window_features`, `daily_feature_rows` | 8 days with 2 mm of rain 2 days ago | `rain_7d` 0.0025, `days_since_rain` 2 | AI2 |
| | | Weather that includes the day itself | Row uses only the day before | NFR9 |
| | | Gap in the 29-day history | No row | NFR5 |
| U6 | `lower_risk_alternatives` | High risk; candidates at high, medium, low, and low with poor coverage | Low then medium, others excluded | FR6, AI6 |
| U7 | `choose_threshold_f2`, `fit_calibration`, `high_threshold` | Toy labels and scores | Threshold 0.4; monotonic calibration; lowest score reaching the precision target | NFR9, AI5 |
| U8 | `in_greece` | Athens, Rhodes, Corfu; Izmir, Tirana, open sea | True; False | AI4 |

## Integration tests

| ID | Components | Input | Expected output | Requirement |
|---|---|---|---|---|
| I1 | Loader, split, data report | Real Track A sample | Inputs come from the day before the label, outcome columns gone; 36 samples per split at 2:1; report shows 114 raw, 6 removed, 108 clean | AI2, NFR2, NFR9 |
| I2 | Training, calibration, saving, loading | Real Track A sample | Reloaded model gives identical predictions; training record lists all 5 models and every NFR8 metric | NFR4, NFR8 |
| I3 | Feeds, features, saved model, service | Rhodes, 18 to 24 July 2023, recorded feeds | High; 7 days scored; every evidence item labelled, dated and sourced; nothing after 17 July used; disclaimer present | FR2-FR4, FR8, NFR3, NFR6 |
| | | Chania, 1 to 3 June 2023, no fires | Low | FR2 |
| | | Chania, same dates, 1 fire nearby | Insufficient evidence, conflict warning | FR5 |
| I4 | Feeds, service, under failure | Weather returns HTTP 500 | Insufficient evidence; no days, score or reasons; source marked unavailable | FR5, NFR5 |
| | | Fire feed down, or no key, with a low forecast | Insufficient evidence instead of low | FR5 |
| | | Fire feed down with a high forecast | High stays visible, with a warning | FR5 |
| | | Air quality down | Source marked unavailable; no air quality item | NFR5 |
| I5 | Service across destinations | Rhodes, 1 to 3 July 2023 | 1 to 3 alternatives, each strictly lower, sorted, "not proof of safety" | FR6, AI6 |
| | | Rhodes and Chania, same dates | One row each with risk, evidence age, sources | FR7 |
| I6 | Command line, service, feeds | `assess rhodes 2023-07-18 2023-07-24` | Exit 0; risk in words, reasons, labels, disclaimer | UR1-UR4, NFR6 |
| | | `assess atlantis ...`; December dates | Exit 2; the reason, and no risk level | FR9 |

## Do the tests detect bugs?

To check the suite can fail, we broke the code on purpose in 8 ways and ran it each time. All 8 were caught.

| Deliberate bug | Caught by |
|---|---|
| Loader feeds the fire day to the model | I1 |
| Negatives aren't cut to 2:1 | I1 |
| Score at a cut-off counts as the lower level | U2 |
| Low result shown despite missing evidence | I3 |
| Missing rain treated as zero | U4 |
| Humidity not converted to 0-1 | U4 |
| Features use the day itself, not the day before | I3 |
| Alternatives may have the same risk level | U6 |

## What these tests don't cover

- **Real FIRMS responses.** The adapter has only run against hand-written files (T12).
- **Live forecast weather.** Recorded responses are reanalysis from the archive service.
- **Model skill.** Tests check that the pipeline behaves correctly. Skill is measured in `docs/model-results.md`, and one acceptance criterion isn't met there.
- **User acceptance targets**, such as the percentage of test users completing a request. These need real users.

## Class demonstration

Run from the repository root, with the virtual environment active (Windows: `.venv\Scripts\activate`).

1. `pytest -m unit -v`, then `pytest -m integration -v`, to show all tests running by themselves. Point at one `U` and one `I` name, and open that test to show its input and expected output.
2. `ashaway assess rhodes 2023-07-18 2023-07-24`, for a real answer on the July 2023 Rhodes fires. It reads live Open-Meteo data, so it needs internet.
3. `ashaway assess atlantis 2023-07-18 2023-07-24`, to show a request being refused with its reason.
4. In `src/ashaway/risk.py`, change `probability >= high_from` to `probability > high_from` and run `pytest -m unit -q`. Test U2 fails, which shows the tests catch real bugs. Undo the change afterwards.
5. Open the Actions tab on GitHub to show the same tests running on each push.
