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
        for table in ("feedback", "turns", "sessions", "graph_edges", "question_skills", "questions", "skills", "sources"):
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


def test_algorithm_question_and_knowledge_management():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "algorithm", "role": "算法工程师"})
        assert started.status_code == 200
        payload = started.json()
        assert payload["question_id"] == "Q009"
        assert len(payload["tests"]) == 4

        stats = client.get("/api/v1/admin/knowledge/stats")
        assert stats.status_code == 200
        assert stats.json()["questions"] >= 9
        listing = client.get("/api/v1/admin/knowledge/items", params={"process_type": "算法面"})
        assert listing.status_code == 200
        assert any(item["id"] == "Q009" for item in listing.json()["items"])

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
        headers = {"X-User-Id": user.json()["user"]["id"]}
        profile = client.put(
            "/api/v1/profile", headers=headers,
            json={"skills": ["Python"], "projects": ["TechMatch"], "experience": "后端"},
        )
        assert profile.status_code == 200
        job = client.post(
            "/api/v1/jobs", headers=headers,
            json={"title": "后端工程师", "jd_text": "Python FastAPI PostgreSQL"},
        )
        assert job.status_code == 200
        assert "python" in [x.lower() for x in job.json()["job"]["skills"]]
        favorite = client.post("/api/v1/questions/Q001/favorite", headers=headers, json={"favorite": True})
        assert favorite.status_code == 200
        assert any(item["id"] == "Q001" for item in client.get("/api/v1/favorites", headers=headers).json()["items"])
        report = client.post("/api/v1/reports", headers=headers, json={"title": "回归报告", "payload": {"score": 4}})
        assert report.status_code == 200
        assert any(item["title"] == "回归报告" for item in client.get("/api/v1/reports", headers=headers).json()["reports"])


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


def test_rag_extracts_normalized_skills_and_reports_recall():
    from app.services.rag import GraphRAGService, extract_skills
    rag_service = GraphRAGService(Path("data/mock-interview-dataset.json"))
    assert "python" in extract_skills("Python3 Fast API PostgreSQL")
    result = rag_service.evaluate_recall([
        {"mode": "algorithm", "role": "算法工程师", "job_text": "Python 数据结构", "profile": {}, "question_id": "Q009", "k": 5},
    ])
    assert result["cases"] == 1
    assert 0 <= result["recall_at_k"] <= 1
