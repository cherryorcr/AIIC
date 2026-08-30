"""不依赖外部模型的轻量 smoke tests。

运行前安装 requirements-dev，并从项目根目录执行 pytest backend/tests。
"""

import os
import tempfile
from datetime import datetime, timezone
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
            "feedback", "turns", "reports", "question_favorites", "sessions", "match_snapshots", "auth_sessions",
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


def test_group_interview_returns_simulated_reaction():
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/sessions",
            json={"mode": "group", "role": "产品经理", "job_text": "沟通协作和指标设计"},
        )
        assert started.status_code == 200
        payload = started.json()
        assert payload["question_id"] == "Q-GROUP-001"
        answered = client.post(
            f"/api/v1/sessions/{payload['session_id']}/turns",
            json={
                "question_id": payload["question_id"],
                "answer_text": "我会先澄清目标和预算，再让每位成员给出指标，最后按影响和成本排序。",
            },
        )
        assert answered.status_code == 200
        feedback = answered.json()["feedback"]
        assert feedback["group_phase"]
        assert feedback["group_reaction"]["speaker"]
        assert 2 <= len(feedback["group_reactions"]) <= 3
        assert set(feedback["scores"]) == {"problem_framing", "collaboration", "consensus", "time_management"}


def test_revision_creates_child_turn_without_advancing_cursor():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "technical", "role": "后端工程师"})
        assert started.status_code == 200
        payload = started.json()
        sid = payload["session_id"]
        first = client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"question_id": payload["question_id"], "answer_text": "我在项目中优化接口，延迟下降 20%，并用压测验证。"},
        )
        assert first.status_code == 200
        before = client.get(f"/api/v1/sessions/{sid}/summary").json()
        revised = client.post(
            f"/api/v1/sessions/{sid}/turns",
            json={
                "question_id": payload["question_id"],
                "answer_text": "补充：我增加了缓存和监控，并在发布后持续复盘。",
                "revision_of": first.json()["turn_id"],
                "answer_mode": "supplement",
            },
        )
        assert revised.status_code == 200
        after = client.get(f"/api/v1/sessions/{sid}/summary").json()
        turns = after["turns"]
        child = next(item for item in turns if item["id"] == revised.json()["turn_id"])
        assert child["parent_turn_id"] == first.json()["turn_id"]
        assert child["answer_mode"] == "supplement"
        assert after["session"]["current_question"] == before["session"]["current_question"]
        assert len(turns) == 2


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


