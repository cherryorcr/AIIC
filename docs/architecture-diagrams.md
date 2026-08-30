# AIIC 架构与部署图

> 本文档以 Mermaid 描述当前仓库实现的架构视图，与 `docs/system-overview-design.md`（文字版）互为补充。图中所有组件均为 `implemented`，除非明确标注 `planned`。渲染方式：GitHub / IDE 内置 Mermaid 预览，或 `mermaid-cli`。

## 1. 系统上下文图（C4 Level 1）

```mermaid
graph TB
    user(["候选人<br/>（浏览器）"])
    admin(["知识库管理员<br/>（CLI / X-Admin-Token）"])

    subgraph cpu["CPU 业务服务器（腾讯云 146.56.204.146）"]
        fe["Nginx + React 前端<br/>:8080（唯一公开端口）"]
        be["FastAPI 后端<br/>127.0.0.1:8000"]
        pg[("PostgreSQL 16<br/>127.0.0.1:5432")]
    end

    subgraph gpu["GPU 模型服务器（双 RTX 4090，Tailscale 私网）"]
        vllm["vLLM Qwen3-32B-AWQ<br/>127.0.0.1:8000"]
    end

    strong["第三方强模型中转<br/>OpenAI-compatible"]

    user -->|HTTPS/HTTP :8080| fe
    fe -->|"/api 反代（180s 超时）"| be
    be --> pg
    be -->|"host.docker.internal:18000<br/>（SSH 反向隧道）"| vllm
    be -->|HTTPS| strong
    admin -->|manage_knowledge.py / admin API| be
```

要点：

- 模型端口、PostgreSQL 与后端 8000 端口均不对公网开放；GPU 网关经 systemd 管理的受限 SSH 反向隧道（`aiic-model-tunnel.service`）转发到 CPU 主机 Docker 网桥 `172.18.0.1:18000`。
- 模型密钥只存在于 CPU 主机 `.env`（0600），不进入浏览器、Git 或数据库。

## 2. 后端组件图（C4 Level 2/3）

```mermaid
graph LR
    subgraph api["app/main.py（路由 + 鉴权 + 错误边界）"]
        auth_r["Auth/用户/工作区路由"]
        sess_r["Session/Turn/群面路由"]
        match_r["匹配/岗位/文档路由"]
        kb_r["题库 + Admin 路由"]
    end

    subgraph services["app/services/"]
        interview["InterviewService<br/>会话状态机、追问、报告"]
        matching["MatchingService<br/>评分快照、个性化出题"]
        documents["DocumentService<br/>PDF/DOCX/TXT 提取 + 两遍解析"]
        rag["GraphRAGService<br/>关系过滤 + 词法/哈希向量召回"]
        prompts["Prompt Policies<br/>8 场景策略与 Rubric"]
        router["ModelRouter<br/>local/strong/规则兜底"]
        sandbox["SandboxService<br/>AST 策略 + 受限子进程"]
        authsvc["AuthService<br/>PBKDF2 + 会话 token 哈希"]
    end

    db[("Database（storage/db.py）<br/>SQLite ⇄ PostgreSQL 方言层")]

    sess_r --> interview
    match_r --> matching & documents
    kb_r --> rag
    auth_r --> authsvc
    interview --> rag & prompts & router & sandbox
    matching --> rag & router
    documents --> router
    services --> db
    router -->|遥测 model_invocations| db
```

## 3. 数据模型 ER 图（核心表）

```mermaid
erDiagram
    users ||--o| user_profiles : "1:1 档案"
    users ||--o{ auth_sessions : "会话（存 token 哈希）"
    users ||--o{ jobs : "保存的岗位/JD"
    users ||--o{ sessions : "训练会话"
    users ||--o{ candidate_documents : "上传的简历/JD"
    users ||--o{ match_snapshots : "不可变评分快照"
    users ||--o{ question_favorites : "收藏"
    users ||--o{ reports : "训练报告"
    jobs |o--o{ sessions : "可关联"
    sessions ||--o{ turns : "作答轮次"
    sessions ||--o{ group_messages : "群面队友发言"
    turns ||--o| feedback : "结构化反馈"
    turns |o--o{ turns : "parent_turn_id 修订链"
    sources ||--o{ questions : "来源台账"
    questions }o--o{ skills : "question_skills"
    questions ||--o{ graph_edges : "Question -tests-> Skill"
    sessions |o--o{ model_invocations : "模型调用遥测"
```

