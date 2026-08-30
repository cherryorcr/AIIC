# 面试陪练数据与数据库管理设计

## 现状

后端默认使用 SQLite 作为零配置的开发数据库，文件默认位于 `data/app.db`；设置 `DATABASE_URL` 后运行时切换到 PostgreSQL（同一 `Database` 仓储接口）。应用启动时会执行幂等建表/迁移，并把 `INTERVIEW_DATASET_PATH` 指向的数据集（默认 `data/approved-dataset.json`）中的题目、技能、来源和图关系写入数据库。题目在运行时从数据库读取，因此修改题库后不需要重新编译前端。

当前活动题库为 **31 条公开来源题目**（`dataset_status: approved_public_transformed`）：行为面题来自 MIT 许可的 `yangshun/tech-interview-handbook` 公开汇总，算法/技术面题为基于其题名和主题的自行转写，每条保留 URL、许可证、版本、访问时间、`content_hash`、脱敏与可再分发标记。早期的 9 条 `synthetic_mock` 合成示例题已在数据库中软删除（`is_active=0`）保留审计；群面讨论题为应用自有 `synthetic_mock` 内置项，数据集缺失时也不会丢失。真实题目接入前必须补齐来源 URL、许可证、访问时间和脱敏状态，不能把合成题标记为高频或真实统计。

## 核心表

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `sessions` | 一次面试训练会话 | 模式、岗位、用户画像、当前题目、状态 |
| `turns` | 用户每次作答 | 题目 ID、文本/代码、算法运行结果 |
| `feedback` | 结构化反馈 | 评分、证据原句、改进建议、下一步 |
| `model_invocations` | 模型路由审计 | 任务、提供方、模型、耗时、降级原因 |
| `sources` | 数据来源台账 | URL、标题、许可证、版本、访问时间、`pii_redacted`、是否允许再分发 |
| `skills` | 技能节点 | 标准名称和别名 |
| `questions` | 面试题节点 | 场景、岗位、难度、题面、追问、Rubric、测试用例、来源置信度、启用状态 |
| `question_skills` | 题目-技能多对多关系 | `question_id`、`skill_id` |
| `graph_edges` | GraphRAG 关系边 | `Question -tests-> Skill` 等关系及来源 |
| `schema_migrations` | 数据库版本记录 | 版本号、说明、应用时间 |
| `users` | 临时用户/正式账户主体 | 用户 ID、显示名、规范化邮箱、密码哈希、临时标记、最近访问时间 |
| `auth_sessions` | 服务端登录态 | 用户 ID、令牌哈希、到期/撤销/最近使用时间、客户端审计信息 |
| `user_profiles` | 用户技能与项目档案 | 技能、项目经历、教育/经验、约束及扩展 JSON |
| `jobs` | 用户保存的岗位和 JD | 岗位名称、公司、JD 文本、归一化技能、来源信息 |
| `match_snapshots` | 简历与 JD 的固定评分快照 | 用户、目标岗位、输入指纹、评分版本、分数、模型/规则来源及解释 |
| `question_favorites` | 用户收藏题目 | 用户 ID、题目 ID、收藏时间 |
| `reports` | 训练报告快照 | 用户/会话、报告标题、结构化报告 JSON |
| `group_messages` | 群面模拟队友的自主发言 | 会话 ID、发言者与角色、讨论阶段、下次发言间隔、生成 provider |
| `candidate_documents` | 简历/JD 上传解析记录 | 用户 ID、文档类型、提取文本、AI 解析草稿、状态（uploaded/parsed/confirmed/failed）、关联资源 ID |

题目删除采用软删除（`questions.is_active=0`），避免破坏历史会话和反馈；重新导入同一个 ID 会自动恢复启用。

## 管理 API

开发环境不设置 `ADMIN_TOKEN` 时可以直接调用；生产环境必须在环境变量中设置，并通过 `X-Admin-Token` 传入。

