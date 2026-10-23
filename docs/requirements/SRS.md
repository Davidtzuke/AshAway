AshAway | Software Engineering for CSAI | Group 9
Version 1.2 (revised after Task 2/3 feedback; original v1.1 kept as `SRS_v1.1_original.docx`)

# 1. Introduction

## 1.1 Purpose

AshAway is a proposed wildfire-risk advisor for travellers visiting
Greece between May and October. A traveller selects a municipality and
travel dates; the system combines historical fire-risk patterns with
available fire observations, disruption reports and smoke/air-quality
information to communicate a risk level, the evidence behind it and
possible lower-risk alternatives. Its purpose is informed travel
planning, not emergency routing or a guarantee of safety.

## 1.2 Intended audience

This SRS is intended for the project team, WanderGuard (proposed
client), testers and future travel-agency users. It specifies the
behaviour that should be verified before a pilot release.

## 1.3 Scope and assumptions

The initial scope is supported Greek municipalities, not all of Europe.
The system advises at municipality-day level, while the proposed fire
model learns at 1 km cell-day level. Risk forecasts, observed incidents
and official warnings must remain clearly distinguishable. The data
pipeline is intended to update automatically; external source
availability is a dependency.

# 2. User requirements

Each requirement describes a system function in terms a non-technical
user can understand, with the metric used to check it in a user
acceptance test.

| **ID** | **Requirement** | **Success metric** | **Task 1 objective** |
|--------|-----------------|--------------------|----------------------|
| UR1 | The system shall allow a user to request a wildfire-risk assessment for a supported Greek destination and chosen travel dates. | ≥ 90% of test users complete a request without help | Place- and date-specific advice |
| UR2 | The system shall show the destination's risk level in plain language that does not require wildfire knowledge. | ≥ 80% of test users correctly explain what the shown risk level means | Flag genuinely affected places |
| UR3 | The system shall show why a risk level was given and when the supporting information was recorded. | 100% of assessments show reasons and dates; ≥ 80% of test users can name the main reason | Explain and date the evidence |
| UR4 | The system shall make clear whether information is a forecast, a confirmed incident, a smoke observation or an official warning. | ≥ 90% of test users classify the information type correctly | Trustworthy information |
| UR5 | The system shall suggest other supported destinations with lower estimated risk for the same dates, when such options exist. | Alternatives shown in 100% of high-risk results where a lower-risk option with adequate data exists | Offer alternatives |
| UR6 | The system shall warn the user when the available information is incomplete or too old for a confident assessment. | 100% of test cases with missing/stale data show a warning | Avoid false reassurance |
| UR7 | The system shall allow a travel adviser to compare destinations for the same date range on the same basis. | ≥ 80% of test advisers complete a two-destination comparison within 2 minutes | Support trip decisions |

# 3. System requirements

## 3.1 Functional requirements

Must = required for pilot; Should = planned if data and development time
permit. \[AI\] identifies a function relying on a trained model. Each
requirement is written as input → system behaviour → output.

| **ID / Priority** | **Input** | **System behaviour** | **Output** | **Success metric** | **Linked UR** |
|---|---|---|---|---|---|
| FR1 / Must | Municipality, start date, end date | The system shall validate that the place is supported and the interval is valid (start ≤ end, within May–Oct coverage). | Accepted request, or a rejection message stating the reason | 100% of invalid test inputs rejected with the correct reason | UR1 |
| FR2 / Must \[AI\] | Valid request | The system shall compute a low/medium/high risk level per requested day for the municipality. | Daily risk levels with query dates and generation time | Recall ≥ 0.80 on affected destinations (held-out test years) | UR2 |
| FR3 / Must | Scheduled trigger (automatic) | The system shall retrieve fire, air-quality and disruption feeds and store each item with source and timestamp. | Updated evidence store; source and time shown per displayed item | ≥ 95% of scheduled updates succeed; 100% of items carry source + timestamp | UR3, UR4 |
| FR4 / Must \[AI\] | Risk result + evidence for that place and period | The system shall identify the main signals contributing to the result. | Short explanation listing the top contributing signals | 100% of explanations reference only evidence for that place/period | UR3 |
| FR5 / Must | Evidence store state | The system shall detect missing, stale or conflicting critical inputs. | "Insufficient evidence" instead of an unqualified low-risk result | 100% of missing-source test cases produce the warning | UR6 |
| FR6 / Should \[AI\] | Request with medium/high risk | The system shall rank other supported destinations for the same dates that have adequate data coverage. | Up to 3 lower-risk alternatives | Every alternative has lower risk and adequate coverage in 100% of test cases | UR5 |
| FR7 / Should | Two or more destinations + one date range | The system shall assess all destinations on the same data and dates. | Side-by-side table of risk, evidence recency and coverage | Comparison generated for 100% of valid multi-destination requests | UR7 |
| FR8 / Must | Evidence items | The system shall label each item as forecast, observation or official alert. | Labelled items, with link to official warning when available | 100% of displayed items labelled; 0 mislabelled in test set | UR4 |
| FR9 / Must | Request outside supported municipalities or dates *(moved from NFR10)* | The system shall stop the assessment instead of guessing. | Explicit limitation message naming what is unsupported | 100% of out-of-scope test requests produce the message | UR1, UR6 |

