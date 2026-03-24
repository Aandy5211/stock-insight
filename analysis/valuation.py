"""估值分析模块：PE/PB 历史百分位、PEG、ROE 趋势、资金流向、综合评分"""
import logging
import numpy as np
import pandas as pd
from data.models import FinancialMetrics, QuoteData

logger = logging.getLogger(__name__)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def calc_percentile(series: pd.Series, current_val: float) -> float | None:
    """
    计算 current_val 在 series 中的百分位（0~100）
    百分位越低说明当前估值越便宜
    """
    try:
        clean = series.dropna().astype(float)
        clean = clean[clean > 0]
        if len(clean) < 10:
            return None
        return round(float(np.sum(clean <= current_val) / len(clean) * 100), 1)
    except Exception as e:
        logger.warning(f"calc_percentile 失败: {e}")
        return None


def rolling_percentile(series: pd.Series, window: int = 250 * 5) -> pd.Series:
    """计算 rolling 历史百分位，用于绘图"""
    def _pct(x):
        cur = x.iloc[-1]
        hist = x.dropna()
        hist = hist[hist > 0]
        if len(hist) < 2:
            return np.nan
        return float(np.sum(hist <= cur) / len(hist) * 100)

    return series.rolling(window=window, min_periods=20).apply(_pct, raw=False)


# ── PE/PB 百分位评分 ───────────────────────────────────────────────────────────

def analyze_valuation_history(df: pd.DataFrame,
                               current_val: float,
                               years: int = 5) -> dict:
    """
    分析历史估值，返回百分位、区间统计
    df 须含 date / value 两列
    """
    if df is None or df.empty:
        return {}
    try:
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
        sub = df[df["date"] >= cutoff]["value"].dropna().astype(float)
        sub = sub[sub > 0]
        if len(sub) < 10:
            return {}
        return {
            "current": round(current_val, 2),
            "min": round(sub.min(), 2),
            "max": round(sub.max(), 2),
            "median": round(sub.median(), 2),
            "mean": round(sub.mean(), 2),
            "percentile": calc_percentile(sub, current_val),
            "years": years,
            "count": len(sub),
        }
    except Exception as e:
        logger.warning(f"analyze_valuation_history 失败: {e}")
        return {}


def score_percentile(percentile: float | None) -> float:
    """
    根据历史百分位评分（百分位越低 = 估值越便宜 = 分越高）

    分档依据：
      同花顺、东方财富、雪球 PE/PB 百分位估值法均采用10档分位表述：
      ≤10%  = 历史极低位（接近历史最便宜）
      ≤20%  = 历史低位
      ≤30%  = 偏低估
      ≤40%  = 合理偏低
      ≤50%  = 历史中位线以下
      ≤60%  = 历史中位线以上
      ≤70%  = 合理偏贵
      ≤80%  = 偏高估
      ≤90%  = 历史高位
      >90%  = 历史极高位（接近历史最贵）

    来源：同花顺 F10 PE/PB 历史百分位；雪球「估值」频道分位表述；
          东方财富「F10→估值分析」10档分位法
    参考：https://www.10jqka.com.cn  https://xueqiu.com
    """
    if percentile is None:
        return 50.0  # 数据不足给中性分
    if percentile <= 10:
        return 100.0   # 历史极低位，极度低估
    elif percentile <= 20:
        return 88.0    # 历史低位
    elif percentile <= 30:
        return 76.0    # 偏低估
    elif percentile <= 40:
        return 64.0    # 合理偏低
    elif percentile <= 50:
        return 55.0    # 历史中位线以下
    elif percentile <= 60:
        return 46.0    # 历史中位线以上
    elif percentile <= 70:
        return 35.0    # 合理偏贵
    elif percentile <= 80:
        return 24.0    # 偏高估
    elif percentile <= 90:
        return 14.0    # 历史高位
    return 8.0         # 历史极高位，极度高估


# ── PEG 评分 ──────────────────────────────────────────────────────────────────

