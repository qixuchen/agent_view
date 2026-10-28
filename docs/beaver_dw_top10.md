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

### 5.7 第二轮方案：三个院系 view（`dept_views`）

**各组的定位。** C 组和 D 组给出的是 gold 实际用的连接，等于事先知道了答案的连接方式，应当看作上限。B 组的文字建议
同样写出了具体的连接条件，也是偏乐观的文字记忆。现实中的文字记忆方法（如 TK-Boost）存的多是抽象规则：它的 17 条
示例规则里只有 3 条提到连接，而且都是通用说法。所以 B 组代表的是"文字记忆最好能做到的程度"。

**为什么不建一个 4 表 view。** 原计划的 4 表 path 是 `SIS_COURSE_DESCRIPTION`（下称 SCD）、`SIS_DEPARTMENT`（SD）、
`SUBJECT_OFFERED_SUMMARY`（SOS）和 `TIP_SUBJECT_OFFERED`（TSO），共 10 题。读 gold SQL 发现，没有任何一个 SELECT
同时用到 3 张以上的表；4 张表一起内连接会得到 23,974,591 行。dw_827、dw_1140、dw_1287、dw_2417 里的 LEFT JOIN
都发生在已经聚合过的 CTE 结果之间，所以各个 view 用内连接即可。

**按连接块选 view。** 用 sqlglot 把每道 gold SQL 拆成 SELECT。一个 SELECT 直接读两张以上原表时，它的表集合加上它
自己 JOIN ON 和 WHERE 中两边都带表名的"列 = 列"条件，算一个连接块。一道题的每个连接块都和某个 view 的连接完全一致，
才算这组 view 覆盖了这道题；只用到 view 中部分表的块不算，因为多出的表会让行数膨胀。实现是
`build_join_experiment.py` 里的 `join_blocks`（拆块）和 `select_view_set_tasks`（判定覆盖并选题）。在全部 945 题、
67 种连接块上，选三个 view 时最多能覆盖 101 题。我们选了覆盖 98 题的第三种组合，因为它包含 4 表 path 里的连接：

| view | 连接 | 一行代表什么 | 行数（实测） |
|---|---|---|---|
| `av_dept_course` | `SCD.DEPARTMENT = SD.DEPARTMENT_CODE` | 一条课程描述及其院系 | 695 |
| `av_dept_offering_summary` | `SD.DEPARTMENT_CODE = SOS.OFFER_DEPT_CODE` | 一条开课汇总记录及其院系 | 9,983 |
| `av_dept_tip_offering_course` | 上面两条中 SD 与 SCD 的连接，加 `SD.DEPARTMENT_CODE = TSO.OFFER_DEPT_CODE` | 一条 TIP 开课记录与同院系每条课程描述的组合 | 189,805 |

98 题按用到的 view 组合分：只用 SD+SOS 的 34 题，只用 SCD+SD 的 32 题，只用三表 view 的 18 题，同时用 SCD+SD 和
SD+SOS 的 6 题，同时用三表 view 和 SD+SOS 的 6 题，同时用 SCD+SD 和三表 view 的 2 题。

**20 题题单。** 需要组合使用多个 view 的题全部入选：同时用三表 view 和 SD+SOS 的 6 题（dw_827、dw_1043、dw_1140、
dw_2417、dw_2519、dw_2563），以及同时用 SCD+SD 和三表 view 的 2 题（dw_1628、dw_1658）。其余 90 题按题号排序后用
`random.Random(0).sample` 抽 12 题：dw_306、dw_334、dw_2040、dw_3742、dw_4462、dw_5144、dw_5161、dw_5215、dw_5433、
dw_5452、dw_5526、dw_5716。抽样没有分层。20 题里 18 题带 domain knowledge，dw_3742 和 dw_4462 没有。

**gold 筛查。** 20 题的 gold 都执行成功，结果也都和原 dw 库一致。有几题的某些列全部相同，都能用题目中的过滤条件
解释：例如 dw_334 和 dw_5716 只查 EECS 一个系，dw_5526 只查数学系，所以按系名做的 dense rank 全为 1。没有发现一定
有错的 gold，因此不排除任何题。这次只检查了结果的形状，没有像第一轮那样逐条读 gold SQL。（后来逐条读 dw_5526 的
gold SQL，发现它的重复行无法解释，见 5.9 节的"gold 的可信度"。）

**view 的列。** 三个 view 都保留各表的全部列。同名列的处理依据的是实测：

- SD 和 SCD 连接后的 695 行里，SCD 的 `DEPARTMENT_NAME`、`SCHOOL_NAME`、`DEPT_NAME_IN_COMMENCEMENT_BK`、
  `SCHOOL_NAME_IN_COMMENCEMENT_BK` 每行都和 SD 的同名列相等，所以只保留 SD 的一份。
- `IS_DEGREE_GRANTING` 有 230 行两边不同，SCD 里也有 23 个课程号同时有 Y 和 N 两行。所以 SD 的列保留原名，SCD 的列
  改名为 `SCD_IS_DEGREE_GRANTING`。这 20 题的 gold 中，`IS_DEGREE_GRANTING` 取自 SD 27 次，取自 SCD 3 次
  （dw_1658、dw_5433）。
- 各表的 `WAREHOUSE_LOAD_DATE` 分别加 `SD_`、`SCD_`、`SOS_`、`TSO_` 前缀。
- SOS 的 `OFFER_DEPT_NAME`、`OFFER_SCHOOL_NAME` 和 SD 的 `DEPARTMENT_NAME`、`SCHOOL_NAME` 每行都相等，但它们本身
  不同名，所以都保留。
- 之前记录的"SD 有 1 个系代码重复"是一行系代码为 NULL 的记录被算了进去。SD 实际没有重复的系代码，所以 view 里
  不会因此出现重复行。

建库脚本是 `db_agent_view/views/dept_views.sql`，`av_catalog` 里为三个 view 写了 13 条说明，写明连接条件、行的
粒度和列的来源。说明只描述粒度，不建议去重，因为 gold 本身就是在这些行上统计的。删除脚本
`drop_dept_views.sql` 会连同 `av_catalog` 表一起删掉，保证 A、B、C 组的库里没有任何 `av_` 对象。

**各组的提示。** 四组都在 domain knowledge 之前加一段说明，文字在 `build_join_experiment.py` 的
`EXPERIMENTS["dept_views"]` 里，生成的文件在 `db_agent_view/experiments/dept_views/`。

- D 组（`view_contexts.jsonl`，741 字符）：说明库里有 `av_` 开头的 view、先读 `av_catalog`，然后逐个列出三个
  view 各自连接了哪些数据，要求优先用 view 而不是自己连表。
- B 组（`join_text_contexts.jsonl`，1,428 字符）：用文字写出三种连接的条件和行的粒度，再说明哪些同名列取值相同、
  `IS_DEGREE_GRANTING` 在两张表里含义不同。B 组的信息和 D 组 `av_catalog` 的说明对齐，只是没有 SQL。
- C 组（`join_sql_contexts.jsonl`，7,760 字符）：由 `views_as_sql_note` 从建库脚本中抽出三段 `SELECT`，分别写成
  名为 `dept_course`、`dept_offering_summary`、`dept_tip_offering_course` 的 `WITH` 子句，每段后面附上对应的
  `av_catalog` 说明原文。C 组的 SQL 和 D 组的 view 定义逐字相同。
- 三组都写了同一句"一道题可能要用到多个 view（或连接），先分别算各部分，再合并结果"。这句话描述的是怎么使用
  这些 view，不涉及具体题目，但论文里要如实交代。

C 组的说明长度是第一轮（3,044 字符）的约 2.5 倍，D 组只从 405 字符增加到 741 字符。这是"知识越多，写进 prompt
的方案越长"的第一个数据点。

**已知风险。** SOS 和 TSO 都是开课记录，题目通常只写"subjects offered"。D 组的引导只按表名区分两者，agent 可能
选错。B、C、D 三组在这一点上的处境相同，所以不影响组间比较，但可能让三组的分数都偏低。

**运行顺序。** 先跑 A（只有 domain knowledge）、B、C 三组，每组 3 个 seed，结果放在 `runs/dept_views/` 下；评测
数据目录是 `runs/dept_views/eval_data20`。这三组跑完后，再建 view 跑 D 组。

### 5.8 几种提供连接知识的方法：优劣对比

本节是讨论记录。凡是给出数字的，都来自第一轮（`join3_course_number`）或本轮的实测；关于静态分析的部分是推断，没有
做过实验。

**静态分析。** 这里指不借助 ground truth、只看库本身来找可连接的表，例如用值的包含或重叠关系推断外键、按列名和类型
的相似度找候选连接。

- 能做到的：找出结构上成立的连接条件（如 `SIS_DEPARTMENT.DEPARTMENT_CODE = SUBJECT_OFFERED_SUMMARY.OFFER_DEPT_CODE`），
  统计连接后行的粒度，检查两张表的同名列取值是否相同。本轮确认 `DEPARTMENT_NAME` 两边相等、`IS_DEGREE_GRANTING`
  有 230 行不同，用的就是这类不需要 gold 的检查。
- 做不到的：判断某类问题该用哪些表、哪些列。三张开课表都能按代码连到其他表，结构上都成立，静态分析没有信号能区分
  哪一张是对的。
- 由此带来的问题：候选太多、准确率低（系代码、课程号这类短代码在很多列之间都有重叠，偶然成立的候选很多）；只给出
  两两之间的边，不知道哪几条要拼成一条路径、哪些部分要分开算再合并。
- 根本原因是没有信息可以用来验证"这条连接对这类问题是否正确"。查询日志能提供一些信号，但那已经不是纯静态分析。

**B 组：文字连接建议。** 直接写出该用哪些表和连接键，以及行的粒度和列的来源。

- 它给出的表和连接键来自 gold，所以已经强于一般的静态分析，可以看作"文字记忆的上限"，不是一个弱基线。现实中的
  文字记忆方法（如 TK-Boost）存的多是抽象规则，17 条示例规则里只有 3 条提到连接，而且都是通用说法。
- 第一轮里，基线 51 份能解析的 SQL 中有 50 份用了 `SUBJECT_OFFERED_SUMMARY`，宽松 EX 为 0/42；B 组 40 份全部改用
  `LIBRARY_SUBJECT_OFFERED`，宽松 EX 为 12/42。提升主要来自"用哪张表"这条信息，而这正是静态分析给不出的。
- 不足：表怎么组合、同名列怎么取舍，仍要 agent 自己写对。

**C 组：把 view 的定义 SQL 写进 prompt。** 选择、组合都已做完，agent 可以直接把这段 SQL 当作 `WITH` 子句使用。

- 第一轮宽松 EX 为 17/42，高于 B 组的 12/42。agent 几乎不用探索，执行命令次数中位数为 5.5，平均每题 SQL 报错 0.19 次。
- 不足：prompt 随知识量线性变长。第一轮每题的说明是 3,044 字符，本轮三个 view 时是 7,760 字符。知识多了以后，还要
  先检索出该放哪几条。此外，写在 prompt 里的 SQL 没有人保证它和当前的库一致。

