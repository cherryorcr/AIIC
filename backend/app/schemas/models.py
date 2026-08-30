from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


InterviewMode = Literal["technical", "algorithm", "behavioral", "stress", "case", "research", "hr", "group"]
Difficulty = Literal["easy", "medium", "hard"]


class UserProfile(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    projects: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: str | None = None
    experience: str | None = None
    achievements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class SessionCreate(BaseModel):
    mode: InterviewMode = "technical"
    role: str = "通用软件开发工程师"
    job_text: str = ""
    user_profile: UserProfile = Field(default_factory=UserProfile)
    difficulty: Difficulty = "medium"
    # Kept for wire compatibility only. The server always derives ownership
    # from the hashed auth session and ignores client-provided user IDs.
    user_id: str | None = None
    job_id: str | None = None


class TemporaryUserCreate(BaseModel):
    """Create a new isolated temporary user (client IDs are ignored)."""

    user_id: str | None = None
    display_name: str = "临时用户"


class TemporaryUser(BaseModel):
    id: str
    display_name: str = ""
    is_temporary: bool = True
    created_at: str | None = None
    last_seen_at: str | None = None


class AccountRegister(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class AccountLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: str | None = None
    experience: str | None = None
    achievements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class UserProfileRecord(BaseModel):
    user_id: str
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: str | None = None
    experience: str | None = None
    achievements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    profile_json: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class JobCreate(BaseModel):
    id: str | None = None
    title: str = ""
    company: str = ""
    role: str = ""
    jd_text: str = ""
    skills: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_license: str | None = None


class JobRecord(BaseModel):
    id: str
    user_id: str | None = None
    title: str = ""
    company: str = ""
    role: str = ""
    jd_text: str = ""
    skills: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_license: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


DocumentKind = Literal["resume", "job_description"]
DocumentStatus = Literal["uploaded", "parsed", "confirmed", "failed"]


class CandidateDocumentRecord(BaseModel):
    id: str
    user_id: str
    kind: DocumentKind
    filename: str
    content_type: str = "application/octet-stream"
    extracted_text: str = ""
    parsed_json: dict[str, Any] = Field(default_factory=dict)
    status: DocumentStatus = "uploaded"
    provider: str | None = None
    error: str | None = None
    linked_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DocumentConfirmRequest(BaseModel):
    """Human-reviewed extraction payload submitted before writing a profile/JD."""

    parsed: dict[str, Any] = Field(default_factory=dict)
    # ``data`` is accepted as an alias for clients that name the editable
    # payload generically.  The API normalizes both forms before persistence.
    data: dict[str, Any] | None = None


class FavoriteRequest(BaseModel):
    user_id: str
    question_id: str


class FavoriteRecord(BaseModel):
    user_id: str
    question_id: str
    created_at: str | None = None


class ReportCreate(BaseModel):
    # Kept for legacy clients; report ownership always comes from auth.
    user_id: str | None = None
    session_id: str | None = None
    title: str = "训练报告"
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportRecord(BaseModel):
    id: str
    user_id: str | None = None
    session_id: str | None = None
    title: str = ""
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class MatchRequest(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)


class AnswerRequest(BaseModel):
    session_id: str | None = None
    question_id: str
    answer_text: str = ""
    code: str | None = None
    language: str = "python"
    tests: list[dict[str, Any]] = Field(default_factory=list)
    # A supplement/revision is evaluated against an earlier turn even when
    # the session has already advanced to a follow-up question.
    revision_of: str | None = None
    answer_mode: Literal["answer", "supplement", "retry"] = "answer"


class AlgorithmRunRequest(BaseModel):
    question_id: str
    code: str
    language: str = "python"
    tests: list[dict[str, Any]] = Field(default_factory=list)


class SessionStartResponse(BaseModel):
    session_id: str
    mode: InterviewMode
    role: str
    matched_skills: list[str] = Field(default_factory=list)
    question_id: str
    question: str
    why_this_question: str
    source_refs: list[str] = Field(default_factory=list)
    tests: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "questioning"


class Feedback(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    evidence_quotes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    better_answer: str = ""
    next_question: str | None = None
    next_action: str = "进入下一题"
    source_refs: list[str] = Field(default_factory=list)
    # Present only for the group-interview scene. The simulated participant
    # response gives the candidate a concrete next interaction to address.
    group_phase: str | None = None
    group_reaction: dict[str, Any] | None = None


class TurnResponse(BaseModel):
    turn_id: str
    session_id: str
    question_id: str
    feedback: Feedback
    next_question: dict[str, Any] | None = None
    algorithm_result: dict[str, Any] | None = None


class AlgorithmRunResponse(BaseModel):
    job_id: str
    session_id: str
    question_id: str
    status: Literal["passed", "failed", "timeout", "error", "rejected", "disabled", "resource_limited"]
    passed: int = 0
    total: int = 0
    stdout: str = ""
    stderr: str = ""
    runtime_ms: float = 0
    details: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeItemCreate(BaseModel):
    id: str | None = None
    process_type: str
    role: str = "通用岗位"
    skills: list[str] = Field(default_factory=list)
    difficulty: str = "中"
    question: str
    follow_ups: list[str] = Field(default_factory=list)
    rubric: list[str] = Field(default_factory=list)
    function_name: str | None = None
    tests: list[dict[str, Any]] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=lambda: {"type": "synthetic_mock"})


class KnowledgeItemUpdate(BaseModel):
    """Partial update payload for an existing knowledge item."""

    process_type: str | None = None
    role: str | None = None
    skills: list[str] | None = None
    difficulty: str | None = None
    question: str | None = None
    follow_ups: list[str] | None = None
    rubric: list[str] | None = None
    function_name: str | None = None
    tests: list[dict[str, Any]] | None = None
    source: dict[str, Any] | None = None
    source_confidence: str | None = None
    is_active: bool | None = None


class KnowledgeSource(BaseModel):
    source_id: str
    title: str = ""
    url: str | None = None
    license: str | None = None
    source_type: Literal["online", "synthetic_mock", "user_submitted", "official"] = "online"
    version: str | None = None
    accessed_at: str | None = None
    redistribution_allowed: bool = False
