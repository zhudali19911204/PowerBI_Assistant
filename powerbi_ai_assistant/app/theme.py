"""
Visual theme for the app — a single CSS injection plus a few markup helpers.

Direction: "precision instrument / engineering workbench" for a DAX assistant whose whole point is
run-verified output. Deep slate ink for structure, a deepened Power BI gold used sparingly as the one
accent, and a three-role type system (Space Grotesk display / Inter body / JetBrains Mono for the data
and DAX). Everything here is presentation only; behavior lives in components.py.
"""

from __future__ import annotations

import streamlit as st

_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root{
  --font-display:'Space Grotesk',system-ui,sans-serif;
  --font-body:'Inter',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,monospace;
  --ink:#1B1F2A; --ink-2:#3A4150; --muted:#737B8C;
  --paper:#F4F5F7; --surface:#FFFFFF; --border:#E5E8EE; --border-2:#EEF0F4;
  --accent:#E0A400; --accent-2:#FFC827; --accent-tint:#FBF1D5;
  --ok:#0E9F6E; --ok-tint:#E7F6EF; --bad:#D6453C; --bad-tint:#FBECEA;
}

/* base */
html, body, [data-testid="stAppViewContainer"], .stMarkdown, p, span, label, div {
  font-family:var(--font-body);
}
/* base colors come from the Streamlit theme (config.toml) so light AND dark both stay readable;
   we only layer fonts/accent/shape on top. */
[data-testid="stHeader"]{ background:transparent; }
.block-container{ padding-top:1rem; max-width:1180px; }
h1,h2,h3,h4{ font-family:var(--font-display); letter-spacing:-.02em; color:inherit; }

/* sidebar — keep the collapse control but kill the big default top gap above our header */
[data-testid="stSidebar"]{ border-right:1px solid var(--border); }
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{ padding-top:.3rem!important; padding-bottom:0!important; min-height:0!important; height:auto!important; }
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{ padding-top:0!important; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{ padding-top:.2rem!important; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div:first-child{ padding-top:0!important; margin-top:0!important; }

/* ---- brand header (sidebar) ---- */
.brand{ display:flex; align-items:center; gap:.6rem; }
.brand .mark{
  width:26px; height:26px; border-radius:8px; flex:0 0 auto;
  background:linear-gradient(150deg,var(--accent-2),var(--accent));
  box-shadow:0 3px 10px rgba(224,164,0,.35); position:relative;
}
.brand .mark::after{
  content:""; position:absolute; left:7px; bottom:6px; width:4px; height:8px; border-radius:1px;
  background:#1B1F2A; box-shadow:6px 0 0 #1B1F2A, 3px -3px 0 #1B1F2A; opacity:.85;  /* tiny bar-chart glyph */
}
.brand .name{ font-family:var(--font-display); font-weight:600; font-size:.98rem; color:inherit; line-height:1; }
.brand .name b{ color:var(--accent); font-weight:700; }
.brand-rule{ height:1px; background:linear-gradient(90deg,var(--accent) 0%,var(--border) 38%); margin:.55rem 0 .2rem; }

/* ---- model readout (instrument-style key/value) ---- */
.readout{ display:flex; flex-direction:column; gap:.2rem; margin:.45rem 0 .1rem; }
.readout .row{ display:flex; align-items:baseline; justify-content:space-between; gap:.7rem; font-size:.78rem; }
.readout .row > span{ color:var(--muted); letter-spacing:.02em; flex:0 0 auto; }
.readout .row > b{ font-weight:500; color:inherit; opacity:.85; text-align:right; word-break:break-all; }
.readout .row > b.mono{ font-family:var(--font-mono); font-size:.73rem; }
.readout .row > b.ok{ color:var(--ok); }
.readout .row > b.warn{ color:var(--accent); }

/* ---- section eyebrow ---- */
.eyebrow{
  font-family:var(--font-body); font-size:.7rem; font-weight:600; letter-spacing:.14em;
  text-transform:uppercase; color:var(--muted); margin:.2rem 0 .35rem; display:flex; align-items:center; gap:.45rem;
}
.eyebrow::before{ content:""; width:6px; height:6px; border-radius:50%; background:var(--accent); }

/* ---- hero (main) ---- */
.hero{ margin:-.3rem 0 1.1rem; }
.hero .kicker{
  font-size:.72rem; font-weight:600; letter-spacing:.18em; text-transform:uppercase; color:var(--accent);
}
.hero h1{ font-size:2.15rem; line-height:1.08; margin:.35rem 0 .5rem; font-weight:700; }
.hero h1 .em{ color:var(--ink); border-bottom:3px solid var(--accent); padding-bottom:1px; }
.hero p{ color:var(--muted); font-size:1rem; max-width:60ch; margin:0; }

/* ---- buttons ---- */
.stButton>button{
  border-radius:10px; font-weight:500; font-family:var(--font-body);
  border:1px solid var(--border);
  transition:border-color .15s, color .15s, background .15s, transform .04s;
}
.stButton>button:hover{ border-color:var(--accent); color:var(--accent); }
.stButton>button:active{ transform:translateY(1px); }
.stButton>button[kind="primary"], [data-testid="stBaseButton-primary"]{
  background:var(--accent)!important; color:#1B1F2A!important; border:1px solid var(--accent)!important;
}
.stButton>button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover{
  background:var(--accent-2)!important; border-color:var(--accent-2)!important; color:#1B1F2A!important;
}
/* sidebar settings gear: bigger, centered glyph, square */
.st-key-ui_gear_btn button{
  padding:.35rem 0!important; min-height:2.6rem;
  display:flex; align-items:center; justify-content:center;
}
.st-key-ui_gear_btn button p{ font-size:1.4rem!important; line-height:1; margin:0; }

/* inputs — keep a clear border so the box stands out; fill/text follow the theme (light or dark) */
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextInput"] [data-baseweb="base-input"]{
  border:1.5px solid var(--accent)!important; border-radius:10px!important; border-color:#C9CFDA!important;
}
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input{
  background:transparent!important; font-family:var(--font-body);
}
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTextInput"] [data-baseweb="base-input"]:focus-within{
  border-color:var(--accent)!important; box-shadow:0 0 0 3px var(--accent-tint)!important;
}

