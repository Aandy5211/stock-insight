"""抖音 (TikTok) 暗色主题 — CSS 注入 & Plotly 布局"""
import streamlit as st

# ── 抖音配色常量 ──────────────────────────────────────────────────────────────
TK_BLACK   = "#010101"   # 主背景
TK_CARD    = "#161823"   # 卡片/容器背景
TK_SIDEBAR = "#0a0a0a"   # 侧边栏
TK_BORDER  = "#2A2A3D"   # 边框
TK_PINK    = "#EE1D52"   # 抖音红（涨 / 利好）
TK_TEAL    = "#25F4EE"   # 抖音青（跌 / 利空）
TK_TEXT    = "#FFFFFF"   # 主文字
TK_MUTED   = "#A3A3A3"   # 次要文字
TK_DIM     = "#666680"   # 极暗文字

# 股市语义色
POSITIVE   = TK_PINK     # 涨
NEGATIVE   = TK_TEAL     # 跌
NEUTRAL    = "#8A8B98"   # 中性


# ── CSS 注入 ──────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ===== TikTok 暗色主题 ===== */

/* 全局背景 */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main {
    background-color: #010101 !important;
}

/* 顶栏 */
[data-testid="stHeader"] {
    background-color: #010101 !important;
    border-bottom: 1px solid #1a1a2e;
}

