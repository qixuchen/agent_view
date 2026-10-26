# 失败驱动的数据产物（agent view）：slides 计划

本文档原是 `docs/dataclaw/agent_view.md` 的第 10 节，2026-10-21 单独拎出。设计本身见 `agent_view.md`；
本文中"第 N 节""第 N.M 节"指本文档自己的章节时写作"本文档第 N 节"，其余（如第 3 节约束、第 4.2 节确定性检查、
第 5 节效用、第 6 节实验平台、第 7 节评测）都指 `agent_view.md` 的章节。修改记录里的旧编号"第 10.k 节"对应本文档第 k 节。

用一版 slides 呈现这个 proposal，共 6 页：动机、示例、产物、流程、研究问题、benchmark。**slides 全部用英文写**；
本文档的说明仍用中文，但每页的上屏文字直接记录英文原文。做法沿用 `docs/insight/plan.md`：先在本文档写每页的
"一页 slides 方案"，再照着做页面，两边保持一致。一页一页地写，每页做完再进行下一页。

## 1. 文件位置

- 每页一个 HTML：`docs/presentations/proposal/agent_view_<页名>.html`，页名依次为 `motivation`、
  `example`、`artifact`、`pipeline`、`merge_select`（第 5 页研究问题页，原计划名 `questions`）、`benchmark`。
- 合订页：`docs/presentations/proposal/agent_view_report.html`，和 `docs/insight/slides/report.html`
  一样，用 iframe 把各页按顺序串起来；`agent_view_report_final.html` 是不用 iframe 的版本，把各页内容直接拼进一个文件，单页改动后需要重新生成。
- 自己画的示意图放在 `docs/presentations/proposal/figs/`。
- 截图检查：用 Windows 上的 Chrome 无头模式（`chrome.exe --headless=new --window-size=1280,720
  --screenshot=...`）渲染，截图放 `tmp/shots/`，不提交。

## 2. 写法约定（沿用 insight，改为英文）

- 上屏文字全部用英文。
- 每页上屏文字控制在 150 词左右，只讲重点；细节、数字出处和补充说明写进该页的"口头补充"。
- 说明文本分点写，要点用短句，关键词加粗。
- 每个点要么能独立读懂，要么结合前面的点能读懂：
  - 提到的概念必须在本点或前面的点里交代过（如 artifact 第一次出现时要用一句话说明）；
  - 给出比例时说清楚分母和各类别的含义；
  - 不用读者无法自行理解的内部术语；
  - 一个点只讲一件事；
  - 用 "they""these" 指代时，指代对象必须在前文明确出现过。
- 数字要能追溯到本文档里的实测或引用；估计的数字在页面上标明是估计。
- 版式：1280×720，和 insight 的 slides 相同的配色（标题蓝色 `#0f5e9c`，标题下一条蓝线，右上角写
  "Proposal · 页码 / 总页数"）。其余布局按每页的内容形状单独安排，不套固定模板。内容不溢出页面，正文字号
  不小于 16px，图表的解释紧挨着图表。每页做完都要渲染截图检查。

## 3. 第 1 页：动机（`agent_view_motivation.html`）

（2026-10-20 第五版已做，页面与下面的文字一致。第一版是中文、带 Y_EC_22 示意图的单页，拆成本页和第 2 页示例页；
第二版约 380 词，太多；第三版精简到约 135 词；第四版改为逐行对比表（用户直接改过：删掉底部研究问题，"Keeps"
一行改为 "Agent Behavior"）；第五版用户认为表格过于简略，改回两栏文字，上屏约 140 词。之后用户直接改页面：
左栏第二、三条互换，删掉 TK-Boost 35.6% / 44.6% 的小字，右栏标题改为 "New: generate data artifacts"。）

**标题：** Motivation: Change the Data, Not the Context。右上角：Proposal · 1 / 5。

**这页要传达的一句话：** 已有方法生成的是知识或误解，不改存储的数据集，靠后续检索放进 agent 的 context；
我们生成的是数据产物，不改 context，而是生成更容易用于解决任务的 view 来提升 agent 表现。

