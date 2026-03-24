"""
财务指标评分体系

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
评分依据与数据来源
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【ROE 门槛】
  来源：同花顺 F10「核心指标」盈利能力模块；
        巴菲特选股标准（持续 ROE≥15% 为优质公司）；
        Wind A 股全市场统计：中位 ROE 约 8%，优质蓝筹约 10~15%。
  参考：https://www.10jqka.com.cn（同花顺 F10 财务摘要）

【毛利率分档】
  来源：东方财富证券研究所行业对比报告；
        申万宏源/中信证券行业分析师常用毛利率基准：
        白酒≥85%、医药≥60%、消费/科技≥40%、制造≥25%、贸易≥15%。
  参考：https://data.eastmoney.com（东方财富行业比较）

【净利率分档】
  来源：证监会《上市公司信息披露管理办法》财务摘要及
        东方财富 Choice 「盈利质量」模块，净利率<5% 被标注为"低质量盈利"。
  参考：https://choice.eastmoney.com

【成长性 YoY 分档】
  来源：国家统计局 GDP 增速（~5%）作为成长下限基准；
        同花顺 F10「成长能力」—— 营收/净利润连续3年增长为"持续成长"标签。
  参考：https://data.stats.gov.cn（国家统计局）
        https://www.10jqka.com.cn（同花顺 F10 成长分析）

【利润增速质量（利润 vs 营收）】
  来源：东方财富 Choice「盈利质量模型」——利润增速高于营收增速为
        正向经营杠杆，反之为利润率承压信号。
  参考：https://choice.eastmoney.com

【资产负债率分档】
  来源：中证指数有限公司行业负债率基准；
        穆迪/标普评级方法：非金融企业负债率≥70% 为"负面关注"，
        ≤40% 为"财务稳健"；
        A 股证监会退市规则：连续2年净亏损触发 ST 预警。
  参考：https://www.csindex.com.cn（中证指数）
        https://www.csrc.gov.cn（证监会退市规则）

【综合权重 40/35/25】
  来源：同花顺 F10「综合评分」权重结构（盈利质量>成长>安全）；
        东方财富 Choice「基本面评分」权重参考。
  参考：https://www.10jqka.com.cn

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import pandas as pd
from data.models import FinancialMetrics


# ── 工具 ──────────────────────────────────────────────────────────────────────

def get_latest_metrics(metrics: list[FinancialMetrics]) -> FinancialMetrics | None:
    """返回最新一期财务指标"""
    return metrics[0] if metrics else None


def metrics_to_dataframe(metrics: list[FinancialMetrics]) -> pd.DataFrame:
    """将多期财务指标转为 DataFrame"""
    if not metrics:
        return pd.DataFrame()
    return pd.DataFrame([{
        "报告期":        m.report_date,
        "ROE(%)":       m.roe,
        "毛利率(%)":    m.gross_margin,
        "净利率(%)":    m.net_margin,
        "营收同比(%)":  m.revenue_yoy,
        "净利润同比(%)":m.profit_yoy,
        "资产负债率(%)":m.debt_ratio,
    } for m in metrics])


# ── 盈利能力评分 ──────────────────────────────────────────────────────────────

def score_profitability(
    m: FinancialMetrics,
    history: list[FinancialMetrics] | None = None,
) -> tuple[float, str]:
    """
    盈利能力评分 0~100，返回 (分值, 说明文字)

    维度权重：
      ROE 水平          40 分  ← 同花顺 F10 / 巴菲特标准
      毛利率            25 分  ← 东方财富行业对比
      净利率            20 分  ← Choice 盈利质量模块
      多期 ROE 稳定性   15 分  ← 同花顺"持续盈利"标签
    """
    score  = 0.0
    labels = []

    # ── ROE 40分 ──────────────────────────────────────────────────────────────
    # 巴菲特：持续 ROE≥15% 为优质公司
    # Wind A股：全市场中位 ROE≈8%；主板蓝筹中位≈10%
    roe = m.roe
    if roe >= 20:
        score += 40
        labels.append(f"ROE {roe:.1f}% · 超优质 ≥20%（来源：Wind A股Top10%分位）")
    elif roe >= 15:
        score += 32
        labels.append(f"ROE {roe:.1f}% · 优质 ≥15%（来源：巴菲特选股门槛）")
    elif roe >= 10:
        score += 22
        labels.append(f"ROE {roe:.1f}% · 中等偏上 ≥10%（来源：Wind A股中位线）")
    elif roe >= 5:
        score += 12
        labels.append(f"ROE {roe:.1f}% · 中等偏下 ≥5%")
    elif roe >= 0:
        score +=  4
        labels.append(f"ROE {roe:.1f}% · 微利")
    else:
        labels.append(f"ROE {roe:.1f}% · 亏损")

    # ── 毛利率 25分 ───────────────────────────────────────────────────────────
    # 东方财富行业基准：白酒≥85%；医药≥60%；消费/科技≥40%；制造≥25%；贸易≥15%
    gm = m.gross_margin
    if gm >= 60:
        score += 25
        labels.append(f"毛利率 {gm:.1f}% · 极强定价权 ≥60%（白酒/医药级，来源：东方财富行业对比）")
    elif gm >= 40:
        score += 20
        labels.append(f"毛利率 {gm:.1f}% · 较强 ≥40%（消费/科技基准）")
    elif gm >= 25:
        score += 14
        labels.append(f"毛利率 {gm:.1f}% · 中等 ≥25%（制造业基准）")
    elif gm >= 15:
        score +=  7
        labels.append(f"毛利率 {gm:.1f}% · 偏低 ≥15%（贸易流通基准）")
    elif gm >= 5:
        score +=  3
        labels.append(f"毛利率 {gm:.1f}% · 较弱 ≥5%")
    else:
        labels.append(f"毛利率 {gm:.1f}% · 极弱")

    # ── 净利率 20分 ───────────────────────────────────────────────────────────
    # Choice 盈利质量模块：净利率<5% 标注为低质量盈利
    nm = m.net_margin
    if nm >= 25:
        score += 20
        labels.append(f"净利率 {nm:.1f}% · 极佳 ≥25%")
    elif nm >= 15:
        score += 16
        labels.append(f"净利率 {nm:.1f}% · 优质 ≥15%")
    elif nm >= 8:
        score += 11
        labels.append(f"净利率 {nm:.1f}% · 中等 ≥8%")
    elif nm >= 3:
        score +=  6
        labels.append(f"净利率 {nm:.1f}% · 偏低 ≥3%（来源：Choice 低质量盈利线）")
    elif nm >= 0:
        score +=  2
        labels.append(f"净利率 {nm:.1f}% · 微利")
    else:
        labels.append(f"净利率 {nm:.1f}% · 亏损")

    # ── 多期 ROE 稳定性 15分 ──────────────────────────────────────────────────
    # 同花顺 F10「持续盈利」标签：连续3年盈利即打标
    if history and len(history) >= 3:
        n = min(len(history), 4)
        roe_vals = [h.roe for h in history[:n]]
        all_pos  = all(r > 0 for r in roe_vals)
        all_10p  = all(r >= 10 for r in roe_vals)
        all_5p   = all(r >= 5  for r in roe_vals)
        any_loss = any(r < 0  for r in roe_vals)
        improving = roe_vals[0] > roe_vals[-1]  # 最新期 > 最早期

        if all_10p:
            score += 15
            labels.append(f"近{n}期 ROE 均≥10% · 持续高盈利（来源：同花顺持续盈利标签）")
        elif all_5p:
            score += 10
            labels.append(f"近{n}期 ROE 均≥5% · 连续盈利")
        elif all_pos:
            score +=  6
            labels.append(f"近{n}期持续盈利")
        elif any_loss:
            score = max(0, score - 15)
            labels.append(f"近{n}期存在亏损 · 风险信号")
        if improving and not any_loss:
            score = min(score + 3, 100)
            labels.append("ROE 趋势向上 ↑")

    return round(min(score, 100), 1), "  /  ".join(labels)


# ── 成长性评分 ────────────────────────────────────────────────────────────────

def score_growth(
    m: FinancialMetrics,
    history: list[FinancialMetrics] | None = None,
) -> tuple[float, str]:
    """
    成长性评分 0~100，返回 (分值, 说明文字)

    维度权重：
      营收 YoY          30 分  ← GDP增速5%为基线（国家统计局）
      净利润 YoY        30 分  ← 同上
      利润增速质量      15 分  ← 东方财富 Choice 盈利质量模型
      多期增长连续性    25 分  ← 同花顺 F10 连续增长N年统计
    """
    score  = 0.0
    labels = []

    # ── 营收 YoY 30分 ─────────────────────────────────────────────────────────
    # 国家统计局 GDP 增速约5%为基线；≥10% 视为有效成长；≥20% 为高成长
    rev = m.revenue_yoy
    if rev >= 30:
        score += 30
        labels.append(f"营收 +{rev:.1f}% · 高成长（来源：同花顺成长能力 ≥30% 档）")
    elif rev >= 20:
        score += 25
        labels.append(f"营收 +{rev:.1f}% · 较快增长 ≥20%")
    elif rev >= 10:
        score += 18
        labels.append(f"营收 +{rev:.1f}% · 温和成长 ≥10%（超GDP增速 2x）")
    elif rev >= 5:
        score += 12
        labels.append(f"营收 +{rev:.1f}% · 略超 GDP 基线 5%（来源：国家统计局）")
    elif rev >= 0:
        score +=  6
        labels.append(f"营收 +{rev:.1f}% · 微增")
    else:
        labels.append(f"营收 {rev:.1f}% · 负增长")

    # ── 净利润 YoY 30分 ───────────────────────────────────────────────────────
    prof = m.profit_yoy
    if prof >= 30:
        score += 30
        labels.append(f"净利 +{prof:.1f}% · 高成长")
    elif prof >= 20:
        score += 25
        labels.append(f"净利 +{prof:.1f}% · 较快增长")
    elif prof >= 10:
        score += 18
        labels.append(f"净利 +{prof:.1f}% · 温和成长")
    elif prof >= 5:
        score += 12
        labels.append(f"净利 +{prof:.1f}% · 略超 GDP")
    elif prof >= 0:
        score +=  6
        labels.append(f"净利 +{prof:.1f}% · 微增")
    else:
        labels.append(f"净利 {prof:.1f}% · 负增长")

    # ── 利润增速质量 15分 ─────────────────────────────────────────────────────
    # 东方财富 Choice：利润增速>营收增速 = 正向经营杠杆（边际利润率提升）
    if rev > 0 and prof > 0:
        diff = prof - rev
        if diff >= 10:
            score += 15
            labels.append(f"利润跑赢营收 +{diff:.1f}% · 盈利质量优（来源：Choice 盈利质量模型）")
        elif diff >= 0:
            score += 10
            labels.append("利润与营收同步增长")
        elif diff >= -10:
            score +=  5
            labels.append(f"利润慢于营收 {diff:.1f}% · 利润率小幅承压")
        else:
            score +=  2
            labels.append(f"增收不增利 · 利润率明显下滑（来源：Choice 盈利质量预警）")
    elif rev > 0 and prof <= 0:
        labels.append("营收增长但净利下降 · 警惕")
    elif rev <= 0 and prof > 0:
        score += 5
        labels.append("降本增利 · 成本管控改善")

    # ── 多期增长连续性 25分 ───────────────────────────────────────────────────
    # 同花顺 F10「连续增长N年」：连续3年营收/净利均为正增长打 ✓ 标
    if history and len(history) >= 3:
        n = min(len(history), 4)
        rev_pos  = [h.revenue_yoy > 0 for h in history[:n]]
        prof_pos = [h.profit_yoy  > 0 for h in history[:n]]
        continuity = (sum(rev_pos) + sum(prof_pos)) / (2 * n)

        if continuity >= 0.875:
            score += 25
            labels.append(f"近{n}期营收/利润均持续增长 ✓（来源：同花顺连续增长标签）")
        elif continuity >= 0.75:
            score += 20
            labels.append(f"近{n}期增长连续性较好")
        elif continuity >= 0.5:
            score += 12
            labels.append(f"近{n}期增长稳定性一般")
        elif continuity >= 0.25:
            score +=  5
            labels.append(f"近{n}期增长不稳定")
        else:
            labels.append(f"近{n}期多数为负增长 · 衰退信号")

        # 增速加快额外加分
        if len(history) >= 2:
            hist_avg = sum(h.revenue_yoy for h in history[1:4]) / max(len(history[1:4]), 1)
            if m.revenue_yoy > hist_avg + 5 and m.revenue_yoy > 0:
                score = min(score + 5, 100)
                labels.append("营收增速加快 ↑")

    return round(min(score, 100), 1), "  /  ".join(labels)


# ── 财务安全评分 ──────────────────────────────────────────────────────────────

def score_safety(
    m: FinancialMetrics,
    history: list[FinancialMetrics] | None = None,
) -> tuple[float, str]:
    """
    财务安全性评分 0~100，返回 (分值, 说明文字)

    维度权重：
      资产负债率        50 分  ← 穆迪/标普评级方法；中证指数行业基准
      盈利持续性        30 分  ← A 股 ST/ST* 退市规则（证监会）
      负债率趋势        20 分  ← 信用评级机构杠杆趋势分析方法
    """
    score  = 0.0
    labels = []

    # ── 资产负债率 50分 ───────────────────────────────────────────────────────
    # 穆迪/标普：非金融企业负债率≥70% 为"负面关注"；≤40% 为"财务稳健"
    # 注：银行/保险等金融机构负债率天然≥85%，本分档适用非金融企业
    dr = m.debt_ratio
    if dr <= 30:
        score += 50
        labels.append(f"负债率 {dr:.1f}% · 极安全 ≤30%（来源：穆迪财务稳健标准）")
    elif dr <= 45:
        score += 40
        labels.append(f"负债率 {dr:.1f}% · 健康 ≤45%")
    elif dr <= 60:
        score += 28
        labels.append(f"负债率 {dr:.1f}% · 中等 ≤60%（来源：中证指数行业中位线）")
    elif dr <= 70:
        score += 16
        labels.append(f"负债率 {dr:.1f}% · 偏高 ≤70%（来源：标普负面关注线）")
    elif dr <= 80:
        score +=  6
        labels.append(f"负债率 {dr:.1f}% · 高风险 ≤80%")
    else:
        labels.append(f"负债率 {dr:.1f}% · 极高风险 >80%（来源：穆迪/标普高风险分档）")

    # ── 盈利持续性 30分 ───────────────────────────────────────────────────────
    # 证监会退市规则：连续2年净亏损 → ST；连续3年 → ST*（强制退市风险）
    if history and len(history) >= 2:
        n = min(len(history), 4)
        recent = history[:n]
        profitable = [h.roe > 0 for h in recent]
        p_count = sum(profitable)

        if p_count == n:
            score += 30
            labels.append(f"近{n}期持续盈利（来源：同花顺持续盈利标签）")
        elif p_count >= n - 1:
            score += 22
            labels.append(f"近{n}期偶有亏损")
        elif p_count >= n // 2:
            score += 12
            labels.append(f"近{n}期盈利不稳定")
        else:
            labels.append(f"近{n}期多次亏损 · 存在退市风险")

        # 连续两期亏损 → ST 预警
        if recent[0].roe < 0 and recent[1].roe < 0:
            score = max(0, score - 20)
            labels.append("⚠ 连续亏损 ST 风险（来源：证监会退市规则）")
    else:
        if m.roe > 0:
            score += 18
            labels.append("当期盈利")
        else:
            labels.append("当期亏损")

    # ── 负债率趋势 20分 ───────────────────────────────────────────────────────
    # 信用评级机构方法：持续加杠杆为负面信号；去杠杆为正面信号
    if history and len(history) >= 3:
        dr_vals = [h.debt_ratio for h in history[:4]]
        dr_diff = dr_vals[0] - dr_vals[-1]   # 正数 = 负债率上升
        if dr_diff <= -5:
            score += 20
            labels.append(f"负债率下降 {abs(dr_diff):.1f}% · 去杠杆（来源：信用评级正面信号）")
        elif dr_diff <= 0:
            score += 15
            labels.append("负债率稳定")
        elif dr_diff <= 5:
            score += 10
            labels.append(f"负债率小幅上升 {dr_diff:.1f}%")
        elif dr_diff <= 15:
            score +=  4
            labels.append(f"负债率明显上升 {dr_diff:.1f}% · 加杠杆（来源：信用评级负面信号）")
        else:
            labels.append(f"负债率急升 {dr_diff:.1f}% · 杠杆风险（来源：穆迪加杠杆预警）")
    else:
        score += 10  # 数据不足给中性分

    return round(min(score, 100), 1), "  /  ".join(labels)


# ── 综合评分 ──────────────────────────────────────────────────────────────────

def composite_score(
    m: FinancialMetrics,
    history: list[FinancialMetrics] | None = None,
) -> dict:
    """
    综合财务评分（0~100）

    权重：盈利能力 40% + 成长性 35% + 财务安全 25%
    来源：同花顺 F10 综合评分权重结构；东方财富 Choice 基本面评分参考

    Returns:
        dict，包含各维度分值、说明文字及数据来源注释
    """
    if m is None:
        empty = {"综合评分": 0, "盈利能力": 0, "成长性": 0, "财务安全": 0,
                 "盈利能力说明": "", "成长性说明": "", "财务安全说明": ""}
        return empty

    p, p_label = score_profitability(m, history)
    g, g_label = score_growth(m, history)
    s, s_label = score_safety(m, history)

    total = round(p * 0.40 + g * 0.35 + s * 0.25, 1)

    return {
        "综合评分":     total,
        "盈利能力":     p,
        "成长性":       g,
        "财务安全":     s,
        "盈利能力说明": p_label,
        "成长性说明":   g_label,
        "财务安全说明": s_label,
    }


def score_label(score: float) -> str:
    """将数值评分映射为文字等级（参考同花顺星级评定）"""
    if score >= 85: return "优秀"
    if score >= 70: return "良好"
    if score >= 55: return "中等"
    if score >= 40: return "偏弱"
    return "较差"
