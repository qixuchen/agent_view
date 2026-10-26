# 失败驱动的数据产物（agent view）设计草稿

状态：讨论稿，尚未实现。后续逐节修改，每次修改在第 11 节记一笔。

## 1. 动机

目前的做法是从轨迹里抽取"数据理解"，写成自然语言规则注入 agent。这和 TK-Boost、MIRA
一类工作容易被认为是同一件事：它们也是从失败中学习知识，再在推理时检索给 agent。

这里换一个方向：**不改 agent 拿到的知识，而改 agent 面对的数据环境。** 当发现某个误解导致
agent 出错时，不写一条"要注意 X"的规则，而是生成一张派生表（产物），让正确的做法变成
最直接的做法。例如单位混用时，提供一张已经统一换算成元的表，而不是提醒 agent 换算单位。

和已有工作的区别：

- TK-Boost 和 MIRA 的产出是知识（自然语言或修复片段），这里的产出是可执行、可验证的数据表。
- TK-Boost 论文批评"预先生成的数据库描述"。这里的产物不是预先生成的，而是由失败驱动，
  并且每个产物都要通过确定性检查和回放验证。
- 和传统物化视图选择的区别：传统做法追求复用和节省计算，这里追求消除 agent 的误解。
  第 7 节的"从负载出发"对照组用来检验这一区别。
- 和 Text-to-SQL friendly logical database design（arXiv 2606.03145）的区别：它也不改模型、只改呈现给模型的 schema，
  但 view 从历史负载挖出、全部注入 prompt、没有预算和选择；这里从失败出发、由 agent 读清单自己选择、在预算下选择，
  并且修的是对数据内容的误解。详见第 10 节。

原始表始终不改，产物只是新增的派生表。

## 2. 产物的定义

### 2.1 单个产物

每个产物由三部分组成：

1. **视图表**：物化后的中间结果表，例如 SQLite 里用 `CREATE TABLE ... AS SELECT` 建出。
2. **产物介绍**：给 agent 看的说明，见 2.2 的清单条目格式。
3. **建表操作**：一条对原始数据的 SQL 查询。

产物限定为声明式的 SQL 视图定义，不允许任意代码。定义由几部分组成：选哪些基表、按什么键、
加哪些派生列、过滤哪些行。这样做的原因是后面几个阶段都可以机械地完成：

- 合并：对结构化定义做并集（第 4.3 节）；
- 大小：直接执行查询就能算出；
- 不变量检查、列裁剪：可以自动完成。

每个产物还附带：

- **来源**：它要修的是哪几道题的哪几个出错片段（第 5 节）；
- **全表不变量**：例如 DataClaw 上"按 industryId 计数的企业数，44 个行业全部等于全国汇总表的
  企业数量"；
- **回放用例**：用来检验它确实能回答原来出错的查询。

### 2.2 清单（manifest）

清单是一个特殊的产物，给 agent 看，介绍有哪些产物可用。agent 运行时，在探查原始数据集之余，
先看清单判断哪些产物用得上，再去具体看相应的产物。

清单条目只放 agent 判断"要不要打开这张表"所需的信息，不放建表 SQL（agent 需要时再去看）。
示意（用 Beaver dw 库第 dw_0 题涉及的表编的例子，不是实际挖出的产物）：

```text
name: dept_subject_offered
grain: one row per subject offering per term
columns: TERM_CODE, OFFER_DEPT_CODE, DEPARTMENT_NAME, SUBJECT_ID, NUM_ENROLLED_STUDENTS, RESPONSIBLE_FACULTY_NAME
replaces: joining LIBRARY_SUBJECT_OFFERED with SIS_DEPARTMENT on OFFER_DEPT_CODE = DEPARTMENT_CODE
use when: the question asks about courses or enrollment per department; "Course 18" means OFFER_DEPT_CODE = 18 (Mathematics)
```

待定：清单放在哪里、以什么方式告诉 agent 先看清单（system prompt 里一句话，还是数据目录里的
一个固定文件）。

## 3. 约束与成本模型

三个约束：

