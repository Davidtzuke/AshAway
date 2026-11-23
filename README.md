# AshAway

Wildfire-risk advisor for holiday destinations in Greece. SE4CSAI 2026-27, group 9.

## Structure

- `src/ashaway/geo.py`, `targets.py` – geographic units (1 km cell-day → municipality-day) and prediction targets
- `src/ashaway/model/` – data loading, training and the fire-danger models
- `src/ashaway/request.py`, `risk.py`, `evidence.py`, `feeds.py`, `assess.py`, `cli.py` – the traveller-facing service
- `src/ashaway/services/` – the three servers: interface, orchestrator and AI (Task 6, see `docs/architecture.md`)
- `models/live-v1/` – the saved product model
- `reports/` – training record and model metrics
- `docs/TODO.md` – task list; `docs/model-results.md` – real results; `docs/testing.md` – test catalogue
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

## Use it

```
ashaway places
ashaway assess rhodes 2023-07-18 2023-07-24
ashaway compare rhodes chania 2023-07-18 2023-07-24
```

Past dates are replayed as if asked the day before the trip. Set `FIRMS_MAP_KEY` to use NASA FIRMS. Without it, results that would be low show "insufficient evidence".

## Run it as three servers

```
python -m ashaway.services
```

This starts the AI server (:8002), the orchestrator (:8001) and the interface (:8000) as separate processes. Open http://127.0.0.1:8000. Add `--replay` to use recorded 2023 weather instead of the internet. To start them one by one, run `ashaway-ai`, `ashaway-orchestrator` and `ashaway-interface` in three terminals. See `docs/architecture.md`.

## Train on real data

```
pip install gdown
python scripts/download_mesogeos.py
python -m ashaway.model.train
```
