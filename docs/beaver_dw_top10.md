# Beaver dw_filtered：常用 10 张表子集与连接模式

写于 2026-10-23。下面的数字都是用脚本直接统计得出的（实测），推断的部分单独标明。

## 1. 数据与统计口径

- 题目：`~/semantic-catalog/data/beaver/query/data/dw_filtered.parquet`，3,312 道 dw 题。它由
  semantic-catalog 的 `scripts/filter_beaver_dw.py` 从官方 dw split（5,787 道）中筛出，只保留标注的表和等值
  连接键与 gold SQL 完全一致的题；只做结构检查，不执行 SQL，也不检查语义。
- 每道题用了哪些表、哪些连接键：取 `dw_filtered_audit.jsonl` 中从 gold SQL 解析出的 `sql_tables` 和
  `sql_join_keys`。在 3,312 道题上，`sql_tables` 与题目自带的 `tables` 标注全部一致。
- "用过"按题数计：一道题里同一张表或同一条连接键只记一次。
- 连接键是 SQL 中所有"列 = 列"的等式，不区分写在 `JOIN ... ON` 还是 `WHERE` 里。

## 2. 选表与选题

### 2.1 第一步：用过的题最多的 10 张表

3,312 道题共用到 dw 库 97 张表中的 53 张。按用过的题数取前 10：

| 排名 | 表 | 3,312 道题中用过的题数 | 954 道子集中用过的题数 |
|---|---|---|---|
| 1 | `SIS_DEPARTMENT` | 1,168 | 483 |
| 2 | `COURSE_CATALOG_SUBJECT_OFFERED` | 905 | 371 |
| 3 | `SIS_COURSE_DESCRIPTION` | 757 | 392 |
| 4 | `TIP_SUBJECT_OFFERED` | 728 | 301 |
| 5 | `ACADEMIC_TERMS` | 713 | 197 |
| 6 | `SUBJECT_OFFERED_SUMMARY` | 650 | 343 |
| 7 | `SIS_SUBJECT_CODE` | 625 | 318 |
| 8 | `ACADEMIC_TERMS_ALL` | 563 | 158 |
| 9 | `TIP_DETAIL` | 539 | 247 |
| 10 | `LIBRARY_SUBJECT_OFFERED` | 435 | 225 |

第 11 名 `FCLT_ORGANIZATION` 用过 428 道，和第 10 名只差 7 道；第 12 名 `CIS_COURSE_CATALOG` 用过 310 道。
这 10 张表大多围绕课程、院系和学期。

### 2.2 第二步：只用这 10 张表的题

所用表全部落在这 10 张表之内的题有 **954 道**，占 dw_filtered 的 29%。按每题涉及的表数：

| 表数 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| 题数 | 302 | 326 | 193 | 117 | 16 |

在子集里，`ACADEMIC_TERMS` 和 `ACADEMIC_TERMS_ALL` 从全集的第 5、8 名掉到最后两名（197、158 道），
说明这两张表常和 10 张以外的表一起出现，那些题被排除了。

## 3. 子集中的连接模式

### 3.1 连接方式高度集中

- 954 道题只涉及 22 种表对、34 种不同的连接键；没有同一张表自连接的连接键。
- 共 143 种不同的表集合，最常见的 20 种覆盖 453 道题（47%）。前五种都是两张表：

| 表集合 | 题数 |
|---|---|
| `ACADEMIC_TERMS`、`COURSE_CATALOG_SUBJECT_OFFERED` | 37 |
| `SIS_DEPARTMENT`、`SIS_SUBJECT_CODE` | 37 |
| `SIS_DEPARTMENT`、`SUBJECT_OFFERED_SUMMARY` | 34 |
| `SIS_COURSE_DESCRIPTION`、`SIS_DEPARTMENT` | 32 |
| `TIP_DETAIL`、`TIP_SUBJECT_OFFERED` | 29 |

### 3.2 连接围绕四个维度

几乎所有连接键都落在四个概念上，每个概念有一张中心表：

