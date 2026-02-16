"""
Redis client para caché y listas (Fases A, B, C).
db=3: chat reciente, watch cache, reports snapshot.
"""
from app.config import REDIS_CONFIG

_redis_cache = None


def get_redis_cache():
    """Cliente Redis db=3 para chat:event:*, watch:event:*, reports:snapshot:*, broadcast:event:*."""
    global _redis_cache
    if _redis_cache is not None:
        return _redis_cache
    try:
        import redis
        _redis_cache = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=3,
            decode_responses=True,
        )
        _redis_cache.ping()
        return _redis_cache
    except Exception:
        return None
