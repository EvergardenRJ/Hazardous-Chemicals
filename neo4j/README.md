# Neo4j 安装目录

原服务器使用 **Neo4j Community 5.26.0**，安装目录为 `/root/autodl-tmp/neo4j/`。本仓库不包含可重新下载的安装包、事务日志、数据库运行文件与 `data/dbms/auth.ini` 认证信息。

从 [Neo4j 官方部署中心](https://neo4j.com/deployment-center/)获取兼容的 Community 5.26 版本，并根据部署环境安装。图谱候选、审核记录和导出结果保存在 `chemical_kb/data/kg/`；启动服务时按需要重新建立数据库。连接配置位于 `chemical_kb/configs/kg/neo4j.yaml`，优先读取 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 环境变量。