**版式：** 上方灰底通栏写问题；下方左右两栏，左栏灰色栏标题，右栏蓝色栏标题、浅蓝渐变底，每栏三条完整句子，
左右逐条对应（生成什么、改什么、怎么起作用）。

**上方通栏：**

> Data agents often fail not because they cannot write SQL, but because they **misunderstand the data**.

**左栏：Existing: learn knowledge from failures**（小字：TK-Boost, MIRA）

> - They mine misconceptions from failed tasks and store them as **knowledge** in text.
> - For every new task, the right piece must be **retrieved** and applied again.
> - The stored dataset stays unchanged; the fix is injected into the agent's **context**.

**右栏：New: generate data artifacts**（无小字）

> - We turn each misconception into a **data artifact**: a derived view over the original tables.
> - The agent's context stays **unchanged**; what changes is the **data** it can query.
> - The views are **task-ready**: the correct query becomes the simple one, so the agent does not have to rediscover
>   the fix.

**口头补充（不上 slide）：**

- 误解的例子（页面上已删，第 2 页示例页展开）：DataClaw 中营业利润（代码 Y_EC_22）有 4 种名称、5 种单位。
- 35.6% 和 44.6% 是 TK-Boost 表 5 的消融：同一批知识全部交给 agent 对比按子查询检索再纠正（Spider 2 SQLite，
  GPT-4.1，不加辅助 27.7%）。
- 已有方法的另一个局限（页面上没放）：同一个误解每道题都要重新纠正。知识只是提醒，agent 每道题都要找到、读懂并写对修正；我们在 DataClaw 上挖规则时，单位换算
  问题在 4 道题里各挖出了一条规则。
- TK-Boost 写成自然语言知识，MIRA 写成经过数据库事实验证的修复记忆。
- 和其他工作的区别（页面上没放，被问到时用）：与离线数据描述相比，产物由真实失败驱动，对应 TK-Boost 论文对
  "预先生成的数据库描述"的批评；与物化视图选择相比，两者都在预算下选派生表，但视图选择是为已知负载复用计算，
  我们的产物收益是修好的失败。产物附带建表 SQL，在全表上检查不变量，并回放原来做错的查询，因此可验证。

**数字来源：** Y_EC_22 的 4 种名称、5 种单位由读
`~/DataClaw/assets/database/enterprise/company_operation_status.csv` 统计（4 种名称：营业利润金额 2,837 行、
经营利润金额 1,390 行、营业利润 1,349 行、营业利润总额 1,319 行；5 种单位各约 1,350 到 1,410 行）；35.6%、44.6%、
27.7% 来自 TK-Boost 表 5（见 `docs/insight/plan.md` TK-Boost 一节）；"4 道题各挖出一条规则"来自 train_a 递归挖掘
的规则。

## 4. 第 2 页：示例（`agent_view_example.html`）

（2026-10-20 第二版已做，页面与下面的文字一致。第二版按用户要求强调"没有产物时 agent 可能发现不了两个数据源
之间的联系"。曾提出三个候选：A 是 task_429 单位不统一导致排序选错省份，
B 是 task_087 空值其实表示 0，C 是 task_116 英文公司名对不上中文记录；用户选了 C。A 和 B 留作口头补充。）

（2026-10-21 第三版：用户直接把标题改为 "Motivating Example"；按用户要求用同一个例子再展示改名（renaming）的作用：
题目说 "listing boards"，`company_profile.csv` 里对应的列名是 `plate`，产物里改名为 `listing_board`。）

**标题：** Motivating Example。右上角：Proposal · 2 / 6。

**这页要传达的一句话：** 答案需要把两个数据源连起来，而连接它们的键（中文公司名）题目里根本没出现；没有产物时
agent 必须自己发现这个联系，很容易发现不了而出错；产物把连接预先做好，就没有需要发现的东西了。同时，题目里的
"listing board" 在原表里叫 `plate`，产物把列名改成题目的说法，agent 不用再猜哪一列对应题目里的词。

**版式：** 上方灰底通栏是题目和 gold；下方左右两栏，左栏 "Without artifact"（灰色），右栏 "With artifact"
（蓝色）。每栏从上到下是数据、agent 轨迹，最下面一个小框写结论。

**上方通栏：**