1. **存储上限 B_storage**：所有产物物化后的总大小不超过上限，按整张表计。
2. **读取 token 上限 B_token**：每个产物的读取代价分两部分。
   - 清单条目的 token m(v)：每道题都要付，不管用不用。
   - 打开产物的 token r(v)：只在 agent 去读这张表时才付，按"相关题的比例乘以每次读取的
     token"估计。
3. **个数上限 K**：产物个数不超过 K。它实际上限制的是清单长度。产物太多会误导 agent，
   这一前提需要第 7 节的"答对率随 K 变化"曲线来支撑。

存储和读取 token 是两种不同的代价，要分开算。一张 17 万行的宽表存储很大，但 agent 只查几行时
读取 token 不多；一张列很多的小表存储很小，但每次 head 都会占满输出。

## 4. 流程

### 4.1 第一阶段：切分数据、运行、分类

1. **先切分训练集和测试集，再做任何事。** 按题型（DataClaw）或按库内分层（Beaver）切分。
   text2sql 上产物按库建，所以必须在**同一个库内**切分，否则测试库上没有产物可用。
   Beaver 的 dw 库有大量同一模板生成的相似题，切分时要把相似题分在同一侧（例如按涉及的表集合
   加 SQL 结构分组），否则测试题和训练题几乎相同，会高估产物的效果。
2. **每道题跑 2 到 3 次**，分成稳定做错、时对时错、稳定做对三类。
   - 产物主要从稳定做错的题里提出；
   - 时对时错的题单独看；
   - 做对的题用来检查产物会不会把对的题改错，也是"省步数"的收益来源。

需要重复运行的依据（实测）：DataClaw 上 init20 的 20 道题在第一轮原始运行中全部做错；不注入
任何规则原样重跑一次（`output_train_a_init20_bare`），有 5 道直接做对（task_078、087、091、
194、485）。单次运行的"错题"里约四分之一会自己翻转。这也意味着现有递归挖掘里"注入规则后做对
而保留"的 8 条 run 中，有 5 道题在不加规则时也做对了，这些收益需要重新审视。

### 4.2 第二阶段：提出原产物

两个来源：

- **从失败出发（主方法）**：从 agent 做错的查询与 gold 的差异出发提出产物，可复用现有
  reflector 流水线，输出从规则换成第 2.1 节的产物规格。
- **从负载出发（对照组）**：从多条 gold SQL 的公共子表达式中挖产物，即传统视图选择的做法
  （CloudViews 一类）。具体做法可沿用 Text-to-SQL friendly logical database design 的 +A：AST 取表集合、频繁项集
  挖掘、LLM 写 DDL（第 10.3 节）。

进入候选池前必须通过的确定性检查：

1. 建表 SQL 能执行，结果确定；
2. 全表不变量成立；
3. 回放用例通过；
4. 建表 SQL 里不出现只在单道训练题里出现的常量（如某所学校名、某个年份、"前 10%"这类题目
   口径），防止题目信息泄漏。

同一个坑会在多道题里被反复提出（DataClaw 上单位问题在 4 道题里各挖出一条规则），这里不去重，
留给第三阶段合并。

### 4.3 第三阶段：生成合并产物

借鉴 AutoAdmin 的视图合并（Agrawal、Chaudhuri、Narasayya，VLDB 2000）：

- **纵向合并**：同一张基表、同一个键，派生列取并集；
- **按键合并**：键相同、基表不同，合并成一张维度表；
- **横向合并**（union）：不鼓励，会混入不同粒度。

合并产物作为**新候选放回候选池**，与它的组成部分互斥，是否采用交给第五阶段决定。第三阶段只
生成候选，不单独求解"合不合并"。合并后要重新检查不变量，并确认仍能通过各组成部分的回放用例。

候选数量最多几十个，两两尝试合并的代价可以忽略。

合并越宽越危险：Text-to-SQL friendly logical database design 的例子里，同一道题多 join 一张表，INNER JOIN 丢掉键为
NULL 的行，计数从 498 变成 377（第 10.3 节）。