**D 组：在库里建好 view，再加引导和 `av_catalog`。**

- 第一轮宽松 EX 为 17/42，和 C 组相同，所以在单条 path 上，"view 比信息相同的文字更准"不成立。
- 代价：平均每题 SQL 报错 0.86 次，主要是查 `av_catalog` 时猜错列名；dw_5466 因为 view 里的重复行被重复计算而全错。
  另外，只建 view 不加引导时，agent 基本不会去用。
- 可能的优势（多数待验证）：
  1. prompt 长度不随知识量增长：本轮 D 组的说明是 741 字符，C 组是 7,760 字符。内容留在库里，由 agent 按需读取。
  2. agent 可以直接查询 view，例如取样、计数，亲眼确认行的粒度；文字描述没法这样验证。目前 agent 还没有利用这一点。
  3. view 由数据库实际执行过，表结构变化时会直接报错；可以做版本管理、测试和权限控制，也能被别的 agent 和 BI 工具复用。

**对比的两层结构。**

1. 有没有任务信号：静态分析没有，B、C、D 都有。这一层的差距是能否知道该选哪张表、哪条路径。第一轮基线 0/42 和
   B 组 12/42 的差距，可以作为"任务信号本身很关键"的证据。
2. 有了同样的信号，知识以什么形式交给 agent：文字建议（B）、写在 prompt 里的 SQL（C）、库里的对象（D）。这才是
   本研究论点真正要比较的地方。

需要主动交代的一点：B、C、D 的知识都来自 gold，view 方法本身同样依赖 ground truth（失败需要 gold 才能判定）。现在的
实验回答的是"知识正确时，哪种形式最好用"。真实场景是从训练题的失败中自动产生知识、再用到测试题上，这需要后续的
train/test 实验来验证。

可选的补充：加一组"静态分析生成的连接说明"作为下界，只列出这些表之间所有结构上成立的连接候选，不标明哪条正确。
预期它远低于 B 组，可以说明分数差距来自任务信号，而不是"给了连接信息"本身。这一组暂不做，先完成 dept_views 的
A、B、C 三组。

### 5.9 设计方案：产物（F）、过滤语义（W）与粒度转换

本节是 dept_views 四组跑完之后的讨论结论，尚未实现。数字都来自本轮实测；设计本身是推断，需要后续实验验证。

**适用范围。** 本设计面向任意数据库中的任意产物，不针对院系或课程。设计只依赖几个通用概念：产物（一个 view）、
粒度（一行代表什么，由唯一键确定）、粒度之间的汇总关系、每一列所属的粒度、产物上的条件。文中出现的三表 view、
`offering`、`program`、`department`、`DEPARTMENT_NAME` 等名称和取值，都只是用 dept_views 的数据举的例子，
不是设计的一部分。

**动机。** D 组在 20 题 × 3 个 seed 上宽松 EX 只有 7/60，低于 A 组的 12/60。逐条看错题后发现，问题几乎都不在
"用哪个 view"，而在拿到 view 之后：

- 三表 view `av_dept_tip_offering_course` 的一行是"一条 TIP 开课记录 × 本系的一个学位项目行"。SCD 的行是各层级
  的学位项目，不是课程（`av_catalog` 和 B、C 组提示里写成"course description"是错的）。每条开课会重复 k 次，k 是
  本系的项目行数。例如数学系有 354 条开课、6 个研究生项目行，`COURSE_LEVEL = 'G'` 筛选后是 2,124 行。
- 在这个 view 上，`COURSE_LEVEL = 'G'` 的实际效果是"只保留有研究生项目的院系"，而 agent 多把"graduate-level"理解
  成"这门课是研究生课"：11 道三表题的 33 次运行里，13 次改用 SOS 的 `HGN_CODE`，9 次用了 `GRADUATE_LEVEL`。
- Biological Engineering 在 SD 里有 `20` 和 `BE` 两个代码。dw_5452 中 D 组按代码分组，拆成 143 和 72 两行，72
  那行被 `> 100` 过滤掉；gold 按 `DEPARTMENT_NAME` 分组，得到 215。

这些错误说明，只把连接做好（产物）还不够，还要告诉 agent 每一列、每个条件在这个产物上是什么意思，以及怎样换算到
题目要的粒度。

**框架。** 按 SQL 的执行顺序 FROM、WHERE、GROUP BY、HAVING、ORDER BY、SELECT（简称 FWGHOS）拆开：

- F（FROM）是产物，即高频出现的连接结构；
- W（WHERE）是产物上的过滤条件；
- G（GROUP BY）是粒度转换；
- H（HAVING）是转换后的产物上的过滤条件；
- O 和 S 相对简单，暂不特殊处理。

**F：高频公共产物，物化成 view。** 每个 F 记录：

- 定义 SQL 和源表；
- 粒度：一行代表什么、唯一键是什么。例如三表 view 的唯一键是 `TIP_SUBJECT_OFFERED_KEY` 加 `SIS_COURSE_DESCRIPTION_KEY`；
- 每一列的语义：属于哪个实体和粒度、含义、取值范围，以及容易混淆的地方（例如 `SCD_IS_DEGREE_GRANTING` 是项目的
  属性，`IS_DEGREE_GRANTING` 是院系的属性，两者有 230 行不同）；
- 行数放大：每个实体在这个 F 里重复了多少次，最好附上分布，并用数据核实。

**W：F 上的过滤定义。** W 和列的语义是两样东西。列的语义回答"这一列是什么"；W 回答"题目里的某个说法对应什么条件，
这个条件在这个 F 上的实际效果是什么"。

- W 以定义的形式存储，而不是每个取值建一个 view。`COURSE_LEVEL = 'G'` 和 `COURSE_LEVEL = 'U'` 是同一条带参数的
  定义 `COURSE_LEVEL = :level`。
- 每条定义绑定到一个 F，并标明它属于哪个粒度。同一个谓词在不同的 F 上效果可能不同：`COURSE_LEVEL = 'G'` 在 SCD 上
  是筛选项目，在三表 view 上是筛选院系。
- 从 SQL 中按原子谓词挖掘；只有在多道题里一起出现、并对应题目里同一个说法的组合，才额外存成组合定义。例如 dw_1658
  的"degree-granting courses"对应 `SCD_IS_DEGREE_GRANTING = 'Y' AND IS_DEGREE_GRANTING = 'Y'`。

**什么时候物化，什么时候只存定义。** 判断标准是：正确的写法能不能只在产物上加一个表达式（WHERE 或 SELECT 里的一个
表达式）就完成，不改 FROM、不加去重、不改分组。能，就只存定义；不能，说明需要额外的结构，此时有两种做法：一是把结构
物化；二是把完整写法（如先去重的子查询）存进定义，并在注意事项里写明"不能直接加 WHERE"。前者让错误写法写不出来，
后者依赖 agent 读到并照抄。结构在很多题里反复出现、照抄仍然容易错时，才值得物化。讨论中原本列了去重、跨粒度筛选、
统一实体标识（例子是院系）三种需要结构的情况，后来发现三者都是粒度问题，可以由下面的粒度转换记录解决，不必物化。

**粒度转换：粒度图。** 每个 F 记录一张粒度图：节点是这个 view 能转换到的粒度，边是两个粒度之间怎么转换。对任意 F，
粒度图按下面的方法得到：

- 节点：
  - F 本身的粒度，唯一键通常是各源表主键的组合，需要用数据确认唯一；
  - 每张源表对应一个粒度，唯一键是该表的主键（或实测唯一的列）；
  - 连接键指向的、F 中只出现了标识列和属性列的实体，也各对应一个粒度。
- 粒度名按实体命名，F 本身的组合粒度用各实体名连接（如示例中的 `offering_program`）。
- 边：如果粒度 A 的唯一键能唯一确定粒度 B 的唯一键（A 对 B 是多对一），就有一条从 A 到 B 的边。这个关系可以从连接
  条件加上被连接一侧的唯一性推出，也可以用数据检验：在 A 的每个分组里，B 的唯一键只有一个取值。只保留直接的边，
  能经由中间粒度到达的不另加边。
- 一般得到的是有向无环图，不一定是树：只要一个粗粒度能从两个不同的细粒度汇总得到，就不是树。只有单链连接的 F，
  粒度图才退化成一条链。

以三表 view 为例，粒度图是一个菱形：

```text
            offering_program（开课 × 项目，view 本身的粒度）
              /                    \
        offering（开课）        program（项目）
              \                    /
              department（院系，键为 DEPARTMENT_NAME）
```

在这个例子里，`department` 有 `offering` 和 `program` 两个来源，树表达不了。两条路径的区别有实际意义：属于
`offering` 的度量（如 `NUM_ENROLLED_STUDENTS`）要走左边，属于 `program` 的度量要走右边；两种度量都要时，各走一条
路径，到 `department` 后再按它的唯一键连接。一般地，度量属于哪个粒度，就从那个粒度出发沿边汇总。

- 节点记录粒度的含义（一行代表什么）和唯一键。同一个实体有多种标识时（例如院系既有代码又有名称，而 Biological
  Engineering 有 `20` 和 `BE` 两个代码），节点上写明应该用哪一个作为唯一键。这是一条知识，直接写在节点上。
- 目前只考虑 `roll_up` 边，即从细到粗的汇总；把粗粒度的结果连接回细粒度的情况暂不考虑。转换的 SQL 模板挂在边上，
  因为同一个粒度可以从不同来源转过来，写法不同。
- `roll_up` 不只是 GROUP BY，有三种写法，适用条件不同：
  1. `GROUP BY` 目标粒度的唯一键：通用写法。可以直接保留的列照常输出，必须聚合的列用聚合函数。例如三表 view
     转到 `offering` 时，用 `MAX(COURSE_LEVEL = 'G')` 判断本系有没有研究生项目。
  2. `SELECT DISTINCT` 唯一键加上可以直接保留的列：只在不需要聚合任何列时可用，结果和第 1 种相同。`DISTINCT` 的
     列表里必须包含唯一键，否则两个不同的实体恰好取值相同时（例如两条同名、同人数的开课）会被合并成一行，和
     `SUM(DISTINCT ...)` 的错误是同一个原因。
  3. `COUNT(DISTINCT 唯一键)`：把"转到目标粒度"和"计数"合在一步，只能用来计数，不能用来求和或求平均。
- 哪些列可以直接保留、哪些必须聚合，可以从图推出来：转到某个粒度后，这个粒度本身以及沿 `roll_up` 边向上能到达的
  粒度，它们的列都可以保留（组内只有一个取值），其余的列必须聚合。所以不单独存储这两个列表。推断结果可以用数据检验：
  在目标粒度的每个分组里，用 `COUNT(DISTINCT 列)` 检查这一列是否只有一个取值（含 NULL 的列要单独处理）。数据检验只能
  证明现有数据里成立，所以以图的推断为准，两者冲突时写进 `notes`。以三表 view 为例，推出来的结果是：

