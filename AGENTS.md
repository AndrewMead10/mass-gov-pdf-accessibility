# Repository Guidelines

## Project Purpose
- TODO: Confirm with stakeholders that the primary audience is Mass.gov digital accessibility teams; current assumption is that they need to upload PDFs, run Adobe PDF Services accessibility checks, and centralize the resulting reports/tagged files.
- Capture per-page findings in SQLite so downstream pipelines can highlight high-impact accessibility issues and attach remediation assets.
- Provide an approachable UI (Jinja templates + Tailwind/HTMX in `templates/` and `static/`) so non-developers can trigger checks, monitor processing, and download outputs.
- Maintain an extensible pipeline layer that translates Adobe findings into actionable tasks and optional auto-fixes stored under `output_pdfs/pipelines/`.

## Current Capabilities
- `app/api/upload.py`, `documents.py`, and `processing.py` expose endpoints for ingesting PDFs, listing stored runs, and kicking off background processing with per-page concurrency.
- `app/pdf_accessibility_checker.py` wraps Adobe's SDK to generate tagged PDFs and JSON reports; page-level runs are parallelized via `_collect_page_reports` to improve throughput.
- Pipeline orchestration in `app/pipelines/manager.py` and friends builds `PipelineContext` payloads, persists structured findings, and optionally executes resolve steps when `PIPELINES_ATTEMPT_RESOLVE` is enabled.
- Processed artifacts and findings are rendered in the dashboard (`templates/dashboard.html`) so reviewers can triage issues without digging into raw JSON.
- Docker and Docker Compose configs mirror the local layout, wiring volumes for input/output directories and credentials to simplify team onboarding.

## Collaboration Notes
- As the user shares new product goals, stakeholder needs, or workflow details, append them here so future agents inherit the latest context.
- Call out any uncertainties or assumptions directly in this document (e.g., prefix with `TODO:`) until the team confirms them.
- Keep asking the user for clarifications when requirements feel ambiguous; the project is evolving and documentation should track that evolution.

## Project Structure & Module Organization
- Core FastAPI application lives in `app/`; API routers sit in `app/api/`, persistence helpers in `app/database.py` and `app/crud.py`, and PDF pipelines in `app/pipelines/`.
- Web assets are split between `templates/` (Jinja HTML) and `static/` (CSS, JS, and uploaded files). Generated artifacts land in `output_pdfs/`, while incoming files live in `input_pdfs/`; the SQLite database `pdf_accessibility.db` is for local development only.
- Docker assets (`Dockerfile`, `docker-compose.yml`) mirror the local layout, so avoid renaming directories without updating those files.

## Build, Test, and Development Commands
- Create a virtual environment and install deps: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run the API with autoreload during development: `uvicorn app.main:app --reload` (equivalent to `python -m app.main`).
- Launch the full stack via containers: `docker-compose up --build`; volumes mount `input_pdfs/`, `output_pdfs/`, and the credentials file for you.
- Execute the test suite (once tests exist): `pytest`; add `-k` selectors to target individual pipelines or API modules.

## Coding Style & Naming Conventions
- Follow PEP 8: 4-space indentation, snake_case for functions/variables, PascalCase for Pydantic models and SQLAlchemy classes.
- Add type hints and concise docstrings to new public call sites, especially in `app/pipelines/` and `app/api/`.
- Keep logging consistent with existing `pdf_accessibility_checker.py` patterns; prefer structured messages over prints.

## Testing Guidelines
- Place unit tests alongside code under a mirrored `tests/` hierarchy (`tests/api/`, `tests/pipelines/`, etc.) and use `pytest` fixtures for temp files and database sessions.
- Exercise FastAPI routes with `TestClient` and validate both JSON payloads and database side effects; stub Adobe SDK calls to keep runs offline.
- For pipeline additions, include golden PDFs in `input_pdfs/fixtures/` and assert on serialized findings stored by the pipeline manager.

## Commit & Pull Request Guidelines
- Use short imperative commit subjects (e.g., `add pipeline abstraction`); limit body lines to 72 chars and reference issues with `Fixes #id` when applicable.
- PRs should describe the change, list manual/automated verification (`pytest`, `uvicorn` smoke test, Docker build), and attach before/after screenshots for UI tweaks.
- Flag schema or pipeline migrations in the PR description so reviewers can plan data refreshes.

## Security & Configuration Tips
- Store Adobe credentials in `pdfservices-api-credentials.json` or environment variables; never commit personal keys.
- Treat `pdf_accessibility.db` as ephemeral—reset with a fresh file or migrations before sharing branches.
- Verify that uploaded PDFs are non-sensitive before checking them into `input_pdfs/fixtures/`.
