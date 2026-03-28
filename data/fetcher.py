"""
数据采集统一接口 - 双源自动切换
优先: yfinance (Yahoo Finance) — 境外 Streamlit Cloud 可用
备用: 新浪财经 / AKShare / baostock — 境内本地可用
"""
import logging
import time
import numpy as np
import pandas as pd
import requests

from data.cache import cached
from data.models import QuoteData, FinancialMetrics
from config import MAX_RETRIES

logger = logging.getLogger(__name__)

# ── Yahoo Finance 可达性检测（启动时一次，结果缓存到进程生命周期）────────────
_yf_available: bool | None = None

def _is_yf_available() -> bool:
    """探测 Yahoo Finance 是否可达（3 秒超时，只检测一次）"""
    global _yf_available
    if _yf_available is not None:
        return _yf_available
    try:
        r = requests.get("https://query1.finance.yahoo.com/", timeout=3)
        _yf_available = r.status_code < 500
    except Exception:
        _yf_available = False
    logger.info(f"Yahoo Finance {'可用，使用 yfinance' if _yf_available else '不可达，使用备用数据源'}")
    return _yf_available

# ── 新浪财经请求头 ─────────────────────────────────────────────────────────────
_SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


# ── 代码标准化 ────────────────────────────────────────────────────────────────