| 粒度 | 唯一键 | 可以直接保留的列 | 必须聚合的列 |
|---|---|---|---|
| `offering_program` | `TIP_SUBJECT_OFFERED_KEY`、`SIS_COURSE_DESCRIPTION_KEY` | 全部 | 无 |
| `offering` | `TIP_SUBJECT_OFFERED_KEY` | 开课的列、院系的列 | 项目的列 |
| `program` | `SIS_COURSE_DESCRIPTION_KEY` | 项目的列、院系的列 | 开课的列 |
| `department` | `DEPARTMENT_NAME` | 院系的列 | 开课和项目的列，且要先经过各自的粒度 |

- 聚合后的业务含义推断不出来，例如 `MAX(COURSE_LEVEL = 'G')` 在开课粒度上表示"本系有研究生项目"。这类含义放进
  `av_semantics`，不放在粒度图里。粒度图只存可以推断和验证的结构信息，`av_semantics` 存需要挖掘或人工编写的业务语义。
- 度量规则写成通用说明：度量只能在它自己粒度的行上聚合（每个实体只算一次），所以要先沿边转到那个粒度；到了之后，
  可以直接按任何沿边能到达的更粗粒度的唯一键分组，不必逐级汇总。逐级汇总得到的是另一个统计量，例如"各院系平均值的
  平均"不等于"全部开课的平均"。COUNT、SUM 对重复敏感；MAX、MIN、方差、COUNT DISTINCT 不敏感。（最初写的是"沿边
  逐步汇总、不能跳步"，在 join3 上手工构造产物时发现它会把按学院直接统计开课的写法判为错误，已改。）

有了这些记录，去重、跨粒度筛选、统一标识三类问题可以用同一种写法解决：先沿边转到度量所属的粒度，在那里把其他粒度
的条件聚合成一列，再继续汇总。以三表 view 为例，"有研究生项目的院系中，每个院系的开课数和选课总人数"：

```sql
WITH offering AS (                         -- 开课粒度
    SELECT TIP_SUBJECT_OFFERED_KEY,
           MAX(DEPARTMENT_NAME)        AS DEPARTMENT_NAME,        -- 院系的列，组内唯一
           MAX(NUM_ENROLLED_STUDENTS)  AS NUM_ENROLLED_STUDENTS,  -- 开课的列，组内唯一
           MAX(COURSE_LEVEL = 'G')     AS DEPT_HAS_GRAD_PROGRAM   -- 项目的列，必须聚合
    FROM av_dept_tip_offering_course
    GROUP BY TIP_SUBJECT_OFFERED_KEY
)
SELECT DEPARTMENT_NAME, COUNT(*), SUM(NUM_ENROLLED_STUDENTS)   -- 院系粒度
FROM offering
WHERE DEPT_HAS_GRAD_PROGRAM = 1
GROUP BY DEPARTMENT_NAME;
```

一条开课对应的 k 行正好是本系的全部项目，所以 `MAX(COURSE_LEVEL = 'G')` 在开课粒度上的含义就是"本系有研究生项目"。
这段 SQL 是示意，没有在库里执行过。

**递归：G 和 H。**

- G 就是粒度图上的 `roll_up` 边，不另存一套。
- G 的输出是一个新的 F，按同样的格式记录粒度、唯一键和列的语义。新 F 多了度量列，每个度量要记录：聚合了哪一列、
  在哪个粒度上聚合、对重复是否敏感。
- H 是新 F 上的 W，例如 `HAVING SUM(NUM_ENROLLED_STUDENTS) > 100` 是院系粒度上的一条过滤定义。
- 多个聚合结果按共同的粒度键连接起来，也构成新的 F。
- 新 F 同样按"高频才物化"处理：高频的聚合产物存成 view，其余只存转换定义，由 agent 在查询里现场计算。聚合粒度
  （如示例中的院系粒度）的 view 必须事先决定装哪些度量，而题目要的度量很难预见，所以多数情况下存定义更合适。

成熟的语义层也是这样处理行数放大的：dbt MetricFlow 和 Cube 给每个实体定义主键，度量归属于实体，引擎先在度量所属的
实体粒度上聚合再连接；Looker 的 symmetric aggregates 专门处理重复计数。这里的区别是把引擎做的事写成说明和模板交给
agent。

**存储方式。** 和 view 一起存在库里，让 agent 读 view 时一并读到，prompt 不随知识量变长。一共四张表，都用
`object_name` 指明适用的 view，agent 按 view 名各查一次就能读全。表结构和字段对任意 view 都相同；下面字段说明里的
示例值都取自三表 view `av_dept_tip_offering_course`，只用于说明。

几条共同约定：

- 每个 view 的粒度名只在 `av_grain` 里定义一次，写明一行代表什么和唯一键；其他表里凡是填粒度的字段，都只填这些
  名称，作为引用。单凭一个词不足以说明含义，例如三表 view 里 SCD 的一行是"一个学位项目在一个层级上的记录"，只写
  `program` 容易被理解成课程。
- 实体和粒度共用同一套名称：每个实体对应以它的主键为唯一键的粒度，"描述某个实体的属性"等价于"在该实体的粒度上
  取值唯一"。因此不再单独设 entity 字段。
- 字段名尽量自解释（如 `applies_at_grain`、`describes_grain`），同时在 prompt 里给出一段固定长度的字段说明。这段说明
  只随字段数量变化，不随知识量增长。
- 聚合到粗粒度的 H，即使那个粒度没有物化成 view，`object_name` 仍然填原来的 view 名，用 `applies_at_grain` 区分。

`av_catalog`：F 本身的说明，每个 view 一行，记录"这个 view 是什么"。列的说明不放在这里，放在 `av_semantics`。
（第一轮的 `av_catalog` 把 view 和列混在一张表里，用 `column_name = '*'` 区分，因为当时还没有 `av_semantics`。）

- `object_name`：view 名，如 `av_dept_tip_offering_course`，是主键。
- `grain`：view 本身的行属于哪个粒度，填 `av_grain` 里定义的粒度名，也是粒度图的起点。例如三表 view 是
  `offering_program`。
- `description`：一行代表什么、连接条件，以及每个实体重复了多少次。例如"每条开课重复 k 次，k 是本系的项目行数；
  数学系 k = 12"。

`av_semantics`：F 上每一列的语义，以及 W 和 H 的定义，记录"view 的某一列或题目里的某个说法在这个 view 上是什么、
怎么写、实际效果是什么"。列、原子谓词、组合谓词和 H 放在同一张表里，避免 agent 多查一张表、多猜一次列名；条件的
`describes_grain` 也要从它用到的列推出来，放在一起便于检验。

- `object_name`：适用的 view。同一个谓词在不同 view 上要各写一行，因为效果可能不同。
- `kind`：定义的类型。`column` 是 view 的一列，每列一行；`filter` 是原子谓词，`filter_combo` 是组合谓词；以后可以
  扩展 `dimension`（分组用的表达式）和 `measure`（度量）。
- `name`：`column` 行填列名；条件填定义名，供 `built_from` 引用，例如 `dept_has_grad_program`。在同一个 view 内唯一，
  而且不区分大小写也要唯一，因为表的排序规则不区分大小写（三表 view 里过滤条件曾叫 `department`，和列 `DEPARTMENT`
  主键冲突，已改名为 `in_department`）。
- `column` 行的其他字段：`applies_at_grain` 填 view 本身的粒度；`describes_grain` 填这一列在哪个粒度上取值唯一；
  `sql_expression` 就是列名；`meaning` 写来源表、含义和取值范围；`caveat` 写容易混淆的地方，例如"`OFFER_DEPT_NAME`
  每行都等于 `DEPARTMENT_NAME`"或"`GRADUATE_LEVEL` 在本 view 的 27 个项目行上全为 NULL"。下面各字段的说明针对条件。
- `applies_at_grain`：表达式在哪个粒度上使用，填粒度名。W 一般是 view 本身的粒度或某个转换后的粒度；H 是聚合后的
  粒度，例如 `department`。agent 要先沿粒度图转到这个粒度，再套用表达式。
- `describes_grain`：条件描述的是哪个粒度上的属性，填粒度名。例如 `COURSE_LEVEL = 'G'` 描述的是 `program`。它比
  `applies_at_grain` 更细、即从 `applies_at_grain` 沿边走不到时，才是跨粒度的情况，`sql_expression` 必须给出聚合后的
  写法；它更粗时（例如在开课行上按院系名筛选）直接使用即可。这个字段可以从表达式用到的列
  的 `column` 行里的 `describes_grain` 推出来；为了方便 agent 阅读仍冗余存储，并用推断结果检验。
- `sql_expression`：用 view 的列名书写的表达式，可以带参数，参数用 `:name` 表示。例如原子谓词
  `COURSE_LEVEL = :level`；在 `offering` 粒度上判断院系是否有研究生项目，写作 `MAX(COURSE_LEVEL = 'G') = 1`；H 写作
  `SUM(NUM_ENROLLED_STUDENTS) > :n`。
- `parameters`：参数的取值范围和含义。例如 `:level` 取 `G`（研究生）或 `U`（本科）。没有参数时为空。
- `meaning`：业务含义和题目里对应的说法。例如"院系至少有一个研究生层级的学位项目；题目中的 graduate-level 在 gold
  里多指这个"。
- `caveat`：使用时的注意事项，尤其是这个条件在这个 view 上的实际效果和常见误用。例如"在原始粒度上直接写
  `COURSE_LEVEL = 'G'`，效果是筛选院系，不是筛选研究生课；判断课程本身是否为研究生课，要用 SOS 的 `HGN_CODE`"。
- `built_from`：只用于组合谓词，列出它由哪些原子谓词的 `name` 组成。例如 dw_1658 的"degree-granting courses"写作
  `program_degree_granting, dept_degree_granting`，原子谓词这一列为空。

`av_grain`：粒度图的节点，记录"这个 view 有哪些粒度、每个粒度是什么"。每个"view × 粒度"一行，view 本身的粒度也
占一行。例如三表 view 有 4 行。

- `object_name`：view 名。
- `grain`：粒度名，是其他表引用粒度时使用的名称，如 `offering`。
- `row_meaning`：用完整句子说明这个粒度的一行代表什么。例如 `program`："一行是 `SIS_COURSE_DESCRIPTION` 的一行，
  即一个学位项目在一个层级上的记录，不是一门课"；`offering_program`："一条 TIP 开课记录和本系一个学位项目行的组合，
  每条开课重复 k 次，k 是本系的项目行数"。
- `key_columns`：这个粒度的唯一键。同一实体有多种标识时，填应该使用的那一个。例如三表 view 的 `offering` 是
  `TIP_SUBJECT_OFFERED_KEY`，`department` 是 `DEPARTMENT_NAME`（不用 `DEPARTMENT_CODE`，因为 Biological
  Engineering 有 `20` 和 `BE` 两个代码）。
