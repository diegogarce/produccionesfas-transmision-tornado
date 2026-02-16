from app.db import create_db_connection, _normalize_timestamps


def _execute_first_success(cursor, attempts):
    last_error = None
    for sql, params in attempts:
        try:
            cursor.execute(sql, params)
            return
        except Exception as e:
            last_error = e
    if last_error:
        raise last_error


def _supports_header_fields(error: Exception) -> bool:
    # PyMySQL raises ProgrammingError for unknown columns.
    msg = str(error)
    return "Unknown column" in msg and (
        "header_bg_color" in msg or "header_text_color" in msg
    )


_event_columns_cache = None


_EVENT_SELECT_COLUMNS = [
    "id",
    "slug",
    "title",
    "description",
    "logo_url",
    "video_url",
    "header_bg_color",
    "header_text_color",
    "is_active",
    "timezone",
    "status",
    "registration_mode",
    "registration_restricted_type",
    "allowed_domain",
    "registration_open_at",
    "registration_close_at",
    "access_open_at",
    "capacity",
    "registration_schema",
    "registration_success_message",
    "is_deleted",
    "created_at",
]

_EVENT_LIST_COLUMNS = [
    "id",
    "slug",
    "title",
    "description",
    "logo_url",
    "video_url",
    "header_bg_color",
    "header_text_color",
    "is_active",
    "created_at",
    "timezone",
    "status",
    "registration_mode",
    "registration_restricted_type",
    "allowed_domain",
    "registration_open_at",
    "access_open_at",
    "capacity",
    "registration_schema",
    "is_deleted",
]


def _get_event_columns(cursor):
    """
    Returns a list of actually available columns in the 'events' table.
    Used for graceful updates when schema changes.
    """
    cursor.execute("DESCRIBE events")
    return [row['Field'] for row in cursor.fetchall()]


def _filter_column_pairs(cursor, pairs):
    """Filters a list of (column, value) tuples based on available DB columns."""
    available = _get_event_columns(cursor)
    return [(k, v) for k, v in pairs if k in available]


def _filter_columns(cursor, columns):
    """Filters a list of columns based on available DB columns."""
    available = _get_event_columns(cursor)
    return [c for c in columns if c in available]


def _select_event(cursor, where_clause, params):
    cols = _filter_columns(cursor, _EVENT_SELECT_COLUMNS)
    sql = f"SELECT {', '.join(cols)} FROM events WHERE {where_clause}"
    cursor.execute(sql, params)
    return cursor.fetchone()


def create_event(
    slug,
    title,
    logo_url,
    video_url,
    description=None,
    header_bg_color=None,
    header_text_color=None,
    timezone="America/Mexico_City",
    status=None,
    registration_mode=None,
    registration_restricted_type=None,
    allowed_domain=None,
    registration_open_at=None,
    registration_close_at=None,
    access_open_at=None,
    capacity=None,
    registration_schema=None,
    registration_success_message=None,
    is_deleted=None,
):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            candidate_pairs = [
                ("slug", slug),
                ("title", title),
                ("logo_url", logo_url),
                ("video_url", video_url),
                ("description", description),
                ("header_bg_color", header_bg_color),
                ("header_text_color", header_text_color),
                ("timezone", timezone),
                ("status", status),
                ("registration_mode", registration_mode),
                ("registration_restricted_type", registration_restricted_type),
                ("allowed_domain", allowed_domain),
                ("registration_open_at", registration_open_at),
                ("registration_close_at", registration_close_at),
                ("access_open_at", access_open_at),
                ("capacity", capacity),
                ("registration_schema", registration_schema),
                ("registration_success_message", registration_success_message),
                ("is_deleted", is_deleted),
            ]
            columns, values = _filter_column_pairs(cursor, candidate_pairs)
            if not columns:
                raise RuntimeError("No columns available to insert event")
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO events ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(sql, values)
            conn.commit()
            return cursor.lastrowid


def get_event_by_slug(slug):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            event = _select_event(cursor, "slug = %s AND is_deleted = 0", (slug,))
            return _normalize_timestamps(event)


def get_event_by_id(event_id):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            event = _select_event(cursor, "id = %s", (event_id,))
            return _normalize_timestamps(event)


def list_events(event_ids=None):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cols = _filter_columns(cursor, _EVENT_SELECT_COLUMNS)
            if event_ids:
                format_strings = ",".join(["%s"] * len(event_ids))
                sql = f"SELECT {', '.join(cols)} FROM events WHERE is_deleted = 0 AND id IN ({format_strings})"
                cursor.execute(sql, tuple(event_ids))
            else:
                sql = f"SELECT {', '.join(cols)} FROM events WHERE is_deleted = 0 ORDER BY created_at DESC"
                cursor.execute(sql)
            events = cursor.fetchall()
            return [_normalize_timestamps(e) for e in events]


def get_registration_count(event_id: int):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM users WHERE event_id = %s",
                (event_id,)
            )
            result = cursor.fetchone()
            return result["count"] if result else 0


def is_email_whitelisted(event_id: int, email: str):
    """
    Verifica si un correo está en la whitelist simple (sólo emails)
    """
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM event_whitelist WHERE event_id = %s AND email = %s",
                (event_id, email.lower()),
            )
            return cursor.fetchone() is not None


