# Alpha 化工安全知识图谱：EDC+R 设计与现行抽取流程

- 文件沿用 `edc_r_pipeline_v1_design.md`，便于原有引用定位；原始 v1.0 设计稿（2026-08-25）保存在 [历史原稿](edc_r_pipeline_v1_design_20260825_archive.md)，本文只描述当前实现与差距。
- 修订：2026-10-06；性质：**现行实现说明 + 未完成设计清单**，不是一次新的抽取任务。
- 适用项目：`/root/autodl-tmp/chemical_kb`；Schema：`data/kg/schema_v1.json`（15 类实体、32 类关系）。
- 本文中的数量是 2026-10-06 的断点快照。实时进度以服务器执行 `python -m scripts.legacy_progress` 的结果为准。

## 1. 与原设计相比，现在哪里不同

原稿设想“规则优先 + Schema/Case 检索增强 + LLM 兜底，所有断言全部人工审核，并从人工结果构建 Success/Failure Case”。当前已实现 EDC 的主要模块，但**全库批处理并不是完整 EDC+R+Case 闭环**：它调用 `KGExtractionPipeline(retriever=None)`，未传入 `case_retriever`；`Definer` 和 `Canonicalizer` 的 LLM 兜底默认也未开启。Schema Retriever、Case Retriever 等模块存在，不能据此推断它们已参与这次全库抽取。

当前批量路线为：

```text
已解析文档的切片元数据
  → 按文档轮转选择 queued 切片
  → Document Router + Rule Extractor
  → Qwen 批量提取 mentions / 关系短语 / 属性 / 条款与要求
  → Definer（词典与类型/方向规则）+ Canonicalizer（规则/词典，未决者保留 provisional）
  → Assertion Builder + Schema Validator
  → SQLite 候选层（记录校验结果和原文引句是否命中）
  → 静态检查 + 独立的 Qwen 语义审核
  → 发布前再次核验来源、Schema、审核方法和重复项
  → reviewed.jsonl 的 approved 版本 → Explorer 图谱；Neo4j 可选同步
```

“抽取出候选”“通过 Schema”“引句匹配”“语义审核有效”“已发布图谱”是不同状态，不可用候选数代替已审核关系数。

## 2. 当前数据范围与断点

| 数据集 | 来源和范围 | 断点 / 私有位置 | 2026-10-06 状态 |
|---|---|---|---|
| 主库 | `data/vector_store/index_metadata.json`；1,061 份文档、24,606 个切片 | `data/kg/batch_extraction/corpus.sqlite` | `done=713`、`empty=1,184`、`extraction_failed=309`、`queued=22,400`；抽取进程与自动跟进已暂停 |
| 主库候选 | 从上述已处理切片产生 | 同一 SQLite 的 `assertions`、`candidate_audits` | 候选 17,506；原文引句匹配 15,410；审核记录 100（`valid=7`、`reject=3`、`needs_review=90`）。这些数字不代表已发布数量 |
| 旧文档正文 | 152 份旧文档的 `document_versions.content`，仅提取文本，无原 DOC/DOCX/PDF 二进制 | 私有 `data/legacy/hazmat_legacy.sqlite`、`body_chunks_metadata.json`、`body_corpus.sqlite` | 以 1,800 字符窗口、600 字符重叠生成 2,775 片；全部 queued |
| 旧关系 | 旧库 3,613 条关系，需重新找证据 | 私有 `legacy_relation_audits` 等表 | 110 条找到邻近原文，待语义审核；3,503 条缺邻近原文证据；不会因导入而自动入图 |
| 旧正文向量 | BGE-M3 重建，与旧 `text-embedding-v4` 向量分开 | 私有 `data/legacy/reembed.sqlite`、`faiss.index` | 0 / 2,775，尚未开始 |

旧库的 7,927 个历史切片可用于关键词检索和追溯，但它们没有覆盖旧文档的全部正文；`data/legacy/corpus.sqlite` 的旧切片队列不作为本次**完整正文**抽取队列。旧正文已加入私有关键词索引；抽取关系和重建向量是后续独立任务。旧库及其派生索引、审核结果不上传公开 GitHub。

最新已知主库持久快照：`/autodl-fs/data/alpha-corpus-checkpoints/corpus_paused_20261004_093143.sqlite`。恢复时先检查现有主库；仅主库缺失或损坏才使用通过完整性检查的快照。

## 3. 主库切片抽取：现在实际做了什么

入口：`scripts/kg/extract_corpus.py`。输入是**已经解析、切片、建立元数据的文本**；这个阶段不重新读取 PDF、DOC 或 DOCX。它按文档轮转，每份文档先处理一个切片，再进入下一轮，避免长文档独占前期处理。当前运行习惯是 GPU 每批 4 片，单个 Qwen 进程；`--batch-size 4` 不等于 4 个独立模型进程。

每片经过 `core/kg/pipeline.py`：

