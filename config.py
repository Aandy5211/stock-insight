"""全局配置"""
import os

# 绕过系统代理直连 A 股数据源（东方财富、新浪财经等国内接口不需要走代理）
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 缓存目录（使用系统临时目录，兼容云端部署环境）
import tempfile as _tempfile
CACHE_DIR = os.path.join(_tempfile.gettempdir(), "stock_insight_cache")

# 缓存过期时间（秒）
CACHE_TTL = {
    "quote": 5 * 60,        # 行情：5分钟
    "news": 30 * 60,        # 新闻：30分钟
    "financial": 24 * 3600, # 财务数据：1天
    "valuation": 24 * 3600, # 估值数据：1天
}

# AKShare 请求间隔（秒），防止触发频率限制
REQUEST_INTERVAL = 0.1

# 请求失败最大重试次数
MAX_RETRIES = 2

# 图表颜色主题
CHART_COLORS = {
    "primary": "#1f77b4",
    "positive": "#d62728",  # 涨 → 红
    "negative": "#2ca02c",  # 跌 → 绿
    "neutral": "#7f7f7f",
}

# 股票市场前缀映射（用于部分 AKShare 接口）
MARKET_PREFIX = {
    "sh": "上交所",
    "sz": "深交所",
    "bj": "北交所",
}
