import os
import json
from datetime import datetime
import tornado.escape

from app.db import create_db_connection
from app.handlers.base import BaseHandler
from app.services import analytics_service, session_service


DEFAULT_REGISTRATION_SCHEMA = {
    "fields": [
        {"key": "name", "label": "Nombre completo", "type": "text", "required": True},
        {"key": "email", "label": "Correo corporativo", "type": "email", "required": True},
        {"key": "phone", "label": "Teléfono", "type": "tel", "required": False},
    ]
}


def _parse_registration_schema(event):
    if not event:
        return DEFAULT_REGISTRATION_SCHEMA

    raw = event.get("registration_schema")
    # print(f"DEBUG: Raw schema from DB for event {event.get('id')}: {raw} (Type: {type(raw)})")
    
    if not raw:
        return DEFAULT_REGISTRATION_SCHEMA

    try:
        # Handle if it's already a dict (JSON column in newer MySQL/PyMySQL)
        if isinstance(raw, dict):
            schema = raw
        # Handle if it's a string (legacy TEXT column or stringified JSON)
        elif isinstance(raw, str):
            schema = json.loads(raw)
        else:
            return DEFAULT_REGISTRATION_SCHEMA
            
        # Basic validation: must have 'fields' as a list
        if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
            # print("DEBUG: Schema is not a dict or fields is not a list")
            return DEFAULT_REGISTRATION_SCHEMA
            
        # print(f"DEBUG: Successfully parsed schema with {len(schema['fields'])} fields")
        return schema
    except Exception as e:
        # print(f"DEBUG: Error parsing registration_schema: {e}")
        return DEFAULT_REGISTRATION_SCHEMA


def _get_schema_fields(event):
    schema = _parse_registration_schema(event)
    fields = []
    for f in schema.get("fields", []):
        key = (f or {}).get("key")
        if not key:
            continue
        fields.append({
            "key": key,
            "label": (f or {}).get("label") or key,
            "type": (f or {}).get("type") or "text",
            "required": bool((f or {}).get("required")),
            "placeholder": (f or {}).get("placeholder") or "",
            "options": (f or {}).get("options") or [],
        })
    if not fields:
        return DEFAULT_REGISTRATION_SCHEMA.get("fields", [])
    return fields


