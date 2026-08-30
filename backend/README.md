# AI 面试陪练后端

这是基于项目方案实现的 FastAPI MVP。后端提供：

- 技术、算法、行为、压力、案例、科研、HR 面和群面场景
- JSON 示例题库驱动的轻量 GraphRAG（关系过滤 + 词法召回）
- 统一 Model Router：本地 OpenAI-compatible 网关 / 第三方强模型 / 规则降级
- 文字回答、结构化反馈、追问和训练总结
- 回答反馈后的重新回答/补充修订；修订 turn 通过 `parent_turn_id` 保留完整对话轨迹且不会重复推进题目
- 群面围绕一个开放问题模拟主持人和队友反应；该场景由应用生成并明确标记为 `synthetic_mock`，不代表真实企业题目
- Python 算法题受限执行（挑战版）；生产环境应使用独立 runner 主机和更强隔离
- SQLite 零配置启动，带 schema 迁移、来源台账和题库管理 API；设置 `DATABASE_URL` 后运行时切换到 PostgreSQL
- 临时用户无感体验，以及可保留现有数据升级的邮箱/密码账户；档案、JD、收藏、会话、回答、准备度和报告按账户隔离

## 本地运行

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

启动后访问 `http://localhost:8000/docs`。

### 用户与认证

首次访问用户接口会创建隔离的临时工作区，并通过 HttpOnly Cookie 保存随机登录态。注册会原地升级当前临时用户，因此已有资料和训练历史不会丢失；登录、退出和当前用户接口为：

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/workspace/overview
```

密码使用带独立盐的 PBKDF2-SHA256 哈希，数据库只保存登录令牌的 SHA-256 摘要。`X-User-Id` 仅作为响应诊断字段，服务端不会将客户端提交的用户 ID 当作身份凭据。HTTPS 部署必须设置 `AUTH_COOKIE_SECURE=true`。

### PostgreSQL 运行时

安装依赖后设置 `DATABASE_URL` 即可切换存储实现。应用启动会幂等执行
`backend/migrations/001_postgres_schema.sql`；已有 SQLite 数据可以先执行迁移脚本并
传入 `--sqlite-path` 复制到 PostgreSQL：

```powershell
python scripts/migrate_postgres.py --database-url $env:DATABASE_URL --sqlite-path ../data/app.db
```

## 模型配置

真实凭据不要写入 `.env.example`、源码、Dockerfile 或日志。部署机器上设置：

```text
STRONG_MODEL_BASE_URL=https://jojocode.com/v1
STRONG_MODEL_API_KEY=<server-secret>
# GPU Compose 示例的 LiteLLM 网关默认使用 4000 端口；若你的网关映射为 8000，请相应调整
LOCAL_MODEL_BASE_URL=http://100.126.175.112:4000/v1
LOCAL_MODEL_API_KEY=<optional>
```

业务代码只调用 `ModelRouter`。如果模型未配置或调用失败，会使用确定性的本地反馈，确保演示流程不被外部服务阻断。

## Docker

CPU 业务服务器运行：

```powershell
cd backend/deploy
docker compose -f compose.cpu.yml up -d --build
```

前端容器应由前端仓库独立构建，用 Nginx 将 `/api` 反向代理到 `backend:8000`。双 4090 服务器使用另一套 Compose，运行 OpenAI-compatible `model-gateway` 和本地推理容器；CPU 服务器只通过私网 HTTPS、IP 白名单或 mTLS 访问网关。

双 4090 服务器可参考 `deploy/compose.gpu.example.yml`。示例使用 vLLM 的 OpenAI-compatible 服务并将两张卡用于 tensor parallel；实际模型名、端口白名单和鉴权密钥应根据服务器环境修改。

## API 快速示例

```powershell
$body = @{ mode='technical'; role='后端开发'; job_text='要求 Python、FastAPI、Redis'; user_profile=@{ skills=@('Python'); projects=@('TechMatch') }; difficulty='medium' } | ConvertTo-Json -Depth 5
$session = Invoke-RestMethod http://localhost:8000/api/v1/sessions -Method Post -ContentType 'application/json' -Body $body
$session | ConvertTo-Json -Depth 5
```

## 题库和数据库管理

启动时会将 JSON 题库幂等导入 `DATABASE_URL` 指定的 PostgreSQL 或 `DATABASE_PATH` 指定的 SQLite 文件（默认 `data/app.db`）。题目、技能、来源和 GraphRAG 关系均在数据库中管理；面试会话、回答、反馈和模型调用也会持久化。

管理员接口（生产环境请设置 `ADMIN_TOKEN` 并通过 `X-Admin-Token` 传入）：

```text
GET    /api/v1/admin/knowledge/stats
GET    /api/v1/admin/knowledge/items
GET    /api/v1/admin/knowledge/sources
POST   /api/v1/admin/knowledge/items
PATCH  /api/v1/admin/knowledge/items/{question_id}
DELETE /api/v1/admin/knowledge/items/{question_id}   # 软删除
POST   /api/v1/admin/knowledge/reload?prune=false
```

也可以使用命令行检查或重载题库：

```powershell
python scripts/manage_knowledge.py stats
python scripts/manage_knowledge.py list --process-type 算法面
python scripts/manage_knowledge.py reload --prune
# 校验/导入已确认许可的外部题库（在线来源必须有 URL）
python scripts/manage_knowledge.py validate --file ../data/approved-dataset.json
python scripts/manage_knowledge.py import --file ../data/approved-dataset.json
```

详细表结构、迁移和真实数据导入规范见 [`docs/database-design.md`](../docs/database-design.md)。

## 数据和许可

`data/mock-interview-dataset.json` 明确标记为 `synthetic_mock`，仅用于流程演示。接入网上题目时必须保存来源 URL、许可证、版本和访问日期，不要把未确认许可的原文直接提交到公开仓库。
