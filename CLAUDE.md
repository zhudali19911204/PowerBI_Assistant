
# CLAUDE.md — PowerBI AI Assistant

> 本文件每次会话自动加载，是本项目的通用规则与约定。修改即时生效。
> 完整方案见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)；背景记忆见 [memory/](memory/)。

## 项目简介
AI 辅助 Power BI 四大痛点（数据清洗 / 建模 / **DAX** / 仪表盘）。一期 MVP = DAX 助手，Desktop-only，Python + Streamlit + 可替换 LLM。

## 沟通与协作
- **用中文回复。**
- **先确认再开发**：动手写代码/搭骨架前先对齐方案，不要急着实现。
- **诚实评估**：如实说明权衡、局限、未验证项；是平局就说平局，不夸大、不过度承诺。
- 评估质量优先用**真实执行/评测**，而非断言。
- 给清晰的 A/B/C 下一步选项，给推荐但不替用户拍板关键决策。

## 环境与命令
- Windows 11 + Git Bash（POSIX sh）；用 Unix 语法（`/dev/null`、正斜杠、`$VAR`）。
- 跑 skill-creator 评测脚本时**必须** `PYTHONUTF8=1`（默认 gbk 编码会报错）。
- 临时文件放 scratchpad，不要污染项目目录。

## 代码与架构约定
- **四个横切抽象**复用于各期：`LLMProvider` / `ContextSource` / `Capability`·`Action` / `Artifact`。加新能力 = 新 `Capability` 子类 + `register()`，UI 自动渲染。
- **Grounding 优先**：所有 DAX/M 生成只能引用 `ModelContext` 中真实存在的表/列/度量值，禁止臆造。
- **实跑验证是硬需求**：DAX 走"生成→静态校验→实跑 `EVALUATE`→修复"闭环（§13.2）；二期 Power Query(M) 走"生成→静态 lint→实跑**刷新回环**（TOM 临时表 + `Table.Schema` 探针，见 [[mquery-refresh-verification]]）→修复"。无 Desktop 时降级静态校验并显式标注"未经实跑验证"。
- **知识双资产同步**：`.claude/skills/<name>-expert/` 是权威知识库，`powerbi_ai_assistant/<name>/prompts.py` 是产品内压缩版——**先改 skill，再回写 prompts.py**。适用于 dax 与 mquery 两套。
- LLM 切换只改 config，不改业务代码（经 `LLMProvider` 抽象）。

## 关键文件
- 方案：[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)
- 二期设计（Power Query/M 助手）：[docs/PHASE2_POWERQUERY_DESIGN.md](docs/PHASE2_POWERQUERY_DESIGN.md)
- DAX skill / prompts：[.claude/skills/dax-expert/](.claude/skills/dax-expert/) ↔ [powerbi_ai_assistant/dax/prompts.py](powerbi_ai_assistant/dax/prompts.py)
- Power Query(M) skill / prompts：[.claude/skills/mquery-expert/](.claude/skills/mquery-expert/) ↔ [powerbi_ai_assistant/mquery/prompts.py](powerbi_ai_assistant/mquery/prompts.py)
- 评测脚手架：`.claude/skills/dax-expert-workspace/`

## Memory 双向同步
- 项目有两份 memory，必须**始终保持一致**：
  - 用户级：`C:\Users\uic89469\.claude\projects\e--AI-Project-PowerBI-AI-Assistant\memory\`（会话自动加载）
  - 项目级：`e:\AI_Project\PowerBI_AI_Assistant\memory\`（随仓库走）
- **每次新增/修改/删除任一处的 memory（含 `MEMORY.md` 索引），都要同步到另一处**，确保文件清单与内容完全一致。
- 同步后用 `diff` 核对清单与逐文件内容，确认无差异再算完成。

## 通用规则（自定义 — 待补充）
<!-- 在下面追加你的规则，例如命名规范、提交信息格式、禁止事项等 -->
- **改完 UI 代码必须干净重启 Streamlit，否则浏览器看到的是旧实例**。常见坑：旧实例没杀掉仍占着 8501，新实例 `exit 1` 起不来，浏览器命中旧代码 → 表现为"改动没生效"。固定流程：
  1. 杀掉 8501 上**所有** PID：`for p in $(netstat -ano | grep ':8501' | grep LISTENING | awk '{print $NF}' | sort -u); do taskkill //F //PID $p; done`，`sleep 2` 后确认 `8501 free`；
  2. 用**项目 venv** 的 Python 起（`.venv/Scripts/python.exe -m streamlit ...`，**不是**系统 Python，系统 Python 没装 streamlit）；
  3. 起好后确认只有**一个** LISTENING PID，再让用户 Ctrl+F5 强刷验证。
