# Alpha 化工安全知识图谱：EDC+R 设计与现行抽取流程

- 文件沿用 `edc_r_pipeline_v1_design.md`，便于原有引用定位；原始 v1.0 设计稿（2026-08-25）保存在 [历史原稿](edc_r_pipeline_v1_design_20260825_archive.md)，本文只描述当前实现与差距。
- 修订：2026-10-06；性质：**现行架构说明 + 已启动的 EDC+R+Case 续跑方案**。
- 适用项目：`/root/autodl-tmp/chemical_kb`；Schema：`data/kg/schema_v1.json`（15 类实体、32 类关系）。
- 数量表是 2026-10-06 续跑前快照，不是实时值。GPU/检索脚本使用 `/root/miniconda3/envs/kb/bin/python`；基础进度可用 `python3 -m scripts.legacy_progress` 查看。

## 1. 与原设计相比，现在哪里不同

原稿设想“规则优先 + Schema/Case 检索增强 + LLM 兜底，所有断言全部人工审核，并从人工结果构建 Success/Failure Case”。先前已处理切片使用 `KGExtractionPipeline(retriever=None)`。2026-10-06 起，**新 queued 切片启用 `--edc-r-case`**：CPU BGE-M3 检索 Schema 和已核对审核记录的 Success/Failure Case，再由 GPU Qwen 抽取；旧 done/empty 不重抽。Definer/Canonicalizer 的 LLM 兜底与审核后自动生成 Case 仍未启用。

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

| 数据集 | 来源和范围 | 断点 / 私有位置 | 2026-10-06 启动前快照 |
|---|---|---|---|
| 主库 | `data/vector_store/index_metadata.json`；1,061 份文档、24,606 个切片 | `data/kg/batch_extraction/corpus.sqlite` | `done=713`、`empty=1,184`、`extraction_failed=309`、`queued=22,400`；此为启动前数值，主库现已在 `screen alpha-edcr` 续跑 |
| 主库候选 | 从上述已处理切片产生 | 同一 SQLite 的 `assertions`、`candidate_audits` | 候选 17,506；原文引句匹配 15,410；审核记录 100（`valid=7`、`reject=3`、`needs_review=90`）。这些数字不代表已发布数量 |
| 旧文档正文 | 152 份旧文档的 `document_versions.content`，仅提取文本，无原 DOC/DOCX/PDF 二进制 | 私有 `data/legacy/hazmat_legacy.sqlite`、`body_chunks_metadata.json`、`body_corpus.sqlite` | 以 1,800 字符窗口、600 字符重叠生成 2,775 片；全部 queued |
| 旧关系 | 旧库 3,613 条关系，需重新找证据 | 私有 `legacy_relation_audits` 等表 | 110 条找到邻近原文，待语义审核；3,503 条缺邻近原文证据；不会因导入而自动入图 |
| 旧正文向量 | BGE-M3 重建，与旧 `text-embedding-v4` 向量分开 | 私有 `data/legacy/reembed.sqlite`、`faiss.index` | 0 / 2,775，尚未开始 |

旧库的 7,927 个历史切片可用于关键词检索和追溯，但它们没有覆盖旧文档的全部正文；`data/legacy/corpus.sqlite` 的旧切片队列不作为本次**完整正文**抽取队列。旧正文已加入私有关键词索引；抽取关系和重建向量是后续独立任务。旧库及其派生索引、审核结果不上传公开 GitHub。

本次切换批大小前的持久快照：`/autodl-fs/data/alpha-corpus-checkpoints/corpus_checkpoint_20261006_030001.sqlite`。恢复时先检查现有主库；仅主库缺失或损坏才使用通过完整性检查的快照。

## 3. 主库切片抽取：现在实际做了什么

入口：`scripts/kg/extract_corpus.py`。输入是**已经解析、切片、建立元数据的文本**；这个阶段不重新读取 PDF、DOC 或 DOCX。它按文档轮转，每份文档先处理一个切片，再进入下一轮，避免长文档独占前期处理。当前在 `screen alpha-edcr` 运行 `scripts/kg/run_edcr_case_corpus.sh`，单个 Qwen 进程、GPU 每批 4 片；`--batch-size 4` 不等于 4 个模型进程。

每片经过 `core/kg/pipeline.py`：

