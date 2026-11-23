AshAway | Software Engineering for CSAI | Group 9
Version 1.4, 23 November 2026: matched to the software as built (Task 7). Earlier versions: v1.1 as submitted for Task 3 (`SRS_v1.1_original.docx`), v1.2 after the Task 2/3 feedback, v1.3 after the first real-data run. Every change is listed in `CHANGELOG.md`.

# 1. Introduction

## 1.1 Purpose

AshAway is a wildfire-risk advisor for travellers visiting Greece
between May and October. A traveller selects a destination and travel
dates; the system combines a fire-danger model with weather, satellite
fire detections and air-quality information to communicate a risk level
per day, the evidence behind it, and lower-risk alternatives. Its
purpose is informed travel planning, not emergency routing or a
guarantee of safety.

## 1.2 Intended audience

This SRS is intended for the project team, WanderGuard (proposed
client), testers and future travel-agency users. It specifies the
behaviour that is verified before a pilot release, and section 5 records
how far the current software meets it.

## 1.3 Scope and assumptions

The pilot covers 11 Greek holiday destinations (Ancient Olympia,
Chania, Heraklion, Lefkada, Marathon, Nafplio, Naxos, North Evia,
Rethymno, Rhodes, Volos), not all of Greece. Each destination is
represented by one 1 km grid cell, the unit the fire model learns on.
Requests may cover May to October, from June 2006, and up to 14 days
ahead, the limit of usable weather forecasts. Past dates are assessed as
if asked the day before the trip. Risk forecasts, observed incidents and
official warnings must remain clearly distinguishable. External data
sources are a dependency: when one fails, the system says so.

## 1.4 System overview

AshAway runs as three servers that talk only over HTTP (details in
`docs/architecture.md`):

- **Interface** (port 8000): web page and JSON API; checks every request
  before passing it on; keeps no data.
- **Orchestrator** (port 8001): fetches the evidence, runs the evidence
  checks, asks the AI server for predictions, builds the answer and
  stores every outcome and feedback.
- **AI server** (port 8002): the only process that loads the model.

The same assessment logic is also available in one process through the
command line (`ashaway assess`).

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
| UR5 | The system shall suggest other supported destinations with lower estimated risk for the same dates, when such options exist. | Alternatives shown in 100% of medium- and high-risk results where a lower-risk option with adequate data exists | Offer alternatives |
| UR6 | The system shall warn the user when the available information is incomplete or too old for a confident assessment. | 100% of test cases with missing/stale data show a warning | Avoid false reassurance |
| UR7 | The system shall allow a travel adviser to compare destinations for the same date range on the same basis. | ≥ 80% of test advisers complete a two-destination comparison within 2 minutes | Support trip decisions |
| UR8 | The system shall allow a user to report an assessment they believe is wrong, without creating an account. | 100% of reports stored with the assessment they concern | Trust in the explanation |

# 3. System requirements

## 3.1 Functional requirements

Must = required for pilot; Should = planned if data and development time
permit. \[AI\] identifies a function relying on a trained model. Each
requirement is written as input → system behaviour → output.

| **ID / Priority** | **Input** | **System behaviour** | **Output** | **Success metric** | **Linked UR** |
|---|---|---|---|---|---|
| FR1 / Must | Destination, start date, end date | The system shall check that the destination is supported, both dates are valid (YYYY-MM-DD), start ≤ end, both fall in May–October of the same year, the trip starts no earlier than June 2006 and ends at most 14 days ahead. The interface checks this before any other server is contacted. | Accepted request, or a refusal stating the reason | 100% of invalid test inputs refused with the correct reason | UR1 |
| FR2 / Must \[AI\] | Accepted request | The system shall compute a calibrated fire score and a low/medium/high level for each requested day (medium from 0.198, high from 0.467), and give the trip the level of its worst day. | Daily levels and scores, with the assessment date, generation time and model version | Recall ≥ 0.80 on fire days in the held-out test years | UR2 |
| FR3 / Must | Each assessment request | The system shall retrieve, for the destination: daily weather (Open-Meteo, critical), satellite fire detections within 20 km (NASA FIRMS, critical, needs an API key) and air quality (Open-Meteo CAMS, optional), and log each retrieval. | Evidence items, each with source and date; a log line per source and request | 100% of displayed items carry source and date; 100% of retrievals logged | UR3, UR4 |
| FR4 / Must \[AI\] | Scores and inputs for the peak day | The system shall identify the inputs that raised the score most (feature contributions). | Up to 3 reasons in plain words, with the input values used | 100% of explanations use only that place's and period's inputs | UR3 |
| FR5 / Must | Status of each source; model level; detections nearby | The system shall detect missing or failed critical sources, critical data older than 2 days, gaps in the weather history, and a low forecast contradicted by nearby fire detections. | "Insufficient evidence" instead of a low result; medium and high results stay visible with a warning | 100% of missing-source test cases produce the warning | UR6 |
| FR6 / Should \[AI\] | Request with a medium or high result | The system shall assess the other destinations for the same dates and keep those with a strictly lower level, every day scored and the same sources available. | Up to 3 alternatives, lowest score first, marked "not proof of safety" | Every alternative is lower and comparable in 100% of test cases | UR5 |
| FR7 / Should | 2 to 11 destinations and one date range | The system shall assess all destinations on the same dates with the same logic. | One row per destination: level, peak score, evidence age, sources available | Comparison generated for 100% of valid requests | UR7 |
| FR8 / Must | Evidence items | The system shall label each item as forecast, observation or official alert. | Labelled items; a forecast is stated to be "predicted, not a confirmed fire" | 100% of displayed items labelled; 0 mislabelled in the test set | UR4 |
| FR9 / Must | Request outside the supported destinations or dates | The system shall stop instead of guessing. | A message naming what is unsupported, and no risk level | 100% of out-of-scope test requests produce the message | UR1, UR6 |
| FR10 / Must | Every assessment the orchestrator handles | The system shall store the request with its outcome (assessed, insufficient evidence, refused, unavailable), level, model version and full answer. | An assessment id, from which the stored answer can be retrieved | 100% of handled requests stored | UR3, UR8 |
| FR11 / Should | Assessment id, verdict (risk too high, too low, evidence wrong, other), optional comment ≤ 500 characters | The system shall store the report beside the assessment and its model version, for the team to review. | Confirmation, or a refusal if no assessment was made | 100% of valid reports stored; 0 used for automatic retraining | UR8 |

