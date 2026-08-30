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
    "group": "群面",
}


GROUP_ITEMS: list[dict[str, Any]] = [
    {
        "id": "Q-GROUP-001",
        "process_type": "群面",
        "role": "通用岗位",
        "skills": ["问题拆解", "沟通协作", "共识推动", "时间管理"],
        "difficulty": "中高",
        "question": "某团队需要在有限预算下决定下一季度最值得投入的产品方向。请在 10 分钟内统一目标、提出评估指标并达成可执行的优先级结论。",
        "follow_ups": [
            "模拟队友认为应优先满足最大客户的需求，请回应并推动小组形成共同判断。",
            "还剩 2 分钟，请总结最终方案、关键依据和未决风险。",
        ],
        "rubric": ["先澄清目标与约束", "主动倾听并整合观点", "用事实推动共识", "控制讨论节奏并形成结论"],
        "source": {"type": "synthetic_mock", "url": None},
        "source_confidence": "synthetic_mock",
    }
]

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
        def contains_alias(alias: str) -> bool:
            # ASCII skill names need token boundaries: SQL is not present in
            # PostgreSQL, and Go should not match words such as "good".
            if re.fullmatch(r"[a-z0-9+#. -]+", alias):
                return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered) is not None
            return alias in lowered

        if any(contains_alias(alias) for alias in aliases) and canonical not in found:
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
            # Group discussion is an application-specific simulation layer;
            # keep one clearly labelled synthetic scenario available even when
            # the imported public question set has no group-interview records.
            if not any(isinstance(item, dict) and item.get("process_type") == "群面" for item in items):
                items = [*items, *GROUP_ITEMS]
            return self._dedupe(items or [*DEFAULT_ITEMS, *GROUP_ITEMS])
        except (OSError, ValueError, TypeError):
            # Keep every supported scene usable even if the optional dataset
            # file is missing or malformed. The group prompt is an
            # application-owned simulation and must not disappear with the
            # external dataset.
            return self._dedupe([*DEFAULT_ITEMS, *GROUP_ITEMS])

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            signature = GraphRAGService._question_signature(item)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            copy = dict(item)
            copy["skills"] = list(dict.fromkeys(normalize_skill(x) for x in item.get("skills", []) if str(x).strip()))
            result.append(copy)
        return result

    @staticmethod
    def _question_signature(item: dict[str, Any]) -> str:
        """Return a stable topic key so paraphrases do not become duplicates.

        Exact text hashes miss common variants such as a translated prompt
        with an added ``solution(s)`` instruction. Known algorithm families get
        explicit keys; other questions fall back to normalized content.
        """
        process = str(item.get("process_type") or "").strip().lower()
        text = str(item.get("question") or "").lower()
        text = re.sub(r"[（(][^）)]{0,80}(?:依据|source|转载|转写|leetcode)[^）)]*[）)]", " ", text, flags=re.I)
        text = re.sub(r"[^a-z0-9+#\u4e00-\u9fff]+", " ", text)
        algorithm_topics = [
            ("two_sum", (r"two sum", r"两数之和", r"和为 target")),
            ("stock_profit", (r"stock", r"股票价格", r"最大利润")),
            ("product_except_self", (r"product except", r"除 nums\s*\[?i\]?", r"除.*元素.*乘积")),
            ("maximum_subarray", (r"maximum subarray", r"最大子数组", r"连续子数组.*最大和")),
            ("contains_duplicate", (r"contains duplicate", r"存在重复元素", r"判断.*重复")),
            ("rotated_search", (r"rotated.*array", r"旋转.*数组.*target", r"旋转后.*下标")),
            ("climbing_stairs", (r"climbing stairs", r"爬楼梯", r"1.*2.*阶")),
            ("coin_change", (r"coin change", r"硬币面额", r"最少硬币")),
            ("number_of_islands", (r"number of islands", r"岛屿数量", r"0 1.*网格")),
            ("course_schedule", (r"course schedule", r"课程.*先修", r"完成所有课程")),
            ("reverse_linked_list", (r"reverse linked list", r"链表.*反转", r"原地反转")),
            ("valid_parentheses", (r"valid parentheses", r"括号.*有效", r"括号.*闭合")),
            ("merge_intervals", (r"merge intervals", r"合并.*区间", r"重叠.*区间")),
            ("longest_substring_without_repeat", (r"longest.*substring", r"最长.*子串", r"不含重复.*字符")),
            ("top_k_frequent", (r"top k", r"频率最高.*k", r"出现频率.*元素")),
            ("maximum_depth_tree", (r"maximum depth", r"二叉树.*最大深度", r"二叉树.*深度")),
            ("generate_parentheses", (r"generate parentheses", r"生成.*括号", r"n 对括号")),
        ]
        for topic, patterns in algorithm_topics:
            if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
                return f"{process}:{topic}"
        tokens = re.findall(r"[a-z][a-z0-9+#]*|[\u4e00-\u9fff]{2,8}", text)
        stop_words = {"给定", "请实现", "说明", "并", "以及", "如何", "一个", "返回", "问题", "时间复杂度", "solution"}
        normalized = " ".join(sorted({token for token in tokens if token not in stop_words}))
        return f"{process}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:20]}" if normalized else ""

    def attach_db(self, db: Database) -> None:
        self.db = db
        persisted = db.list_questions()
        # An initialized database is authoritative even when it currently has
        # zero active questions (for example after an explicit prune).
        self.items = self._dedupe(persisted)

    def reload(self) -> int:
        if self.db is not None:
            self.items = self._dedupe(self.db.list_questions())
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
        refs = []
        if source.get("url"):
            refs.append(str(source["url"]))
        if source_id and str(source_id) not in refs:
            refs.append(str(source_id))
        return refs

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
        scoped = [item for item in self.items if item.get("process_type") == process]
        if mode == "algorithm":
            scoped = [item for item in self.items if item.get("process_type") in {process, "技术面"}]
        # Keep a useful fallback for a newly introduced scene with no data, but
        # never mix unrelated scenes when the requested stage has candidates.
        candidates: list[tuple[float, dict[str, Any]]] = []
        for item in (scoped or self.items):
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
