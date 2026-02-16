import json
import os
import tornado.web
from datetime import datetime

from app.handlers.base import BaseHandler
from app.services import analytics_service, chat_service, questions_service


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

        event_id = event["id"]

        if event.get("is_deleted"):
            self.render("error.html", message="Evento no disponible")
            return

        if os.getenv("EVENT_FLOW_V2", "1") == "1":
            status = event.get("status") or ("PUBLISHED" if event.get("is_active") else "CLOSED")
            is_staff = self.is_moderator_for_event(event_id) or self.is_admin() or self.is_superadmin()
            
            if status == "DRAFT" and not is_staff:
                self.render("error.html", message="El evento no está disponible aún (Borrador).")
                return
                
            if status == "CLOSED" and not is_staff:
                self.render("error.html", message="Este evento ha finalizado.")
                return

            if status != "PUBLISHED" and not is_staff:
                self.render("error.html", message="El evento no está disponible aún.")
                return

            access_open_at = event.get("access_open_at")
            if access_open_at and not is_staff:
                try:
                    from app.db import _get_target_timezone, now_in_timezone
                    tz = _get_target_timezone(event.get("timezone"))
                    access_dt = datetime.strptime(access_open_at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if now_in_timezone(event.get("timezone")) < access_dt:
                        # Show the waiting success message instead of a generic error
                        self.render("waiting.html", event=event)
                        return
                except Exception:
                    pass

        # Check if event is active (allow staff even if paused?)
        # Let's say Viewers cannot enter if paused, but staff can.
        is_staff = self.is_moderator_for_event(event_id) or self.is_admin() or self.is_superadmin()
        if not event["is_active"] and not is_staff:
            self.render("error.html", message="Esta transmisión ha finalizado.")
            return

        # Mark viewer as active even if WebSocket can't connect (fallback).
        user_id = self.get_current_user()
        if user_id:
            analytics_service.ensure_session_analytics(user_id, event_id=event_id)

        chats = None
        questions = None
        from app.config import WATCH_CACHE_TTL_SECONDS
        try:
            from app.services.redis_cache import get_redis_cache
            r = get_redis_cache()
            if r and WATCH_CACHE_TTL_SECONDS > 0:
                key = f"watch:event:{event_id}"
                raw = r.get(key)
                if raw:
                    data = json.loads(raw)
                    chats = data.get("chats") or []
                    questions = data.get("questions") or []
        except Exception:
            pass
        if chats is None:
            chats = chat_service.list_recent_chats(event_id=event_id)
            questions = questions_service.list_questions(status="approved", event_id=event_id)
            try:
                from app.services.redis_cache import get_redis_cache
                r = get_redis_cache()
                if r and WATCH_CACHE_TTL_SECONDS > 0:
                    key = f"watch:event:{event_id}"
                    payload = {"chats": chats, "questions": questions}
                    r.setex(key, WATCH_CACHE_TTL_SECONDS, json.dumps(payload, default=str))
            except Exception:
                pass

        self.render(
            "watch.html",
            event=event,
            user_id=user_id,
            user_name=self.current_user_name(),
            chats=chats,
            approved_questions=questions,
            ws_url=f"{self.get_ws_scheme()}://{self.request.host}/ws?role=viewer&event_id={event_id}",
        )


class APIPingHandler(BaseHandler):
    """HTTP fallback heartbeat to keep sessions marked as active."""

    # Remove @authenticated decorator to prevent 302 Redirect on session expiry
    # We want a clean 401 for the JS fetch to detect.
    def post(self):
        # Manual check
        user_id = self.get_current_user()
        if not user_id:
            self.set_status(401)
            self.write({"error": "session_expired"})
            return

        try:
            event_id = int(self.get_argument("event_id"))
        except (TypeError, ValueError, tornado.web.MissingArgumentError):
            event_id = self.current_event_id()

        analytics_service.record_ping(user_id, event_id=event_id)
        self.write({"ok": True})
