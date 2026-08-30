# AIIC 系统详细设计

## 1. 详细设计基线

本文以当前仓库的 FastAPI、React、SQLite/PostgreSQL 兼容层和 Docker Compose 为实现基线。`implemented` 表示当前代码已存在；`planned` 表示为下一阶段保留的工程边界。

## 2. 前端详细设计

### 2.1 页面与路由

| 路由 | 组件/职责 | 主要 API |
| --- | --- | --- |
| `/` | `DashboardPage`，准备度、最近训练、建议 | `/workspace/overview`、`/history` |
| `/practice` | `PracticePage`，场景选择、提问、回答、追问、算法代码 | `/scenes`、`/sessions`、`/turns`、`/algorithm/run` |
| `/match` | `MatchPage`，岗位、技能覆盖、缺口、题目匹配 | `/jobs`、`/matches` |
| `/materials` | `MaterialsPage`，上传、解析、人工确认简历/JD | `/documents/*`、`/profile`、`/jobs` |
| `/questions` | `QuestionBankPage`，题库搜索、详情、收藏、加入训练 | `/questions`、`/favorites`、`/sessions` |
| `/reports` | `ReportsPage`，历史、摘要和反馈 | `/history`、`/reports`、`/sessions/{id}` |
| `/account`、`/settings` | 账户和设置入口 | `/auth/*`、`/auth/me` |

### 2.2 前端状态

训练页面状态分为四类：

- **Session state**：`sessionId`、`activeMode`、当前问题、下一题、已提交状态。
- **Answer state**：文字回答、代码、运行结果、重答引用 `revisionOf`。
- **Feedback state**：分数、证据、优点、改进、下一步动作和群面反应。
- **UI state**：加载、提交、错误、面板交换、移动端导航。

状态转换：

```text
idle → starting → questioning → submitting → feedback
                                  │             ├─ retry/supplement → submitting
                                  │             ├─ next → questioning
                                  │             └─ complete → completed
algorithm: questioning → running_code → code_result → submitting → feedback
```

### 2.3 网络层策略

- 所有请求通过 `frontend/src/api.ts`，统一使用 `credentials: include`。
- 默认请求超时 12 秒，模型生成和回答评价为 120 秒且禁止盲目重试 POST。
- 408、429 和 5xx 可有限重试；404、422 作为契约错误直接返回。
- 前端不保存 API key；localStorage 仅保存按活动用户 ID 隔离的降级缓存。
- 当前 Nginx 将 `/api/` 反向代理到 backend；SSE 端点需关闭代理缓冲并保持长读超时。

### 2.4 资料确认交互

上传解析后的结果不是最终事实。前端显示 `parsed_json` 的草稿字段，用户编辑后调用 confirm 接口，后端才更新规范 Profile 或 Job。删除文档只删除文档记录，不自动删除已确认的规范资料，避免误删用户工作区。

## 3. 后端详细设计

### 3.1 请求链路

```text
FastAPI route
  → resolve server-side user/session owner
  → validate Pydantic schema
  → domain service
  → repository/model adapter/sandbox
  → normalize response
  → persist audit/telemetry
```

`backend/app/main.py` 负责路由、鉴权和边界错误转换；`services/*` 负责领域行为；`storage/db.py` 负责事务和跨 SQLite/PostgreSQL 的兼容执行。

### 3.2 会话状态机

| 状态 | 进入条件 | 可执行动作 | 离开条件 |
| --- | --- | --- | --- |
| `created` | 会话记录建立 | 生成首题、查看匹配 | 首题可用后进入 `questioning` |
| `questioning` | 有当前题 | 查看题目、提交回答、跳过 | 提交后进入 `evaluating` |
| `evaluating` | Turn 已保存 | 模型评价、代码运行结果合并 | Feedback 保存后进入 `follow_up` 或 `questioning` |
| `follow_up` | 当前题有追问 | 回答追问、重答原题 | 追问结束后进入 `questioning` 或 `completed` |
| `completed` | 用户结束或无下一题 | 查看报告、历史 | 不再推进当前题 |

重答不会将游标退回原题：以 `revision_of` 建立父子 Turn 关系，评价仍使用原题 Rubric。

### 3.3 GraphRAG 详细流程

1. `extract_skills()` 从 role、JD、profile 中识别技能和别名。
2. `normalize_skill()` 统一 `py`/`python3`、`postgres`/`postgresql` 等别名。
3. `GraphRAGService.match()` 按 `process_type`、岗位、难度和技能关系过滤。
4. 对题目文本、技能、岗位和 rubric 生成轻量向量；当前无 embedding 服务时使用确定性哈希向量。
5. 计算余弦相似度和词法重叠，执行 `_dedupe()` 语义去重。
6. 按 source confidence、匹配技能数和相似度排序。
7. 返回 `matched_skills`、题目、`source_refs` 和置信度。

目标迁移路径是以同一 Repository 接口替换为 PostgreSQL + pgvector；不改变 API 输出。

### 3.4 场景策略与 Rubric

场景配置集中在 `services/prompts.py`：

