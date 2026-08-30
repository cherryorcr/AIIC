# AIIC 性能测试方案与基线记录

## 1. 目标与范围

验证在单机 Compose 部署（CPU 业务服务器 + GPU 模型网关）下，核心接口延迟与吞吐满足训练场景需要，并为 NFR-07（多实例高并发）迁移提供决策数据。

关键事实：系统对模型调用有确定性降级（规则 fallback），因此性能分为两条路径分别测量：

- **规则路径**：模型未配置或不可用，全链路本地计算——决定系统延迟下限，也是模型故障时的用户体验。
- **模型路径**：本地 Qwen 网关 / 第三方强模型参与——延迟主要由模型推理决定（前端与 Nginx 已按此把这两类 POST 超时放宽到 120s/180s 且禁止盲重试）。

## 2. 已测基线（规则路径，`measured`）

测试方式：FastAPI TestClient 进程内压测（无网络开销），SQLite 临时库，加载 approved 数据集（32 条活动题）；每接口 10-30 次取 p50/p95。环境：Linux 容器、Python 3.10，2026-08-30。

| 接口 | p50 | p95 | 说明 |
| --- | --- | --- | --- |
| GET /api/v1/health | 0.9 ms | 1.0 ms | 含 DB 探测 |
| GET /api/v1/questions?q=动态规划 | 3.2 ms | 4.2 ms | 词法+哈希向量召回 + 语义去重 |
| GET /api/v1/workspace/overview | 8.7 ms | 11.0 ms | 多表聚合准备度 |
| POST /api/v1/sessions | 27.9 ms | 32.1 ms | RAG 召回 + 会话落库（规则出题） |
| POST /sessions/{id}/turns | 63.3 ms | 68.2 ms | Turn+Feedback+报告快照三写（规则评分） |
| POST /sessions/{id}/algorithm/run | 27.0 ms | 27.9 ms | 含受限 Python 子进程启动与判题 |

同环境回归套件 40 个测试 6.2 秒全部通过。

结论：规则路径全部接口在数十毫秒内完成，瓶颈不在业务层；生产延迟预算应主要分配给模型推理和网络。注意本基线为进程内测量，不含 Nginx 反代与公网 RTT；SQLite 单连接 + 全局锁意味着该基线不代表并发吞吐（见 §4）。

## 3. 模型路径测量方案（`planned`，需在生产环境执行）

`model_invocations` 表已记录每次调用的 provider、model、latency_ms、tokens、cost_usd、attempt 和 fallback_reason，可直接作为测量数据源，无需额外埋点：

```sql
SELECT task, provider,
       COUNT(*) AS calls,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95,
       AVG(cost_usd) AS avg_cost,
       SUM(CASE WHEN status <> 'ok' THEN 1 ELSE 0 END)*1.0/COUNT(*) AS err_rate
FROM model_invocations GROUP BY task, provider;
```

测量项与验收阈值（初始值，按真实用户耐受度校准）：

| 项 | 指标 | 初始阈值 |
| --- | --- | --- |
| 首题生成（本地 Qwen 优先） | p95 | ≤ 15 s |
| 回答评分（强模型优先） | p95 | ≤ 30 s；≤ 120 s 前端超时且不丢输入 |
| 匹配评分（快照未命中） | p95 | ≤ 30 s；命中快照 ≤ 200 ms |
| fallback 率 | 按 task | < 10%（超出说明 provider 不稳，需告警） |
| 双 4090 vLLM（32K ctx / 64 seq） | 显存 | 实测约 42.6 GB/卡（48 GB 卡），并发扩容前不可再加大 ctx |

## 4. 并发与容量测试方案（`planned`）

- 工具：`locust` 或 `k6`，从公网入口（Nginx :8080）打压，场景脚本按"登录→建会话→3 轮回答→完成"编排。
- 阶梯：1 / 5 / 10 / 25 并发虚拟用户；每档 5 分钟，观察 p95、错误率与 PostgreSQL 连接数。
- 已知瓶颈假设（按序验证）：
  1. 模型网关吞吐（单实例 tensor-parallel vLLM，64 序列上限）；
  2. 后端单连接数据库访问（`DATABASE_POOL_SIZE` 配置已预留但未实现连接池）；
  3. 算法沙箱子进程创建（每次运行 fork 一个受限 Python，进程数上限 16）。
- 通过标准：25 并发下非模型接口 p95 < 500 ms、错误率 < 1%、无数据错写（快照不可变、幂等重放约束保持）。
- 未达标时的既定演进路径：PostgreSQL 连接池 → Redis 限流/缓存 → GPU 每卡单副本 + 网关轮询 → 独立沙箱 runner。

## 5. 报告与维护规则

1. 每次性能测试记录：日期、commit、拓扑、数据集规模、结果表和结论，追加到本文件 §6。
2. 涉及模型的结论必须注明 provider 与模型名，不同模型的数字不可互相比较。
3. 规则路径基线在 `db.py`、`rag.py`、`interview.py` 大改后需重跑（§2 的脚本化压测方式）。

## 6. 历史记录

| 日期 | 范围 | 结果 |
| --- | --- | --- |
| 2026-08-30 | 规则路径进程内基线（§2） | 全部接口 p95 < 70 ms；40/40 测试通过 |
