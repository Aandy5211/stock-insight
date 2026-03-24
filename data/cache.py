"""磁盘缓存封装（基于 diskcache）"""
import functools
import time
import diskcache
from config import CACHE_DIR, CACHE_TTL

_cache = diskcache.Cache(CACHE_DIR)


def get(key: str):
    return _cache.get(key)


def set(key: str, value, ttl_key: str = "financial"):
    expire = CACHE_TTL.get(ttl_key, 3600)
    _cache.set(key, value, expire=expire)


def delete(key: str):
    _cache.delete(key)


def clear():
    _cache.clear()


_SENTINEL = object()  # 用于区分"未命中"和"缓存值为 None"


def cached(ttl_key: str = "financial"):
    """装饰器：自动缓存函数返回值，None/空结果也缓存 5 分钟避免重复请求"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            cached_val = _cache.get(cache_key, default=_SENTINEL)
            if cached_val is not _SENTINEL:
                return cached_val
            result = func(*args, **kwargs)
            if result is not None and not (hasattr(result, '__len__') and len(result) == 0):
                expire = CACHE_TTL.get(ttl_key, 3600)
            else:
                expire = 300  # 失败/空结果缓存 5 分钟
            _cache.set(cache_key, result, expire=expire)
            return result
        return wrapper
    return decorator
