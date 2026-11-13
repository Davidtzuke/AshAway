# ToDo list

Repo copy of the Trello tasks, so each commit can point at a task id.

| ID | Task | Requirement | Priority | Status |
|----|------|-------------|----------|--------|
| T1 | Fix the Track A loader: no fire-day inputs, 2:1 negatives per split, data report | AI2, NFR2, NFR9 | Must | Done |
| T2 | Filter by Greek boundary and report Greece and May-October results | AI3, AI4 | Must | Done |
| T3 | Compare models on real data, calibrate, write the training record | AI1, AI3, AI4, AI5, NFR8 | Must | Done |
| T4 | Validate requests and reject unsupported places and dates | FR1, FR9 | Must | Done |
| T5 | Turn calibrated scores into risk levels with an explanation | FR2, FR4, NFR6 | Must | Done |
| T6 | Evidence items with type labels, and stale or missing input detection | FR5, FR8, NFR4 | Must | Done |
| T7 | Open-Meteo weather and air quality feeds, NASA FIRMS adapter, failures marked unavailable | FR3, NFR3, NFR5 | Must | Done |
| T8 | Assessment service with lower-risk alternatives and destination comparison | FR2, FR6, FR7 | Must | Done |
| T9 | Command-line interface for travellers | UR1, NFR7 | Must | Done |
| T10 | Mark tests as unit or integration, run them in GitHub Actions, write the test catalog | Task 5 | Must | Done |
| T11 | One-page test report and class demonstration | Task 5 | Must | Report done, demo after the deadline |
| T12 | Get a FIRMS key and check that adapter against the live service | FR3 | Should | ToDo |
| T13 | GDELT disruption feed | FR3 | Should | ToDo |
| T14 | Web interface | UR1, UR2 | Should | ToDo |
| T15 | Evaluate the municipality-day `affected` target | FR2, AI5 | Should | ToDo |
| T16 | Correct probabilities for the real fire base rate | AI5 | Should | ToDo |
| T17 | Let users report a wrong assessment | AI8 | Should | ToDo |
| T18 | AI inference server: loads the saved model and serves `/model` and `/predict` over HTTP | Task 6, NFR4 | Must | Done |
| T19 | Orchestrator server: feeds, features and evidence checks; calls the AI server and turns its failures into clear errors | Task 6, FR3, FR5 | Must | ToDo |
| T20 | Interface server: validates requests, forwards them to the orchestrator, stores every request and result | Task 6, FR1, NFR3, NFR7 | Must | ToDo |
| T21 | Test the three servers together over real HTTP, including AI and orchestrator outages | Task 6 | Must | ToDo |
| T22 | Start commands, README and architecture notes for the three servers | Task 6 | Must | ToDo |
| T23 | One-page preliminary architecture report | Task 6 | Must | ToDo |