- **院系**：`SIS_DEPARTMENT.DEPARTMENT_CODE` 是中心。最常见的 4 条连接键都连到它：
  `SIS_COURSE_DESCRIPTION.DEPARTMENT`（173 道）、`SUBJECT_OFFERED_SUMMARY.OFFER_DEPT_CODE`（159）、
  `SIS_SUBJECT_CODE.DEPARTMENT_CODE`（150）、`TIP_SUBJECT_OFFERED.OFFER_DEPT_CODE`（140）。
- **课程号**：`SIS_COURSE_DESCRIPTION.COURSE` 是中心，连到 `SUBJECT_OFFERED_SUMMARY.COURSE_NUMBER`（121）、
  `COURSE_CATALOG_SUBJECT_OFFERED.SUBJECT_CODE`（104）、`SIS_SUBJECT_CODE.COURSE_NUMBER`（87）。
- **学期**：`ACADEMIC_TERMS.TERM_CODE` 或 `ACADEMIC_TERMS_ALL.TERM_CODE` 是中心。按列名统计，两边都叫
  `TERM_CODE` 的连接出现 366 次，是最多的一类。
- **科目 ID**：`TIP_DETAIL.SUBJECT_ID` 是中心，连到 `SUBJECT_OFFERED_SUMMARY`（79）、
  `LIBRARY_SUBJECT_OFFERED`（77）、`TIP_SUBJECT_OFFERED`（74）。

整体是几张开课、课程事实表通过院系、课程、学期、科目这几个维度相连的星型结构。

### 3.3 同一概念，列名不统一

连接两边的列名经常不同，agent 只看列名难以猜出怎么连：

- 院系代码叫 `DEPARTMENT_CODE`、`OFFER_DEPT_CODE` 或 `DEPARTMENT`；`DEPARTMENT_CODE = OFFER_DEPT_CODE` 出现
  299 次，`DEPARTMENT = DEPARTMENT_CODE` 出现 173 次。
- 课程号叫 `COURSE`、`COURSE_NUMBER` 或 `SUBJECT_CODE`；`COURSE = COURSE_NUMBER` 出现 208 次，
  `SUBJECT_CODE = COURSE` 出现 104 次，`COURSE = SUBJECT_CODE` 出现 57 次。
- `COURSE_CATALOG_SUBJECT_OFFERED` 与学期相连的列是 `EFFECTIVE_TERM_CODE`（92 次）。

### 3.4 同一对表，有多种连法

| 表对 | 连接列（题数） |
|---|---|
| `ACADEMIC_TERMS` 与 `COURSE_CATALOG_SUBJECT_OFFERED` | `TERM_CODE = EFFECTIVE_TERM_CODE`（92）、`TERM_CODE = TERM_CODE`（49） |
| `SIS_COURSE_DESCRIPTION` 与 `SIS_SUBJECT_CODE` | `COURSE = COURSE_NUMBER`（87）、`COURSE = SUBJECT_CODE`（57） |
| `SIS_DEPARTMENT` 与 `SIS_SUBJECT_CODE` | `DEPARTMENT_CODE`（150）、`SCHOOL_CODE`（32） |
| `TIP_DETAIL` 与 `TIP_SUBJECT_OFFERED` | `SUBJECT_ID`（74）、`TIP_SUBJECT_OFFERED_KEY`（32）、`TERM_CODE`（7） |
| `ACADEMIC_TERMS` 与 `ACADEMIC_TERMS_ALL` | `TERM_CODE`（72）、`ACADEMIC_TERMS_KEY`（14） |
| `SUBJECT_OFFERED_SUMMARY` 与 `TIP_DETAIL` | `SUBJECT_ID`（79）、`TERM_CODE`（13） |
| `LIBRARY_SUBJECT_OFFERED` 与 `TIP_DETAIL` | `SUBJECT_ID`（77）、`TERM_CODE`（18） |
| `LIBRARY_SUBJECT_OFFERED` 与 `TIP_SUBJECT_OFFERED` | `TERM_CODE`（21）、`SUBJECT_ID`（8）、`MASTER_SUBJECT_ID`（7）、`MASTER_SUBJECT_ID_SORT`（6）、`OFFER_DEPT_CODE`（6） |

