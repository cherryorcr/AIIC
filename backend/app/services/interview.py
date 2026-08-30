from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.models import Feedback
from app.services.model_router import ModelRouter
from app.services.prompts import evaluation_prompt, question_prompt, policy_for
from app.services.rag import GraphRAGService
from app.services.sandbox import SandboxService
from app.storage.db import Database


def feedback_schema(mode: str) -> dict[str, Any]:
    """JSON Schema shared by model output validation and API normalization."""
    dimensions = policy_for(mode)["dimensions"]
    return {
        "type": "object",
        "required": ["scores", "evidence_quotes", "strengths", "improvements", "better_answer", "next_action"],
        "properties": {
            "scores": {
                "type": "object",
                "required": dimensions,
                "properties": {dimension: {"type": "number", "minimum": 0, "maximum": 5} for dimension in dimensions},
                "additionalProperties": False,
            },
            "evidence_quotes": {"type": "array", "items": {"type": "string"}},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "improvements": {"type": "array", "items": {"type": "string"}},
            "better_answer": {"type": "string"},
            "next_question": {"type": ["string", "null"]},
            "next_action": {"type": "string"},
            "source_refs": {"type": "array", "items": {"type": "string"}},
            "group_phase": {"type": "string"},
            "group_reaction": {"type": "object"},
        },
        "additionalProperties": True,
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InterviewService:
    def __init__(self, db: Database, rag: GraphRAGService, router: ModelRouter, sandbox: SandboxService):
        self.db = db
        self.rag = rag
        self.router = router
        self.sandbox = sandbox

    async def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = f"sess-{uuid.uuid4().hex}"
        mode = payload["mode"]
        matched = self.rag.match(
            mode=mode,
            role=payload.get("role", ""),
            job_text=payload.get("job_text", ""),
            profile=payload.get("user_profile", {}),
            difficulty=payload.get("difficulty", "medium"),
        )
        questions = matched.get("questions") or []
        if not questions:
            raise ValueError("题库暂无可用题目")
        question = dict(questions[0])
        question_source_id = str(question.get("question_id") or "")
        matched["job_text"] = payload.get("job_text", "")
        generated = await self.router.complete(
            "question",
            question_prompt(mode, payload.get("role", ""), payload.get("user_profile", {}), matched),
            session_id,
            max_tokens=256,
        )
        if generated.get("ok") and generated.get("text", "").strip():
            question["question"] = generated["text"].strip()
            question["source_question_id"] = question_source_id
            question["personalized"] = True
            question["generation_provider"] = generated.get("provider") or "strong_model"
            question["personalization_basis"] = [
                skill for skill in (question.get("skills") or matched.get("matched_skills") or []) if str(skill).strip()
            ][:4]
        session = {
            "session_id": session_id,
            "user_id": payload.get("user_id"),
            "job_id": payload.get("job_id"),
            "mode": mode,
            "role": payload.get("role", ""),
            "job_text": payload.get("job_text", ""),
            "user_profile": payload.get("user_profile", {}),
            "difficulty": payload.get("difficulty", "medium"),
            "matched_skills": matched.get("matched_skills", []),
            "current_question": question,
            "status": "questioning",
            "created_at": now(),
        }
        if session.get("user_id"):
            if not self.db.get_user(session["user_id"]):
                self.db.create_temp_user(session["user_id"])
            self.db.save_user_profile(session["user_id"], session["user_profile"])
        self.db.save_session(session)
        return {
            "session_id": session_id,
            "user_id": session.get("user_id"),
            "job_id": session.get("job_id"),
            "mode": mode,
            "role": session["role"],
            "matched_skills": session["matched_skills"],
            "question_id": question["question_id"],
            "question": question["question"],
            "why_this_question": self._why(question, session["matched_skills"], policy_for(mode)["name"]),
            "source_refs": question.get("source_refs", []),
            "tests": question.get("tests", []),
            "status": "questioning",
        }

    def match(self, session_id: str, filters: dict[str, Any]) -> dict[str, Any]:
        session = self.db.get_session(session_id)
        if not session:
            raise KeyError("session_not_found")
        matched = self.rag.match(
            mode=session["mode"], role=session["role"], job_text=session["job_text"],
            profile=session["user_profile"], difficulty=filters.get("difficulty", "medium"),
        )
        return {"session_id": session_id, **matched}

    async def answer(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.db.get_session(session_id)
        if not session:
            raise KeyError("session_not_found")
        question = session.get("current_question") or {}
        revision_of = str(payload.get("revision_of") or "").strip() or None
        answer_mode = str(payload.get("answer_mode") or "answer")
        parent_turn = None
        if revision_of:
            parent_turn = self.db.get_turn(revision_of, session_id)
            if not parent_turn or not parent_turn.get("feedback"):
                raise ValueError("revision_turn_not_found")
            if payload["question_id"] != parent_turn.get("question_id"):
                raise ValueError("revision_question_mismatch")
            # The current session may already point at a follow-up question;
            # revisions stay attached to the original question and its rubric.
            question = self.db.get_question(str(parent_turn["question_id"]), include_inactive=True) or {
                "question_id": parent_turn["question_id"],
                "question": parent_turn.get("question_text", ""),
                "rubric": policy_for(session["mode"])["dimensions"],
                "follow_ups": [],
            }
            question["question_id"] = question.get("question_id") or question.get("id")
            question["question"] = parent_turn.get("question_text") or question.get("question", "")
        elif payload["question_id"] != question.get("question_id"):
            # A client can lose the response after the server has committed a
            # turn (for example when a model call outlives a proxy timeout)
            # and then replay the same POST.  Treat an already evaluated
            # session/question pair as idempotent and return its persisted
            # result rather than surfacing question_id_not_current.
            existing = self.db.get_turn_by_question(session_id, payload["question_id"])
            if existing and existing.get("feedback"):
                return {
                    "turn_id": existing["id"],
                    "session_id": session_id,
                    "question_id": payload["question_id"],
                    "feedback": existing["feedback"],
                    "next_question": session.get("current_question"),
                    "algorithm_result": existing.get("algorithm_result"),
                }
            raise ValueError("question_id_not_current")
        answer_text = payload.get("answer_text", "").strip()
        if not answer_text and not payload.get("code"):
            raise ValueError("answer_empty")
        algorithm_result = None
        if session["mode"] == "algorithm" and payload.get("code"):
            algorithm_result = self.sandbox.run(payload["code"], payload.get("tests") or [])
        turn_id = f"turn-{uuid.uuid4().hex}"
        self.db.save_turn({
            "turn_id": turn_id, "session_id": session_id, "question_id": payload["question_id"],
            "question_text": question.get("question", ""),
            "answer_text": answer_text, "code": payload.get("code"), "language": payload.get("language", "python"),
            "parent_turn_id": revision_of,
            "answer_mode": answer_mode,
            "algorithm_result": algorithm_result,
        })
        rubric = question.get("rubric") or policy_for(session["mode"])["dimensions"]
        evaluation_answer = answer_text
        if parent_turn and parent_turn.get("answer_text"):
            evaluation_answer = (
                f"原回答（仅作上下文）：\n{parent_turn['answer_text']}\n\n"
                f"本次修改/补充回答：\n{answer_text}"
            )
        generated = await self.router.complete(
            "evaluate",
            evaluation_prompt(session["mode"], question.get("question", ""), evaluation_answer, session["user_profile"], rubric),
            session_id,
            response_schema=feedback_schema(session["mode"]),
            max_tokens=1200,
        )
        feedback = self._fallback_feedback(session["mode"], answer_text, rubric, algorithm_result)
        if generated.get("ok"):
            parsed = self.router.parse_json(generated.get("text", ""))
            if parsed:
                feedback.update({key: parsed[key] for key in feedback.keys() if key in parsed})
        feedback = Feedback.model_validate(feedback).model_dump()
        self.db.save_feedback(turn_id, feedback)

        # A revision is a second pass over the same prompt. Keep the interview
        # cursor where it was so the candidate can continue the existing
        # follow-up flow instead of being sent backwards.
        next_question = session.get("current_question") if revision_of else self._next_question(session, question)
        session["current_question"] = next_question
        session["status"] = "follow_up" if next_question and next_question.get("is_follow_up") else "questioning"
        self.db.save_session(session)
        # Keep a durable, up-to-date report snapshot for the history page.  A
        # stable report ID makes this an idempotent upsert after every turn.
        if session.get("user_id"):
            turns = self.db.list_turns(session_id)
            values = []
            for turn in turns:
                scores = (turn.get("feedback") or {}).get("scores") or {}
                values.extend(float(value) for value in scores.values() if isinstance(value, (int, float)))
            self.db.save_report(
                session["user_id"],
                session_id,
                {
                    "title": f"{session.get('role', '岗位')} · {session.get('mode', 'technical')}",
                    "turn_count": len(turns),
                    "average_score": round(sum(values) / len(values), 2) if values else None,
                    "last_feedback": feedback,
                },
                report_id=f"report-{session_id}",
            )
        return {
            "turn_id": turn_id,
            "session_id": session_id,
            "question_id": payload["question_id"],
            "feedback": feedback,
            "next_question": next_question,
            "algorithm_result": algorithm_result,
        }

    def summary(self, session_id: str) -> dict[str, Any]:
        session = self.db.get_session(session_id)
        if not session:
            raise KeyError("session_not_found")
        turns = self.db.list_turns(session_id)
        score_values = []
        for turn in turns:
            scores = (turn.get("feedback") or {}).get("scores") or {}
            score_values.extend(float(x) for x in scores.values() if isinstance(x, (int, float)))
        average = round(sum(score_values) / len(score_values), 2) if score_values else None
        return {"session": session, "turns": turns, "summary": {"turn_count": len(turns), "average_score": average}}

    def complete(self, session_id: str) -> dict[str, Any]:
        """Mark a session complete and persist its final report snapshot."""
        session = self.db.get_session(session_id)
        if not session:
            raise KeyError("session_not_found")
        session["status"] = "completed"
        session["current_question"] = None
        self.db.save_session(session)
        turns = self.db.list_turns(session_id)
        # Opening a practice screen creates a draft session, but a session
        # without an answer is not a training record and must not create an
        # empty report or a zero-score entry.
        if not turns:
            return {"session": session, "report": None, "turn_count": 0, "status": "completed"}
        values = [
            float(value)
            for turn in turns
            for value in ((turn.get("feedback") or {}).get("scores") or {}).values()
            if isinstance(value, (int, float))
        ]
        report = None
        if session.get("user_id"):
            report = self.db.save_report(
                session["user_id"], session_id,
                {
                    "title": f"{session.get('role', '岗位')} · {session.get('mode', 'technical')}",
                    "turn_count": len(turns),
                    "average_score": round(sum(values) / len(values), 2) if values else None,
                    "status": "completed",
                },
                report_id=f"report-{session_id}",
            )
        return {"session": session, "report": report, "turn_count": len(turns), "status": "completed"}

    @staticmethod
    def _why(question: dict[str, Any], matched_skills: list[str], mode_name: str) -> str:
        skills = "、".join(question.get("skills") or matched_skills[:3]) or "岗位通用能力"
        return f"该题属于{mode_name}，重点考察 {skills}，并可结合用户提供的项目经历回答。"

    def _next_question(self, session: dict[str, Any], question: dict[str, Any]) -> dict[str, Any] | None:
        follow_ups = question.get("follow_ups") or []
        if follow_ups and session["mode"] in {"stress", "behavioral", "technical", "algorithm", "group"}:
            if not question.get("is_follow_up"):
                follow_up_index = 0
            else:
                match = re.search(r"-f(\d+)$", str(question.get("question_id") or ""))
                follow_up_index = int(match.group(1)) if match else 0
            if follow_up_index < len(follow_ups):
                return {
                    **question,
                    "question": follow_ups[follow_up_index],
                    "question_id": f"{question.get('question_id').split('-f')[0]}-f{follow_up_index + 1}",
                    "is_follow_up": True,
                }
        matched = self.rag.match(
            mode=session["mode"], role=session["role"], job_text=session["job_text"], profile=session["user_profile"],
        )
        for candidate in matched.get("questions", []):
            if candidate.get("question_id") != question.get("question_id"):
                return candidate
        return None

    @staticmethod
    def _fallback_feedback(mode: str, answer: str, rubric: list[str], algorithm_result: dict[str, Any] | None) -> dict[str, Any]:
        sentences = [x.strip() for x in re.split(r"[。！？!?\n]", answer) if x.strip()]
        quote = sentences[0][:120] if sentences else "未提供可引用的回答证据"
        has_evidence = any(word in answer for word in ("我", "项目", "结果", "提升", "%", "数据"))
        dims = policy_for(mode)["dimensions"]
        base = 3.0 if len(answer) >= 30 else 2.0
        scores = {dimension: base for dimension in dims}
        if has_evidence:
            for dimension in dims:
                if dimension in {"evidence", "ownership", "star", "authenticity"}:
                    scores[dimension] = min(5.0, base + 1.0)
        if algorithm_result and algorithm_result.get("status") == "passed":
            for dimension in dims:
                if dimension in {"algorithm", "code_quality", "correctness"}:
                    scores[dimension] = 5.0
        result = {
            "scores": scores,
            "evidence_quotes": [quote],
            "strengths": ["回答包含可进一步展开的具体信息。" if answer else ""],
            "improvements": [f"请针对评分维度“{rubric[0] if rubric else dims[0]}”补充事实、过程和结果证据。"],
            "better_answer": "可以按背景—行动—结果—复盘组织回答；未知信息不要补写。",
            "next_question": None,
            "next_action": "建议根据反馈重新回答一次，再进入下一题。",
            "source_refs": [],
        }
        if mode == "group":
            result.update(
                {
                    "group_phase": "观点陈述",
                    "group_reaction": {
                        "speaker": "模拟队友 A",
                        "role": "推进者",
                        "message": "我同意先统一目标，但建议把资源约束量化后再比较方案。",
                        "prompt": "请回应队友并推动小组形成一个可执行的判断标准。",
                    },
                }
            )
        return result
