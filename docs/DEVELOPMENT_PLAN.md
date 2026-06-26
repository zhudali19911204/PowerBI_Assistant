# PowerBI AI Assistant — 详细开发方案

> 版本 v1.0 ｜ 编写日期 2026-06-23 ｜ 一期：DAX 助手 MVP（并预留二/三期接口）
> 二期专项设计（Power Query / M 数据清洗助手）见 [PHASE2_POWERQUERY_DESIGN.md](PHASE2_POWERQUERY_DESIGN.md)。

---

## 1. 项目概述

### 1.1 背景与目标
Power BI 开发存在四大耗时痛点，本工具用 AI 智能化辅助完成：

| # | 痛点 | 期次 |
|---|------|------|
| 3 | **DAX 度量值编写**（上下文机制、业务规则、性能优化） | **一期 MVP** |
| 1 | 数据清洗（Power Query / M 脚本、脏数据探查） | 二期 |
| 2 | 数据建模（星型/雪花、关系推断） | 二期 |
| 4 | 仪表盘设计（配色、布局、视觉对象选择） | 三期 |

### 1.2 约束与定位
- **运行环境：仅 Power BI Desktop**（无 Premium / Fabric）→ 依赖 pbix 文本结构 + 本地 Analysis Services 引擎，而非云端 XMLA 写入。
- **形态：独立 Python 桌面/Web 应用**（与 Power BI 解耦）。
- **LLM 可替换**：默认 Claude，通过抽象接口可切换 OpenAI / 本地模型。

### 1.3 设计三原则（贯穿全期）
1. **模型语境为王（Grounding-first）**：所有生成都基于真实读取的模型结构，杜绝 AI 编造列名。
2. **能力插件化（Pluggable Capability）**：DAX/清洗/建模/仪表盘 是同一接口的不同实现，二/三期只新增插件、不改框架。
3. **真验证而非只建议（一期硬需求）**：连接本地引擎实跑结果（DAX `EVALUATE`），而非仅静态检查。
   依据：在 `dax-expert` skill 的高难度评测（见 §11）中，**带/不带 skill 的顶级模型都会在深层嵌套上下文转换上生成"能编译、解释自洽、但结果错误"的度量值**，且静态自审无法发现。这证明静态生成不可靠，**实跑验证是质量底线，不是可选项**。

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                     UI 层 (Streamlit)                      │
│  按已注册的 Capability 自动渲染标签页 (DAX / 清洗 / 建模...) │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│                  能力层 (core.Capability)                 │
│   DaxCapability │ MQueryCapability │ ModelingCapability   │
│   每个能力 = 若干 Action(generate/explain/optimize...)     │
└──────┬──────────────────┬───────────────────┬────────────┘
       │                  │                   │
┌──────▼──────┐  ┌────────▼────────┐  ┌───────▼─────────┐
│  LLM 抽象层  │  │  模型语境层      │  │  产物与验证层    │
│ LLMProvider │  │  ContextSource  │  │  Artifact       │
│ (claude/...)│  │ (pbix/live/...) │  │ validate/apply  │
└─────────────┘  └─────────────────┘  └─────────────────┘
       │                  │                   │
   Anthropic SDK      pbixray           本地 AS (pyadomd)
   / OpenAI 兼容      / msmdsrv 端口     EVALUATE 实跑
