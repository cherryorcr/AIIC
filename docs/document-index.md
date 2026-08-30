# AIIC 软件工程文档索引

## 1. 文档目的

本索引定义 AIIC（AI Interview Coach）项目的文档入口、适用读者和证据边界。文档以当前仓库实现为基线；当“目标设计”与“当前实现”不一致时，必须标明状态，不得把规划内容写成已交付能力。

## 2. 文档地图

| 层次 | 文档 | 主要读者 | 当前状态 |
| --- | --- | --- | --- |
| 产品 | `docs/product-memo.md` | 评审、产品、开发 | 已补齐，真实访谈部分待回填 |
| 需求 | `docs/research-plan.md` | 产品、研究、评审 | 已有，包含问卷与研究规范 |
| 需求 | `docs/use-case-design.md` | 产品、前后端、测试 | 已补齐 |
| 架构 | `docs/system-overview-design.md` | 全体开发、部署人员 | 已补齐 |
| 详细设计 | `docs/system-detailed-design.md` | 前后端、算法、运维 | 已补齐 |
| 接口 | `docs/api-design.md` | 前后端、测试 | 已补齐，作为详细接口说明 |
| 数据 | `docs/database-design.md` | 后端、数据管理员、运维 | 已有并与当前 schema 对齐 |
| 质量 | `docs/test-plan.md` | 开发、测试、评审 | 已补齐 |
| 追踪 | `docs/requirements-traceability.md` | 项目负责人、评审 | 已补齐 |
| 决策 | `docs/adr.md` | 全体开发、后续维护者 | 已补齐 |
| 来源治理 | `docs/report-source.md`、`data/README.md` | 数据管理员、评审 | 已有，强调许可和来源 |
| 部署运维 | `docs/deployment-runbook.md` | 部署、运维 | 已有，包含 CPU/GPU 双主机拓扑 |
| 共享契约 | `docs/contracts.md` | 前后端 | 已有，兼容历史接口；新接口详见 `api-design.md` |

## 3. 证据标记

- `implemented`：代码和测试中可以直接核验。
- `verified_public`：来源 URL、许可证和访问信息已经登记。
- `synthetic_mock`：为了展示流程而生成的模拟数据，不代表真实调查结论。
- `planned`：设计已确定，但当前代码尚未实现或未完成验收。
- `needs_validation`：需要真实用户、人工标注或部署实验验证。

## 4. 维护规则

1. 新增 API、数据字段或场景时，先更新 `docs/contracts.md` 或 `docs/api-design.md`，再修改代码。
2. 修改用户可见行为时，同时更新用例、需求追踪矩阵和测试计划。
3. 新增外部题目时，先更新来源台账，确认许可证、访问时间、脱敏和是否允许再分发。
4. Product Memo 只写已证实事实；模拟数据、用户需求输入和假设必须分开表述。
5. 每次发布记录版本、日期、变更原因和未解决风险。
