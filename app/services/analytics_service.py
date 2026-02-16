import os
import time
from datetime import datetime, timedelta, timezone

from app.db import _normalize_timestamps, _get_target_timezone, create_db_connection
from app.config import PING_BACKEND

# Active window for "connected" audience; bumped to be more tolerant of slow networks
DEFAULT_ACTIVE_WINDOW_SECONDS = 600

# Con PING_BACKEND=redis: presencia en Redis cada ping; MySQL se actualiza como máximo cada N segundos
# por usuario (y al desconectar) para conservar historial en reportes (start_time, last_ping, total_minutes).
PING_MYSQL_INTERVAL_SECONDS = int(os.environ.get("PING_MYSQL_INTERVAL_SECONDS", "60"))

# Redis key: Sorted Set per event, score=timestamp, member=user_id
def _activity_key(event_id: int) -> str:
    return f"activity:{event_id}"


def _ping_mysql_ts_key(event_id: int, user_id: int) -> str:
    """Última vez que escribimos session_analytics para este user/event (throttle)."""
    return f"ping:mysql_ts:{event_id}:{user_id}"

_redis_activity = None

def _get_redis_activity():
    global _redis_activity
    if _redis_activity is not None:
        return _redis_activity
    if PING_BACKEND != "redis":
        return None
    try:
        import redis
        from app.config import REDIS_CONFIG
        _redis_activity = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=2,  # db=0 sessions, 1 telemetry, 2 activity/presence
            decode_responses=True,
        )
        _redis_activity.ping()
        return _redis_activity
    except Exception:
        return None


def mark_session_inactive(user_id: int, event_id: int = None):
    """Mark a user's session as inactive so it no longer appears as "connected"."""
    if PING_BACKEND == "redis":
        r = _get_redis_activity()
        if r and event_id is not None:
            try:
                r.zrem(_activity_key(event_id), str(user_id))
                r.delete(_ping_mysql_ts_key(event_id, user_id))
            except Exception:
                pass
        # Conservar historial: marcar sesión inactiva en MySQL para reportes
        if event_id is not None:
            try:
                with create_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE session_analytics SET last_ping=DATE_SUB(NOW(), INTERVAL 1 DAY) WHERE user_id=%s AND event_id=%s",
                            (user_id, event_id),
                        )
                    conn.commit()
            except Exception:
                pass
        return
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE session_analytics SET last_ping=DATE_SUB(NOW(), INTERVAL 1 DAY) WHERE user_id=%s",
                (user_id,),
            )


def ensure_session_analytics(user_id: int, event_id: int = None):
    """Presencia en vivo (Redis) y asegurar fila en MySQL para historial de reportes."""
    if event_id is None:
        return
    if PING_BACKEND == "redis":
        r = _get_redis_activity()
        if r:
            try:
                ts = time.time()
                r.zadd(_activity_key(event_id), {str(user_id): ts})
                r.zremrangebyscore(_activity_key(event_id), "-inf", ts - DEFAULT_ACTIVE_WINDOW_SECONDS)
            except Exception:
                pass
        # Historial: asegurar fila en MySQL (INSERT si no existe) para reportes y gráficas
        try:
            with create_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO session_analytics (user_id, event_id, start_time, last_ping, total_minutes) "
                        "VALUES (%s, %s, NOW(), NOW(), 0) "
                        "ON DUPLICATE KEY UPDATE last_ping=NOW()",
                        (user_id, event_id),
                    )
                conn.commit()
        except Exception:
            pass
        return
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM session_analytics WHERE user_id=%s AND event_id=%s",
                (user_id, event_id),
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE session_analytics SET last_ping=NOW() WHERE user_id=%s AND event_id=%s",
                    (user_id, event_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO session_analytics (user_id, event_id, start_time, last_ping, total_minutes) VALUES (%s, %s, NOW(), NOW(), 0)",
                    (user_id, event_id),
                )


