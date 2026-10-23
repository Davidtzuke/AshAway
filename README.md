# AshAway

Wildfire-risk advisor for holiday destinations in Greece. SE4CSAI 2026-27, group 9.

## Structure

- `src/ashaway/geo.py`, `targets.py` – geographic units (1 km cell-day → municipality-day) and prediction targets
- `src/ashaway/model/` – data loading, training and the initial XGBoost fire-danger model
- `reports/` – model metrics
- `docs/requirements/` – SRS (living version + original backup + changelog)
- `docs/scrum-log.md` – check-ins and sprint reviews

## Branches

- `main` – stable, reviewed code
- `feature/*` – one branch per task, merged into `main` via pull request

## Setup

```
pip install -e ".[dev]"
pytest
```
