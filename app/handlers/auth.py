import tornado.escape

from app.db import create_db_connection
from app.handlers.base import BaseHandler
from app.services import analytics_service


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
                cursor.execute("SELECT id, role FROM users WHERE email=%s", (email,))
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
        self.set_secure_cookie("user_id", str(user_id))
        self.set_secure_cookie("user_name", name)
        self.set_secure_cookie("user_role", user_role)
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
                cursor.execute("SELECT id, name, password, role FROM users WHERE email=%s", (email,))
                user = cursor.fetchone()

        if not user:
            self.render(
                "login.html",
                event=event,
                prefill_email=email,
                error="No encontramos ese correo. Regístrate primero.",
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
        
        self.set_secure_cookie("user_id", str(user_id))
        self.set_secure_cookie("user_name", user_name)
        self.set_secure_cookie("user_role", user_role)
        
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

        self.clear_cookie("user_id")
        self.clear_cookie("user_name")
        self.clear_cookie("user_role")
        self.redirect("/")
