# PowerBI AI Assistant

AI 辅助 Power BI 四大痛点（数据清洗 / 建模 / DAX / 仪表盘）。一期 MVP = **DAX 助手**（生成 / 解释 / 优化，并实跑 `EVALUATE` 验证）。Desktop-only，Python + Streamlit + 可替换 LLM。

完整方案见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)；项目规则见 [CLAUDE.md](CLAUDE.md)。

## 快速开始

```bash
# 1. 创建虚拟环境（Windows / Git Bash）
python -m venv .venv
source .venv/Scripts/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env        # 填入 ANTHROPIC_API_KEY 等

# 4. 启动
streamlit run powerbi_ai_assistant/app/main.py
```

> 实跑验证（M6）依赖 `pyadomd` + .NET/ADOMD.NET（Windows）。这两个包在 `requirements.txt` 中默认注释，接入实跑验证时再启用。

## 目录结构

```
powerbi_ai_assistant/
├─ llm/        LLM 抽象层（M3）
├─ context/    模型语境层：读 .pbix / 连本地 AS（M2）
├─ core/       横切抽象：Capability/Action、registry、Artifact（M1）
├─ dax/        DAX 能力：prompts / generate / explain / optimize / 验证
└─ app/        Streamlit UI
docs/   方案    tests/  测试    .claude/skills/dax-expert/  DAX 知识库
```

## 架构要点
四个横切抽象（`LLMProvider` / `ContextSource` / `Capability`·`Action` / `Artifact`）复用于各期；加新能力 = 新 `Capability` 子类 + `register()`，UI 自动渲染。所有 DAX 生成均**锚定真实模型**，并走"生成→静态校验→实跑→修复"闭环（见方案 §13）。
