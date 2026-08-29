# Online interview-data source manifest

更新时间：2026-08-30（Asia/Shanghai）

本文件记录已核验的公开来源和使用边界。它不是“高频面试题”结论，也不代表所有原始内容都可以再发布。`license_status` 必须在每次同步前重新确认。

| source_id | 来源 | 可得到的内容 | license_status | 建议用途 | 注意事项 |
| --- | --- | --- | --- | --- | --- |
| hf-kareem-ai-interview | [K-areem/AI-Interview-Questions](https://huggingface.co/datasets/K-areem/AI-Interview-Questions) | 英文 AI/ML、数据科学、系统设计、DSA 问答；train 4,653 条，eval 1,164 条 | 未在数据卡中声明 | 原型检索和字段设计参考 | 可通过 Hugging Face datasets-server 读取样例；在确认许可证前不要把原文提交到公开仓库 |
| github-yash-ai-interview | [Yash-Jagtap/AI-Interview-Questions-Dataset](https://github.com/Yash-Jagtap/AI-Interview-Questions-Dataset) | Parquet 格式的 AI/ML、数据科学、系统设计、DSA 数据；README 声称来源于上面的 Hugging Face 数据集 | 仓库声明 MIT；上游数据许可仍需单独核验 | 可作为候选导入源 | 遵守 MIT attribution，并核对上游数据权利，不因镜像仓库声明 MIT 就自动获得上游内容权利 |
| github-yangshun-handbook | [yangshun/tech-interview-handbook](https://github.com/yangshun/tech-interview-handbook) | 软件工程技术面、算法题和面试流程内容 | MIT（仓库 LICENSE） | 算法/技术面知识节点和题型标签 | 保留版权与许可证；仓库内外链内容不自动继承 MIT |
| github-kdn-interviews | [kdn251/interviews](https://github.com/kdn251/interviews) | 数据结构、算法、复杂度和面试准备材料 | MIT（仓库 LICENSE） | 算法概念、评分 rubric、追问模板 | 更适合作为学习材料/题型种子，不代表真实公司频次 |
| github-liquidslr-company | [liquidslr/leetcode-company-wise-problems](https://github.com/liquidslr/leetcode-company-wise-problems) | 按公司和时间窗口整理的 LeetCode 题目链接/频次列表；页面说明更新至 2025-06-20 | 未找到明确许可证；LeetCode 内容有独立权利 | 仅作候选题目发现和外链索引 | 不复制题干、解答或付费内容；发布前确认源仓库与 LeetCode 条款 |
| onet-31 | [O*NET Database](https://www.onetcenter.org/database.html) | 职业、任务、技能、知识和工作活动 | CC BY 4.0（O*NET 31.0） | Job/Skill 节点、岗位技能标准化 | 按要求署名；修改后标注修改内容，不暗示 USDOL 背书 |
| esco | [ESCO classification](https://esco.ec.europa.eu/en/about-esco/what-esco) | 3,039 个职业、13,939 个技能，支持多语言和 RDF/CSV/JSON-LD 下载 | 下载条款需在导出时确认 | 职业与技能 taxonomy、跨语言归一化 | 只使用官方下载/API，保存版本号和下载日期 |

## 已执行的只读核验

- 通过 Hugging Face datasets-server 读取了 `hf-kareem-ai-interview` 的 20 条训练集样例，确认字段只有 `text`，总训练规模为 4,653 条。
- 样例内容采用 `[INST] question [/INST] answer` 格式，需先解析问题和答案，再进入 GraphRAG。
- 因该数据卡未声明许可证，原始样例没有复制进本仓库；后续应在 `data/raw/` 中下载，并通过 `.gitignore` 防止误提交。

## 推荐导入字段

```text
source_id, source_url, source_title, source_version, license,
accessed_at, language, process_type, role, question, answer_or_rubric,
skills, difficulty, pii_redacted, source_confidence, redistribution_allowed
```

## 题目类型建议

- 算法题：数组、链表、树、图、动态规划、贪心、二分、复杂度分析
- 技术概念：操作系统、数据库、网络、语言特性、系统设计
- 行为题：项目经历、冲突处理、失败复盘、领导力
- 压力面：连续追问、限时重答、质疑证据
- 案例面：指标拆解、假设验证、产品权衡
- 科研面：研究假设、实验设计、局限性

