# MySQL 到 openGauss 迁移手册

记录本项目从 MySQL 8 迁到 openGauss 7（B 兼容模式）的数据库差异、代码改造、数据迁移步骤与验证结果。原始 [doc/ssms.sql](ssms.sql) 保持不变，作为数据对照基线。

## 1. 目标环境

| 项目 | 取值 |
|---|---|
| 服务端 | openGauss 7.0.0-RC3（build `01b7e318`），`DBCOMPATIBILITY 'B'`，自动加载 Dolphin 插件 |
| 镜像摘要 | `opengauss/opengauss-server:latest`（实测 `sha256:d554be1b8b08165a8b19348f0ca236b5d61a4832ffadac0340ded973c34f38e4`） |
| 目标库与属主 | 数据库 `ssms`，属主 `gaussdb`（非超级用户） |
| JDBC 驱动 | `org.opengauss:opengauss-jdbc:7.0.0-RC3-og`，驱动类 `org.opengauss.Driver` |
| JDBC 连接串 | `jdbc:opengauss://127.0.0.1:5432/ssms` |
| 转换脚本 | [tools/mysql_to_opengauss.py](../tools/mysql_to_opengauss.py) |

## 2. 核心兼容性差异（MySQL 8 vs openGauss 7 B 模式）

B 兼容模式（加载 Dolphin 插件）下，`AUTO_INCREMENT`、`LIMIT offset, count`、`MEDIUMBLOB`、`ENGINE=InnoDB`、`0x...` 十六进制字面量及驼峰列名映射均直接兼容，不用全局改写 SQL。需要单独处理的是以下 6 项：

| 维度 | MySQL 8 | openGauss 7（B 模式） | 适配方案 |
|---|---|---|---|
| 建表外键校验 | `SET FOREIGN_KEY_CHECKS=0` 允许先建引用未定义父表的子表 | 不跳过父表存在性检查，先建子表会报 `relation does not exist` | 拆分为「DDL 建表 -> `INSERT` 导入数据 -> `ALTER TABLE ADD FOREIGN KEY`」三阶段执行 |
| 字符集与排序规则 | `mysqldump` 默认输出 `utf8mb3` / `utf8mb3_unicode_ci` | 建表时产生告警并回退为默认排序规则，导致大小写不敏感比较失效 | 转换脚本将 DDL 中的 `utf8mb3*` 映射为等价的 `utf8*` |
| `java.util.Date` 参数绑定 | `PreparedStatement.setObject` 自动推断为日期类型 | 抛出 `Can't infer the SQL type to use for an instance of java.util.Date` | DATE 列显式转为 `java.sql.Date`（`null` 保持 `NULL` 语义） |
| 自增主键获取 | `RETURN_GENERATED_KEYS` 只返回生成键列 | 返回插入行全部列；指定列名时生成 `RETURNING "id"`，B 模式下返回字符串 `"id"` | 改用无引号 `INSERT ... RETURNING id` 并通过 `executeQuery()` 读取 |
| 默认事务隔离级别 | `REPEATABLE READ`（可重复读） | `READ COMMITTED`（读已提交） | 在 `MysqlTool.getConnection()` 中显式设为 `TRANSACTION_REPEATABLE_READ` |
| 事务内异常行为 | 仅当前语句失败，同事务内后续查询仍可执行 | 事务进入中止（aborted）状态，后续 SQL 一律报错，直到回滚或结束 | DAO 层不再吞掉异常；事务边界统一回滚并复位连接状态 |

## 3. 应用侧代码改造

1. **驱动与连接池配置**（[pom.xml](../pom.xml)、[c3p0-config.xml](../src/main/resources/c3p0-config.xml)）
   - Maven 依赖由 `mysql-connector-java` 改为 `org.opengauss:opengauss-jdbc:7.0.0-RC3-og`，驱动类改为 `org.opengauss.Driver`。
   - 去掉配置文件里的明文密码，补充 `preferredTestQuery=SELECT 1`、`testConnectionOnCheckout=true` 等连接保活与检活参数。

2. **连接管理与外部化凭据注入**（[MysqlTool.java](../src/main/java/com/lizhou/tools/MysqlTool.java)）
   - 静态初始化按 `JVM 系统属性 > 环境变量 > c3p0-config.xml` 顺序读取配置；未提供密码时直接抛出 `IllegalStateException` 拒绝启动：

   | 配置项 | JVM 系统属性 | 环境变量 | 默认值 |
   |---|---|---|---|
   | URL | `ssms.jdbc.url` | `SSMS_DB_URL` | `jdbc:opengauss://127.0.0.1:5432/ssms` |
   | 用户名 | `ssms.jdbc.user` | `SSMS_DB_USER` | `gaussdb` |
   | 密码 | `ssms.jdbc.password` | `SSMS_DB_PASSWORD` | 无（必填） |

   - `getConnection()` 显式设置 `Connection.TRANSACTION_REPEATABLE_READ`。
   - `closeConnection()` 归还连接前检查 `!conn.getAutoCommit()`，有未提交事务先 `rollback()` 再关闭。

3. **DAO 层主键返回与异常传播**（[BaseDaoImpl.java](../src/main/java/com/lizhou/dao/impl/BaseDaoImpl.java)、[ScoreDaoImpl.java](../src/main/java/com/lizhou/dao/impl/ScoreDaoImpl.java)）
   - `insertReturnKeysTransaction` 去掉 SQL 末尾分号后拼接 `RETURNING id`，用 `executeQuery()` 读取首列整型主键。
   - 查询、更新与批量方法不再只打印堆栈，改为抛出 `IllegalStateException` 或向上传播 `SQLException`。
   - `getColumn` 改用数据源自动提交连接与 `try-with-resources`；`ScoreDaoImpl` 删去多余的手动 `MysqlTool.getConnection()` 调用。

