# lyyzoo-ssms

学生成绩管理系统（Student Score Manage System，简称 SSMS），基于 Java Web 的课程、班级、师生与成绩管理应用。

## 技术栈

- **后端**：Servlet 3.1、JSP、commons-dbutils 1.6、c3p0 0.9.5.5、Apache POI 3.8
- **前端**：jQuery EasyUI、H-ui
- **数据库**：openGauss 7.0.0-RC3（B + Dolphin 兼容模式，JDBC 驱动 `org.opengauss.Driver`）
- **构建与运行**：Maven 打包为 WAR，编译目标为 Java 8；已在 JDK 21 与 Tomcat 9 上完成构建与运行验证

## 快速开始

### 环境要求

- JDK 8+（已在 JDK 21 验证构建与运行）
- Maven 3
- Apache Tomcat 9
- openGauss 7.0.0-RC3（B 兼容模式，Dolphin 自动加载）

### 1. 准备数据库

按 [MySQL 到 openGauss 迁移手册](doc/opengauss-migration.md) 创建空的 B 模式 `ssms` 数据库（`OWNER = gaussdb`），并使用转换脚本处理导出数据后导入。仓库内的原始 [doc/ssms.sql](doc/ssms.sql) 保持不变，仅作为数据对照基线。

### 2. 配置数据库连接

`MysqlTool` 在静态初始化时读取连接配置，优先级为 **JVM 系统属性 > 环境变量 > `src/main/resources/c3p0-config.xml` 默认值**。数据库密码不写入仓库，缺失时将抛出 `IllegalStateException` 拒绝启动。

| 配置项 | JVM 系统属性 | 环境变量 | 默认值 |
|---|---|---|---|
| JDBC URL | `ssms.jdbc.url` | `SSMS_DB_URL` | `jdbc:opengauss://127.0.0.1:5432/ssms` |
| 用户名 | `ssms.jdbc.user` | `SSMS_DB_USER` | `gaussdb` |
| 密码 | `ssms.jdbc.password` | `SSMS_DB_PASSWORD` | 无（必填，缺失即拒绝启动） |

在 Tomcat 进程环境中设置 `SSMS_DB_PASSWORD`（按需覆盖 `SSMS_DB_URL`、`SSMS_DB_USER`），或通过 JVM 启动参数 `-Dssms.jdbc.password=...` 传入。

### 3. 构建与部署

```bash
mvn package
```

将生成的 `target/ssms.war` 部署到 Tomcat 9，启动服务后在浏览器访问：

- `http://127.0.0.1:8080/ssms/`

## 默认测试账号

以下示例账号来自 [早期使用说明](doc/学生成绩管理系统使用说明.txt)，初始密码均为 `111111`：

- **管理员**：`admin`
- **教师**：`2012`、`2011`、`2010`、`2009`、`2008`
- **学生**：`201301001`、`201302002`、`201401001`、`201402002`

## 目录结构

```text
.
├── pom.xml              # Maven 构建与依赖配置
├── src/                 # Java 源码、c3p0 配置及 JSP/EasyUI/H-ui 前端资源
├── tools/               # MySQL dump 转 openGauss 导入脚本（mysql_to_opengauss.py）
├── doc/                 # 迁移手册、基准 SQL 与历史文档
├── lib/                 # 本地依赖（FilelLoad.jar）
└── 项目截图/            # 系统各模块页面与工程结构截图
```

## 文档索引

| 文档 | 说明 | 状态 |
|---|---|---|
| [doc/opengauss-migration.md](doc/opengauss-migration.md) | MySQL 到 openGauss 迁移、配置与迁移验证记录 | 当前有效 |
| [doc/ssms.sql](doc/ssms.sql) | 原始 MySQL 基准 SQL（保持原样，作数据对照） | 数据基线 |
| [doc/学生成绩管理系统使用说明.txt](doc/学生成绩管理系统使用说明.txt) | 早期 Eclipse + MySQL 部署与使用说明 | 历史归档 |
| [doc/学生信息管理系统分析.docx](doc/学生信息管理系统分析.docx) | 早期需求与系统分析文档 | 历史归档 |

## 参考链接

- 原项目博客介绍：http://www.cnblogs.com/chiangchou/p/project-ssms.html