```text
GET    /api/v1/admin/knowledge/stats
GET    /api/v1/admin/knowledge/items?process_type=算法面&include_inactive=false
GET    /api/v1/admin/knowledge/sources
POST   /api/v1/admin/knowledge/items
PATCH  /api/v1/admin/knowledge/items/{question_id}
DELETE /api/v1/admin/knowledge/items/{question_id}   # 软删除
POST   /api/v1/admin/knowledge/reload?prune=false
```

`reload` 默认只同步数据集中的新增/修改题目，保留管理员手工录入的数据；明确传 `prune=true` 才会把数据集中已不存在的题目软删除。所有写入均使用事务和参数化 SQL，重复导入不会产生重复题目、技能或关系边。

## 数据导入规范

1. 先登记 `sources`，确认公开访问和许可证，再导入题目。
2. 题目必须包含 `source_id`、`source_confidence` 和 `pii_redacted` 信息；不明来源只能作为低置信度候选。
3. 导入脚本应计算 `content_hash`，用于去重和检测原文变化。
4. 原始网页不直接作为事实展示；前端展示来源类型和可追溯 URL。
5. 用户简历、回答和访谈记录默认脱敏，数据库备份也必须放在受控存储中。

## 部署与备份

- 挑战/单机：SQLite 文件通过 Docker volume 持久化，定期执行 `VACUUM` 前先备份。
- 多实例生产：将 `Database` 接口迁移到 PostgreSQL；向量字段使用 pgvector，图关系可继续使用关系表，必要时再接 Neo4j。
- PostgreSQL 基线迁移脚本位于 `backend/migrations/001_postgres_schema.sql`，可通过
  `python backend/scripts/migrate_postgres.py --database-url "$DATABASE_URL"` 执行；若要
  迁移既有 SQLite 数据，再加 `--sqlite-path data/app.db`。
  SQLite 运行时仍由 `Database.init()` 自动执行版本 1–8 的幂等迁移（v8 引入群面 `group_messages` 表）；因此可以先用
  SQLite 开发，再切换到 PostgreSQL，而不改变 API 层的数据契约。
- 备份至少包含 `app.db` 和题库 JSON；恢复后调用 `POST /api/v1/admin/knowledge/reload` 校验统计数。
- API key、管理员 token 和 SSH 密码只通过部署环境变量/密钥管理注入，禁止写入数据库或仓库。

## 用户隔离与认证

- 临时用户和正式账户都通过服务端 `auth_sessions` 识别；浏览器只持有 HttpOnly 随机令牌，数据库只保存其 SHA-256 摘要。
- 密码采用带随机盐的 PBKDF2-SHA256 哈希，不保存明文或可逆密文。
- 注册会将当前临时用户原地升级，所有以 `user_id` 关联的档案、JD、收藏、文档、会话、回答和报告继续保留。
- 所有按资源 ID 读取或修改的接口先校验资源的 `user_id`，越权访问统一返回 404；客户端提交的 `user_id` 和 `X-User-Id` 不作为授权依据。
- 准备度接口仅查询当前用户的 `user_profiles`、`jobs`、`sessions` 和 `reports`，前端本地降级缓存也按用户 ID 命名空间隔离。

## GraphRAG 与真实数据导入

当前活动题库为已核验许可的公开来源转写数据（见 `docs/report-source.md`），早期
`synthetic_mock` 演示数据已软删除。运行时召回由场景/岗位/技能
关系过滤、关键词匹配和无依赖哈希向量余弦相似度组成；配置本地模型后，
`ModelRouter.embed()` 可用于替换为真实 embedding 服务。题目导入 CLI 会做题面
去重、内容 hash、来源 URL/许可证检查和访问时间记录：

```powershell
python backend/scripts/manage_knowledge.py validate --file data/approved-dataset.json
python backend/scripts/manage_knowledge.py import --file data/approved-dataset.json
```

不要把未确认许可的网页原文复制进仓库；在线数据只能以允许再分发的脱敏题面或
受控引用形式导入，并在前端展示来源 URL、许可证、版本和置信度。
