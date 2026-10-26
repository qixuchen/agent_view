# 交接文档：失败驱动的数据产物（agent view）

写于 2026-10-23。本工作原先在 `~/TK-Boost`（分支 `dataclaw_recursive_update`）里进行，现迁到
`~/agent_view` 继续。新对话开始时，请先读本文件，再读 `docs/agent_view.md` 和
`docs/agent_view_slides.md`。

## 1. 一句话概括

现有方案（TK-Boost、MIRA 等）对比 agent 的 SQL 和 ground truth，把"数据理解不到位"的地方挖成
文本知识，存起来，之后像 RAG 一样检索回 agent 的 context。我们的方案是"改数据，不改 context"：
从失败轨迹里提出 view 产物（派生表加声明式 SQL），原始数据不动；再写一份清单（manifest）列出所有
产物，agent 读清单后自己决定打开哪个。

流程分 5 个阶段：Run、Propose、Merge、Select、Test。其中 Propose（怎么提出 view）、Merge（怎么合并
重叠的 view）、Select（在预算下选哪些物化）是研究问题。

## 2. 目录里的文件

| 路径 | 内容 |
|---|---|
| `docs/agent_view.md` | 设计文档。第 1 到 9 节是设计，第 10 节是最相关论文，第 11 节是修改记录 |
| `docs/agent_view_slides.md` | slides 计划：文件位置、样式约定、每页内容、slides 修改记录 |
| `slides/agent_view_*.html` | 6 页 slides，顺序是 motivation、example、artifact、pipeline、merge_select、benchmark |
| `slides/agent_view_report.html` | 用 iframe 把 6 页串起来，按相对路径引用同目录的 6 个文件 |
| `slides/agent_view_report_final.html` | 6 页静态拼接版，没有链接。**目前已过期**，见第 6 节 |
| `papers/` | 最相关论文、TK-Boost、MIRA 的 PDF |
| `.cursor/rules/explaining.mdc` | 回复规则：中文、先解释代码再引用、说明结论怎么得出的 |

注意：两份文档里写的文件路径还是 TK-Boost 下的旧路径，例如 `docs/presentations/proposal/`、
`docs/dataclaw/`，需要改成本目录的 `slides/`、`docs/`。

原地引用、没有拷过来的数据：

- DataClaw 运行结果：`~/DataClaw/output_train_a` 等；题目在 `~/DataClaw/tasks`（492 道）。
- Beaver 数据：`~/semantic-catalog/data/beaver/`（详见 `docs/agent_view.md` 第 6.1 节）。
- BIRD mini-dev：`~/TK-Boost/data/minidev/MINIDEV/`。
- 原论文库：`~/TK-Boost/docs/insight/papers/`。
- 原对话完整记录（7.8 MB，jsonl，每行一个事件）：
  `~/.cursor/projects/home-qchenax-TK-Boost/agent-transcripts/d7f3bbe7-a5bf-4da4-bb72-958f945fb930/d7f3bbe7-a5bf-4da4-bb72-958f945fb930.jsonl`。
  需要查旧细节时按关键词搜，不要从头读。

## 3. Slides 现状与约定

6 页的内容以 HTML 文件为准，用户经常直接改 HTML。修改前一定先读当前文件，保留用户的改动，并把
改动同步进 `docs/agent_view_slides.md`。用户在 10/23 14:19 改过 motivation、example、artifact、
pipeline、benchmark 五页，这些改动还没同步进 slides 文档，下次动 slides 前先比对一遍。

各页要点（截至 10/21 的记录）：

1. **motivation**：现有方案存文本知识再检索，我们改成提供 view 产物。
2. **example**（Motivating Example）：问题里有 "listing boards"。左栏是原数据：英文名在翻译 JSON 里、
   板块在 `company_profile.csv` 的 `plate` 列（真实列名，值有 主板 4,882、创业板 1,351、科创板 499、
   北交所 162 等），说明问题说的是 "listing board"，列名却叫 `plate`，agent 轨迹失败。右栏是
   `company_dim` view，把 `plate` 改名为 `listing_board`，轨迹成功。
3. **artifact**：左栏是清单加一个 view 产物（表和 SQL `p.plate AS listing_board`）；右栏是两层存储
   示意图（上层是我们创建的产物层，下层是原数据集，agent 不改），以及用户改过的要点。
4. **pipeline**：5 个阶段，Propose、Merge、Select 用橙色标为研究问题，括号"Research questions
   (next page)"横跨第 2 到 5 列。
5. **merge_select**：左栏 Propose & Merge（每题找 view、view 之间重叠、合并候选放回候选池且和
   组成部分互斥、可借鉴 AutoAdmin）；右栏 Select（效用、选择约束、用贪心或 ILP 求解）。
6. **benchmark**：Text2SQL 用 BIRD 和 Beaver（更难），data agent 用 DataClawBench；PoC 阶段用
   BIRD 和 Beaver，因为可以基于 gold SQL 提出 view，快速验证 view 对 agent 有没有收益。

