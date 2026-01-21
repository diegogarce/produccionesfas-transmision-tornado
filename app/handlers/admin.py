import json
import re
import tornado.web
from app.db import create_db_connection
from app.handlers.base import BaseHandler
from app.services import events_service, staff_service


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _sanitize_hex_color(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if not _HEX_COLOR_RE.match(s):
        return None
    # Normalize short hex to 6-char
    if len(s) == 4:
        return f"#{s[1]*2}{s[2]*2}{s[3]*2}".lower()
    return s.lower()

class EventsAdminHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        # Admin console: superadmin sees all events; event-admin sees only assigned events.
        if self.is_superadmin():
            events = events_service.list_events()

            # Enrich events with staff info and registration counts
            if events:
                with create_db_connection() as conn:
                    with conn.cursor() as cursor:
                        for evt in events:
                            eid = evt["id"]
                            # Get Staff Names
                            cursor.execute(
                                "SELECT u.name, es.role FROM event_staff es "
                                "JOIN users u ON u.id = es.user_id "
                                "WHERE es.event_id=%s AND es.role IN ('moderator', 'speaker')",
                                (eid,)
                            )
                            staff_rows = cursor.fetchall()
                            evt["moderator_name"] = next((r["name"] for r in staff_rows if r["role"] == "moderator"), None)
                            evt["speaker_name"] = next((r["name"] for r in staff_rows if r["role"] == "speaker"), None)
                            
                            # Get Registry Count (Viewers registered for this event)
                            cursor.execute(
                                "SELECT COUNT(*) as cnt FROM users WHERE event_id=%s AND role='viewer'",
                                (eid,)
                            )
                            count_res = cursor.fetchone()
                            evt["registration_count"] = count_res["cnt"] if count_res else 0

            self.render("admin/events.html", events=events, is_superadmin=True)
            return

        user_id = self.get_current_user()
        if not user_id:
            self.redirect("/watch")
            return

        from app.services import staff_service
        allowed_event_ids = staff_service.list_event_ids_for_role(int(user_id), "admin")
        
        # If they don't have assigned events but ARE admins (global role), 
        # let them see the dashboard (empty state message) instead of /watch.
        if not allowed_event_ids and not self.is_admin():
            self.redirect("/watch")
            return

        events = events_service.list_events(event_ids=allowed_event_ids) if allowed_event_ids else []
        
        # Enrich events with staff info and registration counts
        if events:
            with create_db_connection() as conn:
                with conn.cursor() as cursor:
                    for evt in events:
                        eid = evt["id"]
                        # Get Staff Names
                        cursor.execute(
                            "SELECT u.name, es.role FROM event_staff es "
                            "JOIN users u ON u.id = es.user_id "
                            "WHERE es.event_id=%s AND es.role IN ('moderator', 'speaker')",
                            (eid,)
                        )
                        staff_rows = cursor.fetchall()
                        evt["moderator_name"] = next((r["name"] for r in staff_rows if r["role"] == "moderator"), None)
                        evt["speaker_name"] = next((r["name"] for r in staff_rows if r["role"] == "speaker"), None)
                        
                        # Get Registry Count (Viewers registered for this event)
                        cursor.execute(
                            "SELECT COUNT(*) as cnt FROM users WHERE event_id=%s AND role='viewer'",
                            (eid,)
                        )
                        count_res = cursor.fetchone()
                        evt["registration_count"] = count_res["cnt"] if count_res else 0
        self.render("admin/events.html", events=events, is_superadmin=False)

class APIEventsHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        # Only superadmin can create new events.
        if not self.is_superadmin():
            self.set_status(403)
            return

        try:
            data = json.loads(self.request.body)
            slug = data.get("slug")
            title = data.get("title")
            logo_url = data.get("logo_url")
            video_url = data.get("video_url")
            header_bg_color = _sanitize_hex_color(data.get("header_bg_color"))
            header_text_color = _sanitize_hex_color(data.get("header_text_color"))
            timezone = data.get("timezone", "America/Mexico_City")

            if not slug or not title:
                self.set_status(400)
                self.write({"status": "error", "message": "Slug and Title are required"})
                return

            event_id = events_service.create_event(slug, title, logo_url, video_url, header_bg_color, header_text_color, timezone)
            self.write({"status": "success", "event_id": event_id})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})

    @tornado.web.authenticated
    def put(self):
        try:
            data = json.loads(self.request.body)
            event_id = data.get("id")
            if not event_id:
                self.set_status(400)
                self.write({"status": "error", "message": "id requerido"})
                return

            # Superadmin can update any event; event-admin can update assigned events only.
            if not (self.is_superadmin() or self.is_admin_for_event(event_id)):
                self.set_status(403)
                return

            title = data.get("title")
            logo_url = data.get("logo_url")
            video_url = data.get("video_url")
            is_active = data.get("is_active")
            header_bg_color = _sanitize_hex_color(data.get("header_bg_color"))
            header_text_color = _sanitize_hex_color(data.get("header_text_color"))
            timezone = data.get("timezone", "America/Mexico_City")

            events_service.update_event(event_id, title, logo_url, video_url, is_active, header_bg_color, header_text_color, timezone)

            # If the event was closed, kick all users
            if not is_active:
                from app.handlers import ws
                ws.kick_all_from_event(event_id)

            self.write({"status": "success"})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})


