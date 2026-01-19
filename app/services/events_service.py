from app.db import create_db_connection, _normalize_timestamps

DEFAULT_THEME_COLOR = '#4f46e5'

def create_event(slug, title, logo_url, video_url, theme_color=None, header_bg_color=None, header_text_color=None, body_bg_color=None, body_text_color=None):
    theme_color = theme_color or DEFAULT_THEME_COLOR
    header_bg_color = header_bg_color or '#0a0b16'
    header_text_color = header_text_color or '#cbd5e1'
    body_bg_color = body_bg_color or '#050511'
    body_text_color = body_text_color or '#cbd5e1'

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events (slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color)
            )
            conn.commit()
            return cursor.lastrowid

def get_event_by_slug(slug):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, is_active FROM events WHERE slug = %s",
                (slug,)
            )
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None

def get_event_by_id(event_id):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, is_active FROM events WHERE id = %s",
                (event_id,)
            )
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None

def list_events():
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, is_active, created_at FROM events ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [_normalize_timestamps(row) for row in rows]

def update_event(event_id, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, is_active):
    theme_color = theme_color or DEFAULT_THEME_COLOR
    header_bg_color = header_bg_color or '#0a0b16'
    header_text_color = header_text_color or '#cbd5e1'
    body_bg_color = body_bg_color or '#050511'
    body_text_color = body_text_color or '#cbd5e1'

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE events SET title=%s, logo_url=%s, video_url=%s, theme_color=%s, header_bg_color=%s, header_text_color=%s, body_bg_color=%s, body_text_color=%s, is_active=%s WHERE id=%s",
                (title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, 1 if is_active else 0, event_id)
            )
            conn.commit()
            return True
