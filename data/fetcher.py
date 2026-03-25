"""AKShare 数据采集统一接口"""
import time
import logging
import requests
import pandas as pd

# ── 全局禁用系统代理 ──────────────────────────────────────────────────────────
# Windows 系统代理（Clash/V2Ray 等）会拦截东方财富等国内接口，导致连接失败。
# 通过 patch requests.Session 的 trust_env，让所有 HTTP 请求绕过系统代理直连。
_orig_session_init = requests.Session.__init__
def _no_proxy_session_init(self, *args, **kwargs):
    _orig_session_init(self, *args, **kwargs)
    self.trust_env = False
requests.Session.__init__ = _no_proxy_session_init
# ──────────────────────────────────────────────────────────────────────────────

import akshare as ak
from data.cache import cached
from data.models import QuoteData, FinancialMetrics, StockInfo
from config import REQUEST_INTERVAL, MAX_RETRIES

logger = logging.getLogger(__name__)


def _safe_call(func, *args, retries=MAX_RETRIES, **kwargs):
    """带重试的安全调用，仅在重试时限速"""
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, pd.DataFrame) and result.empty:
                logger.warning(f"{func.__name__} 返回空数据")
                return None
            return result
        except Exception as e:
            logger.warning(f"{func.__name__} 第{attempt+1}次失败: {e}")
            if attempt == retries - 1:
                logger.error(f"{func.__name__} 最终失败: {e}")
                return None
            time.sleep(REQUEST_INTERVAL)
    return None


def normalize_code(code: str) -> tuple[str, str]:
    """
    标准化股票代码，返回 (纯代码, 市场前缀)
    支持输入格式: "000001", "sh000001", "sz000001", "000001.SZ"
    """
    code = code.strip().upper()
    if code.endswith(".SH") or code.endswith(".SZ") or code.endswith(".BJ"):
        market = code[-2:].lower()
        pure = code[:-3]
        return pure, market
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            return code[2:], prefix.lower()
    # 根据代码规则推断市场
    pure = code
    if pure.startswith("6"):
        return pure, "sh"
    elif pure.startswith(("0", "3")):
        return pure, "sz"
    elif pure.startswith(("4", "8")):
        return pure, "bj"
    return pure, "sh"


@cached(ttl_key="quote")
def get_quote(code: str) -> QuoteData | None:
    """获取实时行情（雪球接口，不依赖 push2.eastmoney.com）"""
    pure, market = normalize_code(code)
    xq_symbol = f"{market.upper()}{pure}"
    df = _safe_call(ak.stock_individual_spot_xq, symbol=xq_symbol)
    if df is None:
        return None

    try:
        info = dict(zip(df["item"], df["value"]))
    except Exception:
        return None

    def _f(key, default=0.0):
        try:
            return float(info.get(key, default))
        except Exception:
            return default

    return QuoteData(
        code=pure,
        name=str(info.get("名称", "")),
        price=_f("现价"),
        change=_f("涨跌"),
        change_pct=_f("涨幅"),
        volume=_f("成交量") / 100,   # 雪球返回股数，除以100转换为手
        turnover=_f("成交额"),
        pe_ttm=_f("市盈率(TTM)"),
        pb=_f("市净率"),
        market_cap=_f("资产净值/总市值") / 1e8,
        circ_cap=_f("流通值") / 1e8,
    )


@cached(ttl_key="financial")
def get_financial_metrics(code: str) -> list[FinancialMetrics]:
    """获取最近8期关键财务指标"""
    pure, _ = normalize_code(code)

    df = _safe_call(ak.stock_financial_abstract_ths, symbol=pure, indicator="按报告期")
    if df is None:
        return []

    # 取最新8期（数据按日期升序，tail 取尾部）
    recent = df.tail(8).iloc[::-1].reset_index(drop=True)

    # 列名别名映射（兼容不同版本 THS 返回字段）
    cols = set(recent.columns)
    _COL = {
        "roe":         next((c for c in ["净资产收益率", "ROE", "Roe", "资产净回报率"] if c in cols), None),
        "gross":       next((c for c in ["毛利率", "销售毛利率", "营业利润率"] if c in cols), None),
        "net":         next((c for c in ["净利率", "销售净利率", "净利润率"] if c in cols), None),
        "rev_yoy":     next((c for c in ["营业总收入同比增长率", "营业收入同比增长率"] if c in cols), None),
        "profit_yoy":  next((c for c in ["归母净利润同比增长率", "扣非净利润同比增长率", "净利润同比增长率"] if c in cols), None),
        "debt":        next((c for c in ["资产负债率"] if c in cols), None),
        "equity_mul":  next((c for c in ["权益乘数"] if c in cols), None),
    }

    def _parse(val, default=0.0) -> float:
        """解析可能带%、元、逗号或 False 的数值"""
        if val is None or val is False or val is True:
            return default
        s = str(val).strip()
        if s in ("False", "True", "None", "—", "-", ""):
            return default
        s = s.rstrip("%").replace(",", "").replace("元", "").strip()
        try:
            return float(s)
        except Exception:
            return default

    def _f(row, key, default=0.0) -> float:
        col = _COL.get(key)
        return _parse(row.get(col), default) if col else default

    results = []
    for _, row in recent.iterrows():
        roe = _f(row, "roe")

        results.append(FinancialMetrics(
            code=pure,
            report_date=str(row.get("报告期", "")),
            roe=roe,
            gross_margin=_f(row, "gross"),
            net_margin=_f(row, "net"),
            revenue_yoy=_f(row, "rev_yoy"),
            profit_yoy=_f(row, "profit_yoy"),
            debt_ratio=_f(row, "debt"),
        ))
    return results