def test_match_score_is_stable_profile_jd_coverage_not_question_count():
    payload = {
        "mode": "technical",
        "role": "后端开发工程师",
        "job_text": "Python FastAPI PostgreSQL Redis",
        "user_profile": {"skills": ["Python", "FastAPI"], "projects": []},
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/matches", json=payload)
        second = client.post("/api/v1/matches", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        first_json = first.json()
        second_json = second.json()
        assert first_json["match_score"] == 50
        assert first_json["match_score"] == second_json["match_score"]
        assert first_json["score_cached"] is False
        assert second_json["score_cached"] is True
        assert first_json["score_snapshot_id"] == second_json["score_snapshot_id"]
        assert first_json["score_source"] == "deterministic"
        assert set(first_json["required_skills"]) == {"python", "fastapi", "postgresql", "redis"}
        assert set(first_json["profile_matched_skills"]) == {"python", "fastapi"}

        # Retrieval size is unrelated to the profile/JD score.
        assert first_json["questions"]
        assert first_json["match_score"] != 50 + len(first_json["matched_skills"]) * 5 + min(len(first_json["questions"]), 5) * 2


def test_model_match_score_is_generated_once_then_loaded_from_snapshot(monkeypatch):
    from app.main import router

    calls = 0

    async def fake_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "text": (
                '{"skill_coverage":80,"experience_relevance":70,'
                '"project_evidence":60,"role_alignment":50,'
                '"strengths":["Python"],"gaps":["PostgreSQL"],'
                '"explanation":"技能与经历相关，但数据库证据不足。"}'
            ),
        }

    monkeypatch.setattr(router, "complete", fake_complete)
    payload = {
        "mode": "technical",
        "role": "后端开发工程师",
        "job_text": "Python FastAPI PostgreSQL",
        "user_profile": {"skills": ["Python", "FastAPI"], "projects": ["API 服务"]},
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/matches", json=payload).json()
        second = client.post("/api/v1/matches", json=payload).json()

    assert calls == 1
    assert first["match_score"] == 72
    assert first["score_source"] == "strong_model"
    assert first["score_cached"] is False
    assert second["score_cached"] is True
    assert second["score_snapshot_id"] == first["score_snapshot_id"]


def test_match_snapshot_is_immutable_after_first_write():
    from app.main import db

    base = {
        "user_id": "snapshot-user",
        "target_key": "job:immutable",
        "input_hash": "same-input",
        "scoring_version": "test-v1",
        "score_source": "strong_model",
    }
    first = db.save_match_snapshot({**base, "match_score": 81, "score_explanation": "first"})
    second = db.save_match_snapshot({**base, "match_score": 29, "score_explanation": "second"})

    assert first["id"] == second["id"]
    assert second["match_score"] == 81
    assert second["score_explanation"] == "first"


def test_match_preview_job_id_uses_owned_saved_jd_and_profile():
    with TestClient(app) as client:
        assert client.put(
            "/api/v1/profile",
            json={"skills": ["Python", "FastAPI"], "projects": []},
        ).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端岗位", "jd_text": "Python FastAPI PostgreSQL Redis"},
        )
        assert saved.status_code == 200
        job_id = saved.json()["job"]["id"]
        response = client.post(
            "/api/v1/matches",
            json={"mode": "technical", "role": "通用软件开发工程师", "job_id": job_id},
        )
        assert response.status_code == 200
        assert response.json()["match_score"] == 50

    with TestClient(app) as other_client:
        denied = other_client.post(
            "/api/v1/matches",
            json={"mode": "technical", "job_id": job_id},
        )
        assert denied.status_code == 404


def test_cleared_confirmed_profile_does_not_fall_back_to_stale_browser_profile():
    with TestClient(app) as client:
        assert client.put("/api/v1/profile", json={"skills": [], "projects": []}).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端岗位", "jd_text": "Python FastAPI"},
        )
        job_id = saved.json()["job"]["id"]
        response = client.post(
            "/api/v1/matches",
            json={
                "mode": "technical",
                "job_id": job_id,
                "user_profile": {"skills": ["Python", "FastAPI"], "projects": ["stale browser data"]},
            },
        )

        assert response.status_code == 200
        assert response.json()["profile_matched_skills"] == []
        assert response.json()["match_score"] == 0


def test_match_snapshot_is_recomputed_after_confirmed_profile_changes():
    with TestClient(app) as client:
        assert client.put("/api/v1/profile", json={"skills": ["Python"], "projects": []}).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端岗位", "jd_text": "Python FastAPI PostgreSQL"},
        )
        job_id = saved.json()["job"]["id"]
        first = client.post("/api/v1/matches", json={"mode": "technical", "job_id": job_id}).json()
        assert first["score_cached"] is False

        # A confirmed resume update changes the canonical profile input hash;
        # the old score must not remain attached to the saved role.
        assert client.put(
            "/api/v1/profile",
            json={"skills": ["Python", "FastAPI", "PostgreSQL"], "projects": ["TechMatch"]},
        ).status_code == 200
        second = client.post("/api/v1/matches", json={"mode": "technical", "job_id": job_id}).json()
        assert second["score_cached"] is False
        assert second["score_snapshot_id"] != first["score_snapshot_id"]
        assert second["profile_matched_skills"] == ["fastapi", "postgresql", "python"]
        assert second["match_score"] >= first["match_score"]


def test_match_snapshot_survives_identical_profile_resave_and_training_start():
    with TestClient(app) as client:
        profile = {
            "headline": "后端开发工程师",
            "skills": ["Python", "FastAPI"],
            "projects": ["TechMatch"],
        }
        assert client.put("/api/v1/profile", json=profile).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端岗位", "jd_text": "Python FastAPI PostgreSQL"},
        )
        job_id = saved.json()["job"]["id"]
        first = client.post("/api/v1/matches", json={"mode": "technical", "job_id": job_id}).json()

        # Both actions update profile storage metadata in the current flow,
        # but neither changes resume/JD evidence and therefore must not create
        # another score or call the model again.
        assert client.put("/api/v1/profile", json=profile).status_code == 200
        started = client.post(
            "/api/v1/sessions",
            json={"mode": "technical", "job_id": job_id, "role": "ignored browser role"},
        )
        assert started.status_code == 200
        second = client.post("/api/v1/matches", json={"mode": "technical", "job_id": job_id}).json()

        assert second["score_cached"] is True
        assert second["score_snapshot_id"] == first["score_snapshot_id"]
        assert second["match_score"] == first["match_score"]


