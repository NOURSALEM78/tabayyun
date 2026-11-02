# Tabayyun — Coding Standards

## Project
Tabayyun is a FastAPI + PostgreSQL (pgvector) backend for Arabic regulatory question answering and access-request decisions. Data comes ONLY from the files in data/raw/.

## Structure
- One responsibility per module. Keep layers separate: db/ (models, session), ingestion/ (OCR, cleaning, splitting, extraction), retrieval/, llm/, services/ (business logic), api/ (routes only).
- API routes must not contain business logic or SQL; they call services/.
- No circular imports. Shared helpers go in backend/common/.

## Code style
- Python 3.11+, full type hints on every function, PEP 8, formatted with black (line length 100) and checked with ruff.
- Small functions (ideally under 40 lines), each doing one thing, with clear English names (e.g. split_into_articles, normalize_arabic).
- Every module and public function has a short docstring explaining purpose, inputs and outputs.
- No magic values: constants (regex patterns, keyword lists, file paths, expected article counts) live in a config.py or constants.py per package.
- No hard-coded secrets or URLs; read from environment variables via a settings module (pydantic-settings) with .env.example documented.
- Use pathlib for paths, logging (not print) with clear messages, and specific exceptions with helpful messages.
- Prefer pure functions for text processing so they can be unit tested.

## Database
- SQLAlchemy 2.0 typed models; never write raw SQL strings inside services unless needed for pgvector queries, and then keep them in retrieval/queries.py.
- Never delete or overwrite legal text: new versions are inserted and old ones get status repealed/amended.
- Column names must match the agreed schema exactly; do not add or rename columns without asking.

## Arabic text
- Keep the original cleaned text in `text`; use `text_normalized` only for search.
- All Arabic normalization lives in one module (ingestion/normalize.py) and is reused everywhere.

## Testing
- Add pytest tests in tests/ for every text-processing function (cleaning, ordinal-to-number conversion, article splitting, clause splitting, normalization) using small real Arabic examples.
- Ingestion must be re-runnable (idempotent) and cache OCR output.

## Working rules
- Before large changes, briefly state the plan and the files you will create or modify.
- After finishing, summarize what changed, how to run it, and any problems found.
- Do not invent data. If something cannot be extracted reliably, report it instead of guessing.