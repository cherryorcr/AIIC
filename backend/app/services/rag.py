from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path
from typing import Any

from app.storage.db import Database


DEFAULT_ITEMS: list[dict[str, Any]] = [
    {
        "id": "Q001",
        "process_type": "技术面",
        "role": "软件开发/算法",
        "skills": ["数据结构", "复杂度分析"],
        "difficulty": "中",
        "question": "请解释你在一个项目中如何选择数据结构，并说明时间复杂度取舍。",
        "follow_ups": ["如果数据规模扩大十倍，你会怎么改？"],
        "rubric": ["能结合真实项目", "能说清复杂度", "能解释取舍"],
        "source": {"type": "synthetic", "url": None},
    },
    {
        "id": "Q003",
        "process_type": "行为面",
        "role": "软件开发/算法",
        "skills": ["项目 ownership", "沟通协作"],
        "difficulty": "中",
        "question": "讲一个你主动发现并解决问题的项目经历。",
        "follow_ups": ["如果不解决会造成什么影响？", "你如何证明结果有效？"],
        "rubric": ["背景清楚", "行动由本人完成", "结果有证据", "有复盘"],
        "source": {"type": "synthetic", "url": None},
    },
]


MODE_TO_PROCESS = {
    "technical": "技术面",
    "algorithm": "算法面",
    "behavioral": "行为面",
    "stress": "压力面",
    "case": "案例面",
    "research": "科研面",
    "hr": "HR面",
}

KNOWN_SKILLS = {
    "python", "java", "go", "c++", "sql", "fastapi", "postgresql", "redis", "docker",
    "数据结构", "复杂度分析", "系统设计", "故障排查", "沟通协作", "项目 ownership",
    "指标设计", "因果分析", "研究设计", "批判性思维", "动机", "岗位匹配", "抗压",
}

SKILL_ALIASES = {
    "py": "python", "python3": "python", "fast api": "fastapi", "pg": "postgresql",
    "postgres": "postgresql", "redis cache": "redis", "ds": "数据结构", "算法与数据结构": "数据结构",
    "ownership": "项目 ownership", "项目负责": "项目 ownership", "指标": "指标设计",
}


def normalize_skill(value: str) -> str:
    """Normalize common Chinese/English aliases to one graph node label."""
    cleaned = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return SKILL_ALIASES.get(cleaned, cleaned)


def extract_skills(text: str, candidate_skills: set[str] | None = None) -> list[str]:
    """Deterministically extract and normalize skills from JD/profile text.

    The local extractor is intentionally explainable and acts as a fallback for
    the optional LLM extractor; callers can later replace it without changing
    the graph contract.
    """
    candidates = candidate_skills or KNOWN_SKILLS
    lowered = str(text or "").lower()
    found: list[str] = []
    for skill in candidates:
        canonical = normalize_skill(skill)
        aliases = [canonical, *[alias for alias, target in SKILL_ALIASES.items() if target == canonical]]
        if any(alias in lowered for alias in aliases) and canonical not in found:
            found.append(canonical)
    return found


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    found = {skill for skill in KNOWN_SKILLS if skill.lower() in lowered}
    found.update(x for x in re.findall(r"[\u4e00-\u9fff]{2,8}", text) if len(x) >= 2)
    found.update(x.lower() for x in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,20}", text))
    return found


