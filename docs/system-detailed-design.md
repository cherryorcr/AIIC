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

当前实现持久化三个会话状态；创建与评分是同步过程，不单独落库：

| 状态 | 进入条件 | 可执行动作 | 离开条件 |
| --- | --- | --- | --- |
| `questioning` | 会话创建成功且首题可用（创建与首题生成在同一请求内同步完成） | 查看题目、提交回答、`/advance` 换根题、`/match` 重新召回 | 评分后若下一题为追问则进入 `follow_up` |
| `follow_up` | 当前题为追问（`is_follow_up=true`，题目 ID 形如 `{root_id}-f{depth}`） | 回答追问、以 `revision_of` 重答/补充原题 | 回答后回到 `follow_up` 或 `questioning`；`/complete` 进入 `completed` |
| `completed` | 用户调用 `/complete` | 查看报告、历史 | 终态 |

补充语义：

- 追问永远延续当前题目主题；换根题必须显式调用 `POST /sessions/{id}/advance`。模型给出的追问若未锚定回答证据，服务端会自动补充“围绕你刚才提到的……”前缀；无模型时按证据/改进点生成确定性追问，题库静态 `follow_ups` 仅作最终兜底。
- 重答不会将游标退回原题：以 `revision_of` 建立父子 Turn（`parent_turn_id` + `answer_mode`），评价仍使用原题 Rubric，且携带原回答上下文。
- 每次评分后服务端以固定 ID `report-{session_id}` upsert 报告快照；`/complete` 生成终版，零回答会话不生成报告。
- 回答提交幂等：同一 (session, question) 已有评分 Turn 时重放请求直接返回持久化结果。
- 群面：评分反馈经 `_normalize_group_feedback` 保证 2-3 位不同人设队友发言；`POST /group/advance` 在用户不发言时让队友自主推进讨论（禁止同一队友连续发言，`next_delay_seconds` 钳制在 4-20 秒），发言持久化到 `group_messages` 并在会话恢复时回放。

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

1. 根据 task 选择 provider 列表；当前配置包含 local 和 strong 两类 OpenAI-compatible endpoint。抽取、embedding、rerank、简单评分和出题（`extract/embed/rerank/simple_evaluate/question`）本地优先；评分、匹配打分、简历解析强模型优先，另一方为 fallback。
2. 发送带超时的请求，仅对瞬态错误（408/425/429/5xx、超时、网络错误）执行有限重试和指数退避（0.25s×2^n，封顶 5s，每 provider 最多 `MODEL_MAX_RETRIES`+1 次）；401/403 等确定性失败立即切换下一 provider，避免拖垮浏览器超时。
3. 记录 provider、model、route、耗时、tokens、状态、错误名和 fallback 原因。
4. 对结构化输出执行 JSON 解析和一次 repair；失败时返回 `ok=false`，由领域服务提供确定性 fallback。
5. 健康检查返回 provider 状态和最后错误，不阻塞业务服务启动。

实现细节：JSON 处理分三段（剥 markdown 围栏 → 修复尾逗号/单引号 dict → schema 校验，`jsonschema` 缺失时使用内置迷你校验器）；匹配打分 schema 同时兼容英文平铺、英文嵌套和中文键三种模型输出形状；local provider 为 Qwen3 系列时通过 `chat_template_kwargs` 关闭思维链外露。`embed()`（/embeddings）与 `rerank()`（/rerank，失败时退化为词法交集打分）已实现但当前主业务链路未调用，属预留能力。每次调用（含失败与兜底）写入 `model_invocations` 遥测（latency/tokens/cost_usd/attempt/fallback_reason）。

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
- `INTERVIEW_DATASET_PATH`：活动题库路径。代码默认（`config.py`）与生产 Compose 均为 `data/approved-dataset.json`；`backend/.env.example` 中的示例值仍指向 `mock-interview-dataset.json`，仅用于无外部数据依赖的最小开发演示，正式开发建议改为 approved 数据集。
- `DATABASE_POOL_SIZE`：配置项存在但当前实现未使用连接池（SQLite 单连接 + 锁；PostgreSQL 单连接），为后续扩展预留。
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
