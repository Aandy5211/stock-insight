"""数据模型定义"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class StockInfo:
    """股票基础信息"""
    code: str           # 股票代码，如 "000001"
    name: str           # 股票名称
    market: str         # 市场：sh / sz / bj
    industry: str = ""  # 所属行业
    concept: str = ""   # 概念板块


@dataclass
class QuoteData:
    """实时行情"""
    code: str
    name: str
    price: float            # 最新价
    change: float           # 涨跌额
    change_pct: float       # 涨跌幅 %
    volume: float           # 成交量（手）
    turnover: float         # 成交额（元）
    pe_ttm: float           # 市盈率 TTM
    pb: float               # 市净率
    market_cap: float       # 总市值（亿元）
    circ_cap: float         # 流通市值（亿元）
    high_52w: float = 0.0   # 52周最高
    low_52w: float = 0.0    # 52周最低


@dataclass
class FinancialMetrics:
    """关键财务指标"""
    code: str
    report_date: str        # 报告期，如 "2024-09-30"
    # 盈利能力
    roe: float = 0.0        # 净资产收益率 %
    gross_margin: float = 0.0  # 毛利率 %
    net_margin: float = 0.0    # 净利率 %
    # 成长性
    revenue_yoy: float = 0.0   # 营收同比增长 %
    profit_yoy: float = 0.0    # 净利润同比增长 %
    # 偿债能力
    debt_ratio: float = 0.0    # 资产负债率 %
    current_ratio: float = 0.0 # 流动比率
    # 运营效率
    asset_turnover: float = 0.0  # 总资产周转率
    # 现金流
    ocf: float = 0.0           # 经营活动现金流（亿元）


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    content: str
    source: str
    publish_time: str
    url: str = ""
    sentiment_score: float = 0.5   # 情感分数 0~1
    sentiment_label: str = "neutral"
    keywords: list = field(default_factory=list)