class GraphRAGService:
    """轻量 GraphRAG：关系过滤 + 词法相似度。

    该实现用 JSON 题库完成挑战 MVP。数据层已保留 source、skill、stage 和
    graph edge 所需字段，后续可替换为 PostgreSQL + pgvector/Neo4j。
    """

    def __init__(self, dataset_path: Path, db: Database | None = None):
        self.dataset_path = Path(dataset_path)
        self.db = db
        self.items = self._load()

    def _load(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.dataset_path.read_text(encoding="utf-8"))
            items = payload.get("items", [])
            return self._dedupe(items or DEFAULT_ITEMS)
        except (OSError, ValueError, TypeError):
            return self._dedupe(DEFAULT_ITEMS)

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized = re.sub(r"\s+", "", str(item.get("question", "")).strip().lower())
            fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if not normalized or fingerprint in seen:
                continue
            seen.add(fingerprint)
            copy = dict(item)
            copy["skills"] = list(dict.fromkeys(normalize_skill(x) for x in item.get("skills", []) if str(x).strip()))
            result.append(copy)
        return result

    def attach_db(self, db: Database) -> None:
        self.db = db
        persisted = db.list_questions()
        # An initialized database is authoritative even when it currently has
        # zero active questions (for example after an explicit prune).
        self.items = persisted

    def reload(self) -> int:
        if self.db is not None:
            self.items = self.db.list_questions()
            return len(self.items)
        self.items = self._load()
        return len(self.items)

    @staticmethod
    def _source_refs(item: dict[str, Any]) -> list[str]:
        source = item.get("source") or {}
        source_type = source.get("type") or source.get("source_type")
        if source_type in {"synthetic", "synthetic_mock"}:
            return ["synthetic_mock"]
        source_id = source.get("source_id") or source.get("id") or source.get("url")
        return [str(source_id)] if source_id else []

    def match(
        self,
        *,
        mode: str,
        role: str,
        job_text: str,
        profile: dict[str, Any],
        difficulty: str = "medium",
        limit: int = 5,
    ) -> dict[str, Any]:
        process = MODE_TO_PROCESS.get(mode, mode)
        profile_text = " ".join(
            [*(profile.get("skills") or []), *(profile.get("projects") or []), profile.get("experience") or ""]
        )
        query_tokens = _tokens(" ".join([role, job_text, profile_text]))
        query_vector = self._vector(" ".join([role, job_text, profile_text]))
        candidates: list[tuple[float, dict[str, Any]]] = []
        for item in self.items:
            score = 0.0
            if item.get("process_type") == process:
                score += 5.0
            elif mode == "algorithm" and item.get("process_type") == "技术面":
                score += 1.5
            item_role = str(item.get("role", ""))
            if item_role and any(token in item_role.lower() for token in _tokens(role)):
                score += 1.5
            item_skills = {str(x).lower() for x in item.get("skills", [])}
            score += sum(1.0 for token in query_tokens if token.lower() in item_skills)
            score += self._cosine(query_vector, self._vector(self._item_text(item))) * 2.0
            if not item_skills:
                score += 0.1
            candidates.append((score, item))
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = [item for _, item in candidates[:limit]] or DEFAULT_ITEMS[:limit]
        matched_skills: list[str] = []
        for item in selected:
            for skill in item.get("skills", []):
                if skill not in matched_skills:
                    matched_skills.append(skill)
        questions = []
        for item in selected:
            questions.append(
                {
                    "question_id": item.get("id", "Q-unknown"),
                    "question": item.get("question", "请介绍一个与目标岗位相关的项目。"),
                    "follow_ups": item.get("follow_ups", []),
                    "rubric": item.get("rubric", []),
                    "skills": item.get("skills", []),
                    "difficulty": item.get("difficulty", difficulty),
                    "function_name": item.get("function_name"),
                    "tests": item.get("tests", []),
                    "source_refs": self._source_refs(item),
                    "source_confidence": item.get("source_confidence")
                    or ("synthetic_mock" if "synthetic_mock" in self._source_refs(item) else "observed"),
                    "match_score": round(next(score for score, candidate in candidates if candidate is item), 3),
                }
            )
        return {"matched_skills": matched_skills, "questions": questions}

    @staticmethod
    def _item_text(item: dict[str, Any]) -> str:
        return " ".join([
            str(item.get("question", "")), str(item.get("role", "")),
            str(item.get("process_type", "")), *[str(x) for x in item.get("skills", [])],
        ])

    @staticmethod
    def _vector(text: str, dimensions: int = 64) -> list[float]:
        """Dependency-free hashed embedding used for hybrid retrieval."""
        values = [0.0] * dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            values[index] += 1.0 if digest[4] % 2 else -1.0
        return values

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        denominator = math.sqrt(sum(x * x for x in left) * sum(y * y for y in right))
        return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0

    def evaluate_recall(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate top-k recall against a small human-labelled benchmark."""
        total = len(cases)
        hits = 0
        rows = []
        for case in cases:
            result = self.match(
                mode=str(case.get("mode", "technical")), role=str(case.get("role", "")),
                job_text=str(case.get("job_text", "")), profile=case.get("profile") or {}, limit=int(case.get("k", 5)),
            )
            ids = [item.get("question_id") for item in result.get("questions", [])]
            expected = str(case.get("question_id", ""))
            hit = expected in ids
            hits += int(hit)
            rows.append({"expected": expected, "retrieved": ids, "hit": hit})
        return {"cases": total, "hits": hits, "recall_at_k": round(hits / total, 4) if total else None, "rows": rows}