class RegistrationHandler(BaseHandler):
    def get(self, slug=None):
        if self.current_user:
            if self.is_admin():
                self.redirect("/admin/events")
            else:
                self.redirect(f"/e/{slug}/watch" if slug else "/watch")
            return
        
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)
        if not event:
            self.render("error.html", message="Evento no encontrado")
            return
        if event.get("is_deleted"):
            self.render("error.html", message="Evento no disponible")
            return
            
        if not event["is_active"]:
            self.render("error.html", message="El registro para este evento ha finalizado.")
            return

        if os.getenv("EVENT_FLOW_V2", "1") == "1":
            status = event.get("status") or ("PUBLISHED" if event.get("is_active") else "CLOSED")
            if status == "DRAFT":
                self.render("error.html", message="El registro para este evento aún no está disponible (Borrador).")
                return
            if status == "CLOSED":
                self.render("error.html", message="El registro para este evento ha finalizado.")
                return
            if status != "PUBLISHED":
                self.render("error.html", message="El evento no está disponible para registro.")
                return

            registration_open_at = event.get("registration_open_at")
            registration_close_at = event.get("registration_close_at")
            
            from app.db import _get_target_timezone, now_in_timezone
            tz = _get_target_timezone(event.get("timezone"))
            now = now_in_timezone(event.get("timezone"))

            if registration_open_at:
                try:
                    open_dt = datetime.strptime(registration_open_at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if now < open_dt:
                        self.render("error.html", message="El registro aún no está disponible.")
                        return
                except Exception:
                    pass
            
            if registration_close_at:
                try:
                    close_dt = datetime.strptime(registration_close_at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if now > close_dt:
                        self.render("error.html", message="El registro para este evento ha finalizado.")
                        return
                except Exception:
                    pass

        registration_fields = _get_schema_fields(event)
        self.render("register.html", event=event, error=None, registration_fields=registration_fields, form_data={})

    def post(self, slug=None):
        print(f"DEBUG: POST received for slug={slug}")
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)
        event_id = event["id"] if event else None
        print(f"DEBUG: Found event_id={event_id}")

        if not event_id:
            self.render("error.html", message="Evento no encontrado")
            return

        registration_fields = _get_schema_fields(event)
        print(f"DEBUG: Schema fields: {registration_fields}")
        
        form_data = {}
        for field in registration_fields:
            value = self.get_body_argument(field["key"], default="", strip=True)
            form_data[field["key"]] = value
            if field["required"] and not value:
                print(f"DEBUG: Missing required field {field['key']}")
                self.render("register.html", event=event, error=f"{field['label']} es obligatorio.", registration_fields=registration_fields, form_data=form_data)
                return
        
        print(f"DEBUG: Form data collected: {form_data}")

        name = form_data.get("name", "").strip()
        email = form_data.get("email", "").strip().lower() if form_data.get("email") is not None else ""
        phone = form_data.get("phone", "").strip() if form_data.get("phone") is not None else ""

        if event.get("is_deleted"):
            self.render("error.html", message="Evento no disponible")
            return

        # Check registration restrictions based on event settings
        reg_mode = event.get("registration_mode")
        restricted_type = event.get("registration_restricted_type")
        allowed_domain = event.get("allowed_domain")
        
        # Determine if we have new-style registration fields
        has_new_fields = reg_mode is not None
        
        if has_new_fields:
            # New flow: respect registration_mode setting
            status = event.get("status") or ("PUBLISHED" if event.get("is_active") else "CLOSED")
            if status == "DRAFT":
                self.render("register.html", event=event, error="El evento está en borrador.", registration_fields=registration_fields, form_data=form_data)
                return
            if status == "CLOSED":
                self.render("register.html", event=event, error="El registro ha finalizado.", registration_fields=registration_fields, form_data=form_data)
                return
            if status != "PUBLISHED":
                self.render("register.html", event=event, error="El evento no está disponible para registro.", registration_fields=registration_fields, form_data=form_data)
                return

            registration_open_at = event.get("registration_open_at")
            registration_close_at = event.get("registration_close_at")
            
            from app.db import _get_target_timezone, now_in_timezone
            tz = _get_target_timezone(event.get("timezone"))
            now = now_in_timezone(event.get("timezone"))

            if registration_open_at:
                try:
                    open_dt = datetime.strptime(registration_open_at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if now < open_dt:
                        self.render("register.html", event=event, error="El registro aún no está disponible.", registration_fields=registration_fields, form_data=form_data)
                        return
                except Exception:
                    pass

            if registration_close_at:
                try:
                    close_dt = datetime.strptime(registration_close_at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if now > close_dt:
                        self.render("register.html", event=event, error="El registro para este evento ha finalizado.", registration_fields=registration_fields, form_data=form_data)
                        return
                except Exception:
                    pass

            capacity = event.get("capacity")
            if capacity:
                try:
                    capacity_val = int(capacity)
                except Exception:
                    capacity_val = 0
                if capacity_val > 0:
                    registered_count = events_service.get_registration_count(event_id)
                    if registered_count >= capacity_val:
                        self.render("register.html", event=event, error="Cupo completo.", registration_fields=registration_fields, form_data=form_data)
                        return

            # Only apply restrictions if mode is RESTRICTED
            if reg_mode == "RESTRICTED":
                if not email:
                    self.render("register.html", event=event, error="Correo requerido para registro restringido.", registration_fields=registration_fields, form_data=form_data)
                    return
                restricted_type = restricted_type or "DOMAIN"
                email_domain = email.split("@")[-1].lower()
                if restricted_type in ("DOMAIN", "BOTH"):
                    domains = allowed_domain or "produccionesfast.com"
                    allowed_domains = [d.strip().lower().lstrip("@") for d in domains.replace(" ", ",").replace(";", ",").split(",") if d.strip()]
                    if email_domain not in allowed_domains:
                        self.render("register.html", event=event, error="Registro restringido", registration_fields=registration_fields, form_data=form_data)
                        return
                if restricted_type in ("WHITELIST", "BOTH"):
                    if not events_service.is_email_whitelisted(event_id, email):
                        self.render("register.html", event=event, error="Registro restringido", registration_fields=registration_fields, form_data=form_data)
                        return
            # If reg_mode == "OPEN", no domain/whitelist restrictions apply
        else:
            # Legacy flow: always restrict to produccionesfast.com
            if email and not email.endswith("@produccionesfast.com"):
                self.render(
                    "register.html", 
                    event=event,
                    error="Registro restringido",
                    registration_fields=registration_fields,
                    form_data=form_data
                )
                return

        if not name:
            self.render("register.html", event=event, error="Nombre es obligatorio.", registration_fields=registration_fields, form_data=form_data)
            return

        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                user = None
                if email:
                    cursor.execute(
                        "SELECT id, role FROM users WHERE email=%s AND event_id=%s",
                        (email, event_id),
                    )
                    user = cursor.fetchone()
                if user:
                    print(f"DEBUG: User already exists for email {email} and event {event_id}")
                    login_url = f"/e/{slug}/login" if slug else "/login"
                    self.redirect(f"{login_url}?email={tornado.escape.url_escape(email)}")
                    return
                else:
                    print(f"DEBUG: Creating new user for email {email} and event {event_id}")
                    # Default role is 'viewer', default password in DB is 'produccionesfast2050'
                    cursor.execute(
                        "INSERT INTO users (name, email, phone, role, event_id) VALUES (%s, %s, %s, %s, %s)",
                        (name, email or None, phone, "viewer", event_id),
                    )
                    user_id = cursor.lastrowid
                    user_role = "viewer"
                    print(f"DEBUG: New user_id: {user_id}")

                if user_id:
                    payload = json.dumps(form_data)
                    print(f"DEBUG: Saving payload for user {user_id}: {payload}")
                    cursor.execute(
                        "INSERT INTO event_registration_data (event_id, user_id, payload) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)",
                        (event_id, user_id, payload),
                    )
                else:
                    print(f"DEBUG: No user_id generated for event {event_id}")
        
        # Create Session in Redis
        session_data = {
            "user_id": user_id,
            "user_name": name,
            "user_role": user_role,
            "current_event_id": event_id
        }
        session_id = session_service.create_session(session_data)
        if not session_id:
            print("[auth] ERROR: session_id is None during registration.")
        is_https = (self.request.protocol == "https") or (self.request.headers.get("X-Forwarded-Proto") == "https")
        self.set_secure_cookie("session_id", session_id, httponly=True, secure=is_https, samesite="Lax")

        # Cleanup legacy cookies
        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")
        
        # We might kept current_event_id cookie as fallback in BaseHandler, but session has it now.
        if event_id:
            self.set_secure_cookie("current_event_id", str(event_id), httponly=True, secure=is_https, samesite="Lax")

        self.redirect(f"/e/{slug}/watch" if slug else "/watch")


class LoginHandler(BaseHandler):
    def get(self, slug=None):
        if self.current_user:
            if self.is_admin():
                self.redirect("/admin/events")
            else:
                self.redirect(f"/e/{slug}/watch" if slug else "/watch")
            return
        
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)
        if not event and slug:
            self.render("error.html", message="Evento no encontrado")
            return
            
        if event and not event["is_active"]:
            self.render("error.html", message="Este evento ya no acepta más accesos.")
            return
        
        prefill_email = self.get_query_argument("email", default="").strip().lower()
        self.render("login.html", event=event, prefill_email=prefill_email, error=None)

    def post(self, slug=None):
        email = self.get_body_argument("email", strip=True).lower()
        password = self.get_body_argument("password", default="")
        
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)

        event_id = None
        if event:
            event_id = event["id"]
        elif slug:
            # Slug was provided but no event found (should have been caught in GET, but safety first)
            event_id = None
        else:
            # Context-less login (/login). We do NOT use current_event_id() cookie here
            # to avoid filtering global staff accounts based on old navigation context.
            event_id = None
        
        if not email:
            self.render("login.html", event=event, prefill_email=email, error="El correo es obligatorio.")
            return

        # Generic password check
        if password != "produccionesfast2050":
            self.render(
                "login.html", 
                event=event,
                prefill_email=email, 
                error="Contraseña incorrecta. Use la clave generica."
            )
            return

        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                if event_id:
                    cursor.execute(
                        "SELECT id, name, password, role, event_id FROM users WHERE email=%s AND event_id=%s",
                        (email, event_id),
                    )
                    user = cursor.fetchone()

                    # Allow global staff accounts (event_id IS NULL) to log in from an event-scoped URL.
                    # Superadmin always allowed; other global users must be assigned via event_staff.
                    if not user:
                        cursor.execute(
                            "SELECT id, name, password, role, event_id FROM users WHERE email=%s AND event_id IS NULL ORDER BY created_at DESC",
                            (email,),
                        )
                        candidate = cursor.fetchone()
                        if candidate:
                            global_role = candidate.get("role")
                            if global_role in ["superadmin", "admin"]:
                                user = candidate
                            else:
                                # Check event_staff assignment
                                cursor.execute(
                                    "SELECT role FROM event_staff WHERE user_id=%s AND event_id=%s",
                                    (candidate["id"], event_id),
                                )
                                staff = cursor.fetchone()
                                if staff:
                                    user = candidate
                else:
                    # No event context: prioritize global staff accounts (event_id IS NULL)
                    cursor.execute(
                        "SELECT id, name, password, role, event_id FROM users WHERE email=%s ORDER BY (event_id IS NULL) DESC, created_at DESC",
                        (email,),
                    )
                    users = cursor.fetchall() or []
                    if not users:
                        user = None
                    elif len(users) == 1:
                        user = users[0]
                    else:
                        # Multiple users: if the first one is global, prioritize it
                        if users[0]["event_id"] is None:
                            user = users[0]
                        else:
                            # Force slug-specific login if all are event-scoped
                            user = None

        if not user:
            self.render(
                "login.html",
                event=event,
                prefill_email=email,
                error=(
                    "Cuenta no encontrada para este evento, o el correo existe en más de un evento. "
                    "Entra desde el link del evento (/e/<slug>/login)."
                ),
            )
            return

        # Validate password from DB (even if generic, it's now in the DB)
        db_password = user.get("password") or "produccionesfast2050"
        if password != db_password:
            self.render(
                "login.html", 
                event=event,
                prefill_email=email, 
                error="Contraseña incorrecta."
            )
            return

        user_id = user["id"]
        user_name = user.get("name") or "Visitante"
        user_role = user.get("role") or "viewer"
        selected_event_id = user.get("event_id") or event_id

        # If no explicit event context, try to find one from staff assignments
        # This is critical for Global Moderators/Speakers who log in from /login
        if not selected_event_id:
            with create_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT event_id FROM event_staff WHERE user_id=%s LIMIT 1",
                        (user_id,)
                    )
                    assignment = cursor.fetchone()
                    if assignment:
                        selected_event_id = assignment["event_id"]

        # Resolve per-event staff role (if any) to decide redirects later.
        staff_role = None
        if selected_event_id:
            try:
                from app.services import staff_service
                staff_role = staff_service.get_event_role(int(user_id), int(selected_event_id))
            except Exception:
                staff_role = None

        # Create Session
        session_data = {
            "user_id": user_id,
            "user_name": user_name,
            "user_role": user_role,
            "current_event_id": selected_event_id
        }
        session_id = session_service.create_session(session_data)
        if not session_id:
            print("[auth] ERROR: session_id is None during login.")
        is_https = (self.request.protocol == "https") or (self.request.headers.get("X-Forwarded-Proto") == "https")
        self.set_secure_cookie("session_id", session_id, httponly=True, secure=is_https, samesite="Lax")

        # Cleanup legacy cookies
        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")

        # Keep event context consistent for the session.
        if selected_event_id:
            self.set_secure_cookie("current_event_id", str(selected_event_id), httponly=True, secure=is_https, samesite="Lax")
            
            # If we didn't have a slug (global login) but found an event, fetch its slug for nicer redirects
            if not slug:
                try:
                     from app.services import events_service
                     evt = events_service.get_event_by_id(selected_event_id)
                     if evt:
                         slug = evt.get("slug")
                except Exception:
                    pass
        
        # Smart redirect based on role
        if user_role in ["superadmin", "admin"]:
            self.redirect("/admin/events")
            return

        # Staff assignment takes priority
        if staff_role == "admin":
            self.redirect("/admin/events")
            return
        if staff_role == "speaker":
            self.redirect(f"/e/{slug}/speaker" if slug else "/speaker")
            return
        if staff_role == "moderator":
            self.redirect(f"/e/{slug}/mod" if slug else "/mod")
            return

        # Fallback to users.role (per-event accounts)
        if user_role == "admin":
            self.redirect("/admin/events")
            return
        if user_role == "speaker":
            self.redirect(f"/e/{slug}/speaker" if slug else "/speaker")
            return
        if user_role in ["moderator", "moderador"]:
            self.redirect(f"/e/{slug}/mod" if slug else "/mod")
            return

        self.redirect(f"/e/{slug}/watch" if slug else "/watch")


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id = self.get_current_user()
        if user_id:
            analytics_service.mark_session_inactive(user_id)
        
        # Determine smart redirect before clearing session
        redirect_url = "/"
        user_role = self.current_user_role()
        event_id = self.current_event_id()
        
        # Invalidate session in Redis
        s_cookie = self.get_secure_cookie("session_id")
        if s_cookie:
            session_service.delete_session(s_cookie.decode())

        self.clear_cookie("session_id")
        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")
        
        # Staff (Global or Event-Level) -> Global Login
        # Viewers -> Event Login (if event context exists)
        if user_role == "viewer" and event_id:
            try:
                from app.services import events_service
                evt = events_service.get_event_by_id(event_id)
                if evt and evt.get("slug"):
                    redirect_url = f"/e/{evt['slug']}/login"
            except Exception:
                pass
        
        self.redirect(redirect_url)
