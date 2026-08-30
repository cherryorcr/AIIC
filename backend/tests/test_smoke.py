"""不依赖外部模型的轻量 smoke tests。

运行前安装 requirements-dev，并从项目根目录执行 pytest backend/tests。
"""

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("STRONG_MODEL_API_KEY", "")
os.environ.setdefault("LOCAL_MODEL_BASE_URL", "")
# Never reuse a checked-in/on-disk test database.  A fresh path prevents old
# schemas and admin data from changing the result of a test run.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp(prefix="ai-interview-tests-")) / "test.db")

from fastapi.testclient import TestClient

from app.main import app
from app.services.rag import GraphRAGService
from app.services.sandbox import SandboxService
from app.config import Settings
from app.services.model_router import ModelRouter
from app.storage.db import Database


@pytest.fixture(autouse=True)
def reset_database():
    """Keep each smoke test independent while reusing the app import."""
    from app.main import db, rag

    db.init()
    with db._lock, db._conn:  # noqa: SLF001 - explicit test-only isolation
        for table in (
            "feedback", "turns", "reports", "question_favorites", "sessions", "auth_sessions",
            "model_invocations", "user_profiles", "jobs", "users", "graph_edges",
            "question_skills", "questions", "skills", "sources",
            "candidate_documents",
        ):
            db._conn.execute(f"DELETE FROM {table}")
    db.seed_questions(rag._load())
    rag.reload()
    yield


def test_start_and_answer():
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/sessions",
            json={
                "mode": "technical",
                "role": "后端开发工程师",
                "job_text": "Python FastAPI Redis",
                "user_profile": {"skills": ["Python"], "projects": ["TechMatch"]},
            },
        )
        assert started.status_code == 200
        payload = started.json()
        answered = client.post(
            f"/api/v1/sessions/{payload['session_id']}/turns",
            json={"question_id": payload["question_id"], "answer_text": "我在 TechMatch 项目中使用 Python，结果延迟下降 20%。"},
        )
        assert answered.status_code == 200
        assert answered.json()["feedback"]["evidence_quotes"]


def test_answer_retry_is_idempotent_after_question_advances():
    """A replayed POST returns the committed turn instead of a 400 race."""
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/sessions",
            json={
                "mode": "behavioral",
                "role": "后端开发工程师",
                "user_profile": {"skills": ["Python"], "projects": ["TechMatch"]},
            },
        )
        assert started.status_code == 200
        payload = started.json()
        body = {
            "question_id": payload["question_id"],
            "answer_text": "我在项目中优化了接口性能，并用压测验证延迟下降 20%。",
        }
        first = client.post(f"/api/v1/sessions/{payload['session_id']}/turns", json=body)
        replay = client.post(f"/api/v1/sessions/{payload['session_id']}/turns", json=body)
        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["turn_id"] == first.json()["turn_id"]
        assert replay.json()["feedback"] == first.json()["feedback"]


def test_match_preview_does_not_create_training_session():
    from app.main import db

    with TestClient(app) as client:
        before = db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        response = client.post(
            "/api/v1/matches",
            json={
                "mode": "technical",
                "role": "后端开发工程师",
                "job_text": "Python FastAPI PostgreSQL",
                "user_profile": {"skills": ["Python"], "projects": ["TechMatch"]},
            },
        )
        assert response.status_code == 200
        assert response.json()["questions"]
        after = db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert after == before


def test_algorithm_runner_rejects_forbidden_code():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "algorithm", "role": "算法工程师"})
        sid = started.json()["session_id"]
        result = client.post(
            f"/api/v1/sessions/{sid}/algorithm/run",
            json={"question_id": started.json()["question_id"], "code": "import os\n\ndef solution(x): return x"},
        )
        assert result.status_code == 200
        assert result.json()["status"] == "rejected"


def test_algorithm_runner_rejects_reflective_sandbox_escape():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "algorithm", "role": "算法工程师"})
        sid = started.json()["session_id"]
        result = client.post(
            f"/api/v1/sessions/{sid}/algorithm/run",
            json={
                "question_id": started.json()["question_id"],
                "code": "def solution(x):\n    return getattr(x, '__class__')",
            },
        )
        assert result.status_code == 200
        assert result.json()["status"] == "rejected"


