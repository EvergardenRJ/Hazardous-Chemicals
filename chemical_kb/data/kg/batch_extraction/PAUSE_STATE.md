# 全库关系抽取暂停断点

- 最终暂停时间：2026-09-28 22:51 CST。
- 服务器抽取进程已停止；SQLite WAL 已 checkpoint，主库和最终备份均通过 `PRAGMA integrity_check`。
- 数据库：`/root/autodl-tmp/chemical_kb/data/kg/batch_extraction/corpus.sqlite`。
- 持久备份：`/autodl-fs/data/alpha-corpus-checkpoints/corpus_20260928_225136.sqlite`。
- 总切片 24,606；`done` 107、`empty` 159、`extraction_failed` 48、`queued` 24,292。
- 已生成 2,304 条候选断言；已有 100 条候选审核记录。
- 22:44 首次停止后出现一次新的抽取进程；已再次停止，并将关联的 Codex 定时检查任务设为 `PAUSED`。检查了 crontab 与 systemd timers，未发现对应启动项。

## 下次续跑

先确认服务器数据库存在并通过 `PRAGMA integrity_check`；若主库丢失，再从上述最终持久备份恢复。`extract_corpus.py` 默认只选择 `queued`，已完成的 `done`、`empty` 切片不会重跑。

```bash
cd /root/autodl-tmp/chemical_kb
nohup /root/miniconda3/envs/kb/bin/python -u scripts/kg/extract_corpus.py --batch-size 4 > /tmp/alpha_corpus_resume.log 2>&1 &
```

待 `queued` 处理完后，再根据失败原因决定是否使用 `--retry-failed`，然后执行候选审核。切勿在抽取进程运行时直接复制 SQLite 主文件；请使用 SQLite 在线备份 API。