def calc_peg(pe: float, earnings_growth_pct: float) -> float | None:
    """
    PEG = PE / 净利润增速(%)
    growth < 0 无意义，返回 None
    """
    try:
        if earnings_growth_pct <= 0 or pe <= 0:
            return None
        return round(pe / earnings_growth_pct, 2)
    except Exception:
        return None


def score_peg(peg: float | None) -> float:
    """
    PEG 评分

    依据：彼得·林奇（Peter Lynch）PEG 理论：PEG=1 为公允价值基准；
          PEG<1 表示被低估；PEG>2 通常被认为高估。
          同花顺/东方财富 PEG 指标注释均以此为依据。

    分档：
      < 0.5  → 100 深度低估（来源：林奇，《彼得林奇的成功投资》）
      0.5~1  →  80 合理低估（PEG=1 为公允价值）
      1~1.5  →  55 合理
      1.5~2  →  30 合理偏贵
      ≥ 2    →  10 高估（来源：市场通行标准）
      None   →  50 数据不足，中性

    参考：https://www.10jqka.com.cn（同花顺 F10 估值分析 PEG 说明）
    """
    if peg is None:
        return 50.0
    if peg < 0.5:
        return 100.0
    elif peg < 1.0:
        return 80.0
    elif peg < 1.5:
        return 55.0
    elif peg < 2.0:
        return 30.0
    return 10.0


# ── ROE 趋势评分 ──────────────────────────────────────────────────────────────

def analyze_roe_trend(metrics: list[FinancialMetrics]) -> dict:
    """
    分析近期 ROE 趋势
    返回 trend: "上升" / "稳定" / "下降"，slope, values
    """
    if not metrics or len(metrics) < 2:
        return {"trend": "数据不足", "slope": 0.0, "values": []}

    # metrics 按时间倒序，取最近 6 期，反转为正序
    recent = metrics[:6][::-1]
    values = []
    for m in recent:
        try:
            values.append(float(m.roe))
        except Exception:
            values.append(0.0)

    if len(values) < 2:
        return {"trend": "数据不足", "slope": 0.0, "values": values}

    x = np.arange(len(values), dtype=float)
    slope = float(np.polyfit(x, values, 1)[0])

    if slope > 0.5:
        trend = "上升"
    elif slope < -0.5:
        trend = "下降"
    else:
        trend = "稳定"

    return {
        "trend": trend,
        "slope": round(slope, 3),
        "values": values,
        "dates": [m.report_date for m in recent],
        "avg": round(float(np.mean(values)), 2),
    }


def score_roe_trend(roe_info: dict) -> float:
    """
    ROE 趋势评分：上升 > 稳定 > 下降，且 ROE 绝对值越高越好
    """
    if not roe_info or "values" not in roe_info or not roe_info["values"]:
        return 50.0
    avg = roe_info.get("avg", 0)
    trend = roe_info.get("trend", "稳定")

    # 基础分：ROE 水平
    if avg >= 20:
        base = 70
    elif avg >= 15:
        base = 55
    elif avg >= 10:
        base = 40
    elif avg >= 5:
        base = 20
    else:
        base = 5

    # 趋势加成
    bonus = {"上升": 30, "稳定": 15, "下降": 0}.get(trend, 15)
    return min(base + bonus, 100)


# ── 资金流向评分 ──────────────────────────────────────────────────────────────

def analyze_fund_flow(df: pd.DataFrame, days: int = 10) -> dict:
    """
    分析近 N 日主力资金净流入情况
    """
    if df is None or df.empty:
        return {}
    df = df.copy()
    # 找日期列和主力净流入列
    date_col = next((c for c in df.columns if "日期" in c or "时间" in c), None)
    flow_col = next((c for c in df.columns if "主力" in c and "净" in c), None)
    if not flow_col:
        flow_col = next((c for c in df.columns if "净" in c), None)
    if not flow_col:
        return {}

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values(date_col, ascending=False)

    recent = df.head(days)
    try:
        flows = recent[flow_col].astype(float)
        total = float(flows.sum())
        actual_days = len(flows)
        pos_days = int((flows > 0).sum())
        return {
            "total_flow": round(total / 1e8, 2),   # 亿元
            "pos_days": pos_days,
            "neg_days": actual_days - pos_days,
            "avg_daily": round(total / actual_days / 1e8, 2),
            "days": actual_days,
        }
    except Exception as e:
        logger.warning(f"analyze_fund_flow 失败: {e}")
        return {}