- `notes`：其他注意事项。

`av_grain_edge`：粒度图的边，记录"怎样从一个粒度汇总到更粗的粒度"。每条边一行，目前都是 `roll_up` 边，所以不设
边类型字段。例如三表 view 有 4 条边：`offering_program` 到 `offering`、`offering_program` 到 `program`、`offering` 到
`department`、`program` 到 `department`。

- `object_name`：view 名。
- `from_grain`、`to_grain`：起点和终点的粒度名。
- `group_by_template`：用 GROUP BY 完成这一步的 SQL 模板，按 `to_grain` 的唯一键分组，必须聚合的列写出聚合函数。
  例如 `offering_program` 到 `offering` 这条边，就是上面示例里那段 `WITH offering AS (...)`。
- `distinct_template`：用 `SELECT DISTINCT` 完成这一步的 SQL 模板，只列唯一键和可以直接保留的列。例如
  `offering_program` 到 `offering`：`SELECT DISTINCT TIP_SUBJECT_OFFERED_KEY, <开课的列>, <院系的列> FROM ...`。
  只在不需要聚合任何列时使用。
- `notes`：这一步要注意什么。例如"`program` 的列在这一步必须聚合，不能出现在 `distinct_template` 里；常用聚合的
  含义见 `av_semantics`"。

四张表的分工是：`av_catalog` 说明产物，`av_semantics` 说明列和条件，`av_grain` 和 `av_grain_edge` 说明粒度和转换。
如果某个聚合产物足够高频、被物化成新 view，它同样在这四张表里各有自己的行。

以后 view 多了，同一个粒度（如示例中的 `offering`）会出现在多个 view 里，含义和唯一键相同。届时可以把节点的定义做成全局的，
每个 view 只记录自己包含哪些节点和边。第一版只有三个 view，先按 view 分别存。

prompt 要明确告诉 agent 这些表很重要，用 view 之前必须读完相关的所有行，并直接给出完整查询，避免猜列名（第一轮 D 组
平均每题 SQL 报错 0.86 次，本轮 0.92 次，主要是猜错 `av_catalog` 的列名）。prompt 里还要给出每个字段的说明和使用
粒度图的通用规则。草稿：

```text
# Agent views
This database has pre-joined views whose names start with `av_`. Before you use any view, you MUST read its full
documentation, which explains what one row means, what each column describes, and how to filter, group and
aggregate on it correctly. Using a view without reading this often gives wrong answers. Run exactly:
  SELECT * FROM av_catalog    WHERE object_name = '<view name>';
  SELECT * FROM av_semantics  WHERE object_name = '<view name>';
  SELECT * FROM av_grain      WHERE object_name = '<view name>';
  SELECT * FROM av_grain_edge WHERE object_name = '<view name>';
Read every row before writing your query, and follow the caveats.

A grain is a level of detail: what one row means. Grain names are defined in av_grain and used everywhere else.

av_grain (one row per grain of a view)
- grain: the grain name.
- row_meaning: what one row at this grain represents. Read it; the name alone can mislead.
- key_columns: the columns that identify one row at this grain.
- notes: other caveats.

av_grain_edge (one row per step from a finer grain to a coarser grain)
- from_grain, to_grain: start and end grain.
- group_by_template: SQL for this step using GROUP BY to_grain's key_columns; columns that must be
  aggregated are wrapped in aggregate functions.
- distinct_template: SQL for this step using SELECT DISTINCT; use it only when no column needs aggregating.
- notes: what must be aggregated in this step, and other caveats.

av_catalog (one row per view)
- grain: the grain of the view's own rows.
- description: what the view joins, what one row means, and how often rows repeat.

av_semantics (one row per column or condition of a view)
- kind: column (one column of the view), filter (a single condition) or filter_combo (several conditions
  used together).
- name: the column name, or an identifier of the condition.
- applies_at_grain: the grain your query must be at when you apply sql_expression.
- describes_grain: for a column, the grain at which it has one value per row (its own grain); for a
  condition, the grain whose attribute it tests. If it is finer than applies_at_grain (not reachable from
  it through av_grain_edge), the condition crosses grains: use sql_expression exactly as given.
- sql_expression, parameters: the column itself, or the SQL to use; :name marks a parameter, explained in
  parameters.
- meaning: what the column or condition means and which phrases in a question it corresponds to.
- caveat: its effect on this view and common mistakes.
- built_from: for a filter_combo, the names of the filters it combines.

Rules for grains:
- Aggregate a column only on rows at its own grain (its describes_grain), where each row counts once: first
  move to that grain along the edges in av_grain_edge. From there you can group by the key_columns of any
  grain reachable through the edges; COUNT and SUM are wrong on duplicated rows.
- A step can be GROUP BY the target key_columns, or SELECT DISTINCT when no column needs aggregating. A
  SELECT DISTINCT must include the target key_columns, otherwise different rows with equal values merge.
  COUNT(DISTINCT key_columns) both moves to the target grain and counts; use it only for counting.
- If you need measures from different grains, roll each up to the same grain separately, then join on that
  grain's key_columns.
```

是否真的读了，可以从运行记录里检查这几条查询，作为引导是否生效的诊断指标。每条定义都应能用数据检验：表达式能在对应
的 view 上执行，注意事项里写的事实（如"每条开课重复 k 次"）能用查询核实。这可以作为生成定义时的测试。

**gold 的可信度。** 原则仍是"先相信 gold"，但前提是 gold 能解释得通。

- 能解释的例子：方差类题目在三表 view 上加 `COURSE_LEVEL = 'G'`，效果是只保留有研究生项目的院系；方差不受均匀
  重复的影响，数学系的 gold 方差 4675.8732 等于 354 条开课的普通方差。
- 解释不通的例子：dw_5526 要求列出数学系 2019FA 有教材的每门课。gold 连接了 SCD，但 SCD 既不参与筛选也不参与输出，
  结果 48 行只有 4 条不同的开课，每条重复 12 次（数学系在 SCD 中的项目行数）。这些重复行没有任何含义。评测器
  （`evaluate.py` 的 `_sequences_match`）要求行数相等，四组 12 次运行全部判错，其中 6 次是 4 列 × 4 行、去重后和
  gold 完全一致（基线 s2、B 组 s2、C 组 s1–s3、D 组 s1）。
- 处理口径待定：把 dw_5526 标为 gold 有缺陷并单独报告，或者对不要求顺序的列表题按去重后的集合比较（会改变所有题的
  评测口径，需要重评全部运行）。其余在三表 view 上做 COUNT、SUM 的 gold 题是否属于同类，还没有逐题检查。
- 这会影响粒度转换的评测：按粒度规则正确去重的答案，在 gold 带重复的题上会被判错。

**这套设计解决不了的事。**

1. 题目说法对应哪个谓词，例如"graduate-level"是"本系有研究生项目"还是"这门课是研究生课"。粒度记录只保证每种
   含义都能写对，选哪种要靠 W 的 `meaning` 写清楚。D 组三表题的错误主要出在这一步。
2. 泄漏：W 和粒度转换比 F 更贴近具体题目，必须只从训练题挖，并把可复用的语义和题目常量分开（例如"Biology 对应
   代码 7"是题目常量）。

**和已有语义层的区别。** 以下对比依据的是对各产品公开设计的了解，没有逐项查阅文档核实，写进论文前需要对照官方文档。
参照对象有两类：面向 BI 的 dbt MetricFlow、Cube、LookML，以及面向 LLM 生成 SQL 的 Snowflake Cortex Analyst 语义
模型、Databricks Genie 的指令和可信资产。它们的共同结构是：带主键的逻辑表或实体、实体之间的关系（连接条件和关系
类型）、维度、度量（一列加一种聚合方式）、由度量组成的指标；面向 LLM 的产品还有命名过滤条件、同义词和经过验证的
示例查询。

| 本设计 | 语义层中的对应 | 差别 |
|---|---|---|
| F：物化的高频产物 | 逻辑表和实体关系 | 语义层的连接通常由引擎在查询时生成，不物化 |
| 列的语义和所属粒度 | 维度、实体主键 | 基本相同 |
| W：带参数的过滤定义 | Cortex Analyst 的命名过滤条件、同义词 | 本设计额外记录条件在这个产物上的实际效果 |
| 粒度转换 | 引擎根据主键和关系自动推导 | 本设计要写成说明和模板交给 agent |
| 度量先回到所属粒度再聚合 | MetricFlow 的度量归属实体、Looker 的 symmetric aggregates | 规则相同，执行者不同 |

本质区别有四点：

1. 谁来执行规则。语义层里，调用方只选指标和维度，由引擎编译 SQL，行数放大和粒度转换由引擎保证正确，代价是表达
   能力受限（方差、窗口函数、多层嵌套未必支持）。本设计中 agent 自己写任意 SQL，规则只能作为说明交给它，靠它读懂
   照做，所以要把引擎内部的逻辑写出来，也要在 prompt 里强调必须读完。
2. 知识从哪里来。语义层由数据工程师事先人工建模，追求覆盖整个模型。本设计从 SQL 日志按频率挖掘、再由失败驱动补充，
   只为高频产物写记录，注意事项来自 agent 实际犯过的错（例如"graduate-level"被理解成课程层级）。
3. 怎样对待放大行数的连接。规范的语义层在建模时避免这类连接：据了解，MetricFlow 只允许不会放大行数的连接路径，
   Cube 和 Looker 用主键在聚合时去重。三表 view 这种按院系两两组合的多对多结构，在语义层里通常不会成为基础实体。
   本设计保留它，因为它在 gold SQL 中高频出现，方差类题的 gold 也正是在它上面计算的；做法是标注粒度和放大情况，
   再配上转换规则。好处是贴近真实写法，代价是会遇到 dw_5526 这种 gold 本身不规范的情况。
4. 谓词的语义依赖所在的产物。语义层中过滤条件和维度的定义通常是全局的，挂在某个实体上。本设计发现同一个
   `COURSE_LEVEL = 'G'` 在 SCD 上是筛选项目、在三表 view 上是筛选院系，所以 W 绑定到具体的 F 并记录实际效果。
   语义层不允许这类多对多产物，因此也较少需要这样的字段。

不是新东西的部分：粒度和主键、度量归属、命名过滤条件和同义词、示例查询，在 MetricFlow、Looker、Cortex Analyst 中都
已存在。论文不宜把这些当作贡献，应说明借鉴关系。比较稳妥的定位是：已有语义层是人工建模、由引擎执行的知识；本研究
探讨能否从查询日志和失败中自动产生类似的知识（产物、过滤语义、粒度转换），并以库内对象的形式交给自己写 SQL 的
agent。由此可以加一个对比组：把同样的知识写成 Cortex Analyst 风格的语义模型 YAML 放进 prompt，和库内 `av_` 对象的
形式比较。

