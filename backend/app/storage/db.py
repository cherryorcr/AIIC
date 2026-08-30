from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, value: str, length: int = 12) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def decode_json(value: Any, default: Any) -> Any:
    """Decode SQLite text or PostgreSQL JSONB values uniformly."""
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class _PostgresCompatConnection:
    """Tiny DB-API facade for the SQLite-shaped repository SQL.

    It keeps the storage methods readable and centralizes dialect conversion;
    production deployments still use a real psycopg connection and transaction.
    """

    def __init__(self, connection: Any):
        self.raw = connection

    def execute(self, sql: str, params: Any = None):
        translated = Database._pg_sql(sql)
        return _PostgresCompatCursor(self.raw.execute(translated, Database._pg_params(params or ())))

    def executescript(self, script: str):
        script = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
        for statement in re.split(r";\s*(?:\n|$)", script):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self):
        # psycopg's connection context manager closes the connection on exit.
        # This adapter is held for the lifetime of the FastAPI process, so a
        # repository transaction must commit/rollback without closing it.
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        return False

    def close(self):
        return self.raw.close()


class _HybridRow(dict):
    """Mapping row that also supports the positional indexing used by SQLite."""

    def __getitem__(self, key: Any):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _PostgresCompatCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return _HybridRow(row) if isinstance(row, dict) else row

    def fetchall(self):
        return [_HybridRow(row) if isinstance(row, dict) else row for row in self._cursor.fetchall()]