> **Q:** In 2022, are the **listing boards**（紫色）of *Chuang Wei Jin Zhi Electrical Appliances Co., Ltd.* and *Long He Chan
> Zhi Di Chan Holdings Co., Ltd.* the same? (DataClaw task_116)　**Gold: Yes**

**左栏：Without artifact**

- Source 1: translation file `bilingual_translation_english_chinese.json`，两行原文（中文名用橙色标出）：
  `"创玮锦智电器公司": "Chuang Wei Jin Zhi Electrical Appliances Co., Ltd."`、
  `"龙河产置地产控股公司": "Long He Chan Zhi Di Chan Holdings Co., Ltd."`。
- 两个数据源之间一条红色虚线，标注："✗ Linked only by the Chinese name; the agent never found this link"。
- Source 2: company records `company_profile.csv` (Chinese names only)（中文名同样用橙色标出）：bmCompanyName | exchange | plate 两行，
  创玮锦智电器公司 | 深交所 SZSE | 主板 Main Board；龙河产置地产控股公司 | 港交所 HKEX | 主板 Main Board。`plate` 列头用紫色标出，
  和题目里的 "listing boards" 同色。
- 表下紫色一行："✗ The question says "listing board", but the column is named `plate`"。
- Agent trace: reads Source 1, never opens Source 2：`ls database` → `look for the company names` →
  `read translation file, never find plate info` → "No relevant data found" ✗（红色）。

**右栏：With artifact**

- View `company_dim`: Source 1 and Source 2 joined in one table：name_en | name_zh | exchange | listing_board 两行（浅黄高亮），取值与左栏一致，
  exchange 和 listing_board 保留原始中文值、旁边加英文注释；`listing_board` 列头紫色。
- 表下绿色一行："✓ Column renamed to match the question: `plate` → `listing_board`"。
- Agent trace (expected)：`ls database` → `look for company names` → `find company name with listing_board presented` → "Yes" ✓（绿色）。

（用户直接改页面：两栏轨迹改写为上面的文字；删掉两栏底部的结论框 Missed link / Link made explicit，以及右栏的建表 SQL。
2026-10-21 按用户要求把轨迹字号调大：步骤 16.5px 等宽字体，箭头和结论 18px。）

**字数：** 上屏约 180 个英文词（去掉 HTML 标签后用脚本统计，不含中文），其中约一半是表格和 JSON 里的数据。

**口头补充（不上 slide）：**

- 原始运行（`output_train_a/.../gpt-5.1_20261005_1256_786b82`）的 6 次调用依次是：直接读目录（报错）、
  `ls database`、在 enterprise 和 industry 下各找一次 `*.json`、在整个 database 下找 `*.json`、读翻译文件，然后就答了
  "No relevant data found"，从没打开过 `company_profile.csv`。过程评判 0/3 个 milestone 达成。
- 右栏的轨迹是预期，不是实测。
- 翻译文件 `company_items` 有 173 条，其中 170 条能在 2022 年的 company_profile 里匹配；有的公司对应多个英文名
  （值是列表），所以真实的 `company_dim` 要允许一个公司有多个 name_en。
- 两家公司都是主板，所以答案是 "Yes"；交易所不同（深交所、港交所），题目问的是板块不是交易所。
- 改名的例子是真实数据，不是编的：`company_profile.csv` 共 29 列，存板块的列就叫 `plate`，取值有主板 4,882 行、创业板 1,351 行、
  科创板 499 行、北交所 162 行，以及境外市场的 Growth、Standard、Prime 等（实测）。题目用 "listing board"，列名用 "plate"，agent 要自己
  意识到二者是一回事；旁边的 `exchange` 列也像是答案所在，题目问板块而不是交易所，容易选错列。
- 改名对应 Text-to-SQL friendly logical database design 的 +R（`agent_view.md` 第 10 节）；该论文也报告改名会出错（financial 库），
  所以改名产物同样要过回放检查。
- 另两个候选：task_429 中，"政府奖励资金、补贴合计"在 14 个省用了 5 种单位，按原始值排序上海第 12、广东第 1，换算成
  元后上海第 1（2,466,523,519 元）、广东第 4；task_087 中，Y_EC_59 共 6,895 行，6,433 行为空值、没有一行写 0，agent
  把海力创耀家电的空值当成缺数据。