def record_ping(user_id: int, event_id: int = None):
    """Presencia en vivo en Redis cada ping; MySQL se actualiza como máximo cada PING_MYSQL_INTERVAL_SECONDS para historial."""
    if event_id is None:
        return
    if PING_BACKEND == "redis":
        r = _get_redis_activity()
        if r:
            try:
                ts = time.time()
                r.zadd(_activity_key(event_id), {str(user_id): ts})
                r.zremrangebyscore(_activity_key(event_id), "-inf", ts - DEFAULT_ACTIVE_WINDOW_SECONDS)
            except Exception:
                pass
        # Historial: actualizar MySQL como máximo cada N segundos por usuario (evita miles de writes/s)
        r = _get_redis_activity()
        if r:
            try:
                key = _ping_mysql_ts_key(event_id, user_id)
                last_str = r.get(key)
                last_ts = float(last_str) if last_str else 0
                if ts - last_ts >= PING_MYSQL_INTERVAL_SECONDS:
                    with create_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE session_analytics SET last_ping=NOW(), total_minutes=total_minutes+1 WHERE user_id=%s AND event_id=%s",
                                (user_id, event_id),
                            )
                        conn.commit()
                    r.setex(key, DEFAULT_ACTIVE_WINDOW_SECONDS, str(ts))
            except Exception:
                pass
        return
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            updated = cursor.execute(
                "UPDATE session_analytics SET last_ping=NOW(), total_minutes=total_minutes+1 WHERE user_id=%s AND event_id=%s",
                (user_id, event_id),
            )
            if updated == 0:
                cursor.execute(
                    "INSERT INTO session_analytics (user_id, event_id, start_time, last_ping, total_minutes) VALUES (%s, %s, NOW(), NOW(), 0)",
                    (user_id, event_id),
                )
                cursor.execute(
                    "UPDATE session_analytics SET last_ping=NOW(), total_minutes=total_minutes+1 WHERE user_id=%s AND event_id=%s",
                    (user_id, event_id),
                )


def list_users_for_report():
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, email, phone, created_at FROM users ORDER BY id DESC")
            rows = cursor.fetchall()
    return [_normalize_timestamps(row) for row in rows]


def list_analytics_for_report():
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT sa.user_id, sa.start_time, sa.last_ping, sa.total_minutes, u.name AS user_name, e.timezone AS timezone "
                "FROM session_analytics sa "
                "JOIN users u ON u.id=sa.user_id "
                "LEFT JOIN events e ON e.id=sa.event_id "
                "ORDER BY sa.last_ping DESC"
            )
            rows = cursor.fetchall()
    return [_normalize_timestamps(row) for row in rows]


def list_active_sessions_for_report(active_within_seconds: int = DEFAULT_ACTIVE_WINDOW_SECONDS, event_id: int = None):
    active_within_seconds = int(active_within_seconds)
    if active_within_seconds <= 0:
        active_within_seconds = DEFAULT_ACTIVE_WINDOW_SECONDS

    # Con Redis: "quién está en vivo" viene del set; start_time, last_ping, session_minutes del historial en MySQL
    if PING_BACKEND == "redis" and event_id is not None:
        r = _get_redis_activity()
        if r:
            try:
                cutoff = time.time() - active_within_seconds
                raw = r.zrangebyscore(_activity_key(event_id), cutoff, "+inf")
                if not raw:
                    return []
                user_ids = [int(member) for member in raw]
                if not user_ids:
                    return []
                placeholders = ",".join(["%s"] * len(user_ids))
                query = (
                    "SELECT sa.user_id, u.name AS user_name, u.chat_blocked, u.qa_blocked, u.banned, "
                    "sa.start_time, sa.last_ping, sa.total_minutes AS session_minutes, e.timezone AS timezone "
                    "FROM session_analytics sa "
                    "JOIN users u ON u.id = sa.user_id "
                    "LEFT JOIN events e ON e.id = sa.event_id "
                    f"WHERE sa.event_id = %s AND sa.user_id IN ({placeholders}) "
                    "AND u.role = 'viewer' "
                    "AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id = %s) "
                    "ORDER BY sa.last_ping DESC"
                )
                params = [event_id] + user_ids + [event_id]
                with create_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(query, params)
                        rows = cursor.fetchall()
                return [_normalize_timestamps(row) for row in rows]
            except Exception:
                pass

    query = (
        "SELECT "
        "  sa.user_id, "
        "  u.name AS user_name, "
        "  u.chat_blocked, "
        "  u.qa_blocked, "
        "  u.banned, "
        "  sa.start_time, "
        "  sa.last_ping, "
        "  sa.total_minutes AS session_minutes, "
        "  e.timezone AS timezone "
        "FROM session_analytics sa "
        "JOIN users u ON u.id = sa.user_id "
        "LEFT JOIN events e ON e.id = sa.event_id "
        f"WHERE sa.last_ping >= DATE_SUB(NOW(), INTERVAL {active_within_seconds} SECOND) "
    )
    query += " AND u.role = 'viewer' "
    params = []
    if event_id:
        query += " AND sa.event_id = %s "
        query += " AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id = %s) "
        params.append(event_id)
        params.append(event_id)
    query += "ORDER BY sa.last_ping DESC"

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [_normalize_timestamps(row) for row in rows]


