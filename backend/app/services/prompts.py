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
    "group": {"name": "群面", "dimensions": ["problem_framing", "collaboration", "consensus", "time_management"]},
}


def policy_for(mode: str) -> dict[str, Any]:
    return SCENE_POLICIES.get(mode, SCENE_POLICIES["technical"])


def question_prompt(mode: str, role: str, profile: dict[str, Any], matched: dict[str, Any]) -> list[dict[str, str]]:
    policy = policy_for(mode)
    context = {
        "role": role,
        "job_description": matched.get("job_text", ""),
        "profile": profile,
        "matched_skills": matched.get("matched_skills", []),
        "candidate_question": (matched.get("questions") or [{}])[0].get("question", ""),
        "candidate_question_source_id": (matched.get("questions") or [{}])[0].get("question_id", ""),
        "candidate_question_rubric": (matched.get("questions") or [{}])[0].get("rubric", []),
        "dimensions": policy["dimensions"],
    }
    instruction = (
        "你是无领导小组讨论的主持人。请从检索到的题目出发，生成一个适合 4-6 人、8-12 分钟讨论的开放问题。"
        "问题必须有明确背景、讨论目标和约束，不能编造用户经历；只输出问题文本，不输出角色、答案或 Markdown。"
        if mode == "group"
        else "你是面试陪练系统的出题器。只能使用用户提供的 JD、简历明确证据和检索到的真实题库题目，不能编造经历。"
        "保留检索题目的核心考察目标和难度，结合岗位真实职责与候选人背景改写成一道个性化问题；"
        "如果简历没有相关证据，就设计核验候选人能力的问题，不要假设候选人做过某事。只输出问题文本。"
    )
    return [
        {
            "role": "system",
            "content": instruction,
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
    if mode == "group":
        schema.update(
            {
                "group_phase": "观点陈述/交叉讨论/总结共识",
                "group_reaction": {
                    "speaker": "模拟队友A",
                    "role": "数据派/推进者/质疑者",
                    "message": "一段模拟队友发言",
                    "prompt": "要求候选人回应的动作",
                },
            }
        )
    return [
        {
            "role": "system",
            "content": (
                "你是结构化面试评分器。不得补写用户没有说过的事实；缺失证据必须明确指出。只输出合法 JSON。"
                + ("群面还要模拟一名队友的简短发言，并给出候选人下一步应回应的动作。" if mode == "group" else "")
            ),
        },
        {"role": "user", "content": json.dumps({"input": payload, "output_schema": schema}, ensure_ascii=False)},
    ]