## 3.2 Non-functional requirements

| **ID / Category** | **Constraint** | **Success metric** | **Related functional requirement** |
|---|---|---|---|
| NFR1 / Speed | An assessment shall be shown quickly; otherwise the page shows progress or an error. | ≥ 95% of assessments shown within 5 s in pilot testing | FR1, FR2, FR7 |
| NFR2 / Data quality | Data ingestion shall record raw and cleaned row counts, removed duplicates, missing-value rates, feature count and file size for each training dataset version. | 100% of dataset versions have a complete data report | FR2 |
| NFR3 / Input/output | Every feed retrieval shall be logged with time, result and any failure; every request shall carry one id through all three servers' logs. User input is destination and dates; output is risk, explanation, evidence and its age, and optional alternatives. | 100% of retrievals and requests logged | FR1–FR6, FR10 |
| NFR4 / Traceability | Each displayed observation shall carry source and observation time; each prediction shall be reproducible from the model version. | 100% of sampled predictions reproduced exactly | FR2–FR4, FR10 |
| NFR5 / Resilience | A failed external feed or server shall be marked unavailable; no values or incidents shall be invented or silently treated as zero. | 0 invented or zero-filled values in failure tests | FR3–FR5 |
| NFR6 / Usability & safety | Risk levels shall be described in words as well as colours; every result shall state that it does not replace official safety advice. | 100% of results contain a text label and the disclaimer | FR2–FR8 |
| NFR7 / Privacy | A query shall not require an account; nothing identifying the traveller (name, account, IP address, browser details) shall be stored. | 0 personal identifiers in stored data and logs | FR1, FR10, FR11 |
| NFR8 / Evaluation \[AI\] | The training record shall report train/val/test counts and percentages, model alternatives, features, recall, precision, F2, AUPRC, calibration, training time, number of boosting rounds and inference latency. | 100% of model versions have a complete training record | FR2, FR4, FR6 |
| NFR9 / Validation \[AI\] | Evaluation shall use held-out years, not random splits of neighbouring cells; cut-offs shall be tuned on validation data to prioritise recall. | Test years never used for training or tuning | FR2, FR6 |
| NFR10 / Architecture | The interface, orchestrator and AI server shall run as separate processes that communicate only over HTTP. The interface shall never call the AI server or hold data; only the AI server loads the model. | Tested on every change: interface loads no model or storage code; requests pass all three servers | All |
| NFR11 / Maintainability | Unit and integration tests shall run automatically on every push and pull request, without internet access. | 100% of tests pass on `main` | All |

# 4. AI-specific requirements

**AI1 — Model choice (FR2; NFR8–9).** The model is XGBoost for mixed
weather, terrain, land-cover and human-activity variables. Compared on
the same data: a hot/dry/windy baseline (Track A has no Fire Weather
Index), logistic regression, random forest, XGBoost with all 28
features, and XGBoost with the 20 features the product can supply live.
The LSTM/transformer models from the Mesogeos benchmark were not chosen,
because they cost much more to train and are harder to explain. The
deployed model is the 20-feature XGBoost (`live-v1`), because
vegetation, soil moisture and land-surface temperature have no live
source yet.

**AI2 — Data (NFR2).** Training data is Mesogeos Track A: 25,916
samples in the files (777,480 rows, 217.8 MB); 194 surplus negatives
are removed to keep 2 negatives per positive in each split, as the
official loader does, leaving 25,722 (8,574 positive, 17,148 negative).
No duplicates or incomplete samples were found. Each sample is a 30-day
window for one 1 km cell; row 29 is the labelled day, so inputs come
only from rows 0–28. Temporal split: train 2006–2019 (19,353; 75.2%),
validation 2020 (2,262; 8.8%), test 2021–2022 (4,107; 16.0%). Outcome
columns (burned area, ignition points) are removed. Live inputs
(Open-Meteo weather and air quality, NASA FIRMS) are retrieved for each
request (FR3).

