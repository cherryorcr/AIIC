# 变更日志

依据 git 历史整理的功能级变更记录；同一天内按提交顺序从新到旧。格式参考 Keep a Changelog。

## [未发布] - 2026-08-30

### 新增
- 群面自主讨论：用户不发言时 AI 队友按可调节奏（4-20 秒）自主推进，发言持久化到 `group_messages` 并支持回放；追问自动锚定回答证据（`fix: anchor follow-ups and automate group discussion`）。
- 对话式训练工作台与群面场景：聊天流交互、暂停/恢复队友讨论（`feat: add conversational and group interview training` 等）。
- 简历/JD 个性化出题：强模型结合检索结果生成可溯源题目（`feat: personalize questions from resume and job context`）。
- 群面场景与回答修订流：`revision_of` + `answer_mode` 父子 Turn（`feat: add group interviews and answer revision flow`）。
- 账户体系：临时用户原地升级注册、按用户隔离工作区、PBKDF2 密码与哈希会话令牌（`feat: add secure accounts and per-user workspaces`）。
- 生产部署与韧性：CPU/GPU Compose、SSH 反向隧道、幂等重放、PostgreSQL 迁移（`feat: add production deployment and resilient interview flow`）。
- 候选人文档流水线：上传→AI 提取→人工校对→确认落库（`feat: add candidate document extraction and storage` 等）。
- Model Router embedding/rerank 预留能力与韧性路由（`feat: add resilient embedding and reranker routing`）。
- 训练报告持久化、数据库健康探测、题库导入校验与幂等岗位（多提交）。

### 修复
- 匹配评分：接受托管网关的分数包装、中文键归一化、评分与准备度一致性、快照稳定（多提交）。
- 简历提取字段映射、训练前档案清洗、题库标题去重、无目标岗位准备度归零等。

### 数据与文档
- approved 公开题库（31 条，MIT 来源转写）替换 synthetic_mock 演示题；来源台账与调研文档（`docs:` 系列提交）。
