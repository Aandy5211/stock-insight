"""新闻分析页 — 新闻聚合 + 情感分析 + 关键词"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from data.fetcher import get_stock_news, get_market_news
from analysis.news import analyze_news_batch, aggregate_keywords, sentiment_summary
from utils.clock import show_world_clock
from utils.theme import (
    apply_theme, dark_layout,
    TK_PINK, TK_TEAL, TK_CARD, TK_BORDER, TK_MUTED, TK_TEXT, POSITIVE, NEGATIVE, NEUTRAL,
)

st.set_page_config(
    page_title="新闻分析 - StockInsight",
    page_icon="📰",
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
    if st.button("查询", use_container_width=True, type="primary"):
        if code_input.strip():
            st.session_state["selected_code"] = code_input.strip()
            st.rerun()
    st.divider()
    st.caption("**常用股票**")
    quick = {"贵州茅台 600519": "600519", "平安银行 000001": "000001",
             "宁德时代 300750": "300750", "招商银行 600036": "600036"}
    for label, qcode in quick.items():
        if st.button(label, use_container_width=True, key=f"q_{qcode}"):
            st.session_state["selected_code"] = qcode
            st.rerun()
    st.divider()
    news_count = st.slider("加载新闻数量", min_value=10, max_value=100, value=30, step=10)
    show_market_news = st.checkbox("同时显示财经要闻", value=False)

code = st.session_state.get("selected_code", "").strip()

# ── 语义色映射 ────────────────────────────────────────────────────────────────
LABEL_COLOR = {
    "利好": POSITIVE,
    "利空": NEGATIVE,
    "中性": NEUTRAL,
}
LABEL_ICON = {"利好": "🔴", "利空": "🟢", "中性": "⚪"}


def _neg_th(): return 0.38
def _pos_th(): return 0.62


@st.cache_data(ttl=1800, show_spinner=False)
def _load_and_analyze(code: str, count: int):
    raw = get_stock_news(code, count=count)
    if raw is None or raw.empty:
        return None, None, None, None, None
    col_title   = next((c for c in raw.columns if "标题" in c), raw.columns[0])
    col_content = next((c for c in raw.columns if "内容" in c or "摘要" in c), None)
    col_time    = next((c for c in raw.columns if "时间" in c or "日期" in c), None)
    col_source  = next((c for c in raw.columns if "来源" in c or "媒体" in c), None)
    col_url     = next((c for c in raw.columns if "链接" in c or "url" in c.lower()), None)
    df = analyze_news_batch(raw, title_col=col_title, content_col=col_content)
    summary  = sentiment_summary(df)
    keywords = aggregate_keywords(df, title_col=col_title, content_col=col_content, topk=25)
    col_map  = {"title": col_title, "content": col_content, "time": col_time,
                "source": col_source, "url": col_url}
    return df, summary, keywords, col_map, raw


# ── 主体 ──────────────────────────────────────────────────────────────────────
st.title("📰 新闻分析")

if not code:
    st.info("请在左侧输入股票代码后点击查询。")
    st.stop()

tab_stock, tab_market = st.tabs([f"📌 个股新闻 ({code})", "🌐 财经要闻"])


# ════════════════════════════════════════════════════════════════════════════
#  个股新闻
# ════════════════════════════════════════════════════════════════════════════
with tab_stock:
    with st.spinner(f"正在抓取 {code} 新闻并分析情感..."):
        df_news, summary, keywords, col_map, raw_news = _load_and_analyze(code, news_count)

    if df_news is None:
        st.warning(f"未找到 **{code}** 的相关新闻，请确认代码正确或稍后重试。")
        st.stop()

    title_col   = col_map["title"]
    content_col = col_map["content"]
    time_col    = col_map["time"]

    # ── 情感摘要卡片 ────────────────────────────────────────────────────────
    st.subheader("情感概览")
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        overall = summary.get("overall", "—")
        color = {
            "偏多": POSITIVE, "偏空": NEGATIVE, "中性": NEUTRAL
        }.get(overall, TK_MUTED)
        st.markdown(
            f'<div style="text-align:center;padding:16px;background:{TK_CARD};'
            f'border-radius:10px;border:1px solid {TK_BORDER};">'
            f'<div style="font-size:0.85em;color:{TK_MUTED};">市场情绪</div>'
            f'<div style="font-size:1.8em;font-weight:800;color:{color};">{overall}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.metric("分析新闻数", summary.get("total", 0))
    with c3:
        st.metric("🔴 利好", f"{summary.get('positive', 0)} 条 ({summary.get('positive_pct', 0)}%)")
    with c4:
        st.metric("🟢 利空", f"{summary.get('negative', 0)} 条 ({summary.get('negative_pct', 0)}%)")
    with c5:
        st.metric("⚪ 中性", f"{summary.get('neutral', 0)} 条 ({summary.get('neutral_pct', 0)}%)")

    st.divider()

    # ── 图表区 ──────────────────────────────────────────────────────────────
    col_pie, col_score, col_kw = st.columns([1, 1.5, 1.5])

    with col_pie:
        st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">情感分布</div>', unsafe_allow_html=True)
        fig_pie = go.Figure(go.Pie(
            labels=["利好", "利空", "中性"],
            values=[summary.get("positive", 0), summary.get("negative", 0), summary.get("neutral", 0)],
            marker_colors=[POSITIVE, NEGATIVE, NEUTRAL],
            hole=0.5,
            textinfo="label+percent",
            textfont=dict(color=TK_TEXT),
        ))
        fig_pie.update_layout(**dark_layout(height=260, showlegend=False))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_score:
        st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">情感分数分布</div>', unsafe_allow_html=True)
        fig_hist = go.Figure(go.Histogram(
            x=df_news["情感分数"],
            nbinsx=20,
            marker_color=TK_TEAL,
            marker_line_color=TK_BORDER,
            marker_line_width=1,
            opacity=0.8,
        ))
        fig_hist.add_vline(x=0.5, line_dash="dash", line_color=TK_MUTED,
                           annotation_text="中性线", annotation_font_color=TK_MUTED)
        mean_val = df_news["情感分数"].mean()
        fig_hist.add_vline(x=mean_val, line_dash="dot", line_color=TK_PINK,
                           annotation_text=f"均值 {mean_val:.2f}",
                           annotation_font_color=TK_PINK)
        fig_hist.update_layout(**dark_layout(
            height=260,
            xaxis=dict(title="情感分数", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            yaxis=dict(title="条数", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        ))
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_kw:
        st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">高频关键词 Top 15</div>', unsafe_allow_html=True)
        if keywords:
            kw_df = pd.DataFrame(keywords[:15], columns=["关键词", "权重"])
            # 渐变色
            n = len(kw_df)
            colors = [
                f"rgba(238,29,82,{0.4 + 0.6 * i / max(n - 1, 1):.2f})"
                for i in range(n)
            ]
            fig_kw = go.Figure(go.Bar(
                x=kw_df["权重"], y=kw_df["关键词"],
                orientation="h",
                marker_color=colors[::-1],
            ))
            fig_kw.update_layout(**dark_layout(
                height=260,
                yaxis=dict(autorange="reversed", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                xaxis=dict(title="TF-IDF 权重", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            ))
            st.plotly_chart(fig_kw, use_container_width=True)
        else:
            st.info("关键词提取失败")

    st.divider()

    # ── 情感时间线 ───────────────────────────────────────────────────────────
    if time_col and time_col in df_news.columns:
        st.markdown(f'<div style="color:{TK_TEXT};font-weight:600;margin-bottom:6px;">情感时间线</div>', unsafe_allow_html=True)
        timeline_df = df_news[[time_col, "情感分数", "情感标签", title_col]].copy()
        timeline_df[time_col] = pd.to_datetime(timeline_df[time_col], errors="coerce")
        timeline_df = timeline_df.dropna(subset=[time_col]).sort_values(time_col)

        fig_tl = go.Figure()
        for label, color in [("利好", POSITIVE), ("利空", NEGATIVE), ("中性", NEUTRAL)]:
            subset = timeline_df[timeline_df["情感标签"] == label]
            if not subset.empty:
                fig_tl.add_trace(go.Scatter(
                    x=subset[time_col], y=subset["情感分数"],
                    mode="markers", name=label,
                    marker=dict(color=color, size=9, opacity=0.8,
                                line=dict(color=TK_BORDER, width=1)),
                    text=subset[title_col].str[:40] + "...",
                    hovertemplate="%{text}<br>分数: %{y:.3f}<br>%{x}<extra></extra>",
                ))
        fig_tl.add_hline(y=0.5, line_dash="dash", line_color=TK_MUTED, line_width=1)
        fig_tl.add_hrect(
            y0=_neg_th(), y1=_pos_th(),
            fillcolor="rgba(255,255,255,0.03)", line_width=0,
            annotation_text="中性区间", annotation_font_color=TK_MUTED,
        )
        fig_tl.update_layout(**dark_layout(
            height=300,
            yaxis=dict(range=[0, 1], title="情感分数", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
            xaxis=dict(title="发布时间", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
        ))
        st.plotly_chart(fig_tl, use_container_width=True)
        st.divider()

    # ── 新闻列表 ────────────────────────────────────────────────────────────
    st.subheader("新闻列表")

    filter_cols = st.columns([1, 1, 2])
    with filter_cols[0]:
        filter_label = st.selectbox("情感筛选", ["全部", "利好", "利空", "中性"])
    with filter_cols[1]:
        sort_by = st.selectbox("排序方式", ["发布时间（最新）", "情感分数（高→低）", "情感分数（低→高）"])

    display_df = df_news.copy()
    if filter_label != "全部":
        display_df = display_df[display_df["情感标签"] == filter_label]

    if sort_by == "情感分数（高→低）":
        display_df = display_df.sort_values("情感分数", ascending=False)
    elif sort_by == "情感分数（低→高）":
        display_df = display_df.sort_values("情感分数", ascending=True)
    elif time_col and time_col in display_df.columns:
        display_df = display_df.sort_values(time_col, ascending=False)

    for _, row in display_df.iterrows():
        label      = row.get("情感标签", "中性")
        score      = row.get("情感分数", 0.5)
        icon       = LABEL_ICON.get(label, "⚪")
        color      = LABEL_COLOR.get(label, NEUTRAL)
        title      = str(row.get(title_col, ""))
        kws        = str(row.get("关键词", ""))
        time_str   = str(row.get(time_col, "")) if time_col else ""
        source_str = str(row.get(col_map["source"], "")) if col_map["source"] else ""
        url_str    = str(row.get(col_map["url"], "")) if col_map["url"] else ""
        meta = " · ".join(filter(lambda x: x and x != "nan", [source_str, time_str]))

        st.markdown(
            f"""<div style="padding:12px 16px;margin-bottom:8px;border-radius:8px;
                background:{TK_CARD};border-left:3px solid {color};
                border-top:1px solid {TK_BORDER};border-right:1px solid {TK_BORDER};
                border-bottom:1px solid {TK_BORDER};
                transition:border-color .2s;">
                <div style="font-size:0.8em;color:{TK_MUTED};margin-bottom:4px;">{meta}</div>
                <div style="font-size:0.97em;font-weight:500;color:{TK_TEXT};">{icon} {title}</div>
                <div style="font-size:0.8em;margin-top:5px;">
                    <span style="color:{color};font-weight:600;">{label}</span>
                    <span style="color:{TK_MUTED};">&nbsp;·&nbsp; 分数 {score:.3f}
                    &nbsp;·&nbsp; 关键词：{kws}</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    with st.expander("查看原始数据表"):
        show_cols = [c for c in [title_col, time_col, col_map["source"],
                                 "情感标签", "情感分数", "置信度", "关键词"]
                     if c and c in display_df.columns]
        st.dataframe(display_df[show_cols], hide_index=True, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
#  财经要闻
# ════════════════════════════════════════════════════════════════════════════
with tab_market:
    if not show_market_news:
        st.info('在左侧勾选「同时显示财经要闻」后加载。')
    else:
        with st.spinner("加载财经要闻..."):
            raw_market = get_market_news(count=30)

        if raw_market is None or raw_market.empty:
            st.warning("财经要闻暂时无法获取。")
        else:
            title_m   = next((c for c in raw_market.columns if "标题" in c), raw_market.columns[0])
            content_m = next((c for c in raw_market.columns if "内容" in c or "摘要" in c), None)
            time_m    = next((c for c in raw_market.columns if "时间" in c or "日期" in c), None)

            df_market = analyze_news_batch(raw_market, title_col=title_m, content_col=content_m)
            sum_m     = sentiment_summary(df_market)
            kw_m      = aggregate_keywords(df_market, title_col=title_m, content_col=content_m, topk=20)

            ca, cb, cc, cd = st.columns(4)
            with ca:
                st.metric("🔴 利好", f"{sum_m.get('positive', 0)} ({sum_m.get('positive_pct', 0)}%)")
            with cb:
                st.metric("🟢 利空", f"{sum_m.get('negative', 0)} ({sum_m.get('negative_pct', 0)}%)")
            with cc:
                st.metric("⚪ 中性", f"{sum_m.get('neutral', 0)} ({sum_m.get('neutral_pct', 0)}%)")
            with cd:
                st.metric("市场情绪", sum_m.get("overall", "—"))

            st.divider()

            if kw_m:
                kw_df_m = pd.DataFrame(kw_m[:15], columns=["关键词", "权重"])
                n = len(kw_df_m)
                colors_m = [
                    f"rgba(37,244,238,{0.4 + 0.6 * i / max(n - 1, 1):.2f})"
                    for i in range(n)
                ]
                fig_kw_m = go.Figure(go.Bar(
                    x=kw_df_m["权重"], y=kw_df_m["关键词"],
                    orientation="h", marker_color=colors_m[::-1],
                ))
                fig_kw_m.update_layout(**dark_layout(
                    height=280,
                    yaxis=dict(autorange="reversed", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                    xaxis=dict(title="热点关键词", gridcolor=TK_BORDER, color=TK_MUTED, linecolor=TK_BORDER),
                ))
                st.plotly_chart(fig_kw_m, use_container_width=True)

            for _, row in df_market.iterrows():
                label    = row.get("情感标签", "中性")
                color    = LABEL_COLOR.get(label, NEUTRAL)
                icon     = LABEL_ICON.get(label, "⚪")
                title    = str(row.get(title_m, ""))
                time_str = str(row.get(time_m, "")) if time_m else ""
                score    = row.get("情感分数", 0.5)
                kws      = str(row.get("关键词", ""))
                st.markdown(
                    f"""<div style="padding:10px 14px;margin-bottom:6px;border-radius:8px;
                        background:{TK_CARD};border-left:3px solid {color};
                        border-top:1px solid {TK_BORDER};border-right:1px solid {TK_BORDER};
                        border-bottom:1px solid {TK_BORDER};">
                        <div style="font-size:0.78em;color:{TK_MUTED};">{time_str}</div>
                        <div style="color:{TK_TEXT};">{icon} {title}</div>
                        <div style="font-size:0.78em;color:{color};margin-top:3px;">
                            {label} · {score:.3f} · {kws}
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )


# ── 底部 ──────────────────────────────────────────────────────────────────────
st.divider()
st.caption("⚠️ 情感分析基于 SnowNLP 模型，结果仅供参考，不构成投资建议。")