同一道题同时用同一表对两条连接键（复合键或附加条件）的只有 32 例：`SIS_DEPARTMENT` 与
`SIS_SUBJECT_CODE` 的 `DEPARTMENT_CODE` 加 `SCHOOL_CODE` 10 例，`ACADEMIC_TERMS` 与
`COURSE_CATALOG_SUBJECT_OFFERED` 的两种学期列 9 例，其余 4 种表对共 13 例。所以上表的计数绝大多数是
不同题用了不同连法。仅凭连接键统计无法判断这些不同连法是题意本来不同（例如按生效学期还是开课学期），
还是模板生成带来的噪声（例如 `COURSE = SUBJECT_CODE`），需要导入数据库后抽题对比执行结果。

## 4. 对 view 设计的启发（推断，未验证）

- **院系维度 view**：以 `SIS_DEPARTMENT` 为中心，统一院系代码的列名，可覆盖最常见的 4 条连接键。
- **学期维度 view**：合并 `ACADEMIC_TERMS` 与 `ACADEMIC_TERMS_ALL`，两者本身就经常互连。
- **预连接 view**：对第 3.4 节中有多种连法的表对固定正确的连接键，收益可能最大；前提是先弄清哪种连法对应
  哪种问法，否则 view 会把原本做对的题改错。
- **改名 view**：第 3.3 节的列名不统一正是 1:1 改名 view 的用武之地。

注意事项：

- 挖 view 只能用训练题的 gold SQL，测试题不能参与，否则泄漏答案。
- 954 道题中有大量同模板生成的相似题，切分训练、测试时要按相似题分组，否则会高估 view 的效果。

## 5. 实验计划：固定 join path 的 view 能否带来提升

写于 2026-10-26。这一节记录 2026-10-26 讨论定下的实验计划和第一轮的进展。数字来源分两类：题目相关的来自对
`db_agent_view/data/tasks_gold.jsonl` 的统计（用 sqlglot 解析 gold SQL），数据相关的来自用 `agent_view_agent`
账号做的只读查询。

题目集合说明：上面第 1 到 4 节统计的是 954 道题。实验用的 MySQL 库 `db_agent_view` 去掉了 9 道 gold 可疑的题，
只有 945 道，下面的统计都基于这 945 道。

### 5.1 实验设计

- **问题**：给 agent 一个与题目连接方式完全一致的 join view，正确率能否提高。
- **对照**：同一组题跑两组。基线组不建 view；view 组在同一个库里加一个 `av_` 开头的 view 和它的说明清单。
  除了 view 和说明清单，两组的其他设置完全相同。
- **注入 domain knowledge，不注入 column mapping**：
  - 带 domain knowledge 的题，把 Beaver 标注的 domain knowledge 原文逐条写进 prompt，同时保存一份到容器里的
    `/tmp/c0-task/context.md`。不带的题不注入。两组注入的内容一字不差。
  - domain knowledge 里几乎都用占位符 `TABLE.列名` 代替表名（1,452 条里有 1,435 条），prompt 中说明 `TABLE`
    指"有这个列的那张表"。
  - domain knowledge 原样注入，不筛掉和题目无关的条目。这是有意的选择，因为两组拿到的噪声相同。
- **"使用这个 join"的定义**：整条 join path 完全一致，即题目标注的表集合相同，且等值连接键集合相同（比较时
  不看顺序，也不看连接键左右两边的顺序）。
- **模型设置**：OpenClaw 运行 gpt-5.1，思考档位为 medium，请求中带 `reasoning_effort: "medium"`（见 5.5 节）。
  每题跑 3 个 seed，用 `evaluate.py` 计算严格 EX 和宽松 EX。

### 5.2 候选 join path

945 道题中，涉及 3 张或 4 张表的有 512 道，分属 128 条不同的 join path。4 张表的 path 最大一组只有 10 道题，
所以每条 path 的题全部使用，不再抽样。

3 张表中题数最多的 4 条：