1. `DocumentRouter` 根据文档类型区分事故、标准、法规等；`RuleExtractor` 提取可确定的编号、数值、模态词和章节提示。
2. `Extractor` 让 Qwen 生成实体提及、开放关系短语、属性和规范要求。批量输出若解析失败会退回逐片处理；仍失败则记录 `extraction_failed` 或 `error`，不伪造关系。
3. `Definer` 将开放谓词映射到现有 Schema，并用主客体类型判断方向；默认使用词典/规则，不对每个谓词再调用 LLM。无法可靠映射的内容保持未决。
4. `Canonicalizer` 使用化学品词典和部分强标识规则；其余实体可能保留带文档 ID 的 `provisional` 身份。**这一步尚不能视为全局实体去重完成**。
5. `AssertionBuilder` 构造带 `source_doc_id`、`source_chunk_id`、`source_text_quote` 的断言；`AssertionValidator` 写入 Schema 校验结果。
6. `extract_corpus.py` 去掉空白后检查引句是否为来源切片的连续子串，写入 `evidence_ok`。这一检查只能证明引句出现过，**不能单独证明关系语义和方向正确**。

每个切片及其候选在同一 SQLite 事务中保存；新 `chunk_pipeline` 表记录运行模式与 Schema/Case 命中数。状态含 `queued`、`done`、`empty`、`extraction_failed`、`error`；默认只选 `queued`。待 queued 全部处理后，才用 `--retry-failed` 单独重试失败切片。中断后从现有 SQLite 继续，不重新导入或清空结果。

## 4. 候选审核与发布：两道独立闸门

### 4.1 主库候选

`scripts/kg/audit_corpus_candidates.py` 只审核尚无审核记录的候选：

- 静态阶段：Schema 未通过或引句不匹配者标 `needs_review`，不进入自动有效集合。
- 语义阶段：将原文、候选断言和关系定义一起交给 Qwen，检查主客体、谓词方向、限定条件及数值。结果为 `valid`、`reject` 或 `uncertain`，连同方法、时间和理由写入 `candidate_audits`。`--static-only` 只做静态检查；语义阶段另行运行，且会占用 GPU。

审核脚本**不直接写图谱**。`scripts/kg/publish_audited_corpus.py` 仅接收 `valid` 且 `method=llm-semantic-v1` 的记录，并重新核对 Schema、来源文档/切片 ID、原文引句和重复三元组；通过后向 `data/kg/review/reviewed.jsonl` 追加 approved 审核版本，先保存旧文件备份。运行前应先 `--dry-run`。

现有批量发布路径只有**模型语义审核 + 确定性门禁**，`reviewed_by` 记为 `alpha-semantic-audit`。用户已明确要求由 Codex Agent（本任务的我）审核，不设置人工审批。因此该脚本的 `valid` 只能算初审，不能直接声称“Agent 已审核”；本轮发布前必须加入第 7.1 节的 Agent 终审记录与发布闸门。页面人工修订功能仍可保留，但不构成本次流程的必经步骤。

### 4.2 旧库原有关系

`scripts/legacy_relation_audit.py` 在旧切片与全部 152 份文档正文中寻找主客体邻近的来源片段；同现不等于关系成立，因此它只恢复证据候选，批准数仍为 0。`scripts/legacy_semantic_review.py` 再将旧谓词映射到当前 Schema，检查 domain/range、含双方名称的逐字引句，以及第二次独立语义判断。现有脚本会在模型语义复审时自动导出通过项，并写入 `reviewed_by=adamin`。这既不能代表人工审核，也不能代表我已终审；在运行该写入流程前必须改成“只保存初审结果、待 Agent 终审后发布”，并修正审核者来源。无证据的 3,503 条保持 `needs_source`。

### 4.3 旧文档全文新抽取

旧库关系复审之外，完整正文切片在独立 `body_corpus.sqlite` 中走与主库相同的抽取及候选审核。执行时必须同时指定 `--metadata data/legacy/body_chunks_metadata.json` 和 `--db data/legacy/body_corpus.sqlite`；通过 `scripts.legacy_publish_corpus` 的来源、Schema 和去重检查后，才写入私有审核版本。现有发布脚本按 `decision=valid` 读取语义审核结果，但没有再次核对审核方法；运行前必须核实 `candidate_audits.method`。不能把历史的 `data/legacy/corpus.sqlite` 队列误当全文队列。

## 5. 旧设计中 R 与 Case 的真实状态

