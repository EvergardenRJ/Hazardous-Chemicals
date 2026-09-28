# 全库关系抽取暂停断点

- 暂停时间：2026-09-28 22:45 CST。
- 服务器进程已停止；SQLite WAL 已 checkpoint，主库和备份均通过 `PRAGMA integrity_check`。
- 数据库：`/root/autodl-tmp/chemical_kb/data/kg/batch_extraction/corpus.sqlite`。
- 持久备份：`/autodl-fs/data/alpha-corpus-checkpoints/corpus_20260928_224525.sqlite`。
- 总切片 24,606；`done` 105、`empty` 154、`extraction_failed` 47、`queued` 24,300。
- 已生成 2,245 条候选断言；已有 100 条候选审核记录。

## 下次续跑

先确认服务器数据库存在并通过 `PRAGMA integrity_check`；若主库丢失，再从持久备份恢复。`extract_corpus.py` 默认只选择 `queued`，已完成的 `done`、`empty` 切片不会重跑。

```bash
cd /root/autodl-tmp/chemical_kb
nohup /root/miniconda3/envs/kb/bin/python -u scripts/kg/extract_corpus.py --batch-size 4 > /tmp/alpha_corpus_resume.log 2>&1 &
```

待 `queued` 处理完后，再根据失败原因决定是否使用 `--retry-failed`，然后执行候选审核。切勿在抽取进程运行时直接复制 SQLite 主文件；请使用 SQLite 在线备份 API。

