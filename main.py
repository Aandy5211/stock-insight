"""StockInsight - 股票洞察 Streamlit 主界面"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data.fetcher import get_quote, get_financial_metrics, get_price_history, search_stock
from analysis.financials import metrics_to_dataframe, composite_score, get_latest_metrics
from utils.clock import show_world_clock
from utils.theme import (
    apply_theme, dark_layout, score_color,
    TK_PINK, TK_TEAL, TK_CARD, TK_BORDER, TK_MUTED, TK_TEXT, POSITIVE, NEGATIVE, NEUTRAL,
)

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StockInsight 股票洞察",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
show_world_clock()


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def pct_color(val: float) -> str:
    return POSITIVE if val >= 0 else NEGATIVE


def fmt_pct(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def fmt_cap(val: float) -> str:
    if val >= 10000:
        return f"{val/10000:.2f}万亿"
    elif val >= 1:
        return f"{val:.2f}亿"
    return f"{val*100:.2f}百万"


# ── 侧边栏 ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="text-align:center;padding:16px 0 8px;">'
        f'<span style="font-size:1.6em;font-weight:900;'
        f'background:linear-gradient(90deg,{TK_PINK},{TK_TEAL});'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;">📈 StockInsight</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("股票信息分析工具")
    st.divider()

    stock_input = st.text_input(
        "输入股票代码或名称",
        placeholder="如：000001 / 平安银行 / 600519",
        help="支持 A 股代码，可带市场前缀（sh/sz）"
    )

    search_btn = st.button("搜索", use_container_width=True, type="primary")

    st.divider()
    st.caption("**常用股票**")
    quick_stocks = {
        "平安银行 000001": "000001",
        "贵州茅台 600519": "600519",
        "宁德时代 300750": "300750",
        "比亚迪 002594": "002594",
        "招商银行 600036": "600036",
    }
    for label, code in quick_stocks.items():
        if st.button(label, use_container_width=True, key=f"quick_{code}"):
            st.session_state["selected_code"] = code

    st.divider()
    st.caption("数据来源：AKShare / 东方财富 / 新浪财经")


# ── 确定当前查询代码 ──────────────────────────────────────────────────────────
selected_code = st.session_state.get("selected_code", "")
if search_btn and stock_input.strip():
    selected_code = stock_input.strip()
    st.session_state["selected_code"] = selected_code


# ── 搜索结果展示 ──────────────────────────────────────────────────────────────
if stock_input.strip() and not search_btn and len(stock_input) >= 2:
    with st.spinner("搜索中..."):
        results = search_stock(stock_input.strip())
    if results is not None and not results.empty:
        st.subheader("搜索结果")
        st.dataframe(
            results.rename(columns={
                "代码": "代码", "名称": "名称",
                "最新价": "最新价", "涨跌幅": "涨跌幅(%)", "总市值": "总市值(元)"
            }),
            hide_index=True,
            use_container_width=True,
        )


# ── 主内容区 ──────────────────────────────────────────────────────────────────
if not selected_code:
    st.markdown(
        f"""
        <div style="text-align:center;padding:60px 20px;">
            <div style="font-size:3em;font-weight:900;
                background:linear-gradient(90deg,{TK_PINK},{TK_TEAL});
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                margin-bottom:8px;">StockInsight</div>
            <div style="color:#A3A3A3;font-size:1.1em;margin-bottom:32px;">
                A 股智能分析 · 数据驱动决策
            </div>
            <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;">
                {''.join([
                    f'<div style="background:{TK_CARD};border-radius:12px;padding:20px 28px;'
                    f'border:1px solid {TK_BORDER};min-width:160px;">'
                    f'<div style="font-size:1.8em;margin-bottom:8px;">{icon}</div>'
                    f'<div style="font-weight:600;margin-bottom:4px;">{title}</div>'
                    f'<div style="color:#A3A3A3;font-size:0.85em;">{desc}</div>'
                    f'</div>'
                    for icon, title, desc in [
                        ("📊", "实时行情", "价格 / 市值 / PE/PB"),
                        ("📋", "财务分析", "ROE / 毛利率 / 净利率"),
                        ("📈", "K线走势", "近250交易日蜡烛图"),
                        ("🎯", "综合评分", "盈利 · 成长 · 安全"),
                    ]
                ])}
            </div>
            <div style="color:#666680;margin-top:40px;font-size:0.9em;">
                在左侧输入股票代码或名称，开始分析 →
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ── 加载数据 ──────────────────────────────────────────────────────────────────
with st.spinner(f"正在加载 {selected_code} 数据..."):
    quote = get_quote(selected_code)
    metrics_list = get_financial_metrics(selected_code)
    price_hist = get_price_history(selected_code)