| 原稿设计 | 当前状态 | 后续若启用需核验 |
|---|---|---|
| Schema Retriever：BGE-M3 检索 Schema 元素并注入抽取 Prompt | 新 queued 切片已启用 CPU Schema 检索；47 项索引命中逐片入库，旧 done/empty 不重抽 | 对比同一金标准样本中有/无检索的正确率与时延；不能只凭模块存在声称已启用 |
| Success / Failure Case 检索与反思 | 已核对 61 个 verified Case 与审核记录的关联，并建成功 25、失败 36 的独立索引；新切片各最多注入 1 例 | 先确认 verified case 质量、权限和数量，再做分组检索与消融；Failure 必须区分错误输出和正确修订 |
| Entity Repository 向量消歧 + 全局实体去重 | 当前 Canonicalizer 以词典/规则及文档内 provisional ID 为主；全局实体注册与冲突治理是另外的后处理/审核路径 | 强 ID、别名和跨文档消歧须有可回溯依据；避免误合并 |
| 每条候选全部审核 | 当前静态/Qwen 初审可覆盖每条候选，但还没有 Codex Agent 终审断点 | 本轮由 Codex Agent 逐批复核并记录每条候选的终局决定；无人工审批 |
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

## 7. 本次运行原则和阶段闸门

**本次目标**：在保留现有断点的前提下完成主库 24,606 片及旧文档全文 2,775 片的关系候选抽取；对全部候选形成审核结论；仅把有原文、Schema 和语义依据的关系写入 reviewed 版本；最后重建旧全文的 BGE-M3 向量。任务按阶段推进，不把“切片处理完”称为“关系审核完”。

- **唯一写入者**：同一 SQLite 队列只允许一个抽取/审核写入进程；同一 GPU 时段只运行一个 Qwen 或 BGE-M3 重任务。60 GB 主存不能替代 24 GB 显存。批大小先沿用主库已跑通的 4；OOM 时下调到 2，再到 1，先看日志再重试。
- **断点优先**：不重新导入文档、不清空 SQLite、不重新处理 done/empty；仅在主库丢失或完整性检查失败时，才从已校验的持久快照恢复。旧库始终使用独立 DB 和元数据。脚本的 `--dry-run` 会调用数据库准备逻辑，不能视为纯只读预览。
- **审核口径**：静态检查和 Qwen 语义审核是初审；Codex Agent 对每条候选给出可追溯的最终结论。只有初审 `valid`、Agent 终审 `approved` 且发布闸门通过者入图；`reject`、`uncertain`、`needs_review` 和无来源旧关系保持未发布。高风险数值、跨来源冲突、全局实体合并和时态断言由 Agent 按原文重点复核。无需人工审批。
- **先检查再发布**：主库发布器仅要求 Qwen 初审 `method=llm-semantic-v1`；旧全文发布器目前只筛 `valid`；旧关系语义脚本还会自动导出。因此三个发布入口都必须接入 Agent 终审闸门后才用于本次正式发布，不能将 `reviewed_by=adamin` 或 `alpha-semantic-audit` 冒充 Agent 结论。
- **保留其他窗口改动**：运行前核对服务器脚本及数据库路径，不能用本地旧代码覆盖服务器。本文档操作不依赖 `scripts/kg/run_after_extract.sh`；该脚本含固定 PID，且不覆盖旧全文和最终发布。
- **安全停机**：`extract_corpus.py --max-seconds` 仅在批次之间停下；不要用 `kill -9` 代替正常结束。SSH 断线时使用 `screen` 保持任务；暂停后做在线快照。断点在 SQLite，而不是 shell 日志。

### 7.1 Agent 全量终审：发布前必须补齐的最小实现

用户指定**由本 Codex Agent 审核，不设置人工审批**。当前仓库只有 Qwen 初审与自动发布，无法仅靠把 `reviewed_by` 改名就满足这个要求。因此抽取可先按现有脚本续跑，正式发布之前由我补齐并验证以下最小改造：

