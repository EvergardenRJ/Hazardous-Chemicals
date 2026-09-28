# Alpha 危险化学品知识库

本仓库是服务器 `/root/autodl-tmp` 的协作快照。`chemical_kb/` 包含文档解析、切片、嵌入、混合检索、知识图谱抽取与审核、Flask API、Streamlit 页面和 React 图谱工作台。

## 目录

- `chemical_kb/app/`、`chemical_kb/core/`、`chemical_kb/scripts/`：应用、处理流程与批量任务。
- `chemical_kb/explorer_web/`：React 前端源码、构建产物和使用说明。
- `chemical_kb/data/`：解析结果、切片、向量与关键词索引、知识图谱候选与审核记录。运行中的 SQLite 库以一致性快照入库。
- `chemical_kb/data/pdf/README.md`：原始 PDF 与 Word 的应放目录和文件清单；原文文件不在仓库。
- `models/README.md`：模型作用、参数、上游下载链接及权重目录；权重不在仓库。
- `neo4j/README.md`、`neo4j-java/README.md`：图数据库及 Java 运行时的版本和安装说明；安装包、运行库、认证文件不在仓库。

## 获取和启动

```bash
git clone https://github.com/EvergardenRJ/Hazardous-Chemicals.git
cd Hazardous-Chemicals
git lfs pull
```

先按 [PDF 清单](chemical_kb/data/pdf/README.md)放置有权使用的原始文档，并按[模型清单](models/README.md)下载权重。当前代码部分路径仍指向原服务器的 `/root/autodl-tmp`，在其他机器部署前需配置这些路径。前端启动细节见 [前端说明](chemical_kb/explorer_web/README.md)。

Neo4j 密码通过 `NEO4J_PASSWORD` 环境变量传入；`chemical_kb/configs/kg/neo4j.yaml` 中仅保留占位值。不要把真实密码、API Key 或 `.env` 提交到公开仓库。

## 数据快照

`chemical_kb/data/` 中的索引和审核记录是本次同步时的快照，后续服务器抽取任务可能继续更新。协作者修改关系时应保留审核历史；更新 SQLite 时使用在线备份，并在提交前运行 `PRAGMA integrity_check`。大型数据库、向量及索引文件由 Git LFS 管理。详见 [数据收录规则](chemical_kb/docs/GITHUB_DATA_POLICY.md)。