def test_algorithm_question_and_knowledge_management():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "algorithm", "role": "算法工程师"})
        assert started.status_code == 200
        payload = started.json()
        assert payload["question_id"].startswith("PUB-ALG-")
        assert isinstance(payload["tests"], list)

        stats = client.get("/api/v1/admin/knowledge/stats")
        assert stats.status_code == 200
        assert stats.json()["questions"] >= 17
        listing = client.get("/api/v1/admin/knowledge/items", params={"process_type": "算法面"})
        assert listing.status_code == 200
        assert any(item["id"].startswith("PUB-ALG-") for item in listing.json()["items"])

        # The public frontend sends the stable mode ID; the database stores
        # the Chinese process label. Both forms must resolve to the same data.
        public_listing = client.get("/api/v1/questions", params={"process_type": "algorithm"})
        assert public_listing.status_code == 200
        assert public_listing.json()["items"]
        assert all(item["id"].startswith("PUB-ALG-") for item in public_listing.json()["items"])

        created = client.post(
            "/api/v1/admin/knowledge/items",
            json={
                "id": "Q-TEST-001",
                "process_type": "技术面",
                "role": "后端开发",
                "question": "如何设计一个可观测的 API？",
                "skills": ["系统设计"],
                "source": {"type": "synthetic_mock", "title": "测试题"},
            },
        )
        assert created.status_code == 200
        assert created.json()["item"]["id"] == "Q-TEST-001"


def test_sandbox_timeout_is_reported():
    sandbox = SandboxService(Settings(sandbox_timeout_seconds=0.1))
    result = sandbox.run("def solution(x):\n    while True: pass\n", [{"args": [1], "expected": 1}])
    assert result["status"] == "timeout"