| | 第 1 条 | 第 2 条 | 第 3 条 | 第 4 条 |
|---|---|---|---|---|
| 表 | `SIS_COURSE_DESCRIPTION`、`SIS_DEPARTMENT`、`TIP_SUBJECT_OFFERED` | `SIS_COURSE_DESCRIPTION`、`SIS_SUBJECT_CODE`、`SUBJECT_OFFERED_SUMMARY` | `LIBRARY_SUBJECT_OFFERED`、`SUBJECT_OFFERED_SUMMARY`、`TIP_DETAIL` | `LIBRARY_SUBJECT_OFFERED`、`SIS_COURSE_DESCRIPTION`、`SIS_SUBJECT_CODE` |
| 连接中心 | 系代码 | 课程号 | `SUBJECT_ID` | 课程号 |
| 题数 | 21 | 18 | 18 | 17 |
| 带 domain knowledge 的题 | 21 | 12 | 0 | 14 |
| 原表之间有外连接的题 | 1 | 0 | 1 | 0 |
| 同一张表用了两次的题 | 5 | 3 | 8 | 5 |
| 三表 inner join 的行数 | 189,805 | 4,307 | 未测 | 17,792 |
| 和最大的 4 表 path 共用的表 | 3 张 | 2 张 | 1 张 | 1 张 |

各条的连接键：

- 第 1 条：`SIS_COURSE_DESCRIPTION.DEPARTMENT = SIS_DEPARTMENT.DEPARTMENT_CODE`，
  `SIS_DEPARTMENT.DEPARTMENT_CODE = TIP_SUBJECT_OFFERED.OFFER_DEPT_CODE`。
- 第 2 条：`SIS_COURSE_DESCRIPTION.COURSE = SIS_SUBJECT_CODE.SUBJECT_CODE`，
  `SIS_COURSE_DESCRIPTION.COURSE = SUBJECT_OFFERED_SUMMARY.COURSE_NUMBER`。
- 第 3 条：`LIBRARY_SUBJECT_OFFERED.SUBJECT_ID = TIP_DETAIL.SUBJECT_ID`，
  `SUBJECT_OFFERED_SUMMARY.SUBJECT_ID = TIP_DETAIL.SUBJECT_ID`。
- 第 4 条：`LIBRARY_SUBJECT_OFFERED.COURSE_NUMBER = SIS_SUBJECT_CODE.COURSE_NUMBER`，
  `SIS_COURSE_DESCRIPTION.COURSE = SIS_SUBJECT_CODE.COURSE_NUMBER`。

最大的 4 表 path 有 10 道题，以系代码为中心：
`SIS_COURSE_DESCRIPTION.DEPARTMENT = SIS_DEPARTMENT.DEPARTMENT_CODE`、
`SIS_DEPARTMENT.DEPARTMENT_CODE = SUBJECT_OFFERED_SUMMARY.OFFER_DEPT_CODE`、
`SIS_DEPARTMENT.DEPARTMENT_CODE = TIP_SUBJECT_OFFERED.OFFER_DEPT_CODE`。

### 5.3 总体安排

一共建 3 个 view：从上表中选两条 3 表 path，再加最大的 4 表 path。先只做一条 3 表 path，跑通"基线组对 view 组"
的完整流程后，再做另外两个。

第一轮选第 4 条，实验名 `join3_course_number`，理由如下：

- **domain knowledge 能直接对上 view 的列名。** 这条 path 的 domain knowledge 只用到 `DEPARTMENT_NAME`、
  `IS_DEGREE_GRANTING` 和 `DEPARTMENT` 三列。`DEPARTMENT_NAME` 和 `SCHOOL_NAME` 在 `SIS_COURSE_DESCRIPTION` 与
  `SIS_SUBJECT_CODE` 中同名，但实测在连接结果的每一行上两边的值都相同（不同的行数为 0），view 里各保留一列、
  沿用原列名即可。gold SQL 取 `DEPARTMENT_NAME` 时总是取自 `SIS_COURSE_DESCRIPTION`。
- **inner join 基本不丢数据。** `LIBRARY_SUBJECT_OFFERED` 的 10,000 行全部能匹配上，连接后 17,792 行。行数变多
  是因为 `SIS_COURSE_DESCRIPTION` 里同一门课有多行（695 行，630 个不同的课程号），属于适度重复，不是多对多膨胀。
