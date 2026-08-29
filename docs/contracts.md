# 面试陪练 MVP 共享契约

## Session

```json
{
  "session_id": "local-uuid",
  "mode": "technical|behavioral|stress|case|research|hr|algorithm",
  "role": "软件开发/算法",
  "job_text": "脱敏 JD",
  "user_profile": {
    "projects": ["项目经历摘要"],
    "skills": ["Python", "SQL"]
  },
  "question_id": "Q001",
  "question": "当前问题",
  "turn_index": 1
}
```

## `POST /api/interview/start`

请求：`mode`、`role`、`job_text`、`user_profile`、可选 `difficulty`。

响应：

```json
{
  "session_id": "local-uuid",
  "matched_skills": ["数据结构", "复杂度分析"],
  "question_id": "Q001",
  "question": "请解释你在一个项目中如何选择数据结构。",
  "why_this_question": "对应 JD 中的算法基础要求，并与用户项目证据相关。",
  "source_refs": ["github-kdn-interviews"]
}
```

## `POST /api/interview/answer`

请求：`session_id`、`question_id`、`answer_text`；算法题额外传 `code` 和 `language`。

响应：

```json
{
  "scores": {
    "relevance": 0,
    "evidence": 0,
    "structure": 0,
    "technical": 0,
    "clarity": 0
  },
  "evidence_quotes": ["用户回答中的原句"],
  "strengths": ["具体优点"],
  "improvements": ["下一次可执行的改进"],
  "better_answer": "在不编造经历的前提下给出结构示例",
  "next_question": "基于薄弱项的追问",
  "next_action": "建议用户重新回答或进入下一题",
  "source_refs": ["github-yangshun-handbook"]
}
```

## 失败与降级

- LLM 超时：返回可重试状态，不丢失当前输入。
- JSON 解析失败：服务端尝试一次修复；仍失败则展示纯文本，并记录错误。
- 检索无结果：使用自编/有许可的基础题，不展示虚假的来源或频次。
- ASR 失败：保留文字输入入口。
- 代码运行超时：终止进程并返回固定提示，不阻塞整场会话。

