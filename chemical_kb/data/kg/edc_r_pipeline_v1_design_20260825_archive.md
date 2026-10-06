# Chemical Safety KG Construction Pipeline v1 设计文档

- 版本：v1.0（设计稿）
- 状态：draft（仅设计，不落地）
- 日期：2026-08-25
- 依赖：`schema_v1.json`（已 finalized，15 实体 / 32 关系）
- 本文档只做设计，不实现、不批量抽取、不改 core/、不建 Neo4j。

---

## 0. 一句话定位

**「规则优先 + 检索增强 + LLM 兜底」的 EDC 抽取流水线，所有候选知识先入 Candidate Layer，经人工审核后才进入 Production KG，并把每一次审核结果沉淀为 Success/Failure Case，反哺下一轮抽取。**

---

## 1. 总体架构与完整数据流

```
Document (标准/法规/事故)
  │
  ▼
Chunk Router  ──── source_type 路由（标准 / 法规 / 事故）
  │
  ▼
Rule Preprocessor  ── regex/章节规则，产出 rule_annotations（不消耗 LLM）
  │
  ▼
Schema Retrieval  ── Schema Repository（15 实体 + 32 关系，BGE-M3 索引）
  │
  ▼
Case Retrieval  ─── Success/Failure Case Repository（分开检索）
  │
  ▼
Extract  ───────── 半开放抽取：entity mentions + relation phrases + 事件/因果表达 + 属性
  │
  ▼
Define   ───────── 开放 predicate → 自然语言定义 → 候选 schema relation + 方向 + confidence
  │
  ▼
Canonicalize ───── mention → normalization → exact/alias → retrieval → LLM 消歧 → canonical entity
  │
  ▼
Schema Validation ─ 自动校验（domain/range/required/provenance/去重）
  │
  ▼
Candidate Assertions ── 进入 Review Layer（不直接进 KG）
  │
  ▼
Human Review ────── approval / reject / modify
  │
  ├─→ Approved Assertions ─→ Production KG（approved 层）
  │
  └─→ Review Result ─→ Case Builder ─→ Success/Failure Repository ─→ Embedding ─→ Case Retriever ─→ 下一轮
```

### 关键分层（贯穿全设计）

| 层 | 位置 | 内容 | 谁可写 |
|---|---|---|---|
| Candidate / Review Layer | `data/kg/assertions/`（review_status=pending/modified/rejected） | 未定稿候选 | pipeline |
| Production KG | `data/kg/assertions/`（review_status=approved）+ `data/kg/canonical_entities/` | 定稿事实 | 仅人工 |

`pending` 与 `approved` 逻辑分层、物理分状态，绝不混写。

---

## 2. EDC 在本项目的映射

### 2.1 Extract —— 采用「半开放（hybrid / schema-guided open-span）」

**推荐：半开放。** 既不是纯 Open IE（召回噪声大、方向难控），也不是纯 schema-guided（漏掉 schema 外的真实表达、过早约束）。Extract 阶段**不 canonicalize、不强制映射 relation**，只做结构化提及抽取。

**分 source_type 微调：**

| source_type | Extract 策略 | 输出重点 |
|---|---|---|
| 事故 | 半开放 | entity mentions、relation/事件短语、因果链表达、属性值 |
| 标准/法规 | schema-guided（强结构） | Clause / Requirement 骨架（modality 由 rule 预打标） |

**Extract 输出中间结构（不落库，纯内存/临时）：**

```jsonc
ExtractionDraft {
  "chunk_id": "ACC_..._c0001",
  "source_metadata": { /* doc_id, source_type, title, section, page_start, page_end */ },
  "rule_annotations": [ /* Rule 层产出，如 modality、cas、death_count、clause_no */ ],
  "entity_mentions": [
    {
      "mention_id": "m_001",
      "surface": "液氯",
      "span": [12, 14],          // optional，OCR offset 不稳，仅参考
      "type_hint": "chemical",   // 弱类型提示，非最终定论
      "context": "液氯充装万向节密封失效导致氯气泄漏",
      "section": "直接原因"
    }
  ],
  "relation_phrases": [
    { "phrase": "导致", "subject_surface": "密封失效", "object_surface": "氯气泄漏", "section": "直接原因" }
  ],
  "event_causal_expressions": [ /* 事故经过的时序/因果链片段 */ ],
  "attribute_mentions": [ /* 死亡人数、经济损失、CAS、标准号等（可与 rule 重叠） */ ]
}
```

**铁律：Extract 阶段不 canonicalize、不改写 surface、不丢弃 mention。** 所有「液氯/氯气/液态氯」都以原文形式保留，交给 Canonicalize 阶段。