## 5. 第 3 页：产物（`agent_view_artifact.html`）

（2026-10-21 第三版已做，页面与下面的文字一致。第二版先讲清单、再讲 view 产物、最后讲 agent 自己选择产物。之后用户直接改页面：
标题改为 "Current design: Manifest + View Artifacts"，删掉底部 agent 运行时的流程条，第三条要点改写。第三版按用户要求删掉 view 产物
的 Description 部分（和清单条目重复），右栏上方加两层存储结构示意图，要点压缩到约 45 词。）

**标题：** Current Design: Manifest + View Artifacts。右上角：Proposal · 3 / 6。

**这页要传达的一句话：** 我们在原数据集之上加一层产物层（清单和 view 产物），原数据集不动；agent 先读清单，再打开相关产物，
需要时仍可读原数据。

**版式：** 左边是结构图（上方清单，下方 view 产物卡片），右边上方是两层存储结构示意图，下方 3 条要点。结构图沿用第 2 页示例页的
`company_dim`，保持连贯。

**左边结构图：**

- 上方蓝框 MANIFEST（one short entry per artifact; illustrative），3 个条目，`company_dim` 一条加白底框表示被选中：
  - `company_dim`：use when the question names a company in English
  - `metric_yuan`：use when comparing money amounts stored in mixed units
  - `award_counts`：use when counting awards; blank cells mean 0
- 从 `company_dim` 引一个箭头向下，展开成 "VIEW ARTIFACT `company_dim`" 卡片，两个编号部分：
  1. View table：name_en | name_zh | exchange | listing_board 两行，与示例页相同（创玮锦智电器公司，深交所，主板；
     龙河产置地产控股公司，港交所，主板）。
  2. Definition (declarative SQL over the original tables)：

```sql
CREATE VIEW company_dim AS
SELECT p.bmCode, t.name_en, p.bmCompanyName AS name_zh,
       p.exchange, p.plate AS listing_board
FROM company_profile p
JOIN translation t ON t.name_zh = p.bmCompanyName;
```

**右边上方：存储结构示意图**

- 左侧一个 agent 图标（🤖，标 "Agent"），引出两条蓝色箭头，都标 "reads"，分别指向右侧上下两层。
- 上层蓝框：**Artifact layer** (created by us)，内含 `manifest`（加粗）、`company_dim`、`…`。
- 两层之间小字："↑ built by SQL over"。
- 下层灰框：**Original dataset** (never modified)，内含 `company_profile.csv`、`…`。

**右边下方要点：**

> - **Manifest:** catalog of artifacts and their descriptions.
> - **View artifact:** a derived table plus the SQL that builds it.
> - **Agent:** reads the manifest first, then opens relevant artifacts; access original dataset as usual; no context change.

（用户直接改过这三条；2026-10-21 随示例页把 view 的列名 `plate` 改为 `listing_board`，表格字号从 15px 调到 14px 以放下新列名。）

**字数：** 上屏约 190 个词，其中约 120 个在结构图的清单、表格和 SQL 里；说明性文字（示意图加要点）约 70 词。

**口头补充（不上 slide）：**

- 产物的介绍（grain、replaces、use when）放在清单条目里，view 产物本身只有表和建表 SQL。清单条目的完整形式（第 2.2 节）是 name、
  grain、columns、replaces、use when，页面上只显示 use when。
- 清单里 `metric_yuan`、`award_counts` 是示意，对应第 8 节的候选产物 1（单位统一）和 5（显式零值），都还没实现。
- company_profile 每年一行（有 year 列），所以 grain 是"每家公司每年一行"。
- "kept only if it fixes the original failures" 对应第 4.2 节的四道确定性检查：建表 SQL 能执行且结果确定、全表不变量成立、回放用例
  通过、建表 SQL 里不出现只在单道训练题里出现的常量。页面上只概括了回放这一条。
- agent 运行时的顺序（页面上的流程条已删）：读清单，选择产物，打开选中的 view，需要时再读原始表，然后作答。没有产物适用时，
  agent 照常读原始表。