**AI3 — Acceptance criteria (FR2).** A model version may be used only
if, on the held-out test years: (a) recall ≥ 0.80 at the chosen
threshold; (b) AUPRC is higher than the baseline; (c) AUROC is in a
plausible range compared with published Greek results (about 0.82–0.87
for XGBoost); and (d) AUROC ≤ 0.92, since higher values trigger a
leakage check. `live-v1` meets (a), (c) and (d), and (b) for the
Mediterranean test years, but not for Greece in May–October (AUPRC
0.595 against 0.698, on 47 fires). This is reported, not hidden; see
section 5.

**AI4 — Performance reporting (NFR8).** Each training run reports the
metrics in NFR8 plus training time, boosting rounds and inference
latency per 1,000 cell-days, in `reports/training_record.json`;
`docs/model-results.md` summarises them.

**AI5 — Explainability and uncertainty (FR4–5).** Explanations reflect
the inputs actually used, never present a predicted fire as a confirmed
event, and disclose absent or outdated evidence. Scores are calibrated
on the validation year (isotonic regression) before being turned into
levels. Because the training data has 1 fire per 2 non-fires, the
scores are relative, not real chances of fire (planned fix: T16).

**AI6 — Recommendations (FR6).** Alternatives are compared for identical
travel dates and the same available sources. A lower score is never
described as proof of safety.

**AI7 — Model updates.** The model shall be retrained at least once a
year before the fire season (May) with the latest completed season
added. A new version replaces the current one only if it meets AI3 and
is not worse on the latest test year. Every version is stored as its own
directory with its training record (NFR4), and a test checks that the
deployed version matches its record. Input distributions shall be
checked monthly during the season for drift.

**AI8 — Feedback.** Users can report an assessment they believe is wrong
(FR11). Reports are stored with the model version and reviewed by the
team, and used in evaluation and the next retraining, never for
automatic online learning.

# 5. Implementation status and traceability

Status on 23 November 2026, for `main`. Met = implemented and tested.
Partly = implemented with a stated gap. User-test metrics (UR1–UR4,
UR7, NFR1) need a pilot with real users, which has not happened yet.

| **Req.** | **Implemented in** | **Tests** | **Status** |
|---|---|---|---|
| UR1, FR1, FR9 | `request.py`, interface server, web page, CLI | U1, I6, I9, I10 | Met; user test pending |
| UR2, FR2 | `risk.py`, `assess.py`, AI server | U2, I3, I7, I8 | Met at cell level (recall 0.946); destination-level recall not yet measured (T15) |
| UR3, FR3 | `feeds.py`, orchestrator | U4, I3, I4 | Partly: weather and air quality live; FIRMS adapter tested on hand-written files only (T12); disruption news not connected (T13) |
| FR4 | `risk.explain`, AI server `/predict` | I3, I7 | Met |
| UR4, FR8 | `evidence.py` | I3 | Partly: forecasts and observations labelled; no official-alert source yet |
| UR5, FR6 | `assess.lower_risk_alternatives` | U6, I5 | Met |
| UR6, FR5 | `evidence.py`, `assess.py` | U3, I3, I4, I10 | Met |
| UR7, FR7 | `assess.compare`, `/api/compare`, CLI | I5, I6, I10 | Met in the API and CLI; not yet on the web page |
| UR8, FR10, FR11 | `store.py`, orchestrator, web page | I8, I9, I10 | Met |
| NFR1 | All servers | Manual run | Partly: about 0.3 s with recorded data; not measured in a pilot |
| NFR2, NFR8, NFR9 | `model/data.py`, `model/train.py` | I1, I2, U7 | Met |
| NFR3, NFR4 | `feeds.log_update`, request ids, model versions | I2, I3, I10, I11 | Met |
| NFR5 | `feeds.py`, orchestrator, interface | U4, I4, I8, I10 | Met |
| NFR6 | `risk.py`, web page, CLI | I3, I6 | Met |
| NFR7 | `store.py`, servers | I3, I9 | Met |
| NFR10 | `services/` | I9, I10 | Met |
| NFR11 | `.github/workflows/tests.yml` | All 164 tests | Met |
| AI1, AI2, AI4 | `model/` | I1, I2 | Met |
| AI3 | `models/live-v1` | `docs/model-results.md` | Partly: criterion (b) not met for Greece |
| AI5 | `model/bundle.py` | U7 | Partly: calibrated, but on the 1:2 training ratio (T16) |
| AI6 | `assess.py` | U6, I5 | Met |
| AI7 | Version directories, training record | I11 | Process defined and checked; no retraining needed yet |
| AI8 | Orchestrator storage | I8 | Met; review is done by the team by hand |
