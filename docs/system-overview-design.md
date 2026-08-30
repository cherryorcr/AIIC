# AIIC 系统概要设计

## 1. 设计目标与边界

AIIC 是一个面向学生求职、实习、校招和保研准备的场景化文字面试陪练平台。系统通过用户背景、脱敏 JD、岗位技能、面试场景、题目和 Rubric 的关联，生成可解释的题目匹配和结构化反馈。

当前版本的核心闭环是：

```text
用户背景/JD → 技能抽取 → GraphRAG 匹配 → 场景化提问 → 用户回答
    → Rubric 评分 → 原句证据/改进建议 → 追问或下一题 → 报告
```

当前不把语音、视频、实时数字人、支付、社区、邮件验证和大规模推荐作为挑战版验收内容。接口和数据结构可以为后续通道扩展，但不能影响文字闭环。

## 2. 系统上下文

```text
┌──────────────────────┐
│ 候选人浏览器          │
│ React + TypeScript    │
└──────────┬───────────┘
           │ HTTPS / REST / SSE
┌──────────▼───────────┐
│ CPU 业务服务器        │
│ Nginx + FastAPI       │
│ SQLite/PostgreSQL     │
│ GraphRAG + 沙箱       │
│ Model Router          │
└───────┬───────────────┘
        │ 私网 HTTPS / 反向隧道 / 鉴权
┌───────▼───────────────┐       ┌──────────────────────┐
│ 双 RTX 4090 模型主机  │ HTTPS │ 第三方强模型中转      │
│ OpenAI-compatible     │◄─────►│ 复杂生成/反馈        │
│ local LLM/embed/rerank│       └──────────────────────┘
└───────────────────────┘
```

## 3. 物理部署

### 3.1 CPU 业务服务器

生产/挑战部署使用 Docker Compose，包含：

- `frontend`：Nginx 提供 React 静态文件并代理 `/api`。
- `backend`：FastAPI API、业务服务、GraphRAG、Model Router 和挑战版沙箱。
- `postgres`：生产持久化数据库；开发可切换 SQLite。
- `redis`：预留给异步任务、缓存和限流；当前 Compose 可按负载启用 worker。

仓库当前的 `backend/deploy/compose.cpu.yml` 已实现 frontend、backend、PostgreSQL 三个容器；Redis、独立 sandbox runner 属于目标拆分，需在扩大并发或开放代码执行前补齐。

### 3.2 GPU 模型服务器

使用 `backend/deploy/compose.gpu.example.yml` 作为双 4090 参考：vLLM 提供 OpenAI-compatible 接口，LiteLLM 或等价网关负责鉴权、模型名映射、限流和健康检查。当前部署手册记录的实际 GPU 服务由主机服务管理；Compose 文件用于可复现的容器化迁移路径。

第一阶段将两张卡分配给一个模型实例做 tensor parallel；并发提升后可以改为每卡一个副本，由网关按负载轮询。GPU 推理端口不应直接暴露公网。

## 4. 逻辑分层

```text
Presentation Layer
  ├─ React pages: 总览、训练、岗位匹配、资料、题库、报告、账户
  └─ API client: timeout/retry/auth-cookie/error normalization

Application Layer
  ├─ Session/Auth/Profile/Job/Document APIs
  ├─ InterviewService: start, answer, retry, summary, complete
  ├─ MatchingService: role/skill/question match
  └─ Admin knowledge and observability APIs

Domain Services
  ├─ GraphRAGService
  ├─ Prompt policy and Rubric resolver
  ├─ ModelRouter
  ├─ SandboxService
  └─ Document parser

Infrastructure Layer
  ├─ Database repository (SQLite/PostgreSQL compatibility)
  ├─ HTTP model adapters
  ├─ file/text extraction
  └─ Docker/Nginx/host tunnel
```

## 5. 模块职责

| 模块 | 责任 | 当前实现 |
| --- | --- | --- |
| Auth | 临时用户、注册、登录、注销、Cookie 会话 | `backend/app/services/auth.py` + `main.py` |
| Profile/Job | 用户画像、岗位和 JD 持久化 | `main.py` + `storage/db.py` |
| Document | 文件类型/大小校验、文本抽取、AI 解析、人工确认 | `services/documents.py` |
| GraphRAG | 技能归一化、关系过滤、去重、向量/词法相似度、来源返回 | `services/rag.py` |
| Interview | 会话状态、首题、回答、重答、追问、反馈、报告 | `services/interview.py` |
| Prompt Policy | 按场景设置题目指令、评价维度和群面反应 | `services/prompts.py` |
| Model Router | provider 顺序、重试、JSON 修复、健康、成本遥测 | `services/model_router.py` |
| Sandbox | Python AST 策略检查、受限子进程、固定测试执行 | `services/sandbox.py` |
| Database | schema、迁移、用户资源隔离、知识库和审计持久化 | `storage/db.py` |
| Frontend | 页面导航、场景工作台、资料确认、匹配和报告 | `frontend/src/App.tsx` |

## 6. 关键质量属性

- **可解释性**：推荐返回技能、场景、来源和置信度；反馈返回原回答证据。
- **降级性**：模型不可用不影响页面打开；按本地模型、第三方模型、规则 fallback 顺序处理。
- **隐私性**：服务端会话推导用户；材料先解析、后确认；密钥只在服务器环境变量中。
- **安全性**：算法代码在受限子进程中运行；生产环境需独立 runner、禁网和资源限制。
- **可扩展性**：场景由 policy/Rubric 驱动；模型通过 adapter 接入；存储通过 Database 边界替换。
- **可运营性**：模型调用记录 provider、model、延迟、token、状态和 fallback 原因。

## 7. 关键技术选择

| 决策 | 选择 | 原因 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite | 现有工作台已实现，组件和构建简单 |
| 后端 | FastAPI + Pydantic | 与 Python RAG、文档解析和算法沙箱生态一致 |
| 数据库 | 开发 SQLite，生产 PostgreSQL | 便于挑战演示，并可扩展并发与备份 |
| 图检索 | 关系表/轻量 GraphRAG + 向量相似度 | MVP 不引入 Neo4j 运维负担，保留迁移边界 |
| 模型 | OpenAI-compatible Model Router | 业务流程不绑定供应商，可本地/远程切换 |
| 部署 | Docker Compose 双主机 | 一天内可完成、可复现、便于资源隔离 |
| 算法运行 | 受限 Python 子进程，后续独立 runner | 满足 MVP 验证并明确生产安全边界 |

## 8. 启动与关闭

1. backend 启动时初始化数据库、幂等导入活动题库、连接 GraphRAG。
2. frontend 依赖 backend 健康检查后启动。
3. Model Router 按需探测 provider；模型不可用只标记 `degraded`，不阻塞 API 启动。
4. 关闭时不删除数据库 volume；报告、会话和来源记录可恢复。

## 9. 设计边界

本概要设计描述的是当前项目真实的服务边界，不等同于完整商业系统。邮件验证、找回密码、异步任务、Redis、独立 sandbox runner、pgvector/真实 embedding、语音/视频通道和企业级多租户均是后续迭代项。
