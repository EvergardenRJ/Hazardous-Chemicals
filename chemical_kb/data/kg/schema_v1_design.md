# 化工安全领域知识图谱 Schema v1 设计文档

- 版本：1.0（定稿）
- 日期：2026-08-25
- 定稿日期：2026-08-25
- 状态：finalized
- 领域：化工 / 危险化学品安全
- 配套机器可读文件：`schema_v1.json`
- 设计依据：`chemical_kb` 项目真实数据抽样（5 篇标准 + 5 篇法规 + 10 篇事故调查报告）

> 边界声明：本文档与 `schema_v1.json` 只做 **Schema 设计**，不包含 EDC、知识抽取实现、Neo4j/Cypher、图数据落地，不改动 FAISS / Streamlit / core / RAG / Retriever。

---

## 1. 设计目标

1. 覆盖三类知识库（标准文档 / 法规文档 / 事故报告）在真实数据中出现的知识对象。
2. 实现 **条款级** 知识建模，不让“整份标准/法规”作为一个黑盒节点。
3. 实现 **事故 ↔ 标准/法规** 的桥接，回答“此事故违反了哪条 / 整改应依据哪条”。
4. 支撑 **事故因果链** 的表达（直接原因 / 间接原因 / 链式传导）。
5. 全链路可溯源（Provenance）、可人工复核（Human Review）、与 Case Repository 解耦兼容。
6. 为未来 EDC + Canonicalization 预留强键与对齐机制，但 v1 不实现。

---

## 2. 数据观察（真实抽样结论）

### 2.1 抽样清单

| 类型 | 文档 | 要点 |
|---|---|---|
| 标准 | AQ 3011-2007 连二亚硫酸钠包装安全要求 | 章/条/款 3.1.1.1 层级、强制性/推荐性、试验方法、引用 GB 系列 |
| 标准 | DB32/T 3617-2019 液氯使用安全技术规范 | 术语定义、规范性引用、量化限值（1.20kg/L、80%）、应急处置章 |
| 标准 | DB37/T 4995-2025 装卸设施安全管理规范 | 术语（可燃液体/毒性气体）、缩略语、联锁、附录 |
| 标准 | GB 30000.30-2025 退敏爆炸物 | GHS 危险类别定义、判定逻辑、标签 |
| 标准 | GB 6222-2025 工业企业煤气安全规范 | 代替旧版、术语（煤气设施/隔断装置/眼镜阀）、煤气管道/柜/应急处置 |
| 法规 | 危险化学品安全法 | 章/条、部门职责（第七条十部门）、许可制度、重大危险源（第十三条） |
| 法规 | 国务院安委会“一件事”全链条措施 | 高危细分领域（硝化/氯化/氟化/重氮化/过氧化）、老旧装置、重大危险源 |
| 法规 | 上海市危险化学品安全管理办法 | 单位责任、属地监管、部门职责、应急预案 |
| 法规 | 湖北省燃气管理条例 | 规划/经营/用气/器具/安全/法律责任 |
| 法规 | 北京市危险化学品禁限控措施(2024) | 禁止目录（62 种，含 CAS 号）、限制/控制措施、限定区域 |
| 事故 | 西艾氟“5·3”反应釜爆炸（3死） | 超压、擅自改变反应条件、异常工况处置不当、DCS/SIS 未触发 |
| 事故 | 融汇化工“8·29”氯气泄漏（19伤） | 液氯充装万向节泄漏、垫片反复泄漏、新鹤管压力不达标 |
| 事故 | 宿州“8·6”硫化氢中毒窒息（3死） | 有限空间、未通风未检测未防护、无审批、无书面合同 |
| 事故 | 淄博峻辰“4·29”火灾 | 违章动火（特级动火票）、储罐闪爆、苯起火 |
| 事故 | 康尼瑞“4·21”锅炉爆炸（2死） | 淘汰锅炉、无证安装、超压运行→热疲劳断裂→硝化物料爆炸链 |
| 事故 | 广汇“3·7”高处坠落（1死） | 未正确系挂安全绳、检维修、高处作业票 |
| 事故 | 璟和“4·15”灼烫（1死2伤） | 擅自改加热介质（95℃热水→160℃蒸汽）、利旧干燥机、未启用温度表 |
| 事故 | 义马“7·19”重大爆炸（15死16重伤） | 空分冷箱泄漏→超压→珠光砂外喷→液氧贮槽破裂→爆炸 |
| 事故 | 信诺立兴“3·8”闪爆（4死） | 角磨机火花→储罐气相空间闪爆、迟报谎报 |
| 事故 | 司尔特“6·7”中毒窒息（1死2伤） | 受限空间违规作业、盲目施救致事故扩大、二吸塔出口阀未关未加盲板 |