/* chat input — clear border so the box stands out; fill follows the theme */
[data-testid="stChatInput"]{
  border:1.5px solid #C9CFDA!important; border-radius:12px!important;
}
[data-testid="stChatInput"]:focus-within{
  border-color:var(--accent)!important; box-shadow:0 0 0 3px var(--accent-tint)!important;
}
[data-testid="stChatInput"] textarea{ background:transparent!important; }

/* Top controls and bottom composer are kept frozen by construction — the chat history sits in a
   fixed-height scroll box between them (see components._render_dax_chat), so neither moves. These rules
   are just light separators. */
.st-key-dax_topbar{ padding:.2rem 0 .4rem; border-bottom:1px solid var(--border); margin-bottom:.3rem; }
.st-key-dax_composer{ padding:.5rem 0 .2rem; }
/* the inline send icon — gold square that reads as the send affordance */
.st-key-dax_send_btn button{
  background:var(--accent)!important; border:1px solid var(--accent)!important; color:#1B1F2A!important;
  border-radius:10px!important; padding:.45rem 0!important;
}
.st-key-dax_send_btn button:hover{ background:var(--accent-2)!important; border-color:var(--accent-2)!important; }

/* code blocks → monospace data surface */
[data-testid="stCode"], pre{ border-radius:10px!important; border:1px solid var(--border)!important; }
code, kbd, pre, [data-testid="stCode"] *{ font-family:var(--font-mono)!important; }

/* expanders */
[data-testid="stExpander"]{ border:1px solid var(--border); border-radius:10px; }
[data-testid="stExpander"] summary{ font-weight:500; }

/* alerts: rounded with a left accent rule */
[data-testid="stAlert"]{ border-radius:10px; }

/* captions */
[data-testid="stCaptionContainer"]{ color:var(--muted); }

/* divider tighten */
hr{ margin:.8rem 0; border-color:var(--border-2); }
</style>
"""


def inject_theme() -> None:
    """Inject the global stylesheet. Call once, right after st.set_page_config. The app is light-only."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def brand_header() -> None:
    """The small brand lockup shown at the top of the sidebar, left of the settings gear."""
    st.markdown(
        '<div class="brand"><span class="mark"></span>'
        '<span class="name">Power BI <b>助手</b></span></div>',
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """A small uppercase section label."""
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def model_readout(provider_label: str, model: str, key_ok: bool) -> None:
    """A compact instrument-style readout of the active LLM parameters, shown under the brand."""
    key_cls, key_txt = ("ok", "已填") if key_ok else ("warn", "未填")
    st.markdown(
        f"""
        <div class="readout">
          <div class="row"><span>供应商</span><b>{provider_label}</b></div>
          <div class="row"><span>模型</span><b class="mono">{model or "未选择"}</b></div>
          <div class="row"><span>密钥</span><b class="{key_cls}">{key_txt}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    """The main-pane hero: a thesis line that states the product's promise (run-verified DAX)."""
    st.markdown(
        """
        <div class="hero">
          <div class="kicker">Power BI · DAX 助手</div>
          <h1>把业务问题，<span class="em">变成可信的 DAX</span></h1>
          <p>连接你正在编辑的 Power BI 模型，读到真实的表、列与关系；生成的每条度量值都经引擎实跑验证。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