## 4. 关键时序：一轮文字面试

```mermaid
sequenceDiagram
    participant U as 浏览器
    participant B as FastAPI
    participant R as GraphRAG
    participant M as ModelRouter
    participant D as Database

    U->>B: POST /api/v1/sessions（mode/role/job_id）
    B->>R: match(场景/岗位/技能)
    R-->>B: top-5 候选题
    B->>M: task=question 个性化改写（本地优先）
    M-->>B: 个性化题（失败则用题库原题）
    B->>D: 保存 Session + 当前题
    B-->>U: 首题 + why_this_question + source_refs

    U->>B: POST /sessions/{id}/turns（answer_text）
    B->>D: 先保存 Turn（失败不丢输入）
    B->>M: task=evaluate 结构化评分（强模型优先）
    alt 模型可用
        M-->>B: JSON 反馈（schema 校验 + 一次 repair）
    else 全部失败
        M-->>B: ok=false
        B->>B: 确定性规则 fallback 评分
    end
    B->>D: 保存 Feedback + upsert 报告快照
    B-->>U: 反馈 + 锚定证据的追问
```

## 5. 关键时序：模型路由与降级

```mermaid
sequenceDiagram
    participant S as 领域服务
    participant MR as ModelRouter
    participant L as 本地网关（双4090）
    participant ST as 强模型中转

    S->>MR: complete(task, messages, schema)
    Note over MR: 按 task 决定顺序：<br/>question/extract → local 优先<br/>evaluate/match → strong 优先
    MR->>ST: 请求（30s 超时）
    alt 瞬态错误（429/5xx/超时）
        MR->>ST: 指数退避重试（≤2 次）
    else 确定性错误（401/403/schema）
        Note over MR: 立即切换，不重试
    end
    MR->>L: fallback 请求
    alt 仍失败
        MR-->>S: ok=false, provider=fallback
        Note over S: 使用确定性规则兜底，<br/>演示流程不中断
    end
    MR->>MR: 每次调用写 model_invocations<br/>(latency/tokens/cost/fallback_reason)
```

## 6. 部署拓扑（当前生产）

```mermaid
graph TB
    inet(("公网"))
    subgraph tencent["腾讯云 CPU 主机"]
        subgraph compose["docker compose（compose.cpu.yml）"]
            ng["frontend: nginx<br/>0.0.0.0:8080→80"]
            api["backend: uvicorn<br/>127.0.0.1:8000"]
            db2[("postgres:16<br/>127.0.0.1:5432")]
        end
        bridge["docker 网桥 172.18.0.1:18000<br/>（SSH 隧道落点）"]
    end
    subgraph gpuhost["GPU 主机 pc-rack-server（Tailscale）"]
        tun["aiic-model-tunnel.service<br/>ssh -R 反向隧道"]
        vllm2["vLLM Qwen3-32B-AWQ :8000<br/>双卡 tensor parallel"]
    end
    inet -->|仅 TCP 8080| ng
    ng --> api --> db2
    api --> bridge
    tun -->|建立| bridge
    tun --- vllm2
```

`compose.gpu.example.yml` 提供 GPU 侧容器化迁移路径（vLLM + LiteLLM 网关、强制 master key、仅绑 loopback/私网）；当前实际 GPU 服务由主机既有 systemd 服务管理。

## 7. 规划中的目标架构增量（planned）

- Redis + 异步 worker（限流、耗时任务卸载）。
- 独立算法沙箱 runner 容器（禁网、只读 FS、seccomp/nsjail）。
- pgvector/真实 embedding 替换哈希向量召回（`ModelRouter.embed()` 已预留）。
- SSE 流式事件（当前 `/sessions/{id}/events` 为占位）。
- 真人群面匹配等待池与房间服务。