**下一步（待定）。** 先为三表 view 手写一版完整的 F、W 和粒度转换记录，修正 SCD 是项目而非课程的说明，在 dept_views
的 20 题上和现有 D 组对比，看错误能减少多少。之后再统计 98 题里 W 原子谓词和粒度转换的复用率，决定自动挖掘的方案。
（三表 view 的手写记录已完成，并在 join3 的 14 题上实测，见 5.10。）

### 5.10 第三轮：在三表 view 上验证 5.9 的设计（`view_semantics`）

**做了什么。** 按 5.9 的设计，为第一轮的三表 view `av_library_offering_course` 手工构造全部产物，在 join3 的 14 道题上
和第一轮的 A、B、C、D 四组对比。view 的定义和第一轮逐字相同，只换了说明的内容和形式。

- 建库脚本是 `db_agent_view/views/join3_semantics.sql`，删除脚本是 `drop_join3_semantics.sql`。四张表的内容：
  - `av_catalog`：1 行，说明 view 本身（连接条件、一行代表什么、每条开课重复几次）。
  - `av_semantics`：55 行。47 行 `kind = 'column'`，每列一行，写明所属粒度、含义和容易混淆的地方；7 条原子过滤条件和
    1 条组合条件。
  - `av_grain`：5 个粒度（`offering_program`、`offering`、`program`、`department`、`school`）。
  - `av_grain_edge`：5 条 `roll_up` 边，每条带 GROUP BY 和 DISTINCT 两种模板。
- 列的说明最初也放在 `av_catalog` 里（每组列一行，共 9 行），后来改为放进 `av_semantics`，让 `av_catalog` 只描述产物。
  改动时发现 `av_semantics` 的主键不区分大小写，过滤条件 `department` 和列 `DEPARTMENT` 冲突，过滤条件已改名为
  `in_department`，并加了回归测试。
- 提示是 `build_join_experiment.py` 里的 `view_semantics` 段（约 3,400 字符）：要求用 view 前必须执行四条给定的查询、
  给出四张表每个字段的含义和三条粒度规则，不含任何 view 的列名。上下文文件是
  `experiments/join3_course_number/view_semantics_contexts.jsonl`。测试是 `tests/test_join3_semantics.py`。
- 模型 gpt-5.1，thinking 档位 medium，每题 3 个 seed，评测数据同第一轮（`runs/join3_course_number/eval_data14`），
  结果目录是 `runs/join3_course_number/view_semantics_dk_medium`。42 次运行全部正常结束，没有运行环境失败。

**结果。**

| 组 | 每个 seed 的宽松 EX | 严格 EX | 宽松 EX |
|---|---|---|---|
| A 基线（domain knowledge） | 0、0、0 | 0/42 | 0/42 |
| B 文字连接建议 | 4、2、6 | 6/42 | 12/42 |
| C view 定义写成文字 | 7、6、4 | 8/42 | 17/42 |
| D view 和强提示 | 4、8、5 | 6/42 | 17/42 |
| E view 和四张说明表（本轮） | 9、8、8 | 12/42 | 25/42 |

| 组 | 执行命令次数中位数 | 平均每题 SQL 报错 | 用时中位数 |
|---|---|---|---|
| D | 8 | 0.86 | 106 秒 |
| E | 6 | 0.14 | 118 秒 |

- 3 次全对的题从 D 组的 4 道增加到 8 道。变化最大的是 dw_5466（选课总人数）：D 组因为重复行被重复计算，3 次都算成
  90,908；E 组 3 次都是正确的 45,454。dw_2946、dw_5615 从 1/3 升到 3/3，dw_5353 从 2/3 升到 3/3。
- 逐条看了 17 次错误的 SQL，没有一次是重复行被重复计算。42 次运行都先执行了四条读说明表的查询。
- SQL 报错从每题 0.86 次降到 0.14 次：提示直接给出完整查询，agent 不再猜说明表的列名。

**错题分析。** 17 次错误中 15 次集中在 5 道题，这 5 道题在五个组的任何一次运行里都没答对过；另 2 次来自 dw_426。
gpt-5.1 的运行记录里几乎没有推理文字，以下判断依据 agent 执行的 SQL 和输出。

| 题目 | 错误次数 | 原因 | 归类 |
|---|---|---|---|
| dw_124 | 3 | 方差 3 次都对。"total number of such courses"：gold 是 `COUNT(DISTINCT COURSE_NUMBER)`，每个院系都是 1；agent 数的是开课条数。按 MIT 的用法 course 指课程号（Course 18 即数学系），gold 说得通，但同一道题里"enrolled students in courses"又按开课算。 | 题目用词，gold 勉强说得通 |
| dw_249 | 3 | 院系、总人数、学院名 3 次都对。"the course with the highest enrollment"：gold 返回课程号（如 `18`），agent 返回 `SUBJECT_ID` 或课程标题；题目没有要求课程号，按课程号理解时这个问题没有意义。另有 1 次把人数跨学期求和，1 次因并列第一多出行。 | 题目有歧义，暂不处理 |
| dw_503 | 3 | 院系行都对。学院的"grand total for all departments"：gold 对各院系平均值再求平均和方差，agent 3 次都在开课行上直接按学院计算。`department` 到 `school` 边的 `notes` 已列出两种做法，但没说这种措辞对应哪一种。此外题目要求的格式是两个 null（6 列），gold 只有 5 列，照题目输出的 2 次即使口径对也会列数不符。 | 汇总口径和措辞的对应；题目格式与 gold 不一致 |
| dw_396 | 3 | 院系、总人数、分类 3 次都对；gold 多一列题目没要求的 `benchmark`，列数不符。 | gold 缺陷 |
| dw_5586 | 3 | agent 按开课去重后计算，得 1.91907；gold 在重复行上计算，得 1.91950。 | gold 缺陷（与粒度规则冲突） |
| dw_426 | 2 | "highest variance across all terms"：gold 按院系和学期算方差再取最大；错的 2 次分别算了全部学期合并的方差、按课程分组的方差。 | 题意有歧义 |

**结论和局限。**

- 在这条 path 上，四张说明表让宽松 EX 从 17/42 提高到 25/42，主要收益来自粒度：重复行不再被重复计算，授予学位的条件
  被正确地直接写在行级别。
- 剩下的错误基本不是粒度问题，而是"题目说法对应什么"：度量用词（dw_124）、汇总口径（dw_503）、题意歧义（dw_249、
  dw_426），以及 gold 本身的问题（dw_396、dw_5586）。去掉 dw_396 和 dw_5586 两道 gold 有缺陷的题，E 组是 25/36。
- 这些说明是看着这 14 道题的 gold 手写的，25/42 是已知答案条件下的上限，不能说明在新题上同样有效。要验证推广，需要
  用没有参与编写的题做对照。

**本轮暴露的设计问题（待处理）。**

1. 缺少度量和用词的定义，例如"number of courses""number of subjects offered"分别对应什么。`degree_granting_program`
   的 `meaning` 把 courses 和 subjects 并列，和 gold 的用法不一致。是否把"course 指课程号"写成通用规则，要先统计题库中
   这两个词在 gold 里的用法是否一致。
2. 粒度边只列出可选做法，没有说明哪种措辞对应哪种口径（dw_503）。
3. dw_249、dw_426 题意有歧义，dw_396、dw_5586 gold 有缺陷，是否在统计中单独列出待定。
4. 多个 view 时说明怎样存放，见 5.11。

**插曲：试跑时模型被换成了 glm-5.2。** 正式运行前先抽 3 题试跑，结果是 0/3，查运行记录发现模型是 glm-5.2。原因是为了
读 MySQL root 密码，在终端里执行了 `set -a; . ~/semantic-catalog/.env`，这个文件里的 `OPENCLAW_CUSTOM_MODEL_ID` 是
glm-5.2，覆盖了 `~/agent_view/.env` 里的 gpt-5.1。之后的运行命令都显式写 `--model gpt-5.1 --thinking medium`，读密码的
命令只在子 shell 里执行。那次试跑的结果不计入上表（目录 `runs/join3_course_number/view_semantics_probe3/seed0`）。

### 5.11 设计方案：多个 view 时怎样存放说明

5.10 只有一个 view，四张说明表都是全局的。像第二轮那样同时 materialize 多个 view（例如 dept_views 的 3 个）时，
需要决定说明放在哪里、agent 怎样找到。以下是讨论后确定的方案，已在 dept_views 上实现，见 5.12。

**每个 view 是一个独立单元。** 每个 view 单独建一组表，和 view 本身写在同一个建库脚本里，一个 view 一个 `.sql` 文件。
以两个 view `v1`、`v2` 为例（`<p>` 代表统一前缀）：

| 建库脚本 | 包含的对象 |
|---|---|
| `v1.sql` | view `<p>v1`，说明表 `<p>v1_semantics`、`<p>v1_grain`、`<p>v1_grain_edge` |
| `v2.sql` | view `<p>v2`，说明表 `<p>v2_semantics`、`<p>v2_grain`、`<p>v2_grain_edge` |
| 目录脚本 | `<p>catalog`、`<p>view_join` |

- 三张说明表的字段和 5.10 的 `av_semantics`、`av_grain`、`av_grain_edge` 相同，只是每个 view 各有一份，内容只描述
  这个 view。因为一张表只属于一个 view，5.10 里标明所属 view 的 `object_name` 列不再需要，主键相应去掉这一列。
- 每个 view 的脚本只删除和重建自己的对象，不能删除目录或其他 view 的表。现在的 `join3_semantics.sql` 开头会
  `DROP TABLE av_catalog`，改成多 view 时要去掉。
- 不另建记录表结构的 schema 文件，表结构就写在各自的建库脚本里。

**目录 `<p>catalog` 放在 view 的上一层。** 它不属于任何一个 view，作用是告诉 agent 库里有哪些 view、各自做什么、
适合什么问题，以及每个 view 的说明表叫什么。每个 view 一行：

| 字段 | 含义 |
|---|---|
| `object_name` | view 名，主键 |
| `grain` | view 的一行代表什么 |
| `description` | 包含什么数据、由哪些表连接而成 |
| `use_for` | 适合回答哪类问题，不适合哪类问题 |
| `semantics_table` | 列和条件说明表的表名 |
| `grain_table` | 粒度节点表的表名 |
| `grain_edge_table` | 粒度上卷边表的表名 |

**组合多个 view 的知识放在全局的 `<p>view_join`。** 它记录两个 view 在什么粒度上、用什么条件连接，全局只有一份。
字段是 `left_object`、`right_object`、`grain`、`join_condition`、`notes`，主键是 (`left_object`, `right_object`,
`grain`)，两个 view 名按字母顺序放，避免同一对 view 记两次。只有一个 view 的问题不需要读这张表。

