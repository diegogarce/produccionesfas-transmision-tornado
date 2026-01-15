import json
from datetime import datetime
import traceback

import tornado.websocket

from app.services import analytics_service, chat_service, questions_service, users_service

WEBSOCKET_CLIENTS = {"viewer": set(), "moderator": set(), "speaker": set()}


def push_reports_snapshot(event_id=None):
    try:
        # 1. Historical data (all registered/seen participants) for the Reports view
        all_participants = analytics_service.list_all_participants_for_report(event_id=event_id)
        broadcast({"type": "active_sessions", "sessions": all_participants}, roles={"reports"}, event_id=event_id)
        
        # 2. Truly active sessions (live viewers) for the Moderator view
        active_viewers = analytics_service.list_active_sessions_for_report(event_id=event_id)
        broadcast({"type": "active_sessions", "sessions": active_viewers}, roles={"moderator"}, event_id=event_id)
        
    except Exception as exc:
        print(f"[WS] ! Error building reports snapshot: {exc}")
        traceback.print_exc()
        return

def kick_all_from_event(event_id):
    """Forcefully disconnect all clients from a closed event."""
    text = json.dumps({"type": "event_closed", "message": "Esta transmisión ha finalizado."})
    target_roles = ["viewer", "moderator", "speaker", "reports"]
    
    for role in target_roles:
        clients = list(WEBSOCKET_CLIENTS.get(role, []))
        for client in clients:
            if getattr(client, "event_id", None) == event_id:
                try:
                    client.write_message(text)
                    client.close()
                except:
                    pass
                WEBSOCKET_CLIENTS[role].discard(client)


def broadcast(payload, roles=None, event_id=None):
    text = json.dumps(payload)
    target_roles = roles if roles else WEBSOCKET_CLIENTS.keys()
    
    sent_count = 0
    for role in target_roles:
        clients = list(WEBSOCKET_CLIENTS.get(role, []))
        for client in clients:
            # Filter by event_id if provided
            if event_id is not None and getattr(client, "event_id", None) != event_id:
                continue
            
            try:
                client.write_message(text)
                sent_count += 1
            except tornado.websocket.WebSocketClosedError:
                WEBSOCKET_CLIENTS[role].discard(client)
    
    print(f"[WS] ✓ Enviado a {sent_count} clientes")


class LiveWebSocket(tornado.websocket.WebSocketHandler):
    def allow_draft76(self):
        return True

    def open(self):
        secure_id = self.get_secure_cookie("user_id")
        if not secure_id:
            self.close()
            return
        try:
            self.user_id = int(secure_id.decode())
        except (AttributeError, ValueError):
            self.close()
            return

        self.user_name = (self.get_secure_cookie("user_name") or b"Guest").decode()
        self.role = self.get_query_argument("role", "viewer")
        arg_event = self.get_query_argument("event_id", default=None)
        try:
            self.event_id = int(arg_event) if arg_event else None
        except (TypeError, ValueError):
            self.event_id = None

        WEBSOCKET_CLIENTS.setdefault(self.role, set()).add(self)
        
        # Track session analytics only for viewers
        if self.role == "viewer":
            analytics_service.ensure_session_analytics(self.user_id, event_id=self.event_id)
        
        # Push update to everyone interested (moderators/reports)
        push_reports_snapshot(event_id=self.event_id)
        
        print(f"[WS] ✓ Conectado: {self.role} | user_id={self.user_id} | event_id={self.event_id}")

    def on_close(self):
        WEBSOCKET_CLIENTS.get(self.role, set()).discard(self)
        if getattr(self, "role", None) == "viewer" and getattr(self, "user_id", None) is not None:
            analytics_service.mark_session_inactive(self.user_id)
            push_reports_snapshot(event_id=self.event_id)
        print(f"[WS] ✗ Desconectado: {self.role} | user_id={self.user_id} | event_id={self.event_id}")

    def on_message(self, message):
        try:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return

            msg_type = payload.get("type")
            print(f"[WS] {self.role} | Mensaje: {msg_type} | Payload: {payload}")

            if msg_type == "chat":
                if users_service.is_chat_blocked(self.user_id):
                    self.write_message(json.dumps({"type": "error", "message": "Tu acceso al chat ha sido restringido."}))
                    return
                text = payload.get("message", "").strip()
                if not text:
                    return
                chat_payload = chat_service.add_chat_message(self.user_id, self.user_name, text, event_id=self.event_id)
                broadcast({"type": "chat", **chat_payload, "timestamp": datetime.now().strftime("%H:%M")}, event_id=self.event_id)

            elif msg_type == "ask":
                if users_service.is_qa_blocked(self.user_id):
                    self.write_message(json.dumps({"type": "error", "message": "Tu acceso a preguntas ha sido restringido."}))
                    return
                question = payload.get("question", "").strip()
                manual_user = payload.get("manual_user", "").strip()
                if not question:
                    return
                
                # Use manual_user if provided (for external questions like WhatsApp)
                display_name = manual_user if manual_user else self.user_name
                
                question_payload = questions_service.add_question(self.user_id, display_name, question, event_id=self.event_id)
                broadcast({"type": "pending_question", **question_payload}, roles={"moderator"}, event_id=self.event_id)

            elif msg_type == "approve" and self.role == "moderator":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                approved_payload = questions_service.approve_question(question_id)
                if approved_payload:
                    broadcast({"type": "approved_question", **approved_payload}, roles={"viewer", "speaker", "moderator"}, event_id=self.event_id)

            elif msg_type == "reject" and self.role == "moderator":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                questions_service.reject_question(question_id)
                broadcast({"type": "rejected_question", "id": question_id}, roles={"moderator"}, event_id=self.event_id)

            elif msg_type == "read" and self.role == "speaker":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                questions_service.mark_question_as_read(question_id)
                broadcast({"type": "question_read", "id": question_id}, roles={"viewer", "speaker", "moderator"}, event_id=self.event_id)

            elif msg_type == "return_to_moderator" and self.role == "speaker":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                returned_payload = questions_service.return_question_to_pending(question_id)
                if returned_payload:
                    # Remove it from the "Approved/Speaker" view for everyone
                    broadcast({"type": "question_removed", "id": question_id}, roles={"viewer", "speaker", "moderator"}, event_id=self.event_id)
                    # Re-add it to the Moderator's "Pending" queue
                    broadcast({"type": "pending_question", **returned_payload}, roles={"moderator"}, event_id=self.event_id)

            elif msg_type == "ping":
                analytics_service.record_ping(self.user_id, event_id=self.event_id)
                push_reports_snapshot(event_id=self.event_id)

        except Exception:
            traceback.print_exc()

    def check_origin(self, origin):
        return True