### 2.2 Define —— 开放 predicate → 定义 → 候选 relation + 方向

**职责：把 Extract 产出的开放关系短语，先给自然语言定义，再映射到 schema relation，并显式解决方向问题。**

**输入：** `open_predicates`（含 subject/object surface、上下文、section）+ `schema_context`（Schema Retriever 返回的候选 relation 定义）。

**输出：**

```jsonc
{
  "open_predicate": "导致",
  "definition": "一个因果因素使另一个事件或因素发生",
  "candidates": [
    {
      "schema_relation": "LEADS_TO",
      "subject_role": "原因因素",      // 文本主语扮演的角色
      "object_role": "结果因素",       // 文本宾语扮演的角色
      "direction": "TEXT_AS_IS",       // 或 SCHEMA_INVERTED
      "confidence": 0.87
    },
    {
      "schema_relation": "DIRECT_CAUSE",
      "subject_role": "事故",
      "object_role": "因果因素",
      "direction": "SCHEMA_INVERTED",  // 文本「因素→导致→事故」需反转为 Accident→DIRECT_CAUSE→CausalFactor
      "confidence": 0.90
    }
  ],
  "notes": "需结合 section（直接原因）与 subject/object 实体类型判定"
}
```

**方向判定规则（核心）：**

- 文本语言方向 ≠ schema 关系方向，必须显式给 `direction`。
- 「某因素 **导致** 事故」：文本主语=因素（CausalFactor）、文本宾语=事故（Accident）；schema 方向是 `Accident -DIRECT_CAUSE-> CausalFactor`，故 `direction = SCHEMA_INVERTED`。
- 「设备 A **造成** 设备 B 损坏」：若两者同为 CausalFactor，则 `CausalFactorA -LEADS_TO-> CausalFactorB`，`direction = TEXT_AS_IS`。
- 判定依据优先级：section 先验（直接/间接原因）> subject/object 实体类型 > 谓词语义。

### 2.3 Canonicalize —— mention → canonical entity 身份

**职责：把 surface mention 解析到本体实体，产出（canonical_id + 类型 + 强标识符 + confidence）。**

**输入：** `mentions`（含 surface/type_hint/context/section）+ `context`（chunk）。

**输出：**

```jsonc
{
  "mention_id": "m_001",
  "surface": "液氯",
  "canonical": {
    "entity_id": "CHM_chlorine",        // 或候选列表
    "entity_type": "chemical",
    "identifiers": { "cas": "7782-50-5", "formula": "Cl2" },
    "physical_state": "liquid",         // 从 surface 保留的 phase 信息
    "canonical_name": "氯"
  },
  "confidence": 0.95,
  "match_level": "exact_id",            // exact_id / alias / retrieval / llm_disambiguated / unresolved
  "needs_review": false
}
```

`match_level` 由低到高：`exact_id`（CAS/标准号/信用码强命中）→ `alias`（词典别名）→ `retrieval`（Entity Repository 向量候选）→ `llm_disambiguated`（LLM 从候选消歧）→ `unresolved`（强制人工）。

---

## 3. Retrieval 设计（R）

### 3.1 Schema Retriever —— 检索对象 = Schema Repository

**Schema Repository**：从 `schema_v1.json` 派生 15 实体 + 32 关系记录，每条记录含可检索的 `embedding_text`。

每条 schema 元素记录字段：

```jsonc
{
  "schema_element_id": "REL_direct_cause",
  "kind": "relation",                    // entity | relation
  "name": "DIRECT_CAUSE",
  "definition": "事故的直接原因，指向一个因果因素",
  "subject_types": ["accident"],
  "object_types": ["causal_factor"],
  "positive_examples": ["罐体腐蚀穿孔直接导致泄漏", "违章动火直接引发爆炸"],
  "negative_examples": ["应急处置措施（非原因）"],
  "aliases": ["直接导致", "直接原因", "直接引发"],
  "keywords": ["原因", "引发", "泄漏"],
  "embedding_text": "<name>\n<definition>\n<positive_examples>\n<keywords>"   // 拼接后编码
}
```

- **query**：chunk text（标准）或 Extract 后的 `relation_phrases`（增强，短语级更聚焦）。
- **TopK**：`top_k_entities = 8`、`top_k_relations = 12`（默认值，可调）。
- **ranking**：BGE-M3 归一化向量内积（IndexFlatIP = 余弦）+ 可选 bge-reranker-v2-m3 精排。
- **为何用 BGE-M3 可行**：项目已用 BGE-M3（max_seq 1024、normalize、IndexFlatIP），schema 元素文本短，编码开销小；definition/positive_examples 提供足够语义区分度。Schema 数量小（47 条），全量检索即可，无需近似索引。

