# Requirements changelog

- `SRS_v1.1_original.docx` — **backup** of the SRS as submitted for Task 3 (v1.1, 9 October 2026). Do not edit.
- `SRS.md` — the **living** version. Update it when requirements change and add an entry below.

At the end of the project, compare `SRS.md` with the original to trace all differences
(e.g. `git log -p docs/requirements/SRS.md`).

## Changes

| Date | Version | Requirement(s) | Change | Reason | Agreed in |
|------|---------|----------------|--------|--------|-----------|
| 2026-10-23 | 1.1 | – | Baseline copied from submitted Task 3 SRS | Start of implementation | Sprint 2 |
| 2026-10-23 | 1.2 | UR1–UR7 | Rewritten as "The system shall …" in non-technical language; success metric added per requirement | Lecturer feedback Task 3 (Sec. 2) | Sprint 2 |
| 2026-10-23 | 1.2 | FR1–FR8 | Rewritten as input → system behaviour → output; success metric added | Lecturer feedback Task 3 (Sec. 3.1) | Sprint 2 |
| 2026-10-23 | 1.2 | NFR10 → FR9 | Scope limitation message moved to functional requirements (it is system behaviour, not a quality constraint) | Lecturer feedback Task 3 (Sec. 3.2) | Sprint 2 |
| 2026-10-23 | 1.2 | NFR1–NFR9 | Success metric column added; "Related function" renamed to "Related functional requirement"; NFR8 adds number of boosting rounds | Lecturer feedback Task 3 (Sec. 3.2) | Sprint 2 |
| 2026-10-23 | 1.2 | AI1–AI8 | Added alternatives considered (AI1), data details with split percentages and pre/post-cleaning note (AI2), acceptance criteria (AI3), performance reporting (AI4), model updates (AI7) and user feedback (AI8) | Lecturer feedback Task 2 and Task 3 (Sec. 4) | Sprint 2 |
| 2026-11-03 | 1.3 | AI2 | Real post-cleaning counts, file size and feature count; row 29 identified as the labelled day; explains 25,916 vs 25,722 samples | First real-data run | Task 5 |
| 2026-11-03 | 1.3 | AI4 | Points to real results; baseline stated to be a proxy because Track A has no FWI column | First real-data run | Task 5 |
| 2026-11-23 | 1.4 | 1.3, 1.4 (new) | Scope set to the 11 pilot destinations, each one 1 km cell; date limits stated (June 2006 onwards, 14 days ahead); new system overview of the three servers | Match the software as built | Task 7 |
| 2026-11-23 | 1.4 | UR8 (new), FR10, FR11 (new) | Users can report a wrong assessment; every assessment and report is stored behind the orchestrator | Implemented in Task 6 (T17, T20) and moved in Task 7 (T24) | Task 7 |
| 2026-11-23 | 1.4 | FR1–FR9 | Rewritten to the implemented behaviour: exact date checks (FR1), cut-offs and worst-day rule (FR2), feeds retrieved per request instead of on a schedule, with sources named (FR3), up to 3 reasons (FR4), 2-day staleness and weather gaps (FR5), alternatives for medium as well as high (FR6), 2 to 11 destinations (FR7) | Match the software as built | Task 7 |
| 2026-11-23 | 1.4 | NFR1, NFR3, NFR7 | NFR1 no longer assumes a cache; NFR3 adds request ids across servers; NFR7 lists what counts as identifying | Match the software as built | Task 7 |
| 2026-11-23 | 1.4 | NFR10, NFR11 (new) | Architecture rule (separate servers, interface never calls the AI server or holds data) and automatic tests on every push | Task 6 design and lecturer feedback on Task 6 | Task 7 |
| 2026-11-23 | 1.4 | AI1–AI8 | Model comparison and deployed model named (AI1); feeds per request (AI2); AI3 result stated, including the unmet Greek criterion; relative scores explained (AI5); version check (AI7); feedback implemented (AI8) | Match the software as built | Task 7 |
| 2026-11-23 | 1.4 | Section 5 (new) | Implementation status and traceability: code, tests and status for every requirement | Task 7: requirements must correspond to the design | Task 7 |