## 3.2 Non-functional requirements

| **ID / Category** | **Constraint** | **Success metric** | **Related functional requirement** |
|---|---|---|---|
| NFR1 / Speed | Cached assessments shall display quickly; otherwise show progress or an error. | ≥ 95% of cached assessments shown within 5 s in pilot testing | FR1, FR2, FR7 |
| NFR2 / Data quality | Data ingestion shall record raw and cleaned row counts, removed duplicates, missing-value rates, feature count and file size (MB/GB) for each training dataset version. | 100% of dataset versions have a complete data report | FR2, FR3 |
| NFR3 / Input/output | Automated updates shall log retrieval time, source failures and generated output. User input is municipality and dates; output is risk, explanation, evidence age and optional alternatives. | 100% of update runs logged | FR1–FR6 |
| NFR4 / Traceability | Each displayed observation shall carry source and observation time; each prediction shall be reproducible from a model version and data snapshot. | 100% of sampled predictions reproduced exactly | FR2–FR4 |
| NFR5 / Resilience | A failed external feed shall be marked unavailable; no values or incidents shall be fabricated or silently treated as zero. | 0 fabricated/zero-filled values in feed-failure tests | FR3–FR5 |
| NFR6 / Usability & safety | Risk levels shall be described in words as well as colours; every result shall state that it does not replace official safety advice. | 100% of result screens contain text label + disclaimer | FR2–FR8 |
| NFR7 / Privacy | A basic query shall not require an account; identifiable travel histories shall not be stored by default. | 0 personal identifiers in stored query logs | FR1, FR7 |
| NFR8 / Evaluation \[AI\] | The training record shall report train/val/test counts and percentages, model alternatives, features, recall, precision, F2, AUPRC, calibration, training time, number of boosting rounds and inference latency. | 100% of model versions have a complete training record | FR2, FR4, FR6 |
| NFR9 / Validation \[AI\] | Evaluation shall use held-out years, not random splits of neighbouring cells; alert thresholds shall be tuned on validation data to prioritise recall. | Test years never used for training or threshold tuning | FR2, FR6 |

# 4. AI-specific requirements

**AI1 — Model choice (FR2; NFR8–9).** The first model is XGBoost for
mixed weather, vegetation, terrain and human-activity variables.
Options considered: a Fire Weather Index (FWI) baseline (kept as the
reference), logistic regression, random forest, and the LSTM/transformer
sequence models from the Mesogeos benchmark. Sequence models were not
chosen first because they cost much more to train and are harder to
explain; they remain a later comparison. Model selection shall use
held-out results and training/inference cost, not complexity alone.

**AI2 — Data (NFR2).** Training data is Mesogeos Track A: 25,722
published samples (8,574 positive, 17,148 negative), each a 30-day
window for one 1 km cell, labelled on the following day. Published
temporal split: train 2006–2019 (19,353; 75.2%), validation 2020
(2,262; 8.8%), test 2021–2022 (4,107; 16.0%). These are source counts
*before* our cleaning; post-cleaning counts, file size (MB) and number
of usable features (9 core features plus the optional Mesogeos
variables present) shall
be recorded after the first real-data run. Outcome columns
(e.g. burned area) shall be removed to prevent leakage. Live inputs
(NASA FIRMS, Open-Meteo/CAMS, GDELT) are retrieved automatically on a
schedule (FR3).

**AI3 — Acceptance criteria: when is the model good enough (FR2).**
A model version may be used only if, on the held-out test years:
(a) recall ≥ 0.80 at the chosen threshold; (b) AUPRC is higher than the
FWI baseline; (c) AUROC is in a plausible range compared with published
Greek results (about 0.82–0.87 for XGBoost); and (d) AUROC ≤ 0.92, since
higher values trigger a leakage check before acceptance.

**AI4 — Performance reporting (NFR8).** Each training run shall report
the metrics in NFR8 plus training time, number of boosting rounds
(early stopping) and inference latency per 1,000 cell-days. Current
status: the pipeline has only been run on synthetic test data, so no
real performance is claimed yet; real results will be added after the
Mesogeos data is loaded.

**AI5 — Explainability and uncertainty (FR4–5).** Explanations shall
reflect available inputs, never present a predicted fire as a confirmed
event, and disclose absent or outdated evidence. The municipality-level
risk fusion shall be evaluated separately from the cell-level model.
Probabilities shall be calibrated on validation data before being
turned into risk levels.

**AI6 — Recommendations (FR6).** Alternatives shall be compared for
identical travel dates and adequate data coverage. A lower predicted
score shall not be described as proof of safety.

**AI7 — Model updates.** The model shall be retrained at least once a
year before the fire season (May) with the latest completed season
added. A new version replaces the current one only if it meets AI3 and
is not worse on the latest test year. Every version is stored with its
data snapshot and training record (NFR4). Input distributions shall be
checked monthly during the season for drift.

**AI8 — Feedback.** Users shall be able to report an assessment they
believe is wrong (no account needed, NFR7). Reports are logged with the
model version and reviewed by the team, and used in evaluation and
the next retraining, not for automatic online learning.