### 3.2 Case Retriever —— Success / Failure 分开检索

- **query 表示**：chunk text（主）+ `type_hint`/开放短语（辅助，用于 schema_overlap/entity_type_overlap 信号）。
- **分开检索：是。** Success 与 Failure 用**独立向量索引**（或同库 + `case_type` 硬过滤），各自返回 `top_k_success`（默认 3）与 `top_k_failure`（默认 3），绝不混排。原因：二者语义作用不同（正例演示 vs 反例约束），混排会互相稀释。

### 3.3 Canonicalization Retriever —— v1 需要，但轻量

**判断：需要。** 理由：

- Chemical/Enterprise/Standard 有强 ID（CAS / 信用代码 / 标准号 / 文号），**规则 + 词典即可精确命中**，几乎不需检索。
- **Equipment / Process / 部分 Chemical 无强 ID**，必须靠 Entity Repository 向量候选 + LLM 消歧（例如「液氯充装万向节」不是 chemical，是 equipment）。
- v1 建 `data/kg/canonical_entities/` 轻量 Entity Repository（无需独立重索引，复用 BGE-M3），按实体类型分字典文件；检索仅在 `exact_id/alias` 未命中时触发。

---

## 4. Document Router 与 Rule + LLM 分工

### 4.1 Document Router

按 `source_type` 路由到不同 Extract strategy（标准 → 结构化 Clause/Requirement；法规 → 同上；事故 → 半开放事件/因果）。路由依据 chunk 的 `document_type`/`doc_type` 字段（已在 chunk 层打标，无需 LLM）。

### 4.2 Rule + LLM 混合（明确分工）

**Rule Layer 负责（确定性、零 LLM）：**

1. 标准号：`GB/T?\s?\d{4,5}([-—]\d{4})?`、`DB\d{2}/?T?\s?\d+`、`HG/T?\s?\d+` 等
2. CAS：`\d{2,7}-\d{2}-\d`
3. 事故伤亡：`(\d+)\s*人死亡`、`(\d+)\s*人受伤`、`(\d+)\s*人失踪`
4. Clause 编号：`第[一二三…0-9]+条`、`\d+(\.\d+)+`
5. Requirement modality：`应|应当|必须|不得|禁止|严禁`
6. 事故章节识别：`直接原因|间接原因|应急处置|整改措施|防范措施`（chunk 已有 `section` 字段，直接读）

**LLM Layer 负责（语义、需上下文）：**

1. Chemical / Equipment / Process 实体识别与属性
2. 开放因果/事件关系抽取（造成/导致/引发/涉及/未执行/违反）
3. 开放 predicate → schema relation 映射（Define）
4. Canonicalization 消歧（rule + retrieval 候选之上）
5. Requirement 的 subject/action/object/condition 语义切分（modality 已 rule 打标）

---

## 5. 事故 Pipeline（section-aware）

利用 chunk 的 `section` 字段做**章节先验**，显著降低 LLM 关系类型错判：

| section（正则命中） | 抽取先验 |
|---|---|
| 直接原因 / 事故原因 | causal factors → `Accident -DIRECT_CAUSE-> CausalFactor` |
| 间接原因 | `Accident -INDIRECT_CAUSE-> CausalFactor` |
| 事故经过 / 事故发生经过 | 事件链：`involves_chemical/equipment/process`、`CausalFactor -LEADS_TO-> CausalFactor` |
| 应急处置 | `Accident -HAS_MEASURE-> Measure{measure_type=应急}` |
| 整改措施 / 防范措施 / 事故防范措施 | `Measure{measure_type=整改}` |
| 人员伤亡 / 伤亡情况 | accident 属性 `death_count/severe_injury_count/minor_injury_count/missing_count`（rule） |
| 经济损失 | accident 属性 `economic_loss`（rule） |
| 基本情况 / 事故概况 | accident 元数据（title/date/site/enterprise/chemical/category） |
| 责任认定 / 责任追究 | `Enterprise -LIABILITY_OF-> Accident`（D3 无 Person 实体） |

**原则：章节先验只是「默认优先」，不是「强制」**；LLM 仍可基于句子语义覆盖，但需输出 `section` 作为 provenance 与审计依据。

---

## 6. 标准 / 法规 Pipeline（Clause / Requirement）

1. **Clause 抽取**：Clause 编号（rule）+ 条款文本 + 层级（`parent_of`）。
2. **Requirement 抽取**：从 Clause 文本切出规范要求。

**Requirement 结构化字段：**

