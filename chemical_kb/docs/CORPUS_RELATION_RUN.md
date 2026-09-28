# 全库关系抽取运行说明

当前向量索引包含 1,061 份文档、24,606 个片段（标准 11,171；事故 8,115；法规 5,320）。此前审核图谱仅来自 2 份文档的 2 个片段：41 条断言中 39 条有效（18 条实体关系、21 条属性），2 条撤销。首页、图谱和审核页现明确展示该覆盖范围。

## 处理入口

```bash
cd /root/autodl-tmp/chemical_kb
/root/miniconda3/envs/kb/bin/python scripts/kg/extract_corpus.py --dry-run
/root/miniconda3/envs/kb/bin/python -u scripts/kg/extract_corpus.py
```

处理器从 `data/vector_store/index_metadata.json` 读取全部文档片段，按文档轮询：每份文档先处理一个片段，再进入下一轮。每个片段的状态与候选断言独立写入 `data/kg/batch_extraction/corpus.sqlite`。中断后重复执行命令即可跳过已完成片段。`--limit N` 用于小批验证；`--retry-failed` 重试失败片段。

通过原项目 `KGExtractionPipeline` 使用本地 Qwen 模型抽取，并保留原 schema 校验结果。每条候选另行标记来源引句是否原样出现在该片段中。**候选暂存于 SQLite，不会自动成为有效图谱关系，也不会自动覆盖现有审核历史。** 后续应按文档、关系类型和证据质量分批复核，再导入审核目录。未校验、来源引句不匹配、方向有疑问和冲突的关系不能自动通过。

`/api/summary` 返回 `batch_extraction` 进度；首页每 30 秒刷新。`done + empty` 是已完成片段数，`staged_candidates` 是暂存候选数，不等于审核通过数。完整任务需要连续运行，耗时取决于本地模型生成速度；单个 461 字法规片段试跑约 8 秒完成抽取（模型另需约 4 秒加载），不能据此保证全库总时长。

## 并行抽取与候选复核

服务器有 60 GB 系统内存和 24 GB GPU 显存。`--batch-size` 控制一次送入 GPU 的片段数，并非开启同样数量的独立模型进程；多进程各自加载 Qwen 会重复占用显存。小批 benchmark 后选择稳定批量。

```bash
/root/miniconda3/envs/kb/bin/python -u scripts/kg/extract_corpus.py --batch-size 4
/root/miniconda3/envs/kb/bin/python scripts/kg/audit_corpus_candidates.py --dry-run
/root/miniconda3/envs/kb/bin/python -u scripts/kg/audit_corpus_candidates.py --batch-size 4
```

`audit_corpus_candidates.py` 对 schema 和来源引句不合格者先标为 `needs_review`，对其余候选按来源片段分组进行 GPU 批量语义复核；结果写入 SQLite 的 `candidate_audits` 表。它同样可断点续跑，且不会自动将未经核验的候选发布到现网图谱。大规模全库复核完成前，页面中现有 39 条有效断言的数字不会被候选数替代。