### 4.4 第四阶段：计算效用

见第 5 节。

### 4.5 第五阶段：选择要物化的产物

记候选集合为 V，出错片段集合为 F，cover(v) 为产物 v 吸收的出错片段，breaks(v) 为 v 在做对的题
上破坏的正确查询数。求 S ⊆ V：

\[
\max_S \; \Big|\bigcup_{v \in S} \mathrm{cover}(v)\Big| \;-\; \lambda \sum_{v \in S} \mathrm{breaks}(v)
\]

约束：

\[
\sum_{v \in S} \mathrm{size}(v) \le B_{storage}, \quad
\sum_{v \in S} \big(m(v) + r(v)\big) \le B_{token}, \quad
|S| \le K
\]

以及互斥约束：原产物和由它合并出的产物不同时入选。

覆盖项满足边际收益递减（每个出错片段被覆盖一次就算数），适用带预算和个数约束的贪心：
按性价比贪心和普通贪心各做一次取较好者，配合惰性求值（CELF；Khuller、Moss、Naor）。
相关的视图选择贪心算法：HRU 1996、Gupta ICDT 1997。

每个库或数据集的候选只有几十个，**直接用整数规划求精确解**。精确解作为参照，贪心作为可扩展的
方法，报告两者差距。互斥关系在整数规划里是一条线性约束，在贪心里是"选了一个就删掉另一个"。

λ 是对破坏正确查询的惩罚系数，待定。

### 4.6 第六阶段：测试

见第 7 节。

## 5. 效用的定义

DataClaw 上有 milestone，可以直接用"覆盖了几个出错的 milestone"。text2sql benchmark（如 Beaver）
没有 milestone，但有 gold SQL，可以拆出三种粒度，从粗到细：

1. **整题执行正确率（EX）**：最终评测指标。太粗，且要真实运行 agent，代价高、噪声大。
   只用于第六阶段，以及用少量运行校准下面两种代理指标。
2. **gold SQL 能否改写成使用产物**：对应"用视图回答查询"（answering queries using views，
   Halevy 2001 综述）。把 gold SQL G 改写成查询产物 V 的 G'，执行 G'，结果与 G 一致则说明 V
   能用于这道题。改写可以交给 LLM，由执行结果把关。效用看 V 吸收了 G 的多少内容：省掉的 join、
   过滤条件、计算表达式个数。完全离线、确定。
3. **出错片段是否被产物吸收**：把 agent 做错的 SQL P 和 gold SQL G 逐子句对比（TK-Boost 按子句、
   按 CTE 定位错误，仓库里 `cte_refiner` 做同样的事），得到一组出错片段，例如 join 键选错、
   过滤值写错、比率分子分母取错。效用是"有几个出错片段落在 V 的建表 SQL 内部"，即换用 V 后
   agent 不再需要写出这个片段。出错片段扮演 milestone 的角色。

   进一步可以把 gold SQL 的每个子查询或 CTE 单独执行，作为"伪 milestone"，沿用 DataClaw 判断
   中间值对错的做法。Beaver 每道题自带标注好的子问题 `sub_questions` 和对应的子 SQL `sub_sqls`
   （dw_filtered 平均每题 1.98 条），可以直接当作伪 milestone，不用自己拆。

分工：**第 2 种做门槛**（产物至少能让若干道训练题的 gold SQL 正确改写才进入候选池），
**第 3 种做主效用**（决定选哪些产物），**第 1 种做校准和最终评测**。

为什么不用"改对的题数"作主效用：

- 题太少，信号太粗；
- 一道题只有所有出错点都被修好才算对。例如 DataClaw task_429 同时需要解决单位问题和指标别名
  问题，两个产物缺一不可。这种"必须同时具备"的关系不满足边际收益递减，贪心的近似保证不再
  成立。它对应 Gupta ICDT 1997 的 AND-OR 视图图，可作为延伸方向。

省步数先作为次要指标或平局依据。

## 6. 实验平台

### 6.1 Beaver（text2sql 主平台）