样式约定：1280×720；主色 `#0f5e9c`；研究问题橙色 `#b45309`；PoC 绿色 `#047857`；改名紫色
`#7c3aed`；字体 "Segoe UI"。用户要求：不要用卡片式小板子，用文字；文字精简；例子用真实数据。

截图方法：用 Windows 侧的 Chrome headless 截图（WSL 沙箱里要用不受限权限运行），每次用新文件名，
避免看到旧缓存。

## 4. 设计要点（详见 `docs/agent_view.md`）

- **Select 的约束**：存储上限、token 上限（清单的 token 每题都付，view 的 token 只在打开时付）、
  产物数 K。效用等于修好的失败数，加上省下的步数，减去改坏的题数。
- **Merge** 参考 AutoAdmin 一类工作：AutoAdmin（VLDB 2000）、index merging（ICDE 1999）、
  relaxation-based tuning（SIGMOD 2005）。
- **最相关论文**：Zhang, Miao, Wang, "The Case for Text-to-SQL Friendly Logical Database Design"
  （arXiv 2606.03145），记录在设计文档第 10 节。
  - 三个算子：+A（用频繁项集从 gold SQL 的表集合里挖连接 view）、+P（分区）、+R（改名，做成 1:1 view）。
  - 结果：在 BIRD-Union 和 Spider-Union 上最多 +4.2 EX；11 个库里 8 个变好、2 个变差；74 题变对、
    42 题变错。论文的 future work 正是"动态、考虑成本的 view 物化"。
  - 和我们的区别：它按整个题目集合挖 view，把相关 view 全部给出，没有预算，是固定流水线而不是 agent。

## 5. 最近两轮讨论的结论（尚未写进任何文档）

### 5.1 为什么存 view 比存文本知识好，即使更占空间

**先换掉比较的维度。** view 可以只存 SQL 定义（`CREATE VIEW`），不占存储；只在计算贵或查得频繁时
才物化，存储代价可以逐个产物决定，由存储上限控制。知识方案的成本不在磁盘上，而在每道题都要付的
检索、context token、以及 agent 每次都要重写一遍修正。应该比的是：同样的 agent token 预算下，谁的
正确率更高、步数更少、改坏的题更少，磁盘占用作为附带约束报告。

**agent 怎么探库（实测，DataClaw train_a 第一轮 123 条运行、2,558 次工具调用）：**

- 工具：exec 2,273 次（89%）、read 228 次、web 56 次。
- 按用途分：grep 按关键词搜行 848 次（33%）；head 或 sed 预览约 740 次（29%）；ls 或 find 列目录
  341 次（13%）；读整个文件 208 次（8%）；awk 162 次（6%）；python 或 node 脚本 119 次（5%）；
  web 搜索 56 次（2%）。
- 脚本失败率 45%（119 次里 53 次），其中 44 次是找不到 python。
- 每条运行调用次数中位数 19，最多 62。
- 位置分布：前 3 次调用里 73% 是列目录；第 4 到 10 次里 45% 是预览、29% 是 grep；第 11 次以后
  grep 占 46%，awk 加脚本占 19%。
- 123 条里 110 条用过 grep，第一次 grep 出现在第 7 次调用（中位数）。grep 的关键词：中文 726 次、
  英文 84 次、数字编码 43 次；跨文件 grep 只有 32 次（1.3%）。
- 翻译 JSON 只在 47 条运行里被碰过（76 条从没碰过）。
- 有 26 次用 `awk 'NR==1'` 枚举表头；读文件出错的例子包括猜测不存在的 `index.json`、`policies.json`。
- 数据库没有 schema 文档：18 个 CSV、1 个 JSON。

**由此得出的论点：**

1. **知识按题目文本检索，误解却跟着数据走。** 换一种问法但碰到同一列的新题，可能检索不到知识。
   agent 的探库路径全在数据上（列目录、预览、grep），view 放在数据目录里，列目录能看到、grep 能
   搜到，不依赖检索命中。可写成 "Retrieval is keyed by question text; misconceptions are keyed by data."
2. **agent 发现不了的东西，知识帮不上。** task_116 里 agent 从没打开 `company_profile`。带英文名列的
   `company_dim` 能让 agent 最常用的"拿名字 grep"直接命中。
3. **检索到了也要每次重新执行修正。** 例如单位统一要覆盖 5 种单位，每题重写一次都可能写错（脚本失败率
   45%）。view 离线写一次、验证一次，正确查询变成最简单的查询。可写成
   "Knowledge tells the agent what to do every time; a view does it once."
4. **知识不去重、不组合。** 单位问题在 4 道题里各被挖成一条独立规则。task_429 同时需要单位统一和指标
   别名（Y_EC_22 有 4 种名字、5 种单位，单位换算后省份排名翻转），合并成一张 `metric_yuan` 就一次解决，
   这就是 Merge 阶段的价值。
5. **知识没法验证，view 可以。** 设计文档第 8 节记录 task_458 挖出的规则理由是错的；view 可在全表上
   检查不变量、回放原来做错的查询。