**agent 读的是库里的表，不是 `.sql` 文件。** 建库脚本事先在宿主机上执行，agent 所在的容器里只有 `task.json`、
`context.md`、`prompt.md` 三个文件（读 `run_agent.py` 得出），此外只能查询 MySQL。所以 agent 是通过 SQL 读目录和
说明表的，目录里必须写明每张说明表的表名。agent 的流程是：

1. 执行 `SELECT * FROM <p>catalog;`，根据 `description` 和 `use_for` 选择要用的 view。
2. 对每个选中的 view，按目录里的表名执行 `SELECT * FROM` 读完三张说明表的全部行。
3. 如果要组合多个 view，再读 `<p>view_join`。
4. 按读到的说明写查询。

**提示要写清楚的内容。**

- 上面四步的完整查询，表名用占位符，说明要照抄目录里的表名。5.10 的实测表明给出完整查询有效：42 次运行都先读了
  说明表，SQL 报错从每题 0.86 次降到 0.14 次。
- 目录、三张说明表和 `<p>view_join` 每个字段的含义，以及三条粒度规则，写法沿用 5.10。
- 强调用某个 view 之前必须仔细读完它的三张说明表，这对理解这个 view 非常重要，不读常常会答错。

**提示全文（草稿）。** 以 5.10 实际运行的 `view_semantics` 提示（`build_join_experiment.py`）为底稿改写，前缀按
`av_` 写。提示里不出现任何具体 view 的名字或列名，同一段提示可以用于任意一组 view，换 view 时只需改库里的表。

```text
# Agent views
This database also has pre-joined views and their documentation, in tables whose names start with
`av_`. Start every question by reading the catalog of views:
  SELECT * FROM av_catalog;
Use description and use_for to choose the view or views that fit the question. If no view fits,
use the base tables.

Before you use a view, you MUST read all rows of its three documentation tables. They explain what
one row means, what each column describes, and how to filter, group and aggregate on the view
correctly. This is essential for understanding the view; using a view without reading them often
gives wrong answers. For each view you choose, run exactly these queries, copying the three table
names from that view's row in av_catalog:
  SELECT * FROM <semantics_table>;
  SELECT * FROM <grain_table>;
  SELECT * FROM <grain_edge_table>;
If you combine two or more views in one query, also run:
  SELECT * FROM av_view_join;
Read every row before writing your query, and follow the caveats.

A grain is a level of detail: what one row means. Each view's grain table defines the grain names
used in that view's other documentation tables. Different views use the same grain name for the
same level of detail.

av_catalog (one row per view)
- object_name: the view name.
- grain: the grain of the view's own rows.
- description: what the view joins, what one row means, and how often rows repeat.
- use_for: which questions the view suits, and which it does not.
- semantics_table, grain_table, grain_edge_table: names of the view's three documentation tables.

Grain table (one row per grain of the view)
- grain: the grain name.
- row_meaning: what one row at this grain represents. Read it; the name alone can mislead.
- key_columns: the columns that identify one row at this grain.
- notes: other caveats.

Grain edge table (one row per step from a finer grain to a coarser grain)
- from_grain, to_grain: start and end grain.
- group_by_template: SQL for this step using GROUP BY to_grain's key_columns; columns that must be
  aggregated are wrapped in aggregate functions.
- distinct_template: SQL for this step using SELECT DISTINCT; use it only when no column needs
  aggregating.
- notes: what must be aggregated in this step, and other caveats.

Semantics table (one row per column or condition of the view)
- kind: column (one column of the view), filter (a single condition) or filter_combo (several
  conditions used together).
- name: the column name, or an identifier of the condition.
- applies_at_grain: the grain your query must be at when you apply sql_expression.
- describes_grain: for a column, the grain at which it has one value per row (its own grain); for a
  condition, the grain whose attribute it tests. If it is finer than applies_at_grain (not reachable
  from it through the grain edges), the condition crosses grains: use sql_expression exactly as given.
- sql_expression, parameters: the column itself, or the SQL to use; :name marks a parameter,
  explained in parameters.
- meaning: what the column or condition means and which phrases in a question it corresponds to.
- caveat: its effect on this view and common mistakes.
- built_from: for a filter_combo, the names of the filters it combines.

av_view_join (one row per pair of views and the grain at which they can be joined)
- left_object, right_object: the two views, in alphabetical order.
- grain: the grain both sides must be at before joining.
- join_condition: the join condition between the two sides once both are at that grain, written with
  the view names as qualifiers.
- notes: how the views differ at this grain (for example rows present in only one view) and other
  caveats.

Rules for grains:
- Aggregate a column only on rows at its own grain (its describes_grain), where each row counts once:
  first move to that grain along the grain edges. From there you can group by the key_columns of any
  grain reachable through the edges; COUNT and SUM are wrong on duplicated rows.
- A step can be GROUP BY the target key_columns, or SELECT DISTINCT when no column needs aggregating.
  A SELECT DISTINCT must include the target key_columns, otherwise different rows with equal values
  merge. COUNT(DISTINCT key_columns) both moves to the target grain and counts; use it only for
  counting.
- If you need measures from different grains, roll each up to the same grain separately, then join
  on that grain's key_columns.
- To combine views, roll each view up to the grain given in av_view_join separately, then join the
  results with its join_condition. Never join the views' rows directly.
```

**和 5.10 提示相比改了哪些地方。**

- 去掉了“关于开课的问题优先用 `av_library_offering_course`”这句指定 view 的话。选哪个 view 改由目录的 `use_for`
  决定，所以第一步固定为读目录。同时加了“没有合适的 view 就用基础表”，因为多个 view 也不可能覆盖所有问题，
  5.10 没有这句话是因为它只在 join3 的 14 道题上运行。
- 读说明表的查询从 `WHERE object_name = '<view name>'` 改为 `SELECT * FROM <表名>`，表名从目录里照抄，因为每个
  view 有自己的说明表。
- “必须读完”这段沿用 5.10 的强措辞，并按讨论加了“This is essential for understanding the view”。
- 三张说明表不再写死表名，改称 grain table、grain edge table、semantics table，并去掉了 `object_name` 字段的说明。
- 新增 `av_catalog` 的 `use_for` 和三个表名字段、`av_view_join` 的全部字段，以及第四条粒度规则：组合 view 时各自先
  上卷到 `av_view_join` 给出的粒度，再按连接条件连接，不能直接连接两个 view 的行。这条规则和第三条（不同粒度的
  度量各自上卷再连接）是同一个道理，因为两个 view 的行直接连接会互相放大。
- 加了“不同 view 中同名粒度表示同一层级”，这需要建库时保证，对应下面测试的最后一条。

**这份草稿要验证的地方。**

- 篇幅：5.10 的提示是 3,485 字符，这份草稿是 4,606 字符（用脚本实测），再加上 agent 选中 k 个 view 要读 3k 张说明表，上下文会明显变长。
  需要实测是否会出现 agent 读一部分就开始写查询的情况，统计方法和 5.10 一样，看运行记录里是否执行了全部读表查询。
- `use_for` 是否足以让 agent 选对 view。可以在运行记录里统计 agent 选的 view 和 gold 用到的表是否一致。
- 第四条规则和 `av_view_join` 在 dept_views 中 8 道需要组合 view 的题上是否有效，和第二轮 D 组对比。

**命名。** 所有新对象（view、说明表、目录、`<p>view_join`）用统一的前缀，和库里已有的业务表区分开，不另建数据库。
前缀沿用 `av_`：2026-10-28 查 `information_schema.tables`，`db_agent_view` 共 15 个对象，以 `av_` 开头的 5 个都是 join3
实验建的，没有业务表用这个前缀。MySQL 表名最长 64 个字符，view 名加上
`_grain_edge` 后缀不能超长。

**实现时要加的测试。**

- 每个 view 的三张说明表字段完全一致，防止各脚本的表结构逐渐不同。
- 目录里列出的每个 view 和每张说明表在库里都存在；库里每个带前缀的 view 在目录里都有一行。
- 每个 view 的说明表只描述自己的列（列说明和 view 的列一一对应），粒度图里 view 的粒度可以上卷到所有其他粒度，
  沿用 5.10 的测试。
- `<p>view_join` 中出现的 view 都在目录里，两个 view 名按字母顺序。
- 多个 view 都有的粒度（例如 `department`），在各自 `grain` 表里的键要一致，否则无法按 `<p>view_join` 连接。

**代价。** n 个 view 共有 4n + 2 个对象；agent 选了 k 个 view 就要多执行 3k 条读说明表的查询，问题需要多个 view 时
读取的说明会明显变长。

### 5.12 第四轮：在 dept_views 上实现 5.11 的多 view 设计（`view_semantics`，已运行，结果见 5.13）

**做了什么。** 题目沿用第二轮的 20 题，三个 view 的定义和第二轮逐字相同，只换了说明的内容和形式：按 5.11 为每个 view
建一组说明表，再加目录 `av_catalog` 和全局的 `av_view_join`。

| 建库脚本 | view 本身的粒度 | 粒度 | 粒度边 | 列说明 | 条件 |
|---|---|---|---|---|---|
| `views/dept_semantics/av_dept_course.sql` | `program` | 4 | 3 | 31 | 6 |
| `views/dept_semantics/av_dept_offering_summary.sql` | `summary_offering` | 3 | 2 | 42 | 7 |
| `views/dept_semantics/av_dept_tip_offering_course.sql` | `tip_offering_program` | 6 | 6 | 52 | 9 |
| `views/dept_semantics/catalog.sql` | `av_catalog` 3 行，`av_view_join` 3 行 | | | | |

- 删除脚本是 `views/drop_dept_semantics.sql`，删掉 3 个 view 和 11 张表。
- 提示是 `build_join_experiment.py` 里 `EXPERIMENTS["dept_views"]["arm_notes"]["view_semantics"]`，和 5.11 的草稿逐字相同
  （4,606 字符，用脚本比对过）。上下文文件是 `experiments/dept_views/view_semantics_contexts.jsonl`，20 行。
- 测试是 `tests/test_dept_semantics.py`，37 个，覆盖 5.11 列出的各项检查，外加"三对组合 view 都在 `av_view_join` 里"
  和"提示不含任何 view 名和列名"。

**写说明时新发现的事实（都是实测）。**

1. `SIS_COURSE_DESCRIPTION` 的一行是一个学位项目，由课程号、方向和层级确定，例如 `6:3:U`。`COURSE` 是项目代码
   （如 `6 3`），共 630 个，不等于院系号；第一轮 join3 里两者相等，只是因为那次按课程号连接后只剩下 27 个不带方向的
   项目行。所以 `av_dept_course` 和三表 view 都多了一个 `course` 粒度，介于 `program` 和 `department` 之间。课程的个数
   写成 `COUNT(DISTINCT COURSE)`：dw_306、dw_4462、dw_5433 的 gold 都这样数，dw_1658 数的是项目行数，和前三题不一致。