- **原表之间全是 inner join**，一个 inner join view 就能覆盖全部 17 道题。
- **和 4 表 path 重叠最少**，只共用 `SIS_COURSE_DESCRIPTION`，连接中心也不同。

其余三条没选的原因：

- 第 1 条是 4 表 path 的子集，而且按系代码多对多连接，近 19 万行，agent 在上面做聚合容易被重复行带偏。
- 第 2 条的 inner join 会丢掉 `SUBJECT_OFFERED_SUMMARY` 约 74% 的行（10,000 行里只有 2,578 行能匹配上）。
- 第 3 条没有 domain knowledge，不适合"注入 domain knowledge"的设定。

第二条 3 表 path 从第 1、2 条中选，等第一轮结果出来再定。第 2 条和第 4 条共用两张表、连接中心都是课程号；第 1 条
和 4 表 path 重叠。无论选哪条，都会有一些重叠。

### 5.4 view 的设计原则

- **命名**：view 以 `av_` 开头，放在 `db_agent_view` 库中，原表保留不动。agent 账号需要能 SELECT 这些 view。
- **domain knowledge 文本不改，由 view 的列命名来迁就它。**
  - 不和其他表重名的列，保留原列名，这样 `TABLE.X` 可以直接理解成 view 的 X 列。
  - 重名的列，先实测连接后两边的值是否总相同。总相同就只保留一列，用原列名；不总相同时，以 gold SQL 实际取值的
    那张表为准保留原名，另一列加表名前缀。
  - 不在 view 组里把 domain knowledge 改写成 view 的列名，否则两组的提示不同，测出的提升会混进改写的效果。
- **说明清单**：写清楚 view 的每一列来自哪张原表的哪一列、连接条件，以及连接造成的行重复。例如在这个 view 上
  算单张表的统计（如平均选课人数）时，需要先去重。
- **inner join 还是 left join**：
  - 经典的物化视图做法是只物化外连接，遇到 inner 查询时由优化器自动加"右表非空列 IS NOT NULL"来还原（Larson 与
    Zhou，VLDB 2005；以 Galindo-Legaria，SIGMOD 1994 为理论基础）。这些文献是凭记忆引用的，没有核对原文。
  - 在我们的设定里，读 view 的是 agent，没有优化器替它补这个条件，所以不能直接照搬。
  - 第一轮的 path 在原表之间全是 inner join，只建 inner join view。
  - 以后遇到确实需要 left join 的 path，物化 left join 版本，加一个显式的匹配标记列（如 `has_offer`），并在说明
    清单里写明 inner 语义的查询要加这个条件。不同时放 inner 和 left 两个 view，避免 agent 选错。
  - 相关工作 *The Case for Text-to-SQL Friendly Logical Database Design* 按表集合的频繁项集挖 view，每个表集合
    一个 view，没有区分连接类型。

### 5.5 第一轮进度（`join3_course_number`）

已完成：

1. **固定题单。** `db_agent_view/build_join_experiment.py` 生成了 `db_agent_view/experiments/join3_course_number/`，
   包括 17 道题的 `manifest.jsonl`、14 道题的 `domain_knowledge_contexts.jsonl` 和记录来源的 `provenance.json`。
   不带 domain knowledge 的 3 道题是 dw_2593、dw_2946、dw_2959。
2. **runner 支持按题注入。** `runner/run_agent.py` 新增了 `--context-path` 参数，每题的日志目录会保留一份
   `context.md`，运行目录下会记录注入文件的 sha256。
3. **第一次基线（作废）。** 结果目录是 `runs/join3_course_number/baseline_dk/seed{0,1,2}`。3 个 seed 共 51 次作答，
   严格 EX 和宽松 EX 都是 0。这次运行实际没有开推理：OpenClaw 把自定义模型标成不支持推理，而且把非 OpenAI 的
   base URL 当作代理，不发 `reasoning_effort`，51 份日志的 `thinkingLevel` 都是 off。
4. **runner 开启推理。** 新增 `--thinking` 参数，默认 medium。onboard 后把模型的 `reasoning` 和
   `compat.supportsReasoningEffort` 设为 true。在容器里用假服务器抓包，实测请求中带上了
   `"reasoning_effort": "medium"`。

