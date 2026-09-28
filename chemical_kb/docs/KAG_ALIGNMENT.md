# KAG 架构参考与 Alpha 关系治理实现

参考：[OpenSPG/KAG 官方仓库](https://github.com/OpenSPG/KAG) 及其 README 中的知识构建、schema 约束、知识与文本片段互索引和推理检索设计。

## 已实现的映射

| KAG 思路 | Alpha 当前实现 |
| --- | --- |
| Schema 约束知识构建 | `core/kg/relation_catalog.py` 校验断言字段、实体类型、关系 domain/range 与时间字段 |
| 知识与原文片段互索引 | `/api/reviews/<id>/source` 依据文档、页码和引句回查原文片段；审核页并列显示引句和片段 |
| 关系生命周期与溯源 | 审核 JSONL 追加新版本，按断言 ID 取最新版投影；历史和审计记录保留 |
| 知识检索 | 原项目的关键词、向量、图检索与 RRF 保持运行；新关系投影进入图谱与导出 |

这是一种架构参考与局部改造，当前没有直接接入 KAG 的 `kg-builder`、`kg-solver` 或 OpenSPG 服务。现有项目的数据规模、schema 和索引方式继续由本项目管理。

## 审核数据规则

- `pending.jsonl` 保存尚无审核版本的断言；`reviewed.jsonl` 是只追加历史。
- 同一断言的最新审核版本决定当前状态，历史版本用于追溯。
- `approved` / `modified` 进入有效图谱；`rejected` 不进入有效图谱，但继续在全量关系目录中显示。
- 提交编辑时使用 `expected_review_id` 防止页面上的旧版本覆盖更新，并在提交前验证 schema。
- 本轮人工审计的详情保存在 `data/kg/review/agent_audit_20260928.jsonl`，执行前备份为同目录下 `*.pre_alpha_audit_20260928.jsonl`。

## 后续接入 KAG 的边界

若未来需要完整 KAG 推理引擎，先统一 schema 与实体 ID，再评估 OpenSPG 图存储及 `kg-builder` / `kg-solver` 对现有 24,606 个片段的增量导入成本。当前的 3D 图谱是前端呈现层，不改变知识结构和检索排序。
