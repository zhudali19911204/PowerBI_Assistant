# 二期：Power Query（M / 数据清洗）助手 — 设计文档

> 版本 v0.3 ｜ 更新日期 2026-06-26（初稿 2026-06-25）｜ 二期第一支柱：数据清洗（Power Query / M）
> 配套：总方案见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)；背景记忆见 `memory/`（`mquery-*`）。

---

## 0. 现状速览（2026-06-26 重大修正）

真机反复崩溃逼出一个硬结论，二期定位因此**从"live 实跑验证闭环"收缩为"只读 + 静态校验"**：

- **⛔ 实跑验证已移除**：M 的实跑验证靠"TOM 建临时表→刷新→回读"。但 Desktop 打开时，这张临时表会被同步进 Desktop 的 Mashup 文档（`Section1`），而我们用 TOM 删除**只删得掉引擎那份、删不掉 Desktop 那份** → 留下幽灵查询 `__pbi_ai_mq_probe` → 污染查询导航器 → 用户一点查询就崩（`NullReferenceException @ QueriesNavigatorModelBase.IsQueryGroupNode`）。**在打开的 Desktop 上，任何 TOM 写操作（写回 OR 验证探针）都不安全。**
- **⛔ 写回已移除**：同一根因（见 §2.3）。
- **✅ 助手现状 = 只读 + 静态**：读现有 M（grounded）→ 生成 → 静态 lint → 用户复制到「高级编辑器」→ **在 Desktop 应用时由 Desktop 真正验证**。所有只读（DMV `SELECT`）操作安全：连接、同步、读列。
- **对比**：一期 DAX 验证用 `EVALUATE`（只读查询、不建表）→ **安全、不受影响、继续可用**。M 没有这种端点，这正是二期与一期的本质差异。

**三个痛点的真实状态**（详见 §5）：

| 痛点 | 状态 |
|---|---|
| 痛点1 增量补片段 + Desktop 同步 | **基本已建**（🔄 同步按钮 + 增量 prompt 已上线；"当前工作 M 基线/步骤链"未形式化） |
| 痛点2 多查询合并/追加 | 未做 |
| 痛点3 目标导向清洗 | **搁置**——自动校验闭环依赖已移除的探针，不可行（用户已确认先不做） |

> 下文 §2.2 的探针机制、§5 各痛点方案，保留作设计记录；凡涉及"实跑验证"的，**以本节 §0 为准**。

## 1. 目标与定位

把一期 DAX 助手验证过的核心理念——**"生成 → 静态校验 → 实跑验证 → 修复" 闭环 + Grounding + （可行时）写回**——复制到 Power BI 四大痛点的第二个：**数据清洗（Power Query / M）**。

延续一期三原则：

1. **Grounding 优先**：M 只能引用真实存在的查询/列/步骤，禁止臆造。
2. **能力插件化**：作为新的 `MQueryCapability` 注册，UI 自动渲染成「Power Query 助手」标签页，零框架改动。
3. **真验证而非只建议**：M 必须经过真实引擎验证，而不是静态自审。

原定路径（2026-06-25 确认）：读现有查询 → 在其 M 之上 grounded 生成 → **真实刷新实跑验证** → 应用结果。**但实跑验证经真机证明会崩 Desktop、已移除（见 §0/§2.2）**，故第 3 条原则"真验证"在 Desktop 上对 M 不成立——降级为"静态校验 + 用户在 Desktop 应用时验证"，并诚实标注"未实跑"。这是真机逼出的结果，符合"实跑优先、不夸大"的项目精神。

---

## 2. 关键技术难点与机制（已验证）

### 2.1 难点：M 没有 `EVALUATE` 那样的查询端点

一期 DAX 的实跑验证靠 ADOMD 把 `EVALUATE` 发给本地引擎拿真值。但 **Power Query 的 M（Mashup）引擎没有独立可查询端点**——你无法"把一段 M 发过去就拿到结果"。因此 M 的"实跑验证"只能用更重的**刷新回环**。

### 2.2 机制：临时表刷新回环 + `Table.Schema` 探针（⛔ 已移除，仅作记录）

> **此机制已停用。** 它在**独立脚本**里跑通了（spike + 真 LLM 端到端，0 修复），但**在打开的 Desktop 上会泄漏临时表进 Mashup 文档并崩溃 Desktop**（见 §0）。`MQueryEvaluator.evaluate_m` 仍在代码里但**不再被任何 UI 调用**；助手改为只读+静态。**切勿对打开的 Desktop 重新启用它。** 下面记录其原理，供理解为何 M 验证这么难。

流程（`mquery/live_eval.py::MQueryEvaluator.evaluate_m`，现已弃用）：