2. 两张开课表分别命名为 `summary_offering`（`SUBJECT_OFFERED_SUMMARY` 的行）和 `tip_offering`（`TIP_SUBJECT_OFFERED`
   的行），没有都叫 `offering`。它们是不同表的记录，不能一一对应；5.11 要求同名粒度表示同一层级，如果共用一个名字，
   agent 可能会按开课把两个 view 连起来。`program`、`course`、`department`、`school` 在多个 view 里同名同键，由测试检查。
3. `DEPT_BUDGET_CODE` 和 `CIP_PROGRAM_CODE` 都是文本类型。63 个 CIP 代码只有 5 位（开头的 0 被去掉），所以 `MIN`、
   `MAX` 按文本比较时 `'90702'` 大于 `'540101'`；有 6 个院系按文本和按数值得到的最小值或最大值不同。gold 都是直接
   `MIN`、`MAX`，即按文本比较。说明里只写了这个事实，没有建议用哪一种。
4. `av_dept_course` 里没有不带项目的院系，例如工程学院的 CTS 和 SENG。所以在这个 view 上算工程院系的平均预算，和在
   `SIS_DEPARTMENT` 上算（106,304.12）不同。dw_334、dw_4462 的 gold 用的是 `SIS_DEPARTMENT`。按数据推算，两种平均值
   得到的分类结果相同：EECS 的 64,000 两种算法下都低于平均的 90%，高于平均的都只有预算为 405,100 的三个院系。
5. 三表 view 上，gold 是在重复行上直接算 `VARIANCE`、`STDDEV`、`AVG`、`MAX`、`MIN`。MySQL 的 `VARIANCE`、`STDDEV`
   是总体方差和总体标准差；只要同一院系内每条开课重复的次数相同，结果就和去重后一样。Biological Engineering 的两个
   代码各有 6 个研究生项目行，所以研究生类的题去重后和 gold 一致；本科项目行分别是 3 行和 2 行，dw_1658 里这个系的
   平均人数，gold 是 18.2319，去重后是 18.0059。
6. "graduate-level"写成两条条件：在 view 的行上用 `program_level`（`COURSE_LEVEL = :level`），先上卷再筛时用
   `department_has_program_level`（`MAX(COURSE_LEVEL = :level) = 1`），并注明它筛的是"有研究生项目的院系"，不是课程
   本身。`SUBJECT_OFFERED_SUMMARY` 的 `HGN_CODE` 的注意事项指向三表 view。目录的 `use_for` 写明了两张开课表的分工：
   涉及项目层级、课程资料、或者课程计数和开课一起算时用三表 view，只看开课本身时用 `av_dept_offering_summary`。这条
   分工是从 20 道题的 gold 里归纳出来的。

**怎么验证的。**

- `python3 -m pytest tests -q`：193 个全部通过，其中新增 37 个。新测试是先写的，在产物和提示都不存在时 37 个全部失败。
- 在临时库 `av_scratch_check` 里执行了 4 个脚本中建表和插入的语句（建 view 的语句除外，因为临时库里没有基础表），
  全部成功，各表行数和上表一致，之后已删掉这个临时库。
- 把三个 view 的定义当作同名 CTE，严格按说明表里的写法重写了 6 道题，在 `db_agent_view` 上只读执行并和 gold 比较：
  dw_5215、dw_5452、dw_306、dw_5433、dw_2417 的结果完全一致；dw_1628 少 3 行，原因见下表。
- 重新生成 `experiments/dept_views/` 后，原有的 5 个上下文和清单文件逐字节不变，`provenance.json` 多登记了新的一组。

**照说明做也会被判错的题（gold 的问题）。**

| 题目 | 原因 |
|---|---|
| dw_1658 | 本科统计在重复行上计算，Biological Engineering 两个代码重复次数不同（见上面第 5 条）；"degree-granting courses"数的是项目行数，和其他题的课程计数口径不同。 |
| dw_1628 | gold 按 `DEPARTMENT_NAME` 和 `DEPARTMENT_FULL_NAME` 分组，把 Biological Engineering 拆成两行，再按系名连回 `SIS_DEPARTMENT`，这个系出现 4 次，共 33 行；按说明是 30 行。 |
| dw_5526 | gold 直接列出三表 view 的行，没有去重，数学系每条开课重复 12 次（数学系有 12 个项目行）。说明里写了"直接列出会重复"，agent 照做会去重。 |
| dw_827、dw_1140、dw_2417 | 变异系数的 gold 用 `STDDEV_SAMP`，题目却写"using STDDEV only"。说明里只写了 MySQL 中 `STDDEV` 是总体标准差、`STDDEV_SAMP` 是样本标准差，没有指定用哪个。 |

**局限。** 和 5.10 一样，这些说明是看着这 20 道题的 gold 写的，`meaning` 和 `use_for` 里直接写了"graduate-level 指
什么""degree granting 指院系还是项目"，所以结果是已知答案条件下的上限，不能说明在新题上同样有效。

**运行命令。** 库里现在留着 join3 的产物，第一步先删掉。agent 账号对整个库有 SELECT 权限，新表不需要另外授权。读
密码的命令只在子 shell 里执行，避免 `~/semantic-catalog/.env` 里的模型设置覆盖 `~/agent_view/.env`（见 5.10 的插曲）。

```bash
cd ~/agent_view
R() { (set -a; . ~/semantic-catalog/.env; set +a
       docker exec -i -e MYSQL_PWD=$BEAVER_C0_MYSQL_ROOT_PASSWORD beaver-c0-mysql \
         mysql -uroot --default-character-set=utf8mb4 db_agent_view); }
R < db_agent_view/views/drop_join3_semantics.sql
for f in av_dept_course av_dept_offering_summary av_dept_tip_offering_course catalog; do
  R < db_agent_view/views/dept_semantics/$f.sql
done

set -a; . ~/agent_view/.env; set +a
EXP=db_agent_view/experiments/dept_views
for seed in 1 2 3; do
  python3 db_agent_view/runner/run_agent.py \
    --manifest-path $EXP/manifest.jsonl \
    --context-path $EXP/view_semantics_contexts.jsonl \
    --model gpt-5.1 --thinking medium \
    --run-root runs/dept_views/view_semantics_dk_medium/seed$seed --parallelism 4
done
for seed in 1 2 3; do
  python3 db_agent_view/evaluate.py \
    --run-root runs/dept_views/view_semantics_dk_medium/seed$seed \
    --data-dir runs/dept_views/eval_data20
done

R < db_agent_view/views/drop_dept_semantics.sql   # 跑完后清理
```

seed 目录沿用第二轮的 `seed1` 到 `seed3`。对比对象是第二轮 A、B、C、D 四组（`runs/dept_views/*_dk_medium`）。

### 5.13 第五轮方案：先拆子任务再选 view，加全局的量表 `av_measure_route`（待实现）

**起因：第四轮的结果。** 以后只看 relaxed EX。第四轮（5.12）三个 seed 的 relaxed 是 8、6、4，平均 6.0/20，是五组里
最高的；第二轮四组的平均依次是 A 组 4.00、B 组 4.67、C 组 3.67、D 组 2.33。三轮共 60 次作答，42 次判错。逐个读了
SQL 和结果，并把能拿到的 37 条 `final_sql` 在库里只读地重新执行、和 gold 比对，归为六类：

| 原因 | 次数 | 涉及的题 |
|---|---|---|
| gold 本身的问题，照说明做也判错（见 5.12 的表） | 17 | dw_1628、dw_5526、dw_827、dw_1140、dw_2417 各 3 次，dw_1658 2 次 |
| 题目的一部分要用另一个 view，agent 只用了一个 | 8 | dw_1043 3 次、dw_2563 3 次、dw_2519 2 次 |
| 说明里写了，agent 没照做 | 9 | dw_5716 3 次、dw_334 2 次、dw_4462 2 次、dw_5433、dw_306 各 1 次 |
| 运行故障，没有产出结果 | 5 | dw_334、dw_1658、dw_2040、dw_2519、dw_4462 各 1 次 |
| 方差、标准差用了样本版本 | 2 | dw_3742、dw_5144 |
| 结果表和 `final_sql` 对不上（SQL 重跑后等于 gold） | 1 | dw_306 |

这一轮只解决第二类。"degree granting"条件用错（第三类里的 5 次）稍后单独处理。

**只用一个 view 是怎么发生的（读运行轨迹得出）。** 统计 agent 实际执行过的查询（不能在整份轨迹里搜表名：提示和
目录的返回结果里本来就含有这些表名，会虚高）。需要两个 view 的 6 道题是 dw_1043、dw_2519、dw_2563，以及三道
变异系数题 dw_1140、dw_2417、dw_827，后者的变异系数部分 gold 用 `SUBJECT_OFFERED_SUMMARY`。18 次运行中 1 次没有
产出 SQL；其余 17 次里，15 次 agent 读完目录就只读了 `av_dept_tip_offering_course` 的三张说明表，另一个 view 的说明
没读过；另外 2 次读了两个 view 的说明，最终仍只用三表 view。对照的 dw_2040 两部分写得很分明（"课程的 CIP 代码"
和"开课的学分"），对的两次都读了多个 view 的说明并组合使用。

原因是 agent 在读目录这一步按整道题选 view：题目里有 graduate-level 就选三表 view，之后不再检查各个子问题。三表
view 里也确实有 2021FA 的全部开课，所以即使读了第二个 view 的说明，agent 也不觉得需要组合。现有设计挡不住这一点：
目录的 `use_for` 写的是"哪类问题用这个 view"，按整题分流；提示写的是 "choose the view or views that fit the
question"，也是按整题选；能纠正它的信息写在另一个 view 的说明里，而 agent 没去读。

**方案：两项改动一起上。** 选 view 的单位从整道题改成子任务，并要求写下来；同时加一张全局的量表，列出每个 view
能算哪些量。两项必须配套：子任务需要一张按"量"组织的表来选 view，表也需要先拆出子任务才用得上，所以不单独
测其中一项，这一轮的结果是两项合起来的效果。各个 view 的说明表这一轮不改，以便和第四轮对比。

agent 的流程改为：

1. 读 `av_catalog` 和 `av_measure_route`。
2. 把题目拆成子任务，写入 `/tmp/c0-output/plan.md`，每个子任务选一个 view。
3. 读 plan 里每个 view 的三张说明表。
4. 每个子任务在自己的 view 上算好。
5. 用了两个以上的 view 时读 `av_view_join`，各部分上卷到连接粒度，再按 `join_condition` 连接。
6. 写 `final.json` 之前，逐个输出列核对它用的 view 和 plan 是否一致。

runner 只从容器里拷出 `final.json` 和 `gateway.log`（读 `run_agent.py` 得出），但 agent 写文件用的 `write` 调用连同
写入内容都会记进 `agent_trace.jsonl`（第四轮 dw_5716 的轨迹里能看到 `final.json` 的完整内容），所以 runner 不用改，
plan 可以从轨迹里取出来分析。

**需要组合几个 view 的量怎么算。** 分两种情况：