```jsonc
{
  "requirement_id": "DB32T3617-2019_6.3.1_R01",   // {doc_id}_{clause_no}_R{index}
  "text": "液氯贮槽接受液氯应小于1.20kg/L。",
  "normalized": "液氯贮槽接受液氯 < 1.20 kg/L",
  "modality": "应",                                  // rule 打标：应/应当/必须/不得/禁止
  "subject": "液氯贮槽",
  "action": "接受液氯",
  "object": null,
  "condition": null,
  "quantitative_constraint": "< 1.20 kg/L",
  "source_clause_id": "DB32T3617-2019_6.3.1"
}
```

**派生关系（由 Define 阶段映射，方向已锁定于 schema）：**

- `Requirement -APPLIES_TO-> Entity`（如 `→ Equipment:液氯贮槽`）
- `Requirement -DERIVED_FROM-> Clause`
- `Clause -HAS_CLAUSE 逆 →`（即 `Standard/Regulation -HAS_CLAUSE-> Clause`）

---

## 7. Assertion 模型

候选知识**不直接进 KG**，统一生成 `CandidateAssertion`。

**字段（完善版）：**

```jsonc
{
  "assertion_id": "ASN_<chunk_id>_<seq>",
  // 主体/谓词/客体
  "subject": "canonical_id 或 surface 占位",
  "predicate": "DIRECT_CAUSE | has_cas | ...",   // schema relation 或属性名
  "object": "canonical_id | literal",
  "subject_type": "accident",
  "object_type": "causal_factor | literal",
  "object_kind": "entity | literal",              // 属性断言 vs 关系断言的分水岭
  // provenance
  "source_doc_id": "ACC_...",
  "source_chunk_id": "ACC_..._c0001",
  "source_text_quote": "液氯充装万向节密封失效导致氯气泄漏。",
  "source_type": "事故",
  "page_start": 12,
  "page_end": 12,
  "span_start": 3, "span_end": 21,                // optional，OCR offset 不稳
  "section": "直接原因",
  // 版本与方法
  "schema_version": "1.0",
  "extraction_method": "edc_r",                    // edc_r | rule | human
  "assertion_type": "explicit",                    // explicit | inferred | human_confirmed
  "confidence": 0.91,
  // 状态
  "review_status": "pending",                      // pending | approved | rejected | modified
  "reviewed_by": null, "review_time": null, "review_note": null,
  "validation_status": null, "validation_errors": [],
  "created_at": "2026-08-25"
}
```

**实体属性 extraction 与 relation assertion 是否同一模型：是（统一 Assertion 模型）。**

- **关系断言**：`object_kind = entity`，predicate ∈ 32 schema relations。
- **属性断言**：`object_kind = literal`，predicate ∈ 属性名（`has_cas`、`has_formula`、`has_physical_state`、`death_count`、`economic_loss` 等），object 为 literal + `value_type` + `unit`。

统一模型的好处：一条审核流、一个 Case Repository、一次去重，属性与关系只在 `object_kind`/`predicate` 语义上区分。

---

## 8. Schema Validation（人工审核前的自动闸门）

候选断言在进入 Human Review 前必须自动校验，至少：

1. `subject_type` ∈ 15 实体（合法）
2. `predicate` ∈ 32 关系 ∪ 属性名白名单（合法）
3. `object_type` 合法（entity 时 ∈ 15 实体；literal 时有 value_type）
4. relation `domain/range` 合法（subject_type ∈ domain、object_type ∈ range）
5. required property 检查（如 requirement 必须有 requirement_id；relation 断言必须有 canonical id 或 surface + confidence）
6. canonical id 检查（entity 断言须能回溯到 canonical_entity 或标记 unresolved）
7. provenance 检查（source_chunk_id / source_text_quote / source_doc_id 非空）
8. duplicate assertion 检查（同 subject+predicate+object+source 去重）

**不合法：不删除**，置 `validation_status = failed` + `validation_errors[]`，进入 `validation_failed` 队列，之后可沉淀为 Failure Case（error_type=relation_type_error/schema_violation/…）。

---

## 9. Canonicalization Pipeline（详细）

```
mention
  ↓ normalization          （去空白/全半角/括号统一）
  ↓ exact ID match         （CAS regex / 标准号 regex / 信用码 regex / 文号）
  ↓ alias match            （canonical dictionary：别名 → canonical）
  ↓ retrieval candidates   （Entity Repository BGE-M3 向量，TopK=5）
  ↓ LLM disambiguation     （候选 + context → 选一或判新实体）
  ↓ confidence + match_level
  ↓ human review if uncertain（confidence < θ 或 unresolved）
  ↓ canonical entity
```

**分类型强 ID 优先级：**