1. 用 TOM 新建**唯一命名临时表** `__pbi_ai_mq_probe`，其 `MPartitionSource.Expression` 包住候选 M；
2. `table.RequestRefresh(RefreshType.Full)` → `model.SaveChanges()` —— **这一步真正调用 Mashup 引擎跑真实数据源**；
3. 用 ADOMD `EVALUATE` 回读结果；
4. `finally` 里删除临时表 + `SaveChanges()`（隔离、用完即删，绝不碰用户真实表）。

**两个非显而易见的坑（决定了设计）：**

- **裸 M 分区没有列。** 经 TOM 加的 M（导入）分区不会自动推断列（Desktop 自己建查询时才做 schema 检测）。所以裸 `EVALUATE '__pbi_ai_mq_probe'` 会报 `表"…"没有任何列`。
  **解法**：让探针返回 `Table.Schema(candidate)`——它的输出形状是**固定已知**的（列名 Name/TypeName/Kind…）。预先声明这几列，刷新后 `EVALUATE` 就把候选 M 的**输出 schema 当数据行**读回来（列名 + M 类型）。回读 key 形如 `'__pbi_ai_mq_probe[Name]'`。
- **坏 M 在 `SaveChanges()` 抛错，而非 EVALUATE。** 异常是 `OperationException`，文本里包着真实 Mashup 报错，如 `…Error returned: '…[Expression.Error] 找不到表的"X"列。'`。`_clean_m_error` 提取 `[Expression.Error]/[DataFormat.Error]/[DataSource.Error]` 核心——正是修复循环要喂回 LLM 的输入。成功/验证失败都置 `run_verified=True`。

### 2.3 写回限制：M 不能回写到打开的 Desktop（已证实，已移除）

> **结论：度量值/计算表可写回，Power Query(M) 不可。**

通过外部连接（TOM `SaveChanges`）改写一个查询的 M，会让 **Power BI Desktop 本身崩溃**：`System.NullReferenceException` in `Microsoft.Mashup.Client.UI…Ux.Navigator.QueriesNavigatorModelBase.IsQueryGroupNode`（Frown 报告确认，Store 版 2.155.756.0）。原因：**在打开的 Desktop 上用外部 XMLA 编辑 Power Query 不被支持**——Desktop 把 M 的权威副本存在自己的 Mashup 文档里，外部一改引擎侧，它的查询导航层就抛空引用。

崩溃堆栈的组件名 `Microsoft.Mashup.Client.UI` 恰好证明了对比：**度量值/计算表写回是纯模型对象、不经过 Mashup UI，所以不受此 bug 影响、安全**（一期写回继续可用）。

**产品取舍**：移除 M 的一键写回（`write_m_partition` 已删除），改为**把实跑验证过的 M 交给用户复制 → 粘到 Power Query「高级编辑器」**：`主页 → 转换数据 → 选中查询 → 高级编辑器 → 粘贴 → 完成 → 关闭并应用`。失败的写回尝试不会持久化、不会损坏模型。

详见 `memory/mquery-refresh-verification.md`。

---

## 3. 架构与已建成内容

### 3.1 复用四个横切抽象

| 抽象 | 一期实现 | 二期做法 |
|------|---------|---------|
| `LLMProvider` | `llm/` | 不动，直接复用 |
| `ContextSource` / `ModelContext` | `context/live_source.py`、`context/base.py` | **扩展**：读 `TMSCHEMA_PARTITIONS`（每表现有 M）+ `TMSCHEMA_EXPRESSIONS`（参数/共享查询）；`ModelContext` 加 `table_queries`/`shared_expressions` + `serialize_query_for_prompt()` |
| `Capability` / `Action` | `dax/capability.py` + `core/registry.py` | **新增** `mquery/capability.py`（`MQueryCapability` / `CleanAction`），`ensure_capabilities()` 里 `register()` |
| `Artifact` / Evaluator | `dax/artifact.py`、`dax/live_eval.py` | **新增** `MScriptArtifact`（静态 lint）+ `MQueryEvaluator`（刷新回环） |
| 知识双资产 | `.claude/skills/dax-expert/` ↔ `dax/prompts.py` | **新增** `.claude/skills/mquery-expert/` ↔ `mquery/prompts.py`（先改 skill 再回写） |
| UI | `components.py::render_capabilities` 自动按 tab 渲染 | **扩展** `_render_capability` 按 `cap.id` 分派，加 `_render_mquery_chat` |

### 3.2 目录结构（镜像 `dax/`）

