# AshAway

Wildfire-risk advice for holiday destinations in Greece. A traveller picks a destination and dates between May and October; AshAway answers with a risk level per day (low, medium or high), the main reasons, the evidence behind it with its source and date, and lower-risk alternatives. When the evidence is missing, old or contradictory, it says "insufficient evidence" instead of "low".

Software Engineering for CSAI 2026-27, group 9: Hammza Abas, Amin El Amrani, Rayan Fikri, Calvin Kakembo, Mikail Kaya, David Vasilescu.

## Quick start

Python 3.10 or newer (CI uses 3.12).

```
pip install -e ".[dev]"
pytest                                  # 160 tests, no internet needed
python -m ashaway.services --replay     # the three servers, with recorded 2023 weather
```

Open http://127.0.0.1:8000 and assess Rhodes, 18 to 24 July 2023 (the week of the Rhodes evacuation). Without `--replay` the servers use live Open-Meteo data.

## How it is built

```
browser ──HTTP──▶ interface :8000 ──HTTP──▶ orchestrator :8001 ──HTTP──▶ AI server :8002
                  checks requests          feeds, evidence checks,       the model only
                  keeps no data            alternatives, SQLite storage
```

| Part | Code | What it does |
|---|---|---|
| Interface server | `src/ashaway/services/interface.py`, `static/index.html` | Web page and JSON API; checks every request before passing it on |
| Orchestrator server | `src/ashaway/services/orchestrator.py`, `store.py` | Runs the assessment, calls the AI server, stores every outcome and feedback |
| AI server | `src/ashaway/services/ai.py` | Loads the model and serves `/model` and `/predict` |
| Assessment logic | `src/ashaway/request.py`, `feeds.py`, `assess.py`, `evidence.py`, `risk.py` | Request checks, live feeds, features, evidence checks, risk levels and reasons |
| Model | `src/ashaway/model/`, `models/live-v1/` | Data loading, training, model comparison, calibration; the deployed model version |
| Geography and targets | `src/ashaway/geo.py`, `targets.py` | 1 km grid cells, municipalities, Greek boundary, prediction targets |
| Command line | `src/ashaway/cli.py` | `ashaway assess`, `ashaway compare`, `ashaway places`, all in one process |

Details: `docs/architecture.md`.

## Use it

As three servers:

```
python -m ashaway.services            # all three as separate processes
ashaway-ai                            # or one per terminal: :8002
ashaway-orchestrator                  # :8001
ashaway-interface                     # :8000
```

Or in one process from the command line:

```
ashaway places
ashaway assess rhodes 2023-07-18 2023-07-24
ashaway compare rhodes chania 2023-07-18 2023-07-24
```

Past dates are assessed as if asked the day before the trip. Set `FIRMS_MAP_KEY` to use NASA FIRMS satellite fire detections; without it, a result that would be low is shown as "insufficient evidence".

## Tests

```
pytest -m unit          # one function at a time, no files or network
pytest -m integration   # components and the three servers together
```

GitHub Actions runs both on every push and pull request. The test catalogue, with input, expected output and reason for each case, is in `docs/testing.md`.

## Train the model on real data

```
pip install gdown
python scripts/download_mesogeos.py    # Mesogeos Track A, 218 MB, CC BY 4.0
python -m ashaway.model.train          # compares 5 models, writes reports/training_record.json and models/live-v1/
```

Results and their limits: `docs/model-results.md`.

## Documents

| File | Contents |
|---|---|
| `docs/requirements/SRS.md` | Requirements, kept in line with the software; `CHANGELOG.md` lists every change |
| `docs/architecture.md` | The three servers, their API, failure handling and how to run them |
| `docs/model-results.md` | Data, model comparison and acceptance criteria on real data |
| `docs/testing.md` | Test catalogue and class demonstration |
| `docs/TODO.md` | Task list; commit messages start with the task id |
| `docs/scrum-log.md` | Sprints and scrum masters |

## Branches

`main` holds reviewed code only. Work happens on `feature/*`, `docs/*` and `fix/*` branches and is merged through pull requests.