def test_knowledge_update_source_and_soft_delete():
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/knowledge/items",
            json={
                "id": "Q-MANAGED-001",
                "process_type": "技术面",
                "role": "后端开发",
                "question": "请说明一次可观测性建设经历。",
                "skills": ["系统设计"],
                "source": {
                    "type": "online",
                    "source_id": "public-guide-v1",
                    "title": "公开面试准备指南",
                    "url": "https://example.com/guide",
                    "license": "CC BY 4.0",
                    "published_at": "2026-01-01",
                    "accessed_at": "2026-08-30",
                    "pii_redacted": True,
                },
            },
        )
        assert created.status_code == 200
        assert created.json()["item"]["source"]["type"] == "online"

        updated = client.patch(
            "/api/v1/admin/knowledge/items/Q-MANAGED-001",
            json={"difficulty": "高", "rubric": ["说明指标", "给出结果证据"]},
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["difficulty"] == "高"

        sources = client.get("/api/v1/admin/knowledge/sources")
        assert sources.status_code == 200
        assert any(source["source_id"] == "public-guide-v1" for source in sources.json()["sources"])

        deleted = client.delete("/api/v1/admin/knowledge/items/Q-MANAGED-001")
        assert deleted.status_code == 200
        active = client.get("/api/v1/admin/knowledge/items").json()["items"]
        inactive = client.get("/api/v1/admin/knowledge/items", params={"include_inactive": "true"}).json()["items"]
        assert all(item["id"] != "Q-MANAGED-001" for item in active)
        assert any(item["id"] == "Q-MANAGED-001" and item["is_active"] is False for item in inactive)


def test_user_profile_job_favorite_history_and_report_persist():
    with TestClient(app) as client:
        user = client.post("/api/v1/users/temporary", json={"display_name": "测试用户"})
        assert user.status_code == 200
        profile = client.put(
            "/api/v1/profile",
            json={"skills": ["Python"], "projects": ["TechMatch"], "experience": "后端"},
        )
        assert profile.status_code == 200
        job = client.post(
            "/api/v1/jobs",
            json={"title": "后端工程师", "jd_text": "Python FastAPI PostgreSQL"},
        )
        assert job.status_code == 200
        assert "python" in [x.lower() for x in job.json()["job"]["skills"]]
        favorite = client.post("/api/v1/questions/PUB-BEH-AMAZON-001/favorite", json={"favorite": True})
        assert favorite.status_code == 200
        assert any(item["id"] == "PUB-BEH-AMAZON-001" for item in client.get("/api/v1/favorites").json()["items"])
        report = client.post("/api/v1/reports", json={"title": "回归报告", "payload": {"score": 4}})
        assert report.status_code == 200
        assert any(item["title"] == "回归报告" for item in client.get("/api/v1/reports").json()["reports"])


def test_registered_accounts_keep_profiles_jobs_readiness_and_sessions_isolated():
    with TestClient(app) as owner, TestClient(app) as other:
        guest = owner.get("/api/v1/auth/me")
        assert guest.status_code == 200
        guest_id = guest.json()["user"]["id"]
        assert guest.json()["authenticated"] is False

        assert owner.put(
            "/api/v1/profile",
            json={
                "full_name": "张三",
                "headline": "后端开发工程师",
                "skills": ["Python", "FastAPI"],
                "projects": ["TechMatch"],
                "experience": "两年后端开发",
            },
        ).status_code == 200
        owner_job = owner.post(
            "/api/v1/jobs",
            json={"title": "后端开发工程师", "role": "后端开发工程师", "jd_text": "Python FastAPI PostgreSQL"},
        ).json()["job"]
        registered = owner.post(
            "/api/v1/auth/register",
            json={"display_name": "张三", "email": "owner@example.com", "password": "safe-pass-123"},
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["id"] == guest_id
        assert registered.json()["user"]["is_temporary"] is False
        assert "password_hash" not in registered.text

        started = owner.post(
            "/api/v1/sessions",
            json={"mode": "technical", "role": "后端开发工程师", "job_id": owner_job["id"]},
        )
        assert started.status_code == 200
        session_id = started.json()["session_id"]
        question_id = started.json()["question_id"]
        owner_report = owner.post(
            "/api/v1/reports",
            json={"session_id": session_id, "title": "账户一报告", "payload": {"score": 4}},
        ).json()["report"]

        other_registered = other.post(
            "/api/v1/auth/register",
            json={"display_name": "李四", "email": "other@example.com", "password": "other-pass-123"},
        )
        assert other_registered.status_code == 201
        assert other.put(
            "/api/v1/profile", json={"full_name": "李四", "skills": ["Java"], "projects": []}
        ).status_code == 200

        assert other.get(f"/api/v1/jobs/{owner_job['id']}").status_code == 404
        assert other.get(f"/api/v1/sessions/{session_id}").status_code == 404
        assert other.get(f"/api/v1/sessions/{session_id}/summary").status_code == 404
        assert other.get(f"/api/v1/sessions/{session_id}/events").status_code == 404
        assert other.post(f"/api/v1/sessions/{session_id}/match", json={"filters": {}}).status_code == 404
        assert other.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"question_id": question_id, "answer_text": "越权回答"},
        ).status_code == 404
        assert other.post(
            f"/api/v1/sessions/{session_id}/algorithm/run",
            json={"question_id": question_id, "code": "def solution(): return 1"},
        ).status_code == 404
        assert other.post(f"/api/v1/sessions/{session_id}/complete").status_code == 404
        assert other.get(f"/api/v1/reports/{owner_report['id']}").status_code == 404
        assert other.post(
            "/api/v1/reports", json={"session_id": session_id, "title": "越权报告"}
        ).status_code == 404
        spoofed = other.get("/api/v1/profile", headers={"X-User-Id": guest_id})
        assert spoofed.status_code == 200
        assert spoofed.json()["profile"]["full_name"] == "李四"

        owner_overview = owner.get("/api/v1/workspace/overview").json()
        other_overview = other.get("/api/v1/workspace/overview").json()
        assert owner_overview["user_id"] != other_overview["user_id"]
        assert owner_overview["counts"]["jobs"] == 1
        assert owner_overview["counts"]["sessions"] == 1
        assert other_overview["counts"]["jobs"] == 0
        assert other_overview["counts"]["sessions"] == 0
        assert "postgresql" in owner_overview["readiness"]["skill_gaps"]

        assert owner.post("/api/v1/auth/logout").status_code == 200
        assert owner.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password"},
        ).status_code == 401
        login = owner.post(
            "/api/v1/auth/login",
            json={"email": "OWNER@example.com", "password": "safe-pass-123"},
        )
        assert login.status_code == 200
        assert owner.get("/api/v1/profile").json()["profile"]["full_name"] == "张三"
        assert owner.get("/api/v1/workspace/overview").json()["counts"]["sessions"] == 1


def test_readiness_starts_at_zero_until_a_target_job_exists():
    with TestClient(app) as client:
        assert client.put(
            "/api/v1/profile",
            json={"skills": ["Python", "FastAPI"], "projects": ["TechMatch"]},
        ).status_code == 200
        overview = client.get("/api/v1/workspace/overview")
        assert overview.status_code == 200
        readiness = overview.json()["readiness"]
        assert readiness["score"] == 0
        assert readiness["skill_coverage"] == 0
        assert readiness["matched_skills"] == []
        assert readiness["skill_gaps"] == []
        assert overview.json()["counts"]["skills"] == 2