```
powerbi_ai_assistant/mquery/
├── __init__.py        公开 API
├── capability.py      MQueryCapability + CleanAction（生成→静态→实跑→修复 编排）
├── generate.py        解析 LLM 的 ```powerquery / ```m 代码块
├── artifact.py        MScriptArtifact + 静态 lint（括号/引号、let/in、#"..." grounding）
├── live_eval.py       MQueryEvaluator（刷新回环 + Table.Schema 回读）
└── prompts.py         M_SYSTEM_PROMPT + build_clean/repair/chat 提示（压缩自 skill）

.claude/skills/mquery-expert/
├── SKILL.md           权威知识库
├── references/        m-language-essentials / cleaning-recipes / pitfalls
└── evals/evals.json   3 个基准清洗场景
```

### 3.3 已建成（截至 2026-06-26）

- 读现有 M（`live_source` 读 `TMSCHEMA_PARTITIONS/EXPRESSIONS/QUERY_GROUPS` + `ModelContext.table_queries/shared_expressions/query_folders`）；
- **grounded 生成 + 静态 lint**（`MScriptArtifact`：括号/引号、let/in、`#"..."` 步骤/查询 grounding）；**实跑验证已移除**（§0），生成卡片标注"✓ 静态校验通过（未实跑，应用后由 Desktop 验证）"；
- UI「Power Query 助手」标签页（`_render_mquery_chat`，复制到高级编辑器；**无写回、无探针**）；
- **增量"补片段"对话**（痛点1）：chat prompt 改为"用户为主、AI 补一步"框架（`build_chat_system_prompt`）；侧栏 **「🔄 同步」** 按钮（`_resync_model`，只读重读已应用 M）；
- **侧栏连接后分两块**：上「Power Pivot · 模型」（表与列 + 度量值）、下「Power Query · 查询」（按查询组文件夹分组列出已加载查询，列数 + M 行数；**点查询=设为清洗目标并展开列**；点列名插入需求框；表/列视觉分层）。仅"已加载到模型"的**标量列**可见——Binary/Record（如 `Content`）等非加载列引擎不存、不显示（曾尝试"展开即探"补全，因探针崩 Desktop 撤销）；
- 知识库 skill（`mquery-expert`：SKILL + 3 references + evals）；
- 单测 `tests/test_mquery.py`（13），全仓 67 passed、mypy clean。

---

## 4. 试用反馈：三个痛点

用户试用后提出（2026-06-25）：

1. **说不清需求**：无法一次准确描述，想一步步拆分对话；但有些操作自己在 Desktop 做更快——有点矛盾。
2. **只能选一张表**：有时要选多张表做合并/追加。
3. **想指定结果**：能否给一个想要的清洗结果，AI 直接清洗到位。

用户已明确互动偏好：**「我为主 + AI 补难点」**——自己在 Power Query 编辑器里点为主，只在卡壳（写不出某段 M / 想不起函数）时找 AI 要那一步。**不希望助手接管整条查询。**

---

## 5. 解决方案

三个痛点指向同一升级方向：把助手从"一次性整段生成"变成"**人机交替的补片段副手 + 多输入 + 目标导向校准**"。

### 5.1 痛点1 → 增量「补片段」对话（按"我为主 + AI 补难点"定位）—— **基本已建**

助手定位 = **按需补片段的副手**，不接管整条查询。**已上线**：增量 prompt 框架 + 「🔄 同步」按钮。

**典型流程**
1. 用户在 Power Query 编辑器点点点做到某处 → **应用**（见下方"数据同步机制"，关键是"应用"而非"保存"）；
2. 回助手点 **「🔄 同步」** → 重新读取该查询**当前已应用的 M** 作上下文；
3. 用户只描述卡住的那一步；
4. AI 给出**那一步的 M** + 完整更新后的 `let…in`（**静态校验**；实跑验证已移除，应用后由 Desktop 验证）；
5. 用户粘回 Desktop 继续。

> 未形式化的部分：「当前工作 M 基线」对象、可视步骤链、输出形态(i)/(ii)的显式切换——当前靠"同步即拉最新 M"+"prompt 同时给新步骤和完整查询"近似覆盖。

#### 数据同步机制（重点澄清，之前写得不清楚）

助手通过 DMV（`TMSCHEMA_PARTITIONS.QueryDefinition`）读的是**引擎里"已应用"的 M**，不是 Power Query 编辑器里"待应用"的草稿。两件事必须分清：

- **「应用」≠「保存」。** 在 Power Query 编辑器改完步骤后，必须把改动**应用**到模型/引擎，助手才看得到：
  - 点「关闭并应用」或「应用」，**或**按 `Ctrl+S` 保存时弹出"未应用的查询中有挂起的更改，是否要应用？"——选 **「应用」**。
  - 选 **「稍后应用」**：文件存了，但改动仍挂起、**没进引擎** → 助手读到的还是旧版本。
  - 这不是为助手特意多做的步骤——"应用"本来就是让查询改动生效、回到报表的常规操作。