第一次基线全错的原因，可供后续对照：50 份能解析的 `final_sql` 全部用了 `SUBJECT_OFFERED_SUMMARY`，没有一份用到
gold 的 `LIBRARY_SUBJECT_OFFERED`。最常见的组合是 `SUBJECT_OFFERED_SUMMARY` 加 `SIS_DEPARTMENT`（24 份）。
题目只说"开设的科目"，而库里有 `SUBJECT_OFFERED_SUMMARY`、`LIBRARY_SUBJECT_OFFERED`、
`COURSE_CATALOG_SUBJECT_OFFERED` 等名字相近的开课表，题目没有提示该用哪张。

5. **第二次基线（medium 档位）。** 结果目录是 `runs/join3_course_number/baseline_dk_medium/seed{0,1,2}`。
   51 份日志都确认 `thinkingLevel` 为 medium，17 道题在 3 个 seed 中全部跑完。严格 EX 和宽松 EX 仍都是 0/51。
   - 评测本身没有问题：用 agent 账号重新执行 17 道题的 gold SQL，交给 `relaxed_compare`，17/17 判为正确。
   - 51 份 `final_sql` 中有 50 份用了 `SUBJECT_OFFERED_SUMMARY`，0 份用了 `LIBRARY_SUBJECT_OFFERED`；最常见的组合仍是
     `SUBJECT_OFFERED_SUMMARY` 加 `SIS_DEPARTMENT`（37 份）。51 份日志都在表清单里见过 `LIBRARY_SUBJECT_OFFERED`，
     但只有 1 份查看过它的结构或数据。17 道题的题目文字都没有提到 library。
   - 两张开课表的数据完全不同。2014FA 学期 `SUBJECT_OFFERED_SUMMARY` 有 253 行、选课人数合计 588；
     `LIBRARY_SUBJECT_OFFERED` 有 442 行、合计 13,043；科目和选课人数都相同的只有 8 行。选错表就不可能答对。
6. **建 view。** DDL 在 `db_agent_view/views/join3_course_number.sql`，删除脚本是
   `db_agent_view/views/drop_join3_course_number.sql`。
   - view 名为 `av_library_offering_course`，实测 17,792 行，和三表 inner join 相同。
   - 同名列：`COURSE_NUMBER` 只保留一列（它就是连接键）；`DEPARTMENT_NAME` 和 `SCHOOL_NAME` 取自
     `SIS_COURSE_DESCRIPTION`（连接后两边不同的行数都是 0）；三张表的 `WAREHOUSE_LOAD_DATE` 分别加
     `LSO_`、`SSC_`、`SCD_` 前缀。
   - MySQL 的 view 不能加注释，说明清单放在 `av_catalog` 表里，记录连接条件、行的粒度和每组列的来源。
   - 在 view 上重写 dw_5353 的 gold SQL，得到 20，和 gold 相同。
7. **3 题试跑：agent 要提示才会用 view。** 抽 dw_356、dw_1303、dw_2959，seed 0，结果在
   `runs/join3_course_number/view_probe3/`。
   - 只建 view、不加提示：3 题都没用 view，仍按表名选了 `SUBJECT_OFFERED_SUMMARY`。
   - 弱提示（"库里有 `av_` 开头的 view，选表前先读 `av_catalog`"）：3 题都读了 `av_catalog`，但都没用 view。
   - 强提示（弱提示后加一句"凡涉及开课的问题，优先用 `av_library_offering_course`，不要自己连原表"）：3 题的
     最终 SQL 都只用 view。强提示现已写进 `build_join_experiment.py` 的 `view_note`，即 view 组每题上下文的开头。
8. **评测改为只在题目要求排序时比对顺序。** 17 道题中 gold 带 `ORDER BY` 的有 11 道，其中 9 道的题目原文没有要求排序。
   现在宽松 EX 只在 gold 有序、且题目原文要求排序时才比对行顺序；严格 EX 仍沿用上游规则。判断题目是否要求排序用的是
   `evaluate.py` 的 `question_requests_order`，按关键词匹配，同一句里出现窗口函数用语的不算。在全部 945 道题上，
   gold 有序的 676 道中仍比对顺序的有 165 道。17 道题里只剩 dw_2593 需要比对顺序。