- 清单的代价：清单条目每道题都要读，view 只在打开时才读，所以产物个数要有上限（第 3 节），第 5 页展开。

## 6. 第 4 页：流程（`agent_view_pipeline.html`）

（2026-10-20 第三版已做，页面与下面的文字一致。第一版 6 张卡片、每张带 "Out:" 产出，约 180 词；第二版卡片缩成一句、
删掉 Out，底部预算先写成一段文字、再改成三条列表。之后用户直接改页面：删掉第 4 阶段 Score，效用问题并入 Select
卡片；预算标题改为 "Selection constraints"，token 一条改写。第三版把约束列表移到第 5 页，网格改为 5 列，阶段重新编号，
橙色括线只盖 Merge 和 Select。2026-10-21 用户直接把 Run、Propose 的做法改短；按用户要求 Propose 也算研究问题，问题是 "How to propose?"，括线扩到 Propose、Merge、Select。）

**标题：** Pipeline: From Failures to Materialized Artifacts。右上角：Proposal · 4 / 5。

**这页要传达的一句话：** 从失败的题出发提出产物，合并成候选池，按效用在约束下选出要物化的产物，最后在留出的测试题上
检验；其中提出、合并和选择三步是研究问题。

**版式：** 5 个阶段卡片横排、垂直居中，卡片之间蓝色箭头；第 2 到 4 阶段用橙色（顶边、浅黄底、阶段名、研究问题）区分，
上方一条橙色括线标 "Research questions (next page)"。每张卡片从上到下：STAGE n、阶段名、一句做法、（第 2 到 4 阶段）
虚线下的研究问题。

**5 张卡片：**

| 阶段 | 名称 | 做法 | 研究问题 |
|---|---|---|---|
| 1 | Run | Run the agent on training tasks. | |
| 2 | Propose | Propose view artifacts for each task. | How to propose? |
| 3 | Merge | Combine compatible artifacts. | Which to merge? |
| 4 | Select | Pick artifacts to materialize based on utility and budget constraints. | How to compute utility? |
| 5 | Test | Evaluate on held-out tasks. | |

**字数：** 上屏约 60 词。

**口头补充（不上 slide）：**

- 第 1 阶段每题跑 2 到 3 次（页面上没写）：DataClaw 上 init20 的 20 道错题不加任何规则原样重跑，有 5 道自己做对，单次运行
  的"错题"里约四分之一会翻转（第 4.1 节）。同时要按题型或库内分层切出测试集；Beaver 要把同模板的相似题分在同一侧。
- 第 2 阶段提出的产物要先过第 4.2 节的四道确定性检查才进入候选池（页面上没写）。
- 第 4 阶段的效用在 DataClaw 上按 milestone 计，在 Beaver 上按出错片段或 `sub_sqls` 计（第 5 节）。
- 第 5 阶段的对照组见第 7 节：不加任何东西重跑、全部候选都给、只给规则、随机挑 K 个、从负载出发、LLM 预先整理。
- 还没画进图里的想法：第 2 到第 5 阶段可以迭代多轮，而不是只跑一次（待确认）。

## 7. 第 5 页：研究问题：合并与选择（`agent_view_merge_select.html`）

（2026-10-20 第一版已做，页面与下面的文字一致。按用户要求只讲合并和选择两个研究问题，并把流程页的约束列表移到本页。
效用怎么算只作为选择栏里的一行目标函数，是否单独成页待定。）

**标题：** Research Questions: Merge and Select。右上角：Proposal · 5 / 5。

**这页要传达的一句话：** 合并要决定把哪些重叠的产物合成一张更宽的 view，做法是把合并产物作为新候选、与组成部分互斥，
交给选择阶段；选择是在存储、token、个数三个约束下最大化修好的失败，覆盖目标边际收益递减，可用贪心，精确整数规划作参照。

**版式：** 左右两栏，橙色顶边。左栏 STAGE 3 Merge，右栏 STAGE 4 Select。每栏底部一行灰色小字写可借鉴的已有工作。

**左栏：Merge: which artifacts to combine?**（用户直接改过：删掉小图和 Open 一条，改写前两条和 Idea。）