1. `DocumentRouter` 根据文档类型区分事故、标准、法规等；`RuleExtractor` 提取可确定的编号、数值、模态词和章节提示。
2. `Extractor` 让 Qwen 生成实体提及、开放关系短语、属性和规范要求。批量输出若解析失败会退回逐片处理；仍失败则记录 `extraction_failed` 或 `error`，不伪造关系。
3. `Definer` 将开放谓词映射到现有 Schema，并用主客体类型判断方向；默认使用词典/规则，不对每个谓词再调用 LLM。无法可靠映射的内容保持未决。
4. `Canonicalizer` 使用化学品词典和部分强标识规则；其余实体可能保留带文档 ID 的 `provisional` 身份。**这一步尚不能视为全局实体去重完成**。
5. `AssertionBuilder` 构造带 `source_doc_id`、`source_chunk_id`、`source_text_quote` 的断言；`AssertionValidator` 写入 Schema 校验结果。
6. `extract_corpus.py` 去掉空白后检查引句是否为来源切片的连续子串，写入 `evidence_ok`。这一检查只能证明引句出现过，**不能单独证明关系语义和方向正确**。

每个切片及其候选在同一 SQLite 事务中保存。状态含 `queued`、`done`、`empty`、`extraction_failed`、`error`；默认只选 `queued`。待 queued 全部处理后，才用 `--retry-failed` 单独重试失败切片。中断后从现有 SQLite 继续，不重新导入或清空结果。

## 4. 候选审核与发布：两道独立闸门

### 4.1 主库候选

`scripts/kg/audit_corpus_candidates.py` 只审核尚无审核记录的候选：

- 静态阶段：Schema 未通过或引句不匹配者标 `needs_review`，不进入自动有效集合。
- 语义阶段：将原文、候选断言和关系定义一起交给 Qwen，检查主客体、谓词方向、限定条件及数值。结果为 `valid`、`reject` 或 `uncertain`，连同方法、时间和理由写入 `candidate_audits`。`--static-only` 只做静态检查；语义阶段另行运行，且会占用 GPU。

审核脚本**不直接写图谱**。`scripts/kg/publish_audited_corpus.py` 仅接收 `valid` 且 `method=llm-semantic-v1` 的记录，并重新核对 Schema、来源文档/切片 ID、原文引句和重复三元组；通过后向 `data/kg/review/reviewed.jsonl` 追加 approved 审核版本，先保存旧文件备份。运行前应先 `--dry-run`。

这条批量发布路径是**模型语义审核 + 确定性门禁**，`reviewed_by` 记为 `alpha-semantic-audit`；并非原稿所写的“每条都由真人手工点击批准”。页面上的人工审核/修订仍是另一条可用路径。如要求所有新关系最终经人确认，应将批量发布改为导入人工待审队列，不能把模型 `valid` 当作人工签核。本文件只记录现状，不改变该治理规则。

### 4.2 旧库原有关系

`scripts/legacy_relation_audit.py` 在旧切片与全部 152 份文档正文中寻找主客体邻近的来源片段；同现不等于关系成立，因此它只恢复证据候选，批准数仍为 0。`scripts/legacy_semantic_review.py` 再将旧谓词映射到当前 Schema，检查 domain/range、含双方名称的逐字引句，以及第二次独立语义判断。只有通过者才进入私有 `data/legacy/reviewed.jsonl`；无证据的 3,503 条不能直接入图。

### 4.3 旧文档全文新抽取

旧库关系复审之外，完整正文切片在独立 `body_corpus.sqlite` 中走与主库相同的抽取及候选审核。执行时必须同时指定 `--metadata data/legacy/body_chunks_metadata.json` 和 `--db data/legacy/body_corpus.sqlite`；通过 `scripts.legacy_publish_corpus` 的来源、Schema、语义审核和去重检查后，才写入私有审核版本。不能把历史的 `data/legacy/corpus.sqlite` 队列误当全文队列。

## 5. 旧设计中 R 与 Case 的真实状态

| 原稿设计 | 当前状态 | 后续若启用需核验 |
|---|---|---|
| Schema Retriever：BGE-M3 检索 Schema 元素并注入抽取 Prompt | 仓库中有 `schema_retriever.py` 和 Schema 索引，但全库入口传 `retriever=None`，本轮未注入 | 对比同一金标准样本中有/无检索的正确率与时延；不能只凭模块存在声称已启用 |
| Success / Failure Case 检索与反思 | 有 Case Repository、Retriever、Builder 模块；全库入口未传 `case_retriever` | 先确认 verified case 质量、权限和数量，再做分组检索与消融；Failure 必须区分错误输出和正确修订 |
| Entity Repository 向量消歧 + 全局实体去重 | 当前 Canonicalizer 以词典/规则及文档内 provisional ID 为主；全局实体注册与冲突治理是另外的后处理/审核路径 | 强 ID、别名和跨文档消歧须有可回溯依据；避免误合并 |
| 每条候选全部人工审核 | 页面支持人工查看、修订和版本历史；批量流程目前可由模型语义审核后发布 | 明确最终批准权限；对高风险关系至少做人审抽样或设最终人工闸门 |
| 审核结果自动生成 Case 并反馈下一片 | 模块存在，但全库批处理未形成自动闭环 | 需单独验证闭环不会放大错误，建立金标准和错误复发率指标 |

