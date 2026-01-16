from app.db import _normalize_timestamps, create_db_connection


def list_recent_chats(limit=25, event_id=None):
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
    return [_normalize_timestamps(row) for row in reversed(rows)]


def add_chat_message(user_id: int, text: str, event_id: int = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages (user_id, message, event_id) VALUES (%s, %s, %s)",
                (user_id, text, event_id),
            )

            cursor.execute("SELECT name FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone() or {}
            user_name = user.get("name") or "Visitante"
    # Return a simple payload for broadcast
    return {
        "user_id": user_id,
        "user": user_name,
        "message": text,
    }