9. **view 组。** 结果目录是 `runs/join3_course_number/view_dk_medium/seed{0,1,2}`。设定和第二次基线相同，只多了
   view 和强提示。51 份 `final_sql` 都引用了 `av_library_offering_course`。
10. **排除 3 道 gold 一定有错的题。** 只排除"无论题目怎么理解，gold 结果都和题意矛盾"的题；有歧义的题一律按 gold 算。
    - dw_356：题目要每个院系一行。gold 找最大选课人数时按"院系、科目"分组，统计也按科目算，结果是 2376 行，
      每行一门科目，方差都是 0。
    - dw_1303：其中一个子查询和 dw_356 逐字相同，结果是 822 行，方差都是 0。
    - dw_2593：gold 在 `WITH ROLLUP` 里对每个院系的方差再求一次方差，15 个院系行的方差全是 0。同样的条件下
      dw_503 的 gold 算出 Urban Studies 的方差是 308.54。
    - 不排除的题：dw_5586 的题目要求只用 `STDDEV`，gold 用的却是 `STDDEV_SAMP`。这可能沿用了 Oracle 的写法
      （Oracle 的 `STDDEV` 是样本标准差），但另外 8 道题说法相同，gold 却用了 MySQL 的 `STDDEV`（总体标准差），
      所以不能判定 gold 一定错。dw_396 的 gold 多了一列题目没要的 `benchmark`，但其余内容都对。
      dw_124 和 dw_503 是题目有歧义。
    - 排除写在 `build_join_experiment.py` 的 `excluded_tasks` 里，并附有理由。此后实验目录只含 14 道题，
      评测统一用 `runs/join3_course_number/eval_data14`。
11. **文字注入对照组 B 和 C。** 目的是比较"信息量相同时，知识做成 view 和写进 prompt 哪个更好"。两组运行时，
    库里既没有 view 也没有 `av_catalog`（跑之前执行删除脚本），提示的语气和 D 组的强提示一样强，后面接的
    domain knowledge 和其他组逐字相同。
    - B 组（`join_text_contexts.jsonl`）：用自然语言说明开课表该用 `LIBRARY_SUBJECT_OFFERED`、两条连接条件、
      连接后行的粒度，以及各类列来自哪张表，不出现 view 的名字。
    - C 组（`join_sql_contexts.jsonl`）：由 `view_as_sql_note` 从 view 的建库脚本里抽出 `SELECT`，改写成名为
      `library_offering_course` 的 `WITH` 子句，再附上 `av_catalog` 的 5 条说明原文。C 组和 D 组的信息逐字相同，
      区别只在于这段 SQL 是写在 prompt 里，还是作为库里的对象存在。
    - 每题上下文中 domain knowledge 之前的说明长度：D 组 405 字符，B 组 1081 字符，C 组 3044 字符。

**目前的主要结果。** 14 道题，每组 3 个 seed，共 42 次作答。各组都用新的顺序规则评测，thinking 档位都是 medium。
结果目录是 `runs/join3_course_number/` 下的 `baseline_dk_medium`、`join_text_dk_medium`、`join_sql_dk_medium` 和
`view_dk_medium`。

| 组 | 每个 seed 的宽松 EX | 严格 EX | 宽松 EX |
|---|---|---|---|
| A 基线（domain knowledge） | 0、0、0 | 0/42 | 0/42 |
| B 文字连接建议 | 4、2、6 | 6/42 | 12/42 |
| C view 定义写成文字 | 7、6、4 | 8/42 | 17/42 |
| D view 和强提示 | 4、8、5 | 6/42 | 17/42 |

- **选表问题由文字就能解决。** B 组 40 份能解析的 `final_sql` 全部用了 `LIBRARY_SUBJECT_OFFERED`，39 份用齐三张表
  并写对两条连接条件；C 组 40 份都用了给出的 `library_offering_course`。基线则有 50/51 份用了 `SUBJECT_OFFERED_SUMMARY`。
- **完整的连接 SQL 比文字描述更有效，但做成 view 没有额外提高准确率。** B 组到 C 组宽松 EX 从 12 升到 17；C 组和
  D 组信息相同，宽松 EX 都是 17/42。