| 类型 | 优先匹配键 |
|---|---|
| Chemical | CAS → UN 编号 → 目录号 → canonical dictionary → retrieval |
| Enterprise | 信用代码 → 精确全名 → 别名 → retrieval |
| Standard | code（GB/DB/HG…） |
| Regulation | doc_no + title |
| Equipment | 无强 ID：mention + context + type + 所属 enterprise 联合 canonicalize（retrieval + LLM） |
| Process | 同 Equipment，弱 ID |

**低 confidence 处理：** `confidence < θ`（默认 0.85）或 `match_level ∈ {retrieval, llm_disambiguated, unresolved}` → `needs_review = true`，进入人工审核；canonical 未决时断言 object 保留 surface + `unresolved` 标记。

---

## 10. Define Repository（谓词定义是否持久化）

**推荐：方案 B —— 持久化到 `predicate_definition_repository`，但 v1 采用「带缓存的临时生成」起步。**

理由：`造成/导致/引发/诱发/引起/致使` 等高频因果谓词在 861 篇文档中重复出现极多；每次 LLM 重定义+重映射是纯浪费，且结果应可复用、可人工校验、可积累成领域谓词词典。

- 首次遇到开放谓词 → LLM 定义+映射 → 写入 repository（`status=pending`）。
- 后续命中 → 直接复用（跳过 LLM），人工可审核为 `verified`。
- 数据结构：

```jsonc
{
  "predicate": "导致",
  "definition": "一个因果因素使另一个事件或因素发生",
  "mappings": [
    { "schema_relation": "DIRECT_CAUSE", "direction_rule": "SCHEMA_INVERTED", "usage_count": 18 },
    { "schema_relation": "LEADS_TO", "direction_rule": "TEXT_AS_IS", "usage_count": 7 }
  ],
  "status": "pending",       // pending | verified | deprecated
  "verified_by": null
}
```

---

## 11. Human Review 工作流

### 审核单位 = **assertion 级**（每条 CandidateAssertion 一个审核单元）

- **entity 级**：entity 的 canonical 正确性**随其所属 assertion 一起审核**；未被任何 assertion 引用的孤立实体（高价值 mention）单独进 review 队列。
- **chunk 级：不直接审核**。整个 chunk 标 failure 会损失其中的正确经验（用户已明确）。

### 审核人看到什么（明确界面要素）

```
--------------------------------
原文：液氯充装万向节密封失效导致氯气泄漏。
[章节] 直接原因   [来源] ACC_xxx_c0001  p12
候选实体：
  [Chemical] 液氯 → canonical 氯  (state=liquid, CAS 7782-50-5)  conf=0.96
  [Equipment] 液氯充装万向节   conf=0.82
  [CausalFactor] 密封失效   conf=0.88
  [Accident] 氯气泄漏事故   conf=0.90
候选 Assertion：
  1. Accident -[INVOLVES_CHEMICAL]-> Chemical(氯)  conf=0.96   [接受][修改][拒绝]
  2. Accident -[DIRECT_CAUSE]-> 密封失效          conf=0.91   [接受][修改][拒绝]
--------------------------------
```

### 审核状态机

`pending → approved | rejected | modified`；`modified` 必须附 `corrected_output` + `review_note`。

### v1 是否全部人工审核：**是（全部人工）**

当前阶段重点是**确保正确**，不是吞吐。但设计 confidence threshold 作为「以后自动 approve」的预留：

- `confidence ≥ 0.95` 且 `assertion_type=explicit` 且 `match_level=exact_id/alias` 且 schema 合法 → 标 `auto_approve_candidate`，v1 **仍进人工队列**（仅排序置顶/高亮），不真正自动通过。
- 待 Case Repository 稳定、Failure Recurrence Rate 下降后，再评估放开。

---

## 12. Case Repository 设计

### 12.1 类型：Success / Failure，Corrected 不独立

**Corrected Case 不是独立类型**，而是 failure_case 内嵌 `corrected_output` 字段。理由：纠正只有和错误配对才有学习价值；独立类型导致信息断裂与重复。

### 12.2 Case 粒度：**两层（chunk 级容器 + assertion 级最小单元）**

- **存储/检索单元 = assertion 级**（一条错误断言 = 一条 failure case；一个通过 chunk 的每条正确断言可汇成 success case，但 success 更常以 chunk 级示范存储）。
- **chunk 级**只作为 provenance/上下文容器（source_text、source_metadata），不参与判定。

### 12.3 Success Case 结构（必要字段）

```jsonc
{
  "case_id": "SC_...",
  "case_type": "success",
  "task_type": "accident_extract | standard_extract | define | canonicalize",
  "source_doc_id": "ACC_...", "source_chunk_id": "ACC_..._c0001",
  "source_type": "事故", "source_text": "…原文…",
  "schema_version": "1.0",
  "schema_context": [ /* 检索到的相关 schema 元素 */ ],
  "model_output": { /* 模型原始输出（extraction draft / assertions） */ },
  "reviewed_output": { /* 人工确认后的最终输出 */ },
  "entities": [...], "relations": [...],
  "quality_score": 0.95,
  "case_status": "verified",       // pending | verified | deprecated
  "created_at": "2026-08-25"
}
```

