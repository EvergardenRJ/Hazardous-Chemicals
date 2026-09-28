# -*- coding: utf-8 -*-
"""统一 UI 主题（frontend-design 精修版）。

危险化学品安全知识平台 / Chemical Safety Knowledge Hub

设计语言：化工安全领域的「物质世界」—— 黑黄警戒线、安全色、标准号。
签名元素：页首 6px 黑黄警戒斜纹条（caution stripe），全站只用这一处 bold。
展示字体用宋体（标准法规的官方分量感），正文无衬线，标准号/ID 用等宽。
"""
import streamlit as st

PLATFORM_NAME = "危险化学品安全知识平台"
PLATFORM_NAME_EN = "Chemical Safety Knowledge Hub"

# 字体栈
_SERIF = ('"Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", "SimSun", serif')
_SANS = ('"PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Hiragino Sans GB", '
         '-apple-system, "Segoe UI", sans-serif')
_MONO = ('"JetBrains Mono", "SF Mono", "Cascadia Code", "Consolas", "Courier New", monospace')

_CSS = f"""
<style>
/* 页首黑黄警戒斜纹条 —— 签名元素 */
.caution-stripe {{
    height: 6px;
    border-radius: 8px 8px 0 0;
    background: repeating-linear-gradient(
        -45deg, #f59e0b 0 12px, #101b28 12px 24px
    );
}}

.block-container {{ max-width: 1280px; padding-top: 1.6rem; padding-bottom: 2rem; }}

/* 页头：深墨蓝 + 宋体展示标题 */
.platform-header {{
    background: #14202e;
    color: #fff;
    border-radius: 0 0 10px 10px;
    padding: 1.3rem 1.6rem 1.1rem;
    margin-bottom: 1.4rem;
}}
.platform-header h1 {{
    font-family: {_SERIF};
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #fff;
    font-size: 1.45rem;
    margin: 0;
}}
.platform-header .sub {{
    font-family: {_SANS};
    color: #9fb0c0;
    font-size: 0.82rem;
    margin-top: 0.35rem;
    letter-spacing: 0.4px;
}}

/* Metric Card：白卡 + 琥珀色顶部刻度 */
.metric-card {{
    background: #ffffff;
    border: 1px solid #e3e8ee;
    border-top: 3px solid #f59e0b;
    border-radius: 8px;
    padding: 0.9rem 1rem;
    text-align: left;
    box-shadow: 0 1px 2px rgba(20, 32, 46, 0.04);
    height: 100%;
}}
.metric-card .value {{
    font-family: {_MONO};
    font-size: 1.75rem;
    font-weight: 700;
    color: #14202e;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}}
.metric-card .label {{
    font-family: {_SANS};
    font-size: 0.76rem;
    color: #5c6b7a;
    margin-top: 0.3rem;
    letter-spacing: 0.4px;
}}

/* 卡片 */
.ui-card {{
    background: #ffffff;
    border: 1px solid #e3e8ee;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    box-shadow: 0 1px 2px rgba(20, 32, 46, 0.04);
    margin-bottom: 0.8rem;
}}

/* 状态徽章 —— 用安全色语义 */
.badge {{
    display: inline-block;
    padding: 0.14rem 0.6rem;
    border-radius: 4px;
    font-family: {_SANS};
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
.badge-pending   {{ background: #fdf3e0; color: #b26a00; }}  /* 琥珀·待处理 */
.badge-approved  {{ background: #e6f4ea; color: #1b6e33; }}  /* 绿·通过 */
.badge-rejected  {{ background: #fdecea; color: #b03020; }}  /* 红·拒绝 */
.badge-modified  {{ background: #fff0e0; color: #c05600; }}  /* 橙·修改 */
.badge-grounded  {{ background: #e8f1fb; color: #1668c7; }}  /* 蓝·文档证据 */
.badge-model     {{ background: #f1eafb; color: #7b3fd0; }}  /* 紫·模型补充 */

/* 证据卡 */
.evidence-card {{
    background: #f8fafc;
    border: 1px solid #e3e8ee;
    border-left: 3px solid #1668c7;
    border-radius: 6px;
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.6rem;
}}
.evidence-card .src {{
    font-family: {_SANS};
    font-size: 0.76rem;
    color: #5c6b7a;
}}

/* 按钮 */
div.stButton > button {{
    border-radius: 6px;
    border: 1px solid #d5dbe2;
    font-family: {_SANS};
    font-weight: 500;
}}
div.stButton > button[kind="primary"] {{
    background: #14202e;
    border-color: #14202e;
    color: #ffffff;
}}
div.stButton > button[kind="primary"]:hover {{
    background: #1f3346;
    border-color: #1f3346;
}}

/* Tab：琥珀色下划线激活态 */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.2rem;
    border-bottom: 1px solid #e3e8ee;
}}
.stTabs [data-baseweb="tab"] {{
    font-family: {_SANS};
    border-radius: 6px 6px 0 0;
    padding: 0.5rem 1rem;
    font-weight: 500;
}}
.stTabs [aria-selected="true"] {{
    color: #14202e;
    border-bottom: 2px solid #f59e0b;
}}

/* 标题层级 */
h1, h2, h3 {{ color: #14202e; font-family: {_SERIF}; }}
h4, h5 {{ color: #14202e; font-family: {_SANS}; }}

/* Graph observatory / dark workspace */
:root {{ color-scheme: dark; }}
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
  background: #08141f; color: #e5f1f2;
}}
[data-testid="stSidebar"] {{ background: #0d2230; border-right:1px solid #22404e; }}
[data-testid="stSidebar"] * {{ color: #d6e8e9; }}
.block-container {{ max-width: 1580px; padding-top: 1.15rem; }}
.caution-stripe {{ height:3px; background:linear-gradient(90deg,#42d1c4,#2a788e 58%,#f3b65c); }}
.platform-header {{
  background: radial-gradient(circle at 78% 20%, rgba(59,189,186,.21),transparent 40%),
              linear-gradient(125deg,#112d3c,#0a1d2c);
  border:1px solid #285367; border-radius:0 0 16px 16px;
  padding:1.55rem 2rem; box-shadow:0 16px 40px rgba(0,0,0,.18);
}}
.platform-header h1 {{ font-family:{_SANS}; font-size:clamp(1.4rem,2.2vw,2.2rem); letter-spacing:.025em; }}
.platform-header .sub {{ color:#9ec2cb; font-size:.9rem; }}
.metric-card,.ui-card {{
  background:linear-gradient(155deg,#123040,#102535); border:1px solid #284759;
  border-top:2px solid #42c9bc; border-radius:12px; box-shadow:0 9px 25px rgba(0,0,0,.12);
}}
.metric-card .value {{ color:#f3fafa; }}
.metric-card .label {{ color:#9dbbc5; }}
.evidence-card {{ background:#102736; border:1px solid #315767; border-left:3px solid #42c9bc; }}
.evidence-card .src {{ color:#a4c2cb; }}
.badge-approved,.badge-grounded {{ background:#123d42; color:#83e5d4; }}
.badge-pending,.badge-modified {{ background:#493820; color:#ffd58d; }}
.badge-rejected {{ background:#4a252b; color:#ffadb2; }}
.badge-model {{ background:#312d54; color:#c4bbff; }}
h1,h2,h3,h4,h5,p,li,label,[data-testid="stMarkdownContainer"] {{ color:#e5f1f2; }}
h1,h2,h3 {{ font-family:{_SANS}; }}
.stCaption,[data-testid="stCaptionContainer"] {{ color:#9dbbc5 !important; }}
div.stButton > button,div.stDownloadButton > button {{
  background:#153344; color:#eaf8f6; border:1px solid #3d6874; border-radius:9px;
  transition:background .18s ease,border-color .18s ease,transform .18s ease;
}}
div.stButton > button:hover,div.stDownloadButton > button:hover {{
  background:#20505d; border-color:#6fd5ca; transform:translateY(-1px);
}}
div.stButton > button[kind="primary"] {{
  background:#38b9ae; color:#061c25; border-color:#38b9ae; font-weight:700;
}}
div.stButton > button[kind="primary"]:hover {{ background:#77ddd0; border-color:#77ddd0; }}
:focus-visible {{ outline:2px solid #f4bd68 !important; outline-offset:2px; }}
.stTabs [data-baseweb="tab-list"] {{ border-color:#305466; }}
.stTabs [aria-selected="true"] {{ color:#79e2d4; border-color:#46cfbf; }}
[data-baseweb="select"] > div, textarea, input {{
  background:#102b3a !important; color:#e8f3f2 !important; border-color:#3e6372 !important;
}}
[data-testid="stExpander"] {{ border-color:#305363; background:#0e2432; }}
@media (max-width:760px) {{
  .platform-header {{ padding:1.1rem; }}
  .block-container {{ padding-left:.8rem; padding-right:.8rem; }}
}}
@media (prefers-reduced-motion:reduce) {{
  *,*::before,*::after {{ transition-duration:0.01ms !important; animation-duration:0.01ms !important; }}
}}
</style>
"""


def apply_theme():
    st.set_page_config(page_title=PLATFORM_NAME, page_icon="🧪", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title, subtitle=""):
    sub = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        '<div class="caution-stripe"></div>'
        f'<div class="platform-header"><h1>{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def metric_row(items):
    """items: [(value, label), ...]，等宽一行 Metric Card。"""
    cols = st.columns(len(items))
    for col, (value, label) in zip(cols, items):
        col.markdown(
            f'<div class="metric-card"><div class="value">{value}</div>'
            f'<div class="label">{label}</div></div>',
            unsafe_allow_html=True,
        )


def badge(status, text=None):
    status = (status or "").lower()
    return f'<span class="badge badge-{status}">{text or status}</span>'


def card(html):
    """把一段 html 包进 ui-card。"""
    return f'<div class="ui-card">{html}</div>'


def evidence_card(html):
    return f'<div class="evidence-card">{html}</div>'