class APIEventStaffHandler(BaseHandler):
    """Superadmin-only API to manage per-event staff assignments."""

    @tornado.web.authenticated
    def get(self):
        if not self.is_superadmin():
            self.set_status(403)
            return

        mode = self.get_query_argument("mode", "list")
        if mode == "users":
            # Return list of users filtered by role and availability
            search_query = self.get_query_argument("q", "").strip().lower()
            target_role = self.get_query_argument("role", "admin").lower()

            with create_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Base query parts
                    query = "SELECT u.id, u.email, u.name FROM users u "
                    params = []
                    
                    # 1. Filter by Global Role
                    where_clauses = ["u.role = %s"]
                    params.append(target_role)

                    # 2. Search filter (name/email)
                    if search_query:
                        where_clauses.append("(u.email LIKE %s OR u.name LIKE %s)")
                        params.append(f"%{search_query}%")
                        params.append(f"%{search_query}%")

                    # 3. Availability Check (Exclusive for Moderator/Speaker)
                    # Admins can be in multiple events, but Mods/Speakers must be free.
                    if target_role in ["moderator", "speaker"]:
                        where_clauses.append("u.id NOT IN (SELECT user_id FROM event_staff)")

                    # Construct final query
                    sql = f"{query} WHERE {' AND '.join(where_clauses)} ORDER BY u.name ASC LIMIT 20"
                    
                    cursor.execute(sql, tuple(params))
                    users = cursor.fetchall() or []
                    
                    # Map to Select2 format
                    results = []
                    for u in users:
                        email = u["email"]
                        name = u["name"] or ""
                        results.append({
                            "id": email, # We still use email as ID for the frontend logic
                            "text": f"{name} ({email})" if name else email
                        })
                    self.write({"status": "success", "results": results})
            return

        try:
            event_id = int(self.get_query_argument("event_id"))
        except Exception:
            self.set_status(400)
            self.write({"status": "error", "message": "event_id requerido"})
            return

        from app.services import staff_service
        rows = staff_service.list_staff_for_event(event_id)
        self.write({"status": "success", "staff": rows})

    @tornado.web.authenticated
    def post(self):
        if not self.is_superadmin():
            self.set_status(403)
            return

        try:
            data = json.loads(self.request.body)
            event_id = int(data.get("event_id"))
            email = data.get("email")
            role = data.get("role")

            from app.services import staff_service
            assignment = staff_service.upsert_staff_by_email(event_id=event_id, email=email, role=role)
            self.write({"status": "success", "assignment": assignment})
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "message": str(e)})

    @tornado.web.authenticated
    def delete(self):
        if not self.is_superadmin():
            self.set_status(403)
            return

        try:
            data = json.loads(self.request.body) if self.request.body else {}
            event_id = int(data.get("event_id") or self.get_query_argument("event_id"))
            user_id = int(data.get("user_id") or self.get_query_argument("user_id"))
        except Exception:
            self.set_status(400)
            self.write({"status": "error", "message": "event_id y user_id requeridos"})
            return

        from app.services import staff_service
        ok = staff_service.remove_staff(user_id=user_id, event_id=event_id)
        self.write({"status": "success", "removed": bool(ok)})


class StaffAdminHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        if not self.is_superadmin():
            self.redirect("/watch")
            return
        
        staff_list = staff_service.list_all_staff_global()
        self.render("admin/staff.html", staff=staff_list, is_superadmin=True)


class APIStaffHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        if not self.is_superadmin():
            self.set_status(403)
            return

        try:
            data = json.loads(self.request.body)
            user_id = data.get("id")
            email = data.get("email", "").strip().lower()
            name = data.get("name", "").strip()
            role = data.get("role", "viewer")

            if not email:
                self.set_status(400)
                self.write({"status": "error", "message": "Email es requerido"})
                return

            with create_db_connection() as conn:
                with conn.cursor() as cursor:
                    if user_id:
                        # Update by ID
                        cursor.execute(
                            "UPDATE users SET email=%s, name=%s, role=%s WHERE id=%s",
                            (email, name, role, user_id)
                        )
                    else:
                        # Check if user already exists by email (for global users)
                        cursor.execute(
                            "SELECT id FROM users WHERE email=%s AND event_id IS NULL LIMIT 1",
                            (email,)
                        )
                        existing = cursor.fetchone()
                        if existing:
                            cursor.execute(
                                "UPDATE users SET name=%s, role=%s WHERE id=%s",
                                (name, role, existing["id"])
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO users (email, name, role, event_id) VALUES (%s, %s, %s, NULL)",
                                (email, name or email.split("@")[0], role)
                            )
                    conn.commit()
            
            self.write({"status": "success"})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})

