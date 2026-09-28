# 化工安全知识库：检索与图谱升级（Agent 维护说明）

项目根目录：`/root/autodl-tmp/chemical_kb`。原有问答、上传、文档管理、Wiki、KG 审核和 Cytoscape 图谱页继续沿用。

## 新增模块与数据

- `core/knowledge.py`：半开区间时态判断、SQLite FTS5/BM25、加权 RRF、冲突候选、重复实体候选及 JSON-LD/Turtle/GraphML/CSV 导出。
- `core/hybrid_retriever.py`：向量、关键词、已审核图谱证据三路召回，先按时点过滤，再按 RRF 融合，最后复用原 BGE reranker。
- `core/entity_registry.py`：审核人记录可撤销的全局别名；原断言不会被改写。
- `scripts/kg/knowledge_ops.py`：离线建索引、审计与导出入口。
- `app/pages/7_Knowledge_Graph.py`：时点、冲突、重复实体、四种导出格式；`app/_theme.py` 与 `app/_graph.py` 提供深色探索工作台。

关键词索引：`data/search/keyword.sqlite`，由已有的 `data/vector_store/index_metadata.json` 构建。首次部署执行：

```bash
/root/miniconda3/envs/kb/bin/python scripts/kg/knowledge_ops.py build-index
```

原有新增文档流程调用 `core/updater.py` 后会重建该索引。向量与关键词均按 `chunk_id` 融合。Neo4j 不可用时，图路会读取人工审核 JSONL；问答仍保留向量和关键词通路。

## 时态语义

`valid_from` 包含，`valid_to` 不包含。没有生效日期的旧记录视为开放区间；`recorded_at` 是写入时间，不能代替生效时间。非法区间不参加时点查询或冲突比较。图谱页和问答页默认使用当天，可选历史日期。旧断言没有日期时，历史查询不能凭空推断其过去的实际效力。

## 审核边界

冲突检测把“同一主体、关系、重叠生效区间、不同来源、不同对象”标记为待核实，不自动认定某条为真。它是保守候选规则：多值关系可能产生误报，别名/隐含冲突可能漏报。实体候选由相同类型和规范化名称生成；只有人工输入审核人并确认后才会产生别名。撤销操作写入审计日志。源断言和审核历史保留。

## 导出

只导出已人工通过或修改的断言。PROV-O 输出含 Document、Chunk、Assertion 的 `prov:Entity`，抽取 `prov:Activity`，审核 `prov:Agent`，并连接 `prov:wasDerivedFrom`、`prov:used`、`prov:wasGeneratedBy`、`prov:wasAssociatedWith`。IRI 使用 `urn:chemical-kb:` 命名空间。GraphML 与 CSV 保留原始 ID 和来源；导出可以按生效时点过滤。

## 验证

```bash
/root/miniconda3/envs/kb/bin/python -m unittest discover -s tests -p test_knowledge_upgrade.py -v
/root/miniconda3/envs/kb/bin/python -m compileall -q core app scripts/kg/knowledge_ops.py
/root/miniconda3/envs/kb/bin/python scripts/kg/knowledge_ops.py audit
```

仅在人工确认候选后执行实体合并。重建 Neo4j 投影时应使用审核过的别名；旧 Neo4j 节点暂不自动物理删除。

