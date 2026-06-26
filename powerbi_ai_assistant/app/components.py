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
    CalibrationPoint,
    CalibrationSession,
    DaxCapability,
    LiveDesktopEvaluator,
    advance,
    has_dax_block,
    is_table_expression,
    measure_expression,
    parse_dax_blocks,
    slice_desc,
    validate_measure_set,
)
from ..dax.prompts import build_chat_system_prompt
from ..mquery import MQueryCapability, MScriptArtifact, has_m_block, parse_m_blocks
from ..mquery.prompts import build_chat_system_prompt as build_m_chat_system_prompt
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
    """Register the capabilities once. Idempotent — Streamlit reruns the script every interaction, so a
    second `register()` (which rejects duplicate ids) would otherwise crash. Each registered capability
    becomes a tab automatically (see `render_capabilities`)."""
    # registration order = tab order (left→right). Power Query 助手 first, then DAX 助手.
    if "mquery" not in registry.CAPABILITIES:
        registry.register(MQueryCapability())
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
            # Show only the panel for the active assistant: Power Query 助手 → 查询 browser;
            # DAX 助手 → Power Pivot 模型 browser. `active_cap` is set by render_capabilities (which
            # runs after this sidebar), so on the first run fall back to the first registered capability.
            active = st.session_state.get("active_cap")
            if active not in registry.CAPABILITIES:
                caps = registry.all_capabilities()
                active = caps[0].id if caps else None
            if active == "mquery":
                eyebrow("Power Query · 查询")
                _render_query_browser(ctx)
            else:
                eyebrow("Power Pivot · 模型")
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


def _render_query_browser(ctx: ModelContext) -> None:
    """Power Query side of the sidebar: the loaded queries grouped by their query-group folder, each with
    its column / M-line counts. Only queries LOADED into the model are visible to the live engine —
    load-disabled staging queries and parameters won't appear (a live-connection limitation, stated)."""
    if not ctx.table_queries:
        st.caption("未读到 Power Query 查询（或仅有计算表/无 M 的表）。")
        return
    # group loaded queries by folder; ungrouped ones go under "（未分组）"
    folders: dict[str, list[str]] = {}
    for q in ctx.table_queries:
        folders.setdefault(ctx.query_folders.get(q) or "（未分组）", []).append(q)
    st.caption(f"共 {len(ctx.table_queries)} 个已加载查询 · 点查询=设为清洗目标并展开列、点列名插入需求框")
    active = st.session_state.get("mq_browse_q")
    for folder in sorted(folders):
        queries = folders[folder]
        with st.expander(f"📁 {folder}（{len(queries)}）", expanded=False):
            for q in queries:
                cols = ctx.tables.get(q, [])
                nlines = len(ctx.table_queries[q].splitlines())
                opened = active == q
                # click a query to toggle its column list (one open at a time, keeps the sidebar tidy)
                if st.button(f"{'▾' if opened else '▸'} {q}　({len(cols)}列·{nlines}行M)",
                             key=f"mqbrowse_{q}", use_container_width=True):
                    st.session_state["mq_browse_q"] = None if opened else q
                    st.session_state["mq_query"] = q  # also make this the cleaning target in the PQ tab
                    st.rerun()
                if opened:
                    for c in cols:
                        if st.button(c.name, key=f"mqcol_{q}_{c.name}", help=c.dtype, use_container_width=True):
                            _insert_into_mq_request(f"[{c.name}]")


def _insert_into_request(ref: str) -> None:
    """Append a field reference to the DAX input box of the CURRENT mode, then rerun (the target widget is
    rendered later in the main pane, so it picks up the new value). Routes by the mode radio so a field
    click lands where the user is working: 基础 DAX 生成 → the chat composer (`dax_gen_text`); 校准式生成
    → the business-requirement box (`cal_request`). No more always-jumping to basic generation."""
    # NOTE: do NOT st.rerun() here. The sidebar renders before the main pane, so setting the target
    # widget's session_state now (before that widget is instantiated this run) makes it pick up the value
    # in the SAME run. Calling st.rerun() mid-sidebar instead aborts the run before the mode radio renders,
    # which desyncs `dax_mode` (radio showed 校准 but the body rendered 基础). The button click already reruns.
    key = "cal_request" if "校准" in str(st.session_state.get("dax_mode", "")) else "dax_gen_text"
    current = st.session_state.get(key, "")
    sep = "" if (not current or current.endswith((" ", "\n"))) else " "
    st.session_state[key] = current + sep + ref + " "