### 2.2 关键观察

1. **标准/法规有稳定的条款层级**：章 → 条 → 款 → 项（如 3.1.1.1、6.3.1、第三条），这是“条款级建模”的天然锚点。
2. **事故报告结构高度一致**：基本情况（企业/装置/设备/现场勘查/鉴定）→ 事故经过（带时间戳）→ 原因（直接/间接）→ 性质 → 责任 → 应急 → 整改。可直接映射为实体与关系。
3. **量化限值密集**：标准正文充满“应小于 1.20kg/L”“不应大于 200mm”“≤ 80%”等可判定要求，是事故“违反”判定的依据。
4. **跨文档同实体大量出现**：液氯同时出现在事故、地方标准、国标、法规中；这是桥接的天然连接点。
5. **强对齐键真实存在**：CAS 号（北京禁止目录）、标准号、统一社会信用代码、文号，可直接支撑 Canonicalization。

---

## 3. Entity Types（15 类）

详见 `schema_v1.json` 的 `entity_types`。要点：

- **事故侧**：Accident、CausalFactor（致因）、Measure（措施）、Enterprise、Equipment、Process、Site、MajorHazardSource、Chemical、HazardClass。
- **文档侧**：Standard、Regulation、Clause（条款）、Requirement（要求）。
- **治理侧**：Regulator（监管部门）。
- 明确 **不建 Person 实体**（v1），伤亡人数/损失作为 Accident 属性。

---

## 4. Relation Types（32 类）

详见 `schema_v1.json` 的 `relation_types`，分为四组（GOVERNS 兼具文档规范与桥接作用，仅计数一次）：

1. **文档结构（6）**：HAS_CLAUSE、PARENT_OF、REFERENCES、REPLACES、DEFINES、DERIVED_FROM。
2. **对象网络（12）**：BELONGS_TO_CLASS、GOVERNS、LOCATED_AT、HAS_EQUIPMENT、OPERATES_PROCESS、HANDLES、HAS_HAZARD_SOURCE、HAZARD_OF、CONTAINS、USED_IN、REGULATES、ISSUED_BY。
3. **事故因果（11）**：OCCURRED_IN、OCCURRED_AT、INVOLVES_CHEMICAL、INVOLVES_EQUIPMENT、INVOLVES_PROCESS、DIRECT_CAUSE、INDIRECT_CAUSE、LEADS_TO、RELATES_TO、HAS_MEASURE、LIABILITY_OF。
4. **桥接（3，另复用 GOVERNS）**：VIOLATES、BASED_ON、APPLIES_TO。

---

## 5. Entity vs Attribute 关键决策

| 对象 | 决策 | 理由 |
|---|---|---|
| 伤亡人数 / 直接经济损失 | **属性**（death_count / severe_injury_count / minor_injury_count / missing_count） | 每个事故一组数值，无需独立节点；Person 级细节 v2 再做 |
| 危险特性（毒害/腐蚀/爆炸/燃烧/助燃） | **属性**（chemical.hazard_property） | 枚举标签，非独立对象 |
| 危险类别（GHS） | **实体 HazardClass** | 有定义、有分类标准（GB 30000 系列）、可被标准定义、可被化学品归属，需跨文档引用 |
| 企业角色（生产/经营/使用/运输/施工） | **属性**（enterprise_type）+ 关系 role | 同一企业多角色，拆分会重复 |
| 条款文本 vs 要求 | **分离**（Clause 结构 / Requirement 语义） | 一条款多要求、事故违反的是“要求” |
| 场所类型（厂区/车间/有限空间/限定区域） | **属性**（site.site_type） | 同一 Site 实体承载物理场所与监管区域 |
| 事故类型/等级 | **属性**（受控枚举） | 统计检索需要受控值 |
| 是否重大危险源 | MajorHazardSource 独立实体 + Enterprise.has_hazard_source | 有专项法规标准要求，是桥接节点 |

