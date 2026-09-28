# Alpha Explorer 前端

## 目标与结构

这是化工安全知识库的独立 React 页面，参考 [Semantica Explorer](https://github.com/semantica-agi/semantica/tree/main/explorer) 的工作台组织方式：导航栏、全屏图谱、实体索引、来源详情、时间轴与快速搜索。页面没有使用原 Streamlit 布局或主题。顶栏提供 Light / Dark 外观切换，并在浏览器中记住选择。旧 Streamlit 程序仍可运行，现有知识处理模块由 Flask API 复用。

- 前端源码：`explorer_web/src/`
- 生产构建：`explorer_web/dist/`
- API 和静态文件服务：`app/explorer_api.py`
- 图谱渲染：Three.js + react-force-graph-3d
- UI：React 19、Lucide、定制 CSS
- 后端数据：原有审核 JSONL、文档元数据、关键词索引、RAG、Wiki 和案例库

## 工作区

1. **总览**：真实知识片段、已审核实体和关系、待审断言统计。
2. **图谱探索**：已审 / 全部视图与 3D 可旋转画布、实体与关系过滤、搜索聚焦、节点邻居、关系来源、最短路径、时间点筛选。
3. **智能检索**：现有关键词、向量、图谱融合问答与证据列表；支持快速片段检索。
4. **断言审核**：展示全部已有关系，核对原文片段，编辑断言，查看版本历史；审核人默认 `adamin`，并沿用案例库写入流程。
5. **实体与冲突**：全局别名确认与撤销、跨来源冲突候选、PROV-O JSON-LD/Turtle、GraphML、CSV 导出。
6. **文档库**：来源文档列表、搜索、分页、PDF 保存入口。
7. **知识 Wiki**：已有 Wiki 阅读、生成、逐节审核。

## 启动

在项目根目录：

```bash
# 本机先构建前端
cd explorer_web
npm ci
npm run build
cd ..

# 服务器使用项目已有的 kb Python 环境
/root/miniconda3/envs/kb/bin/python -m app.explorer_api --host 127.0.0.1 --port 8503
```

服务器默认仅监听本机回环地址。需要从电脑访问时可建立 SSH 隧道：

```powershell
ssh -N -L 8504:127.0.0.1:8503 -p 47157 root@connect.westc.seetacloud.com
```

然后打开 `http://127.0.0.1:8504/`。若改为非回环地址监听，服务要求设置 `CHEM_KB_API_KEY`。生产部署建议使用受管 WSGI 进程和反向代理。

## 维护要点

- 页面从 `/api/summary`、`/api/graph`、`/api/search` 等接口读取真实数据，没有写死演示节点。
- 审核和实体合并是持久化操作；人工确认后追加审核版本，最新版本立即影响图谱，历史记录保留。
- 老断言没有 `valid_from/valid_to` 时会继续显示；时间轴明确提示旧数据未标注日期。
- PDF 上传入口只保存到原项目的 `data/upload`，后续分块建索引仍由原处理流程执行。
- 服务器当前 Neo4j 未连接；图谱使用审核 JSONL 回退数据源。
- 快捷键 `Ctrl+K` / `Cmd+K` 打开搜索工作区与实体的命令面板。

## 本次验证

前端生产构建通过；关系审计覆盖 41 条既有断言，全部可以回查来源原文。最新版审核结果为 39 条有效、2 条撤销，旧版本与审计前备份保留。页面提供 3D 图谱、完整关系目录和 Light / Dark 主题。


