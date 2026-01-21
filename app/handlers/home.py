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

        from app.services import events_service

        events = events_service.list_events() or []
        active_events = [e for e in events if e.get("is_active")]

        # If there's exactly one active event, go straight to its registration.
        if len(active_events) == 1:
            self.redirect(f"/e/{active_events[0]['slug']}/")
            return

        self.render("events.html", events=active_events)