```

**四个横切抽象（即"预留接口"的本体）**：`LLMProvider`、`ContextSource`、`Capability`/`Action`、`Artifact`。二/三期所有新功能都落在这四个抽象的新实现上。

---

## 3. 技术栈（一期）

| 类别 | 选型 | 说明 |
|------|------|------|
| 语言 | **Python 3.11+** | 数据生态最全；3.11 类型/性能好 |
| LLM 默认 | **anthropic SDK** + `claude-opus-4-8`（可配 `claude-sonnet-4-6` 降本） | 经 `LLMProvider` 抽象，可替换 |
| LLM 兼容 | **openai SDK**（指向任意 OpenAI 兼容端点） | 二选一/可并存 |
| 模型读取 | **pbixray**（PyPI） | 静态解析 .pbix：表/列/类型/关系/度量值 |
| 实时引擎（**一期必备**） | **pyadomd** + **pythonnet**（ADOMD.NET） | 连本地 Desktop AS 跑 `EVALUATE` 验证生成的度量值（Windows-only，用户为 Win11 ✓）。评测已证明其必要性（§11） |
| UI | **Streamlit** | Python 出界面最快；架构分层，后续可平滑换 FastAPI+前端 |
| 配置 | **pydantic-settings** + **python-dotenv** | `.env` 管理 key / provider / model |
| 数据 | **pandas** | 验证结果展示、未来清洗模块复用 |
| 测试 | **pytest** | 单测 + 集成测 |
| 代码质量 | **ruff** + **black** + **mypy** | lint/format/类型 |
| 打包(可选) | **pywebview** / PyInstaller | 后期封装成桌面 exe |

> **依赖风险**：`pyadomd` 需 .NET 与 ADOMD.NET 客户端（随 SSMS / 单独安装）。实时验证是一期**核心能力**；当本地无运行中的 Desktop 时降级为静态校验并**明确告知用户"未经实跑验证"**，而非静默通过——避免把未验证的度量值当成已验证。

---

## 4. 核心抽象接口设计（为二/三期预留）

> 这一节是方案的"地基"。一期就把这些抽象定下来，二/三期只写新实现。

### 4.1 LLM 抽象 `llm/base.py`
```python
class LLMProvider(Protocol):
    def complete(self, system: str, messages: list[ChatMessage], **opts) -> str: ...
    def stream(self, system: str, messages: list[ChatMessage], **opts) -> Iterator[str]: ...

# llm/factory.py: build_provider(config) -> LLMProvider   ← 切换厂商的唯一开关
```
实现：`claude.py`(一期)、`openai_compat.py`(一期可选)、`local.py`(未来)。

### 4.2 模型语境抽象 `context/base.py`
```python
@dataclass
class Column:    name: str; dtype: str; table: str; cardinality: int | None
@dataclass
class Relationship: from_table: str; from_col: str; to_table: str; to_col: str; cross_filter: str
@dataclass
class Measure:   name: str; table: str; expression: str
@dataclass
class ModelContext:
    tables: dict[str, list[Column]]
    relationships: list[Relationship]
    measures: list[Measure]
    def serialize_for_prompt(self, focus: list[str] | None = None) -> str: ...  # 紧凑文本

class ContextSource(ABC):
    @abstractmethod
    def load(self) -> ModelContext: ...
```
实现：`PbixFileSource`(一期)、`LiveDesktopSource`(一期，验证用)、`PbipFolderSource`(二期，读 TMDL 工程)。

### 4.3 能力 / 动作抽象 `core/capability.py`（插件核心）
```python
@dataclass
class ActionRequest:  text: str; context: ModelContext; extra: dict
@dataclass
class ActionResult:   artifacts: list["Artifact"]; explanation: str; meta: dict

class Action(ABC):
    id: str; label: str
    @abstractmethod
    def run(self, req: ActionRequest) -> ActionResult: ...

class Capability(ABC):
    id: str; name: str           # "dax" / "mquery" / "modeling" / "dashboard"
    @abstractmethod
    def actions(self) -> list[Action]: ...

# core/registry.py
CAPABILITIES: dict[str, Capability] = {}
def register(cap: Capability) -> None: CAPABILITIES[cap.id] = cap
```
**UI 自动遍历 `CAPABILITIES` 渲染标签页** → 二/三期 `register(MQueryCapability())` 一行接入，UI 零改动。

### 4.4 产物与验证抽象 `core/artifact.py`
```python
@dataclass
class ValidationResult: ok: bool; errors: list[str]; warnings: list[str]; sample: Any | None

class Artifact(ABC):
    kind: str                    # "dax_measure" / "m_script" / "tmdl" / "theme_json"
    content: str
    @abstractmethod
    def validate(self, ctx: ModelContext) -> ValidationResult: ...
    def apply(self, target) -> "ApplyResult": ...   # 写回（按期次能力不同）