> - Misconceptions are proposed from many tasks, so candidates **overlap**.
> - Merging saves storage and manifest lines, but a wider view costs more **tokens** and may mix grains.
> - **Idea:** add merged views as **new candidates**, let selection stage decide which to materialize.
> - **Existing work:** physical design tuners such as **AutoAdmin** already merge candidate views and indexes to fit a
>   storage budget; we may borrow ideas from them.
>
> Related: AutoAdmin view merging (VLDB 2000); index merging (ICDE 1999); relaxation-based tuning (SIGMOD 2005)

**右栏：Select: which artifacts to materialize?**

- 浅黄底目标函数：max_S |∪_{v∈S} cover(v)| − λ Σ_{v∈S} breaks(v)

> - **Utility:** failures an artifact fixes, minus correct answers it breaks.

- 约束框（橙色左边框，标题 "Selection constraints"，文字沿用用户在流程页上的写法）：

> - **Storage:** total size of the materialized views.
> - **# Tokens:** the number of tokens required for agent to read an artifact.
> - **Count:** too many artifacts can mislead the agent.

> - **Solve:** coverage has diminishing returns, so greedy works; exact ILP as reference.
> - **Open:** a task may need **several** artifacts at once, which breaks this property.
>
> Related: view selection (HRU 1996; Gupta, ICDT 1997)

**字数：** 上屏约 180 词（含公式符号和图中的 view 名），略超 150 词的目标。

**口头补充（不上 slide）：**

- 合并的例子（页面上的小图已删）：`profit_yuan`、`subsidy_yuan` 合并成 `metric_yuan`，是示意：DataClaw 上单位问题在 4 道题里各挖出一条规则，对应营业利润
  Y_EC_22（4 种名称、5 种单位）和 task_429 的政府补贴（14 个省用了 5 种单位），按第 4.3 节的纵向合并可以合成一张统一单位的表。
- 合并的三种方式（第 4.3 节）：纵向合并（同一基表、同一键，派生列取并集）、按键合并（键相同、基表不同，合并成维度表）、
  横向合并（union，不鼓励，会混入不同粒度）。合并后要重新检查不变量，并确认仍能通过各组成部分的回放用例。
- 可借鉴的合并相关工作（凭文献记忆整理，引用前需核对）：AutoAdmin 先为每条查询生成候选视图，再两两合并，合并结果作为新候选
  加回去统一选择（Agrawal、Chaudhuri、Narasayya，VLDB 2000）；index merging 合并索引，省存储但单条查询代价上升，和我们
  "清单变短但 view 更宽、更费 token"是同一种取舍（Chaudhuri、Narasayya，ICDE 1999）；relaxation-based tuning 先为每条查询
  找最理想的配置，再反复松弛（含合并视图）直到满足预算，接近我们"每道失败题先提一个产物，再合并到预算内"的流程（Bruno、
  Chaudhuri，SIGMOD 2005）。其他：DB2 Design Advisor（Zilio 等，ICAC 2004）、Data warehouse configuration（Theodoratos、Sellis，
  VLDB 1997）、MVPP（Yang、Karlapalem、Li，VLDB 1997）、多查询优化用于视图选择（Mistry 等，SIGMOD 2001）、合并后能否回答原查询
  用 view matching（Goldstein、Larson，SIGMOD 2001）检查、粒度问题对应 HRU 1996 的 data cube lattice。
- 和这些工作的区别：传统合并按查询执行代价衡量，目标是让已知负载跑得更快；我们衡量合并后还能修好多少失败、agent 读产物要花
  多少 token，而且合并后的 view 要让 agent 读得懂、选得对。
- cover(v) 是产物 v 吸收的出错片段集合，breaks(v) 是 v 在做对的题上破坏的正确查询数，λ 是惩罚系数，待定（第 4.5 节）。
- token 约束细分为两部分（第 3 节）：清单条目每道题都要读，view 只在 agent 打开时才读。
- 求解：按性价比贪心和普通贪心各做一次取较好者，配合惰性求值（CELF）；每个库的候选只有几十个，可以直接用整数规划求精确解，
  报告两者差距。互斥关系在整数规划里是一条线性约束，在贪心里是"选了一个就删掉另一个"。
