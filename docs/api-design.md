# AIIC API 详细设计

## 1. API 约定

- Base path：`/api/v1`。
- 认证：HttpOnly Cookie `techmatch_session`；也接受服务端到服务端的 Bearer token。
- Content-Type：JSON 接口使用 `application/json`；文件解析使用 `multipart/form-data`。
- 时间：服务端持久化 UTC ISO 8601 字符串，前端按本地时区展示。
- 资源隔离：服务端从会话推导 `user_id`；请求体中的 `user_id` 和 `X-User-Id` 不用于授权。
- 错误：业务错误使用 `{ "detail": "stable_error_code" }`；模型和沙箱还会返回可展示的 `status`。

## 2. 认证与工作区

| 方法 | 路径 | 用途 | 认证 |
| --- | --- | --- | --- |
| POST | `/users/temporary` | 创建临时用户 | 可匿名 |
| POST | `/auth/register` | 注册并升级当前临时用户 | 可匿名 |
| POST | `/auth/login` | 邮箱密码登录 | 可匿名 |
| POST | `/auth/logout` | 撤销当前会话 | 当前会话 |
| GET | `/auth/me` | 获取当前用户和 Profile | 可匿名，缺失时建临时用户 |
| GET | `/workspace/overview` | 获取准备度和最近会话 | 当前会话 |

另有无需鉴权的元信息接口：`GET /scenes` 返回全部 8 个面试场景（`technical`、`algorithm`、`behavioral`、`stress`、`case`、`research`、`hr`、`group`）的 ID、名称和评分维度，前端场景选择由此驱动。`/workspace/overview` 返回的 `readiness.score` 为 0-100 综合准备度（技能覆盖 45% + 档案完整度 30% + 训练得分 25%），无目标岗位时恒为 0。

## 3. 资料与岗位

| 方法 | 路径 | 请求核心字段 | 响应核心字段 |
| --- | --- | --- | --- |
| GET | `/profile` | 无 | `user_id`、`profile` |
| PUT | `/profile` | `skills`、`projects`、`education`、`experience`、`achievements`、`constraints` | 保存后的 Profile |
| POST | `/documents/parse` | 文件 `file`、`kind=resume|job_description` | `document`、`status=needs_confirmation` |
| GET | `/documents` | `limit` | 当前用户文档列表 |
| GET | `/documents/{id}` | 文档 ID | 文档详情 |
| POST | `/documents/{id}/confirm` | `parsed` | 确认后的文档和规范资料 |
| DELETE | `/documents/{id}` | 文档 ID | `status=deleted` |
| GET | `/jobs` | `limit` | 当前用户岗位列表 |
| POST | `/jobs` | `title`、`role`、`jd_text`、`skills` | 保存后的岗位 |
| GET | `/jobs/{id}` | 岗位 ID | 岗位详情 |
| POST | `/jobs/extract-skills` | `jd_text` 或 `job_text` | `skills`、`extractor`、`confidence` |

## 4. 匹配和题库

### 4.1 匹配

`POST /matches` 用于不创建 Session 的预览：

```json
{
  "mode": "technical",
  "role": "后端开发工程师",
  "job_text": "需要 Python、FastAPI、PostgreSQL",
  "user_profile": {
    "skills": ["Python", "SQL"],
    "projects": ["实现过一个 API 服务"]
  },
  "difficulty": "medium",
  "job_id": null
}
```

响应至少包含：

```json
{
  "role": "后端开发工程师",
  "match_score": 66,
  "score_breakdown": {"skill_coverage": 70, "experience": 60, "project_evidence": 55, "direction_fit": 80},
  "score_explanation": "……",
  "score_strengths": [],
  "score_gaps": [],
  "score_source": "strong_model",
  "score_cached": false,
  "scoring_version": "resume-jd-personalized-v2",
  "required_skills": ["python", "fastapi", "postgresql"],
  "profile_matched_skills": ["python"],
  "matched_skills": ["python", "系统设计"],
  "questions": [],
  "question_generation_source": "strong_model",
  "source_confidence": "high"
}
```

评分语义：

- `score_source=strong_model` 表示由强模型按 4 维（技能覆盖 55%、相关经历 20%、项目证据 15%、岗位方向一致性 10%）加权打分；模型不可用时降级为 `deterministic`（仅按技能覆盖率计算）。
- 评分结果按 `(user_id, target_key, input_hash, scoring_version)` 持久化为不可变快照（`match_snapshots` 表）；档案或 JD 内容不变时重复请求命中快照（`score_cached=true`），不重复调用付费模型。`input_hash` 基于规范化后的档案与 JD 计算，剥离 `updated_at` 等易变元数据。
- 强模型评分的同一调用可生成至多 5 道 `personalized_questions`（`questions` 中带 `personalized=true` 与 `personalization_basis`），每道题必须引用检索到的 `source_question_id` 并保留原题 Rubric、测试与来源，防止伪造溯源。传 `job_id` 时以服务端保存的 JD 和档案为准，忽略请求体中的旧档案。

### 4.2 题库

