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

Output: `data/processed/Tabayyun_KB.xlsx` (one sheet per table, plus `validation`).

- **Articles** come from reviewed article tables in `data/raw/` (no OCR):
  - `civil_status_law_articles.xlsx` (CSL, 96 articles)
  - `civil_status_regulation_articles.xlsx` (CSR, 199 articles)
  - `nationality_law_and_regulation_articles.xlsx` (NAT, 30 articles, and NATR, 35 articles;
    each row's `الرمز` says which document it belongs to)

  Each table has one row per article with the columns `الرمز`, `رقم المادة`, `نص المادة الحالي`
  (and optionally `صفحة الـ PDF`). To fix an article, edit its text in the table and re-run the
  pipeline. Ingestion stops and lists every invalid row (unknown code, non-numeric or duplicated
  article number, empty text); missing or extra article numbers show in the `validation` sheet.
  A document gets its table through `table_filename` in `backend/ingestion/constants.py`.
  The PDFs stay in `data/raw/` as the original sources.
- **Chunks** are the clauses of each article (markers like `أ -`, `1 -`, `أ.` or `1.`).
- **Reviewed reference data** lives in `data/seed/` and is edited by hand, because OCR cannot read it reliably:
  - `issuers.json`: authorities and the referral text shown when a rule was changed by a document the user may not see.
  - `documents.json`: decision numbers, dates and status of every document (source and referenced).
  - `relations.json`: which document repeals, replaces or amends which, with evidence.
  - `procedures.json`: procedures and their requirements with source articles (`review_status: draft` until approved).
  - `text_corrections.json`: reviewed OCR fixes for documents still read from PDFs, one exact replacement inside one article. A correction whose text is not found is logged as skipped.
  - `reviewed_articles.json`: OCR'd articles checked against the PDFs. An article with a text correction also counts as reviewed.
- Do not open the PDFs in the VS Code text editor: saving them there corrupts the file.

## OCR text review

Only for documents still read from PDFs (documents with an article table are edited in the table).

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

## Embeddings (BGE-M3)

```
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m backend.retrieval.embed
```

Encodes every chunk that has no embedding yet with `BAAI/bge-m3` (1024 dimensions, normalised for cosine search) and stores it in `chunks.embedding` (pgvector). The first run downloads the model (about 2 GB). The CPU build of PyTorch avoids a large GPU download.

Re-running is cheap: only chunks without an embedding are encoded. When `python -m backend.db.seed` updates a chunk whose text changed, it clears that chunk's embedding, so the next `embed` run refreshes exactly those chunks. Use `--all` to re-encode everything (e.g. after changing the model).

## Retrieval (search)

```
python -m backend.retrieval.search "كم مدة التبليغ عن المواليد داخل المدن؟" --employee E001
```

For one question and one employee:

1. **Visibility:** documents at or below the employee's access level; a document with an access list (`document_access`) is visible only to the roles on it.
2. **Rules in force:** only current chunks of active documents and articles.
3. **Hybrid search:** by meaning (BGE-M3 + pgvector, cosine) and by keywords (BM25 on normalised text), fused with reciprocal rank fusion.
4. **Whole articles:** search runs on chunks (clauses), but each result is the whole article of a matched chunk, and each article appears once (through its best-ranked chunk). A clause alone can be just an intro such as «المكلفون بالتبليغ عن المواليد هم:». The result limit counts articles.
5. **Changed rules:** if an article (or its whole document) was amended, repealed, replaced or excepted by a document the employee may not see, its old text is dropped and the issuer's referral text is returned instead; the hidden document is never named. If the employee may see the newer document, the article is kept with a note naming it.

### Amended law articles

Fourteen articles of the Civil Status Law (2, 15, 19, 20, 22, 25, 26, 34, 38, 67, 74, 76, 82, 83) carry the mark «تعديلات المادة» in `civil_status_law.pdf`. The mark links to an internal file of the legal department that the project does not have, so the amendment's text, date and instrument are unknown. Each is recorded as an `amends` relation from a document «تعديلات المادة (n)» (`data/seed/documents.json`, `relations.json`). Because the system holds no text for those documents, the article is still returned, for every employee, but with a notice that it was amended and the issuer's referral (`amended_notices` in the result):

> ⚠ تنبيه: هذه المادة عليها تعديلات لدى الإدارة القانونية، ولا يتوفر للنظام نص التعديل. للحصول على الحكم المعمول به في هذه المسألة، يُرجى الرجوع إلى الإدارة القانونية بوكالة وزارة الداخلية للأحوال المدنية.

The answer then quotes the article word for word («نص المادة كما ورد: …») with its citation; it must not summarise it or state its rule as settled.

```
python -m backend.retrieval.search "كم مدة التبليغ عن المواليد؟" --employee E009
```

A secret circular is different: an article changed by a document the employee may not see is dropped and only the referral is returned, without the article or the circular's name.
