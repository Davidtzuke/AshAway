AshAway \| Software Engineering for CSAI \| Group 9 \| 9 October 2026 \|
Version 1.1

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

The following describe outcomes needed by travellers or advisers, not
particular algorithms or programming tools. Each can be checked in a
user acceptance test.

| **ID** | **User need / acceptance outcome**                                                                           | **Task 1 objective**            |
|--------|--------------------------------------------------------------------------------------------------------------|---------------------------------|
| UR1    | A traveller can request an assessment for a supported Greek destination and chosen travel dates.             | Place- and date-specific advice |
| UR2    | A traveller can understand the destination’s risk level without needing specialist wildfire knowledge.       | Flag genuinely affected places  |
| UR3    | A traveller can see why the risk level was assigned and when supporting information was recorded.            | Explain and date the evidence   |
| UR4    | A traveller can tell a forecast apart from a confirmed incident, smoke observation or official warning.      | Trustworthy information         |
| UR5    | A traveller can discover other supported destinations with lower estimated risk when suitable options exist. | Offer alternatives              |
| UR6    | A traveller is warned when evidence is incomplete or too old to support a confident assessment.              | Avoid false reassurance         |
| UR7    | A travel adviser can compare destinations for the same date range on a consistent basis.                     | Support trip decisions          |

# 3. System requirements

## 3.1 Functional requirements

Must = required for pilot; Should = planned if data and development time
permit. \[AI\] identifies a function relying on a trained model.

| **ID / Priority**   | **Required system action and observable result**                                                                                                    | **Linked user need** |
|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|
| FR1 / Must          | Accept municipality, start date and end date; reject invalid intervals or unsupported places with an explanation.                                   | UR1                  |
| FR2 / Must \[AI\]   | Generate low/medium/high risk per supported municipality and requested day, with query dates and generation time displayed.                         | UR2                  |
| FR3 / Must          | Retrieve available fire, air-quality and disruption feeds automatically and show each displayed item’s source and timestamp.                        | UR3–4                |
| FR4 / Must \[AI\]   | Explain the main signals contributing to the assessment using only evidence available for that location and period.                                 | UR3                  |
| FR5 / Must          | Flag missing, stale or conflicting inputs; show “insufficient evidence” instead of an unqualified low-risk result when critical sources are absent. | UR6                  |
| FR6 / Should \[AI\] | Offer lower-risk alternatives for the same dates, ranked only among destinations with adequate comparable coverage.                                 | UR5                  |
| FR7 / Should        | Show a comparison of at least two destinations including risk, evidence recency and data coverage.                                                  | UR7                  |
| FR8 / Must          | Label forecast, observation and official alert separately; link to official warnings when a link is available.                                      | UR4                  |

## 3.2 Non-functional requirements

| **ID / Category**         | **Constraint / verification criterion**                                                                                                                                                             | **Related function** |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|
| NFR1 / Speed              | In pilot testing, at least 95% of cached assessments shall display within 5 seconds; otherwise show progress or an error.                                                                           | FR1–2, FR7           |
| NFR2 / Data quality       | Data ingestion shall record raw and cleaned row counts, removed duplicates, missing-value rates, feature count and file size (MB/GB) for each training dataset version.                             | FR2–3                |
| NFR3 / Input/output       | Automated updates shall log retrieval time, source failures and generated output; user input shall be municipality and dates, and output risk, explanation, evidence age and optional alternatives. | FR1–6                |
| NFR4 / Traceability       | Each displayed observation shall carry source and observation time; each prediction shall be reproducible from a model version and data snapshot.                                                   | FR2–4                |
| NFR5 / Resilience         | A failed external feed shall be marked unavailable; no values or incidents shall be fabricated or silently treated as zero.                                                                         | FR3–5                |
| NFR6 / Usability & safety | Risk categories shall be described in words as well as colours, and every result shall state that it does not replace official safety advice.                                                       | FR2–8                |
| NFR7 / Privacy            | A basic query shall not require an account; identifiable travel histories shall not be stored by default.                                                                                           | FR1, FR7             |
| NFR8 / Evaluation \[AI\]  | The training record shall report train/dev/test counts and percentages, model alternatives, features, recall, precision, F2, AUPRC, calibration, training duration and inference latency.           | FR2, FR4, FR6        |
| NFR9 / Validation \[AI\]  | The evaluation shall use held-out years rather than random neighbouring cell splits; alert thresholds shall be tuned on dev data to prioritise recall.                                              | FR2, FR6             |
| NFR10 / Scope             | Unsupported municipalities or dates beyond available coverage shall produce an explicit limitation message.                                                                                         | FR1–2                |

# 4. AI-specific requirements

AI1 — Fire prediction (FR2; NFR8–9): The initial candidate is XGBoost
for mixed weather, vegetation, terrain and human-activity variables.
Compare against a Fire Weather Index baseline and at least one
alternative (e.g. random forest). Model selection shall use held-out
results and practical training/inference cost, not complexity alone.

AI2 — Training evidence (NFR2, NFR8–9): Record whether sample counts
refer to raw or cleaned data, dataset size in MB/GB, number of usable
features, class distribution and exact split percentages. The proposed
Mesogeos Track A dataset has 25,722 published samples; this is a source
figure, not a verified post-cleaning count. Training statistics must be
filled from actual experiments; no training run or score is claimed in
this SRS.

AI3 — Explainability and uncertainty (FR4–5): Model explanations shall
reflect available inputs, never present a predicted fire as a confirmed
event, and disclose absent or outdated evidence. The final
municipality-level risk fusion must be evaluated separately from the
cell-level predictor.

AI4 — Recommendations (FR6): Alternatives shall be compared for
identical travel dates and adequate source coverage. A lower predicted
score shall not be described as proof of safety.
