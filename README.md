# SabiLab

SabiLab is a FastAPI-powered simulated business communication and decision-making lab. It presents a scenario-driven huddle in which a learner plays a business role, discusses a problem with AI teammates, submits a recommendation, and receives structured assessment feedback.

The project centers on scenario-based evaluation: a learner is given a brief, joins a timed huddle, responds to a twist, writes a recommendation, and then the application scores that output against a rubric using LLM-based reading and grading. The output includes session results, reviewer review screens, and a scored summary for each attempt.

## What the project does

- Starts a scenario session and preserves conversation state in SQLite or PostgreSQL
- Loads structured training scenarios from the `scenarios/` directory
- Simulates a small team with scripted AI participants and a business-owner prompt
- Evaluates learner messaging and task output against rubric criteria
- Serves a reviewer dashboard at `/review` secured by a password
- Exposes a web UI and API for both the learner and reviewer experience

## Repository structure

- `main.py` — FastAPI application entry point and route definitions
- `config.py` — runtime configuration, LLM defaults, and environment settings
- `db.py` — shared database bootstrap and connection layer for SQLite/PostgreSQL
- `schema.sqlite.sql` and `schema.postgres.sql` — database schema definitions
- `scenarios/` — scenario definitions, including the bundled `adaeze.json` case
- `app/` — core logic for sessions, tasks, messaging, scoring, review, cards, and pipeline execution
- `static/` — landing page and browser UI assets
- `rubric.json` — scoring rubric used by the assessment pipeline
- `tests/` — pytest regressions covering sessions, gate logic, reviews, and pipeline behavior

## Supported stack

- Python 3
- FastAPI
- SQLite by default; PostgreSQL supported via `DATABASE_URL`
- OpenAI-compatible LLM providers (default configuration targets Groq)
- pytest for validation

## Local setup

1. Clone the repository.
2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a local environment file from the sample:

```bash
cp .env.example .env
```

5. Fill in any required secrets before running the app.

Example `.env` values:

```dotenv
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_api_key_here
REVIEW_PASSWORD=changeme
```

Optional fallback provider settings are also supported in `config.py`:

```dotenv
FALLBACK_BASE_URL=
FALLBACK_API_KEY=
FALLBACK_MODEL=
```

## Running the app

Start the API server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- `http://localhost:8000/` for the landing page
- `http://localhost:8000/app` for the application UI
- `http://localhost:8000/review?pw=changeme` for the reviewer dashboard (if `REVIEW_PASSWORD` is set)

The app also exposes API routes such as:

- `POST /session` to create a session
- `POST /session/{session_id}/message` to send chat messages
- `POST /session/{session_id}/score` to trigger assessment scoring
- `GET /session/{session_id}/results` to read the final result
- `GET /health` for a basic health check

## Database configuration

By default, the app uses the local SQLite database at `sabilab.db`.

- `db.py` initializes the schema automatically at startup
- `schema.sqlite.sql` is the default schema for local development
- `schema.postgres.sql` is used when `DATABASE_URL` is configured

Example PostgreSQL configuration:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/sabilab"
```

When `DATABASE_URL` is present, the app uses PostgreSQL instead of the default SQLite database. The database bootstrap logic in `db.py` handles the backend-neutral schema and test database isolation.

## Scenario model

The app loads scenarios from JSON files in `scenarios/`. Each scenario contains the business brief, roster, owner script, facts, timeline, task prompts, checks, and rubric-aligned approaches.

The bundled `scenarios/adaeze.json` scenario is a practical accounting and supply-risk exercise. It references:

- cash on hand
- an overdue invoice
- discount negotiation
- a time-sensitive customer request
- a supplier disruption twist

This is the clearest example of the product’s intended use: a learner must balance customer expectations, cash constraints, and supply continuity in a concise recommendation.

## Validation and evidence

This repository includes tests that validate the main flows and provide evidence that the application is structured and behaving as expected:

- `tests/test_review.py` checks password gating and the reviewer dashboard
- `tests/test_session.py` covers session lifecycle logic
- `tests/test_pipeline.py` exercises scoring pipeline behavior
- `tests/test_gate.py`, `tests/test_verification.py`, and related files cover decision checks and verification flows
- `rubric.json` defines the scoring dimensions and evidence-based evaluation structure

The code also provides runtime evidence for the intended LLM workflow:

- `config.py` sets default provider and model values for reading/scoring calls
- `app/pipeline/llm.py` wraps an OpenAI-compatible client and retries JSON calls with provider fallback support
- `main.py` shows the actual API endpoints and scoring flow used by the application

## Recommended verification commands

Run the project tests:

```bash
pytest
```

Check LLM connectivity using the bundled helper script:

```bash
python check_llm.py
```

## Relevant documents and support files

These files are the most important references when working on or extending the system:

- `main.py` — API surface and bootstrapping
- `config.py` — environment parameters and defaults
- `db.py` — database connection and migration behavior
- `schema.sqlite.sql` — SQLite schema
- `schema.postgres.sql` — PostgreSQL schema
- `rubric.json` — scoring rubric and performance levels
- `scenarios/adaeze.json` — concrete scenario example
- `app/pipeline/llm.py` — LLM calls, retries, and fallback logic
- `app/review_routes.py` — reviewer dashboard security and gate
- `tests/` — validation evidence for the product features

## Notes

- Some parts of the workflow depend on an external LLM provider. If a model call fails because credentials are missing, the app will raise a configuration error until `GROQ_API_KEY` or the fallback settings are populated.
- The reviewer dashboard is intentionally password-protected and reads from the same persisted session data used by the scoring pipeline.
- The repository is designed to support both demo and real sessions via `mode`, `variant`, and scenario-based logic.
