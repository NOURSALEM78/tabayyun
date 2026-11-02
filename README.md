# Tabayyun

## Database Setup

Start PostgreSQL with pgvector, install the Python dependencies, and create the schema:

```bash
cp .env.example .env
docker compose up -d
pip install -r requirements.txt
python -m backend.db.database
```

The database connection is read from `DATABASE_URL` in `.env`. The example file contains the local
Compose connection string; set a different value for other environments.

## Tests

```bash
pytest
```
## Knowledge-base ingestion

```
rm -rf data/processed/civil_status_law data/processed/civil_status_regulation data/processed/nationality_law_and_regulation   # only when the PDFs or OCR settings change
python -m backend.ingestion.run_all
```

Output: `data/processed/Tabayyun_KB.xlsx` (one sheet per table, plus `validation`).

- **Articles and chunks** are extracted from `data/raw/*.pdf`. Scanned PDFs are read with Tesseract (Arabic); the nationality PDF is read with `pdftotext`.
- **Reviewed reference data** lives in `data/seed/` and is edited by hand, because OCR cannot read it reliably:
  - `issuers.json`: authorities and the referral text shown when a rule was changed by a document the user may not see.
  - `documents.json`: decision numbers, dates and status of every document (source and referenced).
  - `relations.json`: which document repeals, replaces or amends which, with evidence.
  - `procedures.json`: procedures and their requirements with source articles (`review_status: draft` until approved).
- Do not open the PDFs in the VS Code text editor: saving them there corrupts the file.
