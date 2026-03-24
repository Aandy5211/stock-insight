"""新闻 NLP 分析：情感分析 + 关键词提取"""
import re
import logging
import pandas as pd
from snownlp import SnowNLP
import jieba
import jieba.analyse

logger = logging.getLogger(__name__)

# 情感分数阈值
_POS_THRESHOLD = 0.62
_NEG_THRESHOLD = 0.38

# 停用词（金融文本常见无意义词）
_STOPWORDS = {
    "的", "了", "在", "是", "和", "与", "及", "或", "等", "对", "为",
    "将", "该", "这", "其", "有", "无", "被", "由", "于", "以", "但",
    "而", "也", "则", "且", "从", "向", "至", "到", "后", "前", "中",
    "上", "下", "内", "外", "元", "亿", "万", "个", "家", "年", "月",
    "日", "时", "分", "期", "次", "份", "项", "条", "块", "只", "名",
    "公司", "股份", "有限", "集团", "投资", "发展", "进行", "表示",
    "相关", "方面", "情况", "问题", "通过", "实现", "同时", "目前",
    "已经", "可以", "一个", "一是", "二是", "三是", "此外", "同期",
}


def _clean_text(text: str) -> str:
    """清理文本：去除 HTML 标签、多余空白"""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def analyze_sentiment(text: str) -> dict:
    """
    情感分析，返回：
    {
        "score": float,         # 0~1，越高越积极
        "label": str,           # "positive" / "negative" / "neutral"
        "label_cn": str,        # "利好" / "利空" / "中性"
        "confidence": float,    # 距离中性的距离，0~0.5
    }
    """
    text = _clean_text(text)
    if not text:
        return {"score": 0.5, "label": "neutral", "label_cn": "中性", "confidence": 0.0}

    try:
        score = SnowNLP(text).sentiments
    except Exception as e:
        logger.warning(f"情感分析失败: {e}")
        return {"score": 0.5, "label": "neutral", "label_cn": "中性", "confidence": 0.0}

    if score >= _POS_THRESHOLD:
        label, label_cn = "positive", "利好"
    elif score <= _NEG_THRESHOLD:
        label, label_cn = "negative", "利空"
    else:
        label, label_cn = "neutral", "中性"

    confidence = round(abs(score - 0.5), 3)
    return {
        "score": round(score, 4),
        "label": label,
        "label_cn": label_cn,
        "confidence": confidence,
    }


def extract_keywords(text: str, topk: int = 10) -> list[tuple[str, float]]:
    """
    关键词提取（TF-IDF），返回 [(词, 权重), ...]
    过滤停用词和单字词
    """
    text = _clean_text(text)
    if not text:
        return []
    try:
        words = jieba.analyse.extract_tags(text, topK=topk * 2, withWeight=True)
        result = [
            (w, round(s, 4))
            for w, s in words
            if w not in _STOPWORDS and len(w) >= 2
        ]
        return result[:topk]
    except Exception as e:
        logger.warning(f"关键词提取失败: {e}")
        return []


def analyze_news_batch(df: pd.DataFrame,
                       title_col: str = "新闻标题",
                       content_col: str | None = "内容") -> pd.DataFrame:
    """
    批量分析新闻 DataFrame，追加情感和关键词列。
    优先分析 content_col，若为空则退回到 title_col。
    """
    df = df.copy()

    scores, labels, labels_cn, confidences, keywords_list = [], [], [], [], []

    for _, row in df.iterrows():
        # 拼接标题 + 内容作为分析文本
        parts = []
        title = str(row.get(title_col, "") or "")
        if title:
            parts.append(title)
        if content_col and content_col in df.columns:
            content = str(row.get(content_col, "") or "")
            if content and content != "nan":
                parts.append(content)
        text = " ".join(parts)

        sent = analyze_sentiment(text)
        kws = extract_keywords(text, topk=8)

        scores.append(sent["score"])
        labels.append(sent["label"])
        labels_cn.append(sent["label_cn"])
        confidences.append(sent["confidence"])
        keywords_list.append("、".join(w for w, _ in kws))

    df["情感分数"] = scores
    df["情感标签"] = labels_cn
    df["置信度"] = confidences
    df["关键词"] = keywords_list
    return df


def aggregate_keywords(df: pd.DataFrame,
                       title_col: str = "新闻标题",
                       content_col: str | None = "内容",
                       topk: int = 30) -> list[tuple[str, float]]:
    """
    汇总所有新闻的关键词，返回频次 Top-K 列表 [(词, 频次), ...]
    """
    word_freq: dict[str, float] = {}
    for _, row in df.iterrows():
        parts = [str(row.get(title_col, "") or "")]
        if content_col and content_col in df.columns:
            c = str(row.get(content_col, "") or "")
            if c and c != "nan":
                parts.append(c)
        kws = extract_keywords(" ".join(parts), topk=15)
        for w, score in kws:
            word_freq[w] = word_freq.get(w, 0) + score

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return sorted_words[:topk]


def sentiment_summary(df: pd.DataFrame) -> dict:
    """
    返回情感汇总统计：
    {
        "total": int,
        "positive": int, "negative": int, "neutral": int,
        "positive_pct": float, "negative_pct": float, "neutral_pct": float,
        "avg_score": float,
        "overall": str,   # "偏多" / "偏空" / "中性"
    }
    """
    if "情感标签" not in df.columns:
        return {}

    total = len(df)
    pos = int((df["情感标签"] == "利好").sum())
    neg = int((df["情感标签"] == "利空").sum())
    neu = total - pos - neg
    avg = float(df["情感分数"].mean()) if "情感分数" in df.columns else 0.5

    if pos > neg * 1.5:
        overall = "偏多"
    elif neg > pos * 1.5:
        overall = "偏空"
    else:
        overall = "中性"

    def pct(n):
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "positive": pos,
        "negative": neg,
        "neutral": neu,
        "positive_pct": pct(pos),
        "negative_pct": pct(neg),
        "neutral_pct": pct(neu),
        "avg_score": round(avg, 3),
        "overall": overall,
    }