---

## 6. 事故建模（因果链）

```
管理缺陷（间接原因）─leads_to→ 不安全行为/不安全状态（间接/直接）─leads_to→ 危险能量/物质释放（直接）─direct_cause→ 事故
                                                                                                                    ├─occurred_in→ 企业
                                                                                                                    ├─involves_*→ 化学品/设备/工艺
                                                                                                                    ├─has_measure→ 应急处置/整改措施
                                                                                                                    └─liability_of→ 责任单位
```

- 事故报告的“直接原因”映射为 `Accident -[DIRECT_CAUSE]-> CausalFactor{causal_level=直接原因}`。
- “间接原因”映射为 `Accident -[INDIRECT_CAUSE]-> CausalFactor{causal_level=间接原因}`。
- 原因之间的传导用 `CausalFactor -[LEADS_TO]-> CausalFactor`（如“锅炉超压运行”→“锅筒热疲劳断裂”→“锅炉爆炸”→“引发硝化物料爆炸”）。
- 每个 CausalFactor 用 `RELATES_TO` 关联到具体 Chemical/Equipment/Process/Site/Enterprise。
- 后果（伤亡/损失）作为 Accident 属性；应急处置与整改作为 Measure 节点。

---

## 7. 标准/法规建模（条款级）

- 整份标准/法规 = Standard/Regulation 文档节点（仅元数据）。
- 其下用 `HAS_CLAUSE` + `PARENT_OF` 建条款树：章 → 条 → 款 → 项。
- 术语和定义条款用 `DEFINES` 指向 HazardClass/Equipment/Chemical 等，避免“只挂一份文档”。
- 量化/规范性内容抽为 Requirement，`DERIVED_FROM` 指向 Clause；每个 Requirement 用稳定 `requirement_id`（`{document_id}_{clause_number}_R{index}`，如 DB32T3617-2019_6.3.1_R01），不以文本为唯一 ID，不同标准中内容相似的要求默认不合并。
- 引用关系用 `REFERENCES`（如液氯标准引用 GB 11984、TSG 21），修订关系用 `REPLACES`（GB 6222-2025 代替 2005 版）。

---

## 8. 事故 ↔ 标准/法规桥接（最核心）

四条桥接路径：

1. **实体共指**：事故与标准/法规共享 Chemical/Equipment/Process/Site 等实体。
   例：融汇氯气泄漏 →(involves_chemical)→ 液氯；液氯 ←(governs)→ DB32/T 3617 / GB 11984。
   查询“涉液氯事故对应哪些标准”即走此路径。

2. **违反（VIOLATES）**：`CausalFactor -[VIOLATES]-> Requirement/Clause`。
   例：“违章动火作业” -(VIOLATES)-> GB 30871 动火作业条款（或企业动火票制度条款）。

3. **整改依据（BASED_ON）**：`Measure -[BASED_ON]-> Requirement/Clause/Standard/Regulation`。
   例：“加装盲板” -(BASED_ON)-> 司尔特大修方案停车要求 / GB 盲板抽堵条款。

4. **适用对象（APPLIES_TO / GOVERNS）**：`Requirement -[APPLIES_TO]-> Equipment/Chemical/Process`。
   反向支持“某设备有哪些安全要求”，再与事故中该设备的状态比对。

> 桥接关系（VIOLATES / BASED_ON / RELATES_TO）带 `assertion_type`（explicit / inferred / human_confirmed）。explicit=事故报告明确写“违反了…”；inferred=系统推断，默认 review_status=pending，人工批准后才进 production KG。

---

## 9. Provenance

