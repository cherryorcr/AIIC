# PostgreSQL migrations

The challenge deployment uses SQLite by default (`DATABASE_PATH`). The
versioned SQL in this directory is the production PostgreSQL baseline. It
contains the same tables and persistence contract as `app.storage.db` plus
native `JSONB`, foreign keys, and indexes.

```powershell
pip install "psycopg[binary]"
$env:DATABASE_URL = "postgresql://user:password@db-host:5432/interview"
python scripts/migrate_postgres.py
```

The checked-in `001_postgres_schema.sql` is the production baseline used by
`Database.init()` when `DATABASE_URL` is configured. Migrations are idempotent
(`CREATE TABLE IF NOT EXISTS` and `schema_migrations` records). Keep
credentials in the deployment secret store; do not place them in this
repository or in migration files. The adapter reuses the same repository
methods (`save_session`, `save_user_profile`, `save_job`, `favorite_question`,
`save_report`, etc.) without changing API handlers. Version 6 adds registered
account columns plus `auth_sessions`; session tokens are stored only as hashes.
