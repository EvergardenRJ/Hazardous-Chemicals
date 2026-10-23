# 危化品兴趣测试与公开题库

入口：智能检索 → 兴趣测试（`#quiz`）。页面含学习、自测、解析、续答、错题、记录导出和问题反馈。已移除全局“专题/生效时点/摘要”横栏。

## 题库快照

2026-10-23 同步 500 道去重学习题：LabSafety 281 道、ChemBench v0.2.0 safety 文本单选子集 192 道、SafetyBench 中文相关题 3 道、原创中文资料判断题 24 道。共 473 道原文题与 27 道中文题。

题目、稳定选项 ID、答案、解析、来源、定位及用途状态在 `app/quiz_content/questions.json`。题库不是模型评测成绩；未复制科研保留集、训练数据、会话数据库、凭据或模型权重。

每题显示仅供参考声明及答案解释。原题保留题源标签；SafetyBench 补充解释和虚构原创教学案例明确注明。完整来源清单在 `app/quiz_content/sources.json`，RGB、ALCE、ARES 等方法参考与实际导入题目分开；ChEmREF、标准图形及高阶扩展尚未全量导入。

服务器同步快照（CRLF）SHA-256：`e505f0732e8685fef2bb5ee45ceadc41467cb0d5904c0aa760cb62d00f5c11a5`。Git 规范化为 LF 后的 SHA-256：`195d7e4898415ba80c16a57238c58f9bc339c8befe1e6322ae2579d7c020e7b2`。两者仅换行不同，500 道题的 JSON 内容完全相同。

## 运行与验证

Flask 在 `app/explorer_api.py` 注册 `app.quiz_api`。运行时 SQLite 默认在 `BASE_DIR/data/quiz/sessions.sqlite`；测试可用 `CHEM_KB_QUIZ_DB` 指向隔离路径。题目快照固定于会话创建时，答案由服务端判定；自测结束前不返回解析。浏览器历史仅保存在当前设备。

```bash
python tests/test_quiz_contract.py
cd explorer_web
npm ci
npm run build
```

前端源码同步了 Ubuntu 已使用的导航、路由和 UIProvider 基础组件，作为兴趣测试的必要接入基础；保留旧 `App.jsx` 供历史入口使用。题库放在后端 app 目录，不放在前端静态发布目录。

Ubuntu Docker 部署额外保留了服务器特有的 `demo_api` 和鉴权逻辑：只有 `quiz.start/answer/report/clear` 属于学习者写接口，不放开上传、知识审核等管理员操作。服务器专用配置与密钥不随仓库同步。

## 来源入口

- [LabSafety Bench](https://github.com/YujunZhou/LabSafety-Bench)
- [ChemBench 归档](https://zenodo.org/records/14010212)
- [SafetyBench](https://github.com/thu-coai/SafetyBench)
- [RGB](https://github.com/chen700564/RGB)（仅承接方法，未复制原始通用题）

更改题库时保留来源与许可信息，更新题目版本及快照哈希；不得把公开学习题再称作未见科研保留测试。
