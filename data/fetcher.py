"""Yahoo Finance 数据采集统一接口（yfinance）"""
import logging
import numpy as np
import pandas as pd
import yfinance as yf

from data.cache import cached
from data.models import QuoteData, FinancialMetrics
from config import MAX_RETRIES

logger = logging.getLogger(__name__)


def normalize_code(code: str) -> tuple[str, str]:
    """
    标准化股票代码，返回 (Yahoo Finance 格式, 纯代码)
    支持: "000001" / "sh000001" / "600519.SH" / "SZ000001"
    Yahoo Finance 上交所用 .SS，深交所用 .SZ
    """
    code = code.strip().upper()

    # 已是 Yahoo Finance 格式
    if code.endswith(".SS") or code.endswith(".SZ"):
        pure = code.rsplit(".", 1)[0]
        return code, pure

    # .SH → .SS
    if code.endswith(".SH"):
        pure = code[:-3]
        return f"{pure}.SS", pure

    # .BJ 北交所（暂时映射到 .SS）
    if code.endswith(".BJ"):
        pure = code[:-3]
        return f"{pure}.SS", pure

    # 去掉 sh/sz/bj 前缀
    for prefix, suffix in [("SH", "SS"), ("SS", "SS"), ("SZ", "SZ"), ("BJ", "SS")]:
        if code.startswith(prefix):
            pure = code[len(prefix):]
            return f"{pure}.{suffix}", pure

    # 根据代码规则推断市场
    pure = code
    if pure.startswith("6"):
        return f"{pure}.SS", pure   # 上交所
    elif pure.startswith(("0", "3")):
        return f"{pure}.SZ", pure   # 深交所
    elif pure.startswith(("4", "8")):
        return f"{pure}.SS", pure   # 北交所（近似）
    return f"{pure}.SS", pure


# ── 行情 ──────────────────────────────────────────────────────────────────────

@cached(ttl_key="quote")
def get_quote(code: str) -> QuoteData | None:
    """获取实时行情（Yahoo Finance）"""
    yf_code, pure = normalize_code(code)
    try:
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
            volume=_f("regularMarketVolume") / 100,          # 股 → 手
            turnover=_f("regularMarketVolume") * price,       # 估算成交额
            pe_ttm=_f("trailingPE"),
            pb=_f("priceToBook"),
            market_cap=_f("marketCap") / 1e8,                # 元 → 亿
            circ_cap=_f("floatShares") * price / 1e8,
            high_52w=_f("fiftyTwoWeekHigh"),
            low_52w=_f("fiftyTwoWeekLow"),
        )
    except Exception as e:
        logger.error(f"get_quote 失败 {yf_code}: {e}")
        return None


# ── 财务指标 ───────────────────────────────────────────────────────────────────

@cached(ttl_key="financial")
def get_financial_metrics(code: str) -> list[FinancialMetrics]:
    """获取最近 8 期季报关键财务指标"""
    yf_code, pure = normalize_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        q_fin = ticker.quarterly_financials      # rows=指标, cols=日期
        q_bs  = ticker.quarterly_balance_sheet
    except Exception as e:
        logger.error(f"get_financial_metrics 失败: {e}")
        return []

    if q_fin is None or q_fin.empty:
        return []

    def _row(df, *keys):
        """从 DataFrame 中找第一个匹配的行，转为 Series"""
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

        # 同比：对比 4 期前（同季度上年）
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


# ── 价格历史 ───────────────────────────────────────────────────────────────────

@cached(ttl_key="financial")
def get_price_history(code: str, count: int = 250) -> pd.DataFrame | None:
    """获取历史价格（近 count 个交易日）"""
    yf_code, _ = normalize_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period="2y")
        if df is None or df.empty:
            return None
        df = df.tail(count).copy().reset_index()
        df = df.rename(columns={
            "Date":   "日期",
            "Open":   "开盘",
            "High":   "最高",
            "Low":    "最低",
            "Close":  "收盘",
            "Volume": "成交量",
        })
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"]).dt.tz_localize(None)
        return df
    except Exception as e:
        logger.error(f"get_price_history 失败: {e}")
        return None


# ── 搜索 ──────────────────────────────────────────────────────────────────────

@cached(ttl_key="financial")
def search_stock(keyword: str) -> pd.DataFrame | None:
    """按关键词搜索股票（Yahoo Finance Search）"""
    try:
        results = yf.Search(keyword, max_results=20).quotes
        if not results:
            return None
        rows = []
        for r in results:
            sym = r.get("symbol", "")
            if not (sym.endswith(".SS") or sym.endswith(".SZ")):
                continue
            pure_code = sym.rsplit(".", 1)[0]
            rows.append({
                "代码": pure_code,
                "名称": r.get("shortname") or r.get("longname") or sym,
            })
        return pd.DataFrame(rows) if rows else None
    except Exception as e:
        logger.error(f"search_stock 失败: {e}")
        return None


# ── 财报三表（通用转换）───────────────────────────────────────────────────────

def _yf_to_df(df_raw: pd.DataFrame, col_map: dict) -> pd.DataFrame | None:
    """
    将 yfinance 财报 DataFrame（行=英文指标, 列=日期）转换为
    （行=日期, 列=AKShare 兼容列名），供 analysis/statements.py 解析
    """
    if df_raw is None or df_raw.empty:
        return None
    available = {k: v for k, v in col_map.items() if k in df_raw.index}
    if not available:
        return None
    sub = df_raw.loc[list(available.keys())].T.copy()
    sub.index.name = "REPORT_DATE"
    sub = sub.reset_index()
    sub = sub.rename(columns=available)
    sub["REPORT_DATE"] = pd.to_datetime(sub["REPORT_DATE"]).dt.strftime("%Y-%m-%d")
    sub = sub.sort_values("REPORT_DATE", ascending=False).reset_index(drop=True)
    return sub