选 Beaver 而不选 BIRD 的原因：BIRD 太简单，普通 agent 大多数题都能做对，失败太少，提不出
多少产物；Beaver 是企业数据仓库上的题，普通 agent 会有很多错误。Beaver 上的实际错误率本地还没有
批量运行结果，需要先跑一批量出来（见第 9 节）。

数据在 `~/semantic-catalog/data/beaver/`（实测）：

- 三个库的 MySQL dump（`database/beaver_db/`）：dw.sql 约 92 MB，neutron.sql 约 6 MB，
  nova.sql 约 2.0 GB。dw 有 97 张表（`table/data/dw-*.parquet`）。
- 题目（`query/data/*.parquet`）：

  | 文件 | 题数 | 每题涉及表数（中位数 / 平均） | 每题子 SQL 平均数 | 含领域知识比例 |
  |---|---|---|---|---|
  | dw_filtered | 3,312 | 3 / 3.40 | 1.98 | 45% |
  | dw_real | 121 | 4 / 3.93 | 1.07 | 77% |
  | nova | 1,053 | 3 / 3.12 | 2.22 | 56% |
  | neutron | 1,017 | 3 / 2.68 | 2.22 | 56% |

  dw 原始有 5,787 题，dw_filtered 是 semantic-catalog 项目按"标注与 SQL 是否一致"过滤后的 3,312 题，
  过滤理由记录在 `dw_filtered_audit.jsonl`。dw_filtered 的题型：complex query 1,813、
  domain-specific complex query 1,060、domain-specific query 439。dw_real 的 121 题全部是真实查询。
- 每题的字段：question、sql、tables、join_keys、column_mapping、domain_knowledge、
  sub_questions、sub_sqls。

对本设计的含义：

1. **题量不再是瓶颈。** 一个 dw 库就有 3,312 题，产物按库建也有足够的训练题。但其中大量是同一
   模板生成的相似题，切分时要按相似题分组（第 4.1 节）。dw_real 的 121 道真实题适合作为最终测试集。
2. **伪 milestone 现成可用。** `sub_sqls` 是标注好的子 SQL，可直接作为第 5 节第 3 种效用的检查点。
3. **`domain_knowledge` 相当于 BIRD 的 evidence。** 例如 dw_0 的标注写明 "Course 18" 对应
   `DEPARTMENT_NAME = 'Mathematics'`。这正是产物想消除的误解，是否提供它会显著影响产物的价值，
   倾向两种设定都报告，以不提供为主实验。
4. **`join_keys` 标注了正确的连接键。** 连接键选错是企业库上的典型错误，"预先连接好的视图"是一类
   天然的产物。
5. **存储约束是真实的。** nova 的 dump 就有 2.0 GB，宽表物化的代价不可忽略，第 3 节的存储上限有
   实际意义。
6. **标注本身有错。** dw_0 的标注列出了 TIP_SUBJECT_OFFERED 表，但 SQL 里并没有用到，这是它被
   过滤掉的原因之一。从 gold SQL 挖出的产物可能把这类错误固化，所以改写一致性检查最好在多道题上
   同时成立。
7. **可复用的环境。** semantic-catalog 已有 MySQL 镜像和初始化脚本（`scripts/beaver_c0/`
   下的 Dockerfile、init_dw_mysql.sh）以及执行正确率评测（evaluate_c0.py，输出 ex、
   column_alignment 等字段）。`artifacts/support_trace/beaver/` 下的 9 条轨迹全部做对（ex=1），
   是挑出来的成功轨迹，不能用来估计错误率。

### 6.2 BIRD mini-dev（备选，不作主平台）

数据在 `data/minidev/MINIDEV/`（实测）：500 题，11 个库，每库 30 到 66 题，难度 simple 148、
moderate 250、challenging 102，带 evidence 字段。不作主平台的原因是普通 agent 大多能做对，
而且每库题少（切分后每库只有约 15 到 30 道训练题）。可作为"简单库上产物不帮倒忙"的补充检验。

### 6.3 DataClaw（有 milestone 的平台）

