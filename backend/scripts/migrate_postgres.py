"""Apply the checked-in PostgreSQL schema migrations.

This intentionally has no dependency on Alembic so a fresh deployment can
bootstrap with one command.  Install ``psycopg[binary]`` on the production
image and provide ``DATABASE_URL`` (never commit credentials).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply AI Interview Coach PostgreSQL migrations")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--sqlite-path", help="Optional legacy SQLite database to copy after schema bootstrap")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - only exercised on deploy image
        raise SystemExit("PostgreSQL migrations require psycopg[binary]. Install it with pip.") from exc

    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    files = sorted(migration_dir.glob("*.sql"))
    if not files:
        raise SystemExit(f"No migration files found in {migration_dir}")
    with psycopg.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            for path in files:
                sql = "\n".join(
                    line for line in path.read_text(encoding="utf-8").splitlines()
                    if not line.lstrip().startswith("--")
                )
                for statement in re.split(r";\s*(?:\n|$)", sql):
                    statement = statement.strip()
                    if statement:
                        cur.execute(statement)
            if args.sqlite_path:
                copied = _copy_sqlite(cur, Path(args.sqlite_path))
            else:
                copied = 0
        conn.commit()
    suffix = f"; copied {copied} row(s) from SQLite" if args.sqlite_path else ""
    print(f"Applied {len(files)} migration file(s) to PostgreSQL{suffix}")
    return 0


def _copy_sqlite(cur, sqlite_path: Path) -> int:
    """Copy an existing MVP SQLite database without changing public IDs.

    The table order follows foreign-key dependencies. JSON text columns are
    wrapped as JSONB values by psycopg; all other fields remain untouched.
    """
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    import psycopg
    from psycopg.types.json import Json

    tables = [
        "schema_migrations", "users", "user_profiles", "jobs", "sessions",
        "sources", "skills", "questions", "question_skills", "graph_edges",
        "question_favorites", "turns", "feedback", "model_invocations", "reports",
        "candidate_documents",
    ]
    boolean_columns = {"is_temporary", "is_active", "redistribution_allowed", "pii_redacted"}
    copied = 0
    with sqlite3.connect(sqlite_path) as source:
        source.row_factory = sqlite3.Row
        for table in tables:
            columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})").fetchall()]
            if not columns:
                continue
            rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
            for row in rows:
                values = []
                for column, value in zip(columns, row):
                    if column in boolean_columns and value is not None:
                        # SQLite stores booleans as 0/1 integers; psycopg must
                        # receive a Python bool for PostgreSQL boolean columns.
                        value = bool(value)
                    if column.endswith("_json") and isinstance(value, str):
                        try:
                            value = Json(__import__("json").loads(value))
                        except (TypeError, ValueError):
                            pass
                    values.append(value)
                placeholders = ", ".join("%s" for _ in columns)
                names = ", ".join(columns)
                cur.execute(
                    f"INSERT INTO {table} ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                    values,
                )
                copied += 1
    return copied


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
