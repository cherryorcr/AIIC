# AIIC 测试计划与验收说明

## 1. 测试目标

验证系统是否能完成“资料/岗位输入 → 匹配 → 场景训练 → 反馈 → 追问/重答 → 报告”的核心闭环，并确认用户隔离、来源可追溯、模型降级和算法代码安全边界。

## 2. 测试层次

| 层次 | 内容 | 工具/方式 |
| --- | --- | --- |
| 单元测试 | 技能归一化、GraphRAG 去重、Prompt schema、沙箱策略 | pytest |
| API 集成测试 | FastAPI 路由、数据库持久化、鉴权和错误码 | FastAPI TestClient + 临时 SQLite |
| 契约测试 | 前端类型、请求字段、响应字段和 legacy 别名 | TypeScript build + JSON fixture |
| 端到端测试 | 浏览器完成资料、匹配、训练、报告 | Playwright 或手工演示 |
| 安全测试 | 跨用户访问、文件上传、模型密钥、代码沙箱 | 专项用例和日志审计 |
| 部署测试 | Compose 启停、健康检查、GPU 网关连接、备份恢复 | Docker Compose + runbook |
| 质量评测 | 匹配相关性、反馈证据、追问相关性、编造率 | 人工金标准评测集 |

## 3. 已有自动化覆盖

`backend/tests/test_smoke.py` 已覆盖：

- 会话创建、文字回答、群面模拟反应；
- 重答父子 Turn、重复提交幂等；
- 匹配预览不创建会话、匹配分数稳定、岗位归属校验；
- 算法代码违规、反射逃逸、超时和题库管理；
- 用户资料、岗位、收藏、历史和报告持久化；
- 注册账户隔离、准备度和文档上传/确认/删除；
- PostgreSQL 迁移基线、模型 fallback 和遥测；
- GraphRAG 技能抽取、语义去重和数据集缺失降级。

当前执行环境未安装 `pytest`，因此本轮只完成测试文件和结构检查，未能重新运行回归套件。交付前应在安装 `backend/requirements-dev.txt` 的环境中执行：

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_smoke.py -q
```

## 4. 关键测试用例

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T-01 | 首次匿名访问 | 建立临时用户和 HttpOnly Cookie |
| T-02 | 注册升级临时用户 | 原 Profile、Job、Session 和报告继续保留 |
| T-03 | 两账户读取对方 Session | 返回 404，不泄露资源存在性 |
| T-04 | 上传超大文件/不支持扩展名 | 413/415，原始文件不落盘 |
| T-05 | 上传后不确认 | 只保存解析草稿，不更新规范资料 |
| T-06 | JD 与项目匹配 | 返回 required/matched/gap 技能和来源 |
| T-07 | 模型返回非法 JSON | 服务端尝试修复，失败时返回规则反馈 |
| T-08 | 强模型超时 | 记录 fallback，切换本地或确定性评分 |
| T-09 | 重复提交已完成题 | 返回已持久化 Turn，不重复推进 |
| T-10 | 重答原题 | 创建子 Turn，不移动当前追问游标 |
| T-11 | 算法正确代码 | 返回 passed 和每个测试结果 |
| T-12 | 算法死循环 | 返回 timeout，进程被终止 |
| T-13 | 算法导入 socket/os 或反射 | 返回 rejected |
| T-14 | 来源缺许可证 | 导入校验失败或进入隔离区 |
| T-15 | 完成零回答会话 | 不生成零分报告 |
| T-16 | CPU Compose 重启 | backend、frontend、PostgreSQL 可恢复 |
| T-17 | GPU 网关不可达 | API 可启动，状态 degraded，页面可使用 fallback |
| T-18 | SSE 事件流 | 连接保持、事件格式可解析、断开可重连 |

## 5. 质量评测集

建议建立 5 组脱敏 JD、5 组用户背景、20-30 道题和人工 Rubric。每条样例记录：

- 应召回的技能和题目；
- 不应召回的技能和题目；
- 可接受的证据原句；
- 反馈必须包含的改进动作；
- 是否出现模型编造；
- 面试场景和难度。

核心指标：岗位技能覆盖率、题目 Precision@k、追问相关性、证据引用率、编造率、建议可执行率、算法判定正确率、p50/p95 延迟、fallback 率和估算成本。

## 6. 安全验收

- API key 不出现在前端产物、Git、数据库和普通日志。
- Cookie 为 HttpOnly；生产 HTTPS 下 `AUTH_COOKIE_SECURE=true`。
- 资源 owner 校验不接受客户端 user ID。
- 管理 API 没有 `ADMIN_TOKEN` 时只允许本地开发，生产必须配置。
- 算法沙箱不联网、不挂宿主目录、不使用 Docker Socket、限制资源和输出。
- 题库数据标明 `observed`、`verified_public`、`synthetic_mock` 或 `self_authored`。

## 7. 发布门槛

发布前必须满足：

1. 自动化测试全部通过，或对未通过项登记原因和风险。
2. API/前端构建成功，健康检查为 `ok` 或有明确降级说明。
3. 题库来源和许可审计完成，模拟数据没有被标记为真实。
4. 至少 5 名真实目标用户完成体验（正式产品发布前）；挑战演示可先使用模拟数据但必须显式标注。
5. 完成数据库备份、恢复和模型网关不可用演练。
