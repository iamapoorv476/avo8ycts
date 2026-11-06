# GB Wind Desk: Day-Ahead Forecast Accuracy Tool

The day-ahead wind forecast overestimated generation by approximately **1,840 MW** throughout January 2026. This tool puts a number on that bias using real data from Elexon BMRS: `FUELHH` for actual generation and `WINDFOR` for forecasts. No synthetic data is used.

**Live demo:** https://avo8ycts-omep.vercel.app/  
**Backend API:** https://avo8ycts-production.up.railway.app/  
**Demo video:** https://youtu.be/9CyH0s_jQXs

---

## What it does

The tool answers three questions a wind trading desk needs to consider before placing day-ahead orders:

1. **How far off has the forecast been, and is the error mostly bias or noise?** The month-level metrics on the dashboard show this through MBE, MAE, RMSE, and a tail-risk ratio.
2. **For a specific delivery day, how did the forecast differ from actual generation throughout the day?** The chart compares forecasts against actual settlement-period data.
3. **Going into the evening demand peak (16:00–19:00 GMT, settlement periods 33–38), what generation figure is safer to plan around?** The risk floor provides a bias-corrected estimate with roughly 90% downside confidence for the desk's highest-risk window.

Every number displayed is either returned directly by the API or derived through a simple arithmetic calculation using API values. Nothing is made up. I wanted to keep the dashboard grounded in actual data, rather than display recommendations the underlying calculations cannot support. I've explained this in the "no fabricated numbers" section of `docs/design-decisions.md`.

## How it's built

```text
Elexon BMRS (FUELHH + WINDFOR)
          │
          │ Build-time fetch
          ▼
   ingestion/*.py → SQLite
          │          (matched series, metrics, risk floor)
          │
          ▼
   FastAPI (3 endpoints)
          │
          ▼
   React + Recharts dashboard
```

The main calculations happen offline during ingestion. This includes forecast matching, bias and error metrics, and risk-floor calculations. The API reads the stored results rather than repeating these calculations on every request.

There are two exceptions to the simple read-only flow:

- `/metrics` calculates the exclusion-reason breakdown using a `GROUP BY` over data already stored in the database.
- When a previously unseen `RANGE` is requested, `/metrics` calculates its metrics and caches the result in `metrics_summary`. Subsequent requests for that range use the cached result.

This keeps the request path lightweight without requiring every possible date range to be calculated in advance. The reasoning behind these decisions, along with the debugging notes, is documented in `docs/design-decisions.md`.

For the database schema and column definitions, see `docs/data-model.md`.

For endpoint contracts and example responses, see `docs/api.md`.

For the original requirements and acceptance criteria, see `docs/requirements.md`.

## Repo layout

```text
backend/
  ingestion/     Fetches Elexon data, matches forecasts with actuals,
                 and calculates metrics and risk floors offline
  db/            SQLite schema and connection helper
  api/           FastAPI app with 3 endpoints
  tests/         pytest suite: 28 tests covering ingestion logic and API
  Dockerfile     Builds the API image and runs ingestion at build time

frontend/
  src/
    api/         Typed fetch client
    hooks/       Data-fetching hooks
    components/  Header, MetricsRow, ForecastChart, AdvisoryPanel
    App.tsx      Month-level risk profile and day-level chart
                 with the advisory panel
  Dockerfile     For local use; production deployment uses Vercel's build

docs/
  requirements.md
  data-model.md
  api.md
  design-decisions.md
  deployment.md

docker-compose.yml   One-command full-stack local run
```

## Running it locally

**Docker, one command:**

```bash
docker compose up --build
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

The first build takes a few minutes because it does more than install dependencies. It also runs the ingestion pipeline against Elexon's live API.

**Manual setup, if you want to run each part separately:**

```bash
cd backend
pip install -r requirements.txt --break-system-packages
python ingestion/run_ingestion_pipeline.py
python -m uvicorn api.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

**Tests:**

```bash
cd backend
pytest -v
```

One thing to keep in mind when running the tests: the test suite and the real ingestion pipeline use the same SQLite file. Running `pytest` after a real ingestion run removes that database during fixture cleanup. The API will then fail because the new database file has no schema.

This is a documented tradeoff for the project's scope. The safe workflow is to run ingestion first, then start the API or demo. If you run the tests in between, run ingestion again before serving the application. More details are in `docs/design-decisions.md`.

## Deployment

The backend is deployed on Railway, and the frontend is deployed on Vercel. The deployment guide in `docs/deployment.md` covers the setup, why Railway was chosen over Heroku, and how the frontend connects to the backend through `VITE_API_BASE_URL`.

## Stack

Python, FastAPI, SQLite, and pytest on the backend. React, TypeScript, Vite, Tailwind CSS, and Recharts on the frontend. Docker, Railway, and Vercel for deployment.

## A note on how this was built

I used Claude (Anthropic) as a collaborative implementation partner throughout this project, not as an autonomous code generator. I defined the requirements, made the architecture and product decisions, including data scope, tech stack choices, UX direction, and what to cut under the time limit, and directed each implementation step.

Claude helped write code based on those decisions, which I then ran, tested, and verified myself against real Elexon data on my own machine. That process included finding actual bugs and UI issues, reporting them, and checking the fixes.

The debugging stories in `docs/design-decisions.md` reflect that actual back-and-forth during development, rather than a summary written after the project was finished.