def list_all_participants_for_report(event_id: int = None):
    """Lists all participants for an event, even if inactive."""
    query = (
        "SELECT "
        "  sa.user_id, "
        "  u.name AS user_name, "
        "  u.email, "
        "  u.phone, "
        "  u.chat_blocked, "
        "  u.qa_blocked, "
        "  u.banned, "
        "  sa.start_time, "
        "  sa.last_ping, "
        "  sa.total_minutes AS session_minutes, "
        "  e.timezone AS timezone "
        "FROM session_analytics sa "
        "JOIN users u ON u.id = sa.user_id "
        "LEFT JOIN events e ON e.id = sa.event_id "
    )
    
    # Exclude global staff roles
    query += " WHERE u.role = 'viewer' "
    
    params = []
    if event_id:
        query += " AND sa.event_id = %s "
        # Exclude event-specific staff
        query += " AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id = %s) "
        params.append(event_id)
        params.append(event_id)
        
    query += "ORDER BY sa.last_ping DESC"

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [_normalize_timestamps(row) for row in rows]


def list_registered_users(event_id: int):
    """Lists all users registered for an event (role='viewer'), regardless of activity."""
    if not event_id:
        return []

    query = (
        "SELECT u.id, u.name, u.email, u.phone, u.created_at, u.role, erd.payload "
        "FROM users u "
        "LEFT JOIN event_registration_data erd ON u.id = erd.user_id AND u.event_id = erd.event_id "
        "WHERE u.event_id=%s AND u.role='viewer' "
        "AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id=%s) "
        "ORDER BY u.created_at DESC"
    )

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (event_id, event_id))
            rows = cursor.fetchall()

    return [_normalize_timestamps(row) for row in rows]


