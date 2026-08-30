# AIIC 面试陪练平台

AIIC（AI Interview Coach）是一个面向求职者的场景化 AI 面试陪练平台。系统结合用户技能、项目经历和目标岗位，通过 GraphRAG 关联岗位、技能、面试环节、题目与评分标准，为用户生成可解释的岗位匹配、面试题和结构化反馈。

## 当前版本

当前仓库包含可本地运行的 MVP：

- 技术面、算法面、行为面、压力面、案例面、科研面和 HR 面
- FastAPI 面试会话、追问和训练反馈 API
- Python 算法题挑战版沙箱
- SQLite 驱动的轻量 GraphRAG；默认加载 31 条带 MIT 来源元数据的公开题库转写
- React + TypeScript + Vite 前端训练工作台
- CPU 业务服务器和 GPU 模型服务器的 Docker Compose 示例

`data/approved-dataset.json` 是当前活动题库：行为面题来自 MIT 许可的 Tech Interview Handbook 公开汇总，算法/系统设计题为基于其题名和主题的自行转写。它们不是公司官方题库或频次统计；LeetCode 原题正文和答案没有复制。`data/mock-interview-dataset.json` 与问卷样例仍明确标记为 `synthetic_mock`，仅用于历史审计和开发演示。所有外部数据必须记录来源 URL、许可证、访问时间、版本和脱敏状态。

## 本地运行

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

API 文档：<http://localhost:8000/docs>

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

打开 <http://localhost:5173/>。前端通过 `/api` 调用后端；开发环境下 Vite 会将请求代理到本地 FastAPI 服务。

## Docker

CPU 业务服务：

```powershell
cd backend/deploy
docker compose -f compose.cpu.yml up -d --build
```

双 RTX 4090 服务器可参考 `compose.gpu.example.yml`，对外只提供经过鉴权的 OpenAI-compatible 模型网关。模型密钥只注入服务端环境变量，不放入浏览器或 Git。

## 目录结构

```text
backend/   FastAPI、模型路由、GraphRAG、算法沙箱和测试
frontend/  React/TypeScript/Vite 前端
data/      approved 公开题库、合成题库、问卷样例和在线数据来源台账
docs/      API 契约、研究计划和数据库设计
```

## 重要限制

- 当前模型未绑定时会使用确定性规则降级；生产环境需要接入模型网关并配置超时、重试和成本记录。
- 当前算法沙箱是挑战版实现，正式开放前必须迁移到独立 runner，并启用禁网、资源限制和更强隔离。
- 当前默认使用 SQLite；多实例部署应迁移到 PostgreSQL，并配置备份和恢复演练。
