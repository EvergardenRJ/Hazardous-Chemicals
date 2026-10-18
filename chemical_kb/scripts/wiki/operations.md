# Wiki v2 运维

运行目录：/root/autodl-tmp/chemical_kb；仅更新实际服务副本，未覆盖 /root/kb_repo。

服务：python -m app.explorer_api --host 127.0.0.1 --port 8503。
Worker：python -m core.wiki.worker，日志 logs/wiki_worker_v2.log，PID logs/wiki_worker_v2.pid。启动不会加载模型；全库关系抽取运行时，生成保持排队。

不依赖 KG 抽取完成来阅读、编辑、审核 Wiki。真正生成任务目前为保护 GPU 而等待抽取结束。

data/wiki/registry.sqlite 为注册/任务/审核事件权威来源。entries/<wiki_id>/revisions/<revision_id> 为不可变正文、证据和 manifest。
原 data/wiki/<实体>、pages、review 与旧目录版本保持原样，用于追溯，不再作为新版列表/审核权威来源。

发布必须身份非空、当前版本全部审核通过、来源未失效、引用和知识块校验通过。姓名/工号是操作者声明；当前部署没有新增登录身份系统。

audit.py 输出待维护情况；repair_audit.py 验证氨、液氯引用与原章节证据一致。
migrate.py 默认 dry-run，只有 --apply 写入新仓库，重复导入幂等。
搜索默认只召回来源未失效的已发布内容；mode=sources 只查原文关键词。当前 Wiki 检索使用 CJK 分词 BM25；未启用需要额外模型的 Wiki 向量重排。
原 PDF 仅允许来自 data/pdf 的确切路径或唯一文件名匹配，无法确认时返回 404。

## 一致性备份

保留不可变版本目录，再通过 SQLite connection.backup 取得数据库快照；不要只复制活动 WAL 主文件。发布搜索投影可从已发布指针重建。迁移前已有完整旧 Wiki 与代码/前端备份，路径见 docs/llmwiki_upgrade_20261001/deployment.json。

## 回滚

核对 API 与 Wiki Worker PID 命令行后仅停止这两个服务，不处理 KG 进程。将备份 code/ 中文件恢复原路径，dist/ 恢复前端；原版旧 Wiki 文件从未更改，可恢复旧接口。新注册表与版本目录另行保留，避免丢弃部署后审核。再按原服务命令启动 API。禁止清空数据目录或覆盖关系抽取文件。

新版发布回滚只移动发布指针，保留所有版本与审核事件。它允许回查历史发布，即便来源已过期；过期内容仍显示来源失效且不参与默认检索。

## 索引更新

上传更新器在 embedding 前去重，相同数据不会调用 embedding。同 ID 内容变化保留向量位置重建 Flat 索引。FAISS、metadata、关键词索引由同一锁和可恢复 journal 提交；协作读取器在读取前完成恢复。旧文件备份在 .generation-*/previous，来源变化记录在 source_event.json。本次部署未执行生产上传、向量生成或主索引重建。
