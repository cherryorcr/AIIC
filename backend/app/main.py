from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas.models import (
    AlgorithmRunRequest,
    AccountLogin,
    AccountRegister,
    AnswerRequest,
    DocumentConfirmRequest,
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
    JobCreate,
    ReportCreate,
    MatchRequest,
    SessionCreate,
    TemporaryUserCreate,
    UserProfileUpdate,
)
from app.services.interview import InterviewService
from app.services.auth import (
    hash_password,
    hash_session_token,
    new_session_token,
    normalize_email,
    verify_password,
)
from app.services.documents import ALLOWED_EXTENSIONS, extract_document_text, parse_document
from app.services.model_router import ModelRouter
from app.services.prompts import SCENE_POLICIES
from app.services.rag import GraphRAGService, MODE_TO_PROCESS, extract_skills
from app.services.sandbox import SandboxService
from app.storage.db import Database


db = Database(settings.database_path, database_url=settings.database_url)
rag = GraphRAGService(settings.dataset_path)
router = ModelRouter(settings, db)
sandbox = SandboxService(settings)
interviews = InterviewService(db, rag, router, sandbox)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    # 初次启动将示例/已配置数据幂等写入知识库；后续 GraphRAG 统一读数据库。
    db.seed_questions(rag.items)
    rag.attach_db(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="GraphRAG 场景化 AI 面试陪练后端",
    lifespan=lifespan,
)
origins = [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=bool(origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    database_ok = db.ping()
    return {
        "status": "ok" if database_ok else "degraded",
        "app": "ok",
        "database": "ok" if database_ok else "unavailable",
        "database_backend": "postgresql" if settings.database_url else "sqlite",
        "graph_rag_items": len(rag.items),
        "local_model_configured": bool(settings.local_model_base_url),
        "strong_model_configured": bool(settings.strong_model_base_url and settings.strong_model_api_key),
        "sandbox_enabled": settings.sandbox_enabled,
    }


@app.get("/api/v1/model/health")
async def model_health() -> dict[str, Any]:
    """Diagnostic provider health and in-process fallback state."""
    probe = await router.health()
    probe["states"] = router.provider_status()
    probe["fallback_available"] = True
    return probe


@app.get("/api/v1/scenes")
def list_scenes() -> dict[str, Any]:
    """Return the seven interview policies so the UI does not duplicate them."""
    return {
        "scenes": [
            {"id": scene_id, "name": policy["name"], "dimensions": policy["dimensions"]}
            for scene_id, policy in SCENE_POLICIES.items()
        ]
    }


@app.post("/api/v1/matches")
def preview_match(request: SessionCreate) -> dict[str, Any]:
    """Preview role/skill/question matching without creating an interview session."""
    matched = rag.match(
        mode=request.mode,
        role=request.role,
        job_text=request.job_text,
        profile=request.user_profile.model_dump(),
        difficulty=request.difficulty,
    )
    questions = matched.get("questions", [])
    # This is deliberately an explainable heuristic score for the MVP; a
    # configured model can later replace it without changing the response shape.
    score = min(100, max(0, 50 + len(matched.get("matched_skills", [])) * 5 + min(len(questions), 5) * 2))
    confidences = [str(question.get("source_confidence") or "").lower() for question in questions]
    if any(value == "synthetic_mock" for value in confidences):
        source_confidence = "synthetic_mock"
    elif any(value == "medium" for value in confidences):
        source_confidence = "medium"
    elif confidences and all(value == "high" for value in confidences):
        source_confidence = "high"
    else:
        source_confidence = "observed"
    return {
        "role": request.role,
        "match_score": score,
        "matched_skills": matched.get("matched_skills", []),
        "questions": questions,
        "source_confidence": source_confidence,
    }


@app.post("/api/v1/jobs/extract-skills")
def extract_job_skills(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Return explainable local JD skill extraction for profile/JD editors."""
    text = " ".join(str(payload.get(key) or "") for key in ("jd_text", "job_text", "role", "description"))
    skills = extract_skills(text)
    return {"skills": skills, "extractor": "deterministic-local", "confidence": "candidate"}


@app.get("/api/v1/questions")
def public_questions(
    query: str | None = None,
    q: str | None = None,
    process_type: str | None = None,
    skill: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Read-only question-bank search for the frontend and anonymous users."""
    # The UI uses stable mode IDs while the knowledge tables retain the
    # user-facing Chinese stage labels. Accept both at the API boundary.
    process_type = MODE_TO_PROCESS.get(process_type or "", process_type)
    items = db.list_questions(process_type=process_type, limit=max(1, min(limit, 500)))
    normalized_query = (query or q or "").strip().lower()
    normalized_skill = (skill or "").strip().lower()
    if normalized_query or normalized_skill:
        filtered = []
        for item in items:
            haystack = " ".join(
                [item.get("question", ""), item.get("role", ""), item.get("process_type", ""), *item.get("skills", [])]
            ).lower()
            skills = [str(value).lower() for value in item.get("skills", [])]
            if normalized_query and normalized_query not in haystack:
                continue
            if normalized_skill and not any(normalized_skill in value for value in skills):
                continue
            filtered.append(item)
        items = filtered
    return {"items": items, "total": len(items)}


@app.get("/api/v1/questions/{question_id}")
def public_question(question_id: str) -> dict[str, Any]:
    item = db.get_question(question_id)
    if item is None:
        raise HTTPException(status_code=404, detail="question_not_found")
    return {"item": item}


AUTH_COOKIE = "techmatch_session"


def _request_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return request.cookies.get(AUTH_COOKIE)


def _set_auth_cookie(response: Response, token: str) -> None:
    max_age = max(1, settings.auth_session_days) * 24 * 60 * 60
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    # Remove the old raw user-id cookie; it is not an authentication secret.
    response.delete_cookie("interview_user_id", path="/")


def _issue_auth_session(user_id: str, request: Request, response: Response) -> None:
    token = new_session_token()
    db.create_auth_session(
        user_id,
        hash_session_token(token),
        lifetime_days=settings.auth_session_days,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    _set_auth_cookie(response, token)


def _authenticated_user(request: Request) -> dict[str, Any] | None:
    token = _request_token(request)
    if not token:
        return None
    resolved = db.resolve_auth_session(hash_session_token(token))
    return resolved["user"] if resolved else None


def _resolve_user(request: Request, response: Response | None = None) -> str:
    """Resolve a hashed server-side session, creating an isolated guest if absent."""
    db.init()
    user = _authenticated_user(request)
    if user:
        resolved = str(user["id"])
    else:
        user = db.create_temp_user()
        resolved = str(user["id"])
        if response is not None:
            _issue_auth_session(resolved, request, response)
    if response is not None:
        response.headers["X-User-Id"] = resolved
    return resolved


def _revoke_request_session(request: Request) -> None:
    token = _request_token(request)
    if token:
        db.revoke_auth_session(hash_session_token(token))


def _validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise HTTPException(status_code=422, detail="email_invalid")
    return normalized


def _require_session_owner(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    session = db.get_session(session_id)
    if session is None or session.get("user_id") != uid:
        # Use 404 so session identifiers cannot be enumerated across accounts.
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


@app.post("/api/v1/users/temporary")
def create_temporary_user(payload: TemporaryUserCreate, request: Request, response: Response) -> dict[str, Any]:
    # Client-provided user IDs are deliberately ignored: an ID is not proof of ownership.
    _revoke_request_session(request)
    user = db.create_temp_user(display_name=payload.display_name)
    _issue_auth_session(str(user["id"]), request, response)
    response.headers["X-User-Id"] = str(user["id"])
    return {"user": user, "status": "ready"}


@app.post("/api/v1/auth/register", status_code=201)
def register_account(payload: AccountRegister, request: Request, response: Response) -> dict[str, Any]:
    email = _validate_email(payload.email)
    current = _authenticated_user(request)
    if current and not current.get("is_temporary"):
        raise HTTPException(status_code=409, detail="account_already_registered")
    upgrade_user_id = str(current["id"]) if current and current.get("is_temporary") else None
    try:
        user = db.register_account(
            email,
            hash_password(payload.password),
            payload.display_name.strip(),
            upgrade_user_id=upgrade_user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 409 if detail in {"email_already_registered", "account_already_registered"} else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        # Handle a concurrent unique-email insert without leaking database details.
        if db.get_user_credentials(email):
            raise HTTPException(status_code=409, detail="email_already_registered") from exc
        raise
    _revoke_request_session(request)
    _issue_auth_session(str(user["id"]), request, response)
    return {"user": user, "profile": db.get_user_profile(str(user["id"])), "status": "registered"}


@app.post("/api/v1/auth/login")
def login_account(payload: AccountLogin, request: Request, response: Response) -> dict[str, Any]:
    email = _validate_email(payload.email)
    credentials = db.get_user_credentials(email)
    if not credentials or not verify_password(payload.password, credentials.get("password_hash")):
        raise HTTPException(status_code=401, detail="email_or_password_invalid")
    _revoke_request_session(request)
    user = db.get_user(str(credentials["id"]))
    if not user:
        raise HTTPException(status_code=401, detail="email_or_password_invalid")
    _issue_auth_session(str(user["id"]), request, response)
    return {"user": user, "profile": db.get_user_profile(str(user["id"])), "status": "authenticated"}


@app.post("/api/v1/auth/logout")
def logout_account(request: Request, response: Response) -> dict[str, Any]:
    _revoke_request_session(request)
    response.delete_cookie(AUTH_COOKIE, path="/")
    response.delete_cookie("interview_user_id", path="/")
    return {"status": "logged_out"}


@app.get("/api/v1/users/me")
@app.get("/api/v1/auth/me")
def current_user(request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    user = db.get_user(uid)
    return {
        "user": user,
        "profile": db.get_user_profile(uid),
        "authenticated": bool(user and not user.get("is_temporary")),
    }


@app.get("/api/v1/profile")
def get_profile(request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"user_id": uid, "profile": db.get_user_profile(uid) or {"skills": [], "projects": [], "constraints": []}}


@app.put("/api/v1/profile")
def put_profile(request: UserProfileUpdate, http_request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(http_request, response)
    profile = db.save_user_profile(uid, request.model_dump())
    return {"user_id": uid, "profile": profile, "status": "saved"}


@app.post("/api/v1/documents/parse")
async def parse_candidate_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    kind: str = Form(...),
) -> dict[str, Any]:
    """Upload and parse a resume or JD into a reviewable draft."""
    kind = {
        "resume": "resume",
        "jd": "job_description",
        "job": "job_description",
        "job_description": "job_description",
    }.get(kind, kind)
    if kind not in {"resume", "job_description"}:
        raise HTTPException(status_code=422, detail="document_kind_invalid")
    uid = _resolve_user(request, response)
    filename = Path(file.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported_document_type")
    # Read one byte past the limit so oversized uploads can be rejected before
    # parser allocation.  The binary is held only for this request.
    max_bytes = max(1, int(settings.document_max_bytes))
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="document_too_large")
    content_type = file.content_type or "application/octet-stream"
    try:
        extracted_text = extract_document_text(
            filename, content_type, data, max_chars=max(1, int(settings.document_max_text_chars))
        )
    except ValueError as exc:
        # Keep a failed record so the UI can show what happened without
        # persisting the original binary or its contents.
        db.save_candidate_document(
            {
                "user_id": uid,
                "kind": kind,
                "filename": filename,
                "content_type": content_type,
                "status": "failed",
                "error": str(exc),
            }
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_result = await parse_document(kind, extracted_text, router)  # type: ignore[arg-type]
    document = db.save_candidate_document(
        {
            "user_id": uid,
            "kind": kind,
            "filename": filename,
            "content_type": content_type,
            "extracted_text": extracted_text,
            "parsed_json": parsed_result["parsed"],
            "status": "parsed",
            "provider": parsed_result.get("provider"),
            "error": parsed_result.get("error"),
        }
    )
    return {"document": document, "status": "needs_confirmation"}


@app.get("/api/v1/documents")
def list_candidate_documents(request: Request, response: Response, limit: int = 100) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"documents": db.list_candidate_documents(uid, max(1, min(limit, 500)))}


@app.get("/api/v1/documents/{document_id}")
def get_candidate_document(document_id: str, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    document = db.get_candidate_document(document_id)
    if document is None or document.get("user_id") != uid:
        raise HTTPException(status_code=404, detail="document_not_found")
    return {"document": document}


@app.post("/api/v1/documents/{document_id}/confirm")
def confirm_candidate_document(
    document_id: str,
    payload: DocumentConfirmRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Persist the human-reviewed resume/JD extraction to its canonical table."""
    uid = _resolve_user(request, response)
    document = db.get_candidate_document(document_id)
    if document is None or document.get("user_id") != uid:
        raise HTTPException(status_code=404, detail="document_not_found")
    reviewed = payload.parsed or {}
    if not isinstance(reviewed, dict):
        raise HTTPException(status_code=422, detail="parsed_payload_invalid")
    kind = str(document.get("kind"))
    content = reviewed.get("profile" if kind == "resume" else "job")
    if not isinstance(content, dict):
        # Accept the compact form sent by clients that edit the inner object.
        content = reviewed
    if kind == "resume":
        existing = db.get_user_profile(uid) or {}
        allowed = {
            "full_name", "headline", "summary", "education", "experience",
            "skills", "projects", "achievements", "constraints",
        }
        merged = {key: value for key, value in existing.items() if key in allowed}
        merged.update({key: content[key] for key in allowed if key in content})
        profile = db.save_user_profile(uid, merged)
        linked_id = uid
        resource = {"profile": profile}
    elif kind == "job_description":
        allowed = {
            "title", "company", "role", "summary", "skills", "responsibilities",
            "requirements", "seniority", "location", "jd_text",
        }
        job_payload = {key: content[key] for key in allowed if key in content}
        job_payload["jd_text"] = job_payload.get("jd_text") or str(document.get("extracted_text") or "")
        saved_job = db.save_job(uid, job_payload)
        linked_id = str(saved_job.get("id") or saved_job.get("job_id"))
        resource = {"job": saved_job}
    else:  # defensive check for rows created outside the API
        raise HTTPException(status_code=400, detail="document_kind_invalid")
    updated = dict(document)
    updated.update({"parsed": reviewed, "status": "confirmed", "linked_id": linked_id, "error": None})
    document = db.save_candidate_document(updated)
    return {"document": document, "status": "confirmed", **resource}


@app.delete("/api/v1/documents/{document_id}")
def delete_candidate_document(document_id: str, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    if not db.delete_candidate_document(document_id, uid):
        raise HTTPException(status_code=404, detail="document_not_found")
    return {"document_id": document_id, "status": "deleted"}


@app.get("/api/v1/jobs")
def list_user_jobs(request: Request, response: Response, limit: int = 100) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"jobs": db.list_jobs(uid, limit=max(1, min(limit, 500)))}


@app.post("/api/v1/jobs")
def create_user_job(job: JobCreate, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    payload = job.model_dump()
    if not payload.get("skills"):
        payload["skills"] = extract_skills(" ".join([payload.get("role", ""), payload.get("title", ""), payload.get("jd_text", "")]))
    saved = db.save_job(uid, payload)
    return {"job": saved, "status": "saved"}


@app.get("/api/v1/jobs/{job_id}")
def get_user_job(job_id: str, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    job = db.get_job(job_id)
    if job is None or job.get("user_id") != uid:
        raise HTTPException(status_code=404, detail="job_not_found")
    return {"job": job}


@app.get("/api/v1/favorites")
def list_user_favorites(request: Request, response: Response, limit: int = 100) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"items": db.list_favorite_questions(uid, max(1, min(limit, 500)))}


@app.post("/api/v1/questions/{question_id}/favorite")
def toggle_question_favorite(
    question_id: str,
    request: Request,
    response: Response,
    body: dict[str, Any] | None = Body(default=None),
    favorite: bool | None = None,
) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    # Accept both a query parameter and the JSON body used by the frontend.
    desired = bool((body or {}).get("favorite", True if favorite is None else favorite))
    if desired:
        if not db.favorite_question(uid, question_id):
            raise HTTPException(status_code=404, detail="question_not_found")
    else:
        db.unfavorite_question(uid, question_id)
    return {"user_id": uid, "question_id": question_id, "favorite": desired}


@app.get("/api/v1/history")
def training_history(request: Request, response: Response, limit: int = 100) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"items": db.list_training_history(uid, max(1, min(limit, 500)))}


@app.get("/api/v1/reports")
def list_user_reports(request: Request, response: Response, limit: int = 100) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    return {"reports": db.list_reports(uid, max(1, min(limit, 500)))}


@app.get("/api/v1/reports/{report_id}")
def get_user_report(report_id: str, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    report = db.get_report(report_id)
    if report is None or report.get("user_id") != uid:
        raise HTTPException(status_code=404, detail="report_not_found")
    return {"report": report}


@app.post("/api/v1/reports")
def create_user_report(report: ReportCreate, request: Request, response: Response) -> dict[str, Any]:
    uid = _resolve_user(request, response)
    if report.session_id:
        _require_session_owner(report.session_id, request, response)
    saved = db.save_report(uid, report.session_id, {"title": report.title, **report.payload})
    return {"report": saved, "status": "saved"}


@app.get("/api/v1/workspace/overview")
def workspace_overview(request: Request, response: Response) -> dict[str, Any]:
    """Return a readiness snapshot derived only from the current user's data."""
    uid = _resolve_user(request, response)
    profile = db.get_user_profile(uid) or {"skills": [], "projects": [], "constraints": []}
    jobs = db.list_jobs(uid, limit=100)
    history = db.list_training_history(uid, limit=100)
    reports = db.list_reports(uid, limit=100)
    latest_job = jobs[0] if jobs else None
    has_target_job = bool(
        latest_job
        and any(
            str(latest_job.get(key) or "").strip()
            for key in ("jd_text", "job_text", "role", "title")
        )
    )

    raw_profile_skills = {
        str(value).strip().lower() for value in profile.get("skills", []) if str(value).strip()
    }
    profile_skills = raw_profile_skills | set(extract_skills(" ".join(raw_profile_skills)))
    required_values = (latest_job or {}).get("skills") or extract_skills(
        str((latest_job or {}).get("jd_text") or "")
    )
    raw_required_skills = {
        str(value).strip().lower() for value in required_values if str(value).strip()
    }
    required_skills = raw_required_skills | set(
        extract_skills(" ".join([*raw_required_skills, str((latest_job or {}).get("jd_text") or "")]))
    )
    matched_skills = sorted(profile_skills & required_skills) if has_target_job else []
    skill_gaps = sorted(required_skills - profile_skills) if has_target_job else []
    # A readiness score is a comparison against a concrete target role. A
    # profile or training history alone must not look like a 50-point match.
    skill_coverage = len(matched_skills) / len(required_skills) if required_skills else 0.0

    completeness_fields = (
        profile.get("full_name"), profile.get("headline"), profile.get("summary"),
        profile.get("education"), profile.get("experience"), profile.get("projects"), profile.get("skills"),
    )
    profile_completeness = sum(bool(value) for value in completeness_fields) / len(completeness_fields)
    score_values = [
        float(item["average_score"])
        for item in history
        if isinstance(item.get("average_score"), (int, float))
    ]
    training_score = min(1.0, (sum(score_values) / len(score_values)) / 5) if score_values else min(1.0, len(history) / 5)
    readiness = (
        round(100 * (0.45 * skill_coverage + 0.30 * profile_completeness + 0.25 * training_score))
        if has_target_job
        else 0
    )
    if not has_target_job:
        readiness_label = "先设置目标岗位，再开始针对性训练"
    elif readiness >= 80:
        readiness_label = "准备充分，继续强化高频场景"
    elif readiness >= 55:
        readiness_label = "基础已具备，优先补齐能力缺口"
    else:
        readiness_label = "先完善背景与目标岗位，再开始针对性训练"
    return {
        "user_id": uid,
        "readiness": {
            "score": readiness,
            "label": readiness_label,
            "role": str((latest_job or {}).get("role") or (latest_job or {}).get("title") or profile.get("headline") or "尚未设置目标岗位"),
            "profile_completeness": round(profile_completeness * 100),
            "skill_coverage": round(skill_coverage * 100),
            "training_score": round(training_score * 100),
            "matched_skills": matched_skills,
            "skill_gaps": skill_gaps,
        },
        "counts": {
            "skills": len(profile_skills),
            "jobs": len(jobs),
            "sessions": len(history),
            "reports": len(reports),
        },
        "latest_job": latest_job,
        "recent_sessions": history[:5],
    }


def _require_admin(token: str | None) -> None:
    # 开发环境允许空 token；生产环境必须设置 ADMIN_TOKEN。
    if settings.admin_token and token != settings.admin_token:
        raise HTTPException(status_code=401, detail="admin_token_invalid")


@app.get("/api/v1/admin/knowledge/stats")
def knowledge_stats(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(x_admin_token)
    return {**db.knowledge_stats(), "dataset_path": str(settings.dataset_path), "status": "loaded"}


@app.post("/api/v1/admin/knowledge/reload")
def reload_knowledge(
    prune: bool = False,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    items = rag._load()
    processed = db.seed_questions(items, prune=prune)
    loaded = rag.reload()
    return {
        **db.knowledge_stats(),
        "items_processed": processed,
        "items_loaded": loaded,
        "prune": prune,
        "status": "reloaded",
    }


@app.get("/api/v1/admin/knowledge/items")
def list_knowledge_items(
    process_type: str | None = None,
    query: str | None = None,
    q: str | None = None,
    limit: int = 100,
    include_inactive: bool = False,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    process_type = MODE_TO_PROCESS.get(process_type or "", process_type)
    items = db.list_questions(
            process_type=process_type,
            limit=max(1, min(limit, 500)),
            include_inactive=include_inactive,
        )
    normalized_query = (query or q or "").strip().lower()
    if normalized_query:
        items = [
            item for item in items
            if normalized_query in " ".join([
                str(item.get("question", "")), str(item.get("role", "")),
                str(item.get("process_type", "")), *[str(x) for x in item.get("skills", [])]
            ]).lower()
        ]
    return {"items": items, "total": len(items)}


@app.get("/api/v1/admin/knowledge/sources")
def list_knowledge_sources(
    limit: int = 100,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    return {"sources": db.list_sources(limit=max(1, min(limit, 500)))}


@app.post("/api/v1/admin/knowledge/evaluate")
def evaluate_knowledge_recall(
    cases: list[dict[str, Any]] = Body(default_factory=list),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    return rag.evaluate_recall(cases)


@app.post("/api/v1/admin/knowledge/items")
def create_knowledge_item(
    request: KnowledgeItemCreate,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    payload = request.model_dump()
    if not payload.get("id"):
        payload["id"] = None
    db.seed_questions([payload])
    rag.reload()
    item_id = payload.get("id")
    if not item_id:
        from app.storage.db import stable_id

        item_id = stable_id("Q", str(payload["question"]), 8)
    item = db.get_question(item_id, include_inactive=True)
    return {"item": item, "status": "created"}


@app.patch("/api/v1/admin/knowledge/items/{question_id}")
def update_knowledge_item(
    question_id: str,
    request: KnowledgeItemUpdate,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    item = db.update_question(question_id, request.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge_item_not_found")
    rag.reload()
    return {"item": item, "status": "updated"}


@app.delete("/api/v1/admin/knowledge/items/{question_id}")
def delete_knowledge_item(
    question_id: str,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    if not db.delete_question(question_id):
        raise HTTPException(status_code=404, detail="knowledge_item_not_found")
    rag.reload()
    return {"question_id": question_id, "status": "deleted", "delete_mode": "soft"}


@app.post("/api/interview/start")
@app.post("/api/v1/sessions")
async def start_session(request: SessionCreate, http_request: Request, response: Response) -> dict[str, Any]:
    try:
        payload = request.model_dump()
        payload["user_id"] = _resolve_user(http_request, response)
        stored_profile = db.get_user_profile(payload["user_id"]) or {}
        submitted_profile = payload.get("user_profile") or {}
        if not any(submitted_profile.get(key) for key in ("skills", "projects", "education", "experience")):
            payload["user_profile"] = stored_profile
        if payload.get("job_id"):
            job = db.get_job(str(payload["job_id"]))
            if job is None or job.get("user_id") != payload["user_id"]:
                raise HTTPException(status_code=404, detail="job_not_found")
            if not payload.get("job_text"):
                payload["job_text"] = str(job.get("jd_text") or job.get("job_text") or "")
            if not payload.get("role") or payload.get("role") == "通用软件开发工程师":
                payload["role"] = str(job.get("role") or job.get("title") or payload["role"])
        return await interviews.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/sessions/{session_id}/match")
def match_session(
    session_id: str, payload: MatchRequest, request: Request, response: Response
) -> dict[str, Any]:
    _require_session_owner(session_id, request, response)
    try:
        return interviews.match(session_id, payload.filters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc


@app.post("/api/interview/answer")
async def answer_legacy(
    payload: AnswerRequest,
    request: Request,
    response: Response,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or payload.session_id
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id query parameter is required")
    return await _answer(session_id, payload, request, response)


@app.post("/api/v1/sessions/{session_id}/turns")
async def answer_turn(
    session_id: str, payload: AnswerRequest, request: Request, response: Response
) -> dict[str, Any]:
    return await _answer(session_id, payload, request, response)


async def _answer(
    session_id: str, payload: AnswerRequest, request: Request, response: Response
) -> dict[str, Any]:
    _require_session_owner(session_id, request, response)
    try:
        return await interviews.answer(session_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/sessions/{session_id}/algorithm/run")
def run_algorithm(
    session_id: str, payload: AlgorithmRunRequest, request: Request, response: Response
) -> dict[str, Any]:
    session = _require_session_owner(session_id, request, response)
    if session.get("mode") != "algorithm":
        raise HTTPException(status_code=400, detail="session_mode_must_be_algorithm")
    current_question = session.get("current_question") or {}
    if payload.question_id != current_question.get("question_id"):
        raise HTTPException(status_code=400, detail="question_id_not_current")
    tests = payload.tests or current_question.get("tests") or []
    result = sandbox.run(payload.code, tests)
    return {"session_id": session_id, "question_id": payload.question_id, **result}


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    _require_session_owner(session_id, request, response)
    try:
        return interviews.summary(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc


@app.get("/api/v1/sessions/{session_id}/summary")
def get_summary(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    return get_session(session_id, request, response)


@app.post("/api/v1/sessions/{session_id}/complete")
def complete_session(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    _require_session_owner(session_id, request, response)
    try:
        return interviews.complete(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc


@app.get("/api/v1/sessions/{session_id}/events")
def session_events(session_id: str, request: Request, response: Response) -> StreamingResponse:
    _require_session_owner(session_id, request, response)

    def stream():
        payload = {"type": "session_status", "session_id": session_id, "status": "ready"}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