/* 侧边栏 */
[data-testid="stSidebar"] {
    background-color: #0a0a0a !important;
    border-right: 1px solid #1a1a2e !important;
}
[data-testid="stSidebar"] * { color: #FFFFFF; }
[data-testid="stSidebarContent"] { background-color: #0a0a0a; }

/* block 容器 */
.block-container { color: #FFFFFF; }

/* 文字 */
p, span, label, div, li { color: #FFFFFF; }
h1, h2, h3, h4, h5, h6 { color: #FFFFFF !important; }

/* subheader 装饰线 */
[data-testid="stSubheader"]::after {
    content: "";
    display: block;
    height: 2px;
    background: linear-gradient(90deg, #EE1D52, #25F4EE);
    border-radius: 2px;
    margin-top: 4px;
}

/* caption */
[data-testid="stCaptionContainer"],
.stCaption { color: #666680 !important; }

/* ── Metric 卡片 ── */
[data-testid="metric-container"] {
    background: #161823 !important;
    border-radius: 10px !important;
    border: 1px solid #2A2A3D !important;
    padding: 12px 16px !important;
    transition: border-color .2s;
}
[data-testid="metric-container"]:hover { border-color: #EE1D52 !important; }
[data-testid="metric-container"] > label,
[data-testid="stMetricLabel"] > div { color: #A3A3A3 !important; }
[data-testid="stMetricValue"] > div { color: #FFFFFF !important; }

/* ── 输入框 ── */
[data-testid="stTextInput"] input {
    background-color: #161823 !important;
    color: #FFFFFF !important;
    border: 1px solid #2A2A3D !important;
    border-radius: 8px !important;
}
[data-testid="stTextInput"] input::placeholder { color: #666680; }
[data-testid="stTextInput"] input:focus {
    border-color: #EE1D52 !important;
    box-shadow: 0 0 0 1px #EE1D52 !important;
    outline: none;
}

/* ── 按钮 ── */
.stButton > button {
    background: #161823 !important;
    color: #FFFFFF !important;
    border: 1px solid #2A2A3D !important;
    border-radius: 8px !important;
    transition: all .2s;
}
.stButton > button:hover {
    background: #2A2A3D !important;
    border-color: #69C9D0 !important;
    color: #69C9D0 !important;
}
.stButton > button[kind="primary"],
[data-testid="baseButton-primary"] {
    background: linear-gradient(90deg, #EE1D52 0%, #fe4d76 100%) !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(90deg, #ff2d66, #EE1D52) !important;
    box-shadow: 0 4px 15px rgba(238,29,82,.4) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #0a0a0a !important;
    border-bottom: 1px solid #1a1a2e !important;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    color: #A3A3A3 !important;
    background: transparent !important;
    border-radius: 6px 6px 0 0;
    padding: 8px 20px;
}
.stTabs [data-baseweb="tab"]:hover { color: #FFFFFF !important; }
.stTabs [aria-selected="true"] {
    color: #25F4EE !important;
    border-bottom: 2px solid #25F4EE !important;
    background: #161823 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #010101 !important;
    padding-top: 16px;
}

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    background: #161823 !important;
    border: 1px solid #2A2A3D !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
}
[data-baseweb="select"] svg { fill: #A3A3A3; }

/* ── 下拉菜单 ── */
[data-baseweb="popover"],
[data-baseweb="menu"] {
    background: #161823 !important;
    border: 1px solid #2A2A3D !important;
}
[data-baseweb="menu"] li:hover { background: #2A2A3D !important; }
[data-baseweb="menu"] li * { color: #FFFFFF !important; }

/* ── Radio ── */
[data-testid="stRadio"] label > div:first-child {
    border-color: #2A2A3D !important;
    background: #161823 !important;
}
[data-testid="stRadio"] label:hover > div:first-child { border-color: #EE1D52 !important; }

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBarMax"] {
    color: #A3A3A3;
}
[data-baseweb="slider"] [role="slider"] { background: #EE1D52 !important; }

/* ── Checkbox ── */
[data-testid="stCheckbox"] label { color: #FFFFFF !important; }
[data-testid="stCheckbox"] svg { fill: #EE1D52; }

/* ── Divider ── */
hr { border-color: #1a1a2e !important; }

/* ── DataFrame ── */
[data-testid="stDataFrameResizable"] {
    border: 1px solid #2A2A3D !important;
    border-radius: 8px !important;
    overflow: hidden;
}
.dvn-scroller { background: #161823 !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161823 !important;
    border: 1px solid #2A2A3D !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary { color: #FFFFFF !important; }
[data-testid="stExpander"] summary:hover { color: #25F4EE !important; }

/* ── Alert / Info ── */
[data-testid="stAlert"] {
    background: #161823 !important;
    border-radius: 8px;
    border: 1px solid #2A2A3D !important;
}
[data-testid="stAlert"] * { color: #FFFFFF !important; }

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #EE1D52 !important;
    border-right-color: transparent !important;
    border-bottom-color: transparent !important;
    border-left-color: transparent !important;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0a0a0a; }
::-webkit-scrollbar-thumb { background: #2A2A3D; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #EE1D52; }

/* ── 隐藏右上角工具栏（Fork / GitHub / 菜单）── */
[data-testid="stToolbar"],
[data-testid="stDecoration"],
#MainMenu,
footer { visibility: hidden !important; height: 0 !important; }
</style>
"""


def apply_theme() -> None:
    """向 Streamlit 页面注入抖音暗色主题 CSS"""
    st.markdown(_CSS, unsafe_allow_html=True)


def dark_layout(**extra) -> dict:
    """
    返回 Plotly 深色布局基础配置字典，可通过 **extra 追加覆盖。
    用法：fig.update_layout(**dark_layout(height=350, barmode="group"))
    """
    base = dict(
        plot_bgcolor=TK_CARD,
        paper_bgcolor=TK_BLACK,
        font=dict(color=TK_TEXT, family="'Segoe UI','PingFang SC',system-ui,sans-serif"),
        xaxis=dict(
            gridcolor=TK_BORDER,
            zerolinecolor=TK_BORDER,
            color=TK_MUTED,
            linecolor=TK_BORDER,
        ),
        yaxis=dict(
            gridcolor=TK_BORDER,
            zerolinecolor=TK_BORDER,
            color=TK_MUTED,
            linecolor=TK_BORDER,
        ),
        legend=dict(
            bgcolor=TK_CARD,
            bordercolor=TK_BORDER,
            borderwidth=1,
            font=dict(color=TK_TEXT),
        ),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    base.update(extra)
    return base


def card(content: str, border_color: str = TK_BORDER) -> str:
    """生成深色卡片 HTML 片段"""
    return (
        f'<div style="background:{TK_CARD};border-radius:10px;padding:16px;'
        f'border:1px solid {border_color};margin-bottom:8px;">'
        f'{content}</div>'
    )


def score_color(score: float) -> str:
    """评分对应颜色（高分红/中分橙/低分青）"""
    if score >= 70:
        return TK_PINK
    elif score >= 50:
        return "#FE7C59"
    return TK_TEAL