@cached(ttl_key="financial")
def get_price_history(code: str, period: str = "daily", count: int = 250) -> pd.DataFrame | None:
    """获取历史价格（近 count 个交易日，新浪财经接口）"""
    pure, market = normalize_code(code)
    sina_symbol = f"{market}{pure}"
    df = _safe_call(ak.stock_zh_a_daily, symbol=sina_symbol, adjust="qfq")
    if df is None:
        return None
    df = df.tail(count).copy()
    # 统一为 K 线图所需的中文列名
    df = df.rename(columns={
        "date":   "日期",
        "open":   "开盘",
        "high":   "最高",
        "low":    "最低",
        "close":  "收盘",
        "volume": "成交量",
        "amount": "成交额",
    })
    return df


@cached(ttl_key="financial")
def search_stock(keyword: str) -> pd.DataFrame | None:
    """按关键词搜索股票（使用股票代码/名称列表）"""
    df = _safe_call(ak.stock_info_a_code_name)
    if df is None:
        return None
    mask = (
        df["code"].str.contains(keyword, na=False) |
        df["name"].str.contains(keyword, na=False)
    )
    result = df[mask].rename(columns={"code": "代码", "name": "名称"}).head(20)
    return result if not result.empty else None


@cached(ttl_key="financial")
def get_stock_list() -> pd.DataFrame | None:
    """获取 A 股全量代码和名称"""
    return _safe_call(ak.stock_info_a_code_name)


# ── 财报三表 ──────────────────────────────────────────────────────────────────

@cached(ttl_key="financial")
def get_income_statement(code: str) -> pd.DataFrame | None:
    """
    利润表（按报告期，东方财富 emweb 接口）
    需传入 SH/SZ 前缀格式，如 SZ000001
    """
    pure, market = normalize_code(code)
    em_symbol = f"{market.upper()}{pure}"
    df = _safe_call(ak.stock_profit_sheet_by_report_em, symbol=em_symbol)
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


@cached(ttl_key="financial")
def get_balance_sheet(code: str) -> pd.DataFrame | None:
    """
    资产负债表（按报告期，东方财富 emweb 接口）
    需传入 SH/SZ 前缀格式，如 SZ000001
    """
    pure, market = normalize_code(code)
    em_symbol = f"{market.upper()}{pure}"
    df = _safe_call(ak.stock_balance_sheet_by_report_em, symbol=em_symbol)
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


@cached(ttl_key="financial")
def get_cash_flow(code: str) -> pd.DataFrame | None:
    """
    现金流量表（按报告期，东方财富）
    主要字段：报告期、经营活动现金流、投资活动现金流、筹资活动现金流、自由现金流
    """
    pure, market = normalize_code(code)
    em_symbol = f"{market.upper()}{pure}"
    df = _safe_call(ak.stock_cash_flow_sheet_by_report_em, symbol=em_symbol)
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


# ── 新闻 ──────────────────────────────────────────────────────────────────────

@cached(ttl_key="news")
def get_stock_news(code: str, count: int = 50) -> pd.DataFrame | None:
    """
    获取个股新闻（东方财富）
    返回列：关键词、新闻标题、内容、发布时间、文章来源、新闻链接
    """
    pure, _ = normalize_code(code)
    df = _safe_call(ak.stock_news_em, symbol=pure)
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df.head(count)