- "Open" 的例子：DataClaw task_429 同时需要单位统一和指标别名两个产物，缺一不可。这种"必须同时具备"的关系不满足边际收益
  递减，贪心的近似保证不再成立，对应 Gupta ICDT 1997 的 AND-OR 视图图。
- 效用的三种粒度（整题执行正确率、gold SQL 能否改写成使用产物、出错片段是否被吸收）见第 5 节；评测噪声见第 4.1 节。

## 8. 第 6 页：benchmark（`agent_view_benchmark.html`）

（2026-10-21 第二版已做，页面与下面的文字一致。加入这一页后总页数改为 6，前 5 页右上角页码同步改为 "/ 6"。第一版用三张卡片
（BIRD、Beaver 标 PoC，DataClawBench 标 Later）加一个理由框；第二版按用户要求不用卡片，改为两段分点文字。）

**标题：** Benchmarks: Text2SQL First, Then Data Agents。右上角：Proposal · 6 / 6。

**这页要传达的一句话：** 可用的 benchmark 有 text2sql 的 BIRD、Beaver 和 data agent 的 DataClawBench；PoC 阶段先用 BIRD 和 Beaver，
因为它们每道题都有 gold SQL，可以直接从 gold SQL 提出 view，快速验证 view 能不能给 agent 带来收益。

**版式：** 两段分点文字，上下排列、垂直居中。第一段蓝色标题，第二段绿色标题，要点里的关键词用标题同色加粗。

**第一段：Candidate benchmarks**

> - **Text2SQL:** BIRD (mini-dev: 500 questions over 11 databases; mostly solved by a plain agent) and Beaver (enterprise
>   data warehouses, e.g. 3,312 questions over 97 tables; much harder).
> - **Data agent:** DataClawBench (492 multi-step analysis tasks over raw CSV and JSON files; no gold SQL, graded by
>   milestones).

**第二段：PoC: start with BIRD and Beaver**

> - Every question has a **ground-truth SQL**, so views can be proposed directly from the gold SQL of training questions.
> - This lets us **quickly verify** whether the views help the agent before building the full pipeline.
> - DataClawBench comes **later**, with views proposed from agent failures.

**字数：** 上屏约 110 词。

**口头补充（不上 slide）：**

- 数字来源（第 6 节，实测）：BIRD mini-dev 500 题、11 个库（`data/minidev/MINIDEV/`）；Beaver dw_filtered 3,312 题、dw 库 97 张表，另有
  dw_real 121、nova 1,053、neutron 1,017 题（`~/semantic-catalog/data/beaver/`）；DataClaw 492 道题（`~/DataClaw/tasks`），数据目录
  `~/DataClaw/assets/database` 下是 18 个 CSV 和 1 个 JSON 翻译文件。
- "BIRD 普通 agent 大多能做对"和"Beaver 错误多"是用户的判断，本地都还没有批量运行结果（第 6.1 节），需要先各跑一批量出错误率。
- 从 gold SQL 提出 view 相当于第 4.2 节的"从负载出发"，PoC 阶段先用它代替"从失败出发"，验证 view 本身有没有用；之后再换成从
  agent 失败出发。
- 只能用训练题的 gold SQL 提 view，测试题的 gold SQL 不能参与，否则会把答案泄漏进 view。Beaver 要按相似题分组切分（第 4.1 节）。
- 验证方式：同一批测试题上，agent 带 view 和不带 view 各跑 2 到 3 次，比较执行正确率（EX）；BIRD 上主要看 view 会不会把原本
  做对的题改错。
- Beaver 的 `sub_sqls`、`join_keys` 可直接用来提 view（预先连接好的视图、子查询物化），见第 6.1 节。
- DataClawBench 放到后面：没有 gold SQL，view 只能从 agent 失败出发提出，效用用 milestone 计。

## 9. 修改记录

- 2026-10-20：新增第 10 节 slides 计划（4 页：动机、产物、流程、研究问题），修改记录改为第 11 节。
- 2026-10-20：slides 路径改为 `docs/presentations/proposal/`；做出第 1 页动机页，第 10.3 节改为与页面一致的定稿文字。
- 2026-10-20：slides 改为全英文；动机页拆成两页（动机页：上方问题，左栏已有做法，右栏我们的想法和区别；
  示例页单独成页，尚未做），总页数改为 5，第 10 节各页重新编号。
