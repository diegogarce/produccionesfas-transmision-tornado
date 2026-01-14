from app.db import _normalize_timestamps, create_db_connection


def list_recent_chats(limit=25, event_id=None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            sql = "SELECT user_name, message, created_at FROM chat_messages"
            params = []
            if event_id:
                sql += " WHERE event_id = %s"
                params.append(event_id)
            sql += " ORDER BY id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    return [_normalize_timestamps(row) for row in reversed(rows)]


def add_chat_message(user_id: int, user_name: str, text: str, event_id: int = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages (user_id, user_name, message, event_id) VALUES (%s, %s, %s, %s)",
                (user_id, user_name, text, event_id),
            )
    # Return a simple payload for broadcast
    return {
        "user": user_name,
        "message": text,
    }
