# Tabayyun

## Database Setup

Start PostgreSQL with pgvector, install the Python dependencies, and create the schema:

```bash
docker compose up -d
pip install -r requirements.txt
python -m backend.db.database
```

The database connection defaults to `postgresql+psycopg://tabayyun:tabayyun@localhost:5432/tabayyun`.
Copy `.env.example` to `.env` to override `DATABASE_URL` for another environment.

## Tests

```bash
pytest
```