### 12.4 Failure Case 结构（必要字段 + 内嵌纠正）

```jsonc
{
  "case_id": "FC_...",
  "case_type": "failure",
  "task_type": "accident_extract | define | canonicalize",
  "source_doc_id": "...", "source_chunk_id": "...", "source_type": "事故",
  "source_text": "…原文…",
  "model_output": { /* 错误输出 */ },
  "wrong_assertion": { "predicate": "DIRECT_CAUSE", "subject": "...", "object": "..." },
  "corrected_assertion": { /* 人工纠正后的正确断言 */ },
  "error_type": "relation_direction_error",   // 见 error taxonomy
  "error_reason": "文本主语=因素，应反转为 Accident→DIRECT_CAUSE",
  "review_comment": "…",
  "schema_element": "REL_direct_cause",
  "canonicalization_error": null,             // canonicalization_error 类型时填充
  "case_status": "verified",
  "created_at": "2026-08-25"
}
```

### 12.5 Error Taxonomy（评审：合理，微调后采用）

12 类中，`canonicalization_error` 与 `attribute_error` 是「属性/实体」级错误，其余为「关系/输出」级错误，边界清晰、可自动归因。微调：

- `hallucination` 与 `entity_extra` 有重叠，定义上区分：`hallucination` = 输出在原文无任何支撑（凭空捏造）；`entity_extra` = 实体存在但非本句/本任务应抽取。
- `provenance_error` 与 `schema_violation` 通常可被 Schema Validation 自动捕获，二者更多作为 **validation 阶段产出的 failure**，而非仅人工标注。

最终 taxonomy（12 类）：

| error_type | 含义 |
|---|---|
| entity_missing | 漏抽实体 |
| entity_extra | 多抽/不应抽的实体 |
| entity_type_error | 实体类型错判 |
| relation_missing | 漏抽关系 |
| relation_extra | 多抽关系 |
| relation_type_error | 关系类型错判 |
| relation_direction_error | 关系方向错（subject/object 颠倒） |
| canonicalization_error | 实体归一化错（同指未合并 / 错合并） |
| attribute_error | 属性值/单位/约束错 |
| provenance_error | 出处/引用/页码错 |
| hallucination | 原文无支撑的捏造 |
| schema_violation | domain/range/字段不合 schema |

### 12.6 Case 存储：**方案 C（metadata 统一 + 向量索引按 case_type 分开）**

- **metadata**：统一一个 `cases.jsonl`（或 `success_cases.jsonl` + `failure_cases.jsonl` 分文件但同一 schema），统一治理 case_status、去重、审计。
- **向量索引**：按 `case_type` 分 `success.index` / `failure.index`（各自 `embeddings.npy`），满足 Success/Failure 独立 TopK。
- 方案 A（完全统一索引）混排不可取；方案 B（完全分开存储）治理碎片化。**方案 C 取二者之长，为 v1 推荐。**

### 12.7 Case 学习闭环

- **Success Case 作用**：positive demonstration（正向 few-shot，示范正确抽取/映射/归一化）。
- **Failure Case 作用**：negative constraint + reflection（反例约束，显式告诉模型「别这样做」）。
- **进入 Repository 条件**：只有 `case_status = verified`（人工审核完成）才进入检索池；`pending` 不参与；发现错后置 `deprecated`，**不删除历史**。

### 12.8 防止错误案例诱导模型（标准格式）

Failure Case 进入 prompt 必须显式区分「错误输出」与「正确纠正」，否则模型会把错误三元组当正例学。标准模板：

```
Previous Failure:
  Input:          <原文/chunk>
  Incorrect Output: <模型错误输出>
  Why Incorrect:  <error_type + error_reason>
  Corrected Output: <人工纠正>
  Rule Learned:   <抽象出的规则，如：直接原因句中主语=因素须反转为 Accident-DIRECT_CAUSE->
Current Task:
  <当前 chunk>
```

### 12.9 Case Retrieval Ranking（公式框架，权重后调）

```
score = w1·semantic_similarity
      + w2·schema_overlap        (case 涉及的 schema 元素与当前 chunk 检索 schema 的 Jaccard)
      + w3·entity_type_overlap   (case 实体类型与当前 mention 类型的重叠)
      + w4·source_type_match     (事故/标准/法规 是否一致，0/1)
      + w5·task_type_match       (extract/define/canonicalize 是否一致，0/1)
      + w6·case_quality          (quality_score / 编辑距离修正)
      (+ w7·recency, optional)
```