- **各组错的题不同。** D 组在 dw_323、dw_2959 上 3 次全对，B 组、C 组各只对 1 到 2 次；D 组在 dw_5466 上全错（view
  中的重复行被重复计算），B 组、C 组各对 2 次。按题的差异在 14 题、3 个 seed 的规模下可能只是波动。
- **成本**（来自 `task_costs.json`；API 返回的 token 用量全为 0，所以没有 token 数）：

  | 组 | 执行命令次数中位数 | 平均每题 SQL 报错 | 用时中位数 |
  |---|---|---|---|
  | B | 9 | 0.21 | 117 秒 |
  | C | 5.5 | 0.19 | 136 秒 |
  | D | 8 | 0.86 | 106 秒 |

  C 组 agent 几乎不用探索就直接写查询。D 组报错多，主要是查询 `av_catalog` 时猜错列名，例如查了不存在的 `VIEW_NAME`。
- 被排除的 3 题在 D 组里一次也没答对，所以若按 17 道题计，D 组是严格 6/51、宽松 17/51。
- D 组里真正因为 view 而错的是 dw_5466 和 dw_249。`SIS_COURSE_DESCRIPTION` 中每个课程号有两行，
  `IS_DEGREE_GRANTING` 一行为 Y、一行为 N，所以 view 里每条开课记录出现两次：Mathematics 有 2254 行，但只对应
  1127 条开课记录。`av_catalog` 已写明"an offering can appear more than once"，但 agent 没在行级别筛选 Y，
  Mathematics 的总人数变成 90908，是 gold 的 2 倍。
- 3 次作答因运行环境出错而失败，目前按错题计：B 组 seed 2 的 dw_5615（`docker exec` 失败）和 C 组 seed 2 的
  dw_2946（模型输出中途截断）。用原命令重跑对应目录即可补上，最多各加 1 题，不影响 C 组和 D 组持平的结论。
  另有 4 次是 agent 输出的 `final.json` 不是合法 JSON，属于 agent 自身的失败，不重跑。

**对论点的含义。** 在单条 path 上，"view 比信息相同的文字注入准确率更高"不成立。现有结果支持的是：大部分收益来自
"用哪张表、怎么连"这条信息本身，而以可执行 SQL 的形式给出比文字描述更有效。view 可能的优势在规模上：C 组每条知识
要占约 3000 字符 prompt，D 组只需一句引导，内容留在库里按需读取；知识条目多了以后，C 组的 prompt 会线性变长，还要先
检索放哪几条。这一点需要同时提供多条 path 的知识来验证。

待完成：

1. 补跑上面 2 次运行环境失败的作答。
2. 设计规模实验：同时提供多条 path 的 view 或文字知识，比较准确率、prompt 长度和成本。
3. 再做第二条 3 表 path 和最大的 4 表 path。
4. 视需要做 D 组的两个变体，区分引导和内容说明的作用：只给引导、不给 `av_catalog`；把 `av_catalog` 的说明直接放进
   prompt、不给引导。

### 5.6 解读结果时要注意的地方

- **地板效应**：如果基线仍接近 0，任何提升看起来都会很大。
- **提升来自哪里**：view 的一部分作用是告诉 agent 该用哪张开课表，而这一点题目本身就没交代清楚。分析时要把
  "view 帮 agent 选对了表"和"view 帮 agent 连对了键"分开统计：看 agent 是否用了 view，用了之后答对多少，剩下的
  错误再分成"用了 view 仍然错"和"没用 view"两类。
- **domain knowledge 噪声**：第 4 条 path 的 35 条 domain knowledge 中有 7 条没有被 gold 用到。例如 dw_356 和
  dw_503 拿到的是和数学系、Course 18 相关的无关条目，缺少 degree-granting 那一条；dw_323 拿到了无关的 Economics
  条目；不带 domain knowledge 的 3 道题，gold 却需要 `IS_DEGREE_GRANTING = 'Y'`。
- **题量小**：每条 path 只有 10 到 21 道题，结论需要多个 seed 和多条 path 互相印证。