- 共 492 道题（`~/DataClaw/tasks`，实测）；
- train_a 第一轮 123 道，69 道做错、54 道做对（实测）；
- 题型分布不均：train_a 中 enterprise_industry_analysis 56、enterprise_industry_policy_analysis 19、
  comprehensive_decision 18、international_comparison 10、industry_planning 7、
  hypothesis_verification 7、risk_assessment 6（实测）。

DataClaw 的数据是 CSV 而不是数据库，建表操作可以用 DuckDB 直接查 CSV。

## 7. 评测设计

1. **只在测试集上测，每题重复 3 次**。报告修好率和改错率（MIRA 指出改错率与修好率同样重要），
   以及步数。
2. **对照组**：
   - 不加任何东西重跑（噪声基线）；
   - 全部候选产物都给，不做选择；
   - 只给规则（现有递归挖掘的做法）；
   - 同样个数 K、随机挑选的产物；
   - 从负载出发的产物（第 4.2 节）；
   - Text-to-SQL friendly logical database design 的 +A：从负载挖 view，按 schema linking 结果全部注入（第 10 节）；
   - 不看失败、让 LLM 预先整理数据库得到的产物（对应 TK-Boost 批评的"预先生成的数据库描述"）。
3. **消融**：合并与不合并；K 取不同值的答对率曲线。
4. **使用情况**：从轨迹统计 agent 是否看了清单、是否打开了产物、打开的是否是离线判定能用上的
   产物。"产物没被用"和"用了没效果"是两种失败。
5. **清单选择的离线评测**：把题目和清单交给 LLM，问它会打开哪几个产物，与离线判定的可用产物
   比对。只需一次 LLM 调用，单独衡量清单写得好不好。

统计功效提醒：约 240 道测试题、每题 3 次，大概只能可靠检测几个百分点以上的差别（粗略估计，
未正式计算）。

## 8. DataClaw 上已测的数据事实与候选产物

数据事实（`~/DataClaw/assets/database`，实测）：

- company_operation_status：353,438 行，49 个指标代码，每个代码都有不止一个名称，10 个代码有
  不止一种单位；Y_EC_22 有 5 种单位、各约 1,400 行；Y_EC_59 的名称混用省级、部级、省部级，
  所以产物要按代码而不是按名称组织。
- regional_industry_status：170,896 行，4,482 个 targetName，没有代码列，167 个名称有多种单位；
  营收合计有 5 种写法（广东、上海、新疆、山东用"营收金额合计"，北京用"营业收入金额合计"）。
- policy_resource：1,129 条记录分布在 92,057 个物理行上。
- 翻译表 company_items：173 条，其中 170 条能在 2022 年企业画像中匹配。
- company_profile 按 industryId 计数，44/44 个行业等于全国汇总表的企业数量；商业电气机械和器材
  制造业的 335 行是 320 行 industryId=8 加 15 行 industryId 为空，所以 task_458 那条规则给出的
  原因是错的。

轨迹统计（208 次运行、123 道题、4,272 次调用，实测）：查指标 27%、看表头 26%、列目录 15%、
计算 12%、查实体 9%、翻译 3%、联网 3%；第一次针对性查询前中位数 5 次调用；`python: not found`
出现 74 次。

候选产物（从已有规则中归纳，未实现）：

1. 单位统一的 `value_yuan`；
2. 规范指标列，加按代码组织的别名表；
3. 展平的政策表；
4. 实体解析表（英文名、中文名、bmCode、属性）；
5. 显式零值（`value_or_zero` 加 `value_source`）；
6. 是否计入汇总的标记（industryId 非空，44/44 不变量）；
7. 企业上下文视图。

初步合并为 3 个：规范化指标表（1、2b、5）、企业维度表（4、6、7）、政策表（3）。

## 9. 待定问题

1. 实验是否提供 Beaver 的 `domain_knowledge`（倾向两种都做，以不提供为主）。
2. Beaver 上的基线错误率和翻转率：先在 dw 训练集上抽一批题（例如 200 道），用普通 agent 每题跑
   2 到 3 次，量出错误率和翻转率，同时得到做错的 SQL，作为出错片段的来源。