def get_whitelist(event_id: int):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT email FROM event_whitelist WHERE event_id = %s",
                (event_id,),
            )
            return [row["email"] for row in cursor.fetchall()]


def is_user_whitelisted(event_id: int, user_data: dict):
    """
    Verifica si un usuario está en la whitelist avanzada basándose en múltiples campos
    user_data debe contener los campos del formulario de registro
    """
    # 1. Obtener campos de la whitelist (desde el primer registro o esquema)
    # Para simplificar, buscamos en los registros de la tabla event_whitelist si tuviéramos campos dinámicos.
    # Pero hoy event_whitelist solo tiene 'email'.
    # Si implementamos whitelist avanzada, necesitaríamos otra tabla o estructura.
    # Por ahora, usamos event_whitelist como base.
    
    email = user_data.get("email", "").lower()
    if not email:
        return False
        
    return is_email_whitelisted(event_id, email)


def _whitelist_matches(user_data: dict, whitelist_entry: dict):
    """
    Verifica si los datos del usuario coinciden con una entrada de whitelist
    """
    # Campos clave para verificar
    key_fields = ['email', 'name', 'employee_id', 'phone', 'company']
    
    for field in key_fields:
        if field in whitelist_entry:
            user_value = str(user_data.get(field, '')).strip().lower()
            whitelist_value = str(whitelist_entry.get(field, '')).strip().lower()
            
            if user_value != whitelist_value:
                return False
    
    return True


def get_advanced_whitelist(event_id: int):
    """
    Obtiene la whitelist avanzada completa para un evento
    """
    if not event_id:
        return []
    
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT whitelist_data FROM event_whitelist_advanced WHERE event_id=%s ORDER BY created_at ASC",
                    (event_id,),
                )
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    whitelist_data = row.get("whitelist_data")
                    if isinstance(whitelist_data, str):
                        try:
                            import json
                            whitelist_data = json.loads(whitelist_data)
                        except:
                            continue
                    result.append(whitelist_data)
                
                return result
    except Exception:
        return []


def replace_advanced_whitelist(event_id: int, whitelist_entries: list):
    """
    Reemplaza la whitelist avanzada con nuevas entradas
    whitelist_entries es una lista de diccionarios con los campos del usuario
    """
    if not event_id:
        return 0
    
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                # Eliminar entradas existentes
                cursor.execute("DELETE FROM event_whitelist_advanced WHERE event_id=%s", (event_id,))
                
                # Insertar nuevas entradas
                import json
                count = 0
                for entry in whitelist_entries:
                    if not entry:
                        continue
                    
                    # Asegurar que entry sea un JSON válido
                    whitelist_json = json.dumps(entry, ensure_ascii=False)
                    cursor.execute(
                        "INSERT INTO event_whitelist_advanced (event_id, whitelist_data) VALUES (%s, %s)",
                        (event_id, whitelist_json)
                    )
                    count += 1
                
                conn.commit()
                return count
    except Exception as e:
        print(f"Error replacing advanced whitelist: {e}")
        return 0


def replace_whitelist(event_id: int, emails):
    if not event_id:
        return 0

    normalized = []
    if emails:
        for e in emails:
            if not e:
                continue
            s = str(e).strip().lower()
            if "@" not in s:
                continue
            normalized.append(s)

    deduped = sorted(set(normalized))
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM event_whitelist WHERE event_id=%s", (event_id,))
                if deduped:
                    cursor.executemany(
                        "INSERT INTO event_whitelist (event_id, email) VALUES (%s, %s)",
                        [(event_id, e) for e in deduped],
                    )
            conn.commit()
        return len(deduped)
    except Exception:
        return 0


def update_event(
    event_id,
    title,
    logo_url,
    video_url,
    is_active,
    description=None,
    header_bg_color=None,
    header_text_color=None,
    timezone="America/Mexico_City",
    status=None,
    registration_mode=None,
    registration_restricted_type=None,
    allowed_domain=None,
    registration_open_at=None,
    registration_close_at=None,
    access_open_at=None,
    capacity=None,
    registration_schema=None,
    registration_success_message=None,
    is_deleted=None,
):
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            candidate_pairs = [
                ("title", title),
                ("description", description),
                ("logo_url", logo_url),
                ("video_url", video_url),
                ("header_bg_color", header_bg_color),
                ("header_text_color", header_text_color),
                ("is_active", 1 if is_active else 0),
                ("timezone", timezone),
                ("status", status),
                ("registration_mode", registration_mode),
                ("registration_restricted_type", registration_restricted_type),
                ("allowed_domain", allowed_domain),
                ("registration_open_at", registration_open_at),
                ("registration_close_at", registration_close_at),
                ("access_open_at", access_open_at),
                ("capacity", capacity),
                ("registration_schema", registration_schema),
                ("registration_success_message", registration_success_message),
                ("is_deleted", is_deleted),
            ]
            columns, values = _filter_column_pairs(cursor, candidate_pairs)
            if not columns:
                return False
            set_clause = ", ".join(f"{col}=%s" for col in columns)
            sql = f"UPDATE events SET {set_clause} WHERE id=%s"
            cursor.execute(sql, values + [event_id])
            conn.commit()
            return cursor.rowcount > 0