- 每个节点/边必带：`source_doc_id`、`source_chunk_id`、`source_type`（标准/法规/事故）、`page_start`、`page_end`。
- 可选：`section`、`confidence`、`created_at`、`updated_at`。
- chunk_id 差异：标准/法规 `{doc_id}_p{page}_c{n}`；事故 `{doc_id}_c{n}`（带 section 与 page_start/page_end 字段）。
- 抽取方式枚举：`rule` / `llm` / `human` / `manual`。

---

## 10. Canonicalization（对齐机制，v1 只定义不实现）

- 强键：Chemical 用 `cas_number`/`catalog_no`/`un_number`；Enterprise 用 `credit_code`；Standard 用 `code`；Regulation 用 `doc_no`+title。
- 流程：精确匹配 → 别名表（真正同义）→ 规范化（去空格/全半角/繁简）→ 外部权威对齐。
- **Chemical 本体 vs 文本 mention**：Chemical 表示化学物质本体（如 氯/Chlorine，identifier=Cl2）。液氯/氯气/液态氯可归一化到同一 identity，但原始 mention 与 `physical_state`（液氯=liquid、氯气=gas）必须保留，不得因归一化丢失物态信息。
- **真同义别名**：仅真正可互换的名称作 alias（保险粉=连二亚硫酸钠、水银=汞）；上下文相关的物态表达（液氯 vs 氯气）不作无条件 alias merge。
- 图谱节点只存 `canonical_id` + `aliases[]` + `mentions[]`，映射表独立维护，由人工审核 + 未来 EDC 更新。

---

## 11. Human Review 兼容设计（Assertion 层解耦）

- 审核/抽取元数据放在独立的 **Assertion** 层（assertion_id、subject_id、predicate、object_id、source_chunk_id、extraction_method、confidence、assertion_type、review_status、reviewed_by、review_time、review_note），不塞进业务实体/关系本体。
- 业务图谱只承载 approved 事实；pending 进入审核池；rejected 留审核池/Case Repository；modified 保留原输出并生成 corrected assertion。
- 冲突/重复节点用 `merge_proposal` 提交合并，由审核人裁决。

---

## 12. Case Repository 兼容设计（解耦）

- 案例库（成功/失败/人工修正）与图谱**分库**，通过 `canonical_id` + `external_ref` 指向图谱节点，不内嵌图谱。
- 预留字段：`case_id`、`external_ref`、`case_type`、`feedback`。
- 案例库的人工修正通过**独立反馈接口**回流 canonicalization（别名纠正、错误合并纠正），不直接改图。

---

## 13. 三个图谱示例（真实数据三元组）

> 均来自真实抽样文本，可脱敏但非虚构。关系名后括号为来源。

### 示例 1：事故（康尼瑞“4·21”锅炉爆炸）

```
(事故:康尼瑞"4·21"锅炉爆炸事故) -[OCCURRED_IN]-> (企业:大庆康尼瑞生物科技有限公司)
(事故) -[DIRECT_CAUSE]-> (致因:锅炉超压运行)
(致因:锅炉超压运行) -[LEADS_TO]-> (致因:锅筒水冷壁角焊缝管桥热疲劳断裂)
(致因:热疲劳断裂) -[LEADS_TO]-> (致因:高压汽水混合物扩散锅炉爆炸)
(致因:锅炉爆炸) -[LEADS_TO]-> (致因:引发硝化反应物料爆炸)
(事故) -[INDIRECT_CAUSE]-> (致因:使用淘汰落后锅炉)
(事故) -[INDIRECT_CAUSE]-> (致因:无证人员非法安装)
(事故) -[INVOLVES_EQUIPMENT]-> (设备:DZL型2吨蒸汽锅炉)
(事故) -[INVOLVES_PROCESS]-> (工艺:硝化工艺)
(企业) -[HAS_EQUIPMENT]-> (设备:DZL型2吨蒸汽锅炉)
(企业) -[OPERATES_PROCESS]-> (工艺:硝化工艺)
(企业) -[HANDLES{operation=使用}]-> (化学品:硝酸)
(设备) -[CONTAINS]-> (化学品:高压蒸汽/水)
(致因:使用淘汰落后锅炉) -[VIOLATES]-> (要求:特种设备使用单位应使用取得许可生产的合格特种设备)  # 依据 特种设备安全法
(事故) -[HAS_MEASURE{type=整改}]-> (措施:更换合规锅炉并依法办理使用登记)
```