3. Beaver 相似题的分组方式（按表集合加 SQL 结构，还是按 sub_sqls 聚类），以及先用 dw 一个库，
   还是 dw、nova、neutron 三个库都做。
4. agent 运行环境：复用 semantic-catalog 的 MySQL 镜像和评测脚本，还是在 TK-Boost 里重新接一套。
5. 清单的放置位置和告知 agent 的方式。
6. λ 的取值。
7. B_storage、B_token、K 的具体数值。
8. 产物描述的 DSL 具体形式（直接用 SQL，还是用结构化字段再生成 SQL）。
9. 是否把 1:1 改名 view 作为一类产物（第 10.3 节），以及清单条目是否附使用示例查询。
10. BIRD 是否采用合库（BIRD-Union）、去掉 evidence 的设定来提高难度（第 10.3 节）。

## 10. 相关工作：Text-to-SQL Friendly Logical Database Design

论文：Shi Heng Zhang、Zhengjie Miao、Jiannan Wang，*The Case for Text-to-SQL Friendly Logical Database Design*，
arXiv 2606.03145，2026 年 6 月（本地 `docs/insight/papers/text-to-sql friendly logical database.pdf`）。下面的内容和数字
由 PyMuPDF 提取论文正文后阅读得出。这是目前和本设计最接近的工作，必须引用并讲清区别。

### 10.1 论文做了什么

- **主张：** schema 的读者从人变成了 LLM，逻辑设计应多一个目标：让 LLM 容易把问题写成正确的 SQL。不改模型，只改
  呈现给模型的 schema，底层数据库不动。
- **三种不改语义的变换：**
  - **+A（schema abstraction）：** 把历史负载里反复出现的 join 路径做成逻辑 view（如 `atom_join_bond_join_molecule`）。
  - **+P（schema partitioning）：** 按历史负载把表分区，每题只给相关分区，few-shot 示例也只从该分区的历史题里取。
  - **+R（schema renaming）：** 表名、列名改成描述性名字（如 `molecule.label` 改为 `carcinogenic_flag`），实现为 1:1 的
    view 加映射字典。
- **语义保持的定义：** +R 是标识符上的双射；+A 的 view 必须能由原 schema 经 SQL 组合得到，不引入新信息；+P 只取原 schema
  的子集。
- **+A 的实现四步：** (1) 用 AST 解析历史 SQL 取出表集合，做频繁项集挖掘得到候选 join 组合；(2) 让 LLM 写 view 的 DDL，
  有外键时可退回按外键生成的代码，丢掉会产生笛卡尔积的候选；(3) 让 LLM 把历史 SQL 改写成使用 view 的版本，只保留执行结果
  一致的改写；(4) 推理时把含有 schema linking 选中表的 view 全部加入 prompt，并把用到这些 view 的历史 SQL 加入示例池。
  没有历史负载时，跳过 (1)(3)，按 schema linking 选中的表临时生成 view。
- **实验：** BIRD-Union（BIRD dev 的 11 个库合成一个 schema，75 张表，1,534 题，去掉 evidence 和列描述）和 Spider-Union
  （19 个库，78 张表，1,004 题）；历史负载和测试各占一半，baseline 也拿同样的 few-shot 示例，唯一区别是 schema。
  执行正确率最多提高 4.2 个百分点（Gemini 2.5-flash-lite 上 BaseSQL 从 48.1 到 52.3）；GPT-4.1 mini 上 BaseSQL 从
  49.8 到 52.4（+A+P）。
- **不是单调有益：** BIRD-Union 11 个库中 8 个变好、1 个不变、2 个变差，card_games 降 5.4 个百分点。按题看变好 74 题、
  变差 42 题，变差的几乎都来自分区剪掉了需要的表或检索到错误的 view。改名也会出错：financial 库上改出的
  `Bank_Clients`、`Bank_Districts` 看起来合理，却把模型引到错误的表。
- **future work 第一条：** "dynamic, cost-aware view materialization"，即带代价的 view 物化选择。