@cached(ttl_key="news")
def get_market_news(count: int = 30) -> pd.DataFrame | None:
    """
    获取财经要闻（财新 stock_news_main_cx）
    返回列：新闻标题、关键词、新闻链接
    """
    df = _safe_call(ak.stock_news_main_cx)
    if df is None:
        return None
    df = df.copy()
    # 统一为页面期望的列名
    rename = {}
    if "summary" in df.columns:
        rename["summary"] = "新闻标题"
    if "tag" in df.columns:
        rename["tag"] = "关键词"
    if "url" in df.columns:
        rename["url"] = "新闻链接"
    df = df.rename(columns=rename)
    return df.head(count)


# ── 估值 ──────────────────────────────────────────────────────────────────────

@cached(ttl_key="valuation")
def get_pe_pb_history(code: str, indicator: str = "PE") -> pd.DataFrame | None:
    """
    个股历史 PE/PB，由价格历史 + 财务数据（EPS/BPS）计算
    indicator: "PE"（市盈率）/ "PB"（市净率）
    返回列：date, value
    """
    pure, market = normalize_code(code)

    # 价格历史
    sina_symbol = f"{market}{pure}"
    price_df = _safe_call(ak.stock_zh_a_daily, symbol=sina_symbol, adjust="qfq")
    if price_df is None or price_df.empty:
        return None

    # 财务数据
    fin_df = _safe_call(ak.stock_financial_abstract_ths, symbol=pure, indicator="按报告期")
    if fin_df is None or fin_df.empty:
        return None

    val_col = "基本每股收益" if indicator == "PE" else "每股净资产"
    if val_col not in fin_df.columns:
        return None

    fin_df = fin_df.copy()
    fin_df["报告期"] = pd.to_datetime(fin_df["报告期"], errors="coerce")
    fin_df[val_col] = pd.to_numeric(fin_df[val_col], errors="coerce")
    fin_df = fin_df.dropna(subset=["报告期", val_col])
    fin_df = fin_df[fin_df[val_col] > 0].sort_values("报告期").reset_index(drop=True)

    if fin_df.empty:
        return None

    # 价格整理
    price_df = price_df.copy()
    price_df["date"] = pd.to_datetime(price_df["date"], errors="coerce")
    price_df = price_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    fin_dates = fin_df["报告期"].values
    fin_vals = fin_df[val_col].values

    results = []
    for _, row in price_df.iterrows():
        d = row["date"]
        close = row.get("close")
        if close is None or pd.isna(close) or close <= 0:
            continue
        mask = fin_dates <= d
        if not mask.any():
            continue
        latest_val = float(fin_vals[mask][-1])
        if latest_val <= 0:
            continue
        ratio = round(float(close) / latest_val, 2)
        max_ratio = 500.0 if indicator == "PE" else 50.0
        if 0 < ratio < max_ratio:
            results.append({"date": d, "value": ratio})

    if not results:
        return None
    return pd.DataFrame(results)


@cached(ttl_key="valuation")
def get_analyst_forecast(code: str) -> pd.DataFrame | None:
    """
    分析师盈利预测（同花顺）
    返回列：预测年度、最小值、均值、最大值、行业平均值 等
    """
    pure, _ = normalize_code(code)
    df = _safe_call(ak.stock_profit_forecast_ths, symbol=pure, indicator="预测年报每股收益")
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


@cached(ttl_key="valuation")
def get_fund_flow(code: str) -> pd.DataFrame | None:
    """
    个股资金流向（东方财富，近 100 日）
    返回列：日期、主力净流入、超大单净流入、大单净流入、中单净流入、小单净流入
    """
    pure, market = normalize_code(code)
    df = _safe_call(
        ak.stock_individual_fund_flow,
        stock=pure,
        market=market,
    )
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df


@cached(ttl_key="valuation")
def get_industry_pe(code: str) -> pd.DataFrame | None:
    """
    同行业 PE 比较：获取该股所属行业的行业 PE 历史
    先查该股行业，再取行业 PE
    """
    pure, _ = normalize_code(code)
    # 先获取所属行业
    info_df = _safe_call(ak.stock_individual_info_em, symbol=pure)
    if info_df is None:
        return None
    try:
        info = dict(zip(info_df.iloc[:, 0], info_df.iloc[:, 1]))
        industry = str(info.get("行业", ""))
    except Exception:
        return None
    if not industry:
        return None

    # 取申万行业 PE
    df = _safe_call(
        ak.stock_board_industry_hist_em,
        symbol=industry,
        period="daily",
        adjust="",
    )
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    return df
