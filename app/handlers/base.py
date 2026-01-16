import tornado.web


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        secure_id = self.get_secure_cookie("user_id")
        if not secure_id:
            return None
        try:
            return int(secure_id.decode())
        except (ValueError, AttributeError):
            return None

    def current_user_name(self):
        name = self.get_secure_cookie("user_name")
        return name.decode() if name else "Visitante"

    def prepare(self):
        # Detect event context from URL
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

        # Global check for banned users
        user_id = self.get_current_user()
        if user_id:
            from app.services import users_service
            if users_service.is_user_banned(user_id):
                self.clear_cookie("user_id")
                self.clear_cookie("user_name")
                self.clear_cookie("user_role")
                self.redirect("/login?error=" + tornado.escape.url_escape("Tu cuenta ha sido suspendida."))
                return

    def current_event_id(self):
        eid = self.get_secure_cookie("current_event_id")
        return int(eid.decode()) if eid else None

    def current_user_role(self):
        role = self.get_secure_cookie("user_role")
        return role.decode() if role else "visor"

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