4. **Service 层事务边界与数据类型适配**（`ClazzService`、`CourseService`、`ExamService`、`GradeService`、`ScoreService`、`StudentService`、`TeacherService`）
   - `ExamService` 与 `ScoreService` 新增 `toSqlDate(java.util.Date)`，把 `exam.getTime()` 显式转为 `java.sql.Date`。
   - 修正 `ClazzService`、`ExamService`、`GradeService`、`ScoreService`、`TeacherService` 在事务内混用自动提交连接的问题，全部改用当前事务连接 `conn`（`getList(conn, ...)` / `updateTransaction(conn, ...)`）。
   - `StudentService`、`TeacherService`、`ExamService` 将 `startTransaction()` 移入 `try` 块；各 Service 在 `catch` 块中捕获回滚异常并用 `e.addSuppressed(rollbackError)` 挂到原异常上，防止掩盖原始异常。

## 4. 数据迁移（导出、转换与导入）

### 4.1 源库导出与目标库建库

停写源库后执行导出（导出文件只放本地工作目录，不进仓库）：

```bash
mysqldump --host=127.0.0.1 --port=3307 --user=<user> --password \
  --single-transaction --skip-comments --skip-add-drop-table \
  --skip-lock-tables --skip-add-locks --set-gtid-purged=OFF \
  --no-tablespaces --hex-blob --default-character-set=utf8mb4 \
  ssms > ssms-before-opengauss.sql
```

- 必须显式指定 `--skip-add-locks`（只给 `--skip-lock-tables` 仍会输出 `LOCK TABLES`）。
- `--hex-blob` 将二进制列导出为 `0x...` 字面量。

用有建库权限的账号创建空 B 模式目标库（Dolphin 内置视图不触发基表空库校验）：

```sql
CREATE DATABASE ssms WITH OWNER = gaussdb DBCOMPATIBILITY 'B';
```

### 4.2 DDL 与 DML 转换

```bash
python tools/mysql_to_opengauss.py \
  --input ssms-before-opengauss.sql \
  --output ssms-opengauss-import.sql
```

脚本用引号与注释感知扫描器处理单行数百 KB 的 `0x...` BLOB 及含 `;`、`--` 的字符串字面量，规则如下：
- **剔除与解包**：去掉 `SET`、`LOCK/UNLOCK TABLES`、`USE`、`DISABLE/ENABLE KEYS`、`DROP TABLE` 及普通注释；解包 MySQL 条件注释 `/*!NNNNN ... */` 后按语句类型处理。
- **字符集映射与重排**：只在 DDL 的 `CHARACTER SET`、`CHARSET`、`COLLATE` 子句中把 `utf8mb3*` 映射为 `utf8*`；字符串与 `0x...` 字面量原样保留；按「前置空库校验 -> 全部 `CREATE TABLE` -> 全部 `INSERT` -> 全部 `ALTER TABLE ADD FOREIGN KEY`」输出为单事务脚本（`\set ON_ERROR_STOP on` + `BEGIN`/`COMMIT`）。
- **退出码**：`0` 成功；`2` 输入问题（缺文件、非 UTF-8、空文件、引号未闭合）；`3` 遇到不支持的语法（`INSERT ... SELECT`、列级 `REFERENCES`、未命名外键、触发器/存储过程/视图/`CREATE DATABASE`、真实双引号字符串），报出行号并中止。

### 4.3 导入目标库

必须用应用连接账号 `gaussdb` 导入，保证表属主与运行时权限一致：

```bash
# 交互输入密码（脚本内置 BEGIN/COMMIT，不要加 -1）
gsql -h 127.0.0.1 -p 5432 -U gaussdb -d ssms -f ssms-opengauss-import.sql

# 容器内执行（需显式指定 LD_LIBRARY_PATH）
docker exec -i -u omm <opengauss-container> env LD_LIBRARY_PATH=/usr/local/opengauss/lib \
  /usr/local/opengauss/bin/gsql -h 127.0.0.1 -p 5432 -U gaussdb -d ssms -f <import.sql>
```

> 自动化场景可用 `-2` 从标准输入管道传密码（该镜像忽略 `PGPASSWORD`），且 `-2` 必须与 `-c` 或 `-f` 合用。

## 5. 数据核对与回滚策略

### 5.1 导入核对

```sql
-- 预期基线：11 张基表，13 条外键
SELECT count(*) FROM pg_tables WHERE schemaname = 'public';
SELECT count(*) FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
 WHERE c.contype = 'f' AND n.nspname = 'public';
```

基准行数对照（合计 438 行）：`clazz` 13、`clazz_course_teacher` 8、`course` 10、`escore` 223、`exam` 2、`grade` 3、`grade_course` 13、`student` 70、`system` 1、`teacher` 12、`user` 83。

### 5.2 回滚策略

- **导入阶段失败**：单事务自动回滚，目标库保持为空，修好输入重跑即可。
- **应用切换失败**：当前 WAR 已去掉 MySQL 驱动，不能只改连接串回退；需要恢复迁移前的旧版 WAR 或 webapp 目录，并把切换后 openGauss 产生的增量数据单独导出迁回 MySQL（原 MySQL 在迁移期间保持只读未改）。
- **重试导入**：新建或换用另一个空的 B 模式库导入，不要靠删库重建重试。
