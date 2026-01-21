from __future__ import annotations

from typing import Iterable, Optional

from app.db import create_db_connection


EVENT_STAFF_ROLES = {"admin", "moderator", "speaker"}


def get_event_role(user_id: int, event_id: int) -> Optional[str]:
    if not user_id or not event_id:
        return None

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT role FROM event_staff WHERE user_id=%s AND event_id=%s",
                (user_id, event_id),
            )
            row = cursor.fetchone()
            return (row or {}).get("role")


def user_has_any_event_role(user_id: int, event_id: int, roles: Iterable[str]) -> bool:
    roles = {str(r) for r in (roles or [])}
    if not roles:
        return False

    role = get_event_role(user_id, event_id)
    return bool(role and role in roles)


def list_event_ids_for_role(user_id: int, role: str) -> list[int]:
    role = str(role)
    if role not in EVENT_STAFF_ROLES:
        return []

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT event_id FROM event_staff WHERE user_id=%s AND role=%s ORDER BY event_id ASC",
                (user_id, role),
            )
            rows = cursor.fetchall() or []

    return [int(r.get("event_id")) for r in rows if r.get("event_id") is not None]


def list_staff_for_event(event_id: int) -> list[dict]:
    if not event_id:
        return []

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT es.user_id, u.name, u.email, es.event_id, es.role "
                "FROM event_staff es "
                "JOIN users u ON u.id = es.user_id "
                "WHERE es.event_id=%s "
                "ORDER BY FIELD(es.role,'admin','moderator','speaker'), u.name ASC",
                (event_id,),
            )
            return cursor.fetchall() or []


def upsert_staff_by_email(event_id: int, email: str, role: str) -> dict:
    """Assign a staff role to a (possibly global) user identified by email.

    Creates a global user (event_id NULL) if none exists.
    """
    if not event_id:
        raise ValueError("event_id requerido")

    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email requerido")

    role = str(role)
    if role not in EVENT_STAFF_ROLES:
        raise ValueError("role inválido")

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            # Prefer a global account for staff.
            cursor.execute(
                "SELECT id, name, email FROM users WHERE email=%s AND event_id IS NULL ORDER BY created_at DESC LIMIT 1",
                (email,),
            )
            user = cursor.fetchone()

            if not user:
                # Fallback: allow promoting an existing event-scoped user.
                cursor.execute(
                    "SELECT id, name, email FROM users WHERE email=%s AND event_id=%s ORDER BY created_at DESC LIMIT 1",
                    (email, event_id),
                )
                user = cursor.fetchone()

            if not user:
                cursor.execute(
                    "INSERT INTO users (name, email, role, event_id) VALUES (%s, %s, 'viewer', NULL)",
                    (email.split("@")[0], email),
                )
                user_id = cursor.lastrowid
            else:
                user_id = user["id"]

            cursor.execute(
                "INSERT INTO event_staff (user_id, event_id, role) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE role=VALUES(role)",
                (user_id, event_id, role),
            )
            conn.commit()

    return {"user_id": int(user_id), "event_id": int(event_id), "role": role}


def remove_staff(user_id: int, event_id: int) -> bool:
    if not user_id or not event_id:
        return False

    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            n = cursor.execute(
                "DELETE FROM event_staff WHERE user_id=%s AND event_id=%s",
                (user_id, event_id),
            )
            conn.commit()
            return n > 0


def list_all_staff_global() -> list[dict]:
    """List all users who have an administrative role (either global or per-event)."""
    with create_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT u.id, u.name, u.email, u.role as global_role, "
                "(SELECT COUNT(*) FROM event_staff WHERE user_id = u.id) as event_count "
                "FROM users u "
                "LEFT JOIN event_staff es ON u.id = es.user_id "
                "WHERE u.role IN ('superadmin', 'admin', 'moderator', 'speaker') OR es.role IS NOT NULL "
                "GROUP BY u.id, u.name, u.email, u.role "
                "ORDER BY FIELD(u.role, 'superadmin', 'admin', 'moderator', 'speaker', 'viewer'), u.name ASC"
            )
            return cursor.fetchall() or []
