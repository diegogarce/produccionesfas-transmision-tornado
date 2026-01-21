from app.db import _normalize_timestamps, create_db_connection


# Active window for "connected" audience; bumped to be more tolerant of slow networks
DEFAULT_ACTIVE_WINDOW_SECONDS = 600


def mark_session_inactive(user_id: int):
    """Mark a user's session as inactive so it no longer appears as "connected".

    We don't have an explicit end_time column; instead we move last_ping far enough
    into the past so the active filter excludes it.
    """
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE session_analytics SET last_ping=DATE_SUB(NOW(), INTERVAL 1 DAY) WHERE user_id=%s",
                (user_id,),
            )


def ensure_session_analytics(user_id: int, event_id: int = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            if event_id is None:
                return

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
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            if event_id is None:
                return

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

    # NOTE: MySQL does not reliably allow binding the INTERVAL value as a parameter,
    # so we safely inline this integer after coercion.
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
    
    params = []
    if event_id:
        query += " AND sa.event_id = %s "
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
    
    params = []
    if event_id:
        query += " WHERE sa.event_id = %s "
        params.append(event_id)
        
    query += "ORDER BY sa.last_ping DESC"

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [_normalize_timestamps(row) for row in rows]