```
实现：`DaxMeasureArtifact`(一期)、未来 `MScriptArtifact` / `TmdlArtifact` / `ThemeJsonArtifact`。

---

## 5. 一期 DAX MVP — 详细模块设计

### 5.1 目录结构
```
powerbi_ai_assistant/
├─ llm/        base.py  claude.py  openai_compat.py  factory.py
├─ context/    base.py  pbix_source.py  live_source.py
├─ core/       capability.py  registry.py  artifact.py
├─ dax/
│   ├─ capability.py     # DaxCapability + 三个 Action
│   ├─ prompts.py        # system prompt（DAX 规范 + 语境注入模板）
│   ├─ generate.py       # NL -> DAX
│   ├─ explain.py        # DAX -> 解释
│   ├─ optimize.py       # DAX -> 优化版 + 说明
│   └─ artifact.py       # DaxMeasureArtifact（静态+实时验证）
├─ app/        main.py   components.py
├─ config.py   .env.example  requirements.txt  README.md
└─ tests/      test_context.py  test_dax.py  test_validate.py
```

### 5.2 三大 Action 设计

**① 生成 (generate)**：输入业务描述 → 注入 `ModelContext.serialize_for_prompt()` → LLM 产出 DAX → 包装为 `DaxMeasureArtifact` → 自动 `validate()`。
**② 解释 (explain)**：输入度量值 → LLM 逐段拆解行/筛选上下文、上下文转换、计算流程。
**③ 优化 (optimize)**：输入度量值 → 检测反模式（对整表 `FILTER`、未用变量、`/` 替代 `DIVIDE`、重复 `CALCULATE` 等）→ 产出优化版 + 差异说明。

### 5.3 Prompt 设计要点（`dax/prompts.py`）✅ 已实现
已从 `dax-expert` skill 蒸馏落地（`powerbi_ai_assistant/dax/prompts.py`）：`DAX_SYSTEM_PROMPT` +
三个动作的 `build_generate/explain/optimize_prompt` builder。内置规则：
- 只能引用注入语境中**真实存在**的表/列/度量值（grounding 防幻觉）；
- 优先用 `VAR`；除法用 `DIVIDE`（并免去多余 `IF` 判零）；
- `CALCULATE` 上下文转换、`KEEPFILTERS`/`REMOVEFILTERS`/`ALLSELECTED` 语义；
- 避免对整表 `FILTER`，改用列谓词；
- **嵌套迭代器陷阱**：迭代一表却在内层聚合另一表时，必须用 `CALCULATE` 触发上下文转换（评测真实失败案例，见 §11）；
- 输出结构：度量值代码块 + 逻辑说明 + 需确认的假设。
> skill 是长版知识库（开发/评测用），`prompts.py` 是产品内的压缩版；二者保持同步——真实失败先改 skill，再回写 prompts。

### 5.4 验证机制（`dax/artifact.py`）—— 一期质量底线
- **静态**（始终可用，第一道）：解析引用的表/列/度量值是否在 `ModelContext` 中存在；括号/函数名基本语法检查。能拦住"幻觉列名""语法错"。
- **实时（必备，第二道）**：发现本地 AS 端口（读 `%LOCALAPPDATA%/Microsoft/Power BI Desktop/AnalysisServicesWorkspaces/*/Data/msmdsrv.port.txt`）→ pyadomd 连接 → 以 `DEFINE MEASURE <t>[<m>] = <expr> EVALUATE ROW("v", <t>[<m>])` 实跑 → 返回真实值/报错。**这是唯一能抓出"能编译但语义错"（如嵌套上下文转换缺失）的手段**（§11 实证）。
- **降级策略**：无运行中的 Desktop 时仅做静态校验，并在 UI 显式标注"⚠ 未经实跑验证"，不得伪装为已验证。

### 5.5 配置（`config.py`）
```
LLM_PROVIDER=claude            # claude | openai_compat
LLM_MODEL=claude-opus-4-8
ANTHROPIC_API_KEY=...
OPENAI_BASE_URL=... / OPENAI_API_KEY=...   # 可选
ENABLE_LIVE_VALIDATION=true
```

---

## 6. 开发计划与里程碑

| 阶段 | 内容 | 交付物 | 验收标准 | 估时 |
|------|------|--------|----------|------|
| **M0 骨架** | 目录、依赖、config、Streamlit Hello | 可运行空应用 | `streamlit run` 起得来 | 0.5d |
| **M1 抽象层** | §4 四个抽象 ABC + registry | `llm/`/`context/`/`core/` 接口 | mypy 通过、可被 import | 1d |
| **M2 模型语境** | `PbixFileSource` + 紧凑序列化 | 读样例 .pbix 打印语境 | 表/列/关系/度量值齐全 | 1.5d |
| **M3 LLM 接入** | `claude.py` + factory | 一次 completion 成功 | 切 provider 配置生效 | 1d |
| **M4 DAX 生成** | `DaxCapability.generate` + prompts | NL→DAX | 只引用真实列、含 VAR/DIVIDE | 2d |
| **M5 解释+优化** | explain / optimize Action | 两个 Action | 解释准确、优化可见改进 | 1.5d |
| **M6 验证闭环** | 静态校验 + `live_source` 实时 `EVALUATE` + **报错回喂修复**（§13.2，K=3） | `validate()` + 闭环编排 | 错列报错；实时返回真实值；故意制造可修复错误时能自动修正 | 2.5d |
| **M7 UI 整合** | 按 registry 渲染标签页 | 可用 MVP | 端到端走通 §8 全部用例 | 1.5d |
| **M8 收尾** | 测试、README、打包(可选) | 文档+测试 | 关键路径单测覆盖 | 1d |

**合计约 12 人日**（单人）。M1 的抽象层是后续期次的根基，优先级最高。

---

## 7. 二期 / 三期接口预留

| 期次 | 新能力 | 复用的抽象 | 需新增的实现 |
|------|--------|-----------|--------------|
| 二期 | **数据清洗(M)** | LLMProvider, ContextSource | `mquery/capability.py`(profile→生成M)、`MScriptArtifact`、pandas 数据探查器 |
| 二期 | **数据建模** | 同上 + `PbipFolderSource` | `modeling/capability.py`(事实/维度推断、关系建议)、`TmdlArtifact`(产 TMDL) |
| 三期 | **仪表盘设计** | LLMProvider, ModelContext | `dashboard/capability.py`(视觉对象推荐)、`ThemeJsonArtifact`(配色)、PBIR 布局生成器 |

接入方式统一为：写新 `Capability` 子类 → `register()` → UI 自动出现新标签页。**框架与 UI 零改动。**

预留扩展点清单：
- `ContextSource`：新增 `PbipFolderSource`(读 TMDL 工程)、`CsvExcelSource`(清洗输入)。
- `Artifact.apply()`：二/三期实现写回（TMDL 落盘、theme.json 导出、M 脚本注入 PBIP）。
- `prompts/`：每能力独立 prompt 模块，互不干扰。

---

## 8. 验证与测试策略

**端到端用例（M7 验收）**：
1. 加载真实 .pbix → 左栏列出真实表/列/度量值。
2. 输入"按月计算同比销售增长率" → 生成 DAX 仅引用真实列、含 `VAR`/`DIVIDE`。
3. 故意引用不存在列 → 静态校验报错。
4. 打开同报表 Desktop → 实时验证 `EVALUATE` 返回真实值。
5. 切换 `LLM_PROVIDER` → 全流程仍正常（证明抽象层有效）。

**单元测试**：`ModelContext.serialize_for_prompt` 输出稳定；静态校验对错列/错语法判定准确；factory 按配置返回正确 provider。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| pyadomd/.NET 环境依赖复杂 | 实时验证设为可选，缺失时降级静态校验，不阻塞主流程 |
| LLM 编造列名 | 强制注入语境 + 静态校验拦截 + prompt 硬约束 |
| pbix 大模型语境超 token | `serialize_for_prompt(focus=...)` 按相关表裁剪 |
| 本地 AS 端口发现失败 | 多策略：读 port 文件 → 扫描进程 → 手动填端口 |
| Streamlit 后期不够用 | 业务逻辑全在 core/dax，UI 可整体替换为 FastAPI+前端 |

---

## 10. 落地动作

确认本方案后，将本文档保存为项目内 **`docs/DEVELOPMENT_PLAN.md`**，并按 M0 搭建项目骨架（目录 + `requirements.txt` + `config.py` + `.env.example` + 空 Streamlit 应用），随后按里程碑推进。

---

## 11. DAX 能力评测实证（dax-expert skill，3 轮）

为给 DAX 能力建立质量基线，用 skill-creator 跑了 3 轮"带 skill / 不带 skill"对照评测（每题独立子代理，按显式 assertion 评分）。工件在 `.claude/skills/dax-expert-workspace/iteration-{1,2,3}/`（含 `review.html` 可视化）。

| 轮次 | 难度 | 带 skill | 不带 skill | 拉开差距处 |
|---|---|---|---|---|
| 1 | 基础（YoY/优化/占比） | 100% | 93.3% | 基线留多余 `IF` 判零 |
| 2 | 复杂（跨表/上下文转换/移动平均/半累加） | 100% | 95.8% | 基线写出 `RESULT=` 语法错（无法编译） |
| 3 | 极难（嵌套上下文/多变量帕累托/快照周转/留存） | 95.8% | 95.8% | 持平；**两边同一隐蔽 bug** |

**两条决定架构的结论：**
1. **顶级模型 DAX 推理极强**，skill 的增量主要在"工程纪律"（去冗余、防语法错），难题上被基线本身能力稀释。
2. **§3.3 的铁证**：迭代 3 的库存周转率题，带/不带 skill **都**在嵌套迭代器内层漏了 `CALCULATE`，生成"能编译、解释自洽、结果却错"的度量值，静态自审无法发现 → **实跑 `EVALUATE` 验证是一期硬需求**（已写入 §1.3 / §5.4）。该真实案例已回写进 skill 与 `prompts.py`。

## 12. 持续优化闭环（skill 与 prompts.py 的真实案例迭代）

本工具的"DAX 大脑"= `dax-expert` skill（知识库）+ `dax/prompts.py`（产品内压缩版）+ 实跑验证。三者都设计为**可被真实使用反哺迭代**：

1. **捕获失败案例**：使用中发现 AI 写错/次优的度量值时，连同模型 schema 存为一个新测试题（`evals/` 或直接进 workspace 的新 `eval-N/`）。日积月累形成"真实失败案例库"。
2. **回归评测**：用现有 skill-creator 脚手架跑一轮对照——baseline 选**旧版 skill/prompts**，新版为改进后版本，即可量化"改了有没有更好、有没有回退"。命令见 §11 工件目录（`aggregate_benchmark` + `generate_review.py`，Windows 需 `PYTHONUTF8=1`）。
3. **先改 skill，再回写 prompts.py**：skill 是长版权威知识，先在此沉淀经验（如新加的"嵌套迭代器陷阱"§11），再把要点压缩进 `prompts.py` 的 `DAX_SYSTEM_PROMPT`，保持两者同步。
4. **可选客观化**：需要更中立的结论时，用 skill-creator 的"盲评"（匿名两版交独立子代理评判）。

> 一句话：**是的，可以在使用过程中用实际案例持续优化 skill 和 prompts.py**——评测脚手架已就绪，案例越多、打磨越准。这条闭环建议固化为开发纪律。

---

## 13. 准确性约束架构（让 LLM 跑得准的"马具"）

**设计原理**：prompt 只是缰绳，定方向；准确性靠两条——**(a) 闭环**：让模型撞到真实环境的栏杆才修正（环境反馈 > 自我提醒）；**(b) 缩小可跑偏空间**：把确定性的活交给确定性的代码，别让随机的模型做本该由轨道保证的事。
**实证依据**：§11 评测中，模型的自我审查没能发现嵌套上下文转换 bug，只有实跑能发现 → 约束的重心必须是**执行闭环**，而非更多提示或自我批判。

### 13.1 约束层一览（马具 → 机制 → 杀掉哪种跑偏）

| 马具 | 机制（落点） | 杀掉的跑偏 |
|---|---|---|
| 缰绳 · prompt | `dax/prompts.py` 系统提示 + 规则 | 风格/习惯偏差 |
| 眼罩 · 语境锚定 | 注入真实 schema；约束词表，只允许引用 `ContextSource` 列出的对象 | 幻觉列名 |
| **围栏 · 执行验证+修复闭环** ⭐ | `LiveDesktopSource` 跑 `EVALUATE` → 报错/异常回喂 → 重生成，至多 K 次 | 语义错、"能编译但算错" |
| 挡板 · 确定性静态校验 | `dax/validate.py`（代码非 LLM）：列/度量值存在性、括号配平、反模式 lint（含**嵌套迭代器缺 `CALCULATE`** 检测） | 语法错、低级反模式 |
| 导轨 · 结构化输出 | tool-use/JSON schema 返回 `{measure, name, deps, assumptions}` | 让验证可自动化、闭环可编程 |
| 熟练路线 · 模板库 | 常见指标(YoY/占比/累计)用参数化 DAX 模板**确定性填充** | 80% 常见场景的随机性 |
| 看路 · 工具访问 | 给模型工具：列字段、查 Date 表是否标记、抽样、探针查询 | 盲猜假设 |
| 投票 · 自洽/Best-of-N | 采样 N 个候选 → 各自 `EVALUATE` → 选能跑通/一致者 | 难题单次不稳定 |
| 勒马 · 弃权/升级 | 显式声明假设；歧义反问；K 次失败转人工 | 强行输出错误答案 |
| 训练场 · 回归评测（已有） | skill-creator 脚手架 + 真实失败案例库（§12） | 改动导致质量回退 |

### 13.2 一期核心流程（`dax/` 必须实现的闭环）

**生成 → 静态校验 → 实跑验证 → 修复** —— 作为 `DaxCapability.generate` 的主干，而非"生成完就交付"：

```
NL 需求 + ModelContext
      │  build_generate_prompt() + LLMProvider（结构化输出）
      ▼
  候选度量值 (DaxMeasureArtifact)
      │  ① 静态校验  validate.py：列/度量值存在？括号配平？反模式(含嵌套迭代器缺 CALCULATE)？
      ├── 失败 ─► 把具体问题回喂 LLM 重生成 ┐
      ▼                                      │
  ② 实跑验证  LiveDesktopSource：DEFINE MEASURE … EVALUATE ROW(…)
      ├── 报错/异常 ─► 把真实错误回喂 LLM 修复 ┘ （①②合计至多 K 次，默认 K=3）
      ▼
  ③ 通过 ─► 交付（附：跑出的真实值 + 用到的列/度量值 provenance + 已过校验标记）
      └── K 次仍失败 ─► 弃权：交付最佳候选并显式标注"⚠ 未通过验证，需人工复核"
```

落点：`dax/capability.py`（编排闭环）、`dax/validate.py`（静态+反模式 lint）、`dax/artifact.py`（`validate()`/实跑）、`context/live_source.py`（`EVALUATE`）。无运行中的 Desktop 时跳过 ②，并按 §5.4 标注"未经实跑验证"。

### 13.3 实施优先级（投入产出比）

- **第一梯队**（直击已证实失败模式）：执行验证+**修复闭环** ⭐、结构化输出、确定性静态校验器。→ 并入里程碑 **M6**（验证从"通过/失败"升级为"校验→实跑→修复"闭环）。
- **第二梯队**：模板库（常见指标确定性填充）、工具访问（让模型查模型而非猜）、Best-of-N（难题用执行结果投票）。→ MVP 跑通后增量加入。
- **第三梯队**：假设门控/弃权升级、provenance 审计。→ 随产品成熟补齐。

> 收口：**缰绳定方向，围栏(执行闭环)保证不出界，挡板(确定性校验)挡掉低级错，熟练路线(模板)减少瞎跑。执行闭环是决定性马具**——已对齐 §1.3/§5.4 的一期硬需求。

---

## 14. 一期后续优化 — 校准强化（待办）

**背景**：当前校准式生成（`dax/calibrate.py`）已能挡住"能跑但算错"——用户给**单个**切片的已知正确值（oracle），系统生成→在该切片实跑→比对→不中则自修/反问，直到命中。但保证的只是**"在那一个切片上等于该值"**，不等于"在所有上下文下都对"：单点命中、总计/空切片/跨期下可能仍错；oracle 本身若算错则闭环会收敛到"一致地错"。下列三条按投入产出比强化这一块。

### 14.1 多切片校准（优先级：高）

- **做什么**：让用户给 2~3 个切片的真值（**强制至少含一个"总计行"**，即无筛选/整模型的合计），一次性要求生成的度量值在**所有**给定切片上同时命中才算通过。
- **为什么**：单切片对 ≠ 全局对。总计行与单点常是两套行为（汇总粒度、context transition、去重），多点同时约束能大幅降低"单点对、全局错"。
- **代码落点**：
  - `dax/calibrate.py`：`CalibrationSession.filters/expected` 单值 → **改为切片列表** `cases: list[(filters, expected)]`；`_test()` 遍历所有 case，全中才 `passed`，未中时把**每个**切片的"期望 vs 实跑值"一并喂进诊断。
  - `dax/prompts.py`：`build_calibrated_generate_prompt` / `build_calibrate_diagnose_prompt` / `build_calibrate_refine_prompt` 的 `slice_desc + expected` 参数 → 多切片表格（含总计行）。
  - `app/components.py`：`_render_calibrate_setup` 的"添加筛选条件 + 单个正确值" → 支持**添加多组 (切片, 正确值)**，并提示"建议加一行总计"；`_render_calibrate_thread/_transcript` 按 case 展示命中情况。
- **验收**：构造一个"单点能蒙对、总计会错"的指标（如带去重的占比），多切片校准必须暴露并修正它。

### 14.2 自动反例探测（优先级：中）

- **做什么**：命中后**自动**在一组"危险切片"上再跑一遍并展示结果，无需用户预先提供真值——危险切片含：总计/无筛选、空切片（不存在的成员→应为 BLANK 而非 0 或报错）、跨期/跨年、单成员 vs 多成员。
- **为什么**：主动暴露"用户没想到去验的上下文"，把隐患从"上线后才发现"提前到"交付前看一眼"。这是**探测**而非判定——没有 oracle，只标"看起来可疑"（如总计 ≠ 各行之和、空切片返回非空），让用户复核。
- **代码落点**：`dax/calibrate.py` 命中分支后新增 `probe_danger_slices()`（复用 `evaluate_at_slice`，空切片用模型里不存在的成员值构造）；`app/components.py` 在 `passed` 状态下渲染一张"反例探测"小表，可疑项高亮。
- **注意**：纯启发式、零真值，文案须明确"提示可疑，需人工确认"，不得当成"已验证不一致"。

### 14.3 校准前口径澄清（优先级：中）

- **做什么**：在**生成第一个候选之前**，先让模型基于需求文本判断有无高风险歧义（是否含税 / 同比口径 / 跨月 vs 单月 / 是否去重 / 用哪张日期表），**有则先反问 1~2 个关键口径**，澄清后再进入生成→实跑闭环。
- **为什么**：当前是"先生成、算错了才反问"（`advance` 里 auto 预算耗尽才问）；把澄清提前能少跑几轮无效的生成-实跑，更快收敛，也更省 token。
- **代码落点**：`dax/calibrate.py` `advance()` 在 `not session.candidate` 分支前插入一个可选的 `_clarify_intent()` 预检（新增 `CalibrationSession.status="clarifying"`）；新增 `dax/prompts.py::build_calibrate_clarify_prompt`（只判歧义、只问问题，不出 DAX）。
- **权衡**：避免"为问而问"——仅在模型判定为**高风险歧义**时才打断；低风险直接生成，靠实跑闭环兜底。

### 14.4 实施顺序与依赖

1. **先 14.1**：它改 `CalibrationSession` 数据结构（单值→列表），是另外两条的地基；14.2 的反例探测、14.3 的澄清都构建在多切片之上。
2. 再 **14.3**（澄清提前，纯增量、低风险），最后 **14.2**（反例探测，需要稳定的多切片实跑器）。
3. 三条都遵守 §12 的"先改 skill 再回写 prompts.py"与 §5.4 的"未实跑不得标为已验证"。

