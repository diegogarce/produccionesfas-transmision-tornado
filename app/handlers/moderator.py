import json
import tornado.web

from app.handlers.base import BaseHandler
from app.services import analytics_service, chat_service, questions_service


class ModeratorHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, slug=None):
        if not self.is_moderator():
            self.redirect("/watch")
            return
        
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
        
        # Fetch initial data for SSR
        pending = questions_service.list_questions(status="pending", event_id=event_id)
        approved = questions_service.list_questions(status="approved", event_id=event_id)
        read_questions = questions_service.list_questions(status="read", event_id=event_id)
        chats = chat_service.list_recent_chats(limit=50, event_id=event_id)
        # Fix: use list_active_sessions_for_report instead of nonexistent list_active_participants_for_report
        participants = analytics_service.list_active_sessions_for_report(event_id=event_id)

        self.render(
            "moderator.html",
            event=event,
            user_name=self.current_user_name(),
            pending_questions=pending,
            approved_questions=approved,
            read_questions=read_questions,
            chat_messages=chats,
            participants=participants,
            ws_url=f"{self.get_ws_scheme()}://{self.request.host}/ws?role=moderator&event_id={event_id}",
        )


class APIQuestionsHandler(BaseHandler):
    """API endpoint to fetch pending and approved questions"""

    @tornado.web.authenticated
    def get(self):
        try:
            event_id = int(self.get_argument("event_id"))
        except (TypeError, ValueError, tornado.web.MissingArgumentError):
            event_id = self.current_event_id()

        payload = questions_service.list_pending_and_approved(limit=50, event_id=event_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(payload, default=str))


class APIParticipantsHandler(BaseHandler):
    """API endpoint to fetch currently connected participants (viewers)."""

    @tornado.web.authenticated
    def get(self):
        try:
            event_id = int(self.get_argument("event_id"))
        except (TypeError, ValueError, tornado.web.MissingArgumentError):
            event_id = self.current_event_id()

        # Fix: use list_active_sessions_for_report instead of nonexistent list_active_participants_for_report
        participants = analytics_service.list_active_sessions_for_report(event_id=event_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(participants, default=str))


class APIChatsHandler(BaseHandler):
    """API endpoint to fetch recent chat messages"""

    @tornado.web.authenticated
    def get(self):
        try:
            event_id = int(self.get_argument("event_id"))
        except (TypeError, ValueError, tornado.web.MissingArgumentError):
            event_id = self.current_event_id()

        chats = chat_service.list_recent_chats(limit=50, event_id=event_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(chats, default=str))


class APIUserStatusHandler(BaseHandler):
    """API endpoint to update user status (chat block, QA block, ban)."""

    @tornado.web.authenticated
    def post(self):
        if not self.is_admin():
            self.set_status(403)
            return

        from app.services import users_service
        try:
            data = json.loads(self.request.body)
            user_id = int(data.get("user_id"))
            field = data.get("field")  # chat_blocked, qa_blocked, banned
            value = bool(data.get("value"))

            success = users_service.update_user_status(user_id, field, value)
            if success:
                # Trigger a refresh of active sessions for all reports/moderators
                from app.handlers import ws
                ws.push_reports_snapshot()
                
                # If banned, we might want to notify via WS to force kick (future enhancement)
                if field == "banned" and value:
                    ws.broadcast({"type": "force_logout", "user_id": user_id})

                self.write({"status": "success"})
            else:
                self.set_status(400)
                self.write({"status": "error", "message": "Invalid field"})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})