项目的**问答/检索**另有关键词、向量、图检索与 RRF 融合。它与这里的**关系抽取时 Schema/Case 检索注入**不是同一条调用路径，不能混为一谈。

## 6. 图谱、存储与可追溯性

| 层 | 当前存储 | 作用 |
|---|---|---|
| 主库候选 | `data/kg/batch_extraction/corpus.sqlite` 的 `chunks`、`assertions`、`candidate_audits` | 保留抽取结果、失败及审核理由；候选尚不等于图谱关系 |
| 主库已审核版本 | `data/kg/review/reviewed.jsonl` | approved / modified / rejected 的版本历史；有效投影供 Explorer 使用 |
| 旧库正文与证据 | 私有 `data/legacy/hazmat_legacy.sqlite`、`body_chunks_metadata.json`、`body_corpus.sqlite` | 旧文档正文、重切片、旧关系证据和独立断点 |
| 旧库已审核版本 | 私有 `data/legacy/reviewed.jsonl` | 旧关系及旧全文抽取合格关系的审核版本 |
| Neo4j | `scripts/kg/sync_to_neo4j.py` 可选择同步 | 当前不是抽取断点的唯一来源；连接不可用时仍能从审核 JSONL 展示图谱 |

关系的来源应保留文档/切片 ID、逐字引句及审核版本。时间字段（如 `valid_from`、`valid_to`）只有在来源明确支持时填写；不能把审核时间当作关系生效时间。图谱上的节点/边数取决于有效审核版本，不随候选 SQLite 自动增加。

## 7. 继续运行时的顺序与边界

当前**暂停**；修改本文档不会启动任何 GPU 任务。恢复前先查是否已有抽取进程、现有主库完整性和最新在线快照；只有主库缺失或损坏才恢复快照。不要覆盖其他窗口正在修改的代码。

1. 主库：只续跑 `queued`；完成后单独重试 `error` / `extraction_failed`，核对仍失败的原因。
2. 主库审核：先静态检查，再运行语义审核；`publish_audited_corpus.py --dry-run` 核查数量，按既定审核权限决定是否发布。
3. 旧关系复审：检查 110 条有来源候选的语义和 Schema；3,503 条无邻近证据者保留 `needs_source`，不批量批准。
4. 旧全文：仅用 `body_chunks_metadata.json` + `body_corpus.sqlite` 续跑 2,775 片，随后静态/语义审核、dry-run、发布合格关系。
5. 向量：GPU 空闲时用 `scripts.legacy_reembed` 对 2,775 个旧正文切片重建 BGE-M3 私有 FAISS；它改善检索，不代替关系审核。
6. 同步与备份：按需同步 Neo4j；SQLite 写入期间用在线 backup API 生成快照并执行 `PRAGMA integrity_check`。主库快照放 `/autodl-fs/data/alpha-corpus-checkpoints/`，旧库私有备份放 `/autodl-fs/data/alpha-legacy-import/`。不得只复制有 WAL 写入中的主文件。

单个 Qwen GPU 重任务依次运行，避免同时抽取、语义审核和向量重建争用显存。旧 `text-embedding-v4` 向量不与 BGE-M3 索引混用。主库完整进度另见 `docs/CORPUS_RELATION_RUN.md`，旧库操作细节见 `data/legacy/README.md`。

## 8. 验收口径与未完成事项

- 覆盖：主库 `queued=0`；失败切片已重试或逐项留有原因；旧全文 2,775 片也达到同样状态。不能用“有候选”代替“全库覆盖”。
- 证据：每条发布断言能回查来源文档、切片和逐字引句；Schema、方向、限定条件及数值检查有审核记录。
- 发布：实际有效关系数按 reviewed 版本与图谱投影统计，分别报告主库、旧关系复审、旧全文新抽取；报告拒绝、未决和无来源数量。
- 检索：旧正文的私有关键词索引与 BGE-M3 FAISS 均可查询；不泄露旧正文到 GitHub。
- 质量：建立跨事故、标准、法规的人工金标准，统计实体/关系精确率和召回率、无来源率、方向错误、跨来源冲突、误合并及人工修订率。目前没有足够证据宣称原稿的 A–F 消融、Case 学习闭环或 Failure Recurrence Rate 已完成。

原稿提出的完整 EDC+R+Case 体系仍可作为后续演进方向，但启用前必须通过同一金标准和安全闸门验证，不能让设计意图覆盖当前代码与数据库事实。