class Database:
    """MVP 持久化层。

    默认使用 SQLite 让挑战项目可以零配置启动；生产环境可将该接口替换为
    PostgreSQL + pgvector，而业务服务不需要改变。
    """

    def __init__(self, path: Path | str, database_url: str | None = None):
        # Keep SQLite as the zero-configuration default, while allowing the
        # same repository methods to run against PostgreSQL in production.
        configured_url = database_url or (str(path) if str(path).startswith(("postgres://", "postgresql://")) else "")
        self.database_url = configured_url
        self.is_postgres = bool(configured_url)
        self.path = Path(path) if not self.is_postgres else Path(":postgresql:")
        if not self.is_postgres:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if self.is_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - deploy-only branch
                raise RuntimeError("DATABASE_URL requires psycopg[binary] to be installed") from exc
            raw_connection = psycopg.connect(self.database_url, row_factory=dict_row, autocommit=False)
            self._conn = _PostgresCompatConnection(raw_connection)
        else:
            # SQLite connections are shared by the FastAPI worker threads in
            # the challenge deployment.  Enable the pragmas on every connection
            # so foreign keys and concurrent writes behave deterministically.
            self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA busy_timeout = 5000")
            if str(self.path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")

    @staticmethod
    def _pg_sql(sql: str) -> str:
        """Translate the small SQLite SQL dialect used by this repository."""
        ignored = "INSERT OR IGNORE" in sql.upper()
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if ignored and "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        # SQLite represents booleans as 0/1, while the PostgreSQL schema uses
        # native BOOLEAN columns.  TRUE/FALSE are also valid SQLite literals,
        # so this keeps one repository query surface for both dialects.
        sql = re.sub(r"\bis_active\s*=\s*1\b", "is_active = TRUE", sql, flags=re.I)
        sql = re.sub(r"\bis_active\s*=\s*0\b", "is_active = FALSE", sql, flags=re.I)
        # PostgreSQL accepts the same DDL and SELECT syntax after qmark
        # parameters are converted to psycopg's positional placeholders.
        return sql.replace("?", "%s")

    @staticmethod
    def _pg_params(params: Any) -> Any:
        """Wrap serialized JSON values so psycopg binds them as JSONB."""
        if params is None:
            return params
        try:
            from psycopg.types.json import Json
        except ImportError:  # pragma: no cover
            return params
        values = list(params) if isinstance(params, (tuple, list)) else [params]
        adapted = []
        for value in values:
            if isinstance(value, str) and value[:1] in {"{", "["}:
                try:
                    adapted.append(Json(json.loads(value)))
                    continue
                except (TypeError, ValueError):
                    pass
            adapted.append(value)
        return tuple(adapted) if isinstance(params, tuple) else adapted

    def _execute(self, sql: str, params: Any = None):
        if not self.is_postgres:
            return self._conn.execute(sql, params or ())
        return self._conn.execute(self._pg_sql(sql), self._pg_params(params or ()))

    def _executescript(self, script: str) -> None:
        if not self.is_postgres:
            self._conn.executescript(script)
            return
        # The checked-in baseline contains standalone statements only; split
        # on semicolons so psycopg can execute them in one transaction.
        script = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
        for statement in re.split(r";\s*(?:\n|$)", script):
            statement = statement.strip()
            if statement:
                self._execute(statement)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
        """Add a column to an existing MVP database without destructive migration."""
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def init(self) -> None:
        with self._lock, self._conn:
            if self.is_postgres:
                migration = Path(__file__).resolve().parents[2] / "migrations" / "001_postgres_schema.sql"
                self._executescript(migration.read_text(encoding="utf-8"))
                return
            self._executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    job_id TEXT,
                    mode TEXT NOT NULL,
                    role TEXT NOT NULL,
                    job_text TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_question_json TEXT,
                    matched_skills_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    code TEXT,
                    language TEXT,
                    algorithm_result_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    turn_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(turn_id) REFERENCES turns(id)
                );
                CREATE TABLE IF NOT EXISTS model_invocations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    task TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    latency_ms REAL,
                    status TEXT NOT NULL,
                    fallback_reason TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_usd REAL,
                    attempt INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    url TEXT,
                    license TEXT,
                    source_type TEXT NOT NULL,
                    version TEXT,
                    published_at TEXT,
                    accessed_at TEXT,
                    redistribution_allowed INTEGER NOT NULL DEFAULT 0,
                    pii_redacted INTEGER NOT NULL DEFAULT 1,
                    content_hash TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY,
                    process_type TEXT NOT NULL,
                    role TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    question TEXT NOT NULL,
                    follow_ups_json TEXT NOT NULL DEFAULT '[]',
                    rubric_json TEXT NOT NULL DEFAULT '[]',
                    function_name TEXT,
                    tests_json TEXT NOT NULL DEFAULT '[]',
                    source_id TEXT NOT NULL,
                    source_confidence TEXT NOT NULL DEFAULT 'unknown',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES sources(source_id)
                );
                CREATE TABLE IF NOT EXISTS question_skills (
                    question_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    PRIMARY KEY(question_id, skill_id),
                    FOREIGN KEY(question_id) REFERENCES questions(id),
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
                );
                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    from_type TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    to_type TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    source_id TEXT,
                    UNIQUE(from_type, from_id, relation, to_type, to_id)
                );
                -- User-facing persistence.  These tables intentionally use
                -- JSON payloads for evolving profile/JD/report fields while
                -- retaining frequently filtered fields as columns.
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL DEFAULT '',
                    is_temporary INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    skills_json TEXT NOT NULL DEFAULT '[]',
                    projects_json TEXT NOT NULL DEFAULT '[]',
                    education TEXT,
                    experience TEXT,
                    constraints_json TEXT NOT NULL DEFAULT '[]',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT NOT NULL DEFAULT '',
                    company TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    jd_text TEXT NOT NULL DEFAULT '',
                    skills_json TEXT NOT NULL DEFAULT '[]',
                    source_url TEXT,
                    source_license TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS question_favorites (
                    user_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, question_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    session_id TEXT,
                    title TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_documents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    extracted_text TEXT NOT NULL DEFAULT '',
                    parsed_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'uploaded',
                    provider TEXT,
                    error TEXT,
                    linked_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_feedback_turn ON feedback(turn_id);
                CREATE INDEX IF NOT EXISTS idx_questions_process ON questions(process_type);
                CREATE INDEX IF NOT EXISTS idx_edges_from ON graph_edges(from_type, from_id);
                CREATE INDEX IF NOT EXISTS idx_favorites_user ON question_favorites(user_id);
                CREATE INDEX IF NOT EXISTS idx_candidate_documents_user ON candidate_documents(user_id, updated_at);
                """
            )
            # Databases created by an earlier MVP release already contain the
            # four session tables.  These additive migrations make upgrading
            # them safe and repeatable.
            self._ensure_column(self._conn, "sources", "published_at", "TEXT")
            self._ensure_column(self._conn, "sources", "pii_redacted", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(self._conn, "sources", "content_hash", "TEXT")
            self._ensure_column(self._conn, "questions", "is_active", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(self._conn, "sessions", "user_id", "TEXT")
            self._ensure_column(self._conn, "sessions", "job_id", "TEXT")
            self._ensure_column(self._conn, "users", "display_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(self._conn, "users", "is_temporary", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(self._conn, "users", "last_seen_at", "TEXT")
            self._ensure_column(self._conn, "user_profiles", "skills_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(self._conn, "user_profiles", "projects_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(self._conn, "user_profiles", "education", "TEXT")
            self._ensure_column(self._conn, "user_profiles", "experience", "TEXT")
            self._ensure_column(self._conn, "user_profiles", "constraints_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(self._conn, "user_profiles", "profile_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(self._conn, "jobs", "role", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(self._conn, "jobs", "source_url", "TEXT")
            self._ensure_column(self._conn, "jobs", "source_license", "TEXT")
            self._ensure_column(self._conn, "jobs", "payload_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(self._conn, "reports", "title", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(self._conn, "model_invocations", "input_tokens", "INTEGER")
            self._ensure_column(self._conn, "model_invocations", "output_tokens", "INTEGER")
            self._ensure_column(self._conn, "model_invocations", "cost_usd", "REAL")
            self._ensure_column(self._conn, "model_invocations", "attempt", "INTEGER")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_active ON questions(is_active)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?, ?, ?)",
                (1, "initial interview and knowledge schema", utc_now()),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?, ?, ?)",
                (2, "source provenance fields and soft-delete support", utc_now()),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?, ?, ?)",
                (3, "temporary users, profiles, jobs, favorites and reports", utc_now()),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?, ?, ?)",
                (4, "model invocation token, cost and retry telemetry", utc_now()),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?, ?, ?)",
                (5, "candidate resume and job-description documents", utc_now()),
            )

    def seed_questions(self, items: list[dict[str, Any]], *, prune: bool = False) -> int:
        """幂等写入题目、技能、来源和图边；返回本次处理题目数。

        ``prune=False``（默认）只同步当前数据，保留管理员手工录入的题目。
        管理员明确要求完整重载时传 ``prune=True``，数据集中不存在的题目会被
        软删除，历史会话仍然可以引用它们。
        """
        if not isinstance(items, list):
            raise TypeError("items must be a list")
        count = 0
        incoming_ids: set[str] = set()
        with self._lock, self._conn:
            for item in items:
                if not isinstance(item, dict):
                    continue
                question_id = str(item.get("id") or stable_id("Q", str(item.get("question", "")), 8))
                incoming_ids.add(question_id)
                source = item.get("source") or {}
                source_type = str(source.get("type") or source.get("source_type") or "synthetic_mock")
                if source_type == "synthetic":
                    source_type = "synthetic_mock"
                source_id = str(source.get("source_id") or source.get("id") or source.get("url") or source_type)
                now = utc_now()
                self._conn.execute(
                    """
                    INSERT INTO sources
                    (source_id, title, url, license, source_type, version, published_at, accessed_at,
                     redistribution_allowed, pii_redacted, content_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        title=excluded.title, url=excluded.url, license=excluded.license,
                        source_type=excluded.source_type, version=excluded.version,
                        published_at=excluded.published_at, accessed_at=excluded.accessed_at,
                        redistribution_allowed=excluded.redistribution_allowed,
                        pii_redacted=excluded.pii_redacted, content_hash=excluded.content_hash,
                        updated_at=excluded.updated_at
                    """,
                    (
                        source_id, str(source.get("title", "")), source.get("url"), source.get("license"),
                        source_type, source.get("version"), source.get("published_at"),
                        source.get("accessed_at") or source.get("collected_at"),
                        bool(source.get("redistribution_allowed", source_type == "synthetic_mock")),
                        bool(source.get("pii_redacted", True)), source.get("content_hash"), now, now,
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO questions
                    (id, process_type, role, difficulty, question, follow_ups_json, rubric_json, function_name,
                     tests_json, source_id, source_confidence, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        process_type=excluded.process_type, role=excluded.role, difficulty=excluded.difficulty,
                        question=excluded.question, follow_ups_json=excluded.follow_ups_json, rubric_json=excluded.rubric_json,
                        function_name=excluded.function_name, tests_json=excluded.tests_json, source_id=excluded.source_id,
                        source_confidence=excluded.source_confidence, is_active=1, updated_at=excluded.updated_at
                    """,
                    (
                        question_id, str(item.get("process_type", "技术面")), str(item.get("role", "通用岗位")),
                        str(item.get("difficulty", "中")), str(item.get("question", "")),
                        json.dumps(item.get("follow_ups", []), ensure_ascii=False),
                        json.dumps(item.get("rubric", []), ensure_ascii=False), item.get("function_name"),
                        json.dumps(item.get("tests", []), ensure_ascii=False), source_id,
                        str(item.get("source_confidence") or ("synthetic_mock" if source_type == "synthetic_mock" else "observed")),
                        True, now, now,
                    ),
                )
                self._conn.execute("DELETE FROM question_skills WHERE question_id = ?", (question_id,))
                self._conn.execute(
                    "DELETE FROM graph_edges WHERE from_type = 'Question' AND from_id = ? AND relation = 'tests'",
                    (question_id,),
                )
                for name in item.get("skills", []):
                    name = str(name).strip()
                    if not name:
                        continue
                    skill_id = stable_id("skill", name.lower(), 10)
                    self._conn.execute(
                        "INSERT OR IGNORE INTO skills (skill_id, name, aliases_json, created_at) VALUES (?, ?, '[]', ?)",
                        (skill_id, name, now),
                    )
                    self._conn.execute(
                        "INSERT OR IGNORE INTO question_skills (question_id, skill_id) VALUES (?, ?)",
                        (question_id, skill_id),
                    )
                    edge_id = stable_id("edge", f"{question_id}:{skill_id}", 12)
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO graph_edges
                        (edge_id, from_type, from_id, relation, to_type, to_id, source_id)
                        VALUES (?, 'Question', ?, 'tests', 'Skill', ?, ?)
                        """,
                        (edge_id, question_id, skill_id, source_id),
                    )
                count += 1
            if prune:
                # Soft delete keeps historical turns and their feedback valid.
                if incoming_ids:
                    placeholders = ",".join("?" for _ in incoming_ids)
                    self._conn.execute(
                        f"UPDATE questions SET is_active = 0, updated_at = ? WHERE id NOT IN ({placeholders})",
                        (utc_now(), *incoming_ids),
                    )
                else:
                    self._conn.execute("UPDATE questions SET is_active = 0, updated_at = ?", (utc_now(),))
        return count

    def _question_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["id"] = item.pop("id")
        item["follow_ups"] = decode_json(item.pop("follow_ups_json"), [])
        item["rubric"] = decode_json(item.pop("rubric_json"), [])
        item["tests"] = decode_json(item.pop("tests_json"), [])
        item["is_active"] = bool(item.get("is_active", 1))
        skills = self._conn.execute(
            "SELECT s.name FROM skills s JOIN question_skills qs ON s.skill_id = qs.skill_id "
            "WHERE qs.question_id = ? ORDER BY s.name",
            (item["id"],),
        ).fetchall()
        item["skills"] = [x[0] for x in skills]
        source = self._conn.execute("SELECT * FROM sources WHERE source_id = ?", (item["source_id"],)).fetchone()
        if source:
            source_payload = dict(source)
            # Keep the persisted ``source_type`` name for DB consumers and
            # expose ``type`` for the public JSON contract used by GraphRAG.
            source_payload["type"] = source_payload.get("source_type")
            source_payload["redistribution_allowed"] = bool(source_payload.get("redistribution_allowed"))
            source_payload["pii_redacted"] = bool(source_payload.get("pii_redacted"))
            item["source"] = source_payload
        else:
            item["source"] = {"source_id": item["source_id"], "type": item["source_confidence"]}
        return item

    def get_question(self, question_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
        with self._lock:
            query = "SELECT * FROM questions WHERE id = ?"
            params: tuple[Any, ...] = (question_id,)
            if not include_inactive:
                query += " AND is_active = 1"
            row = self._conn.execute(query, params).fetchone()
            return self._question_from_row(row) if row else None

    def list_questions(
        self,
        process_type: str | None = None,
        limit: int = 100,
        *,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        with self._lock:
            clauses = []
            params: list[Any] = []
            if process_type:
                clauses.append("process_type = ?")
                params.append(process_type)
            if not include_inactive:
                clauses.append("is_active = 1")
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(max(1, min(int(limit), 500)))
            rows = self._conn.execute(
                f"SELECT * FROM questions{where} ORDER BY updated_at DESC, id ASC LIMIT ?", params
            ).fetchall()
            return [self._question_from_row(row) for row in rows]

    def list_sources(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sources ORDER BY updated_at DESC, source_id ASC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["type"] = item.get("source_type")
                item["redistribution_allowed"] = bool(item.get("redistribution_allowed"))
                item["pii_redacted"] = bool(item.get("pii_redacted"))
                result.append(item)
            return result

    def delete_question(self, question_id: str) -> bool:
        """Soft-delete a question while retaining historical interview turns."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE questions SET is_active = 0, updated_at = ? WHERE id = ? AND is_active = 1",
                (utc_now(), question_id),
            )
            return cursor.rowcount > 0

    def update_question(self, question_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Merge and persist a knowledge item, returning its canonical form."""
        current = self.get_question(question_id, include_inactive=True)
        if current is None:
            return None
        merged = {
            key: current.get(key)
            for key in (
                "id", "process_type", "role", "skills", "difficulty", "question", "follow_ups",
                "rubric", "function_name", "tests", "source", "source_confidence",
            )
        }
        merged.update({key: value for key, value in changes.items() if value is not None})
        merged["id"] = question_id
        self.seed_questions([merged])
        if changes.get("is_active") is False:
            with self._lock, self._conn:
                self._conn.execute(
                    "UPDATE questions SET is_active = 0, updated_at = ? WHERE id = ?",
                    (utc_now(), question_id),
                )
        return self.get_question(question_id, include_inactive=True)

    def knowledge_stats(self) -> dict[str, int]:
        with self._lock:
            result = {
                "questions": int(self._conn.execute("SELECT COUNT(*) FROM questions WHERE is_active = 1").fetchone()[0]),
                "questions_total": int(self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]),
                "questions_inactive": int(self._conn.execute("SELECT COUNT(*) FROM questions WHERE is_active = 0").fetchone()[0]),
                "skills": int(self._conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]),
                "sources": int(self._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]),
                "graph_edges": int(self._conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]),
            }
            result["sources_with_license"] = int(
                self._conn.execute("SELECT COUNT(*) FROM sources WHERE license IS NOT NULL AND trim(license) <> ''").fetchone()[0]
            )
            return result

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> bool:
        """Check the configured database without exposing connection details."""
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def save_session(self, payload: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO sessions
                (id, user_id, job_id, mode, role, job_text, profile_json, status, current_question_json,
                 matched_skills_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=COALESCE(excluded.user_id, sessions.user_id),
                    job_id=COALESCE(excluded.job_id, sessions.job_id),
                    status=excluded.status,
                    current_question_json=excluded.current_question_json,
                    matched_skills_json=excluded.matched_skills_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["session_id"],
                    payload.get("user_id"),
                    payload.get("job_id"),
                    payload["mode"],
                    payload["role"],
                    payload.get("job_text", ""),
                    json.dumps(payload.get("user_profile", {}), ensure_ascii=False),
                    payload.get("status", "questioning"),
                    json.dumps(payload.get("current_question"), ensure_ascii=False),
                    json.dumps(payload.get("matched_skills", []), ensure_ascii=False),
                    payload.get("created_at", now),
                    now,
                ),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["session_id"] = result.pop("id")
            result["user_profile"] = decode_json(result.pop("profile_json"), {})
            result["current_question"] = decode_json(result.pop("current_question_json"), None)
            result["matched_skills"] = decode_json(result.pop("matched_skills_json"), [])
            return result

    # ------------------------------------------------------------------
    # User/profile/job/report persistence
    # ------------------------------------------------------------------
    def save_candidate_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist extracted document text and structured result, never bytes."""
        import uuid

        document_id = str(payload.get("id") or f"doc-{uuid.uuid4().hex}")
        user_id = str(payload["user_id"])
        if not self.get_user(user_id):
            self.create_temp_user(user_id)
        now = utc_now()
        parsed = payload.get("parsed_json", payload.get("parsed", {}))
        if not isinstance(parsed, dict):
            parsed = {}
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO candidate_documents
                (id, user_id, kind, filename, content_type, extracted_text, parsed_json,
                 status, provider, error, linked_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id, kind=excluded.kind, filename=excluded.filename,
                    content_type=excluded.content_type, extracted_text=excluded.extracted_text,
                    parsed_json=excluded.parsed_json, status=excluded.status, provider=excluded.provider,
                    error=excluded.error, linked_id=excluded.linked_id, updated_at=excluded.updated_at
                """,
                (
                    document_id, user_id, str(payload.get("kind") or "resume"),
                    str(payload.get("filename") or "document"),
                    str(payload.get("content_type") or "application/octet-stream"),
                    str(payload.get("extracted_text") or ""),
                    json.dumps(parsed, ensure_ascii=False),
                    str(payload.get("status") or "uploaded"), payload.get("provider"),
                    payload.get("error"), payload.get("linked_id"),
                    payload.get("created_at") or now, now,
                ),
            )
        return self.get_candidate_document(document_id) or {"id": document_id, **payload}

    def get_candidate_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM candidate_documents WHERE id = ?", (document_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["parsed"] = decode_json(item.pop("parsed_json"), {})
            return item

    def list_candidate_documents(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM candidate_documents WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, max(1, min(int(limit), 500))),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["parsed"] = decode_json(item.pop("parsed_json"), {})
                result.append(item)
            return result

    def delete_candidate_document(self, document_id: str, user_id: str) -> bool:
        with self._lock, self._conn:
            result = self._conn.execute(
                "DELETE FROM candidate_documents WHERE id = ? AND user_id = ?", (document_id, user_id)
            )
            return result.rowcount > 0

    # Short aliases keep integrations that refer to generic "documents" APIs
    # compatible with the explicit candidate-document storage methods.
    save_document = save_candidate_document
    get_document = get_candidate_document
    list_documents = list_candidate_documents
    delete_document = delete_candidate_document

    def create_temp_user(
        self,
        user_id: str | None = None,
        display_name: str = "临时用户",
        *,
        is_temporary: bool = True,
    ) -> dict[str, Any]:
        """Create (or touch) an anonymous user suitable for MVP login.

        A caller may pass a stable ``user_id`` from a cookie/local storage;
        otherwise a random ``usr-…`` id is generated.  The operation is
        idempotent and never stores authentication secrets.
        """
        import uuid

        uid = str(user_id or f"usr-{uuid.uuid4().hex}")
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO users(id, display_name, is_temporary, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name=CASE WHEN excluded.display_name <> '' THEN excluded.display_name ELSE users.display_name END,
                    is_temporary=excluded.is_temporary,
                    last_seen_at=excluded.last_seen_at
                """,
                (uid, display_name or "", bool(is_temporary), now, now),
            )
            row = self._conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            return dict(row) if row else {"id": uid, "display_name": display_name, "is_temporary": is_temporary}

    # Alias used by API handlers that prefer an explicit name.
    get_or_create_temp_user = create_temp_user

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["is_temporary"] = bool(item.get("is_temporary"))
            return item

    def save_user_profile(self, user_id: str, profile: dict[str, Any] | None) -> dict[str, Any]:
        """Upsert a user's skills, projects and free-form profile fields."""
        profile = dict(profile or {})
        # Ensure a user row exists for temporary-user flows.
        if not self.get_user(user_id):
            self.create_temp_user(user_id)
        skills = [str(x).strip() for x in profile.get("skills", []) if str(x).strip()]
        projects = [str(x).strip() for x in profile.get("projects", []) if str(x).strip()]
        constraints = [str(x).strip() for x in profile.get("constraints", []) if str(x).strip()]
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO user_profiles
                (user_id, skills_json, projects_json, education, experience, constraints_json, profile_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    skills_json=excluded.skills_json, projects_json=excluded.projects_json,
                    education=excluded.education, experience=excluded.experience,
                    constraints_json=excluded.constraints_json, profile_json=excluded.profile_json,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    json.dumps(skills, ensure_ascii=False),
                    json.dumps(projects, ensure_ascii=False),
                    profile.get("education"), profile.get("experience"),
                    json.dumps(constraints, ensure_ascii=False),
                    json.dumps(profile, ensure_ascii=False), now,
                ),
            )
        return self.get_user_profile(user_id) or {"user_id": user_id, **profile}

    # More concise alias for route implementations.
    upsert_user_profile = save_user_profile

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["skills"] = decode_json(item.pop("skills_json"), [])
            item["projects"] = decode_json(item.pop("projects_json"), [])
            item["constraints"] = decode_json(item.pop("constraints_json"), [])
            raw = decode_json(item.pop("profile_json"), {})
            # Preserve custom profile keys while canonical columns win.
            raw.update({k: item[k] for k in ("skills", "projects", "education", "experience", "constraints")})
            raw["user_id"] = user_id
            raw["updated_at"] = item.get("updated_at")
            return raw

    def save_job(self, user_id: str | None, job: dict[str, Any]) -> dict[str, Any]:
        """Persist a user's target role/JD and normalized skills."""
        payload = dict(job or {})
        if payload.get("id") or payload.get("job_id"):
            job_id = str(payload.get("id") or payload.get("job_id"))
        else:
            # Re-saving the same target JD is idempotent; distinct JDs still
            # receive separate records for the user's comparison history.
            fingerprint = "|".join([
                str(user_id or ""), str(payload.get("title") or payload.get("name") or ""),
                str(payload.get("role") or ""), str(payload.get("jd_text") or payload.get("job_text") or ""),
            ])
            job_id = f"job-{hashlib.sha1(fingerprint.encode('utf-8')).hexdigest()[:16]}"
        if user_id and not self.get_user(user_id):
            self.create_temp_user(user_id)
        now = utc_now()
        skills = [str(x).strip() for x in payload.get("skills", []) if str(x).strip()]
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs
                (id, user_id, title, company, role, jd_text, skills_json, source_url, source_license,
                 payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=COALESCE(excluded.user_id, jobs.user_id), title=excluded.title,
                    company=excluded.company, role=excluded.role, jd_text=excluded.jd_text,
                    skills_json=excluded.skills_json, source_url=excluded.source_url,
                    source_license=excluded.source_license, payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    job_id, user_id, str(payload.get("title") or payload.get("name") or ""),
                    str(payload.get("company") or ""), str(payload.get("role") or ""),
                    str(payload.get("jd_text") or payload.get("job_text") or payload.get("description") or ""),
                    json.dumps(skills, ensure_ascii=False), payload.get("source_url") or payload.get("url"),
                    payload.get("source_license") or payload.get("license"),
                    json.dumps(payload, ensure_ascii=False), now, now,
                ),
            )
        return self.get_job(job_id) or {"id": job_id, "user_id": user_id, **payload}

    upsert_job = save_job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["skills"] = decode_json(item.pop("skills_json"), [])
            payload = decode_json(item.pop("payload_json"), {})
            payload.update(item)
            payload["job_id"] = payload.get("id")
            return payload

    def list_jobs(self, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            params: list[Any] = []
            where = ""
            if user_id:
                where = " WHERE user_id = ?"
                params.append(user_id)
            params.append(max(1, min(int(limit), 500)))
            rows = self._conn.execute(
                f"SELECT * FROM jobs{where} ORDER BY updated_at DESC LIMIT ?", params
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["skills"] = decode_json(item.pop("skills_json"), [])
                payload = decode_json(item.pop("payload_json"), {})
                payload.update(item)
                payload["job_id"] = payload.get("id")
                result.append(payload)
            return result

    def favorite_question(self, user_id: str, question_id: str) -> bool:
        if not self.get_user(user_id):
            self.create_temp_user(user_id)
        with self._lock, self._conn:
            # Invalid question IDs are reported as False rather than leaking
            # an integrity error to API clients.
            if not self._conn.execute("SELECT 1 FROM questions WHERE id = ?", (question_id,)).fetchone():
                return False
            self._conn.execute(
                "INSERT OR IGNORE INTO question_favorites(user_id, question_id, created_at) VALUES (?, ?, ?)",
                (user_id, question_id, utc_now()),
            )
            return True

    add_favorite = favorite_question

    def unfavorite_question(self, user_id: str, question_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM question_favorites WHERE user_id = ? AND question_id = ?", (user_id, question_id)
            )
            return cur.rowcount > 0

    remove_favorite = unfavorite_question

    def list_favorite_questions(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT q.* FROM questions q JOIN question_favorites f ON q.id = f.question_id
                WHERE f.user_id = ? ORDER BY f.created_at DESC LIMIT ?
                """,
                (user_id, max(1, min(int(limit), 500))),
            ).fetchall()
            return [self._question_from_row(row) for row in rows]

    list_favorites = list_favorite_questions

    def save_report(
        self,
        user_id: str | None,
        session_id: str | None,
        report: dict[str, Any],
        report_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a generated training report; repeated writes are idempotent."""
        import uuid

        rid = str(report_id or report.get("id") or f"report-{uuid.uuid4().hex}")
        now = utc_now()
        if user_id and not self.get_user(user_id):
            self.create_temp_user(user_id)
        payload = dict(report or {})
        title = str(payload.get("title") or payload.get("name") or "训练报告")
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO reports(id, user_id, session_id, title, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=COALESCE(excluded.user_id, reports.user_id), session_id=COALESCE(excluded.session_id, reports.session_id),
                    title=excluded.title, payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (rid, user_id, session_id, title, json.dumps(payload, ensure_ascii=False), now, now),
            )
        return self.get_report(rid) or {"id": rid, "user_id": user_id, "session_id": session_id, **payload}

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            payload = decode_json(item.pop("payload_json"), {})
            payload.update(item)
            payload["report_id"] = payload.get("id")
            return payload

    def list_reports(self, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            params: list[Any] = []
            where = ""
            if user_id:
                where = " WHERE user_id = ?"
                params.append(user_id)
            params.append(max(1, min(int(limit), 500)))
            rows = self._conn.execute(
                f"SELECT * FROM reports{where} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                payload = decode_json(item.pop("payload_json"), {})
                payload.update(item)
                payload["report_id"] = payload.get("id")
                result.append(payload)
            return result

    def list_training_history(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return session history with turn counts and average score."""
        sessions = []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, max(1, min(int(limit), 500))),
            ).fetchall()
            for row in rows:
                item = dict(row)
                sid = item["id"]
                score_rows = self._conn.execute(
                    """
                    SELECT f.payload_json FROM feedback f JOIN turns t ON f.turn_id = t.id
                    WHERE t.session_id = ?
                    """, (sid,)
                ).fetchall()
                values: list[float] = []
                for score_row in score_rows:
                    try:
                        scores = decode_json(score_row[0], {}).get("scores", {})
                        values.extend(float(v) for v in scores.values() if isinstance(v, (int, float)))
                    except (TypeError, ValueError, AttributeError):
                        continue
                item["session_id"] = item.pop("id")
                item["turn_count"] = int(self._conn.execute("SELECT COUNT(*) FROM turns WHERE session_id = ?", (sid,)).fetchone()[0])
                item["average_score"] = round(sum(values) / len(values), 2) if values else None
                item["user_profile"] = decode_json(item.pop("profile_json"), {})
                item["current_question"] = decode_json(item.pop("current_question_json"), None)
                item["matched_skills"] = decode_json(item.pop("matched_skills_json"), [])
                sessions.append(item)
        return sessions

    # Alias used by report/history API handlers.
    list_history = list_training_history

    def save_turn(self, payload: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO turns
                (id, session_id, question_id, answer_text, code, language, algorithm_result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id=excluded.session_id, question_id=excluded.question_id,
                    answer_text=excluded.answer_text, code=excluded.code, language=excluded.language,
                    algorithm_result_json=excluded.algorithm_result_json, created_at=excluded.created_at
                """,
                (
                    payload["turn_id"],
                    payload["session_id"],
                    payload["question_id"],
                    payload.get("answer_text", ""),
                    payload.get("code"),
                    payload.get("language"),
                    json.dumps(payload.get("algorithm_result"), ensure_ascii=False),
                    payload.get("created_at", utc_now()),
                ),
            )

    def save_feedback(self, turn_id: str, payload: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO feedback (id, turn_id, payload_json, created_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET turn_id=excluded.turn_id,
                    payload_json=excluded.payload_json, created_at=excluded.created_at
                """,
                (f"fb-{turn_id}", turn_id, json.dumps(payload, ensure_ascii=False), utc_now()),
            )

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY created_at ASC", (session_id,)
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["algorithm_result"] = decode_json(item.pop("algorithm_result_json"), None)
                fb = self._conn.execute("SELECT payload_json FROM feedback WHERE turn_id = ?", (item["id"],)).fetchone()
                item["feedback"] = decode_json(fb[0], {}) if fb else None
                result.append(item)
            return result

    def get_turn_by_question(self, session_id: str, question_id: str) -> dict[str, Any] | None:
        """Return the most recent persisted turn for a session/question pair.

        The browser may retry a POST after a timeout even though the first
        request has already committed.  Looking up the existing turn lets the
        API return the original result idempotently instead of reporting that
        the question is no longer current.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM turns WHERE session_id = ? AND question_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (session_id, question_id),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["algorithm_result"] = decode_json(item.pop("algorithm_result_json"), None)
            feedback = self._conn.execute(
                "SELECT payload_json FROM feedback WHERE turn_id = ?", (item["id"],)
            ).fetchone()
            item["feedback"] = decode_json(feedback[0], {}) if feedback else None
            return item

    def save_model_invocation(self, payload: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO model_invocations
                (id, session_id, task, provider, model, latency_ms, status, fallback_reason,
                 input_tokens, output_tokens, cost_usd, attempt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload.get("session_id"), payload["task"], payload["provider"],
                    payload["model"], payload.get("latency_ms"), payload["status"],
                    payload.get("fallback_reason"), payload.get("input_tokens"),
                    payload.get("output_tokens"), payload.get("cost_usd"),
                    payload.get("attempt"), utc_now(),
                ),
            )
