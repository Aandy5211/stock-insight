"""财报三表解析、同比/环比计算"""
import pandas as pd
import numpy as np


# ── 字段映射（东方财富接口列名 → 展示名） ─────────────────────────────────────

INCOME_COLS = {
    "REPORT_DATE": "报告期",
    "TOTAL_OPERATE_INCOME": "营业总收入",
    "OPERATE_INCOME": "营业收入",
    "TOTAL_OPERATE_COST": "营业总成本",
    "OPERATE_COST": "营业成本",
    "GROSS_PROFIT": "毛利润",
    "OPERATE_PROFIT": "营业利润",
    "TOTAL_PROFIT": "利润总额",
    "NETPROFIT": "净利润",
    "PARENT_NETPROFIT": "归母净利润",
    "BASIC_EPS": "基本每股收益",
}

BALANCE_COLS = {
    "REPORT_DATE": "报告期",
    "MONETARYFUNDS": "货币资金",
    "ACCOUNTS_RECE": "应收账款",
    "INVENTORY": "存货",
    "TOTAL_ASSETS": "总资产",
    "TOTAL_LIABILITIES": "总负债",
    "TOTAL_EQUITY": "股东权益",
    "PARENT_EQUITY": "归母股东权益",
}

CASHFLOW_COLS = {
    "REPORT_DATE": "报告期",
    "NETCASH_OPERATE": "经营活动现金流净额",
    "NETCASH_INVEST": "投资活动现金流净额",
    "NETCASH_FINANCE": "筹资活动现金流净额",
    "CAPITAL_EXPENDITURE": "资本支出",
    "FREE_CASHFLOW": "自由现金流",
}


def _to_yi(val):
    """将元转换为亿元，非数字返回 None"""
    try:
        v = float(val)
        return round(v / 1e8, 2)
    except Exception:
        return None


def _parse_report_date(df: pd.DataFrame) -> pd.DataFrame:
    """统一报告期格式为 YYYY-MM-DD 字符串，并按时间降序排列"""
    date_col = None
    for c in df.columns:
        if "DATE" in c.upper() or "报告期" in c or "REPORT" in c.upper():
            date_col = c
            break
    if date_col is None:
        return df
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.sort_values(date_col, ascending=False).reset_index(drop=True)
    return df


def _rename_cols(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """按映射重命名列，只保留映射中存在的列"""
    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)
    return df


def _add_yoy(df: pd.DataFrame, date_col: str = "报告期",
             value_cols: list | None = None) -> pd.DataFrame:
    """
    计算同比（Year-over-Year）增长率
    匹配同一季度的上年数据（如 2024-09-30 对比 2023-09-30）
    """
    df = df.copy()
    if value_cols is None:
        value_cols = [c for c in df.columns if c != date_col]

    for col in value_cols:
        yoy_col = f"{col}同比(%)"
        df[yoy_col] = None
        for i, row in df.iterrows():
            try:
                cur_date = pd.Timestamp(row[date_col])
                prev_date_str = f"{cur_date.year - 1}-{cur_date.month:02d}-{cur_date.day:02d}"
                prev_rows = df[df[date_col] == prev_date_str]
                if prev_rows.empty:
                    continue
                cur_val = float(row[col])
                prev_val = float(prev_rows.iloc[0][col])
                if prev_val == 0:
                    continue
                df.at[i, yoy_col] = round((cur_val - prev_val) / abs(prev_val) * 100, 2)
            except Exception:
                continue
    return df


def _add_qoq(df: pd.DataFrame, date_col: str = "报告期",
             value_cols: list | None = None) -> pd.DataFrame:
    """
    计算环比（Quarter-over-Quarter）增长率（仅对相邻行计算）
    """
    df = df.copy()
    if value_cols is None:
        value_cols = [c for c in df.columns if c != date_col]

    for col in value_cols:
        qoq_col = f"{col}环比(%)"
        df[qoq_col] = None
        for i in range(len(df) - 1):
            try:
                cur_val = float(df.at[i, col])
                prev_val = float(df.at[i + 1, col])
                if prev_val == 0:
                    continue
                df.at[i, qoq_col] = round((cur_val - prev_val) / abs(prev_val) * 100, 2)
            except Exception:
                continue
    return df


