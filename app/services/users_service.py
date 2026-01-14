from app.db import create_db_connection

def get_user_status(user_id):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT chat_blocked, qa_blocked, banned FROM users WHERE id=%s",
                (user_id,)
            )
            return cursor.fetchone()

def update_user_status(user_id, field, value):
    # field should be one of: chat_blocked, qa_blocked, banned
    valid_fields = ["chat_blocked", "qa_blocked", "banned"]
    if field not in valid_fields:
        return False
        
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE users SET {field}=%s WHERE id=%s",
                (1 if value else 0, user_id)
            )
            conn.commit()
            return True

def is_user_banned(user_id):
    status = get_user_status(user_id)
    return status.get("banned") if status else False

def is_chat_blocked(user_id):
    status = get_user_status(user_id)
    return status.get("chat_blocked") if status else False

def is_qa_blocked(user_id):
    status = get_user_status(user_id)
    return status.get("qa_blocked") if status else False
