from datetime import datetime

from app.db import _normalize_timestamps, create_db_connection


def list_questions(status=None, limit=30, event_id=None):
    sql = "SELECT id, user_name, question_text, status, created_at FROM questions"
    params = []
    
    where_clauses = []
    if status:
        where_clauses.append("status=%s")
        params.append(status)
    if event_id:
        where_clauses.append("event_id=%s")
        params.append(event_id)
        
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
        
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    return [_normalize_timestamps(row) for row in rows]


def list_pending_and_approved(limit=50, event_id=None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            pending_sql = "SELECT id, user_name, question_text, created_at FROM questions WHERE status='pending'"
            approved_sql = "SELECT id, user_name, question_text, created_at FROM questions WHERE status='approved'"
            read_sql = "SELECT id, user_name, question_text, created_at FROM questions WHERE status='read'"
            params = []
            
            if event_id:
                pending_sql += " AND event_id = %s"
                approved_sql += " AND event_id = %s"
                read_sql += " AND event_id = %s"
                params.append(event_id)
            
            pending_sql += " ORDER BY created_at DESC LIMIT %s"
            approved_sql += " ORDER BY created_at DESC LIMIT %s"
            read_sql += " ORDER BY created_at DESC LIMIT %s"
            
            cursor.execute(pending_sql, params + [limit])
            pending = cursor.fetchall()
            cursor.execute(approved_sql, params + [limit])
            approved = cursor.fetchall()
            cursor.execute(read_sql, params + [limit])
            read_questions = cursor.fetchall()
    return {
        "pending": [_normalize_timestamps(row) for row in pending],
        "approved": [_normalize_timestamps(row) for row in approved],
        "read": [_normalize_timestamps(row) for row in read_questions],
    }


def add_question(user_id: int, user_name: str, question_text: str, event_id: int = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO questions (user_id, user_name, question_text, status, event_id) VALUES (%s, %s, %s, 'pending', %s)",
                (user_id, user_name, question_text, event_id),
            )
            question_id = cursor.lastrowid
    return {
        "id": question_id,
        "user": user_name,
        "question": question_text,
        "timestamp": datetime.now().strftime("%H:%M"),
    }


def approve_question(question_id: int):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE questions SET status='approved' WHERE id=%s", (question_id,))
            cursor.execute(
                "SELECT user_name, question_text FROM questions WHERE id=%s",
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": question_id,
        "user": row["user_name"],
        "question": row["question_text"],
        "timestamp": datetime.now().strftime("%H:%M"),
    }


def reject_question(question_id: int):
    """Delete rejected question from database"""
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM questions WHERE id=%s", (question_id,))
    return True


def return_question_to_pending(question_id: int):
    """Returns an approved question back to pending status."""
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE questions SET status='pending' WHERE id=%s", (question_id,))
            cursor.execute(
                "SELECT user_name, question_text FROM questions WHERE id=%s",
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": question_id,
        "user": row["user_name"],
        "question": row["question_text"],
        "timestamp": datetime.now().strftime("%H:%M"),
    }


def mark_question_as_read(question_id: int):
    """Sets a question status to 'read' or 'answered'."""
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE questions SET status='read' WHERE id=%s", (question_id,))
    return True
