# AIIC 需求追踪矩阵

## 1. 使用说明

需求 ID 是跨 Product Memo、用例、实现和测试的稳定索引。状态以当前仓库为准：`implemented` 已有实现，`partial` 已有 MVP 实现但有生产限制，`planned` 尚未实现，`needs_validation` 需要真实用户或人工评测。

## 2. 功能需求

| ID | 需求 | 用例 | 主要实现 | 验证 | 状态 |
| --- | --- | --- | --- | --- | --- |
| FR-01 | 用户可匿名建立隔离工作区 | UC-01 | `main.py` auth/session、`db.py` | `test_user_profile_job_favorite_history_and_report_persist` | implemented |
| FR-02 | 用户可注册、登录、注销 | UC-02 | `auth.py`、`main.py` | `test_registered_accounts_keep_profiles_jobs_readiness_and_sessions_isolated` | implemented |
| FR-03 | 用户可维护个人背景 | UC-03 | `/profile`、`user_profiles` | 同上 | implemented |
| FR-04 | 用户可上传并确认简历/JD | UC-04 | `documents.py`、`/documents/*` | `test_candidate_document_upload_parse_confirm_and_ownership` | implemented |
| FR-05 | 系统可抽取和归一化岗位技能 | UC-05 | `rag.py`、`/jobs/extract-skills` | `test_rag_extracts_normalized_skills_and_reports_recall` | implemented |
| FR-06 | 系统可按岗位、技能、场景匹配题目 | UC-05/06 | `GraphRAGService.match` | `test_match_preview_does_not_create_training_session` | implemented |
| FR-07 | 用户可选择八类面试场景 | UC-06/07 | `SCENE_POLICIES`、`/scenes` | `test_start_and_answer`、场景枚举 | implemented |
| FR-08 | 用户可提交文字回答并获得结构化反馈 | UC-07 | `InterviewService.answer` | `test_start_and_answer` | implemented |
| FR-09 | 用户可重答、补充和继续追问 | UC-07/09 | `revision_of`、`_next_question` | `test_revision_creates_child_turn_without_advancing_cursor` | implemented |
| FR-10 | 用户可运行算法题代码 | UC-08 | `SandboxService`、`/algorithm/run` | `test_algorithm_runner_rejects_forbidden_code`、超时测试 | partial |
| FR-11 | 用户可完成会话并生成报告 | UC-10 | `complete`、`reports` | `test_session_can_be_completed_and_reported` | implemented |
| FR-12 | 用户可浏览、收藏和加入题库训练 | UC-11 | `/questions`、favorites | `test_algorithm_question_and_knowledge_management` | implemented |
| FR-13 | 用户可查看准备度和训练历史 | UC-12 | `/workspace/overview`、`/history` | readiness/history tests | implemented |
| FR-14 | 管理员可导入、审核、软删除题目 | UC-13 | `/admin/knowledge/*`、`manage_knowledge.py` | knowledge management tests | implemented |
| FR-15 | 系统统一路由本地/强模型并记录 fallback | UC-14 | `ModelRouter`、`model_invocations` | `test_model_fallback_is_recorded_with_telemetry` | implemented |
| FR-16 | 反馈只能引用用户原回答证据 | UC-07 | Prompt/schema/fallback 约束 | 人工评测集待建立 | needs_validation |
| FR-17 | 所有公开数据保留来源和许可 | UC-11/13 | approved dataset、sources | `report-source.md`、导入校验 | implemented |

## 3. 非功能需求

| ID | 需求 | 设计/实现 | 验证方式 | 状态 |
| --- | --- | --- | --- | --- |
| NFR-01 | API 失败不丢失用户输入 | 前端草稿、后端先保存 Turn、POST 禁止盲重试 | 超时和重放测试 | implemented |
| NFR-02 | 用户资源隔离 | HttpOnly Cookie + 服务端 owner 校验 + 404 防枚举 | 跨账户测试 | implemented |
| NFR-03 | 模型供应商可替换 | Model Router + OpenAI-compatible adapter | provider fallback 测试 | implemented |
| NFR-04 | 题目可追溯 | source/license/version/hash/confidence | 来源台账审查 | implemented |
| NFR-05 | 算法代码受资源限制 | AST、audit hook、timeout、RLIMIT | 违规/超时/资源测试 | partial |
| NFR-06 | 生产部署可复现 | CPU/GPU Compose、Dockerfile、runbook | 双主机 smoke test | implemented |
| NFR-07 | 多实例高并发 | PostgreSQL + Redis + worker + runner | 压测和故障演练 | planned |
| NFR-08 | 语音/视频扩展不影响文字闭环 | 通道接口预留 | 后续设计评审 | planned |

## 4. 需求到交付物

| 交付物 | 覆盖需求 |
| --- | --- |
| `docs/use-case-design.md` | FR-01 至 FR-17 的用户行为和异常流程 |
| `docs/system-overview-design.md` | NFR-02、NFR-03、NFR-06、NFR-08 |
| `docs/system-detailed-design.md` | FR-05 至 FR-15、NFR-01 至 NFR-05 |
| `docs/api-design.md` | 前后端接口字段、状态和兼容策略 |
| `docs/test-plan.md` | 功能、契约、安全、性能和用户验收 |
| `docs/product-memo.md` | 需求假设、范围、迭代原因和下一步验证 |
