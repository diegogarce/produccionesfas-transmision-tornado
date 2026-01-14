from app.db import create_db_connection, _normalize_timestamps

def create_event(slug, title, logo_url, video_url):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events (slug, title, logo_url, video_url) VALUES (%s, %s, %s, %s)",
                (slug, title, logo_url, video_url)
            )
            conn.commit()
            return cursor.lastrowid

def get_event_by_slug(slug):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slug, title, logo_url, video_url, is_active FROM events WHERE slug = %s",
                (slug,)
            )
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None

def get_event_by_id(event_id):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slug, title, logo_url, video_url, is_active FROM events WHERE id = %s",
                (event_id,)
            )
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None

def list_events():
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, slug, title, logo_url, video_url, is_active, created_at FROM events ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [_normalize_timestamps(row) for row in rows]

def update_event(event_id, title, logo_url, video_url, is_active):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE events SET title=%s, logo_url=%s, video_url=%s, is_active=%s WHERE id=%s",
                (title, logo_url, video_url, 1 if is_active else 0, event_id)
            )
            conn.commit()
            return True
