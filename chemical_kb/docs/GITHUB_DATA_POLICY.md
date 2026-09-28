# Alpha：GitHub 数据与大文件收录规则

> 收录范围：源码、处理结果与索引；PDF/Word 原件、模型权重及可重新下载的 Neo4j/Java 运行时以各目录 README 说明。

## 收录范围

**提交到 GitHub：**全部源码、前端、脚本、schema、配置示例；解析结果、OCR 结果、切片、嵌入向量、FAISS/关键词检索索引；知识图谱候选、审核记录、关系修订、实体别名与导出结果。数据库只提交一致性快照，不能直接提交后台正在写入的文件。

**不提交到 GitHub：**data/pdf/ 下的 PDF、Word、图片等原始资料；模型权重和下载缓存；密钥、环境变量文件、日志、node_modules、构建缓存和临时备份包。data/pdf/README.md 与 models/README.md **必须提交**，以说明文件放置位置、模型作用及下载方式。模型实际目录在项目外，项目内 models/README.md 是应入库的副本。

## 建议的忽略规则

~~~gitignore
/data/pdf/**
!/data/pdf/README.md
/models/**
!/models/README.md
*.pdf
*.doc
*.docx
.env
.env.*
!.env.example
**/__pycache__/
*.pyc
/explorer_web/node_modules/
/logs/
*.log
*.tgz
*.zip
*.sqlite-wal
*.sqlite-shm
*.db-wal
*.db-shm
~~~

不要再写“/data/*”或全局忽略 *.sqlite、*.npy、*.index；那会与本方案冲突。前端源码中的图片若不在 data/pdf/ 下，可以正常入库。建仓库时以 git check-ignore -v 和 git status 实测，避免误排除或误收录。

## 大型生成文件用 Git LFS

建议在首次添加数据前设置 .gitattributes：

~~~gitattributes
*.sqlite filter=lfs diff=lfs merge=lfs -text
*.db filter=lfs diff=lfs merge=lfs -text
*.index filter=lfs diff=lfs merge=lfs -text
*.faiss filter=lfs diff=lfs merge=lfs -text
*.npy filter=lfs diff=lfs merge=lfs -text
*.npz filter=lfs diff=lfs merge=lfs -text
~~~

当前 data/search/keyword.sqlite 约 119.5 MiB，超过 GitHub 普通 Git 单文件 100 MiB 限制，必须走 LFS 或改存 GitHub Release。data/vector_store/faiss.index 约 96.1 MiB、data/embeddings/chunks_embeddings.npy 约 64.4 MiB，虽低于硬限制，仍建议用 LFS。JSON/JSONL、CSV 和 Markdown 优先保留普通 Git 文本差异；若某一单文件继续增长超过限额，再分片或改用 LFS。

Git LFS 会按每次上传的**完整二进制版本**计入存储和带宽，不能每天随意提交整个索引或 SQLite 库。建议每次完成一轮语料、模型或 schema 更新后提交一个标记清晰的快照，并记录源文件清单、模型版本、代码 commit 和校验值。协作者需要安装 Git LFS 才能取得真实大文件。参考 [GitHub 大文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)、[LFS 计费](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)。

## 正在运行的审核库如何提交

data/kg/batch_extraction/corpus.sqlite 正由全库任务写入。直接复制这个文件，或只复制 SQLite 主文件而不处理 WAL，可能得到不一致的版本。应使用 SQLite 在线 backup API 或 VACUUM INTO 生成一个只读快照，验证 PRAGMA integrity_check 通过，再把快照作为 LFS 对象提交。在线备份方法见 [SQLite 官方文档](https://www.sqlite.org/backup.html)。

审核与关系修订的 JSONL 应保留 append-only 历史和稳定 assertion_id；协作者通过 PR 提交修订，避免两人同时修改同一条最终状态。提交前还应检查候选和审核记录中引用的原文是否包含不宜在目标 GitHub 仓库公开的内容。

## 首次入库的验收

1. PDF/Word/图片等原始资料和模型权重均不在暂存清单中，但两个 README 在暂存清单中。
2. 解析、切片、嵌入、FAISS、关键词索引、schema、审核记录与修订结果均可在克隆或 LFS 拉取后读取。
3. SQLite 快照通过 integrity_check；向量数量、维度、片段数与元数据一致；审核关系数与页面统计一致。
4. git lfs ls-files 包含应走 LFS 的库和索引，普通 Git 对象没有超过 GitHub 单文件限制。
5. 列出本次快照对应的代码 commit、模型 revision、原始资料目录版本和生成时间。

本规则同时适用于首次上传和后续维护。