if quote is None:
    st.error(f"未找到股票 **{selected_code}** 的数据，请检查代码是否正确。")
    st.stop()


# ── 股票头部信息 ──────────────────────────────────────────────────────────────
change_color = POSITIVE if quote.change >= 0 else NEGATIVE
change_sign  = "▲" if quote.change >= 0 else "▼"

st.markdown(
    f"""
    <div style="background:{TK_CARD};border-radius:14px;padding:20px 28px;
                border:1px solid {TK_BORDER};margin-bottom:16px;
                border-left:4px solid {change_color};">
        <div style="display:flex;align-items:center;gap:32px;flex-wrap:wrap;">
            <div>
                <div style="font-size:1.6em;font-weight:800;">{quote.name}</div>
                <div style="color:{TK_MUTED};font-size:0.85em;margin-top:2px;">
                    {quote.code}
                </div>
            </div>
            <div>
                <div style="font-size:2.4em;font-weight:900;color:{TK_TEXT};">
                    ¥{quote.price:.2f}
                </div>
            </div>
            <div>
                <div style="font-size:1.5em;font-weight:700;color:{change_color};">
                    {change_sign} {abs(quote.change):.2f}
                </div>
                <div style="font-size:1em;color:{change_color};">
                    {fmt_pct(quote.change_pct)}
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── 行情指标卡片 ──────────────────────────────────────────────────────────────
st.subheader("行情概览")
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    st.metric("市盈率(TTM)", f"{quote.pe_ttm:.2f}" if quote.pe_ttm else "—")
with c2:
    st.metric("市净率", f"{quote.pb:.2f}" if quote.pb else "—")
with c3:
    st.metric("总市值", fmt_cap(quote.market_cap))
with c4:
    st.metric("流通市值", fmt_cap(quote.circ_cap))
with c5:
    vol = quote.volume / 10000 if quote.volume else 0
    st.metric("成交量", f"{vol:.1f}万手")
with c6:
    turn = quote.turnover / 1e8 if quote.turnover else 0
    st.metric("成交额", f"{turn:.2f}亿")


# ── K线/收盘价走势图 ─────────────────────────────────────────────────────────
if price_hist is not None and not price_hist.empty:
    st.subheader("价格走势（近250交易日）")

    date_col  = "日期" if "日期" in price_hist.columns else price_hist.columns[0]
    close_col = "收盘" if "收盘" in price_hist.columns else None

    if close_col:
        if all(c in price_hist.columns for c in ["开盘", "收盘", "最高", "最低"]):
            fig = go.Figure(data=[go.Candlestick(
                x=price_hist[date_col],
                open=price_hist["开盘"],
                high=price_hist["最高"],
                low=price_hist["最低"],
                close=price_hist["收盘"],
                increasing_line_color=POSITIVE,
                increasing_fillcolor=POSITIVE,
                decreasing_line_color=NEGATIVE,
                decreasing_fillcolor=NEGATIVE,
                name=quote.name,
            )])
        else:
            fig = go.Figure(go.Scatter(
                x=price_hist[date_col], y=price_hist[close_col],
                line=dict(color=TK_PINK, width=2),
                fill="tozeroy", fillcolor="rgba(238,29,82,0.08)",
            ))

        fig.update_layout(**dark_layout(
            height=420,
            xaxis_rangeslider_visible=False,
        ))
        st.plotly_chart(fig, use_container_width=True)


# ── 财务指标 ──────────────────────────────────────────────────────────────────
if metrics_list:
    st.subheader("财务指标")

    latest = get_latest_metrics(metrics_list)
    scores = composite_score(latest, history=metrics_list)

    # ── 综合评分 ──
    col_score, col_sub = st.columns([1, 3])
    with col_score:
        sc = scores["综合评分"]
        color = score_color(sc)
        st.markdown(
            f'<div style="text-align:center;padding:24px;background:{TK_CARD};'
            f'border-radius:14px;border:1px solid {TK_BORDER};">'
            f'<div style="font-size:0.85em;color:{TK_MUTED};margin-bottom:8px;">综合评分</div>'
            f'<div style="font-size:3.2em;font-weight:900;color:{color};">{sc}</div>'
            f'<div style="font-size:0.8em;color:{TK_MUTED};margin-top:6px;">满分 100 分</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col_sub:
        sub_cols = st.columns(3)
        for idx, (label, key, desc_key) in enumerate([
            ("盈利能力", "盈利能力", "盈利能力说明"),
            ("成长性",   "成长性",   "成长性说明"),
            ("财务安全", "财务安全", "财务安全说明"),
        ]):
            with sub_cols[idx]:
                st.metric(label, f"{scores[key]} 分")
                desc = scores.get(desc_key, "")
                if desc:
                    with st.expander("评分依据", expanded=False):
                        for item in desc.split("  /  "):
                            if item.strip():
                                st.caption(f"• {item.strip()}")

    st.divider()

    # ── 最新期关键指标 ──
    st.markdown(
        f'<div style="color:{TK_MUTED};font-size:0.9em;margin-bottom:8px;">'
        f'最新报告期：<span style="color:{TK_TEAL};font-weight:600;">{latest.report_date}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    m_cols = st.columns(6)
    metrics_display = [
        ("ROE",      f"{latest.roe:.1f}%"),
        ("毛利率",   f"{latest.gross_margin:.1f}%"),
        ("净利率",   f"{latest.net_margin:.1f}%"),
        ("营收同比", fmt_pct(latest.revenue_yoy)),
        ("净利润同比", fmt_pct(latest.profit_yoy)),
        ("资产负债率", f"{latest.debt_ratio:.1f}%"),
    ]
    for idx, (label, val) in enumerate(metrics_display):
        with m_cols[idx]:
            st.metric(label, val)

    st.divider()

    # ── 历史趋势图 ──
    df_metrics = metrics_to_dataframe(metrics_list)
    if not df_metrics.empty:
        tab1, tab2, tab3 = st.tabs(["盈利能力趋势", "成长性趋势", "历史数据表"])

        with tab1:
            fig1 = go.Figure()
            for col, color, name in [
                ("ROE(%)",  TK_PINK, "ROE"),
                ("毛利率(%)", TK_TEAL, "毛利率"),
                ("净利率(%)", "#FE7C59", "净利率"),
            ]:
                if col in df_metrics.columns:
                    fig1.add_trace(go.Scatter(
                        x=df_metrics["报告期"], y=df_metrics[col],
                        name=name, line=dict(color=color, width=2.5),
                        mode="lines+markers",
                        marker=dict(size=6),
                    ))
            fig1.update_layout(**dark_layout(height=350))
            st.plotly_chart(fig1, use_container_width=True)

        with tab2:
            fig2 = go.Figure()
            for col, name in [("营收同比(%)", "营收同比"), ("净利润同比(%)", "净利润同比")]:
                if col in df_metrics.columns:
                    fig2.add_trace(go.Bar(
                        x=df_metrics["报告期"], y=df_metrics[col],
                        name=name,
                        marker_color=[
                            POSITIVE if v >= 0 else NEGATIVE
                            for v in df_metrics[col]
                        ],
                    ))
            fig2.update_layout(**dark_layout(height=350, barmode="group"))
            st.plotly_chart(fig2, use_container_width=True)

        with tab3:
            st.dataframe(df_metrics, hide_index=True, use_container_width=True, height=350)

else:
    st.info("暂无财务数据，可能该股票数据源暂不支持，请尝试其他股票。")


# ── 底部说明 ──────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "⚠️ **免责声明**：本工具仅供学习和信息参考，所有数据来源于公开渠道（AKShare / 东方财富 / 新浪财经），"
    "不构成任何投资建议。投资有风险，决策需谨慎。"
)