def _insert_into_mq_request(ref: str) -> None:
    """Append a column reference to the Power Query cleaning composer (keyed `mq_gen_text`), then rerun —
    the composer is rendered later in the main pane, so it picks up the new value on the next run."""
    current = st.session_state.get("mq_gen_text", "")
    sep = "" if (not current or current.endswith((" ", "\n"))) else " "
    st.session_state.mq_gen_text = current + sep + ref + " "
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


def _resync_model() -> None:
    """Re-read the model from the open Desktop engine so the assistant sees the user's latest APPLIED M.

    Power Query (M) edits the user makes in Desktop only reach the engine after they Apply (Save → 应用).
    The assistant caches the model at connect time and does not auto-refresh, so this button re-reads the
    cached port and updates the shared `model_ctx`. Core enabler of the "我为主 + AI 补难点" loop (痛点1)."""
    port = st.session_state.get("model_ctx_port")
    if not port:
        st.warning("尚未连接 Power BI Desktop，无法同步。")
        return
    try:
        with st.spinner("从 Desktop 重新读取已应用的查询…"):
            ctx = LiveDesktopSource(port).load()
    except Exception as e:  # noqa: BLE001 — surface connection/query errors
        st.error(f"同步失败：{type(e).__name__}: {e}")
        return
    st.session_state.model_ctx = ctx
    st.toast("已从 Desktop 同步最新模型")
    st.rerun()


def render_capabilities(cfg: RuntimeConfig, ctx: ModelContext | None) -> None:
    """Render the selected capability. A segmented control (not `st.tabs`) drives the choice, because the
    server must know which assistant is active so the sidebar can show only that assistant's panel
    (`st.tabs` renders every tab and never tells the server which one the user clicked). The selection is
    stored under `active_cap` (a capability id) which the sidebar reads — see `render_model_source_sidebar`."""
    caps = registry.all_capabilities()
    if not caps:
        return
    # Pre-seed the active capability so the sidebar (which renders before this) has a value to read.
    if st.session_state.get("active_cap") not in registry.CAPABILITIES:
        st.session_state["active_cap"] = caps[0].id
    active = st.session_state["active_cap"]

    # A top "main menu" of plain buttons (full click area, fully style-controllable) instead of
    # st.segmented_control (whose thin button group was hard to click). The active one is gold (primary),
    # the rest are ghost. The keyed container `cap_nav` is styled as a separated nav bar in theme.py.
    # Each capability gets a representative icon: Σ (functions) for DAX measures, cleaning for Power Query.
    # Short nav labels (cap.name is the full "… 助手" used elsewhere; the top menu stays compact).
    nav_icons = {"dax": ":material/functions:", "mquery": ":material/cleaning_services:"}
    nav_labels = {"dax": "DAX", "mquery": "PQ"}
    with st.container(key="cap_nav"):
        cols = st.columns([1] * len(caps) + [max(1, 6 - len(caps))])
        for col, cap in zip(cols, caps):
            is_active = cap.id == active
            if col.button(nav_labels.get(cap.id, cap.name), key=f"nav_{cap.id}", use_container_width=True,
                          icon=nav_icons.get(cap.id), type="primary" if is_active else "secondary"):
                if not is_active:
                    st.session_state["active_cap"] = cap.id
                    st.rerun()

    _render_capability(registry.get(active), cfg, ctx)


def _render_capability(cap: Capability, cfg: RuntimeConfig, ctx: ModelContext | None) -> None:
    if ctx is None:
        st.info("👈 请先在左侧「📂 模型来源」连接 Power BI Desktop 模型。")
        return
    if not cfg.is_ready:
        st.info("👈 请先在左侧「⚙️ 模型设置」配置大模型与 API Key。")
        return

    if cap.id == "dax":
        _render_dax_capability(cfg, ctx)
    elif cap.id == "mquery":
        _render_mquery_capability(cfg, ctx)
    else:
        st.caption(f"（能力「{cap.name}」将在后续里程碑接入）")