def score_fund_flow(flow_info: dict) -> float:
    """
    主力资金净流入评分
    总净流入 > 0 且流入天数多 → 高分
    """
    if not flow_info:
        return 50.0
    total = flow_info.get("total_flow", 0)
    pos_days = flow_info.get("pos_days", 0)
    days = flow_info.get("days", 10)

    pos_ratio = pos_days / days if days else 0

    # 资金量分（50分）
    if total > 5:
        amount_score = 50
    elif total > 1:
        amount_score = 40
    elif total > 0:
        amount_score = 25
    elif total > -1:
        amount_score = 15
    else:
        amount_score = 0

    # 持续性分（50分）
    continuity_score = round(pos_ratio * 50)
    return min(amount_score + continuity_score, 100)


# ── 分析师预测评分 ────────────────────────────────────────────────────────────

def analyze_analyst_forecast(df: pd.DataFrame) -> dict:
    """
    解析分析师预测数据，兼容同花顺 EPS 预测格式和东方财富评级格式
    """
    if df is None or df.empty:
        return {}
    try:
        result = {"raw": df}

        # ── 同花顺 EPS 预测格式：预测年度 / 均值 / 最小值 / 最大值 ────────────
        year_col = next((c for c in df.columns if "年" in c and "度" in c), None)
        mean_col = next((c for c in df.columns if "均值" in c or "平均" in c), None)

        if year_col and mean_col:
            tmp = df[[year_col, mean_col]].copy()
            tmp[year_col] = pd.to_numeric(tmp[year_col], errors="coerce")
            tmp[mean_col] = pd.to_numeric(tmp[mean_col], errors="coerce")
            tmp = tmp.dropna().sort_values(year_col)
            if not tmp.empty:
                eps_vals = tmp[mean_col].values
                # EPS 增速判断：上升→偏多，否则中性/偏空
                if len(eps_vals) >= 2 and eps_vals[-1] > eps_vals[0] * 1.05:
                    result["buy_ratio"] = 70.0
                    result["sell_ratio"] = 5.0
                    result["ratings"] = {"EPS 预期增长": int(tmp[year_col].max())}
                elif len(eps_vals) >= 2 and eps_vals[-1] < eps_vals[0] * 0.95:
                    result["buy_ratio"] = 25.0
                    result["sell_ratio"] = 35.0
                    result["ratings"] = {"EPS 预期下降": int(tmp[year_col].max())}
                else:
                    result["buy_ratio"] = 50.0
                    result["sell_ratio"] = 15.0
                    result["ratings"] = {"EPS 预期平稳": int(tmp[year_col].max())}
                # 用最新年度均值 EPS 标记（用于展示，非目标价）
                result["eps_mean"] = round(float(eps_vals[-1]), 2)
            return result

        # ── 东方财富评级格式（保留兼容）────────────────────────────────────────
        rating_col = next((c for c in df.columns if "评级" in c), None)
        target_col = next((c for c in df.columns if "目标" in c and "价" in c), None)

        if rating_col:
            ratings = df[rating_col].value_counts().to_dict()
            result["ratings"] = ratings
            pos_words = ["买入", "增持", "强烈推荐", "推荐"]
            neg_words = ["卖出", "减持", "回避"]
            pos = sum(v for k, v in ratings.items()
                      if any(w in str(k) for w in pos_words))
            neg = sum(v for k, v in ratings.items()
                      if any(w in str(k) for w in neg_words))
            total = len(df)
            result["buy_ratio"] = round(pos / total * 100, 1) if total else 0
            result["sell_ratio"] = round(neg / total * 100, 1) if total else 0

        if target_col:
            targets = pd.to_numeric(df[target_col], errors="coerce").dropna()
            if not targets.empty:
                result["target_mean"] = round(targets.mean(), 2)
                result["target_max"] = round(targets.max(), 2)
                result["target_min"] = round(targets.min(), 2)

        return result
    except Exception as e:
        logger.warning(f"analyze_analyst_forecast 失败: {e}")
        return {}