def test_training_start_ignores_postgres_datetime_profile_metadata(monkeypatch):
    from app.main import db

    with TestClient(app) as client:
        assert client.put(
            "/api/v1/profile",
            json={"headline": "后端工程师", "skills": ["Python"], "projects": ["TechMatch"]},
        ).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端岗位", "jd_text": "Python FastAPI"},
        )
        job_id = saved.json()["job"]["id"]
        original_get_profile = db.get_user_profile

        def postgres_style_profile(user_id):
            profile = original_get_profile(user_id)
            if profile is not None:
                profile["updated_at"] = datetime.now(timezone.utc)
            return profile

        monkeypatch.setattr(db, "get_user_profile", postgres_style_profile)
        started = client.post(
            "/api/v1/sessions",
            json={"mode": "technical", "job_id": job_id},
        )

        assert started.status_code == 200
        session = db.get_session(started.json()["session_id"])
        assert session["user_profile"]["headline"] == "后端工程师"
        assert "updated_at" not in session["user_profile"]


def test_match_generates_traceable_personalized_questions_from_retrieved_bank(monkeypatch):
    import json

    from app.main import rag, router

    source = {
        "question_id": "Q-SOURCE-001",
        "question": "请设计一个高并发 API 服务。",
        "skills": ["系统设计", "API 设计"],
        "rubric": ["容量假设明确", "说明一致性取舍"],
        "follow_ups": ["依赖超时如何止损？"],
        "source_refs": ["https://example.test/public-question"],
        "source_confidence": "high",
    }
    prompts = []

    def fake_match(**_kwargs):
        return {"matched_skills": ["系统设计"], "questions": [source]}

    async def fake_complete(_task, messages, **_kwargs):
        prompts.append(messages)
        return {
            "ok": True,
            "provider": "strong",
            "text": json.dumps(
                {
                    "skill_coverage": 80,
                    "experience_relevance": 75,
                    "project_evidence": 70,
                    "role_alignment": 85,
                    "strengths": ["Python"],
                    "gaps": ["分布式系统"],
                    "explanation": "岗位方向与项目经验基本匹配。",
                    "personalized_questions": [
                        {
                            "source_question_id": "Q-SOURCE-001",
                            "question": "你在 TechMatch 的 FastAPI 服务中如何设计高并发 API，并说明数据一致性取舍？",
                            "follow_ups": ["如果 PostgreSQL 延迟升高，你会如何止损？"],
                            "personalization_basis": ["简历项目：TechMatch", "简历技能：FastAPI", "JD：高并发 API"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        }

    monkeypatch.setattr(rag, "match", fake_match)
    monkeypatch.setattr(router, "complete", fake_complete)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/matches",
            json={
                "mode": "technical",
                "role": "后端工程师",
                "job_text": "负责高并发 API，要求 Python FastAPI PostgreSQL",
                "user_profile": {"skills": ["Python", "FastAPI"], "projects": ["TechMatch"]},
            },
        )
    assert response.status_code == 200
    body = response.json()
    question = body["questions"][0]
    assert body["question_generation_source"] == "strong_model"
    assert question["personalized"] is True
    assert question["source_question_id"] == "Q-SOURCE-001"
    assert question["source_refs"] == ["https://example.test/public-question"]
    assert question["rubric"] == source["rubric"]
    assert question["personalization_basis"]
    assert any("TechMatch" in message["content"] for batch in prompts for message in batch)


def test_match_score_accepts_strong_model_chinese_score_wrapper():
    from app.services.matching import build_match_context, match_score_schema, model_match_snapshot
    from app.services.model_router import ModelRouter

    payload = {
        "candidate_name": "张三",
        "role": "后端工程师",
        "scores": {"技能覆盖": 78, "相关经历": 64, "项目证据": 35, "岗位方向一致性": 76},
        "strengths": ["FastAPI"],
        "gaps": ["故障排查"],
        "explanation": "岗位方向与简历基本匹配。",
        "personalized_questions": [],
    }
    ModelRouter.validate_json(payload, match_score_schema())
    context = build_match_context(
        role="后端工程师",
        job_text="Python FastAPI PostgreSQL",
        job_skills=[],
        profile={"skills": ["Python", "FastAPI"], "projects": ["TechMatch"]},
    )
    snapshot = model_match_snapshot(context, payload)
    assert snapshot["score_source"] == "strong_model"
    assert snapshot["score_breakdown"] == {
        "skill_coverage": 78,
        "experience_relevance": 64,
        "project_evidence": 35,
        "role_alignment": 76,
    }

    with pytest.raises(ValueError, match="response_schema_invalid"):
        ModelRouter.validate_json(
            {"strengths": [], "gaps": [], "explanation": "missing all score dimensions"},
            match_score_schema(),
        )


def test_match_score_accepts_observed_strong_model_english_wrapper():
    from app.services.matching import build_match_context, match_score_schema, model_match_snapshot
    from app.services.model_router import ModelRouter

    payload = {
        "scores": {
            "skill_coverage": 40,
            "relevant_experience": 55,
            "project_evidence": 30,
            "role_direction_alignment": 70,
        },
        "strengths": ["Python API"],
        "gaps": ["PostgreSQL"],
        "explanation": "API 经历匹配，但数据库证据不足。",
        "personalized_questions": [],
    }
    ModelRouter.validate_json(payload, match_score_schema())
    context = build_match_context(
        role="后端工程师",
        job_text="Python FastAPI PostgreSQL",
        job_skills=[],
        profile={"skills": ["Python", "FastAPI"], "projects": ["TechMatch"]},
    )

    snapshot = model_match_snapshot(context, payload)
    assert snapshot["score_breakdown"] == {
        "skill_coverage": 40,
        "experience_relevance": 55,
        "project_evidence": 30,
        "role_alignment": 70,
    }
    assert snapshot["match_score"] == 44
    assert snapshot["score_source"] == "strong_model"


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
        assert owner_overview["counts"]["sessions"] == 0
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
        assert owner.get("/api/v1/workspace/overview").json()["counts"]["sessions"] == 0


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


def test_readiness_updates_after_a_training_answer_for_target_job():
    with TestClient(app) as client:
        assert client.put(
            "/api/v1/profile",
            json={
                "full_name": "张三",
                "headline": "后端开发工程师",
                "summary": "负责 API 服务开发",
                "experience": "使用 Python 开发后端服务",
                "skills": ["Python"],
                "projects": ["TechMatch"],
            },
        ).status_code == 200
        saved = client.post(
            "/api/v1/jobs",
            json={"title": "后端开发工程师", "jd_text": "Python FastAPI PostgreSQL"},
        )
        job_id = saved.json()["job"]["id"]
        before = client.get("/api/v1/workspace/overview").json()["readiness"]

        started = client.post(
            "/api/v1/sessions",
            json={
                "mode": "technical",
                "role": "错误的本地岗位名",
                "job_id": job_id,
                "job_text": "错误的本地 JD",
                "user_profile": {"skills": ["过期本地技能"], "projects": []},
            },
        )
        assert started.status_code == 200
        session = started.json()
        answered = client.post(
            f"/api/v1/sessions/{session['session_id']}/turns",
            json={
                "question_id": session["question_id"],
                "answer_text": "我在 TechMatch 中使用 Python 优化接口，延迟下降 20%。",
            },
        )
        assert answered.status_code == 200

        after = client.get("/api/v1/workspace/overview").json()["readiness"]
        assert before["training_score"] == 0
        assert after["training_score"] > 0
        assert after["profile_completeness"] == before["profile_completeness"]
        assert after["score"] > before["score"]


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


def test_rag_semantic_dedupe_collapses_algorithm_paraphrases():
    from app.services.rag import GraphRAGService

    items = [
        {"id": "a", "process_type": "算法面", "question": "Two Sum: return indices whose sum equals target", "skills": []},
        {"id": "b", "process_type": "算法面", "question": "两数之和：给定数组和 target，返回两个下标（solution）", "skills": []},
        {"id": "c", "process_type": "算法面", "question": "请反转一个单链表并分析复杂度", "skills": []},
    ]
    deduped = GraphRAGService._dedupe(items)
    assert [item["id"] for item in deduped] == ["a", "c"]


def test_rag_missing_dataset_keeps_group_simulation():
    rag_service = GraphRAGService(Path(tempfile.mkdtemp()) / "missing.json")
    result = rag_service.match(mode="group", role="产品经理", job_text="", profile={})
    assert result["questions"]
    assert result["questions"][0]["question_id"] == "Q-GROUP-001"


def test_resume_fallback_sections_are_mapped_to_profile_fields():
    from app.services.documents import _fallback_parse

    parsed = _fallback_parse(
        "resume",
        "张三\n求职意向：后端开发工程师\n"
        "教育背景\n清华大学 计算机科学\n"
        "工作经历\n某科技公司 后端工程师 2022-2024\n"
        "项目经历\nTechMatch 面试匹配平台\n"
        "专业技能\nPython FastAPI PostgreSQL\n"
        "获奖成果\n优秀员工奖",
    )
    profile = parsed["profile"]
    assert profile["full_name"] == "张三"
    assert "清华大学" in profile["education"]
    assert "某科技公司" in profile["experience"]
    assert profile["projects"] == ["TechMatch 面试匹配平台"]
    assert "python" in profile["skills"]
    assert profile["achievements"] == ["优秀员工奖"]


def test_model_resume_extraction_is_repaired_into_explicit_fields():
    import asyncio
    import json

    from app.services.documents import parse_document

    text = (
        "个人简介\n张三 | 北京航空航天大学 · 软件工程\n"
        "研究兴趣：大模型应用、RAG\n"
        "教育背景\n北京航空航天大学 · 软件工程 · 本科在读\n"
        "工作/实习经历\n某科技公司 · 后端实习生 · 2025\n"
        "项目经历\nTechMatch 面试匹配平台\n"
        "专业技能\nPython FastAPI PostgreSQL\n"
        "关键成果\n接口延迟下降 20%"
    )

    class MisalignedRouter:
        async def complete(self, *_args, **_kwargs):
            # Simulate the failure seen in production: the model copies the
            # whole PDF into summary/education instead of filling fields.
            payload = {
                "kind": "resume",
                "profile": {
                    "full_name": text,
                    "summary": text,
                    "education": text,
                    "experience": "",
                    "skills": "Python, FastAPI",
                    "projects": "",
                    "achievements": [],
                    "constraints": [],
                },
                "warnings": [],
            }
            return {"ok": True, "text": json.dumps(payload, ensure_ascii=False), "provider": "fake"}

        @staticmethod
        def parse_json(value):
            return json.loads(value)

        @staticmethod
        def repair_json(_value):
            return None

    parsed = asyncio.run(parse_document("resume", text, MisalignedRouter()))
    profile = parsed["parsed"]["profile"]
    assert profile["full_name"] == "张三"
    assert "北京航空航天大学" in profile["education"]
    assert "某科技公司" in profile["experience"]
    assert profile["projects"] == ["TechMatch 面试匹配平台"]
    assert "python" in profile["skills"]
    assert profile["achievements"] == ["接口延迟下降 20%"]
    assert "工作/实习经历" not in profile["education"]


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


def test_unanswered_session_is_hidden_until_first_answer():
    with TestClient(app) as client:
        started = client.post("/api/v1/sessions", json={"mode": "technical", "role": "后端工程师"})
        assert started.status_code == 200
        empty_sid = started.json()["session_id"]
        assert client.post(f"/api/v1/sessions/{empty_sid}/complete").status_code == 200
        assert empty_sid not in {item["session_id"] for item in client.get("/api/v1/history").json()["items"]}
        assert empty_sid not in {item.get("session_id") for item in client.get("/api/v1/reports").json()["reports"]}

        answered = client.post("/api/v1/sessions", json={"mode": "technical", "role": "后端工程师"})
        assert answered.status_code == 200
        answered_payload = answered.json()
        response = client.post(
            f"/api/v1/sessions/{answered_payload['session_id']}/turns",
            json={
                "question_id": answered_payload["question_id"],
                "answer_text": "我在项目中使用 Python 优化接口，延迟下降 20%。",
            },
        )
        assert response.status_code == 200
        assert answered_payload["session_id"] in {
            item["session_id"] for item in client.get("/api/v1/history").json()["items"]
        }
        reports = client.get("/api/v1/reports").json()["reports"]
        report = next(item for item in reports if item.get("session_id") == answered_payload["session_id"])
        detail = client.get(f"/api/v1/reports/{report['id']}")
        assert detail.status_code == 200
        turns = detail.json()["report"]["turns"]
        assert turns and turns[0]["question_text"]


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