def test_model_fallback_is_recorded_with_telemetry():
    path = Path(tempfile.mkdtemp(prefix="router-tests-")) / "router.db"
    database = Database(path)
    database.init()
    try:
        router = ModelRouter(Settings(strong_model_api_key="", local_model_base_url=""), database)
        import asyncio
        result = asyncio.run(router.complete("evaluate", [{"role": "user", "content": "hello"}]))
        assert result["fallback"] is True
        row = database._conn.execute("SELECT provider, status, fallback_reason FROM model_invocations ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row[0] == "fallback"
        assert row[1] == "fallback"
        assert row[2] == "no_model_configured"
    finally:
        database.close()


def test_model_retry_policy_skips_deterministic_failures():
    """Auth/schema failures go straight to the next provider."""
    from app.services.model_router import ModelRouter

    assert not ModelRouter._retryable(401, RuntimeError("unauthorized"))
    assert not ModelRouter._retryable(200, ValueError("invalid schema"))
    assert ModelRouter._retryable(503, RuntimeError("temporarily unavailable"))


def test_rag_extracts_normalized_skills_and_reports_recall():
    from app.services.rag import GraphRAGService, extract_skills
    rag_service = GraphRAGService(Path("data/mock-interview-dataset.json"))
    assert "python" in extract_skills("Python3 Fast API PostgreSQL")
    result = rag_service.evaluate_recall([
        {"mode": "algorithm", "role": "算法工程师", "job_text": "Python 数据结构", "profile": {}, "question_id": "Q009", "k": 5},
    ])
    assert result["cases"] == 1
    assert 0 <= result["recall_at_k"] <= 1


def test_session_can_be_completed_and_reported():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "technical", "role": "后端工程师"})
        assert started.status_code == 200
        sid = started.json()["session_id"]
        completed = client.post(f"/api/v1/sessions/{sid}/complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        summary = client.get(f"/api/v1/sessions/{sid}")
        assert summary.json()["session"]["status"] == "completed"


def test_candidate_document_upload_parse_confirm_and_ownership():
    with TestClient(app) as client, TestClient(app) as other_client:
        created = client.post("/api/v1/users/temporary", json={"display_name": "资料用户"})
        assert created.status_code == 200
        uid = created.json()["user"]["id"]
        upload = client.post(
            "/api/v1/documents/parse",
            files={"file": ("resume.txt", "张三\\nPython FastAPI\\nTechMatch 项目", "text/plain")},
            data={"kind": "resume"},
        )
        assert upload.status_code == 200
        document = upload.json()["document"]
        assert document["status"] == "parsed"
        assert document["extracted_text"].startswith("张三")
        assert "raw" not in document
        did = document["id"]
        listed = client.get("/api/v1/documents")
        assert listed.status_code == 200 and listed.json()["documents"]
        confirmed = client.post(
            f"/api/v1/documents/{did}/confirm",
            json={"parsed": {"profile": {"full_name": "张三", "skills": ["Python"], "projects": ["TechMatch"]}}},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        profile = client.get("/api/v1/profile").json()["profile"]
        assert profile["full_name"] == "张三"
        other = other_client.post("/api/v1/users/temporary", json={"display_name": "其他用户"})
        assert other.status_code == 200
        assert other_client.get(f"/api/v1/documents/{did}").status_code == 404
        # A raw user ID is no longer accepted as proof of identity.
        assert other_client.get(f"/api/v1/documents/{did}", headers={"X-User-Id": uid}).status_code == 404
        assert client.delete(f"/api/v1/documents/{did}").status_code == 200


def test_candidate_document_rejects_unsupported_and_oversized_uploads():
    with TestClient(app) as client:
        headers = {"X-User-Id": "doc-format-user"}
        bad = client.post(
            "/api/v1/documents/parse", headers=headers,
            files={"file": ("resume.exe", b"MZ", "application/octet-stream")}, data={"kind": "resume"},
        )
        assert bad.status_code == 415
        huge = client.post(
            "/api/v1/documents/parse", headers=headers,
            files={"file": ("resume.txt", b"x" * (5 * 1024 * 1024 + 1), "text/plain")}, data={"kind": "resume"},
        )
        assert huge.status_code == 413


def test_postgres_migration_baseline_is_checked_in():
    """The production DATABASE_URL path must have a runnable schema baseline."""
    migration = Path(__file__).resolve().parents[1] / "migrations" / "001_postgres_schema.sql"
    sql = migration.read_text(encoding="utf-8")
    for table in (
        "users", "auth_sessions", "user_profiles", "jobs", "sessions", "sources", "skills",
        "questions", "question_skills", "graph_edges", "turns", "feedback",
        "model_invocations", "question_favorites", "reports", "candidate_documents",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "ON CONFLICT (version) DO NOTHING" in sql
    migration_script = (Path(__file__).resolve().parents[1] / "scripts" / "migrate_postgres.py").read_text(encoding="utf-8")
    assert "boolean_columns" in migration_script