- `source_type_match`、`task_type_match` 作为**硬过滤**（不匹配直接排除）再排序；`case_quality` 作为质量加权。
- 本阶段只给框架，权重由后续消融实验确定。

---

## 13. Production KG 与 Review KG 分层

| 层 | 存储 | review_status 取值 |
|---|---|---|
| Candidate / Review Layer | `data/kg/assertions/` | pending / modified / rejected / validation_failed |
| Production KG | `data/kg/assertions/`（仅 approved）+ `data/kg/canonical_entities/` | approved |

- pending 与 approved **物理分状态、逻辑分层**，绝不混写。
- v1 **不建 Neo4j**，Production KG 用本地 JSONL 表达节点+边（逻辑图模型），后续再决定是否落地到图数据库。

---

## 14. Prompt 架构（模板结构，不写全量几千字）

| Prompt | 输入 | 输出 JSON schema（要点） | 必要约束 | 失败处理 |
|---|---|---|---|---|
| `extract_accident_prompt` | chunk text + source_metadata + rule_annotations + schema_context + case_context | `{entity_mentions[], relation_phrases[], event_causal_expressions[], attribute_mentions[]}` | 不 canonicalize、不丢弃 surface、保留 section | 无结构化 JSON → 重试 1 次；仍失败 → 降级 rule-only 并标 `extraction_method=rule` |
| `extract_standard_prompt` | clause 文本 + rule(编号/modality) + schema_context | `{clauses[], requirements[]}`（含 requirement 全字段） | requirement_id 必填；modality 以 rule 为准 | 同上 |
| `define_prompt` | open_predicates + schema_context（候选 relation） | `{predicate, definition, candidates[]{schema_relation, subject_role, object_role, direction, confidence}}` | 必须显式给 direction；候选关系必须来自 schema_context | 无法映射 → 保留开放谓词 + `schema_relation=null`，标 `relates_to` 兜底并进 review |
| `canonicalize_prompt` | mentions + entity_repo 候选 + context | `{mention_id, canonical{}, confidence, match_level, needs_review}` | 只从候选或词典选；不可凭空造 CAS/编号 | unresolved → needs_review=true |
| `case_augmented_extract_prompt` | 同 extract + top_k success（正例）+ top_k failure（Previous Failure 格式） | 同 extract | failure 必须按「错误/纠正」分离展示 | 同上 |
| `case_reflection_prompt` | current output + 检索到的 failure case | `{violations[], revisions[], final_output}` | 只对照 Rule Learned 修，不改已正确部分 | 无违规 → 原样返回 |

每个 prompt 均需：输入占位、输出 JSON schema、约束清单、失败降级路径四要素。

---

## 15. 推荐目录架构（不实现，仅推荐）

```
core/kg/
  schema_manager.py        # 加载 schema_v1.json → Schema Repository
  schema_retriever.py      # Schema 元素 BGE-M3 索引 + TopK
  document_router.py       # source_type 路由
  rule_extractor.py        # Rule Layer（regex/章节先验）
  extractor.py             # Extract（半开放）
  definer.py               # Define（开放谓词 → relation 映射 + 方向）
  canonicalizer.py         # Canonicalize（mention → entity）
  entity_repository.py     # Entity Repository（字典 + 向量候选）
  assertion.py             # CandidateAssertion 数据结构
  validator.py             # Schema Validation
  case_repository.py       # Case 读写 + case_status 治理
  case_retriever.py        # Success/Failure 分开检索 + ranking
  case_builder.py          # 从 review 结果构建 case
  review_manager.py        # Human Review 状态机
  pipeline.py              # 编排 EDC+R 主流程

data/kg/
  schema_v1.json
  cases/
    cases.jsonl            # 统一 metadata
    success_embeddings.npy / success.index
    failure_embeddings.npy / failure.index
  assertions/
    candidate_assertions.jsonl     # pending/modified/rejected/validation_failed
    approved_assertions.jsonl      # Production KG（approved）
  canonical_entities/
    chemical.json / enterprise.json / equipment.json / standard.json / regulation.json
  predicate_definition_repository.jsonl
  schema_repository.json    # schema_v1.json 派生 + embedding_text

configs/kg/
  pipeline_config.yaml      # 阈值/TopK/权重/开关
  prompts.yaml             # prompt 模板

scripts/kg/
  build_schema_repository.py
  build_case_index.py
  run_pipeline.py
  eval_pipeline.py
```

（现有 `core/`、`FAISS`、`Streamlit`、RAG 均不动；`core/kg/` 为新增独立子包。）

