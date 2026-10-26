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
