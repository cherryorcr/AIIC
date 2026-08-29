# 面试陪练数据与数据库管理设计

## 现状

后端现在使用 SQLite 作为零配置的 MVP 数据库，文件默认位于 `data/app.db`。应用启动时会执行幂等建表/迁移，并把 `data/mock-interview-dataset.json` 中的题目、技能、来源和图关系写入数据库。题目在运行时从数据库读取，因此修改题库后不需要重新编译前端。

当前随仓库提供的是 **9 条合成示例题**，来源类型为 `synthetic_mock`，不是已经采集的真实面试原文。真实题目接入前必须补齐来源 URL、许可证、访问时间和脱敏状态，不能把合成题标记为高频或真实统计。

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
| `users` | 临时用户/登录用户主体 | 用户 ID、显示名、临时标记、最近访问时间 |
| `user_profiles` | 用户技能与项目档案 | 技能、项目经历、教育/经验、约束及扩展 JSON |
| `jobs` | 用户保存的岗位和 JD | 岗位名称、公司、JD 文本、归一化技能、来源信息 |
| `question_favorites` | 用户收藏题目 | 用户 ID、题目 ID、收藏时间 |
| `reports` | 训练报告快照 | 用户/会话、报告标题、结构化报告 JSON |

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
  SQLite 运行时仍由 `Database.init()` 自动执行版本 1–3 的幂等迁移；因此可以先用
  SQLite 开发，再切换到 PostgreSQL，而不改变 API 层的数据契约。
- 备份至少包含 `app.db` 和题库 JSON；恢复后调用 `POST /api/v1/admin/knowledge/reload` 校验统计数。
- API key、管理员 token 和 SSH 密码只通过部署环境变量/密钥管理注入，禁止写入数据库或仓库。

## GraphRAG 与真实数据导入

当前题库仍是明确标注的 `synthetic_mock` 演示数据。运行时召回由场景/岗位/技能
关系过滤、关键词匹配和无依赖哈希向量余弦相似度组成；配置本地模型后，
`ModelRouter.embed()` 可用于替换为真实 embedding 服务。题目导入 CLI 会做题面
去重、内容 hash、来源 URL/许可证检查和访问时间记录：

```powershell
python backend/scripts/manage_knowledge.py validate --file data/approved-dataset.json
python backend/scripts/manage_knowledge.py import --file data/approved-dataset.json
```

不要把未确认许可的网页原文复制进仓库；在线数据只能以允许再分发的脱敏题面或
受控引用形式导入，并在前端展示来源 URL、许可证、版本和置信度。
