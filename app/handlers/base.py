import tornado.web
from app.services import session_service


class BaseHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.session = None

    def get_current_user(self):
        if self.session is None:
            self._load_session()
        return self.session.get("user_id") if self.session else None

    def _load_session(self):
        self.session = None
        s_cookie = self.get_secure_cookie("session_id")
        if s_cookie:
            try:
                self.session = session_service.get_session(s_cookie.decode())
            except Exception:
                self.session = None

    def current_user_name(self):
        if self.session is None: self._load_session()
        return self.session.get("user_name") if self.session else "Visitante"

    def prepare(self):
        # Determine event context from URL
        # URL format: /e/SLUG/...
        path_parts = self.request.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "e":
            from app.services import events_service
            slug = path_parts[1]
            event = events_service.get_event_by_slug(slug)
            if event:
                self.set_secure_cookie("current_event_id", str(event["id"]))
            elif not path_parts[1].startswith("{"): # Ignore if it looks like a regex/placeholder
                 pass

        # Load session early
        self._load_session()

        # Global check for banned users
        user_id = self.get_current_user()
        if user_id:
            from app.services import users_service
            if users_service.is_user_banned(user_id):
                # Clear session
                if self.session:
                     s_cookie = self.get_secure_cookie("session_id")
                     if s_cookie: session_service.delete_session(s_cookie.decode())
                
                self.clear_cookie("session_id")
                self.clear_cookie("user_id")
                self.clear_cookie("user_name")
                self.clear_cookie("user_role")
                self.redirect("/login?error=" + tornado.escape.url_escape("Tu cuenta ha sido suspendida."))
                return

    def current_event_id(self):
        # Priority 1: Session (Logged in user context)
        if self.session is None: self._load_session()
        if self.session and self.session.get("current_event_id"):
             return int(self.session.get("current_event_id"))
        
        # Priority 2: Cookie context (Implicit navigation context)
        eid = self.get_secure_cookie("current_event_id")
        return int(eid.decode()) if eid else None

    def current_user_role(self):
        if self.session is None: self._load_session()
        return self.session.get("user_role") if self.session else "visor"

    def is_chat_blocked(self):
        user_id = self.get_current_user()
        if not user_id: return False
        from app.services import users_service
        return users_service.is_chat_blocked(user_id)

    def is_qa_blocked(self):
        user_id = self.get_current_user()
        if not user_id: return False
        from app.services import users_service
        return users_service.is_qa_blocked(user_id)

    def is_admin(self):
        return self.current_user_role() == "administrador"

    def is_speaker(self):
        return self.current_user_role() in ["speaker", "administrador"]

    def is_moderator(self):
        return self.current_user_role() in ["moderador", "administrador"]

    def get_ws_scheme(self):
        # Detect if we are in HTTPS via direct protocol or proxy header
        if self.request.protocol == "https" or self.request.headers.get("X-Forwarded-Proto") == "https":
            return "wss"
        return "ws"
