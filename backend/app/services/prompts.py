from __future__ import annotations

import json
from typing import Any


SCENE_POLICIES: dict[str, dict[str, Any]] = {
    "technical": {"name": "技术面", "dimensions": ["correctness", "complexity", "tradeoff", "debugging"]},
    "algorithm": {"name": "算法面", "dimensions": ["problem_understanding", "algorithm", "complexity", "code_quality"]},
    "behavioral": {"name": "行为面", "dimensions": ["star", "ownership", "evidence", "reflection"]},
    "stress": {"name": "压力面", "dimensions": ["stability", "evidence", "conciseness", "adaptability"]},
    "case": {"name": "案例面", "dimensions": ["decomposition", "metrics", "hypothesis", "validation"]},
    "research": {"name": "科研面", "dimensions": ["hypothesis", "experiment", "limitations", "critical_thinking"]},
    "hr": {"name": "HR面", "dimensions": ["motivation", "fit", "communication", "authenticity"]},
}


def policy_for(mode: str) -> dict[str, Any]:
    return SCENE_POLICIES.get(mode, SCENE_POLICIES["technical"])


def question_prompt(mode: str, role: str, profile: dict[str, Any], matched: dict[str, Any]) -> list[dict[str, str]]:
    policy = policy_for(mode)
    context = {
        "role": role,
        "profile": profile,
        "matched_skills": matched.get("matched_skills", []),
        "candidate_question": (matched.get("questions") or [{}])[0].get("question", ""),
        "dimensions": policy["dimensions"],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是面试陪练系统的出题器。只能使用用户提供的经历和检索到的技能，不能编造经历。"
                "输出一道适合当前场景的问题，并在问题中体现考察目标。只输出问题文本。"
            ),
        },
        {"role": "user", "content": f"场景={policy['name']}\n{json.dumps(context, ensure_ascii=False)}"},
    ]


def evaluation_prompt(
    mode: str,
    question: str,
    answer: str,
    profile: dict[str, Any],
    rubric: list[str],
) -> list[dict[str, str]]:
    policy = policy_for(mode)
    payload = {
        "mode": policy["name"],
        "dimensions": policy["dimensions"],
        "question": question,
        "answer": answer,
        "profile": profile,
        "rubric": rubric,
    }
    schema = {
        "scores": {dimension: "0-5" for dimension in policy["dimensions"]},
        "evidence_quotes": ["只能引用回答原句"],
        "strengths": ["具体优点"],
        "improvements": ["可执行改进"],
        "better_answer": "不编造经历的回答结构示例",
        "next_question": "可选追问",
        "next_action": "重新回答或进入下一题",
    }
    return [
        {
            "role": "system",
            "content": "你是结构化面试评分器。不得补写用户没有说过的事实；缺失证据必须明确指出。只输出合法 JSON。",
        },
        {"role": "user", "content": json.dumps({"input": payload, "output_schema": schema}, ensure_ascii=False)},
    ]

