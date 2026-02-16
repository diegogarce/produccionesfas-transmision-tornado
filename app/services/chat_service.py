"""
Chat: listado reciente y envío. Con CHAT_RECENT_IN_REDIS, últimos N mensajes en Redis;
persistencia en MySQL (síncrona o async vía IOLoop.add_callback).
"""
import json
from app.db import _normalize_timestamps, create_db_connection
from app import metrics
from app.config import CHAT_RECENT_IN_REDIS, CHAT_REDIS_MAX_MESSAGES

CHAT_KEY_PREFIX = "chat:event:"


def _get_chat_redis():
    if not CHAT_RECENT_IN_REDIS:
        return None
    try:
        from app.services.redis_cache import get_redis_cache
        return get_redis_cache()
    except Exception:
        return None


def list_recent_chats(limit=25, event_id=None):
    if CHAT_RECENT_IN_REDIS and event_id is not None:
        r = _get_chat_redis()
        if r:
            try:
                key = f"{CHAT_KEY_PREFIX}{event_id}"
                raw = r.lrange(key, -limit, -1)
                if raw:
                    out = []
                    for s in raw:
                        try:
                            row = json.loads(s)
                            out.append(_normalize_timestamps(row))
                        except (json.JSONDecodeError, TypeError):
                            continue
                    return out
            except Exception:
                pass
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = (
                "SELECT "
                "  u.name AS user_name, "
                "  cm.user_id, "
                "  cm.message, "
                "  cm.created_at "
                "FROM chat_messages cm "
                "JOIN users u ON u.id = cm.user_id"
            )
            params = []
            if event_id:
                sql += " WHERE cm.event_id = %s"
                params.append(event_id)
            sql += " ORDER BY cm.id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    result = [_normalize_timestamps(row) for row in reversed(rows)]
    if CHAT_RECENT_IN_REDIS and event_id is not None and result:
        r = _get_chat_redis()
        if r:
            try:
                key = f"{CHAT_KEY_PREFIX}{event_id}"
                for row in reversed(result):
                    r.rpush(key, json.dumps(row, default=str))
                r.ltrim(key, -CHAT_REDIS_MAX_MESSAGES, -1)
            except Exception:
                pass
    return result


def add_chat_message(user_id: int, text: str, event_id: int = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone() or {}
    user_name = user.get("name") or "Visitante"

    if CHAT_RECENT_IN_REDIS and event_id is not None:
        r = _get_chat_redis()
        if r:
            try:
                from datetime import datetime, timezone
                row = {
                    "user_name": user_name,
                    "user_id": user_id,
                    "message": text,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                key = f"{CHAT_KEY_PREFIX}{event_id}"
                r.rpush(key, json.dumps(row, default=str))
                r.ltrim(key, -CHAT_REDIS_MAX_MESSAGES, -1)
                r.delete(f"watch:event:{event_id}")
            except Exception:
                pass
        try:
            metrics.chat_messages.labels(event_id=str(event_id) or "global").inc()
        except Exception:
            pass
        return {"user_id": user_id, "user": user_name, "message": text}

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages (user_id, message, event_id) VALUES (%s, %s, %s)",
                (user_id, text, event_id),
            )
            try:
                metrics.chat_messages.labels(event_id=str(event_id) or "global").inc()
            except Exception:
                pass
    return {"user_id": user_id, "user": user_name, "message": text}


def persist_chat_to_mysql(user_id: int, text: str, event_id: int = None):
    """Persistir mensaje en MySQL (llamar vía IOLoop.add_callback cuando CHAT_RECENT_IN_REDIS)."""
    if event_id is None:
        return
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO chat_messages (user_id, message, event_id) VALUES (%s, %s, %s)",
                    (user_id, text, event_id),
                )
            conn.commit()
    except Exception:
        pass