@cached(ttl_key="financial")
def get_income_statement(code: str) -> pd.DataFrame | None:
    yf_code, _ = normalize_code(code)
    try:
        df = yf.Ticker(yf_code).quarterly_financials
        return _yf_to_df(df, {
            "Total Revenue":                  "TOTAL_OPERATE_INCOME",
            "Cost Of Revenue":                "OPERATE_COST",
            "Total Operating Expenses":       "TOTAL_OPERATE_COST",
            "Gross Profit":                   "GROSS_PROFIT",
            "Operating Income":               "OPERATE_PROFIT",
            "Net Income":                     "NETPROFIT",
            "Net Income Common Stockholders": "PARENT_NETPROFIT",
            "Basic EPS":                      "BASIC_EPS",
        })
    except Exception as e:
        logger.error(f"get_income_statement 失败: {e}")
        return None


@cached(ttl_key="financial")
def get_balance_sheet(code: str) -> pd.DataFrame | None:
    yf_code, _ = normalize_code(code)
    try:
        df = yf.Ticker(yf_code).quarterly_balance_sheet
        return _yf_to_df(df, {
            "Cash And Cash Equivalents":              "MONETARYFUNDS",
            "Accounts Receivable":                    "ACCOUNTS_RECE",
            "Inventory":                              "INVENTORY",
            "Total Assets":                           "TOTAL_ASSETS",
            "Total Liabilities Net Minority Interest": "TOTAL_LIABILITIES",
            "Stockholders Equity":                    "TOTAL_EQUITY",
            "Common Stock Equity":                    "PARENT_EQUITY",
        })
    except Exception as e:
        logger.error(f"get_balance_sheet 失败: {e}")
        return None


@cached(ttl_key="financial")
def get_cash_flow(code: str) -> pd.DataFrame | None:
    yf_code, _ = normalize_code(code)
    try:
        df = yf.Ticker(yf_code).quarterly_cashflow
        return _yf_to_df(df, {
            "Operating Cash Flow":  "NETCASH_OPERATE",
            "Investing Cash Flow":  "NETCASH_INVEST",
            "Financing Cash Flow":  "NETCASH_FINANCE",
            "Capital Expenditure":  "CAPITAL_EXPENDITURE",
            "Free Cash Flow":       "FREE_CASHFLOW",
        })
    except Exception as e:
        logger.error(f"get_cash_flow 失败: {e}")
        return None


# ── 新闻 ──────────────────────────────────────────────────────────────────────

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
            "新闻标题": title,
            "内容":    summary,
            "发布时间": pub_time,
            "文章来源": source,
            "新闻链接": url,
        })
    return pd.DataFrame(rows) if rows else None


@cached(ttl_key="news")
def get_stock_news(code: str, count: int = 30) -> pd.DataFrame | None:
    yf_code, _ = normalize_code(code)
    try:
        return _parse_yf_news(yf.Ticker(yf_code).news, count)
    except Exception as e:
        logger.error(f"get_stock_news 失败: {e}")
        return None


@cached(ttl_key="news")
def get_market_news(count: int = 30) -> pd.DataFrame | None:
    try:
        # 用沪深 300 作为大盘新闻代理
        return _parse_yf_news(yf.Ticker("000300.SS").news, count)
    except Exception as e:
        logger.error(f"get_market_news 失败: {e}")
        return None


# ── 估值数据 ───────────────────────────────────────────────────────────────────

@cached(ttl_key="valuation")
def get_pe_pb_history(code: str, indicator: str = "PE") -> pd.DataFrame | None:
    """
    历史 PE/PB（用历史收盘价 ÷ 最新 EPS/BPS 近似计算）
    """
    yf_code, _ = normalize_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        info   = ticker.info

        if indicator == "PE":
            base = float(info.get("trailingEps") or 0)
        else:
            base = float(info.get("bookValue") or 0)

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
        logger.error(f"get_pe_pb_history 失败: {e}")
        return None


@cached(ttl_key="valuation")
def get_analyst_forecast(code: str) -> pd.DataFrame | None:
    """
    分析师评级（yfinance recommendations → 转换为兼容格式）
    """
    yf_code, _ = normalize_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        rec = ticker.recommendations
        if rec is None or rec.empty:
            return None
        # 汇总最近 3 期评级，展开为逐行 "评级" 格式
        recent = rec.tail(3)
        rows = []
        for _, row in recent.iterrows():
            for label, col in [("买入", "strongBuy"), ("买入", "buy"),
                                ("中性", "hold"),
                                ("卖出", "sell"),  ("卖出", "strongSell")]:
                n = int(row.get(col, 0) or 0)
                rows.extend([{"评级": label}] * n)
        return pd.DataFrame(rows) if rows else None
    except Exception as e:
        logger.error(f"get_analyst_forecast 失败: {e}")
        return None


@cached(ttl_key="valuation")
def get_fund_flow(code: str) -> pd.DataFrame | None:
    """资金流向（yfinance 不支持，返回 None）"""
    return None


@cached(ttl_key="valuation")
def get_industry_pe(code: str) -> pd.DataFrame | None:
    """行业 PE（yfinance 不支持，返回 None）"""
    return None