# ── 公开接口 ──────────────────────────────────────────────────────────────────

def parse_income_statement(raw: pd.DataFrame, periods: int = 8) -> pd.DataFrame:
    """
    解析利润表，返回关键字段 + 同比，金额单位：亿元
    """
    df = _parse_report_date(raw)
    df = _rename_cols(df, INCOME_COLS)
    df = df.head(periods).reset_index(drop=True)

    # 金额单位转换
    money_cols = [c for c in df.columns if c not in ("报告期", "基本每股收益")]
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_yi)

    # 补充毛利率
    if "营业收入" in df.columns and "营业成本" in df.columns:
        def _gross_margin(row):
            try:
                rev = float(row["营业收入"])
                cost = float(row["营业成本"])
                if rev == 0:
                    return None
                return round((rev - cost) / rev * 100, 2)
            except Exception:
                return None
        df["毛利率(%)"] = df.apply(_gross_margin, axis=1)

    value_cols = [c for c in ["营业总收入", "归母净利润", "营业利润"] if c in df.columns]
    df = _add_yoy(df, value_cols=value_cols)
    return df


def parse_balance_sheet(raw: pd.DataFrame, periods: int = 8) -> pd.DataFrame:
    """
    解析资产负债表，返回关键字段，金额单位：亿元
    """
    df = _parse_report_date(raw)
    df = _rename_cols(df, BALANCE_COLS)
    df = df.head(periods).reset_index(drop=True)

    money_cols = [c for c in df.columns if c != "报告期"]
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_yi)

    # 补充资产负债率
    if "总资产" in df.columns and "总负债" in df.columns:
        def _debt_ratio(row):
            try:
                return round(float(row["总负债"]) / float(row["总资产"]) * 100, 2)
            except Exception:
                return None
        df["资产负债率(%)"] = df.apply(_debt_ratio, axis=1)

    value_cols = [c for c in ["总资产", "归母股东权益"] if c in df.columns]
    df = _add_yoy(df, value_cols=value_cols)
    return df


def parse_cash_flow(raw: pd.DataFrame, periods: int = 8) -> pd.DataFrame:
    """
    解析现金流量表，返回关键字段，金额单位：亿元
    """
    df = _parse_report_date(raw)
    df = _rename_cols(df, CASHFLOW_COLS)
    df = df.head(periods).reset_index(drop=True)

    money_cols = [c for c in df.columns if c != "报告期"]
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_yi)

    # 如果没有自由现金流，尝试用经营现金流 - 资本支出计算
    if "自由现金流" not in df.columns or df.get("自由现金流", pd.Series()).isna().all():
        if "经营活动现金流净额" in df.columns and "资本支出" in df.columns:
            def _fcf(row):
                try:
                    return round(float(row["经营活动现金流净额"]) - abs(float(row["资本支出"])), 2)
                except Exception:
                    return None
            df["自由现金流"] = df.apply(_fcf, axis=1)

    value_cols = [c for c in ["经营活动现金流净额"] if c in df.columns]
    df = _add_yoy(df, value_cols=value_cols)
    return df


def highlight_change(val):
    """Pandas Styler 格式化：正数红色，负数绿色"""
    try:
        v = float(val)
        if v > 0:
            return "color: #d62728; font-weight: bold"
        elif v < 0:
            return "color: #2ca02c; font-weight: bold"
    except Exception:
        pass
    return ""


def format_number(val, decimals: int = 2) -> str:
    """格式化数字，None/NaN 显示为 —"""
    try:
        v = float(val)
        if pd.isna(v):
            return "—"
        return f"{v:,.{decimals}f}"
    except Exception:
        return "—"
