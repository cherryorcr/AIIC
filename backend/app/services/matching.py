from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.rag import extract_skills, normalize_skill


MATCH_SCORING_VERSION = "resume-jd-personalized-v2"


def _values(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def build_match_context(
    *,
    role: str,
    job_text: str,
    job_skills: list[str] | None,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical resume/JD comparison used by every score surface."""
    explicit_required = _values(job_skills)
    required = {
        normalize_skill(skill)
        for skill in [*explicit_required, *extract_skills(f"{role} {job_text}")]
        if str(skill).strip()
    }
    profile_parts = [
        *_values(profile.get("skills")),
        *_values(profile.get("projects")),
        *_values(profile.get("achievements")),
        str(profile.get("headline") or ""),
        str(profile.get("summary") or ""),
        str(profile.get("education") or ""),
        str(profile.get("experience") or ""),
    ]
    profile_text = "\n".join(part for part in profile_parts if part.strip())
    candidate = {
        normalize_skill(skill)
        for skill in [*_values(profile.get("skills")), *extract_skills(profile_text)]
        if str(skill).strip()
    }
    matched = sorted(required & candidate)
    gaps = sorted(required - candidate)
    coverage = round(100 * len(matched) / len(required)) if required else 0
    return {
        "role": str(role or "").strip(),
        "job_text": str(job_text or "").strip(),
        "profile": profile,
        "required_skills": sorted(required),
        "candidate_skills": sorted(candidate),
        "profile_matched_skills": matched,
        "skill_gaps": gaps,
        "skill_coverage": coverage,
    }


def match_input_hash(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def match_target_key(role: str, job_text: str, job_id: str | None = None) -> str:
    if job_id:
        return f"job:{job_id}"
    canonical = json.dumps(
        {"role": str(role or "").strip(), "job_text": str(job_text or "").strip()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"adhoc:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def match_score_schema() -> dict[str, Any]:
    dimensions = {
        "skill_coverage": {"type": "number", "minimum": 0, "maximum": 100},
        "experience_relevance": {"type": "number", "minimum": 0, "maximum": 100},
        "project_evidence": {"type": "number", "minimum": 0, "maximum": 100},
        "role_alignment": {"type": "number", "minimum": 0, "maximum": 100},
    }
    personalized_question = {
        "type": "object",
        "required": ["source_question_id", "question", "follow_ups", "personalization_basis"],
        "properties": {
            "source_question_id": {"type": "string"},
            "question": {"type": "string"},
            "follow_ups": {"type": "array", "items": {"type": "string"}},
            "personalization_basis": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": [*dimensions, "strengths", "gaps", "explanation"],
        "properties": {
            **dimensions,
            "strengths": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "explanation": {"type": "string"},
            "personalized_questions": {
                "type": "array",
                "maxItems": 5,
                "items": personalized_question,
            },
        },
        "additionalProperties": False,
    }


def match_score_prompt(
    context: dict[str, Any],
    source_questions: list[dict[str, Any]] | None = None,
    mode: str = "technical",
) -> list[dict[str, str]]:
    question_evidence = []
    for item in (source_questions or [])[:5]:
        question_evidence.append(
            {
                "source_question_id": item.get("question_id"),
                "question": item.get("question", ""),
                "skills": item.get("skills", []),
                "rubric": item.get("rubric", []),
                "follow_ups": item.get("follow_ups", []),
                "source_refs": item.get("source_refs", []),
            }
        )
    payload = {
        "role": context["role"],
        "job_description": context["job_text"],
        "resume": context["profile"],
        "interview_mode": mode,
        "deterministic_skill_extraction": {
            "required_skills": context["required_skills"],
            "matched_skills": context["profile_matched_skills"],
            "missing_skills": context["skill_gaps"],
        },
        "question_bank_evidence": question_evidence,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是招聘岗位匹配评分器。只依据给定 JD 和简历，不得补写候选人经历。"
                "分别对技能覆盖、相关经历、项目证据、岗位方向一致性给出 0-100 分。"
                "分数要拉开差异：没有证据的维度不得超过 40；有可核对的直接证据才可超过 75。"
                "strengths 和 gaps 各最多 4 项，explanation 用两句中文说明评分依据。"
                "同时从 question_bank_evidence 中选择最多 5 道最相关题目，生成 personalized_questions。"
                "每道个性化题必须填写对应的 source_question_id，保留原题考察目标和 Rubric，"
                "结合 JD 的真实职责/技能与简历中明确出现的教育、经历、项目或成果改写；"
                "没有简历证据时只能设计核验问题，不能假设候选人做过某事。"
                "follow_ups 只写可由当前题目自然追问的问题，personalization_basis 只写实际使用的证据。"
                "算法题不得改变原题的函数签名、输入输出语义或测试约束。只输出合法 JSON。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def personalized_questions_from_model(
    model_items: Any,
    source_questions: list[dict[str, Any]],
    *,
    provider: str = "strong_model",
) -> list[dict[str, Any]]:
    """Attach model-written variants to their retrieved source questions.

    The model may only refer to retrieved IDs. Keeping the original metadata
    makes provenance, Rubric, algorithm tests and source URLs survive the
    personalization step.
    """
    if not isinstance(model_items, list):
        return []
    by_id = {str(item.get("question_id")): item for item in source_questions if item.get("question_id")}
    result: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_questions: set[str] = set()
    for raw in model_items[:5]:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("source_question_id") or "").strip()
        base = by_id.get(source_id)
        question = str(raw.get("question") or "").strip()
        if base is None or not question or len(question) < 8 or source_id in seen_sources:
            continue
        signature = re.sub(r"\s+", " ", question).casefold()
        if signature in seen_questions:
            continue
        seen_sources.add(source_id)
        seen_questions.add(signature)
        item = dict(base)
        item["question"] = question[:1200]
        follow_ups = raw.get("follow_ups")
        if isinstance(follow_ups, list) and follow_ups:
            item["follow_ups"] = [str(value).strip()[:500] for value in follow_ups if str(value).strip()][:4]
        basis = raw.get("personalization_basis")
        if isinstance(basis, list):
            item["personalization_basis"] = [str(value).strip()[:240] for value in basis if str(value).strip()][:4]
        else:
            item["personalization_basis"] = []
        item["source_question_id"] = source_id
        item["personalized"] = True
        item["generation_provider"] = provider
        result.append(item)
    return result


def _score(value: Any, fallback: float = 0) -> float:
    try:
        return min(100.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def deterministic_match_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    coverage = int(context["skill_coverage"])
    return {
        "match_score": coverage,
        "score_breakdown": {
            "skill_coverage": coverage,
            "experience_relevance": 0,
            "project_evidence": 0,
            "role_alignment": 0,
        },
        "score_explanation": "当前模型不可用，已按简历与 JD 的明确技能覆盖率生成固定评分。",
        "score_strengths": context["profile_matched_skills"][:4],
        "score_gaps": context["skill_gaps"][:4],
        "score_source": "deterministic",
    }


def model_match_snapshot(
    context: dict[str, Any],
    parsed: dict[str, Any],
    source_questions: list[dict[str, Any]] | None = None,
    *,
    provider: str = "strong_model",
) -> dict[str, Any]:
    breakdown = {
        "skill_coverage": _score(parsed.get("skill_coverage"), context["skill_coverage"]),
        "experience_relevance": _score(parsed.get("experience_relevance")),
        "project_evidence": _score(parsed.get("project_evidence")),
        "role_alignment": _score(parsed.get("role_alignment")),
    }
    total = round(
        0.55 * breakdown["skill_coverage"]
        + 0.20 * breakdown["experience_relevance"]
        + 0.15 * breakdown["project_evidence"]
        + 0.10 * breakdown["role_alignment"]
    )
    personalized_questions = personalized_questions_from_model(
        parsed.get("personalized_questions"), source_questions or [], provider=provider
    )
    return {
        "match_score": total,
        "score_breakdown": {key: round(value) for key, value in breakdown.items()},
        "score_explanation": str(parsed.get("explanation") or "评分基于已确认的简历与岗位描述。")[:500],
        "score_strengths": _values(parsed.get("strengths"))[:4],
        "score_gaps": _values(parsed.get("gaps"))[:4] or context["skill_gaps"][:4],
        "score_source": "strong_model",
        "personalized_questions": personalized_questions,
    }