| 方法 | 路径 | 查询参数 | 说明 |
| --- | --- | --- | --- |
| GET | `/questions` | `q`、`process_type`、`skill`、`limit` | 匿名可读的公开题库 |
| GET | `/questions/{id}` | 无 | 题目、技能、Rubric、来源 |
| GET | `/favorites` | `limit` | 当前用户收藏 |
| POST | `/questions/{id}/favorite` | `{ "favorite": true }` | 收藏或取消收藏 |

题目响应必须保留 `source_refs`、`source_type`、`source_license`、`source_version`、`source_confidence` 和 `pii_redacted`（若字段存在）。

## 5. 训练会话

### 5.1 创建

`POST /sessions`：

```json
{
  "mode": "behavioral",
  "role": "后端开发工程师",
  "job_text": "脱敏 JD",
  "user_profile": {"skills": ["Python"], "projects": ["TechMatch"]},
  "difficulty": "medium",
  "job_id": null
}
```

响应：`session_id`、`mode`、`role`、`matched_skills`、`question_id`、`question`、`why_this_question`、`source_refs`、`tests`、`status`。

### 5.2 提交回答

`POST /sessions/{session_id}/turns`：

```json
{
  "question_id": "Q001",
  "answer_text": "我在项目中使用缓存降低接口延迟，并通过压测验证。",
  "answer_mode": "answer",
  "revision_of": null,
  "code": null,
  "language": "python",
  "tests": []
}
```

算法面可以同时提交 `code` 和 `tests`。重答/补充必须设置 `revision_of`（`answer_mode` 取 `retry` 或 `supplement`），且 question ID 必须与父 Turn 相同；修订 Turn 通过 `parent_turn_id` 关联原回答，评分时携带原回答上下文，且不推进当前题目游标。

**幂等重放**：若提交的 `question_id` 不是当前题、但该 (session, question) 已存在评过分的 Turn，服务端直接返回已持久化的结果而不报错——用于客户端网络超时后的安全重放。前端对这两个高延迟 POST 均禁用自动重试。

群面（`mode=group`）的 feedback 额外携带 `group_phase`、`group_reaction` 与 `group_reactions`（2-3 位固定人设模拟队友——推进者、质疑者、数据派——的发言与下一步提示）。

响应：

```json
{
  "turn_id": "turn-...",
  "session_id": "sess-...",
  "question_id": "Q001",
  "feedback": {
    "scores": {"correctness": 4},
    "evidence_quotes": ["我在项目中使用缓存降低接口延迟"],
    "strengths": ["给出了实际行动"],
    "improvements": ["补充缓存失效和一致性策略"],
    "better_answer": "按背景、行动、结果、复盘组织",
    "next_question": null,
    "next_action": "建议重新回答一次",
    "source_refs": []
  },
  "next_question": null,
  "algorithm_result": null
}
```

### 5.3 查询、报告和事件

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/sessions/{id}` | 读取 Session、Turns、（群面）group_messages 和摘要 |
| GET | `/sessions/{id}/summary` | 读取汇总 |
| POST | `/sessions/{id}/advance` | 显式切换到新的根题（跳过已答过的题根） |
| POST | `/sessions/{id}/match` | 会话内按 `filters.difficulty` 重新召回题目 |
| POST | `/sessions/{id}/group/advance` | 群面专用：生成并持久化一条模拟队友自主发言，body `{"interval_seconds": 4-20}`，响应可携带 `next_delay_seconds` 供前端自适应节奏 |
| POST | `/sessions/{id}/complete` | 结束 Session 并生成报告快照 |
| GET | `/sessions/{id}/events` | SSE 事件流；**当前为占位实现**，仅发送一条 `session_status: ready` 事件，流式推送为 planned |
| GET | `/history` | 当前用户训练历史 |
| GET | `/reports` | 当前用户报告列表 |
| GET | `/reports/{id}` | 报告详情 |
| POST | `/reports` | 创建或补充报告 |

## 6. 算法执行

`POST /sessions/{id}/algorithm/run` 请求字段：`question_id`、`code`、`language=python`、`tests`。

`algorithm_result.status` 取值：`passed`、`failed`、`timeout`、`error`、`rejected`、`disabled`、`resource_limited`。即使代码失败，接口也应返回结构化运行结果，不把用户输入丢失。

## 7. 管理 API

生产环境必须提供 `X-Admin-Token`：

```text
GET    /admin/knowledge/stats
GET    /admin/knowledge/items?process_type=算法面&include_inactive=false
GET    /admin/knowledge/sources
POST   /admin/knowledge/evaluate
POST   /admin/knowledge/items
PATCH  /admin/knowledge/items/{question_id}
DELETE /admin/knowledge/items/{question_id}      # 软删除
POST   /admin/knowledge/reload?prune=false
```

## 8. 健康检查

- `GET /health` 和 `GET /api/v1/health`：应用、数据库、题库、模型配置和沙箱开关。
- `GET /api/v1/model/health`：本地/强模型 provider 状态、延迟、错误和 fallback 可用性。
- 前端 Nginx `GET /health`：只表示 frontend 容器存活，不代表 backend 健康。

## 9. 兼容与版本策略

仓库保留 `/api/interview/start` 和 `/api/interview/answer` 作为历史兼容别名；新开发统一使用 `/api/v1/sessions` 和 `/api/v1/sessions/{id}/turns`。破坏性字段变更需要提升 `/api/v2` 或增加版本化 schema，并同步更新前端、契约、用例和测试。