- **助手不会自动刷新。** 模型是在**连接那一刻**读进来缓存的。用户在 Desktop「应用」后，助手要**重新读一次**才更新：
  - 当前版本：再点一次侧栏 **「🔌 连接 Power BI Desktop」**（会重新读取整个模型）即等效；
  - 规划中的 **「🔄 从 Desktop 同步」** 按钮 = 不走扫描、一键重读当前查询，待实现。
- **时序提醒**：「应用」会触发受影响表**重新刷新数据**（从 SharePoint/Excel 拉，可能耗时几秒~几十秒）；但查询的 **M 结构是立即更新**的，助手要读的就是 M，不必等数据刷完。

> 一句话流程：**Desktop 改查询 → 保存弹窗点「应用」→ 回助手重读（现点"连接"，将来点"同步"）→ 看到最新 Power Query。**

**关键设计**
- 「从 Desktop 同步」从可选变**核心**：用户大部分步骤自己做，AI 必须随时基于其最新真实状态。
- 维护「当前工作 M」基线（起始 = 现有 M，同步/采纳后更新）；可显示当前步骤链。
- 输出形态**二选一**（待定）：(i) 只给新增的那一步/表达式（贴到对应位置，最贴合"我为主"）；(ii) 给完整 `let…in`（整段替换，省找插入点）。

**工作量**：中（chat 状态模型 + 同步 + 步骤链）。

### 5.2 痛点2 → 多查询输入（主查询 + 参与查询）

- "要清洗的查询" 从单选改为：一个**主查询** + 可多选的**参与查询**（合并/追加用）。
- grounding 注入**所有所选查询的"现有 M + 输出列"**（当前只给主表列、其它仅列名）——AI 才能正确挑连接键、对齐追加列。
- 生成的 M 用 `#"其它查询"` 引用它们（静态校验即可——引用名在 grounding 里能查；实跑验证已移除）。
- 输出是新的合并查询（粘贴为新查询，或替换主查询）。

**工作量**：小～中（UI 多选 + grounding 扩展）。**未做，性价比最高，是后续首选。**

### 5.3 痛点3 → 目标导向清洗 —— **搁置（自动闭环不可行）**

原设想复用 DAX「校准式生成」：用户给"标准答案"，AI 反推 M，**实跑刷新→回读实际输出→与目标比对→迭代到匹配**。

**但这个闭环依赖已移除的探针**（实跑刷新回读 = 那个会崩 Desktop 的临时表机制，§0）。M 没有 `EVALUATE` 那种只读端点，所以**全自动"校验到匹配"在 Desktop 上做不了**。

讨论过的安全替代（**用户已选择先不做**，记录备查）：

- **人在环目标校验**：定目标 → AI 生成 → 用户在 Desktop 应用 → 点同步 → 助手用**只读 DMV** 读回实际列、与目标比对、给差异反馈 → AI 再改。真验证、安全（无探针）、契合"我为主"；代价是每轮手动应用一次。
- **轻量目标导向生成**：目标只进 prompt，AI 朝它生成 + 静态校验，用户自行应用查看，无自动比对。

**结论**：痛点3 暂不实现。若将来要做，走"人在环 + 同步比对"，不要再碰探针。

---

## 6. 路线现状

| 阶段 | 内容 | 状态 |
|---|---|---|
| 已做 | 读现有 M、grounded 生成 + 静态校验、增量补片段对话 + 🔄 同步、侧栏分两块、复制到高级编辑器 | ✅ 上线 |
| 已撤 | 实跑验证、M 写回、"展开即探"读全列 | ⛔ 因崩 Desktop 移除 |
| 下一步候选 | **痛点2 多查询合并/追加**（性价比最高、纯生成+静态、安全） | 未做 |
| 搁置 | 痛点3 目标导向（自动闭环不可行；若做走"人在环+同步比对"） | 搁置 |

---

## 7. 经验教训（核心）

- **M 在打开的 Desktop 上无法安全实跑验证。** 唯一的实跑手段（TOM 临时表刷新）会泄漏进 Desktop 的 Mashup 文档并崩溃它。这不是 bug 可修，是平台限制。**二期的"真验证"理想在 Desktop 上对 M 不成立。**
- **凡 TOM 写操作（写回 / 探针 / 任何加删表）对打开的 Desktop 都不安全**；只有只读 DMV（`SELECT`）安全。一期 DAX 用 `EVALUATE`（只读）所以没事。
- 因此 M 助手定位务实收缩为：**grounded 生成 + 静态校验 + 复制到高级编辑器，由 Desktop 应用时验证**。仍有实用价值（省写 M、列名 grounding、读现有查询作上下文），只是丢了"粘贴前就保证对"。
- 详细崩溃证据与红线见 `memory/mquery-refresh-verification.md`。
