import tornado.web

from app.handlers.base import BaseHandler
from app.services import chat_service, questions_service


class WatchHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, slug=None):
        from app.services import events_service
        event = None
        if slug:
            event = events_service.get_event_by_slug(slug)
        
        # Fallback to current session event if no slug but has cookie
        if not event and self.current_event_id():
            event = events_service.get_event_by_id(self.current_event_id())

        if not event:
            # If no event found, show a placeholder or redirect to events list if admin
            if self.is_admin():
                self.redirect("/admin/events")
            else:
                self.render("error.html", message="Evento no encontrado")
            return

        # Check if event is active (allow staff even if paused?)
        # Let's say Visors cannot enter if paused, but staff can.
        if not event["is_active"] and not self.is_moderator():
            self.render("error.html", message="Esta transmisión ha finalizado.")
            return

        event_id = event["id"]
        chats = chat_service.list_recent_chats(event_id=event_id)
        questions = questions_service.list_questions(status="approved", event_id=event_id)
        
        self.render(
            "watch.html",
            event=event,
            user_id=self.get_current_user(),
            user_name=self.current_user_name(),
            chats=chats,
            approved_questions=questions,
            ws_url=f"{self.get_ws_scheme()}://{self.request.host}/ws?role=viewer&event_id={event_id}",
        )
