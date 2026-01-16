import tornado.escape

from app.db import create_db_connection
from app.handlers.base import BaseHandler
from app.services import analytics_service, session_service


class RegistrationHandler(BaseHandler):
    def get(self, slug=None):
        if self.current_user:
            self.redirect(f"/e/{slug}/watch" if slug else "/watch")
            return
        
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)
        if not event:
            self.render("error.html", message="Evento no encontrado")
            return
            
        if not event["is_active"]:
            self.render("error.html", message="El registro para este evento ha finalizado.")
            return

        self.render("register.html", event=event, error=None)

    def post(self, slug=None):
        name = self.get_body_argument("name", strip=True)
        email = self.get_body_argument("email", strip=True).lower()
        phone = self.get_body_argument("phone", strip=True)
        
        from app.services import events_service
        event = events_service.get_event_by_slug(slug)
        event_id = event["id"] if event else None

        if not event_id:
            self.render("error.html", message="Evento no encontrado")
            return

        if not (name and email):
            self.render("register.html", event=event, error="Nombre y correo son obligatorios.")
            return

        # Restricted domain check
        if not email.endswith("@produccionesfast.com"):
            self.render(
                "register.html", 
                event=event,
                error="Registro restringido"
            )
            return

        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, role FROM users WHERE email=%s AND event_id=%s",
                    (email, event_id),
                )
                user = cursor.fetchone()
                if user:
                    login_url = f"/e/{slug}/login" if slug else "/login"
                    self.redirect(f"{login_url}?email={tornado.escape.url_escape(email)}")
                    return
                else:
                    # Default role is 'visor', default password in DB is 'produccionesfast2050'
                    cursor.execute(
                        "INSERT INTO users (name, email, phone, role, event_id) VALUES (%s, %s, %s, %s, %s)",
                        (name, email, phone, "visor", event_id),
                    )
                    user_id = cursor.lastrowid
                    user_role = "visor"
        
        # Create Session in Redis
        session_data = {
            "user_id": user_id,
            "user_name": name,
            "user_role": user_role,
            "current_event_id": event_id
        }
        session_id = session_service.create_session(session_data)
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
        else:
            # If no slug, try cookie context. If still missing, login may be ambiguous.
            event_id = self.current_event_id()
        
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

                    # Allow a global admin (event_id IS NULL) to log in from an event-scoped URL.
                    if not user:
                        cursor.execute(
                            "SELECT id, name, password, role, event_id FROM users WHERE email=%s AND event_id IS NULL ORDER BY created_at DESC",
                            (email,),
                        )
                        candidate = cursor.fetchone()
                        if candidate and (candidate.get("role") == "administrador"):
                            user = candidate
                else:
                    # No event context: if there are multiple event-scoped users with the same email,
                    # force using the event-specific login URL (/e/{slug}/login).
                    cursor.execute(
                        "SELECT id, name, password, role, event_id FROM users WHERE email=%s ORDER BY created_at DESC",
                        (email,),
                    )
                    users = cursor.fetchall() or []
                    if len(users) == 1:
                        user = users[0]
                    else:
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
        user_role = user.get("role") or "visor"
        selected_event_id = user.get("event_id") or event_id

        # Create Session
        session_data = {
            "user_id": user_id,
            "user_name": user_name,
            "user_role": user_role,
            "current_event_id": selected_event_id
        }
        session_id = session_service.create_session(session_data)
        is_https = (self.request.protocol == "https") or (self.request.headers.get("X-Forwarded-Proto") == "https")
        self.set_secure_cookie("session_id", session_id, httponly=True, secure=is_https, samesite="Lax")

        # Cleanup legacy cookies
        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")

        # Keep event context consistent for the session.
        if selected_event_id:
            self.set_secure_cookie("current_event_id", str(selected_event_id), httponly=True, secure=is_https, samesite="Lax")
        
        # Smart redirect based on role
        if user_role == "administrador":
            self.redirect("/admin/events")
        elif user_role == "speaker":
            self.redirect(f"/e/{slug}/speaker" if slug else "/speaker")
        elif user_role == "moderador":
            self.redirect(f"/e/{slug}/mod" if slug else "/mod")
        else:
            self.redirect(f"/e/{slug}/watch" if slug else "/watch")


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id = self.get_current_user()
        if user_id:
            analytics_service.mark_session_inactive(user_id)
        
        # Invalidate session in Redis
        s_cookie = self.get_secure_cookie("session_id")
        if s_cookie:
            session_service.delete_session(s_cookie.decode())

        self.clear_cookie("session_id")
        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")
        self.redirect("/")