def _render_dax_capability(cfg: RuntimeConfig, ctx: ModelContext) -> None:
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


def _render_chat_toggles() -> tuple[bool, bool]:
    """The chat's two toggles (write-back, deep-thinking), rendered inside the pinned top bar.
    Returns (write_on, deep_think)."""
    port = st.session_state.get("model_ctx_port")
    c1, c2 = st.columns(2)
    with c1:
        write_on = st.toggle(
            "✍️ 写入 Power BI",
            value=st.session_state.get("chat_write_on", False),
            key="chat_write_on", disabled=port is None,
            help="会修改当前打开的模型；写入后请在 Desktop 按 Ctrl+S 保存。" if port else "需先连接 Power BI Desktop。",
        )
    with c2:
        deep_think = st.toggle(
            "🧠 深度思考",
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
    chat_box = st.container(height=440, key="chat_box")
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
        c_in, c_cancel, c_btn = st.columns([20, 2, 2], vertical_alignment="center")
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


# =================================================================================================
# Phase 2 — data cleaning (Power Query / M). Mirrors the DAX chat: ask in natural language, get a grounded
# M query, run-verified by a real refresh round-trip, with one-click write-back into the open model.
# =================================================================================================

def _render_mquery_capability(cfg: RuntimeConfig, ctx: ModelContext) -> None:
    if not ctx.table_queries:
        st.info("当前模型没有可清洗的 Power Query 查询（仅有计算表/无 M 的表）。")
        return
    # Top bar (pinned by theme.py via `st-key-mq_topbar`): pick the query to clean, a re-sync button, toggles.
    with st.container(key="mq_topbar"):
        c_sel, c_sync = st.columns([5, 1], vertical_alignment="bottom")
        with c_sel:
            query_name = st.selectbox(
                "要清洗的查询", list(ctx.table_queries), key="mq_query",
                help="选择一个现有 Power Query 查询作为清洗起点；AI 在它当前已应用的 M 之上补步骤。",
            )
        with c_sync:
            if st.button("🔄 同步", key="mq_resync", use_container_width=True,
                         help="你在 Desktop 改完查询并点「应用」后，按这里重读最新的 M（助手不会自动刷新）"):
                _resync_model()
        deep_think = _render_mq_toggles()
    # Switching the target query starts a fresh conversation, so prior steps don't bleed across queries.
    if st.session_state.get("mq_active_query") != query_name:
        st.session_state["mq_active_query"] = query_name
        st.session_state["mq_msgs"] = []
    _render_mquery_chat(cfg, ctx, query_name, deep_think)


def _render_mq_toggles() -> bool:
    """The cleaning chat's deep-thinking toggle. Returns deep_think.

    There is intentionally NO write-back toggle here: writing M into an OPEN Power BI Desktop model via the
    external connection crashes Desktop's Mashup query navigator (verified — NullReferenceException in
    `Microsoft.Mashup.Client.UI...QueriesNavigatorModelBase`); editing Power Query externally on Desktop is
    unsupported. The verified M is offered for the user to copy into the Advanced Editor instead."""
    deep_think = st.toggle(
        "🧠 深度思考（更准但更慢）",
        value=st.session_state.get("mq_deep_think", False),
        key="mq_deep_think",
        help="开启后让模型在作答前进行内部推理，适合复杂清洗；默认关闭以求快速响应。",
    )
    return deep_think


def _submit_mq_chat() -> None:
    """Composer submit callback for the cleaning chat: stash trimmed text as pending, clear the input."""
    text = str(st.session_state.get("mq_gen_text", "")).strip()
    if text:
        st.session_state["_mq_pending"] = text
    st.session_state["mq_gen_text"] = ""


def _clear_mq_input() -> None:
    st.session_state["mq_gen_text"] = ""


def _render_mquery_chat(
    cfg: RuntimeConfig, ctx: ModelContext, query_name: str, deep_think: bool
) -> None:
    """Grounded data-cleaning chat for one query: describe the cleaning, get an M query, run-verified by a
    real Desktop refresh round-trip. The verified M is shown for the user to copy into Power Query's Advanced
    Editor — there is no direct write-back (it would crash Desktop's Mashup navigator; see _render_mq_toggles)."""
    port = st.session_state.get("model_ctx_port")

    msgs: list[dict] = st.session_state.setdefault("mq_msgs", [])
    _, c_clear = st.columns([4, 1])
    with c_clear:
        if st.button("🗑 清除对话", key="mq_clear", use_container_width=True, disabled=not msgs):
            st.session_state["mq_msgs"] = []
            st.rerun()

    chat_box = st.container(height=440, key="mq_chat_box")
    with chat_box:
        st.caption(f"正在清洗查询：`{query_name}` · 共 {len(ctx.table_queries[query_name].splitlines())} 行 M")
        for i, m in enumerate(msgs):
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m["role"] == "assistant" and m.get("items"):
                    _render_mq_items(i, m, ctx, port, query_name)

    with st.container(key="mq_composer"):
        c_in, c_cancel, c_btn = st.columns([20, 2, 2], vertical_alignment="center")
        with c_in:
            st.text_input(
                "消息", key="mq_gen_text", label_visibility="collapsed",
                placeholder="描述要做的清洗，例如：去掉客户编号为空的行，并把订单日期改成日期类型（回车发送）",
                on_change=_submit_mq_chat,
            )
        with c_cancel:
            st.button(":material/close:", key="mq_cancel_btn", on_click=_clear_mq_input,
                      help="取消发送（清空输入）", use_container_width=True)
        with c_btn:
            st.button(":material/send:", key="mq_send_btn", on_click=_submit_mq_chat,
                      help="发送（也可按回车）", use_container_width=True)

    prompt = st.session_state.pop("_mq_pending", None)
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
                msgs.pop()
                return
            grounding = ctx.serialize_query_for_prompt(query_name)
            system = build_m_chat_system_prompt(grounding, query_name)
            history = [ChatMessage(role=x["role"], content=x["content"]) for x in msgs[-10:]]
            try:
                text = st.write_stream(provider.stream(
                    system=system, messages=history, max_tokens=4000, enable_thinking=deep_think,
                ))
            except Exception as e:  # noqa: BLE001
                st.error(f"生成失败：{type(e).__name__}: {e}")
                msgs.pop()
                return
        entry: dict = {"role": "assistant", "content": str(text)}
        if has_m_block(str(text)):
            blocks = parse_m_blocks(str(text))
            items: list[dict[str, Any]] = [{"code": b} for b in blocks if b.strip()]
            if items:
                entry["items"] = items
                # Live refresh verification is DISABLED: the temp-table probe it needs gets synced into
                # Desktop's Mashup document (Section1) and can't be removed from there via TOM, so it leaks a
                # `__pbi_ai_mq_probe` query that crashes Desktop's query navigator. Static lint only; the user
                # applies in Desktop, which is what truly verifies. See memory: mquery-refresh-verification.
                for it in items:
                    it["validation"] = MScriptArtifact(it["code"], name=query_name).validate(ctx)
        msgs.append(entry)
        st.rerun()


def _render_mq_items(
    i: int, m: dict, ctx: ModelContext, port: int | None, query_name: str
) -> None:
    """Render each generated M query with its refresh-verification. The code block has Streamlit's built-in
    copy button; the user applies it by pasting into Power Query's Advanced Editor (no direct write-back —
    that crashes Desktop's Mashup navigator; see _render_mq_toggles)."""
    items: list[dict] = m["items"]
    if len(items) > 1:
        st.caption(f"本回复包含 {len(items)} 个查询：")

    for j, it in enumerate(items):
        code = it["code"]
        vr = it.get("validation")
        static_ok = bool(vr and vr.ok)  # static lint passed (run_verified is always False now)
        st.code(code, language="powerquery")  # the code block carries a built-in copy button (top-right)
        if vr is not None:
            if static_ok:
                st.info("✓ 静态校验通过（结构/列引用 grounding）。未实跑——在 Desktop 应用后由它真正验证。")
            else:
                st.error("❌ 静态校验未过：" + "；".join(vr.errors))
            for w in (vr.warnings or []):
                st.caption("⚠ " + w)

        if static_ok:
            st.caption(
                f"📋 复制上面的 M（代码框右上角按钮），在 Desktop 里 `主页 → 转换数据` → 选中查询 "
                f"`{query_name}` → `高级编辑器` → 全选粘贴 → `完成` → `关闭并应用`（应用时即完成真正验证）。"
            )


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

    write_on, deep_think = _render_cal_toggles(port)
    sess: CalibrationSession | None = st.session_state.get("cal_session")
    if sess is None:
        _render_calibrate_setup(cfg, ctx, port, deep_think)
    else:
        sess.deep_think = deep_think   # let the live toggle steer an in-flight session
        _render_calibrate_thread(sess, cfg, ctx, port, write_on)


def _render_cal_toggles(port: int | None) -> tuple[bool, bool]:
    """Calibration's two toggles: one-click write-back + deep thinking. Returns (write_on, deep_think).
    Deep thinking defaults ON here — calibration is exactly where the extra reasoning earns its cost."""
    c1, c2 = st.columns(2)
    with c1:
        write_on = st.toggle(
            "✍️ 写入 Power BI",
            value=st.session_state.get("cal_write_on", False), key="cal_write_on", disabled=not port,
            help="开启后，校准命中的度量值可一键写入当前打开的模型（写完在 Desktop 按 Ctrl+S 保存）。",
        )
    with c2:
        deep_think = st.toggle(
            "🧠 深度思考",
            value=st.session_state.get("cal_deep_think", True), key="cal_deep_think",
            help="校准默认开启深度思考——让模型反复推敲口径、少绕几轮自动修正；可临时关掉求快。",
        )
    return write_on, deep_think


def _cached_column_values(port: int, table: str, column: str) -> list:
    key = f"cal_vals::{table}::{column}"
    if key not in st.session_state:
        try:
            st.session_state[key] = LiveDesktopSource(port).column_values(table, column)
        except Exception:  # noqa: BLE001
            st.session_state[key] = []
    return st.session_state[key]


def _render_calibrate_setup(cfg: RuntimeConfig, ctx: ModelContext, port: int, deep_think: bool = True) -> None:
    st.markdown(
        "**用「已知正确值」校准。** 描述需求，再给一个或多个你手算确认过的切片值（**多点校准**：要求"
        "生成的度量值在每个切片都算对）——AI 会反复实跑验证、必要时反问你，倒逼出准确口径。"
    )
    request = st.text_area("业务需求", key="cal_request", placeholder="例如：本年度已审批的采购总额", height=80)

    points: list = st.session_state.setdefault("cal_points", [])  # list[(filters, expected)]

    eyebrow("校准点 · 一个切片 + 该切片下你确定的正确值")
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
    if filters and bcol2.button("清空筛选", use_container_width=True):
        st.session_state.cal_filters = []
        st.rerun()
    st.caption("当前切片：" + (slice_desc(filters) if filters else "（请至少加一个筛选条件）"))

    expected = st.number_input("该切片下的正确值", value=0.0, format="%.5f", key="cal_expected")
    # Place "添加为校准点" directly below the value box, at the same width as "添加筛选条件" (the [3, 1] split).
    acol1, _ = st.columns([3, 1])
    if acol1.button("➕ 添加为校准点", use_container_width=True, disabled=not filters):
        points.append((list(filters), float(expected)))
        st.session_state.cal_filters = []   # reset the slice builder for the next point
        st.rerun()

    if points:
        eyebrow(f"已添加 {len(points)} 个校准点（需全部命中）")
        for i, (f, e) in enumerate(points):
            pc1, pc2 = st.columns([8, 1])
            pc1.caption(f"#{i + 1}　{slice_desc(f)} → **{e}**")
            if pc2.button("✕", key=f"cal_rm_{i}", help="删除该校准点"):
                points.pop(i)
                st.rerun()

    match_mode = st.selectbox(
        "匹配规则", list(_MATCH_TOL), key="cal_match",
        help="命中判定的容差（对所有校准点统一生效）。值很大时建议用相对容差；金额到分用「四舍五入到 2 位」。",
    )
    rel_tol, abs_tol = _MATCH_TOL[match_mode]

    if st.button("开始校准", type="primary", disabled=not request.strip() or not points):
        try:
            provider = build_provider(cfg)
        except Exception as e:  # noqa: BLE001
            st.error(f"无法初始化模型：{e}")
            return
        sess = CalibrationSession(
            request=request.strip(),
            points=[CalibrationPoint(filters=f, expected=e) for f, e in points],
            home_table=next(iter(ctx.tables)), rel_tol=rel_tol, abs_tol=abs_tol, deep_think=deep_think,
        )
        if _run_calibration(sess, cfg, ctx, port, provider=provider):
            st.session_state.cal_session = sess
            st.session_state.cal_points = []
            st.session_state.cal_filters = []
            st.rerun()


def _render_calibrate_thread(
    sess: CalibrationSession, cfg: RuntimeConfig, ctx: ModelContext, port: int, write_on: bool = False
) -> None:
    # Keep the original request + calibration target visible the whole time, so the user can reason
    # about the AI's questions without losing what they asked for. The targets reflect any mid-conversation
    # corrections (the controller mutates sess.points when the user fixes a value in chat).
    st.markdown(f"**你的需求**：{sess.request}")
    st.caption(f"🎯 校准目标（需全部命中，共 {len(sess.points)} 个）：")
    for i, p in enumerate(sess.points):
        st.caption(f"　#{i + 1}　{slice_desc(p.filters)} → **{p.expected}**")
    st.caption("💡 填错了标准值？直接在下面对话里说「第N个切片应该是 X」即可即时更正。")
    st.divider()
    _render_calibrate_transcript(sess)

    # Same chat box as the AI 对话 mode — bottom-anchored, submit on Enter.
    if sess.status == "asking":
        reply = st.chat_input("回答问题、或更正标准值（如「第2个切片应该是 34.28」）以继续校准…")
        if reply and reply.strip():
            if _run_calibration(sess, cfg, ctx, port, user_reply=reply.strip()):
                st.rerun()
    elif sess.status == "passed":
        st.success("✅ 已用你的标准值验证：上方度量值在每个切片下算出的值与你给的正确值一致。")
        if write_on:
            _render_cal_writeback(sess, ctx, port)
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
            pts = e.get("points") or []
            if pts:
                n_ok = sum(1 for p in pts if p["ok"])
                header = f"实跑验证：{n_ok}/{len(pts)} 命中"
                (st.success if e.get("ok") else st.error)(header + (" ✓" if e.get("ok") else ""))
                for i, p in enumerate(pts):
                    exp, act = p["expected"], p.get("actual")
                    if p["ok"]:
                        st.caption(f"　✓ 切片{i + 1} [{p['slice']}]：{p['actual_text']} ＝ {exp}")
                    else:
                        extra = ""
                        if isinstance(act, (int, float)) and isinstance(exp, (int, float)) and exp:
                            diff = act - exp
                            extra = f"　·　差 {diff:+,.4f}（{diff / exp * 100:+.2f}%）"
                        st.markdown(
                            f"　✗ 切片{i + 1} [{p['slice']}]：实跑 **{p['actual_text']}** ≠ 期望 **{exp}**{extra}"
                        )
            else:  # legacy fallback (no per-point data)
                (st.success if e.get("ok") else st.error)(f"实跑值 {e['text']}")
        elif kind == "question":
            st.info("AI 提问：" + e["text"])
        elif kind == "answer":
            st.caption("你的回答：" + e["text"])
        elif kind == "refine":
            st.caption("你的优化要求：" + e["text"])
        elif kind == "note":
            st.warning("✏️ " + e["text"])  # e.g. a mid-conversation target correction


def _render_cal_writeback(sess: CalibrationSession, ctx: ModelContext, port: int) -> None:
    """Write the calibrated (verified-correct) measure into the open model. Mirrors the chat write-back."""
    name = sess.candidate_name or "新度量值"
    expr = measure_expression(sess.candidate, sess.candidate_name)
    with st.expander(f"✍️ 写入「{name}」到模型", expanded=False):
        wname = st.text_input("名称", value=name, key="cal_wt_name")
        table = st.selectbox("目标表", list(ctx.tables), key="cal_wt_tbl")
        if st.button("写入度量值", key="cal_wt_btn", type="primary", disabled=not wname.strip()):
            res = LiveDesktopWriter(port).write_measure(table, wname.strip(), expr)
            (st.success if res.ok else st.error)(res.detail)


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