def normalize_code(code: str) -> tuple[str, str, str]:
    """
    标准化股票代码
    返回: (纯6位代码, 新浪前缀 sh/sz, Yahoo Finance 后缀代码 600519.SS)
    """
    code = code.strip().upper()

    # 去掉后缀
    for suffix in (".SH", ".SS", ".SZ", ".BJ"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
            break

    # 去掉前缀
    for prefix in ("SH", "SS", "SZ", "BJ"):
        if code.startswith(prefix) and len(code) > 6:
            code = code[len(prefix):]
            break

    pure = code

    # 推断市场
    if pure.startswith("6"):
        market = "sh"
        yf_suffix = "SS"
    elif pure.startswith(("0", "3")):
        market = "sz"
        yf_suffix = "SZ"
    elif pure.startswith(("4", "8")):
        market = "bj"
        yf_suffix = "SS"
    else:
        market = "sh"
        yf_suffix = "SS"

    yf_code = f"{pure}.{yf_suffix}"
    return pure, market, yf_code


# ════════════════════════════════════════════════════════════════════════════════
# 实时行情
# ════════════════════════════════════════════════════════════════════════════════

def _get_quote_yfinance(code: str) -> QuoteData | None:
    import yfinance as yf
    pure, market, yf_code = normalize_code(code)
    ticker = yf.Ticker(yf_code)
    info = ticker.info
    if not info:
        return None

    def _f(key, default=0.0):
        try:
            v = info.get(key)
            return float(v) if v is not None else default
        except Exception:
            return default

    price = _f("currentPrice") or _f("regularMarketPrice")
    if price == 0:
        return None

    prev_close = _f("regularMarketPreviousClose") or _f("previousClose") or price
    change     = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    name       = info.get("shortName") or info.get("longName") or yf_code

    return QuoteData(
        code=pure,
        name=name,
        price=price,
        change=round(change, 3),
        change_pct=round(change_pct, 2),
        volume=_f("regularMarketVolume") / 100,
        turnover=_f("regularMarketVolume") * price,
        pe_ttm=_f("trailingPE"),
        pb=_f("priceToBook"),
        market_cap=_f("marketCap") / 1e8,
        circ_cap=_f("floatShares") * price / 1e8,
        high_52w=_f("fiftyTwoWeekHigh"),
        low_52w=_f("fiftyTwoWeekLow"),
    )


def _get_quote_sina(code: str) -> QuoteData | None:
    """新浪财经实时行情（境内备用）"""
    pure, market, _ = normalize_code(code)
    sina_code = f"{market}{pure}"
    r = requests.get(
        f"http://hq.sinajs.cn/list={sina_code}",
        headers=_SINA_HEADERS,
        timeout=8,
    )
    r.encoding = "gbk"
    text = r.text
    try:
        body = text[text.index('"') + 1 : text.rindex('"')]
    except ValueError:
        return None
    if not body:
        return None
    parts = body.split(",")
    if len(parts) < 10:
        return None

    def _fp(idx, default=0.0):
        try:
            return float(parts[idx]) if parts[idx] else default
        except Exception:
            return default

    price = _fp(3)
    if price == 0:
        return None
    prev_close = _fp(2) or price
    change     = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0

    return QuoteData(
        code=pure,
        name=parts[0],
        price=price,
        change=round(change, 3),
        change_pct=round(change_pct, 2),
        volume=_fp(8) / 100,    # 股 → 手
        turnover=_fp(9),
        pe_ttm=0.0,
        pb=0.0,
        market_cap=0.0,
        circ_cap=0.0,
        high_52w=0.0,
        low_52w=0.0,
    )


@cached(ttl_key="quote")
def get_quote(code: str) -> QuoteData | None:
    """获取实时行情（yfinance 优先，新浪财经备用）"""
    if _is_yf_available():
        try:
            result = _get_quote_yfinance(code)
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_quote 失败，切换备用源: {e}")
    try:
        return _get_quote_sina(code)
    except Exception as e:
        logger.error(f"Sina get_quote 失败: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
# 财务指标
# ════════════════════════════════════════════════════════════════════════════════

def _get_financial_yfinance(code: str) -> list[FinancialMetrics]:
    import yfinance as yf
    pure, _, yf_code = normalize_code(code)
    ticker = yf.Ticker(yf_code)
    q_fin = ticker.quarterly_financials
    q_bs  = ticker.quarterly_balance_sheet

    if q_fin is None or q_fin.empty:
        return []

    def _row(df, *keys):
        if df is None or df.empty:
            return pd.Series(dtype=float)
        for key in keys:
            if key in df.index:
                return df.loc[key]
        return pd.Series(dtype=float)

    def _val(series, col, default=0.0):
        try:
            v = series.get(col) if hasattr(series, "get") else series[col]
            f = float(v)
            return default if np.isnan(f) else f
        except Exception:
            return default

    rev_s    = _row(q_fin, "Total Revenue")
    gp_s     = _row(q_fin, "Gross Profit")
    ni_s     = _row(q_fin, "Net Income", "Net Income Common Stockholders")
    assets_s = _row(q_bs,  "Total Assets")
    equity_s = _row(q_bs,  "Stockholders Equity", "Common Stock Equity",
                    "Total Equity Gross Minority Interest")
    debt_s   = _row(q_bs,  "Total Debt")

    cols = list(q_fin.columns[:8])
    results = []
    for i, col in enumerate(cols):
        rev    = _val(rev_s,    col)
        gp     = _val(gp_s,     col)
        ni     = _val(ni_s,     col)
        assets = _val(assets_s, col)
        equity = _val(equity_s, col)
        debt   = _val(debt_s,   col)

        gross_margin = gp / rev    * 100 if rev    > 0 else 0.0
        net_margin   = ni / rev    * 100 if rev    > 0 else 0.0
        roe          = ni / equity * 100 if equity > 0 else 0.0
        debt_ratio   = debt / assets * 100 if assets > 0 else 0.0

        rev_yoy = profit_yoy = 0.0
        if i + 4 < len(cols):
            prev = cols[i + 4]
            prev_rev = _val(rev_s, prev)
            prev_ni  = _val(ni_s,  prev)
            if prev_rev > 0:
                rev_yoy = (rev - prev_rev) / abs(prev_rev) * 100
            if prev_ni != 0:
                profit_yoy = (ni - prev_ni) / abs(prev_ni) * 100

        results.append(FinancialMetrics(
            code=pure,
            report_date=str(col)[:10],
            roe=round(roe, 2),
            gross_margin=round(gross_margin, 2),
            net_margin=round(net_margin, 2),
            revenue_yoy=round(rev_yoy, 2),
            profit_yoy=round(profit_yoy, 2),
            debt_ratio=round(debt_ratio, 2),
        ))
    return results


def _get_financial_akshare(code: str) -> list[FinancialMetrics]:
    """AKShare 新浪财经财务指标（境内备用）"""
    import akshare as ak
    pure, _, _ = normalize_code(code)
    df = ak.stock_financial_analysis_indicator(symbol=pure, start_year="2018")
    if df is None or df.empty:
        return []

    df = df.sort_values(by=df.columns[0], ascending=False).head(8).reset_index(drop=True)

    def _pos(row, idx, default=0.0):
        try:
            if idx >= len(row):
                return default
            v = row.iloc[idx]
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return default
            return float(v)
        except Exception:
            return default

    results = []
    for _, row in df.iterrows():
        results.append(FinancialMetrics(
            code=pure,
            report_date=str(row.iloc[0])[:10],
            roe=_pos(row, 11),
            gross_margin=_pos(row, 12),
            net_margin=_pos(row, 17),
            revenue_yoy=_pos(row, 31),
            profit_yoy=_pos(row, 32),
            debt_ratio=_pos(row, 61),
        ))
    return results


@cached(ttl_key="financial")
def get_financial_metrics(code: str) -> list[FinancialMetrics]:
    """获取财务指标（yfinance 优先，AKShare 备用）"""
    if _is_yf_available():
        try:
            result = _get_financial_yfinance(code)
            if result:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_financial_metrics 失败，切换备用源: {e}")
    try:
        return _get_financial_akshare(code)
    except Exception as e:
        logger.error(f"AKShare get_financial_metrics 失败: {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════════
# 历史价格
# ════════════════════════════════════════════════════════════════════════════════

def _get_history_yfinance(code: str, count: int) -> pd.DataFrame | None:
    import yfinance as yf
    pure, _, yf_code = normalize_code(code)
    ticker = yf.Ticker(yf_code)
    df = ticker.history(period="2y")
    if df is None or df.empty:
        return None
    df = df.tail(count).copy().reset_index()
    df = df.rename(columns={
        "Date": "日期", "Open": "开盘", "High": "最高",
        "Low": "最低", "Close": "收盘", "Volume": "成交量",
    })
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"]).dt.tz_localize(None)
    return df


def _get_history_baostock(code: str, count: int) -> pd.DataFrame | None:
    """baostock 历史价格（境内备用）"""
    import baostock as bs
    pure, market, _ = normalize_code(code)
    bs_code = f"{market}.{pure}"
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date="2020-01-01",
            frequency="d",
            adjustflag="2",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"])
    for col in ["开盘", "最高", "最低", "收盘", "成交量", "成交额"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.dropna(subset=["收盘"]).tail(count).reset_index(drop=True)
    return df if not df.empty else None


@cached(ttl_key="financial")
def get_price_history(code: str, count: int = 250) -> pd.DataFrame | None:
    """获取历史价格（yfinance 优先，baostock 备用）"""
    if _is_yf_available():
        try:
            result = _get_history_yfinance(code, count)
            if result is not None and not result.empty:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_price_history 失败，切换备用源: {e}")
    try:
        return _get_history_baostock(code, count)
    except Exception as e:
        logger.error(f"baostock get_price_history 失败: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
# 搜索
# ════════════════════════════════════════════════════════════════════════════════

def _search_yfinance(keyword: str) -> pd.DataFrame | None:
    import yfinance as yf
    results = yf.Search(keyword, max_results=20).quotes
    if not results:
        return None
    rows = []
    for r in results:
        sym = r.get("symbol", "")
        if not (sym.endswith(".SS") or sym.endswith(".SZ")):
            continue
        rows.append({
            "代码": sym.rsplit(".", 1)[0],
            "名称": r.get("shortname") or r.get("longname") or sym,
        })
    return pd.DataFrame(rows) if rows else None


def _search_akshare(keyword: str) -> pd.DataFrame | None:
    """AKShare 股票代码名称搜索（境内备用）"""
    import akshare as ak
    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        return None
    mask = (
        df["code"].str.contains(keyword, na=False) |
        df["name"].str.contains(keyword, na=False)
    )
    result = df[mask].head(20).rename(columns={"code": "代码", "name": "名称"})
    return result if not result.empty else None


@cached(ttl_key="financial")
def search_stock(keyword: str) -> pd.DataFrame | None:
    """搜索股票（yfinance 优先，AKShare 备用）"""
    if _is_yf_available():
        try:
            result = _search_yfinance(keyword)
            if result is not None and not result.empty:
                return result
        except Exception as e:
            logger.warning(f"yfinance search 失败，切换备用源: {e}")
    try:
        return _search_akshare(keyword)
    except Exception as e:
        logger.error(f"AKShare search 失败: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
# 财报三表
# ════════════════════════════════════════════════════════════════════════════════

def _yf_to_df(df_raw: pd.DataFrame, col_map: dict) -> pd.DataFrame | None:
    if df_raw is None or df_raw.empty:
        return None
    available = {k: v for k, v in col_map.items() if k in df_raw.index}
    if not available:
        return None
    sub = df_raw.loc[list(available.keys())].T.copy()
    sub.index.name = "REPORT_DATE"
    sub = sub.reset_index().rename(columns=available)
    sub["REPORT_DATE"] = pd.to_datetime(sub["REPORT_DATE"]).dt.strftime("%Y-%m-%d")
    return sub.sort_values("REPORT_DATE", ascending=False).reset_index(drop=True)


@cached(ttl_key="financial")
def get_income_statement(code: str) -> pd.DataFrame | None:
    pure, market, yf_code = normalize_code(code)
    if _is_yf_available():
        try:
            import yfinance as yf
            result = _yf_to_df(yf.Ticker(yf_code).quarterly_financials, {
                "Total Revenue": "TOTAL_OPERATE_INCOME",
                "Gross Profit":  "GROSS_PROFIT",
                "Operating Income": "OPERATE_PROFIT",
                "Net Income":    "NETPROFIT",
                "Basic EPS":     "BASIC_EPS",
            })
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_income_statement 失败: {e}")
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=f"{market}{pure}", symbol="利润表")
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.error(f"AKShare get_income_statement 失败: {e}")
        return None


@cached(ttl_key="financial")
def get_balance_sheet(code: str) -> pd.DataFrame | None:
    pure, market, yf_code = normalize_code(code)
    if _is_yf_available():
        try:
            import yfinance as yf
            result = _yf_to_df(yf.Ticker(yf_code).quarterly_balance_sheet, {
                "Total Assets":      "TOTAL_ASSETS",
                "Total Liabilities Net Minority Interest": "TOTAL_LIABILITIES",
                "Stockholders Equity": "TOTAL_EQUITY",
            })
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_balance_sheet 失败: {e}")
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=f"{market}{pure}", symbol="资产负债表")
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.error(f"AKShare get_balance_sheet 失败: {e}")
        return None


@cached(ttl_key="financial")
def get_cash_flow(code: str) -> pd.DataFrame | None:
    pure, market, yf_code = normalize_code(code)
    if _is_yf_available():
        try:
            import yfinance as yf
            result = _yf_to_df(yf.Ticker(yf_code).quarterly_cashflow, {
                "Operating Cash Flow": "NETCASH_OPERATE",
                "Investing Cash Flow": "NETCASH_INVEST",
                "Financing Cash Flow": "NETCASH_FINANCE",
                "Free Cash Flow":      "FREE_CASHFLOW",
            })
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_cash_flow 失败: {e}")
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=f"{market}{pure}", symbol="现金流量表")
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.error(f"AKShare get_cash_flow 失败: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
# 新闻
# ════════════════════════════════════════════════════════════════════════════════

def _parse_yf_news(news_list: list, count: int) -> pd.DataFrame | None:
    if not news_list:
        return None
    rows = []
    for item in news_list[:count]:
        content = item.get("content", {})
        if isinstance(content, dict):
            title    = content.get("title", "")
            pub_time = content.get("pubDate", "")
            provider = content.get("provider", {})
            source   = provider.get("displayName", "") if isinstance(provider, dict) else ""
            canon    = content.get("canonicalUrl", {})
            url      = canon.get("url", "") if isinstance(canon, dict) else ""
            summary  = content.get("summary", "")
        else:
            title    = item.get("title", "")
            pub_time = str(item.get("providerPublishTime", ""))
            source   = item.get("publisher", "")
            url      = item.get("link", "")
            summary  = ""
        if not title:
            continue
        rows.append({
            "新闻标题": title, "内容": summary,
            "发布时间": pub_time, "文章来源": source, "新闻链接": url,
        })
    return pd.DataFrame(rows) if rows else None


@cached(ttl_key="news")
def get_stock_news(code: str, count: int = 30) -> pd.DataFrame | None:
    """获取个股新闻（yfinance 优先，AKShare 备用）"""
    pure, _, yf_code = normalize_code(code)
    if _is_yf_available():
        try:
            import yfinance as yf
            result = _parse_yf_news(yf.Ticker(yf_code).news, count)
            if result is not None and not result.empty:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_stock_news 失败，切换备用源: {e}")
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=pure)
        if df is None or df.empty:
            return None
        df = df.head(count)
        cols = [c for c in ["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"] if c in df.columns]
        df = df[cols].rename(columns={"新闻内容": "内容"})
        return df if not df.empty else None
    except Exception as e:
        logger.error(f"AKShare get_stock_news 失败: {e}")
        return None


@cached(ttl_key="news")
def get_market_news(count: int = 30) -> pd.DataFrame | None:
    if _is_yf_available():
        try:
            import yfinance as yf
            result = _parse_yf_news(yf.Ticker("000300.SS").news, count)
            if result is not None and not result.empty:
                return result
        except Exception as e:
            logger.warning(f"yfinance get_market_news 失败，切换备用源: {e}")
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol="000300")
        if df is None or df.empty:
            return None
        df = df.head(count)
        cols = [c for c in ["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"] if c in df.columns]
        df = df[cols].rename(columns={"新闻内容": "内容"})
        return df if not df.empty else None
    except Exception as e:
        logger.error(f"AKShare get_market_news 失败: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
# 估值数据
# ════════════════════════════════════════════════════════════════════════════════

@cached(ttl_key="valuation")
def get_pe_pb_history(code: str, indicator: str = "PE") -> pd.DataFrame | None:
    pure, _, yf_code = normalize_code(code)
    try:
        import yfinance as yf
        ticker = yf.Ticker(yf_code)
        info   = ticker.info
        base   = float(info.get("trailingEps") or 0) if indicator == "PE" \
                 else float(info.get("bookValue") or 0)
        if base <= 0:
            return None
        hist = ticker.history(period="5y")[["Close"]].copy()
        if hist.empty:
            return None
        hist = hist.reset_index()
        hist["date"]  = pd.to_datetime(hist["Date"]).dt.tz_localize(None)
        hist["value"] = (hist["Close"] / base).round(2)
        max_val = 500.0 if indicator == "PE" else 50.0
        hist = hist[(hist["value"] > 0) & (hist["value"] < max_val)]
        return hist[["date", "value"]].reset_index(drop=True)
    except Exception as e:
        logger.warning(f"get_pe_pb_history 失败: {e}")
        return None


@cached(ttl_key="valuation")
def get_analyst_forecast(code: str) -> pd.DataFrame | None:
    pure, _, yf_code = normalize_code(code)
    try:
        import yfinance as yf
        rec = yf.Ticker(yf_code).recommendations
        if rec is None or rec.empty:
            return None
        recent = rec.tail(3)
        rows = []
        for _, row in recent.iterrows():
            for label, col in [("买入", "strongBuy"), ("买入", "buy"),
                                ("中性", "hold"),
                                ("卖出", "sell"), ("卖出", "strongSell")]:
                n = int(row.get(col, 0) or 0)
                rows.extend([{"评级": label}] * n)
        return pd.DataFrame(rows) if rows else None
    except Exception as e:
        logger.warning(f"get_analyst_forecast 失败: {e}")
        return None


@cached(ttl_key="valuation")
def get_fund_flow(code: str) -> pd.DataFrame | None:
    pure, market, _ = normalize_code(code)
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(
            stock=pure,
            market="sh" if market == "sh" else "sz",
        )
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.warning(f"get_fund_flow 失败: {e}")
        return None


@cached(ttl_key="valuation")
def get_industry_pe(code: str) -> pd.DataFrame | None:
    return None
