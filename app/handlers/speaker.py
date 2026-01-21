import tornado.web

from app.handlers.base import BaseHandler
from app.services import questions_service


class SpeakerHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, slug=None):
        from app.services import events_service
        event = None
        if slug:
            event = events_service.get_event_by_slug(slug)
            
        if not event and self.current_event_id():
            event = events_service.get_event_by_id(self.current_event_id())
            
        if not event:
            self.redirect("/admin/events")
            return

        event_id = event["id"]
        if not self.is_speaker_for_event(event_id):
            self.redirect(f"/e/{slug}/watch" if slug else "/watch")
            return
        approved = questions_service.list_questions(status="approved", event_id=event_id)
        self.render(
            "speaker.html",
            event=event,
            user_name=self.current_user_name(),
            approved_questions=approved,
            ws_url=f"{self.get_ws_scheme()}://{self.request.host}/ws?role=speaker&event_id={event_id}",
        )