1. 主库与旧全文分别在现有 SQLite 增加可恢复的 Agent 审核记录，至少保存 `assertion_id`、候选内容哈希、来源片段哈希、初审决定/方法、Agent 最终决定（`approved/rejected/needs_review/needs_source`）、逐条理由、审核时间及审核版本。候选或原文变化时旧结论失效，重新排队；每批事务提交，断线后只续未终审项。
2. 我逐批读取**全部**候选及原文，而不是只看 Qwen 判为 `valid` 的子集。确定性核对 Schema、主客体、引句逐字匹配和来源 ID；对语义、方向、单位、约束条件、法规生效时间、同名实体及跨来源矛盾做独立复核。原文无法支持时判 `rejected` 或 `needs_source`；证据仍有歧义时判 `needs_review` 并保持未发布。可使用 Qwen 帮助分析，但 Qwen 的输出只能作证据输入，不能直接冒充我的终审记录。
3. 主库和旧全文发布器只接受“Qwen 初审 `valid` + Agent 终审 `approved` + 内容哈希未变化 + 原文/Schema/去重再次通过”的断言。旧关系模型复审先只写初审，不自动导出；其 3,503 条无来源项记录为 Agent `needs_source`，有证据的 110 条逐条给出 Agent 结论后才发布。发布审核者真实标识为 `alpha-codex-agent`，同时保留 Qwen 初审方法，不再使用伪人工 `adamin`。
4. 加入可核验的 dry-run 统计：各库候选总数、未做 Qwen 初审数、未做 Agent 终审数、Agent 各决定数、可发布数、被来源/Schema/重复/冲突拦截数。用小批候选验证断点、哈希失效和发布过滤，再放开全库。未补齐这些门禁前，抽取与初审可继续，**自动发布暂停**。

Codex Agent 的终审要在实际运行时逐批执行并写入断点；计划文档或 Qwen 日志本身不代表我已审核。若任务因服务器关机或会话结束中断，下次从 Agent 审核记录继续。无需用户逐条操作，也不要求真人最后点击确认。
### 7.2 已启动的 EDC+R+Case 续跑与并行边界

主库从健康的 `corpus.sqlite` 只续跑 queued；启动前 `queued=22,400`。当前 `screen alpha-edcr` 执行 `scripts/kg/run_edcr_case_corpus.sh`，日志为 `data/kg/batch_extraction/edcr_case_20261006.log`。运行器用 `flock` 防止同库双写，按 6 小时窗口循环，每轮用 `scripts/kg/checkpoint_corpus.py` 对主库做在线备份和完整性校验。试跑库只用于验证，不并入主库。查看进度：

```bash
screen -ls
tail -n 30 /root/autodl-tmp/chemical_kb/data/kg/batch_extraction/edcr_case_20261006.log
cd /root/autodl-tmp/chemical_kb
python3 -m scripts.legacy_progress
```

容器内存限制为 60 GiB，单卡显存约 24 GiB。同一 GPU 同一 SQLite 队列不能直接开多个抽取进程：会重复领片并争用显存。已在独立试跑库验证批大小 4 无显存错误，先提高单进程批量；将来只有在实现事务级领片和测得总吞吐提升后才考虑多进程。主库抽取完成后才进入失败重试和 Agent 审核，自动发布闸门仍按第 7.1 节执行。
## 8. 服务器执行手册

以下命令均从服务器项目目录运行。主库 queued 阶段**已经在运行**；后续阶段只有在前一阶段满足闸门后才逐步执行。服务器现有 `/usr/bin/screen`、`/root/miniconda3/envs/kb/bin/python` 和 RTX 4090 D；续跑前无抽取进程，主库 `PRAGMA quick_check=ok`，磁盘可用空间约 33 GB（项目盘）和 443 GB（共享挂载的 `df` 读数）。

### 8.1 预检与在线断点

```bash
cd /root/autodl-tmp/chemical_kb
pgrep -af '[e]xtract_corpus|[a]udit_corpus_candidates|[l]egacy_semantic_review|[l]egacy_reembed' || true
python3 -m scripts.legacy_progress
df -h /root/autodl-tmp /autodl-fs
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
```

先核对脚本版本、主库路径和主库完整性；若已有进程，先确认其目标库，不启动第二个写入者。主库存在且检查正常时**不恢复快照**。需要保存主库时用 SQLite online backup API，不能只复制正在写入的 `corpus.sqlite` 主文件（WAL 中可能有未合并的事务）：

