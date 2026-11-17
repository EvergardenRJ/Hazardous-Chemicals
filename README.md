# Alpha 危险化学品知识库

本仓库是面向协作的公开快照，归档 `chemical_kb/` 中的文档解析、切片、嵌入、混合检索、知识图谱抽取与审核、Flask API、Streamlit 页面和 React 图谱工作台。

## 目录

- `chemical_kb/app/`、`chemical_kb/core/`、`chemical_kb/scripts/`：应用、处理流程与批量任务。
- `chemical_kb/explorer_web/`：React 前端源码、构建产物和前端说明。
- `chemical_kb/data/`：解析结果、切片、向量与关键词索引、知识图谱候选与审核记录。运行中的 SQLite 库按一致性快照入库。
- `chemical_kb/data/pdf/README.md`：原始 PDF 与 Word 的应放目录和文件清单；原文文件不在仓库。
- `models/README.md`：模型作用、参数、上游下载链接及权重目录；权重不在仓库。
- `neo4j/README.md`、`neo4j-java/README.md`：图数据库及 Java 运行时的版本和安装说明；安装包、运行库、认证文件不在仓库。

## 当前前端功能

- 工作总览保留原有首页布局；其余 10 个功能页为：兴趣测试、智能检索、知识 Wiki、化学品专题、图谱探索、数据洞察、多维分析、危化品新闻、知识治理、文档与数据。
- 10 个功能页每次进入或刷新显示一条随机引文。中文引文显示原句；外文引文先显示原文，下一行显示中文译文。引文库含中、英、法、德四种语言共 100 条，作者、篇目和来源可在“原文与出处”中展开核对。
- 引文按页面主题抽取，并优先避免与上一次重复；首页工作总览和主导航不显示引文。
- 「图谱与治理」提供实体关系浏览、来源追溯、断言审核和冲突处理。

## 获取和启动

```bash
git clone https://github.com/EvergardenRJ/Hazardous-Chemicals.git
cd Hazardous-Chemicals
git lfs pull
```

先按 [PDF 清单](chemical_kb/data/pdf/README.md) 放置有权使用的原始文档，并按 [模型清单](models/README.md) 下载模型权重。代码中部分路径仍沿用原部署布局，部署前应按实际环境配置。

### 前端

```bash
cd chemical_kb/explorer_web
npm ci
npm test
npm run build
```

`npm test` 运行引文库和页面覆盖测试；`npm run build` 生成 `chemical_kb/explorer_web/dist/`。开发预览使用 `npm run dev`，生产预览使用 `npm run preview`。

### 后端

在已安装项目 Python 依赖（Flask、检索与文档处理依赖）的环境中，从 `chemical_kb/` 目录启动：

```bash
python -m app.explorer_api --host 127.0.0.1 --port 8503
```

服务默认仅监听本机回环地址。需要从本机访问时使用可替换的主机名建立隧道，不要把实际部署主机、端口、账号或密钥写入仓库：

```bash
ssh -N -L 8504:127.0.0.1:8503 user@server.example.com
```

将 `user@server.example.com` 替换为部署账号和主机名，然后打开 `http://127.0.0.1:8504/`。若改为非回环地址监听，服务要求设置 `CHEM_KB_API_KEY`。生产部署建议使用受管 WSGI 进程和反向代理。

## 数据、模型与配置

- 页面从 `/api/summary`、`/api/graph`、`/api/search` 等接口读取真实数据。
- 审核和实体合并是持久化操作；人工确认后追加审核版本，最新版本影响图谱，历史记录保留。
- 老断言没有 `valid_from/valid_to` 时继续显示；时间轴会明确提示数据未标注生效日期。
- PDF 上传入口保存到项目的数据目录，后续分块和建索引仍由原处理流程执行。
- Neo4j 密码通过 `NEO4J_PASSWORD` 环境变量传入；`chemical_kb/configs/kg/neo4j.yaml` 仅保留占位值。
- 大型数据库、向量及索引文件由 Git LFS 管理。原始资料、模型、索引、数据库和审核数据不随本次前端更新上传。
- 不要把真实密码、API Key、`.env` 或私有部署信息提交到公开仓库。

## 协作与验证

- 修改关系时保留审核历史；更新 SQLite 时使用在线备份，并在提交前运行 `PRAGMA integrity_check`。详见 [数据收录规则](chemical_kb/docs/GITHUB_DATA_POLICY.md)。
- 前端以 `npm test` 和 `npm run build` 验证；本仓库不包含 GitHub Actions、Dockerfile 或 Ubuntu 部署脚本。