- 2026-10-20：动机页精简到约 135 词（每页目标 150 词左右），细节移到口头补充；底部加研究问题一行。
- 2026-10-20：动机页改为逐行对比（Generates / Modifies / Keeps / Helps by），突出"已有方法改 context、
  我们改数据"；标题改为 Motivation: Change the Data, Not the Context；问题框删去例子（用户直接改页面）。
- 2026-10-20：做出第 2 页示例页，用 task_116（英文公司名对不上中文记录）；第 10.4 节改为定稿方案。
- 2026-10-20：示例页改为强调两个数据源之间的隐藏联系：标题改为 A Hidden Link Between Two Sources，两个数据源
  标为 Source 1/2、相同中文名橙色高亮、中间加"从未发现的联系"虚线，结论框改为 Missed link / Link made explicit。
- 2026-10-20：动机页由对比表改回两栏文字（用户认为表格过于简略），每栏三条句子左右逐条对应。
- 2026-10-20：同步用户对动机页的直接修改；做出第 3 页产物页，第 10.5 节改为定稿方案。
- 2026-10-20：产物页改为先讲清单、再讲 view 产物、最后讲 agent 自己选择产物；标题改为 The Manifest and View Artifacts。
- 2026-10-20：做出第 4 页流程页，第 10.6 节改为定稿方案。
- 2026-10-20：流程页预算改为一段文字，卡片做法缩成一句，删掉 Out 产出。
- 2026-10-20：流程页预算由一段文字改为三条列表。
- 2026-10-20：同步用户对流程页的直接修改（删掉 Score 阶段，效用问题并入 Select，预算标题改为 Selection constraints）；
  流程页改为 5 列、重新编号，约束列表移出；做出第 5 页研究问题页 `agent_view_merge_select.html`（合并与选择），第 10.6、10.7 节改为定稿方案。
- 2026-10-20：同步用户对研究问题页 Merge 栏的直接修改；Merge 栏加一条 "Existing work"（可借鉴 AutoAdmin 等物理设计工具的合并做法），
  Related 补成三篇；口头补充加入合并相关工作列表和区别。
- 2026-10-20：做出合订页 `agent_view_report.html`，用 iframe 按顺序串起 5 页（动机、示例、产物、流程、合并与选择）。
- 2026-10-21：同步用户对产物页的直接修改（标题、删流程条、第三条要点）；删掉 view 产物的 Description 部分，右栏加两层存储结构示意图（产物层与原数据集，agent 同时读两层），要点压缩，第 10.5 节改为定稿方案。
- 2026-10-21：同步用户对示例页的直接修改（轨迹改写，删结论框和右栏 SQL）；示例页 agent 轨迹字号调大。
- 2026-10-21：同步用户对流程页 Run、Propose 做法的直接修改；Propose 阶段改为研究问题（How to propose?），括线覆盖第 2 到 4 阶段。
- 2026-10-21：新增第 6 页 benchmark 页（BIRD、Beaver 作 PoC，DataClawBench 放后面），新增第 10.8 节；总页数改为 6，各页页码和合订页同步更新。
- 2026-10-21：benchmark 页去掉卡片和理由框，改为两段分点文字（Candidate benchmarks、PoC: start with BIRD and Beaver）。
- 2026-10-21：做出无 iframe 的合订页 `agent_view_report_final.html`，把 6 个单页的内容和样式直接拼进一个文件（各页样式加作用域），内容与 `agent_view_report.html` 相同。
- 2026-10-21：本计划从 `agent_view.md` 第 10 节拎出，成为独立文档；原 10.1 到 10.8 改为本文档第 1 到 8 节，slides 相关的修改记录一并移入。
- 2026-10-21：示例页用同一个例子加入改名：题目的 "listing boards" 和原表列名 `plate` 紫色对照，产物里改名为 `listing_board`；产物页的 view 表和建表 SQL 同步改名；同步用户对示例页标题和产物页要点的直接修改；重新生成 `agent_view_report_final.html`。
