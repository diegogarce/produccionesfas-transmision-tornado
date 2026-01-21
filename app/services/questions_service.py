from app.db import _normalize_timestamps, create_db_connection, now_hhmm_in_timezone


def _fetch_event_timezone(cursor, event_id: int | None) -> str | None:
    if not event_id:
        return None
    try:
        cursor.execute("SELECT timezone FROM events WHERE id=%s", (event_id,))
        row = cursor.fetchone() or {}
        return row.get("timezone")
    except Exception:
        return None


def list_questions(status=None, limit=30, event_id=None):
    sql = (
        "SELECT "
        "  q.id, "
        "  COALESCE(q.manual_user_name, u.name) AS user_name, "
        "  q.question_text, "
        "  q.status, "
        "  q.created_at "
        "FROM questions q "
        "JOIN users u ON u.id = q.user_id"
    )
    params = []
    
    where_clauses = []
    if status:
        where_clauses.append("q.status=%s")
        params.append(status)
    if event_id:
        where_clauses.append("q.event_id=%s")
        params.append(event_id)
        
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
        
    sql += " ORDER BY q.id DESC LIMIT %s"
    params.append(limit)
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    return [_normalize_timestamps(row) for row in rows]


def list_pending_and_approved(limit=50, event_id=None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            base_select = (
                "SELECT "
                "  q.id, "
                "  COALESCE(q.manual_user_name, u.name) AS user_name, "
                "  q.question_text, "
                "  q.created_at "
                "FROM questions q "
                "JOIN users u ON u.id = q.user_id "
            )
            pending_sql = base_select + " WHERE q.status='pending'"
            approved_sql = base_select + " WHERE q.status='approved'"
            read_sql = base_select + " WHERE q.status='read'"
            params = []
            
            if event_id:
                pending_sql += " AND q.event_id = %s"
                approved_sql += " AND q.event_id = %s"
                read_sql += " AND q.event_id = %s"
                params.append(event_id)
            
            pending_sql += " ORDER BY q.created_at DESC LIMIT %s"
            approved_sql += " ORDER BY q.created_at DESC LIMIT %s"
            read_sql += " ORDER BY q.created_at DESC LIMIT %s"
            
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


def add_question(user_id: int, question_text: str, event_id: int = None, manual_user_name: str = None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO questions (user_id, manual_user_name, question_text, status, event_id) VALUES (%s, %s, %s, 'pending', %s)",
                (user_id, manual_user_name, question_text, event_id),
            )
            question_id = cursor.lastrowid

            cursor.execute(
                "SELECT COALESCE(q.manual_user_name, u.name) AS user_name "
                "FROM questions q JOIN users u ON u.id=q.user_id WHERE q.id=%s",
                (question_id,),
            )
            row = cursor.fetchone() or {}
            display_name = row.get("user_name") or "Visitante"
            event_tz = _fetch_event_timezone(cursor, event_id)
    return {
        "id": question_id,
        "user": display_name,
        "question": question_text,
        "timestamp": now_hhmm_in_timezone(event_tz),
    }


def approve_question(question_id: int):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE questions SET status='approved' WHERE id=%s", (question_id,))
            cursor.execute(
                "SELECT COALESCE(q.manual_user_name, u.name) AS user_name, q.question_text, e.timezone "
                "FROM questions q "
                "JOIN users u ON u.id=q.user_id "
                "LEFT JOIN events e ON e.id=q.event_id "
                "WHERE q.id=%s",
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": question_id,
        "user": row["user_name"],
        "question": row["question_text"],
        "timestamp": now_hhmm_in_timezone(row.get("timezone")),
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
                "SELECT COALESCE(q.manual_user_name, u.name) AS user_name, q.question_text, e.timezone "
                "FROM questions q "
                "JOIN users u ON u.id=q.user_id "
                "LEFT JOIN events e ON e.id=q.event_id "
                "WHERE q.id=%s",
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": question_id,
        "user": row["user_name"],
        "question": row["question_text"],
        "timestamp": now_hhmm_in_timezone(row.get("timezone")),
    }


def mark_question_as_read(question_id: int):
    """Sets a question status to 'read' or 'answered'."""
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE questions SET status='read' WHERE id=%s", (question_id,))
            cursor.execute(
                "SELECT COALESCE(q.manual_user_name, u.name) AS user_name, q.question_text, e.timezone "
                "FROM questions q "
                "JOIN users u ON u.id=q.user_id "
                "LEFT JOIN events e ON e.id=q.event_id "
                "WHERE q.id=%s",
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": question_id,
        "user": row["user_name"],
        "question": row["question_text"],
        "timestamp": now_hhmm_in_timezone(row.get("timezone")),
    }
