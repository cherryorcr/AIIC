# 公开面试题库来源核验报告

**受众**：项目开发与评审人员

**日期**：2026-08-30（Asia/Shanghai）

**范围**：为 AI 面试陪练系统导入可追溯、许可边界清晰的公开行为面、算法面和系统设计题目；同时核验强模型、弱模型网关和 CPU 服务的可用性。
**排除项**：无明确许可证的数据集原文、付费题库、公司内部面经、LeetCode 原题正文/答案和任何含个人信息的面试记录。

## 结论

本次已导入 31 条公开来源题目，活动题目全部来自 MIT 许可的
`yangshun/tech-interview-handbook` 仓库（提交
`e1d28e8886c0b6ff3e50da991ce0e895134ddc59`）：10 条按公司整理的行为面问题、17 条根据算法公开清单题名自行转写的算法练习、4 条根据系统设计主题自行转写的技术面问题。数据库保留 URL、许可证、版本、访问时间、内容哈希、脱敏状态、可再分发标记和来源置信度。

算法题是“来源可追溯的转写题”，不是 LeetCode 原文镜像；题库界面应显示这一边界，不能把条目包装成某公司的官方题库或频次统计。原有 9 条 `synthetic_mock` 数据已在 SQLite 中软删除，历史记录仍可审计和恢复。

模型连通性核验结果：强模型地址 `https://jojocode.com/v1/models` 可达，但部署时携带的密钥返回 HTTP 401，需要用户在轮换后重新注入。双 4090 主机重启后两张 RTX 4090 正常，已有 Qwen3-32B-AWQ vLLM 服务以 `Qwen3-32B-AWQ-vLLM` 运行在 8000 端口；通过 systemd 管理的受限 SSH 反向隧道转发到 CPU 主机 18000 端口。CPU 主机已运行 PostgreSQL、FastAPI 和 Nginx 前端容器，后端 `/health`、题库、岗位匹配、会话和模型健康接口已完成联调；强模型不可用时自动回退本地 Qwen 和规则评分。

## 来源与证据

| 来源 | 证据 | 使用方式 | 置信度 |
| --- | --- | --- | --- |
| [Tech Interview Handbook behavioral questions](https://github.com/yangshun/tech-interview-handbook/blob/main/apps/website/contents/behavioral-interview-questions.md) | GitHub API `license.spdx_id=MIT`；仓库文件按 Airbnb、Amazon、ByteDance、Dropbox、Hired、Lyft、Palantir、Slack、Stack Overflow、Stripe、Twitter 等章节列出公开问题 | 行为面问题按来源保存；每条保留“题源”角色标签和 MIT 元数据 | 中（公开汇总题源，不代表官方频次） |
| [Tech Interview Handbook algorithms](https://github.com/yangshun/tech-interview-handbook/tree/main/apps/website/contents/algorithms) | GitHub API `license.spdx_id=MIT`；数组、图、动态规划、链表、栈、树等清单含公开题名和外部问题链接 | 使用题名和主题自行转写中文练习描述；自行补充评分 rubric 和本地测试样例 | 高（主题/题名来源清晰；转写内容需单独维护） |
| [Tech Interview Handbook system design](https://github.com/yangshun/tech-interview-handbook/blob/main/apps/website/contents/system-design.md) | GitHub API `license.spdx_id=MIT`；明确区分分布式系统、API、面向对象和前端系统设计 | 根据主题自行转写场景题，不复制第三方课程正文 | 高 |

## 数据处理

1. 通过 GitHub API 核验仓库许可证和默认分支；记录访问日期及提交 SHA。
2. 行为题保留公开问题文本；去除图片、链接追踪参数和任何潜在个人信息。
3. 算法/系统设计题只保留转写后的问题、技能、难度、追问和评分标准；不抓取或再分发 LeetCode 题干和答案。
4. 导入前按题目文本 SHA-256 去重，并要求在线来源具有 URL；导入脚本会写入 `sources`、`questions`、`skills`、`question_skills` 和 `graph_edges`。
5. `python backend/scripts/manage_knowledge.py validate --file data/approved-dataset.json` 通过后，再执行带 `--prune` 的导入，使活动集合只包含公开数据。

## 可复核命令

```powershell
python backend/scripts/manage_knowledge.py validate --file data/approved-dataset.json
python backend/scripts/manage_knowledge.py import --file data/approved-dataset.json --prune
python backend/scripts/manage_knowledge.py stats
python backend/scripts/manage_knowledge.py sources --limit 20
```

本地完整开发库最近一次导入结果为 31 条活动题目、41 条历史总记录（10 条软删除）、72 个技能节点和 114 条图边；CPU 生产库从 approved 数据集全新初始化，当前为 31 条活动题目、64 个技能节点和 94 条图边。两者均保留来源元数据。

## 未解决限制

- 行为题来自公开汇总页面，不能推断真实公司当前面试频率或官方流程。
- 算法题转写保留了概念和题名，但需要在产品中继续展示“转写”标记，并定期重新核验上游许可证。
- Hugging Face `K-areem/AI-Interview-Questions` 数据卡未声明许可证，本次没有导入其原文；`liquidslr/leetcode-company-wise-problems` 也未找到明确许可证，仅保留候选来源。
- 岗位数据和 O*NET/ESCO 技能 taxonomy 尚未写入活动题库，后续可按同样的来源字段和版本策略单独导入。
- 强模型部署变量已注入 CPU 主机，但当前第三方网关返回 HTTP 401；轮换有效密钥后无需改代码，只需更新 `.env` 并重启 backend。
- GPU 主机当前的 vLLM 由既有主机启动服务管理，未启用 API key；模型端口不应开放公网。CPU 主机通过受限 SSH 隧道访问它，隧道单元文件为 `backend/deploy/aiic-model-tunnel.service`。
- CPU 主机外网 TCP/8080 是否可访问取决于腾讯云安全组；若访问超时，需要添加入站 8080 规则，同时保持 5432、8000 和 18000 关闭。

## Claim-to-source ledger

| 主张 | 来源 | 访问/版本 | 备注 |
| --- | --- | --- | --- |
| Yangshun 仓库为 MIT | [GitHub repository metadata](https://api.github.com/repos/yangshun/tech-interview-handbook) | 2026-08-30；提交 SHA 如上 | API 返回 `license.key=mit` |
| 行为面章节包含公司分组问题 | [behavioral-interview-questions.md](https://github.com/yangshun/tech-interview-handbook/blob/main/apps/website/contents/behavioral-interview-questions.md) | 2026-08-30 | 公开汇总，不是官方频次统计 |
| 算法清单覆盖数组、图、DP、链表、栈、树 | [algorithms directory](https://github.com/yangshun/tech-interview-handbook/tree/main/apps/website/contents/algorithms) | 2026-08-30 | 题目正文未复制 |
| 系统设计分类含分布式、API、OOD、前端 | [system-design.md](https://github.com/yangshun/tech-interview-handbook/blob/main/apps/website/contents/system-design.md) | 2026-08-30 | 题目为转写 |
