from app.db import create_db_connection, _normalize_timestamps


def _supports_header_fields(error: Exception) -> bool:
    # PyMySQL raises ProgrammingError for unknown columns.
    msg = str(error)
    return "Unknown column" in msg and (
        "header_bg_color" in msg or "header_text_color" in msg
    )


def create_event(
    slug,
    title,
    logo_url,
    video_url,
    header_bg_color=None,
    header_text_color=None,
    timezone="America/Mexico_City",
):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO events (slug, title, logo_url, video_url, header_bg_color, header_text_color, timezone) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (slug, title, logo_url, video_url, header_bg_color, header_text_color, timezone),
                )
            except Exception as e:
                if _supports_header_fields(e):
                    cursor.execute(
                        "INSERT INTO events (slug, title, logo_url, video_url) VALUES (%s, %s, %s, %s)",
                        (slug, title, logo_url, video_url),
                    )
                else:
                    raise
            conn.commit()
            return cursor.lastrowid


def get_event_by_slug(slug):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT id, slug, title, logo_url, video_url, header_bg_color, header_text_color, is_active, timezone FROM events WHERE slug = %s",
                    (slug,),
                )
            except Exception as e:
                if _supports_header_fields(e):
                    cursor.execute(
                        "SELECT id, slug, title, logo_url, video_url, is_active, timezone FROM events WHERE slug = %s",
                        (slug,),
                    )
                else:
                    raise
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None


def get_event_by_id(event_id):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT id, slug, title, logo_url, video_url, header_bg_color, header_text_color, is_active, timezone FROM events WHERE id = %s",
                    (event_id,),
                )
            except Exception as e:
                if _supports_header_fields(e):
                    cursor.execute(
                        "SELECT id, slug, title, logo_url, video_url, is_active, timezone FROM events WHERE id = %s",
                        (event_id,),
                    )
                else:
                    raise
            row = cursor.fetchone()
            return _normalize_timestamps(row) if row else None


def list_events(event_ids=None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            params = []
            where_sql = ""
            if event_ids:
                event_ids = [int(eid) for eid in event_ids if eid is not None]
                if event_ids:
                    placeholders = ",".join(["%s"] * len(event_ids))
                    where_sql = f" WHERE id IN ({placeholders}) "
                    params.extend(event_ids)
            try:
                cursor.execute(
                    "SELECT id, slug, title, logo_url, video_url, header_bg_color, header_text_color, is_active, created_at, timezone FROM events"
                    + where_sql
                    + " ORDER BY created_at DESC",
                    params,
                )
            except Exception as e:
                if _supports_header_fields(e):
                    cursor.execute(
                        "SELECT id, slug, title, logo_url, video_url, is_active, created_at, timezone FROM events"
                        + where_sql
                        + " ORDER BY created_at DESC",
                        params,
                    )
                else:
                    raise
            rows = cursor.fetchall()
            return [_normalize_timestamps(row) for row in rows]


def update_event(
    event_id,
    title,
    logo_url,
    video_url,
    is_active,
    header_bg_color=None,
    header_text_color=None,
    timezone="America/Mexico_City",
):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "UPDATE events SET title=%s, logo_url=%s, video_url=%s, header_bg_color=%s, header_text_color=%s, is_active=%s, timezone=%s WHERE id=%s",
                    (
                        title,
                        logo_url,
                        video_url,
                        header_bg_color,
                        header_text_color,
                        1 if is_active else 0,
                        timezone,
                        event_id,
                    ),
                )
            except Exception as e:
                if _supports_header_fields(e):
                    cursor.execute(
                        "UPDATE events SET title=%s, logo_url=%s, video_url=%s, is_active=%s WHERE id=%s",
                        (title, logo_url, video_url, 1 if is_active else 0, event_id),
                    )
                else:
                    raise
            conn.commit()
            return True
