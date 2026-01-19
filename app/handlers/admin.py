import json
import tornado.web
from app.handlers.base import BaseHandler
from app.services import events_service

class EventsAdminHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        if not self.is_moderator():
            self.redirect("/watch")
            return
        
        events = events_service.list_events()
        self.render("admin/events.html", events=events)

class APIEventsHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        if not self.is_admin():
            self.set_status(403)
            return
        
        try:
            data = json.loads(self.request.body)
            slug = data.get("slug")
            title = data.get("title")
            logo_url = data.get("logo_url")
            video_url = data.get("video_url")
            theme_color = data.get("theme_color")
            header_bg_color = data.get("header_bg_color")
            header_text_color = data.get("header_text_color")
            body_bg_color = data.get("body_bg_color")
            body_text_color = data.get("body_text_color")
            
            if not slug or not title:
                self.set_status(400)
                self.write({"status": "error", "message": "Slug and Title are required"})
                return
            
            event_id = events_service.create_event(slug, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color)
            self.write({"status": "success", "event_id": event_id})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})

    @tornado.web.authenticated
    def put(self):
        if not self.is_admin():
            self.set_status(403)
            return
        
        try:
            data = json.loads(self.request.body)
            event_id = data.get("id")
            title = data.get("title")
            logo_url = data.get("logo_url")
            video_url = data.get("video_url")
            theme_color = data.get("theme_color")
            header_bg_color = data.get("header_bg_color")
            header_text_color = data.get("header_text_color")
            body_bg_color = data.get("body_bg_color")
            body_text_color = data.get("body_text_color")
            is_active = data.get("is_active")
            
            events_service.update_event(event_id, title, logo_url, video_url, theme_color, header_bg_color, header_text_color, body_bg_color, body_text_color, is_active)
            
            # If the event was closed, kick all users
            if not is_active:
                from app.handlers import ws
                ws.kick_all_from_event(event_id)

            self.write({"status": "success"})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})
