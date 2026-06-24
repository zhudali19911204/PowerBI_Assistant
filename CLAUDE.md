
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
- **实跑验证是一期硬需求**：DAX 走"生成→静态校验→实跑 `EVALUATE`→修复"闭环（§13.2）；无 Desktop 时降级静态校验并显式标注"未经实跑验证"。
- **DAX 知识双资产同步**：`.claude/skills/dax-expert/` 是权威知识库，`powerbi_ai_assistant/dax/prompts.py` 是产品内压缩版——**先改 skill，再回写 prompts.py**。
- LLM 切换只改 config，不改业务代码（经 `LLMProvider` 抽象）。

## 关键文件
- 方案：[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)
- DAX skill：[.claude/skills/dax-expert/](.claude/skills/dax-expert/)
- DAX prompts：[powerbi_ai_assistant/dax/prompts.py](powerbi_ai_assistant/dax/prompts.py)
- 评测脚手架：`.claude/skills/dax-expert-workspace/`

## 通用规则（自定义 — 待补充）
<!-- 在下面追加你的规则，例如命名规范、提交信息格式、禁止事项等 -->
- 
