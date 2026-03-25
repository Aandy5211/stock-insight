"""估值分析页 + Excel 报告导出"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from data.fetcher import (
    get_quote, get_financial_metrics,
    get_pe_pb_history, get_analyst_forecast, get_fund_flow,
    get_income_statement, get_balance_sheet, get_cash_flow,
    get_stock_news,
)
from analysis.valuation import (
    analyze_valuation_history, composite_valuation_score,
    calc_peg, analyze_roe_trend, analyze_fund_flow,
    analyze_analyst_forecast, score_percentile,
)
from analysis.financials import composite_score, get_latest_metrics
from analysis.statements import parse_income_statement, parse_balance_sheet, parse_cash_flow
from analysis.news import analyze_news_batch
from export.report import export_to_excel
from utils.clock import show_world_clock
from utils.theme import (
    apply_theme, dark_layout, score_color,
    TK_PINK, TK_TEAL, TK_CARD, TK_BORDER, TK_MUTED, TK_TEXT, POSITIVE, NEGATIVE, NEUTRAL,
)

st.set_page_config(
    page_title="估值分析 - StockInsight",
    page_icon="🎯",
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
    st.divider()
    pe_years = st.radio("PE/PB 历史区间", [3, 5, 10], index=1,
                        horizontal=True, format_func=lambda x: f"{x}年")

code = st.session_state.get("selected_code", "").strip()

if not code:
    st.info("请在左侧输入股票代码后点击查询。")
    st.stop()

st.title(f"🎯 估值分析 — {code}")


# ── 加载数据（并行）────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_all(code):
    from concurrent.futures import ThreadPoolExecutor
    tasks = {
        "quote":    (get_quote,             (code,),        {}),
        "metrics":  (get_financial_metrics, (code,),        {}),
        "pe_hist":  (get_pe_pb_history,     (code, "PE"),   {}),
        "pb_hist":  (get_pe_pb_history,     (code, "PB"),   {}),
        "forecast": (get_analyst_forecast,  (code,),        {}),
        "flow":     (get_fund_flow,         (code,),        {}),
    }
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {key: ex.submit(fn, *args, **kw)
                   for key, (fn, args, kw) in tasks.items()}
        for key, fut in futures.items():
            try:
                results[key] = fut.result(timeout=20)
            except Exception:
                results[key] = None
    return results


with st.spinner("加载估值数据..."):
    data = _load_all(code)

quote    = data["quote"]
metrics  = data["metrics"]
pe_hist  = data["pe_hist"]
pb_hist  = data["pb_hist"]
forecast = data["forecast"]
flow_df  = data["flow"]

if quote is None:
    st.error(f"未找到 **{code}** 的数据，请检查代码是否正确。")
    st.stop()

stock_name = quote.name

# ── 计算各维度 ────────────────────────────────────────────────────────────────
pe_info      = analyze_valuation_history(pe_hist, quote.pe_ttm, years=pe_years) if pe_hist is not None else {}
pb_info      = analyze_valuation_history(pb_hist, quote.pb,     years=pe_years) if pb_hist is not None else {}
roe_info     = analyze_roe_trend(metrics)
flow_info    = analyze_fund_flow(flow_df) if flow_df is not None else {}
analyst_info = analyze_analyst_forecast(forecast) if forecast is not None else {}

latest_m = get_latest_metrics(metrics) if metrics else None
peg = None
if latest_m and quote.pe_ttm > 0:
    peg = calc_peg(quote.pe_ttm, latest_m.profit_yoy)

val_scores = composite_valuation_score(pe_info, pb_info, peg, roe_info, flow_info, analyst_info)
fin_scores = composite_score(latest_m, history=metrics) if latest_m else {}


# ── 综合评分展示 ──────────────────────────────────────────────────────────────
st.subheader("综合估值评分")
col_val, col_fin, col_detail = st.columns([1, 1, 2])

with col_val:
    sc     = val_scores.get("综合评分", 0)
    judge  = val_scores.get("估值判断", "—")
    color  = score_color(sc)
    st.markdown(
        f'<div style="text-align:center;padding:24px 20px;background:{TK_CARD};'
        f'border-radius:14px;border:1px solid {color};">'
        f'<div style="font-size:0.85em;color:{TK_MUTED};margin-bottom:6px;">估值评分</div>'
        f'<div style="font-size:3.2em;font-weight:900;color:{color};">{sc}</div>'
        f'<div style="font-size:1.05em;color:{color};font-weight:700;margin-top:4px;">{judge}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col_fin:
    sc2    = fin_scores.get("综合评分", 0)
    color2 = score_color(sc2)
    st.markdown(
        f'<div style="text-align:center;padding:24px 20px;background:{TK_CARD};'
        f'border-radius:14px;border:1px solid {color2};">'
        f'<div style="font-size:0.85em;color:{TK_MUTED};margin-bottom:6px;">财务评分</div>'
        f'<div style="font-size:3.2em;font-weight:900;color:{color2};">{sc2}</div>'
        f'<div style="font-size:1.05em;color:{TK_MUTED};margin-top:4px;">盈利·成长·安全</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col_detail:
    detail_items = [
        ("PE 百分位得分", val_scores.get("PE 百分位得分", "—")),
        ("PB 百分位得分", val_scores.get("PB 百分位得分", "—")),
        ("PEG 得分",      val_scores.get("PEG 得分", "—")),
        ("ROE 趋势得分",  val_scores.get("ROE 趋势得分", "—")),
        ("资金流向得分",  val_scores.get("资金流向得分", "—")),
        ("机构评级得分",  val_scores.get("机构评级得分", "—")),
    ]
    cols = st.columns(3)
    for i, (k, v) in enumerate(detail_items):
        with cols[i % 3]:
            try:
                st.metric(k, f"{float(v):.1f}")
            except Exception:
                st.metric(k, str(v))

# ── 估值评分依据 ──
val_desc = val_scores.get("_说明", {})
fin_desc_items = [
    ("盈利能力评分依据", fin_scores.get("盈利能力说明", "")),
    ("成长性评分依据",   fin_scores.get("成长性说明", "")),
    ("财务安全评分依据", fin_scores.get("财务安全说明", "")),
]
has_val_desc = any(v for v in val_desc.values())
has_fin_desc = any(v for v in [x[1] for x in fin_desc_items])

if has_val_desc or has_fin_desc:
    with st.expander("📋 评分依据与数据来源", expanded=False):
        if has_val_desc:
            st.markdown(f'<div style="color:{TK_TEAL};font-weight:600;margin-bottom:6px;">估值评分说明</div>', unsafe_allow_html=True)
            for dim, note in val_desc.items():
                if note:
                    st.caption(f"**{dim}**：{note}")
            st.markdown("---")
        if has_fin_desc:
            st.markdown(f'<div style="color:{TK_TEAL};font-weight:600;margin-bottom:6px;">财务评分说明</div>', unsafe_allow_html=True)
            for title, desc in fin_desc_items:
                if desc:
                    st.markdown(f'<div style="font-size:0.88em;font-weight:600;color:{TK_MUTED};margin-top:8px;">{title}</div>', unsafe_allow_html=True)
                    for item in desc.split("  /  "):
                        if item.strip():
                            st.caption(f"• {item.strip()}")

st.divider()


# ── PE / PB 历史百分位图 ──────────────────────────────────────────────────────
st.subheader(f"PE / PB 历史估值（近 {pe_years} 年）")
tab_pe, tab_pb = st.tabs(["市盈率 PE", "市净率 PB"])


def _build_valuation_chart(hist_df, info, current_val, label):
    if hist_df is None or hist_df.empty or not info:
        st.info(f"{label} 历史数据暂不可用")
        return
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=pe_years)
    sub = hist_df[hist_df["date"] >= cutoff].copy()
    if sub.empty:
        st.info("数据不足")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sub["date"], y=sub["value"],
        name=label,
        line=dict(color=TK_TEAL, width=1.5),
        fill="tozeroy",
        fillcolor="rgba(37,244,238,0.07)",
    ))
    fig.add_hline(
        y=current_val, line_dash="dash", line_color=TK_PINK, line_width=2,
        annotation_text=f"当前 {current_val:.1f}",
        annotation_font_color=TK_PINK,
        annotation_position="right",
    )
    median = info.get("median")
    if median:
        fig.add_hline(
            y=median, line_dash="dot", line_color="#FE7C59", line_width=1.5,
            annotation_text=f"中位 {median:.1f}",
            annotation_font_color="#FE7C59",
            annotation_position="left",
        )
    fig.update_layout(**dark_layout(
        height=340,
        margin=dict(l=0, r=60, t=10, b=0),
        xaxis=dict(title="日期", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        yaxis=dict(title=label, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
    ))
    st.plotly_chart(fig, width="stretch")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("当前值",   f"{info.get('current', '—'):.2f}")
    with c2: st.metric("历史中位", f"{info.get('median', '—'):.2f}")
    with c3: st.metric("历史最低", f"{info.get('min', '—'):.2f}")
    with c4: st.metric("历史最高", f"{info.get('max', '—'):.2f}")
    with c5:
        pct = info.get("percentile")
        label_pct = "便宜" if pct and pct <= 30 else "适中" if pct and pct <= 60 else "偏贵"
        st.metric("历史百分位", f"{pct:.1f}%" if pct else "—",
                  delta=label_pct, delta_color="inverse")


with tab_pe:
    _build_valuation_chart(pe_hist, pe_info, quote.pe_ttm, "PE")

with tab_pb:
    _build_valuation_chart(pb_hist, pb_info, quote.pb, "PB")

st.divider()


# ── PEG & ROE 趋势 ────────────────────────────────────────────────────────────
st.subheader("PEG & ROE 趋势")
col_peg, col_roe = st.columns(2)

with col_peg:
    st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:8px;">PEG 分析</div>', unsafe_allow_html=True)
    peg_score_val = val_scores.get("PEG 得分", 50)

    if peg:
        peg_color = "#25F4EE" if peg < 1 else "#FE7C59" if peg < 2 else TK_PINK
        judge_peg = "低估" if peg < 0.5 else "合理" if peg < 1 else "偏贵" if peg < 2 else "高估"
        st.markdown(
            f'<div style="padding:16px;background:{TK_CARD};border-radius:10px;'
            f'border:1px solid {peg_color};">'
            f'<div style="font-size:0.82em;color:{TK_MUTED};">PEG = PE ÷ 净利润增速</div>'
            f'<div style="font-size:2.4em;font-weight:900;color:{peg_color};">{peg:.2f}</div>'
            f'<div style="color:{peg_color};font-weight:600;">{judge_peg}</div>'
            f'<div style="font-size:0.8em;color:{TK_MUTED};margin-top:8px;">'
            f'PE={quote.pe_ttm:.1f}&nbsp;&nbsp;净利增速={latest_m.profit_yoy:.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("PEG 无法计算（净利润增速为负或数据不足）")

    fig_peg = go.Figure(go.Bar(
        x=["PEG<0.5\n低估", "0.5~1.0\n合理", "1.0~2.0\n偏贵", ">2.0\n高估"],
        y=[100, 80, 55, 10],
        marker_color=[TK_TEAL, "#4FC3F7", "#FE7C59", TK_PINK],
        text=[f"{v}" for v in [100, 80, 55, 10]],
        textposition="auto",
        textfont=dict(color=TK_TEXT),
    ))
    if peg:
        fig_peg.add_hline(
            y=peg_score_val, line_dash="dash", line_color=TK_TEXT,
            annotation_text=f"当前得分 {peg_score_val:.0f}",
            annotation_font_color=TK_MUTED,
        )
    fig_peg.update_layout(**dark_layout(
        height=200,
        yaxis=dict(title="分值", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        xaxis=dict(gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        showlegend=False,
    ))
    st.plotly_chart(fig_peg, width="stretch")


with col_roe:
    st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:8px;">ROE 趋势</div>', unsafe_allow_html=True)
    trend = roe_info.get("trend", "数据不足")
    trend_color = {
        "上升": POSITIVE, "稳定": TK_TEAL, "下降": "#FE7C59"
    }.get(trend, TK_MUTED)
    avg_roe = roe_info.get("avg", 0)

    st.markdown(
        f'<div style="padding:10px 16px;background:{TK_CARD};border-radius:8px;'
        f'margin-bottom:8px;border:1px solid {TK_BORDER};">'
        f'<span style="font-size:0.88em;color:{TK_MUTED};">趋势：</span>'
        f'<span style="font-weight:700;color:{trend_color};">{trend}</span>'
        f'&nbsp;&nbsp;&nbsp;'
        f'<span style="font-size:0.88em;color:{TK_MUTED};">均值 ROE：</span>'
        f'<span style="font-weight:700;color:{TK_TEXT};">{avg_roe:.2f}%</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    roe_vals  = roe_info.get("values", [])
    roe_dates = roe_info.get("dates", list(range(len(roe_vals))))
    if roe_vals:
        fig_roe = go.Figure()
        fig_roe.add_trace(go.Scatter(
            x=roe_dates, y=roe_vals,
            mode="lines+markers+text",
            text=[f"{v:.1f}%" for v in roe_vals],
            textposition="top center",
            textfont=dict(color=TK_MUTED, size=10),
            line=dict(color=trend_color, width=2.5),
            marker=dict(size=7, color=trend_color),
            fill="tozeroy",
            fillcolor=f"rgba(37,244,238,0.07)",
        ))
        fig_roe.add_hline(y=15, line_dash="dot", line_color="#FE7C59",
                          annotation_text="15% 优秀线",
                          annotation_font_color="#FE7C59")
        fig_roe.update_layout(**dark_layout(
            height=240,
            xaxis=dict(tickangle=-20, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            yaxis=dict(title="ROE(%)", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        ))
        st.plotly_chart(fig_roe, width="stretch")
    else:
        st.info("ROE 历史数据不足")

st.divider()


# ── 资金流向 ──────────────────────────────────────────────────────────────────
st.subheader("主力资金流向（近10日）")

if flow_df is not None and not flow_df.empty:
    flow_info_display = analyze_fund_flow(flow_df, days=10)
    ca, cb, cc, cd = st.columns(4)
    total_f = flow_info_display.get("total_flow", 0)
    with ca:
        st.metric("10日净流入", f"{total_f:+.2f} 亿",
                  delta="净流入" if total_f >= 0 else "净流出",
                  delta_color="normal" if total_f >= 0 else "inverse")
    with cb:
        st.metric("流入天数", f"{flow_info_display.get('pos_days', 0)} 天")
    with cc:
        st.metric("流出天数", f"{flow_info_display.get('neg_days', 0)} 天")
    with cd:
        st.metric("资金流向得分", f"{val_scores.get('资金流向得分', 0):.0f} 分")

    date_col = next((c for c in flow_df.columns if "日期" in c or "时间" in c), None)
    flow_col = next((c for c in flow_df.columns if "主力" in c and "净" in c), None)
    if not flow_col:
        flow_col = next((c for c in flow_df.columns if "净" in c), None)

    if date_col and flow_col:
        plot_df = flow_df[[date_col, flow_col]].copy().head(30)
        plot_df[flow_col] = pd.to_numeric(plot_df[flow_col], errors="coerce")
        plot_df = plot_df.dropna().sort_values(date_col)
        plot_df["color"] = plot_df[flow_col].apply(
            lambda x: POSITIVE if x >= 0 else NEGATIVE
        )
        fig_flow = go.Figure(go.Bar(
            x=plot_df[date_col],
            y=plot_df[flow_col] / 1e8,
            marker_color=plot_df["color"],
            name="主力净流入（亿元）",
        ))
        fig_flow.add_hline(y=0, line_color=TK_BORDER, line_width=1)
        fig_flow.update_layout(**dark_layout(
            height=280,
            xaxis=dict(tickangle=-30, gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            yaxis=dict(title="亿元", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        ))
        st.plotly_chart(fig_flow, width="stretch")
else:
    st.info("资金流向数据暂不可用")

st.divider()


# ── 机构评级 ──────────────────────────────────────────────────────────────────
st.subheader("机构分析师评级")

if analyst_info and forecast is not None:
    ratings     = analyst_info.get("ratings", {})
    target_mean = analyst_info.get("target_mean")
    buy_ratio   = analyst_info.get("buy_ratio", 0)

    ca, cb, cc = st.columns(3)
    with ca:
        st.metric("买入/增持占比", f"{buy_ratio:.1f}%")
    with cb:
        st.metric("卖出/减持占比", f"{analyst_info.get('sell_ratio', 0):.1f}%")
    with cc:
        if target_mean:
            upside = (target_mean / quote.price - 1) * 100 if quote.price else 0
            st.metric("平均目标价", f"¥{target_mean:.2f}",
                      delta=f"{upside:+.1f}% 空间",
                      delta_color="normal" if upside >= 0 else "inverse")
        elif analyst_info.get("eps_mean"):
            st.metric("预测年报EPS均值", f"¥{analyst_info['eps_mean']:.2f}")
        else:
            st.metric("平均目标价", "—")

    if ratings:
        fig_r = go.Figure(go.Pie(
            labels=list(ratings.keys()),
            values=list(ratings.values()),
            hole=0.45,
            textinfo="label+percent",
            textfont=dict(color=TK_TEXT),
            marker=dict(
                colors=[TK_TEAL, TK_PINK, "#FE7C59", "#8A8B98", "#4FC3F7"],
                line=dict(color=TK_BORDER, width=1),
            ),
        ))
        fig_r.update_layout(**dark_layout(height=280))
        st.plotly_chart(fig_r, width="stretch")

    with st.expander("查看完整分析师预测数据"):
        st.dataframe(forecast, hide_index=True, width="stretch")
else:
    st.info("机构评级数据暂不可用")

st.divider()


# ── Excel 导出 ────────────────────────────────────────────────────────────────
st.subheader("📥 导出研究报告")
st.caption("将当前股票的行情、财务、估值、新闻数据打包导出为 Excel 文件")

if st.button("生成 Excel 报告", type="primary", width="content"):
    with st.spinner("正在生成报告，请稍候..."):
        quote_items = [
            ("股票名称", stock_name),
            ("股票代码", code),
            ("最新价",   f"¥{quote.price:.2f}"),
            ("涨跌幅",   f"{quote.change_pct:+.2f}%"),
            ("市盈率(TTM)", f"{quote.pe_ttm:.2f}" if quote.pe_ttm else "—"),
            ("市净率",   f"{quote.pb:.2f}" if quote.pb else "—"),
            ("总市值",   f"{quote.market_cap:.2f} 亿"),
        ]
        score_items_export = [
            ("综合财务评分", f"{fin_scores.get('综合评分', '—')}"),
            ("盈利能力",     f"{fin_scores.get('盈利能力', '—')}"),
            ("成长性",       f"{fin_scores.get('成长性', '—')}"),
            ("财务安全",     f"{fin_scores.get('财务安全', '—')}"),
        ]
        val_items_export = [
            ("估值评分",     f"{val_scores.get('综合评分', '—')}"),
            ("估值判断",     val_scores.get("估值判断", "—")),
            ("PE 历史百分位", f"{pe_info.get('percentile', '—')}%"
             if pe_info.get("percentile") else "—"),
            ("PB 历史百分位", f"{pb_info.get('percentile', '—')}%"
             if pb_info.get("percentile") else "—"),
            ("PEG",          f"{peg:.2f}" if peg else "—"),
            ("ROE 趋势",     roe_info.get("trend", "—")),
        ]

        raw_inc = get_income_statement(code)
        raw_bs  = get_balance_sheet(code)
        raw_cf  = get_cash_flow(code)
        inc_df  = parse_income_statement(raw_inc) if raw_inc is not None else None
        bs_df   = parse_balance_sheet(raw_bs)     if raw_bs  is not None else None
        cf_df   = parse_cash_flow(raw_cf)         if raw_cf  is not None else None

        raw_news = get_stock_news(code, count=30)
        news_df  = None
        if raw_news is not None and not raw_news.empty:
            title_col   = next((c for c in raw_news.columns if "标题" in c), raw_news.columns[0])
            content_col = next((c for c in raw_news.columns if "内容" in c), None)
            news_df = analyze_news_batch(raw_news, title_col=title_col, content_col=content_col)

        excel_bytes = export_to_excel(
            code=code,
            stock_name=stock_name,
            quote_items=quote_items,
            score_items=score_items_export,
            valuation_items=val_items_export,
            income_df=inc_df,
            balance_df=bs_df,
            cashflow_df=cf_df,
            news_df=news_df,
        )

    filename = f"{stock_name}_{code}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    st.download_button(
        label=f"⬇️ 下载 {filename}",
        data=excel_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    st.success("报告生成完毕，点击上方按钮下载。")


# ── 底部 ──────────────────────────────────────────────────────────────────────
st.divider()
st.caption("⚠️ 估值数据来源：百度股市通 / 东方财富，综合评分仅供参考，不构成投资建议。")
