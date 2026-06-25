"""Reusable Streamlit UI pieces."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ..context import (
    DesktopInstance,
    LiveDesktopSource,
    LiveDesktopWriter,
    ModelContext,
    find_instances,
)
from ..core import registry
from ..core.capability import Capability
from ..dax import (
    CalibrationSession,
    DaxCapability,
    LiveDesktopEvaluator,
    advance,
    has_dax_block,
    is_table_expression,
    parse_dax_blocks,
    slice_desc,
    validate_measure_set,
)
from ..dax.prompts import build_chat_system_prompt
from ..llm import ChatMessage, build_provider, user
from ..runtime_config import (
    PRESET_BY_KEY,
    PROVIDER_PRESETS,
    RuntimeConfig,
    load,
    save,
)
from .theme import brand_header, eyebrow, model_readout

_CUSTOM_MODEL = "（自定义…）"


def get_config() -> RuntimeConfig:
    """The current runtime config, loaded once per session into session_state."""
    if "llm_config" not in st.session_state:
        st.session_state.llm_config = load()
    return st.session_state.llm_config


def render_settings_entry() -> RuntimeConfig:
    """Sidebar header: brand lockup on the left, a settings gear on the right, anchored by a gold
    hairline. The gear opens the full config form in a modal dialog. Returns the active config."""
    cfg = get_config()
    with st.sidebar:
        col_brand, col_gear = st.columns([5, 1], vertical_alignment="center")
        with col_brand:
            brand_header()
        with col_gear:
            if st.button("⚙️", key="ui_gear_btn", help="模型设置"):
                _settings_dialog()
        label = PRESET_BY_KEY[cfg.preset].label if cfg.preset in PRESET_BY_KEY else cfg.preset
        model_readout(label, cfg.model, bool(cfg.api_key))
        st.markdown('<div class="brand-rule"></div>', unsafe_allow_html=True)
    return get_config()


@st.dialog("⚙️ 模型设置")
def _settings_dialog() -> None:
    """The full provider/model/key form, shown on demand in a modal rather than always in the sidebar."""
    cfg = get_config()

    # --- provider preset ---
    # The selectbox's own `key` is the single source of truth — seed it once from the saved config,
    # then never pass `index=`. Passing an index derived from a separately-stored value (updated later
    # in the function) is what caused the "needs two clicks to switch" lag.
    keys = list(PRESET_BY_KEY)
    if "provider_preset" not in st.session_state:
        st.session_state.provider_preset = cfg.preset if cfg.preset in keys else keys[0]
    preset_key = st.selectbox(
        "大模型供应商",
        keys,
        key="provider_preset",
        format_func=lambda k: PRESET_BY_KEY[k].label,
        help="预置常用供应商；选「自定义」可填入任意 OpenAI 兼容接口（DeepSeek/Kimi/千问/Ollama 等）。",
    )
    preset = PRESET_BY_KEY[preset_key]
    # Dependent widgets are keyed by preset, so each provider gets its own widget instance: switching to
    # a provider for the first time seeds from the preset defaults; the saved config only seeds the
    # provider that was active when the app loaded.
    seed_from_cfg = preset_key == cfg.preset

    # --- model: suggested list + custom ---
    models = list(preset.models)
    default_model = cfg.model if (seed_from_cfg and cfg.model) else (models[0] if models else "")
    options = models + [_CUSTOM_MODEL]
    m_idx = models.index(default_model) if default_model in models else len(models)
    choice = st.selectbox("模型", options, index=m_idx, key=f"model_sel_{preset_key}")
    if choice == _CUSTOM_MODEL:
        model = st.text_input("自定义模型 ID", value=default_model, key=f"model_custom_{preset_key}")
    else:
        model = choice

    # --- base url (openai-compatible only) ---
    base_url = ""
    if preset.impl == "openai_compat":
        default_base = cfg.base_url if (seed_from_cfg and cfg.base_url) else preset.base_url
        base_url = st.text_input(
            "API Base URL", value=default_base,
            placeholder="https://api.example.com/v1", key=f"base_{preset_key}",
        )

    # --- api key (shared across providers; user updates per provider as needed) ---
    if "api_key_input" not in st.session_state:
        st.session_state.api_key_input = cfg.api_key
    api_key = st.text_input("API Key", type="password", key="api_key_input")
    remember = st.checkbox(
        "在本机记住 API Key", value=True,
        help="明文保存在 ~/.powerbi_ai_assistant/config.json（仅本机）。取消勾选则只在本次会话有效。",
    )

    new_cfg = RuntimeConfig(
        preset=preset_key, provider=preset.impl, model=model, api_key=api_key, base_url=base_url
    )
    st.session_state.llm_config = new_cfg  # commit live so the app uses edits even before "保存"

    col_save, col_test = st.columns(2)
    if col_save.button("保存", use_container_width=True):
        path = save(new_cfg, remember_key=remember)
        st.success("已保存" + ("（含密钥）" if remember else "（未存密钥）"))
        st.caption(str(path))
    if col_test.button("测试连接", use_container_width=True):
        _test_connection(new_cfg)
    st.caption("配置即时生效；关闭本窗口（右上角 ✕）即可回到主界面。")


# =================================================================================================
# M7 — capability-driven UI: register capabilities, load a model, render one tab per capability.
# =================================================================================================

def ensure_capabilities() -> None:
    """Register the phase-1 capabilities once. Idempotent — Streamlit reruns the script every
    interaction, so a second `register()` (which rejects duplicate ids) would otherwise crash."""
    if "dax" not in registry.CAPABILITIES:
        registry.register(DaxCapability())


def render_model_source_sidebar() -> ModelContext | None:
    """Sidebar panel to connect to an open Power BI Desktop model (live).

    Phase 1 reads the model only from the running Desktop engine — it exposes calculated tables'
    columns and every relationship, which static .pbix parsing cannot. The loaded ModelContext is
    cached in session_state. Returns it, or None if not connected yet.
    """
    with st.sidebar:
        ctx: ModelContext | None = st.session_state.get("model_ctx")

        # "模型来源" eyebrow with a built-in traffic-light dot: green = connected, red = not.
        connected = ctx is not None
        dot = "#0E9F6E" if connected else "#D6453C"  # --ok / --bad
        label = "已连接" if connected else "未连接"
        st.markdown(
            f'<div style="font-size:.7rem;font-weight:600;letter-spacing:.14em;'
            f'text-transform:uppercase;color:#737B8C;margin:.2rem 0 .55rem;'
            f'display:flex;align-items:center;gap:.5rem;">'
            f'<span style="width:9px;height:9px;border-radius:50%;background:{dot};'
            f'box-shadow:0 0 0 3px {dot}22;flex:0 0 auto;"></span>模型来源'
            f'<span style="margin-left:auto;color:{dot};letter-spacing:.04em;">{label}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if st.button("🔌 连接 Power BI Desktop", type="primary", use_container_width=True):
            _scan_and_connect()

        # Only when more than one report is open do we ask which instance (by port).
        instances: list[DesktopInstance] = st.session_state.get("pbi_instances", [])
        if len(instances) > 1:
            port = st.selectbox(
                "选择报表实例", [i.port for i in instances],
                format_func=lambda p: f"端口 {p}", key="pbi_pick_port",
            )
            if st.button("加载选中模型", use_container_width=True):
                _connect_instance(next(i for i in instances if i.port == port))

        if ctx is not None:
            _render_model_browser(ctx)
        return ctx


def _render_model_browser(ctx: ModelContext) -> None:
    """A clickable field reference: each table column / measure is a button that inserts its exact
    `'Table'[Column]` / `[Measure]` reference into the request box — grounding the user's wording in real
    names and cutting down on the AI inventing objects. (Type is shown on hover, not inline.)"""
    with st.expander("📋 表与列（点字段插入到需求框）", expanded=False):
        table = st.selectbox("选择表", list(ctx.tables), key="browse_table")
        if table:
            cols = ctx.tables.get(table, [])
            tag = "（日期表）" if table in ctx.date_tables else ""
            st.caption(f"`{table}`{tag} · {len(cols)} 列 · 点列名插入到「业务需求」框")
            for c in cols:
                if st.button(c.name, key=f"col_{table}_{c.name}", help=c.dtype, use_container_width=True):
                    _insert_into_request(f"'{table}'[{c.name}]")
    if ctx.measures:
        with st.expander(f"📐 度量值（{len(ctx.measures)}）", expanded=False):
            for m in ctx.measures:
                if st.button(m.name, key=f"meas_{m.name}", use_container_width=True):
                    _insert_into_request(f"[{m.name}]")


def _insert_into_request(ref: str) -> None:
    """Append a field reference to the DAX request text box (keyed `dax_gen_text`), then rerun so the
    text area — rendered later in the main pane — shows the updated value."""
    current = st.session_state.get("dax_gen_text", "")
    sep = "" if (not current or current.endswith((" ", "\n"))) else " "
    st.session_state.dax_gen_text = current + sep + ref + " "
    st.rerun()


def _scan_and_connect() -> None:
    """Scan for open Desktop instances. One → connect immediately; several → stash them for the picker."""
    with st.spinner("扫描打开的 Power BI Desktop…"):
        try:
            instances = find_instances()
        except Exception as e:  # noqa: BLE001
            st.error(f"扫描失败：{type(e).__name__}: {e}")
            return
    if not instances:
        st.session_state.pbi_instances = []
        st.error("未发现打开的 Power BI Desktop。请在 Desktop 中打开报表后重试。")
        return
    st.session_state.pbi_instances = instances
    if len(instances) == 1:
        _connect_instance(instances[0])  # reruns on success


def _connect_instance(inst: DesktopInstance) -> None:
    try:
        with st.spinner(f"从端口 {inst.port} 读取模型…"):
            ctx = LiveDesktopSource(inst.port).load()
    except ModuleNotFoundError as e:
        st.error(f"缺少依赖：{e}. 运行 `pip install -r requirements.txt`（需要 pythonnet）")
        return
    except Exception as e:  # noqa: BLE001 — surface connection/query errors
        st.error(f"读取失败：{type(e).__name__}: {e}")
        return
    if not ctx.tables:
        st.warning("已连接，但未读到任何表。")
    st.session_state.model_ctx = ctx
    st.session_state.model_ctx_port = inst.port
    st.rerun()  # refresh so the traffic light flips to green immediately


def render_capabilities(cfg: RuntimeConfig, ctx: ModelContext | None) -> None:
    """Render one tab per registered capability. New phases light up here with no change to this code."""
    caps = registry.all_capabilities()
    if not caps:
        return
    tabs = st.tabs([cap.name for cap in caps])
    for tab, cap in zip(tabs, caps):
        with tab:
            _render_capability(cap, cfg, ctx)


def _render_capability(cap: Capability, cfg: RuntimeConfig, ctx: ModelContext | None) -> None:
    if ctx is None:
        st.info("👈 请先在左侧「📂 模型来源」连接 Power BI Desktop 模型。")
        return
    if not cfg.is_ready:
        st.info("👈 请先在左侧「⚙️ 模型设置」配置大模型与 API Key。")
        return

    for action in cap.actions():
        if action.id == "generate":
            # Mode switch + chat toggles live in a keyed container that theme.py pins to the top
            # (`st-key-dax_topbar`), so they stay put while the chat history scrolls underneath.
            with st.container(key="dax_topbar"):
                mode = st.radio(
                    "生成模式", ["💬 基础 DAX 生成", "🎯 校准式生成"],
                    horizontal=True, key="dax_mode", label_visibility="collapsed",
                )
                chat_toggles = _render_chat_toggles() if mode.startswith("💬") else None
            if mode.startswith("💬"):
                assert chat_toggles is not None
                _render_dax_chat(cfg, ctx, *chat_toggles)
            else:
                _render_dax_calibrate(cfg, ctx)
        else:
            # explain / optimize panels land in M5; until then, note the action exists.
            st.caption(f"（能力「{action.label}」将在后续里程碑接入）")


def _render_chat_toggles() -> tuple[bool, bool]:
    """The chat's two toggles (write-back, deep-thinking), rendered inside the pinned top bar.
    Returns (write_on, deep_think)."""
    port = st.session_state.get("model_ctx_port")
    write_on = st.toggle(
        "✍️ 写入 Power BI（开启后，验证通过的度量值可一键写入当前模型）",
        value=st.session_state.get("chat_write_on", False),
        key="chat_write_on", disabled=port is None,
        help="会修改当前打开的模型；写入后请在 Desktop 按 Ctrl+S 保存。" if port else "需先连接 Power BI Desktop。",
    )
    deep_think = st.toggle(
        "🧠 深度思考（更准但更慢）",
        value=st.session_state.get("chat_deep_think", False),
        key="chat_deep_think",
        help="开启后让模型在作答前进行内部推理（如千问思考模式），适合复杂度量值；默认关闭以求快速响应。",
    )
    return write_on, deep_think


def _submit_chat() -> None:
    """Composer submit callback (Enter or send icon): stash the trimmed text as the pending prompt and
    clear the input box. Runs before widgets re-instantiate, so resetting `dax_gen_text` is allowed."""
    text = str(st.session_state.get("dax_gen_text", "")).strip()
    if text:
        st.session_state["_chat_pending"] = text
    st.session_state["dax_gen_text"] = ""


def _clear_chat_input() -> None:
    """Cancel the unsent draft: empty the composer (callback → safe to reset the widget key)."""
    st.session_state["dax_gen_text"] = ""


def _render_dax_chat(cfg: RuntimeConfig, ctx: ModelContext, write_on: bool, deep_think: bool) -> None:
    """A general grounded chat: ask anything, get reasoning + a measure, auto run-verified; with the write
    toggle on, a validated measure can be written straight into the open Power BI model. The two toggles
    are rendered by the pinned top bar (`_render_chat_toggles`) and passed in."""
    port = st.session_state.get("model_ctx_port")

    msgs: list[dict] = st.session_state.setdefault("chat_msgs", [])
    # Clear-conversation control above the history (right-aligned, disabled when already empty).
    _, c_clear = st.columns([4, 1])
    with c_clear:
        if st.button("🗑 清除对话", key="chat_clear", use_container_width=True, disabled=not msgs):
            st.session_state["chat_msgs"] = []
            st.rerun()
    # History lives in a fixed-height scroll box, so the top controls and the bottom composer stay put
    # by construction — they're outside the scrolling region. Far more reliable than CSS sticky.
    chat_box = st.container(height=620, key="chat_box")
    with chat_box:
        for i, m in enumerate(msgs):
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m["role"] == "assistant" and m.get("items"):
                    _render_chat_items(i, m, ctx, port, write_on)

    # A text_input composer (keyed `dax_gen_text`) so the sidebar field browser can insert
    # 'Table'[Column] references into it. Enter (on_change) and the send icon (on_click) both go
    # through `_submit_chat`, which stashes the text and clears the box — clearing the widget key is
    # allowed inside a callback (it runs before the widget is re-instantiated). Wrapped in a keyed
    # container (`st-key-dax_composer`) so theme.py can pin it to the bottom.
    with st.container(key="dax_composer"):
        c_in, c_cancel, c_btn = st.columns([18, 1, 1], vertical_alignment="center")
        with c_in:
            st.text_input(
                "消息", key="dax_gen_text", label_visibility="collapsed",
                placeholder="问我任何 Power BI / DAX 问题…（左侧点字段可插入引用，回车发送）",
                on_change=_submit_chat,
            )
        with c_cancel:
            st.button(":material/close:", key="dax_cancel_btn", on_click=_clear_chat_input,
                      help="取消发送（清空输入）", use_container_width=True)
        with c_btn:
            st.button(":material/send:", key="dax_send_btn", on_click=_submit_chat,
                      help="发送（也可按回车）", use_container_width=True)
    prompt = st.session_state.pop("_chat_pending", None)
    if prompt:
        msgs.append({"role": "user", "content": prompt})
        with chat_box:
            st.chat_message("user").markdown(prompt)
            assistant_box = st.chat_message("assistant")
        with assistant_box:
            try:
                provider = build_provider(cfg)
            except Exception as e:  # noqa: BLE001
                st.error(f"无法初始化模型：{e}")
                msgs.pop()  # drop the dangling user turn
                return
            system = build_chat_system_prompt(ctx.serialize_for_prompt())
            history = [
                ChatMessage(role=x["role"], content=x["content"]) for x in msgs[-12:]  # bound context
            ]
            try:
                text = st.write_stream(provider.stream(
                    system=system, messages=history, max_tokens=4000, enable_thinking=deep_think,
                ))
            except Exception as e:  # noqa: BLE001 — surface provider/auth/stream errors
                st.error(f"生成失败：{type(e).__name__}: {e}")
                msgs.pop()
                return
        entry: dict = {"role": "assistant", "content": str(text)}
        # A reply may contain measures (scalar) AND/OR a calculated table (e.g. a date table). Split into
        # items, classify each, and validate it the right way — a table via EVALUATE, a measure via the
        # set-validator (which isolates a syntactically-broken sibling).
        if has_dax_block(str(text)):
            # One object per ```dax block (no within-block splitting). Default a name if the model omitted it.
            parts = parse_dax_blocks(str(text))
            items: list[dict[str, Any]] = [
                {"name": n or f"度量值_{i + 1}", "expr": e,
                 "kind": "table" if is_table_expression(e) else "measure"}
                for i, (n, e) in enumerate(parts)
            ]
            if items:
                entry["items"] = items
                if port:
                    home = next(iter(ctx.tables), "")
                    evaluator = LiveDesktopEvaluator(port)
                    scalars = [(it["name"], it["expr"]) for it in items if it["kind"] == "measure"]
                    with st.spinner("实跑 EVALUATE 验证…"):
                        scalar_vrs = dict(zip(
                            [n for n, _ in scalars], validate_measure_set(evaluator, home, scalars)
                        ))
                        for it in items:
                            it["validation"] = (
                                evaluator.evaluate_table_expr(it["expr"]) if it["kind"] == "table"
                                else scalar_vrs[it["name"]]
                            )
        msgs.append(entry)
        st.rerun()


def _render_chat_items(i: int, m: dict, ctx: ModelContext, port: int | None, write_on: bool) -> None:
    """Render each generated object (measure or calculated table) with its run-verification and, when
    writing is on, the matching write control."""
    items: list[dict] = m["items"]
    if len(items) > 1:
        st.caption(f"本回复包含 {len(items)} 个对象：")

    for j, it in enumerate(items):
        name, expr, kind = it["name"], it["expr"], it["kind"]
        vr = it.get("validation")
        ok = bool(vr and vr.run_verified and vr.ok)
        label = "计算表" if kind == "table" else "度量值"
        st.markdown(f"**{label}：** `{name}`")
        st.code(f"{name} = {expr}", language="dax")
        if vr is not None:
            if ok:
                msg = f"✅ 实跑验证通过：返回 {vr.sample}" if kind == "table" else f"✅ 实跑验证通过：EVALUATE = {vr.sample}"
                st.success(msg)
            elif vr.run_verified:
                st.error("❌ 实跑失败（引擎报错）：" + "；".join(vr.errors))
        elif port is None:
            st.caption("ⓘ 未连引擎，未实跑验证。")

        if write_on and port and ok:
            with st.expander(f"✍️ 写入「{name}」到模型", expanded=False):
                wname = st.text_input("名称", value=name, key=f"wt_name_{i}_{j}")
                if kind == "table":
                    if st.button("写入计算表", key=f"wt_btn_{i}_{j}", type="primary", disabled=not wname.strip()):
                        res = LiveDesktopWriter(port).write_calculated_table(wname.strip(), expr)
                        (st.success if res.ok else st.error)(res.detail)
                else:
                    table = st.selectbox("目标表", list(ctx.tables), key=f"wt_tbl_{i}_{j}")
                    if st.button("写入度量值", key=f"wt_btn_{i}_{j}", type="primary", disabled=not wname.strip()):
                        res = LiveDesktopWriter(port).write_measure(table, wname.strip(), expr)
                        (st.success if res.ok else st.error)(res.detail)


# match rule label -> (rel_tol, abs_tol) for calibration hit detection
_MATCH_TOL: dict[str, tuple[float, float]] = {
    "相对 0.01%（推荐）": (1e-4, 0.01),
    "相对 0.1%": (1e-3, 0.01),
    "四舍五入到 2 位小数": (0.0, 0.005),
    "完全相等": (1e-9, 1e-9),
}


def _render_dax_calibrate(cfg: RuntimeConfig, ctx: ModelContext) -> None:
    """Calibrated generation: the user gives a known-correct value at a slice; the AI iterates (and asks
    when needed) until the measure reproduces it. Requires a live engine for slice evaluation."""
    port = st.session_state.get("model_ctx_port")
    if not port:
        st.info("🎯 校准式生成需要实时引擎来在切片下验证。请先在左侧连接 Power BI Desktop。")
        return

    sess: CalibrationSession | None = st.session_state.get("cal_session")
    if sess is None:
        _render_calibrate_setup(cfg, ctx, port)
    else:
        _render_calibrate_thread(sess, cfg, ctx, port)


def _cached_column_values(port: int, table: str, column: str) -> list:
    key = f"cal_vals::{table}::{column}"
    if key not in st.session_state:
        try:
            st.session_state[key] = LiveDesktopSource(port).column_values(table, column)
        except Exception:  # noqa: BLE001
            st.session_state[key] = []
    return st.session_state[key]


def _render_calibrate_setup(cfg: RuntimeConfig, ctx: ModelContext, port: int) -> None:
    st.markdown(
        "**用「已知正确值」校准。** 描述需求，再给一个你手算确认过的切片值——AI 会反复实跑验证、"
        "必要时反问你，倒逼出准确口径，直到算对。"
    )
    request = st.text_area("业务需求", key="cal_request", placeholder="例如：本年度已审批的采购总额", height=80)

    eyebrow("校准切片 · 你确定答案的那个口径")
    filters: list = st.session_state.setdefault("cal_filters", [])
    c1, c2, c3 = st.columns(3)
    table = c1.selectbox("表", list(ctx.tables), key="cal_f_table")
    columns = [c.name for c in ctx.tables.get(table, [])]
    column = c2.selectbox("列", columns, key="cal_f_col")
    values = _cached_column_values(port, table, column) if column else []
    value = c3.selectbox("值", values, key="cal_f_val", format_func=str) if values else None
    bcol1, bcol2 = st.columns([3, 1])
    if bcol1.button("➕ 添加筛选条件", use_container_width=True) and value is not None:
        filters.append((table, column, value))
        st.rerun()
    if filters and bcol2.button("清空", use_container_width=True):
        st.session_state.cal_filters = []
        st.rerun()
    if filters:
        st.caption("当前切片：" + slice_desc(filters))

    ec1, ec2 = st.columns([2, 2])
    expected = ec1.number_input("该切片下的正确值", value=0.0, format="%.5f", key="cal_expected")
    match_mode = ec2.selectbox(
        "匹配规则", list(_MATCH_TOL), key="cal_match",
        help="命中判定的容差。值很大时建议用相对容差；金额到分用「四舍五入到 2 位」。",
    )
    rel_tol, abs_tol = _MATCH_TOL[match_mode]

    if st.button("开始校准", type="primary", disabled=not request.strip() or not filters):
        try:
            provider = build_provider(cfg)
        except Exception as e:  # noqa: BLE001
            st.error(f"无法初始化模型：{e}")
            return
        sess = CalibrationSession(
            request=request.strip(), filters=list(filters), expected=float(expected),
            home_table=next(iter(ctx.tables)), rel_tol=rel_tol, abs_tol=abs_tol,
        )
        if _run_calibration(sess, cfg, ctx, port, provider=provider):
            st.session_state.cal_session = sess
            st.session_state.cal_filters = []
            st.rerun()


def _render_calibrate_thread(sess: CalibrationSession, cfg: RuntimeConfig, ctx: ModelContext, port: int) -> None:
    # Keep the original request + calibration target visible the whole time, so the user can reason
    # about the AI's questions without losing what they asked for.
    st.markdown(f"**你的需求**：{sess.request}")
    st.caption(f"🎯 校准目标：在 {slice_desc(sess.filters)} 下应等于 {sess.expected}")
    st.divider()
    _render_calibrate_transcript(sess)

    # Same chat box as the AI 对话 mode — bottom-anchored, submit on Enter.
    if sess.status == "asking":
        reply = st.chat_input("回答上面的问题以继续校准…")
        if reply and reply.strip():
            if _run_calibration(sess, cfg, ctx, port, user_reply=reply.strip()):
                st.rerun()
    elif sess.status == "passed":
        st.success("✅ 已用你的标准值验证：上方度量值在此切片下算出的值与你给的正确值一致。")
        refine = st.chat_input("继续优化 / 调整（用 DIVIDE、提升性能、加注释、改口径…）")
        if refine and refine.strip():
            if _run_calibration(sess, cfg, ctx, port, refine_request=refine.strip()):
                st.rerun()

    if st.button("↺ 重新开始"):
        st.session_state.pop("cal_session", None)
        st.rerun()


def _render_calibrate_transcript(sess: CalibrationSession) -> None:
    for e in sess.transcript:
        kind = e.get("kind")
        if kind == "measure":
            st.markdown("**AI 候选度量值**")
            st.code(e["text"], language="dax")
        elif kind == "result":
            if e.get("ok"):
                st.success(f"实跑值 {e['text']} ＝ 期望 {sess.expected} ✓")
            else:
                actual = e.get("actual")
                if isinstance(actual, (int, float)):
                    diff = actual - sess.expected
                    pct = (diff / sess.expected * 100) if sess.expected else float("inf")
                    st.error(
                        f"实跑值 **{e['text']}** ≠ 期望 **{sess.expected}**　·　差 {diff:+,.4f}（{pct:+.4f}%）"
                    )
                else:
                    st.error(f"实跑值 {e['text']} ≠ 期望 {sess.expected}")
        elif kind == "question":
            st.info("AI 提问：" + e["text"])
        elif kind == "answer":
            st.caption("你的回答：" + e["text"])
        elif kind == "refine":
            st.caption("你的优化要求：" + e["text"])


def _run_calibration(
    sess: CalibrationSession, cfg: RuntimeConfig, ctx: ModelContext, port: int,
    *, provider=None, user_reply: str | None = None, refine_request: str | None = None,
) -> bool:
    """Advance the session one step, surfacing errors. Returns True on success (caller reruns)."""
    try:
        if provider is None:
            provider = build_provider(cfg)
        evaluator = LiveDesktopEvaluator(port)
        with st.spinner("生成并在切片下实跑验证…"):
            advance(
                sess, provider=provider, evaluator=evaluator, context=ctx,
                user_reply=user_reply, refine_request=refine_request,
            )
    except ModuleNotFoundError as e:
        st.error(f"缺少依赖：{e}. 运行 `pip install -r requirements.txt`")
        return False
    except Exception as e:  # noqa: BLE001 — surface provider/engine errors
        st.error(f"校准失败：{type(e).__name__}: {e}")
        return False
    st.session_state.cal_session = sess
    return True


def _test_connection(cfg: RuntimeConfig) -> None:
    if not cfg.is_ready:
        st.warning("请先填写模型与 API Key")
        return
    try:
        provider = build_provider(cfg)
        reply = provider.complete(
            system="You are a connectivity probe. Reply with exactly: OK",
            messages=[user("Reply with OK.")],
            max_tokens=16,
        )
        st.success(f"连接成功 ✅ 模型回复：{reply.strip()[:40]}")
    except ModuleNotFoundError as e:  # SDK not installed
        st.error(f"缺少依赖：{e}. 运行 `pip install -r requirements.txt`")
    except Exception as e:  # noqa: BLE001 — surface any provider/auth error to the user
        st.error(f"连接失败：{type(e).__name__}: {e}")
