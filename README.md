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
python -m backend.ingestion.run_all
```

The page text of every PDF is cached in `data/ocr/` and committed, so everyone works on the same OCR text and no OCR runs on a normal checkout. Delete a folder there only when that PDF or the OCR settings change (the text corrections then need re-checking).

Output: `data/processed/Tabayyun_KB.xlsx` (one sheet per table, plus `validation`).

- **Articles and chunks** are extracted from `data/raw/*.pdf`. Scanned PDFs are read with Tesseract (Arabic); the nationality PDF is read with `pdftotext`.
- **Reviewed reference data** lives in `data/seed/` and is edited by hand, because OCR cannot read it reliably:
  - `issuers.json`: authorities and the referral text shown when a rule was changed by a document the user may not see.
  - `documents.json`: decision numbers, dates and status of every document (source and referenced).
  - `relations.json`: which document repeals, replaces or amends which, with evidence.
  - `procedures.json`: procedures and their requirements with source articles (`review_status: draft` until approved).
  - `text_corrections.json`: reviewed OCR fixes, one exact replacement inside one article. A correction whose text is not found is logged as skipped.
  - `reviewed_articles.json`: articles checked against the scanned PDFs. An article with a text correction also counts as reviewed.
- Do not open the PDFs in the VS Code text editor: saving them there corrupts the file.

## OCR text review

```
python -m backend.ingestion.review_export
```

Writes `data/processed/Tabayyun_OCR_Review.xlsx` from the current text: a sheet of articles still to review, a sheet of reviewed ones, and an empty corrections sheet. Fill the yellow columns (review status, and one corrections row per mistake with the wrong text copied exactly from the article), then:

```
python -m backend.ingestion.review_import data/processed/Tabayyun_OCR_Review.xlsx
python -m backend.ingestion.run_all
python -m backend.db.seed
```

The import checks every correction against the current article text first. If any row has a problem, it lists all problems and saves nothing. Rows already imported are skipped, so running it twice is safe.