```bash
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3

source = Path("data/kg/batch_extraction/corpus.sqlite").resolve()
folder = Path("/autodl-fs/data/alpha-corpus-checkpoints")
folder.mkdir(parents=True, exist_ok=True)
name = "corpus_checkpoint_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".sqlite"
target = folder / name
building = folder / (name + ".building")
if not source.exists():
    raise SystemExit("主库不存在；先检查，不要自动创建空库")
with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=60) as old:
    if old.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise SystemExit("主库完整性检查失败；停止并核对最近的有效快照")
    with sqlite3.connect(building) as new:
        old.backup(new, pages=500)
        if new.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("快照完整性检查失败")
os.replace(building, target)
print(target)
PY
```

旧私有库使用仓库内备份器，并为每次备份指定新目录，以免覆盖上次快照：

```bash
python3 -m scripts.legacy_backup --out-dir "/autodl-fs/data/alpha-legacy-import/checkpoints/$(date -u +%Y%m%d_%H%M%S)"
```

至少在启动前、每个长运行时段结束后、失败重试前和发布前保存断点；确认备份工具报告成功，记录快照文件名及 `scripts.legacy_progress` 结果。恢复只在现有主库丢失/损坏时由 Agent 核对后执行，先验证目标快照的 `integrity_check` 和文档/切片规模；当前已知旧快照是 `corpus_paused_20261004_093143.sqlite`，但不应覆盖更新的健康主库。

### 8.2 主库：只跑 queued（已启动）

已用独立试跑库检查 6 片 batch=2、8 片 batch=4，确认检索索引和断点写入。正式主库从 `queued=22,400` 开始，在 `screen alpha-edcr` 运行 `scripts/kg/run_edcr_case_corpus.sh`；它显式传 `--edc-r-case --case-success-k 1 --case-failure-k 1 --batch-size 4`，并在每个 6 小时窗口之后做在线备份。**不要在它运行时另外执行一次提取命令**。查看进程、日志、断点见 7.2 节。主库 `queued=0` 后，该脚本自动结束；失败重试和审核按后续节另行执行。

如果服务器重启或 screen 结束，先核对健康主库、是否仍有抽取进程和最新快照。仅在确认无其他写入者且主库健康时，从当前 queued 继续：

```bash
cd /root/autodl-tmp/chemical_kb
screen -dmS alpha-edcr bash -lc 'cd /root/autodl-tmp/chemical_kb && exec bash scripts/kg/run_edcr_case_corpus.sh >> data/kg/batch_extraction/edcr_case_20261006.log 2>&1'
```
### 8.3 主库：一次失败重试、证据复核、全部候选审核

仅在 `queued=0` 后运行一次失败重试，因为 `--retry-failed` 的实际选择范围是 `queued + error + extraction_failed`。重试结束后按错误类型、模型解析问题及具体切片登记仍失败项；修复原因后再定向重试，避免无差别无限循环。当前脚本没有“只选失败项且排除 queued”的独立参数。

```bash
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --retry-failed --batch-size 2
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --recheck-evidence
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --dry-run
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --static-only
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --batch-size 2 --limit-prompts 100
```

审核脚本 `--limit-prompts 100` 让每次语义审核有界；前一轮完成并备份后再运行下一轮，直到 `--dry-run` 输出 `unaudited=0`。静态失败项会永久记录为 `needs_review`，后续语义脚本不会自动再审它们；只有校正来源/Schema 并设计明确复审流程后才能重审，不能直接将其改成 `valid`。`uncertain` 也算“有审核记录”，但不是通过；完结报告必须单列未决数。语义审核进程同样放入 `screen`，与抽取和向量任务错开。

发布前做在线备份和 dry-run。现有 `ready` 仅表示模型初审通过；我必须按第 7.1 节完成全量 Agent 终审并核对所有将发布项的引句、方向、限定条件、数值、时效和跨来源冲突。**在发布器接入 Agent 终审闸门以前，下面第二条写入命令禁止执行**；改造并验证后由我执行，不等待人工批准。

```bash
/root/miniconda3/envs/kb/bin/python scripts/kg/publish_audited_corpus.py --dry-run
/root/miniconda3/envs/kb/bin/python scripts/kg/publish_audited_corpus.py
```

### 8.4 旧关系与 152 份旧正文

先处理旧库 3,613 条历史关系。现有证据检索已将 110 条标为待语义复审、3,503 条标为缺来源，故此阶段不重复导入、不盲目重跑证据检索。先 `--dry-run` 查看待审量。**运行下面的写入命令之前**，必须按第 7.1 节把旧关系脚本改成仅存模型初审、不自动导出批准项；否则会绕过我的终审，并把 `reviewed_by` 错写成 `adamin`。改造验证后在 GPU 空闲时分批运行、逐批由我终审并备份；无逐字证据的历史关系最终结论为 `needs_source`。