| mode | 评分维度 |
| --- | --- |
| technical | correctness、complexity、tradeoff、debugging |
| algorithm | problem_understanding、algorithm、complexity、code_quality |
| behavioral | star、ownership、evidence、reflection |
| stress | stability、evidence、conciseness、adaptability |
| case | decomposition、metrics、hypothesis、validation |
| research | hypothesis、experiment、limitations、critical_thinking |
| hr | motivation、fit、communication、authenticity |
| group | problem_framing、collaboration、consensus、time_management |

新增场景只需增加 policy、题库 `process_type`、Prompt 和反馈 schema，InterviewService 不应复制一套会话流程。

### 3.5 Model Router

标准调用：

```python
await router.complete(
    task="question|evaluate|extract|follow_up",
    messages=[...],
    session_id=session_id,
    response_schema=optional_json_schema,
    max_tokens=1200,
)
```

处理顺序：

1. 根据 task 选择 provider 列表；当前配置包含 local 和 strong 两类 OpenAI-compatible endpoint。
2. 发送带超时的请求，针对网络错误、429、5xx 执行有限重试和退避。
3. 记录 provider、model、route、耗时、tokens、状态、错误名和 fallback 原因。
4. 对结构化输出执行 JSON 解析和一次 repair；失败时返回 `ok=false`，由领域服务提供确定性 fallback。
5. 健康检查返回 provider 状态和最后错误，不阻塞业务服务启动。

### 3.6 评价结果约束

`Feedback` 至少包括 `scores`、`evidence_quotes`、`strengths`、`improvements`、`better_answer` 和 `next_action`。服务端通过 `feedback_schema(mode)` 校验维度和 0-5 范围，再保存到 Turn。模型输出中的证据必须在用户答案中可定位；无法证明时显示缺失证据。

### 3.7 算法沙箱

当前 `SandboxService` 在临时目录创建 harness：

- AST 级别拒绝危险导入、危险调用、双下划线名称和反射属性。
- 只暴露有限 builtins 和允许导入。
- audit hook 拒绝 socket、子进程、系统命令和动态库加载。
- Linux 使用 `RLIMIT_CPU`、`RLIMIT_AS`、`RLIMIT_NPROC`、`RLIMIT_FSIZE` 和 `RLIMIT_NOFILE`。
- wall timeout、输出字节数和固定测试用例由配置控制。
- Windows 开发环境使用无窗口、独立进程组；生产应迁移到 Linux runner 容器。

**生产边界**：语言级策略不等同于操作系统级隔离。开放公网代码执行前，必须使用独立非 root runner、禁网容器、只读文件系统、seccomp/AppArmor 或 nsjail，并禁止 Docker Socket 挂载。

## 4. 数据访问设计

业务代码只通过 `Database` 方法访问持久化数据。关键事务：

1. 创建会话：写入 Session，保存当前题目和用户画像。
2. 提交回答：写 Turn，写 Feedback，更新 Session 游标，upsert 报告快照。
3. 确认资料：写文档确认状态，再更新 Profile 或 Job。
4. 导入题库：来源、题目、技能、关系在一个事务中幂等写入。
5. 注册账户：用户升级、密码哈希和会话令牌在同一业务操作中完成。

## 5. 错误模型

| 错误 | HTTP | 前端处理 |
| --- | --- | --- |
| `session_not_found` | 404 | 返回会话不存在，不暴露跨用户资源 |
| `document_too_large` | 413 | 提示压缩或手工输入 |
| `unsupported_document_type` | 415 | 提示支持的文件类型 |
| `answer_empty` | 400 | 保留草稿，要求输入 |
| `question_id_not_current` | 409/400 | 刷新会话状态后重试 |
| `model_timeout` | 503 或降级响应 | 显示降级和重试入口 |
| `sandbox timeout` | 200 + status=timeout | 展示超时，不阻塞会话 |
| `email_or_password_invalid` | 401 | 不区分邮箱是否存在 |

## 6. 配置与密钥

配置来源为环境变量，参考 `.env.example` 和 `backend/.env.example`：

- `DATABASE_URL`：生产 PostgreSQL DSN。
- `INTERVIEW_DATASET_PATH`：活动题库路径，默认 `approved-dataset.json`。
- `LOCAL_MODEL_*`、`STRONG_MODEL_*`：模型网关地址、模型名和服务端密钥。
- `MODEL_TIMEOUT_SECONDS`、`MODEL_MAX_RETRIES`：模型请求策略。
- `AUTH_COOKIE_SECURE`、`AUTH_SESSION_DAYS`：会话 Cookie 策略。
- `SANDBOX_*`：算法资源和输出限制。

密钥不能写入源码、前端 bundle、Dockerfile、数据库或普通日志；部署文件只提供变量名和示例占位符。

## 7. 可观测性

每次模型调用关联 `session_id` 和内部 `request_id`；记录 provider、model、任务、耗时、token、估算成本、状态和 fallback。普通日志不记录完整回答和原始简历；调试采样必须脱敏并设置保留时间。

## 8. 详细设计验收

- API 响应字段与 `docs/api-design.md`、`docs/contracts.md` 一致。
- 同一请求的模型失败不会丢失已保存回答。
- 重答不会推进两次题目。
- 用户确认资料前，AI 抽取结果不写入规范 Profile/Job。
- 题目来源、许可和数据状态可在题目详情追溯。
- 算法超时、违规和异常均有结构化结果。