### 示例 2：标准/法规（DB32/T 3617-2019 液氯使用安全技术规范）

```
(标准:DB32/T 3617-2019) -[HAS_CLAUSE]-> (条款:第6章 安全技术要求)
(条款:第6章) -[PARENT_OF]-> (条款:第6.3条 液氯贮槽)
(条款:第6.3条) -[PARENT_OF]-> (条款:第6.3.1条)
(条款:第6.3.1条) -[DEFINES]-> (化学品:液氯)          # 术语/条款语境
(条款:第6.3.1条) -[REFERENCES]-> (标准:GB 5138 工业用液氯)
(要求:液氯贮槽接受液氯应小于1.20kg/L) -[DERIVED_FROM]-> (条款:第6.3.1条)
(要求:液氯贮槽接受液氯应小于1.20kg/L) -[APPLIES_TO]-> (设备:液氯贮槽)
(要求:液氯汽车罐车卸载应采用液体装卸臂，不应使用软管) -[APPLIES_TO]-> (设备:液体装卸臂)
(标准) -[GOVERNS]-> (化学品:液氯)
(标准) -[GOVERNS]-> (工艺:液氯气化)
(标准) -[REPLACES]-> (标准:AQ 3014-2008 液氯使用安全技术要求)  # 引用/关联，非严格代替
```

### 示例 3：事故 + 标准法规联合（融汇“8·29”氯气泄漏）

```
(事故:融汇化工"8·29"氯气泄漏事故) -[OCCURRED_IN]-> (企业:芜湖融汇化工有限公司)
(事故) -[INVOLVES_CHEMICAL]-> (化学品:液氯)
(事故) -[INVOLVES_EQUIPMENT]-> (设备:液氯充装万向节(鹤管))
(事故) -[OCCURRED_AT]-> (场所:液氯充装台)
(事故) -[DIRECT_CAUSE]-> (致因:万向节液相管道连接处密封失效氯气泄漏)
(致因) -[RELATES_TO]-> (设备:液氯充装万向节(鹤管))
(致因) -[VIOLATES]-> (要求:液氯汽车罐车卸载应采用液体装卸臂并符合 HG/T 2040、HG/T 21608)  # DB32/T 3617 6.1.4
(企业) -[HANDLES{operation=生产/储存}]-> (化学品:液氯)
(企业) -[HAS_HAZARD_SOURCE]-> (重大危险源:液氯储罐区)
(重大危险源) -[HAZARD_OF]-> (化学品:液氯)
# 标准/法规侧
(标准:DB32/T 3617-2019) -[GOVERNS]-> (化学品:液氯)
(标准:DB32/T 3617-2019) -[GOVERNS]-> (工艺:液氯充装)
(法规:危险化学品安全法) -[GOVERNS]-> (化学品:液氯)      # 第二条 生产储存使用经营运输适用本法
(法规:危险化学品安全法) -[HAS_CLAUSE]-> (条款:第十三条 重大危险源)
# 桥接结论：从“事故”经“液氯”即可抵达 DB32/T 3617 与危险化学品安全法的相应条款
```

---

## 14. 定稿决策（已锁定）

见 `schema_v1.json` 的 `design_decisions`，四条均已 `resolved`：
- **D1** 条款与要求分离 → **方案B**（Clause=文档结构单元，Requirement=可执行/可约束/可违反的规范性要求）。
- **D2** 企业不拆实体 → **方案A**（单一 Enterprise + enterprise_type / role）。
- **D3** 不建 Person → **方案A**（伤亡作 Accident 属性，Person 留 v2）。
- **D4** 事故类型/等级受控枚举 → **方案A**。

如需变更，升级为 v1.1 并记录原因，不回改 v1.0。

---

## 15. v2 候选扩展

Person 实体、Term 术语表、Document 统一父类、Consequence 后果实体、EnvironmentalPollution、TemporalEvent 事故时间线、semantic_equivalent_to 关系（跨标准相似 Requirement 等价对齐）。