---

## 16. 核心模块接口（只签名，不实现）

```python
SchemaRetriever.retrieve(text, top_k_entities=8, top_k_relations=12) -> SchemaContext

CaseRetriever.retrieve(text, task_type, source_type, top_k_success=3, top_k_failure=3) -> CaseContext

Extractor.extract(text, schema_context, case_context, source_metadata) -> ExtractionDraft

Definer.define(open_predicates, schema_context) -> list[RelationMapping]

Canonicalizer.canonicalize(mentions, context) -> list[CanonicalResult]

AssertionValidator.validate(assertions, schema) -> ValidationReport

CaseBuilder.build_from_review(original_output, reviewed_output) -> Case

CaseRepository.add(case) / .get(case_id) / .deprecate(case_id) / .list(status=...)

ReviewManager.submit(assertion) / .review(assertion_id, decision, corrected_output) -> Case

DocumentRouter.route(chunk_metadata) -> strategy
```

---

## 17. 评估实验设计

### 17.1 对照实验（评审：合理，保留为递增消融）

| 实验 | 配置 | 回答的问题 |
|---|---|---|
| A | Schema-guided baseline | 纯 schema 约束下限 |
| B | EDC | EDC 三段式增益 |
| C | EDC + Schema Retrieval | Schema R 增益 |
| D | EDC + Schema R + Success Cases | 正例 few-shot 增益 |
| E | EDC + Schema R + Success + Failure | 反例 reflection 增益 |
| F | 完整（EDC + R + Case + Human Feedback） | 全栈上限 |

**固定同一个小规模 test set（标注黄金标准）**，保证可比性。D 作为 Success-only 消融有独立价值，保留。

### 17.2 消融（Ablation）

去掉 Schema Retrieval / Success Case / Failure Case / Canonicalization Retrieval / Human Feedback，各测一次，比较：准确率、错误复发率、人工审核成本。

### 17.3 Evaluation Metrics

- Entity P / R / F1
- Relation P / R / F1
- Canonicalization Accuracy（canonical 实体解析正确率）
- Schema Violation Rate（进入人工前未通过 validation 的占比）
- Hallucination Rate（无原文支撑的断言占比）
- Human Correction Rate（被人工修改/拒绝的占比）
- Review Acceptance Rate（直接接受的占比）
- Case Retrieval Hit Rate（检索到的 case 中「确与当前样本同类」的占比）
- **Failure Recurrence Rate**

### 17.4 Failure Recurrence Rate 定义

> 某类错误（同 error_type + 同 schema_element/谓词模式）**进入 Failure Repository 之后**，后续出现的**相似样本**中再次犯**同类错误**的比例。

即：把「历史已纠正的同类错误」作为锚，衡量 Case Memory 是否真正抑制了同类错误复发。这是本项目最具区分度的指标——它直接量化「学习闭环」是否有效，而非单看静态准确率。

### 17.5 Human Effort Metrics（人工成本，不能只看准确率）

- 平均每 chunk 审核时间
- 平均每 100 assertions 修改数量
- 自动通过率（auto_approve_candidate 占比）
- 人工修改率 / 人工拒绝率
- **Case Memory 加入后审核时间是否下降**（直接证明 Case Repository 是否真的减轻人工）

---

## 18. 当前设计风险

1. **Qwen3-4B 是 4B 小模型**，半开放抽取 + 方向判定 + 消歧的可靠性存疑，需在 Prototype 阶段实测其结构化 JSON 遵循度，必要时加 JSON 约束/少样本。
2. **Case 冷启动**：初期无 verified case，Case Retrieval 为空，F 实验早期与 E 无差别；需先积累「种子 case」（人工标注 30–50 条）。
3. **Failure 诱导风险**：错误案例展示不当会反向诱导；必须严格走「Previous Failure 错误/纠正分离」模板（§12.8），并在 Prototype 中验证 Failure Recurrence Rate 不升反降。
4. **OCR 文本质量**：事故报告 OCR 噪声高，offset 不稳，provenance 以 quote+chunk_id 为主、span 为辅（§7）。
5. **Schema 覆盖边界**：schema 只 32 关系，开放世界存在无法映射的谓词，`relates_to` 兜底会积累「弱关系」，需在 review 中监控其占比。

---

## 19. 下一步建议（只给建议，不执行）

- **是否立即批量处理 861 文档：否。**
- **是否先做小规模 Prototype：是。**
- **建议文档量：30–50 篇**（事故 ~15、标准 ~15、法规 ~10，覆盖三种 source_type + 各 error_type 出现面），先跑通 EDC+R+Review+Case 闭环，标黄金标准，产出 A–F 实验首轮数据，再决定放量。

---

（完）