def _round_down_to_interval(dt_utc: datetime, interval_minutes: int) -> datetime:
    interval_seconds = max(int(interval_minutes), 1) * 60
    seconds = int(dt_utc.timestamp())
    rounded = (seconds // interval_seconds) * interval_seconds
    return datetime.fromtimestamp(rounded, tz=timezone.utc)


def _build_time_labels(start_utc: datetime, end_utc: datetime, interval_minutes: int, tz_name: str | None):
    tz = _get_target_timezone(tz_name)
    interval = timedelta(minutes=max(int(interval_minutes), 1))
    labels = []
    buckets = []

    cursor = _round_down_to_interval(start_utc, interval_minutes)
    end_rounded = _round_down_to_interval(end_utc, interval_minutes)

    total_minutes = int((end_rounded - cursor).total_seconds() / 60) if end_rounded >= cursor else 0
    include_date = total_minutes > 24 * 60

    while cursor <= end_rounded:
        local = cursor.astimezone(tz)
        labels.append(local.strftime("%m-%d %H:%M") if include_date else local.strftime("%H:%M"))
        buckets.append(cursor)
        cursor += interval

    return labels, buckets


def _fill_series_from_buckets(buckets, data_map):
    series = []
    for bucket in buckets:
        series.append(int(data_map.get(int(bucket.timestamp()), 0)))
    return series


def _apply_sample_series(labels, series_list):
    has_data = any(sum(series) > 0 for series in series_list)
    if has_data or not labels:
        return labels, series_list

    sample_labels = labels[-6:] if len(labels) >= 6 else labels
    sample_series = []
    base_patterns = [2, 4, 3, 6, 5, 2]
    for idx, series in enumerate(series_list):
        values = base_patterns[-len(sample_labels):]
        scale = idx + 1
        sample_series.append([v * scale for v in values])

    return sample_labels, sample_series


def build_reports_charts(event_id: int, tz_name: str | None, window_minutes: int = 60, interval_minutes: int = 5):
    if not event_id:
        return {
            "active_participants": {"labels": [], "series": []},
            "engagement": {"labels": [], "chat": [], "questions": []},
            "question_status": {"labels": [], "series": []},
            "retention": {"labels": [], "series": []},
        }

    window_minutes = max(int(window_minutes), 10)
    interval_minutes = max(int(interval_minutes), 1)

    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(minutes=window_minutes)

    labels, buckets = _build_time_labels(start_utc, end_utc, interval_minutes, tz_name)

    bucket_seconds = interval_minutes * 60

    active_map = {}
    chat_map = {}
    question_map = {}
    retention_map = {}

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "  FLOOR(UNIX_TIMESTAMP(sa.last_ping) / %s) * %s AS bucket_epoch, "
                "  COUNT(*) AS total "
                "FROM session_analytics sa "
                "JOIN users u ON u.id = sa.user_id "
                "WHERE sa.event_id = %s "
                "  AND u.role = 'viewer' "
                "  AND sa.last_ping >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
                "  AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id = %s) "
                "GROUP BY bucket_epoch "
                "ORDER BY bucket_epoch",
                (bucket_seconds, bucket_seconds, event_id, window_minutes, event_id),
            )
            for row in cursor.fetchall():
                active_map[int(row["bucket_epoch"]) if isinstance(row, dict) else int(row[0])] = int(
                    row["total"] if isinstance(row, dict) else row[1]
                )

            cursor.execute(
                "SELECT "
                "  FLOOR(UNIX_TIMESTAMP(created_at) / %s) * %s AS bucket_epoch, "
                "  COUNT(*) AS total "
                "FROM chat_messages "
                "WHERE event_id = %s "
                "  AND created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
                "GROUP BY bucket_epoch "
                "ORDER BY bucket_epoch",
                (bucket_seconds, bucket_seconds, event_id, window_minutes),
            )
            for row in cursor.fetchall():
                chat_map[int(row["bucket_epoch"]) if isinstance(row, dict) else int(row[0])] = int(
                    row["total"] if isinstance(row, dict) else row[1]
                )

            cursor.execute(
                "SELECT "
                "  FLOOR(UNIX_TIMESTAMP(created_at) / %s) * %s AS bucket_epoch, "
                "  COUNT(*) AS total "
                "FROM questions "
                "WHERE event_id = %s "
                "  AND created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
                "GROUP BY bucket_epoch "
                "ORDER BY bucket_epoch",
                (bucket_seconds, bucket_seconds, event_id, window_minutes),
            )
            for row in cursor.fetchall():
                question_map[int(row["bucket_epoch"]) if isinstance(row, dict) else int(row[0])] = int(
                    row["total"] if isinstance(row, dict) else row[1]
                )

            cursor.execute(
                "SELECT "
                "  FLOOR(UNIX_TIMESTAMP(sa.last_ping) / %s) * %s AS bucket_epoch, "
                "  AVG(sa.total_minutes) AS avg_minutes "
                "FROM session_analytics sa "
                "JOIN users u ON u.id = sa.user_id "
                "WHERE sa.event_id = %s "
                "  AND u.role = 'viewer' "
                "  AND sa.last_ping >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
                "  AND u.id NOT IN (SELECT user_id FROM event_staff WHERE event_id = %s) "
                "GROUP BY bucket_epoch "
                "ORDER BY bucket_epoch",
                (bucket_seconds, bucket_seconds, event_id, window_minutes, event_id),
            )
            for row in cursor.fetchall():
                retention_map[int(row["bucket_epoch"]) if isinstance(row, dict) else int(row[0])] = int(
                    row["avg_minutes"] if isinstance(row, dict) else row[1]
                )

            cursor.execute(
                "SELECT status, COUNT(*) AS total "
                "FROM questions "
                "WHERE event_id = %s "
                "GROUP BY status",
                (event_id,),
            )
            status_rows = cursor.fetchall()

    active_series = _fill_series_from_buckets(buckets, active_map)
    chat_series = _fill_series_from_buckets(buckets, chat_map)
    question_series = _fill_series_from_buckets(buckets, question_map)
    retention_series = _fill_series_from_buckets(buckets, retention_map)

    labels, (active_series, chat_series, question_series, retention_series) = _apply_sample_series(
        labels, [active_series, chat_series, question_series, retention_series]
    )

    status_labels = ["pending", "approved", "rejected", "read"]
    status_map = {"pending": 0, "approved": 0, "rejected": 0, "read": 0}
    for row in status_rows or []:
        if isinstance(row, dict):
            status_map[row.get("status")] = int(row.get("total") or 0)
        else:
            status_map[row[0]] = int(row[1] or 0)

    status_series = [status_map[label] for label in status_labels]
    if sum(status_series) == 0:
        status_series = [5, 3, 1, 2]

    return {
        "active_participants": {"labels": labels, "series": active_series},
        "engagement": {"labels": labels, "chat": chat_series, "questions": question_series},
        "question_status": {"labels": status_labels, "series": status_series},
        "retention": {"labels": labels, "series": retention_series},
    }