6. **检索本身脆弱。** TK-Boost 表 5（GPT-4.1）：基线 27.7%，全部知识直接给 35.6%，按子查询检索后纠正
   44.6%，效果高度依赖检索质量。另外 init20 不加任何规则重跑，原本做错的 20 题里也有 5 题变对，
   说明单次比较噪声大。

**要承认 view 不占优的情况：** 题意理解错误（task_183）、无法写成数据变换的一次性事实或常识、
探库成本本来就低的小库、view 也可能误导（上述论文有 42 题变差）。定位是互补：view 负责反复出现、
能写成可执行变换的数据层误解，知识负责其余部分。

**证明它的实验：**

1. 等 token 预算对比知识检索和"清单加 view"，报告正确率、步数、token、改坏率，存储分虚拟 view 和
   物化 view 单独报告。
2. 按"测试题和训练题的文本相似度"分组，预期知识检索在低相似、但碰到同一批表和列的题上明显下降。
3. 失败归因：知识方案分"没检索到、检索到没用、用错"；view 方案分"没打开、打开用错、正确"。
4. oracle 对照：直接给正确知识，和 view 比，区分"免检索"和"免重复执行"两部分优势。
5. 探库效率：第一次针对性查询之前的步数和总步数是否下降。

### 5.2 Beaver 还是 BIRD 更容易看出 view 的效果

结论：Beaver 更容易看出效果，BIRD 适合作对照。这与设计文档第 6 节一致（Beaver 为主平台，BIRD
mini-dev 为备选）。

- Beaver 的优势：来自 MIT 真实企业数据仓库，表多（dw 有 97 张表），命名多用缩写和内部编码，和问题
  里的自然语言差得远，改名 view 和预连接 view 都有用武之地；基线准确率低，提升空间大；`join_keys`
  标注了正确连接键，"预先连接好的视图"是天然的产物。
- BIRD 的劣势：evidence 字段相当于现成的知识注入，会冲淡 view 的边际收益；库小、连接简单，探库
  成本低；基线高，剩下的错误里标注噪声和题意歧义比例大；上述论文也要合库成 BIRD-Union 才看到效果。
- 上一轮口头回答里有两处说法与设计文档第 6.1 节的实测不符，以文档为准：
  - 本地有 Beaver 数据，在 `~/semantic-catalog/data/beaver/`，不是"仓库里没有"。
  - Beaver 也有和 BIRD evidence 类似的 `domain_knowledge` 字段，覆盖 45% 到 77% 的题，不是"没有现成
    提示"。因此 Beaver 上也要分"提供"和"不提供" `domain_knowledge` 两种设定，以不提供为主实验。
  - 另外，每题涉及表数的中位数是 3 到 4（dw_real 为 4），连接数并不夸张，Beaver 的难点更多在表多和
    命名晦涩上。
- Beaver 的风险：基线太低可能有地板效应，要同时报告修好的题数和步数；dw_filtered 里大量题是同一模板
  生成的相似题，切分时必须按相似题分组，否则训练题和测试题重合会高估效果；PoC 前先统计训练题和测试题
  在表和列上的重合度，这决定了效果上限；nova 的 dump 有 2.0 GB，物化成本真实，优先用虚拟 view。
- 建议安排：Beaver 为主实验；BIRD 作对照，分"有 evidence"和"去掉 evidence"两种设定跑；预先写下
  可检验的预测：view 的增益随 gold SQL 的表数和 schema 大小上升。

## 6. 待办

1. **重新生成 `slides/agent_view_report_final.html`。** 它是 10/21 17:28 生成的，之后 5 页在 10/23
   被改过。当时的生成脚本是命令行里临时跑的 Python，没存文件，做法是：按顺序读 6 个 HTML，提取每页
   的 `<style>` 和 `<section class="slide">...</section>`；把每个 CSS 选择器加上作用域 `.report-page-N`
   （`:root`、`html`、`body` 换成作用域类本身，`*` 换成 `.report-page-N *`）；每页包成
   `<div class="page-sheet report-page-N"><style>…</style>section</div>`，页面背景灰色，每页 1280×720。
   建议这次存成 `slides/build_report.py`。每次改完 slides 都要重新生成。
2. 把两份文档里的旧路径改成本目录路径。
3. 把用户 10/23 对 5 页 slides 的改动同步进 `docs/agent_view_slides.md`。
4. 视需要把第 5.1 节（view 对比文本知识的论证）写进设计文档第 1 节和 motivation 页，把第 5.2 节写进
   设计文档第 6 节和 benchmark 页。
5. 设计文档第 9 节的待定问题（Beaver 基线错误率、相似题分组、运行环境、清单放置、λ、预算数值、
   产物 DSL、改名 view、BIRD-Union 设定）。

## 7. 工作约定

- 始终用中文回复，遵守 `.cursor/rules/explaining.mdc`。
- 不打印、不提交任何密钥。
- 只在用户要求时 commit 或 push。真实 LLM 调用由用户自己跑。
- 改代码用严格 TDD（先写失败测试，再最小实现，再重构）；用户说"只改文档"时不碰代码。
- 原 TK-Boost 仓库里有别人未提交的改动（`src/agents/cte_refiner.py`、`src/agents/sql_agent_runner.py`），
  不要动。