```bash
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_semantic_review --dry-run
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_semantic_review --limit 20
```

每批结束复查进度、错误与新批准的证据；再运行下一批，直到无待审关系。若模型错误导致脚本提前停止，先看日志和数据库状态，不立即无限重试。

旧全文新抽取使用**完整正文的** 2,775 个切片，不使用旧的 7,927 片队列。以下每条抽取和审核命令都要同时传入这两个参数，避免误写主库或旧切片库：

```bash
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --dry-run
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --batch-size 4 --max-seconds 21600
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --retry-failed --batch-size 2
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --edc-r-case --case-success-k 1 --case-failure-k 1 --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --recheck-evidence
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --static-only
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --batch-size 2 --limit-prompts 100
```

同样先把旧全文 `queued` 跑到 0，才使用第三条 `--retry-failed`；上述命令是**顺序模板**，不能一次粘贴让所有阶段无条件连续执行。语义审核重复最后一条直到该库 `unaudited=0`。我随后对每条候选形成 Agent 终审结论。旧全文发布器当前没有审核方法和 Agent 闸门，必须先改造并验证，再运行写入命令；审核时检查来源/Schema、与历史旧关系及主库的重复和冲突：

```bash
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_publish_corpus --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --dry-run
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_publish_corpus --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite
```

### 8.5 旧正文向量及图谱更新

所有 Qwen GPU 任务结束后，用旧全文元数据和 BGE-M3 重建私有向量，先 dry-run 再运行；`reembed.sqlite` 保存每片断点，全部 2,775 向量完成后才构建 FAISS。旧 `text-embedding-v4` 向量不能混入 BGE-M3 索引。向量是检索材料，不是关系证据。

```bash
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_reembed --dry-run
/root/miniconda3/envs/kb/bin/python -m scripts.legacy_reembed --batch-size 16
python3 -m scripts.legacy_progress
```

Explorer 的边数按 reviewed 有效版本更新；如部署需要 Neo4j，先在 JSONL 发布完成后按 `scripts/kg/sync_to_neo4j.py` 的实际配置执行同步并核对数量。不能把 SQLite 候选数或旧历史关系数直接当成界面的边数。

## 9. 完成标准、报告和后续改造

| 检查项 | 本次完成标准 |
|---|---|
| 主库覆盖 | 24,606 个切片有状态；`queued=0`；失败已做一次重试，残余逐类列出切片 ID、原因和后续处理，不隐瞒为“完成” |
| 旧全文覆盖 | 2,775 个完整正文切片达到同一口径；7,927 个历史短切片仍只作追溯/关键词检索，不能混为新抽取覆盖率 |
| 候选审核 | 主库与旧全文分别 `unaudited=0`；分别报告 `valid/reject/uncertain/needs_review`；静态不合格及无来源候选保持未发布 |
| 发布关系 | 按主库、旧关系复审、旧全文新抽取分别统计新增 approved 和有效投影；每条可回查文档 ID、切片 ID、逐字引句、Schema、审核方法和版本 |
| 检索与断点 | 私有 BGE-M3 向量为 2,775/2,775，FAISS 可查；主库和旧库最终在线快照校验通过，文件路径写入报告 |
| 治理与质量 | 每条候选有 Agent 终局结论及理由；数值/方向/时点/跨来源冲突及实体合并由 Agent 针对性复核；无原文支持的关系不入图；报告区分 Qwen 初审数和 Agent 终审数，不宣称人工签核 |

若残余失败或未决关系仍存在，应明确标成“已覆盖但待解决”，不能称作“全部关系审核通过”。任何时态 `valid_from/valid_to` 只来自原文中的生效事实；审核日期不可充当生效日期。旧正文、候选 SQLite、reviewed 私有版本及模型文件继续留在服务器，不上传公开 GitHub。

本次抽取先使用当前已稳定的规则 + Qwen + 审核流程。Schema Retriever、Case Retriever、全局实体消歧/去重和冲突仲裁是下一阶段改造；先建立事故/法规/标准金标准样本，量化关系精确率、召回率、错误方向、无证据率和冲突误判，再分批启用并做同样数据上的对照。当前不能宣称原稿的完整 EDC+R+Case 闭环已上线。