1. 一道题由几个量拼起来，每个量各自只需要一个 view。例如 dw_1043：极差和方差来自三表 view，2021FA 的最大选课
   人数来自 `av_dept_offering_summary`，按院系拼在一起。这不是组合量，靠拆子任务加 `av_view_join` 解决。第四轮
   "只用一个 view"的 8 次错误都属于这种。
2. 一个量的计算本身需要两个 view 的数据：
   - 各自聚合之后再组合就能算。例如"每个院系的课程数除以开课数"：课程数在 `av_dept_course` 上按院系算，开课数
     在 `av_dept_offering_summary` 上按院系算，在 department 粒度连接后相除。这种写成组合量 `measure_combo`，记录
     它由哪几个单 view 的量组成、在哪个粒度连接、最后的公式。
   - 必须在行级别对上两个 view 的数据才能算。例如"研究生层次科目的选课人数方差"：要先知道每条开课属于有研究生
     项目的院系，再在开课行上算方差，不能拿两个聚合好的结果去拼，提示的粒度规则也禁止直接连接 view 的行。这种量
     需要一个专门建好的 view，三表 view 就是为此建的。所以在量表里它是三表 view 的一个单 view 量，不是组合量。

所以量表有两种行，和 semantics 表的 `filter` / `filter_combo` 同一思路：`measure` 是用一个 view 就能算的量（行级别
的组合已经在 view 里做好）；`measure_combo` 由几个 `measure` 在某个粒度连接后组合而成，这个粒度必须在
`av_view_join` 里有对应的行。

**`av_measure_route` 的字段。** 全局一张，和 `av_catalog`、`av_view_join` 一起放在 `views/dept_semantics/catalog.sql`
里。提示里直接写出这张表的名字，和 `av_view_join` 一样，不登记在目录里。

| 字段 | 含义 |
|---|---|
| `measure_id` | 量的标识，主键，忽略大小写后唯一 |
| `kind` | `measure` 或 `measure_combo` |
| `measure` | 这个量是什么，以及题目里常见的说法 |
| `view` | `measure` 行填算它的 view；`measure_combo` 行为空 |
| `grain` | 结果所在的粒度，取所用 view 的 grain 表里的名字 |
| `how` | `measure` 行写用哪些列和条件，用该 view 说明表里的名字；`measure_combo` 行写各部分怎样连接、公式是什么 |
| `built_from` | 只用于 `measure_combo`，填组成它的 `measure_id`，逗号分隔 |
| `not_for` | 说法相近、但要在别处算的量，以及去哪里算 |

**这一轮要写的量（按 20 道题的 gold 归纳）。**

| measure_id（暂定） | view | 量 | 用到的题 |
|---|---|---|---|
| `level_subject_enrollment_stats` | 三表 view | 研究生或本科层次科目的选课人数的极差、方差、标准差、平均、最大和对应科目 | dw_1043、dw_2519、dw_2563、dw_5215、dw_1140、dw_2417、dw_827、dw_1628、dw_1658 |
| `level_subject_count` | 三表 view | 某院系研究生层次科目的个数 | dw_2417 |
| `subject_with_course_material` | 三表 view | 有课程资料的开课清单 | dw_5526 |
| `min_enrollment_with_course_count` | 三表 view | 某学院各院系开课的最小选课人数，和授予学位的课程数一起算 | dw_5433 |
| `term_enrollment_max_avg` | `av_dept_offering_summary` | 某学期某院系任意科目（不限层次）的最大、平均选课人数和最大的科目 | dw_1043、dw_2519、dw_2563 |
| `enrollment_cv` | `av_dept_offering_summary` | 选课人数（只算选课人数大于 0 的开课）的变异系数 | dw_1140、dw_2417、dw_827 |
| `total_units_stats` | `av_dept_offering_summary` | 开课学分的平均、极差、方差、标准差、几何平均 | dw_2040、dw_3742、dw_5144、dw_5161 |
| `dept_total_enrollment` | `av_dept_offering_summary` | 院系开课的总选课人数 | dw_5452 |
| `course_count_cip` | `av_dept_course` | 院系或学院的课程数，CIP 代码的最小、最大、平均、方差 | dw_306、dw_4462、dw_1628、dw_1658、dw_2040 |
| `course_list_budget` | `av_dept_course` | 列出某院系的课程及院系预算代码，按预算分类 | dw_334、dw_5716、dw_4462 |

- `not_for` 的例子：`level_subject_enrollment_stats` 写"不限研究生或本科层次的某学期统计，见
  `term_enrollment_max_avg`；变异系数见 `enrollment_cv`"。agent 即使只看了这一行，也会被引到另一个 view。
- 20 道题里没有需要 `measure_combo` 的量，这一轮不写这种行，只实现字段和测试，避免写出没有题目依据的内容。
- 和 5.12 的说明一样，这张表是看着 gold 写的。例如两张开课表其实都能回答"2021FA 的最大选课人数"，gold 用哪一张
  是由题目模板决定的；dw_5433 问"任意科目的最小选课人数"，gold 却用三表 view，因为它和课程数在一起算。所以
  表里的分流规则属于已知答案条件下的上限。

**表不完整怎么写。** 量表不可能列全每个 view 能算的量，分两处说明：

- 提示里写明：这张表列的是常见的量，并不完整，某个 view 能算的量可能不在表里，表里没有不代表没有 view 能算；
  子任务找不到对应的行时，按 `av_catalog` 的 `use_for` 和各 view 的说明表选 view，都不合适就用基础表。
- plan 里找不到对应行的子任务，`measure_id` 填 `none` 并写理由。之后可以从轨迹统计表覆盖了多少子任务，以及
  没覆盖到的子任务 agent 选得对不对。

**提示的改动（草稿）。** 在 5.11 的提示上改两处，其余段落（三张说明表和 `av_view_join` 的字段说明、四条粒度规则）
逐字不变。第一处替换开头"读目录、选 view、读说明表"这几段：

```text
# Agent views
This database also has pre-joined views and their documentation, in tables whose names start with
`av_`. Start every question by reading the catalog of views and the table of measures:
  SELECT * FROM av_catalog;
  SELECT * FROM av_measure_route;

Then, before you read any view's documentation or write any query, split the question into
subtasks and write the plan to /tmp/c0-output/plan.md. A subtask is one value the question asks for
(one output column, or several output columns computed together), with the conditions that value
needs, such as the school, the term or the program level. Write one line per subtask:
  subtask | measure_id | view | grain | reason
- measure_id: the row of av_measure_route that matches the subtask, or none.
- view: the view that computes the subtask. Different subtasks of one question often need different
  views: choose a view for each subtask separately, not one view for the whole question.
- grain: the grain of the subtask's result, for example department.
av_measure_route lists common measures, but it is not complete: a view can compute measures that are
not listed. If no row matches a subtask, write none and choose the view from av_catalog's use_for
and the views' documentation tables. If no view fits, use the base tables.

Before you use a view, you MUST read all rows of its three documentation tables. They explain what
one row means, what each column describes, and how to filter, group and aggregate on the view
correctly. This is essential for understanding the view; using a view without reading them often
gives wrong answers. For each view in your plan, run exactly these queries, copying the three table
names from that view's row in av_catalog:
  SELECT * FROM <semantics_table>;
  SELECT * FROM <grain_table>;
  SELECT * FROM <grain_edge_table>;
If your plan uses two or more views, also run:
  SELECT * FROM av_view_join;
Compute each subtask on its own view, roll each result up to the grain given in av_view_join, then
join the results with its join_condition. Apply the question's conditions on departments, such as
degree granting or excluding a department, to every subtask. Read every row before writing your
query, and follow the caveats.

Before you write final.json, check every output column against plan.md: it must come from the view
that the plan chose for its subtask.
```

第二处在 `av_catalog` 的字段说明后面加上量表的字段说明：

```text
av_measure_route (one row per measure)
- measure_id: identifier of the measure.
- kind: measure (computed on one view) or measure_combo (computed from several measures, each on its
  own view, joined at one grain).
- measure: what the measure is, and the phrases in a question that ask for it.
- view: for a measure, the view that computes it; empty for a measure_combo.
- grain: the grain of the measure's result.
- how: for a measure, the columns and conditions to use, named as in the view's semantics table; for
  a measure_combo, how to join its parts and the formula.
- built_from: for a measure_combo, the measure_ids it combines.
- not_for: similar measures that are computed elsewhere, and where.
```

和 5.11 相比：第一步多读一张表；新增拆子任务、写 plan 的要求，并明确"不同子任务常常要用不同的 view"；读说明表的
范围从"选中的 view"改成"plan 里的每个 view"；读 `av_view_join` 的条件从"一条查询里组合多个 view"改成"plan 用了
两个以上的 view"，并把组合的步骤写成明确的指令，加上"院系条件要加到每个部分上"；最后加一步提交前的核对。提示里
仍不出现任何具体 view 名和列名。

**实现步骤（按 TDD）。**

1. 先写测试，确认在表和提示都不存在时失败：
   - `av_measure_route` 的字段和上表一致，`measure_id` 忽略大小写后唯一，`kind` 只取两种值；
   - `measure` 行的 `view` 都在 `av_catalog` 里，`grain` 在该 view 的 grain 表里有定义，`how` 里提到的说明表名字
     都存在；`built_from` 只出现在 `measure_combo` 行，引用的 `measure_id` 都存在；`measure_combo` 的粒度在
     `av_view_join` 里有对应的 view 对；
   - 删除脚本会删掉 `av_measure_route`；
   - 提示里有读量表的完整查询、写 `plan.md` 的要求和"表不完整"的说明，量表每个字段都有解释，仍不含 view 名和
     列名。
2. 在 `views/dept_semantics/catalog.sql` 里建表并写入上面 10 行，`views/drop_dept_semantics.sql` 加上这张表。
3. 在 `build_join_experiment.py` 的 `EXPERIMENTS["dept_views"]["arm_notes"]` 里新加一组（暂定名 `view_plan`），
   重新生成 `experiments/dept_views/`，确认原有文件逐字节不变。
4. 在临时库里执行建表语句检查行数，`python3 -m pytest tests -q` 全部通过。
5. 用户运行 3 个 seed，结果放在 `runs/dept_views/view_plan_dk_medium`。

**怎么评估。**

- 主要指标是 relaxed EX 的三 seed 平均，和第四轮的 6.0 对比；单独看上面 6 道需要两个 view 的题。
- 从轨迹统计：写了 `plan.md` 的比例；6 道题里 plan 选了两个 view、并且读了两个 view 说明的次数（第四轮是
  17 次里 2 次读了两个 view 的说明、0 次组合）；`measure_id` 为 `none` 的子任务占多少；最终 SQL 用的 view 和 plan
  是否一致。
- 篇幅和代价：提示变长，每题多读一张表、多写一个文件，比较每题的轮数和耗时。
- 不变的部分作为对照：gold 有问题的 6 道题仍会判错，relaxed 的上限仍是 14/20。
