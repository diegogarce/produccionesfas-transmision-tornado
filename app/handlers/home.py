import tornado.web

from app.handlers.base import BaseHandler


class HomeHandler(BaseHandler):
    def get(self):
        # If user already has a session, try to keep them in the same event context.
        if self.current_user:
            from app.services import events_service

            if self.is_admin():
                self.redirect("/admin/events")
                return

            event_id = self.current_event_id()
            if event_id:
                event = events_service.get_event_by_id(event_id)
                if event and event.get("slug"):
                    self.redirect(f"/e/{event['slug']}/watch")
                    return

            self.redirect("/watch")
            return

        # Redirect directly to login, skipping the event list page.
        self.redirect("/login")