### 10.2 和本设计的区别

1. **产物从哪里来：** 他们从历史 gold SQL 的频繁表组合挖 view，相当于本设计第 4.2 节的"从负载出发"；本设计的主方法是
   从 agent 失败出发。
2. **产物修什么：** 他们修 schema 结构层面的问题（join 路径、无关上下文、名字不清）；本设计还要修对数据内容的误解，
   例如单位不统一、空值表示 0、两个数据源只能靠中文名连接（第 8 节），而且 DataClaw 的数据是原始 CSV 和 JSON。
3. **怎么交给模型：** 他们按 schema linking 结果把相关 view 全部注入 prompt；本设计让 agent 先读清单，自己决定打开哪些
   产物（第 2.2 节）。
4. **预算与选择：** 他们没有存储、token、个数预算，也没有选择步骤；本设计的第 4.5 节正是他们 future work 所说的
   带代价物化选择。
5. **系统形态：** 他们是固定流程的 text2sql pipeline（BaseSQL、DIN-SQL、MAC-SQL、CSCSQL）；本设计面向会自己探查数据的 agent。

### 10.3 可以借鉴的做法

- **PoC 的产物提出方法（第 4.2 节）：** 在 BIRD、Beaver 上从训练题 gold SQL 提 view 时，直接沿用他们 +A 的前两步：AST 取
  表集合、频繁项集挖掘、LLM 写 DDL 加外键兜底、过滤笛卡尔积。
- **让 agent 知道怎么用产物：** 他们发现示例里从没用过的 view 模型往往不会用，所以把历史 SQL 改写成使用 view 的版本作为
  示例。本设计可以在清单条目里附一条使用该产物的示例查询；改写本身和第 5 节"gold SQL 能否改写成使用产物"是同一操作，
  可以共用实现。
- **合并的风险（第 4.3 节）：** 他们讨论了 view 窄则覆盖少、宽则趋向把所有表连在一起的 "omni-view"，并给出反例：同一道题
  多 join 一张表后 INNER JOIN 丢掉键为 NULL 的行，计数从 498 变成 377。这支持合并后必须重新检查不变量。
- **breaks(v) 和个数上限 K（第 3、4.5 节）：** 他们 42 道变差题主要来自错误的 view 和过度剪枝，是"产物会把对的题改错、
  产物太多会误导"的外部证据。可以借鉴他们按变好、变差两组分别比较各 SQL 子句匹配率的错误分析。
- **改名作为一类产物：** 1:1 改名 view 加映射字典符合本设计的产物格式；Beaver 列名晦涩，可能收益大，但也要过回放检查。
- **实验设计（第 6、7 节）：** 把 BIRD 的多个库合成一个 schema、去掉 evidence，可以缓解"BIRD 太简单"；baseline 拿同样的
  示例以隔离 schema 的作用；区分设计时历史和 prompt 时历史；历史比例 0%、50%、100% 的消融。
- **对照组（第 7 节）：** 复现他们的 +A（从负载挖 view，按相关性全部注入）作为强基线，用来说明"从失败出发、清单加选择、
  带预算"的增益。

## 11. 修改记录

- 2026-10-20：初稿，记录当前讨论。
- 2026-10-20：text2sql 主平台由 BIRD 改为 Beaver（BIRD 太简单，普通 agent 大多能做对）。
  新增第 6.1 节 Beaver 的实测数据和对设计的含义；BIRD 降为第 6.2 节备选；清单示例改用 Beaver dw
  的表；第 4.1 节加入相似题分组切分；第 5 节注明 `sub_sqls` 可直接作伪 milestone；第 9 节待定问题
  随之更新。
- 2026-10-20 至 2026-10-21：slides 计划（原第 10 节）及其修改，现见 `agent_view_slides.md`。
- 2026-10-21：原第 10 节 slides 计划拎出为 `agent_view_slides.md`；新增第 10 节相关工作（Text-to-SQL Friendly Logical
  Database Design，arXiv 2606.03145），第 1、4.2、4.3、7、9 节加入相应引用。
