# 面试陪练 MVP 共享契约

> 本文件保留前端和后端已使用的最小共享字段及历史接口。完整的资源列表、错误码、版本策略和示例见 `docs/api-design.md`；用例和状态机见 `docs/use-case-design.md` 与 `docs/system-detailed-design.md`。

## 用户与工作区

```text
POST /api/v1/auth/register  # display_name, email, password；升级当前临时用户
POST /api/v1/auth/login     # email, password
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/workspace/overview
```

浏览器使用 HttpOnly Cookie，服务端从登录态推导 `user_id`。请求体或 `X-User-Id` 中的用户 ID 不参与授权。未注册用户仍有独立临时工作区；注册后现有资料、岗位和训练历史保留。

## Session

```json
{
  "session_id": "local-uuid",
  "mode": "technical|algorithm|behavioral|stress|case|research|hr|group",
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