def score_analyst(forecast_info: dict) -> float:
    """
    基于机构评级买入比例评分
    """
    if not forecast_info:
        return 50.0
    buy_ratio = forecast_info.get("buy_ratio", 50)
    if buy_ratio >= 80:
        return 90.0
    elif buy_ratio >= 60:
        return 70.0
    elif buy_ratio >= 40:
        return 50.0
    elif buy_ratio >= 20:
        return 30.0
    return 15.0


# ── 综合估值评分 ──────────────────────────────────────────────────────────────

def composite_valuation_score(
    pe_info: dict,
    pb_info: dict,
    peg: float | None,
    roe_info: dict,
    flow_info: dict,
    analyst_info: dict,
) -> dict:
    """
    综合估值评分（0~100）

    权重依据：
      PE 百分位   30%  ← 最主流估值指标，同花顺/东方财富 F10 估值分析首位
      PEG         25%  ← 林奇理论，成长性调整后的 PE，Wind/Choice 均收录
      ROE 趋势    20%  ← 盈利质量因子，参照 MSCI 质量因子模型
      PB 百分位   15%  ← 重资产/银行类股票核心指标（申万宏源/中信使用）
      资金流向     5%  ← 短期市场情绪，同花顺主力资金流向（滞后信号，低权重）
      机构评级     5%  ← 卖方分析师共识（滞后于市场，低权重）

    来源：
      - 同花顺 F10「估值分析」权重参考 https://www.10jqka.com.cn
      - Wind 量化因子库（质量因子 ROE 权重）https://www.wind.com.cn
      - MSCI World Quality Index 因子权重（ROE、盈利稳定性）
      - 彼得·林奇 PEG 理论《彼得林奇的成功投资》

    估值判断分档：
      ≥75  → 低估       （来源：雪球/同花顺通行标准）
      ≥58  → 合理偏低
      ≥45  → 合理
      ≥32  → 合理偏高
      <32  → 高估
    """
    s_pe       = score_percentile(pe_info.get("percentile"))
    s_pb       = score_percentile(pb_info.get("percentile"))
    s_peg      = score_peg(peg)
    s_roe      = score_roe_trend(roe_info)
    s_flow     = score_fund_flow(flow_info)
    s_analyst  = score_analyst(analyst_info)

    total = (
        s_pe      * 0.30
        + s_peg   * 0.25
        + s_roe   * 0.20
        + s_pb    * 0.15
        + s_flow  * 0.05
        + s_analyst * 0.05
    )

    def val_label(score):
        if score >= 75: return "低估"
        if score >= 58: return "合理偏低"
        if score >= 45: return "合理"
        if score >= 32: return "合理偏高"
        return "高估"

    return {
        "综合评分":     round(total, 1),
        "估值判断":     val_label(total),
        "PE 百分位得分":  round(s_pe, 1),
        "PB 百分位得分":  round(s_pb, 1),
        "PEG 得分":       round(s_peg, 1),
        "ROE 趋势得分":   round(s_roe, 1),
        "资金流向得分":   round(s_flow, 1),
        "机构评级得分":   round(s_analyst, 1),
        # 各维度说明（供前端展示）
        "_说明": {
            "PE 百分位":  f"{pe_info.get('percentile', '—')}% 分位（5年历史）",
            "PB 百分位":  f"{pb_info.get('percentile', '—')}% 分位（5年历史）",
            "PEG":        f"{round(peg, 2) if peg else '无法计算'}（林奇标准：<1低估）",
            "ROE 趋势":   roe_info.get("trend", "—"),
            "资金流向":   f"10日净流入 {flow_info.get('total_flow', 0):+.2f} 亿",
            "权重来源":   "同花顺F10·Wind质量因子·MSCI Quality Index",
        },
    }
