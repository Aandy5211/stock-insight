"""财务报表页 — 利润表 / 资产负债表 / 现金流量表"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data.fetcher import get_income_statement, get_balance_sheet, get_cash_flow
from analysis.statements import (
    parse_income_statement,
    parse_balance_sheet,
    parse_cash_flow,
    highlight_change,
    format_number,
)
from utils.clock import show_world_clock
from utils.theme import (
    apply_theme, dark_layout,
    TK_PINK, TK_TEAL, TK_CARD, TK_BORDER, TK_MUTED, TK_TEXT, POSITIVE, NEGATIVE,
)


def _try_float(v) -> bool:
    try:
        float(v)
        return True
    except Exception:
        return False


st.set_page_config(
    page_title="财务报表 - StockInsight",
    page_icon="📊",
    layout="wide",
)

apply_theme()
show_world_clock()

# ── 侧边栏 ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="text-align:center;padding:12px 0 6px;">'
        f'<span style="font-size:1.4em;font-weight:900;'
        f'background:linear-gradient(90deg,{TK_PINK},{TK_TEAL});'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;">📈 StockInsight</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    code_input = st.text_input(
        "股票代码",
        value=st.session_state.get("selected_code", ""),
        placeholder="如：000001 / 600519",
        key="fs_code_input",
    )
    if st.button("查询", width="stretch", type="primary"):
        if code_input.strip():
            st.session_state["selected_code"] = code_input.strip()
            st.rerun()
    st.divider()
    st.caption("**常用股票**")
    quick = {"贵州茅台 600519": "600519", "平安银行 000001": "000001",
             "宁德时代 300750": "300750", "招商银行 600036": "600036"}
    for label, qcode in quick.items():
        if st.button(label, width="stretch", key=f"q_{qcode}"):
            st.session_state["selected_code"] = qcode
            st.rerun()

code = st.session_state.get("selected_code", "").strip()

if not code:
    st.info("请在左侧输入股票代码后点击查询。")
    st.stop()

st.title(f"📊 财务报表 — {code}")


# ── 加载数据（并行）────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _load_statements(code):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_inc = ex.submit(get_income_statement, code)
        f_bal = ex.submit(get_balance_sheet, code)
        f_cf  = ex.submit(get_cash_flow, code)
        return (
            _safe_get(f_inc),
            _safe_get(f_bal),
            _safe_get(f_cf),
        )


def _safe_get(future):
    try:
        return future.result(timeout=20)
    except Exception:
        return None


with st.spinner("加载财务数据中..."):
    raw_income, raw_balance, raw_cash = _load_statements(code)

if raw_income is None and raw_balance is None and raw_cash is None:
    st.error("无法获取财务数据，请检查代码是否正确或稍后重试。")
    st.stop()


# ── 报告期选择 ───────────────────────────────────────────────────────────────
period_option = st.radio(
    "展示期数",
    options=[4, 8, 12],
    index=1,
    horizontal=True,
    format_func=lambda x: f"近{x}期",
)

tab_income, tab_balance, tab_cash = st.tabs(["利润表", "资产负债表", "现金流量表"])


# ════════════════════════════════════════════════════════════════════════════
#  利润表
# ════════════════════════════════════════════════════════════════════════════
with tab_income:
    if raw_income is None:
        st.warning("利润表数据暂不可用")
    else:
        df_inc = parse_income_statement(raw_income, periods=period_option)

        if not df_inc.empty:
            latest = df_inc.iloc[0]
            st.markdown(
                f'<div style="color:{TK_MUTED};font-size:0.9em;margin-bottom:12px;">'
                f'最新报告期：<span style="color:{TK_TEAL};font-weight:600;">'
                f'{latest.get("报告期", "—")}</span></div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns(4)

            def _mv(row, key):
                v = row.get(key)
                try:
                    return f"{float(v):,.2f} 亿"
                except Exception:
                    return "—"

            with c1:
                st.metric("营业总收入", _mv(latest, "营业总收入"))
            with c2:
                st.metric("归母净利润", _mv(latest, "归母净利润"))
            with c3:
                st.metric("毛利率", f"{latest.get('毛利率(%)', '—')}%"
                          if latest.get('毛利率(%)') else "—")
            with c4:
                yoy = latest.get("营业总收入同比(%)")
                try:
                    yoy_f = float(yoy)
                    sign = "+" if yoy_f >= 0 else ""
                    st.metric("营收同比", f"{sign}{yoy_f:.2f}%", delta=yoy_f)
                except Exception:
                    st.metric("营收同比", "—")

        st.divider()

        # ── 趋势图 ──────────────────────────────────────────────────────────
        col_chart, col_margin = st.columns(2)

        with col_chart:
            st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">营收 & 归母净利润趋势（亿元）</div>', unsafe_allow_html=True)
            fig = go.Figure()
            for col, color, name in [
                ("营业总收入", TK_TEAL,   "营业总收入"),
                ("归母净利润", TK_PINK,   "归母净利润"),
            ]:
                if col in df_inc.columns:
                    fig.add_trace(go.Bar(
                        x=df_inc["报告期"], y=df_inc[col],
                        name=name, marker_color=color, opacity=0.85,
                    ))
            fig.update_layout(**dark_layout(
                height=320, barmode="group",
                xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                yaxis=dict(gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            ))
            st.plotly_chart(fig, width="stretch")

        with col_margin:
            st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">毛利率 & 净利率趋势(%)</div>', unsafe_allow_html=True)
            fig2 = go.Figure()
            for col, color in [("毛利率(%)", TK_TEAL), ("净利率(%)" if "净利率(%)" in df_inc.columns else None, "#FE7C59")]:
                if col and col in df_inc.columns:
                    fig2.add_trace(go.Scatter(
                        x=df_inc["报告期"], y=df_inc[col],
                        name=col, line=dict(width=2.5, color=color),
                        mode="lines+markers", marker=dict(size=6),
                    ))
            yoy_col = "营业总收入同比(%)"
            if yoy_col in df_inc.columns:
                fig2.add_trace(go.Bar(
                    x=df_inc["报告期"], y=df_inc[yoy_col],
                    name="营收同比(%)",
                    marker_color=[
                        "rgba(238,29,82,0.35)" if (_try_float(v) and float(v) >= 0) else "rgba(37,244,238,0.35)"
                        for v in df_inc[yoy_col]
                    ],
                    yaxis="y2", opacity=0.6,
                ))
                fig2.update_layout(
                    yaxis2=dict(
                        overlaying="y", side="right", showgrid=False,
                        title="同比(%)", color=TK_MUTED, linecolor=TK_BORDER,
                    ),
                )
            fig2.update_layout(**dark_layout(
                height=320,
                xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                yaxis=dict(gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            ))
            st.plotly_chart(fig2, width="stretch")

        st.markdown(f'<div style="color:{TK_MUTED};font-size:0.85em;margin-bottom:6px;">明细数据（亿元，% 为同比增长率）</div>', unsafe_allow_html=True)
        yoy_cols = [c for c in df_inc.columns if "同比" in c]
        st.dataframe(
            df_inc.style.map(highlight_change, subset=yoy_cols),
            hide_index=True,
            width="stretch",
        )


# ════════════════════════════════════════════════════════════════════════════
#  资产负债表
# ════════════════════════════════════════════════════════════════════════════
with tab_balance:
    if raw_balance is None:
        st.warning("资产负债表数据暂不可用")
    else:
        df_bs = parse_balance_sheet(raw_balance, periods=period_option)

        if not df_bs.empty:
            latest = df_bs.iloc[0]
            st.markdown(
                f'<div style="color:{TK_MUTED};font-size:0.9em;margin-bottom:12px;">'
                f'最新报告期：<span style="color:{TK_TEAL};font-weight:600;">'
                f'{latest.get("报告期", "—")}</span></div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                v = latest.get("总资产")
                st.metric("总资产", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c2:
                v = latest.get("总负债")
                st.metric("总负债", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c3:
                v = latest.get("归母股东权益")
                st.metric("归母净资产", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c4:
                v = latest.get("资产负债率(%)")
                st.metric("资产负债率", f"{float(v):.1f}%" if _try_float(v) else "—")

        st.divider()

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">总资产 & 股东权益趋势（亿元）</div>', unsafe_allow_html=True)
            fig3 = go.Figure()
            for col, color in [("总资产", TK_TEAL), ("归母股东权益", TK_PINK)]:
                if col in df_bs.columns:
                    fig3.add_trace(go.Bar(
                        x=df_bs["报告期"], y=df_bs[col],
                        name=col, marker_color=color, opacity=0.85,
                    ))
            fig3.update_layout(**dark_layout(
                height=320, barmode="group",
                xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                yaxis=dict(gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            ))
            st.plotly_chart(fig3, width="stretch")

        with col_r:
            st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">资产负债率趋势(%)</div>', unsafe_allow_html=True)
            fig4 = go.Figure()
            if "资产负债率(%)" in df_bs.columns:
                vals = df_bs["资产负债率(%)"].tolist()
                fig4.add_trace(go.Scatter(
                    x=df_bs["报告期"], y=vals,
                    name="资产负债率(%)",
                    line=dict(color=TK_PINK, width=2.5),
                    mode="lines+markers+text",
                    marker=dict(size=6, color=TK_PINK),
                    text=[f"{v:.1f}%" if _try_float(v) else "" for v in vals],
                    textposition="top center",
                    textfont=dict(color=TK_MUTED, size=10),
                    fill="tozeroy",
                    fillcolor="rgba(238,29,82,0.08)",
                ))
                fig4.add_hline(y=60, line_dash="dash", line_color="#FE7C59",
                               annotation_text="60% 警戒线",
                               annotation_font_color=TK_MUTED)
            fig4.update_layout(**dark_layout(
                height=320,
                xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                yaxis=dict(range=[0, 110], gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            ))
            st.plotly_chart(fig4, width="stretch")

        st.markdown(f'<div style="color:{TK_MUTED};font-size:0.85em;margin-bottom:6px;">明细数据（亿元）</div>', unsafe_allow_html=True)
        yoy_cols = [c for c in df_bs.columns if "同比" in c]
        st.dataframe(
            df_bs.style.map(highlight_change, subset=yoy_cols) if yoy_cols else df_bs,
            hide_index=True,
            width="stretch",
        )


# ════════════════════════════════════════════════════════════════════════════
#  现金流量表
# ════════════════════════════════════════════════════════════════════════════
with tab_cash:
    if raw_cash is None:
        st.warning("现金流量表数据暂不可用")
    else:
        df_cf = parse_cash_flow(raw_cash, periods=period_option)

        if not df_cf.empty:
            latest = df_cf.iloc[0]
            st.markdown(
                f'<div style="color:{TK_MUTED};font-size:0.9em;margin-bottom:12px;">'
                f'最新报告期：<span style="color:{TK_TEAL};font-weight:600;">'
                f'{latest.get("报告期", "—")}</span></div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                v = latest.get("经营活动现金流净额")
                st.metric("经营现金流", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c2:
                v = latest.get("投资活动现金流净额")
                st.metric("投资现金流", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c3:
                v = latest.get("筹资活动现金流净额")
                st.metric("筹资现金流", f"{float(v):,.2f} 亿" if _try_float(v) else "—")
            with c4:
                v = latest.get("自由现金流")
                st.metric("自由现金流", f"{float(v):,.2f} 亿" if _try_float(v) else "—")

        st.divider()

        st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">三大现金流趋势（亿元）</div>', unsafe_allow_html=True)
        fig5 = go.Figure()
        cf_items = [
            ("经营活动现金流净额", TK_TEAL),
            ("投资活动现金流净额", "#FE7C59"),
            ("筹资活动现金流净额", "#8A8B98"),
        ]
        for col, color in cf_items:
            if col in df_cf.columns:
                fig5.add_trace(go.Bar(
                    x=df_cf["报告期"], y=df_cf[col],
                    name=col, marker_color=color, opacity=0.85,
                ))
        if "自由现金流" in df_cf.columns:
            fig5.add_trace(go.Scatter(
                x=df_cf["报告期"], y=df_cf["自由现金流"],
                name="自由现金流",
                line=dict(color=TK_PINK, width=2.5, dash="dot"),
                mode="lines+markers",
                marker=dict(size=6),
            ))
        fig5.add_hline(y=0, line_color=TK_BORDER, line_width=1)
        fig5.update_layout(**dark_layout(
            height=380, barmode="group",
            xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            yaxis=dict(gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        ))
        st.plotly_chart(fig5, width="stretch")

        st.markdown(f'<div style="color:{TK_MUTED};font-size:0.85em;margin-bottom:6px;">明细数据（亿元）</div>', unsafe_allow_html=True)
        yoy_cols = [c for c in df_cf.columns if "同比" in c]
        st.dataframe(
            df_cf.style.map(highlight_change, subset=yoy_cols) if yoy_cols else df_cf,
            hide_index=True,
            width="stretch",
        )


# ── 底部 ──────────────────────────────────────────────────────────────────────
st.divider()
st.caption("⚠️ 数据来源：东方财富，仅供参考，不构成投资建议。")
