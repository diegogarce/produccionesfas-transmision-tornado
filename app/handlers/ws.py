import json
import threading
from datetime import datetime
import traceback

import tornado.websocket

from app.db import now_hhmm_in_timezone
from app.services import analytics_service, chat_service, questions_service, users_service
from app.services import session_service
from app.services import events_service, poll_service
from app import metrics
from app.services import message_validation_service

# Keep per-role client pools. Reports is a first-class role.
WEBSOCKET_CLIENTS = {"viewer": set(), "moderator": set(), "speaker": set(), "reports": set()}

# Best-effort auto-close timers for timed polls (per event/poll).
_poll_auto_close_lock = threading.Lock()
_poll_auto_close_handles = {}


def _schedule_poll_auto_close(event_id: int, poll_id: int, close_at_str: str | None):
    if not event_id or not poll_id or not close_at_str:
        return
    try:
        close_at = datetime.strptime(str(close_at_str), "%Y-%m-%d %H:%M:%S")
        delay = max(0.0, (close_at - datetime.utcnow()).total_seconds())
    except Exception:
        return

    key = (int(event_id), int(poll_id))
    from tornado.ioloop import IOLoop

    def _do_close_if_still_active():
        # Drop handle reference first to avoid leaks.
        with _poll_auto_close_lock:
            _poll_auto_close_handles.pop(key, None)

        # Only close if the same poll is still live.
        try:
            from app.services.redis_cache import get_redis_cache
            r = get_redis_cache()
            if not r:
                return
            live_json = r.get(f"poll:live:{event_id}")
            if not live_json:
                return
            live_data = json.loads(live_json)
            if int(live_data.get("poll_id") or 0) != int(poll_id):
                return
        except Exception:
            return

        try:
            res = poll_service.close_poll(event_id)
            if res:
                broadcast({"type": "poll_end", "final_results": res}, event_id=event_id)
        except Exception:
            traceback.print_exc()

    with _poll_auto_close_lock:
        old = _poll_auto_close_handles.get(key)
        try:
            if old is not None:
                old.cancel()
        except Exception:
            pass
        _poll_auto_close_handles[key] = IOLoop.current().call_later(delay, _do_close_if_still_active)

# Fase C: Redis Pub/Sub para broadcast entre instancias
_pubsub_subscribed_events = set()
_pubsub_lock = threading.Lock()
_pubsub_listener_started = False
_ioloop_for_pubsub = None
_pubsub_current_subscriptions = set()


def _run_pubsub_listener():
    global _pubsub_listener_started
    try:
        from app.config import REDIS_CONFIG
        import redis
        redis_sub = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=3,
            decode_responses=True,
        )
        pubsub = redis_sub.pubsub()
        while True:
            with _pubsub_lock:
                to_sub = list(_pubsub_subscribed_events)
            for eid in to_sub:
                ch = f"broadcast:event:{eid}"
                if eid not in _pubsub_current_subscriptions:
                    try:
                        pubsub.subscribe(ch)
                        _pubsub_current_subscriptions.add(eid)
                    except Exception:
                        pass
            for eid in list(_pubsub_current_subscriptions):
                if eid not in _pubsub_subscribed_events:
                    try:
                        pubsub.unsubscribe(f"broadcast:event:{eid}")
                        _pubsub_current_subscriptions.discard(eid)
                    except Exception:
                        pass
            msg = pubsub.get_message(timeout=0.5)
            if msg and msg.get("type") == "message":
                try:
                    data = json.loads(msg.get("data") or "{}")
                    event_id = data.get("event_id")
                    roles = data.get("roles")
                    payload = data.get("payload")
                    if event_id is not None and payload is not None and _ioloop_for_pubsub:
                        _ioloop_for_pubsub.add_callback(
                            _local_broadcast, payload, roles=roles, event_id=event_id
                        )
                except Exception:
                    pass
    except Exception as e:
        print(f"[WS] Pub/Sub listener error: {e}")
    finally:
        _pubsub_listener_started = False


def _ensure_pubsub_subscribe(event_id):
    global _ioloop_for_pubsub, _pubsub_listener_started
    from app.config import BROADCAST_PUBSUB
    if not BROADCAST_PUBSUB or event_id is None:
        return
    with _pubsub_lock:
        _pubsub_subscribed_events.add(event_id)
        if _ioloop_for_pubsub is None:
            _ioloop_for_pubsub = tornado.ioloop.IOLoop.current()
        if not _pubsub_listener_started:
            _pubsub_listener_started = True
            t = threading.Thread(target=_run_pubsub_listener, daemon=True)
            t.start()


def _ensure_pubsub_unsubscribe(event_id):
    if event_id is None:
        return
    has_clients = any(
        getattr(c, "event_id", None) == event_id
        for clients in WEBSOCKET_CLIENTS.values()
        for c in clients
    )
    if not has_clients:
        with _pubsub_lock:
            _pubsub_subscribed_events.discard(event_id)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def push_reports_snapshot(event_id=None):
    try:
        if event_id is None:
            event_ids = set()
            for clients in WEBSOCKET_CLIENTS.values():
                for client in list(clients):
                    eid = getattr(client, "event_id", None)
                    if eid is not None:
                        event_ids.add(eid)
            for eid in sorted(event_ids):
                push_reports_snapshot(event_id=eid)
            return

        from app.config import REPORTS_CACHE_TTL_SECONDS
        cache_key = f"reports:snapshot:{event_id}"
        try:
            from app.services.redis_cache import get_redis_cache
            r = get_redis_cache()
            if r and REPORTS_CACHE_TTL_SECONDS > 0:
                raw = r.get(cache_key)
                if raw:
                    cached = json.loads(raw)
                    active_viewers = cached.get("active_sessions") or []
                    total_registered_users = cached.get("total_registered_users", 0)
                    live_watchers_count = cached.get("live_watchers_count", 0)
                    total_minutes_consumed = cached.get("total_minutes_consumed", 0)
                    charts_payload = cached.get("charts") or {}
                    broadcast({"type": "active_sessions", "sessions": active_viewers}, roles={"reports"}, event_id=event_id)
                    broadcast({"type": "active_sessions", "sessions": active_viewers}, roles={"moderator"}, event_id=event_id)
                    broadcast(
                        {
                            "type": "reports_metrics",
                            "total_registered_users": total_registered_users,
                            "live_watchers_count": live_watchers_count,
                            "total_minutes_consumed": total_minutes_consumed,
                        },
                        roles={"reports"},
                        event_id=event_id,
                    )
                    broadcast({"type": "reports_charts", **charts_payload}, roles={"reports"}, event_id=event_id)
                    return
        except Exception:
            pass

        active_viewers = analytics_service.list_active_sessions_for_report(event_id=event_id)
        broadcast({"type": "active_sessions", "sessions": active_viewers}, roles={"reports"}, event_id=event_id)
        broadcast({"type": "active_sessions", "sessions": active_viewers}, roles={"moderator"}, event_id=event_id)

        all_participants = analytics_service.list_all_participants_for_report(event_id=event_id)
        registered_users = analytics_service.list_registered_users(event_id=event_id)
        total_registered_users = len(registered_users or [])
        live_watchers_count = len(active_viewers or [])
        total_minutes_consumed = sum(_safe_int(row.get("session_minutes")) for row in (all_participants or []))

        broadcast(
            {
                "type": "reports_metrics",
                "total_registered_users": total_registered_users,
                "live_watchers_count": live_watchers_count,
                "total_minutes_consumed": total_minutes_consumed,
            },
            roles={"reports"},
            event_id=event_id,
        )

        event_tz = None
        try:
            event = events_service.get_event_by_id(event_id) or {}
            event_tz = event.get("timezone")
        except Exception:
            event_tz = None

        charts_payload = analytics_service.build_reports_charts(event_id=event_id, tz_name=event_tz)
        broadcast(
            {"type": "reports_charts", **charts_payload},
            roles={"reports"},
            event_id=event_id,
        )

        try:
            from app.services.redis_cache import get_redis_cache
            r = get_redis_cache()
            if r and REPORTS_CACHE_TTL_SECONDS > 0:
                cache_payload = {
                    "active_sessions": active_viewers,
                    "total_registered_users": total_registered_users,
                    "live_watchers_count": live_watchers_count,
                    "total_minutes_consumed": total_minutes_consumed,
                    "charts": charts_payload,
                }
                r.setex(cache_key, REPORTS_CACHE_TTL_SECONDS, json.dumps(cache_payload, default=str))
        except Exception:
            pass

        print(f"[WS] snapshot event_id={event_id} active={len(active_viewers)} total={len(all_participants)}")

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


def _local_broadcast(payload, roles=None, event_id=None):
    """Envía solo a clientes locales (misma instancia)."""
    text = json.dumps(payload)
    target_roles = roles if roles else WEBSOCKET_CLIENTS.keys()
    sent_count = 0
    for role in target_roles:
        clients = list(WEBSOCKET_CLIENTS.get(role, []))
        for client in clients:
            if event_id is not None and getattr(client, "event_id", None) != event_id:
                continue
            try:
                client.write_message(text)
                sent_count += 1
            except tornado.websocket.WebSocketClosedError:
                WEBSOCKET_CLIENTS[role].discard(client)
    try:
        metrics.ws_messages_out.labels(
            event_id=str(event_id) if event_id else "global",
            role="broadcast",
            type=payload.get("type", "unknown")
        ).inc(sent_count)
    except Exception:
        pass
    return sent_count


def broadcast(payload, roles=None, event_id=None):
    from app.config import BROADCAST_PUBSUB
    if BROADCAST_PUBSUB and event_id is not None:
        try:
            from app.services.redis_cache import get_redis_cache
            r = get_redis_cache()
            if r:
                channel = f"broadcast:event:{event_id}"
                msg = json.dumps({"event_id": event_id, "roles": list(roles) if roles else None, "payload": payload})
                r.publish(channel, msg)
        except Exception:
            pass
    sent_count = _local_broadcast(payload, roles=roles, event_id=event_id)
    print(f"[WS] OK: Enviado a {sent_count} clientes")


class LiveWebSocket(tornado.websocket.WebSocketHandler):
    def allow_draft76(self):
        return True

    def open(self):
        # Redis session-backed auth
        s_cookie = self.get_secure_cookie("session_id")
        if not s_cookie:
            print("[WS] ! Conexión rechazada: No hay cookie session_id")
            self.close(code=4001, reason="session_missing")
            return

        self.session_id = s_cookie.decode()
        session = session_service.get_session(self.session_id)
        if not session:
            print("[WS] ! Conexión rechazada: sesión expirada o inválida")
            self.close(code=4001, reason="session_expired")
            return

        self.user_id = session.get("user_id")
        if not self.user_id:
            self.close(code=4001, reason="session_invalid")
            return

        self.user_name = session.get("user_name") or "Guest"

        requested_role = self.get_query_argument("role", "viewer")
        user_role = session.get("user_role") or "viewer"

        is_superadmin = user_role == "superadmin"

        arg_event = self.get_query_argument("event_id", default=None)
        # Fallback: if client omitted event_id (or malformed), try the cookie set by BaseHandler.prepare
        try:
            self.event_id = int(arg_event) if arg_event else None
        except (TypeError, ValueError):
            self.event_id = None

        if self.event_id is None:
            # Prefer session-scoped event id
            try:
                self.event_id = int(session.get("current_event_id")) if session.get("current_event_id") else None
            except (TypeError, ValueError):
                self.event_id = None

        if self.event_id is None:
            cookie_event = self.get_secure_cookie("current_event_id")
            try:
                self.event_id = int(cookie_event.decode()) if cookie_event else None
            except (TypeError, ValueError):
                self.event_id = None

        # Enforce role permissions to avoid privilege escalation via querystring.
        # For non-viewer roles, we require an event_id so we can validate assignment.
        staff_role = None
        if self.event_id is not None:
            try:
                from app.services import staff_service
                staff_role = staff_service.get_event_role(int(self.user_id), int(self.event_id))
            except Exception:
                staff_role = None

        try:
            session_event_id = int(session.get("current_event_id")) if session.get("current_event_id") else None
        except (TypeError, ValueError):
            session_event_id = None

        if requested_role == "viewer":
            self.role = "viewer"
        elif requested_role == "moderator":
            if self.event_id is None:
                self.close(code=4002, reason="event_missing")
                return
            # Allowed if superadmin, event-assigned staff, or per-event moderator account
            if is_superadmin or staff_role in ["admin", "moderator"] or (user_role in ["moderator", "moderador"] and session_event_id == self.event_id):
                self.role = "moderator"
            else:
                self.close(code=4003, reason="role_forbidden")
                return
        elif requested_role == "speaker":
            if self.event_id is None:
                self.close(code=4002, reason="event_missing")
                return
            if is_superadmin or staff_role in ["admin", "speaker"] or (user_role == "speaker" and session_event_id == self.event_id):
                self.role = "speaker"
            else:
                self.close(code=4003, reason="role_forbidden")
                return
        elif requested_role == "reports":
            if self.event_id is None:
                self.close(code=4002, reason="event_missing")
                return
            if is_superadmin or staff_role == "admin":
                self.role = "reports"
            else:
                self.close(code=4003, reason="role_forbidden")
                return
        else:
            print(f"[WS] ! Conexión rechazada: role inválido requested={requested_role}")
            self.close(code=4003, reason="role_forbidden")
            return

        # Keep accepting connections even if event_id is missing.
        # Audience counting also has an HTTP fallback on /api/ping.

        self.event_timezone = None
        if self.event_id is not None:
            try:
                event = events_service.get_event_by_id(self.event_id) or {}
                self.event_timezone = event.get("timezone")
            except Exception:
                self.event_timezone = None

        WEBSOCKET_CLIENTS.setdefault(self.role, set()).add(self)

        _ensure_pubsub_subscribe(self.event_id)
        
        # Track session analytics only for viewers
        if self.role == "viewer":
            analytics_service.ensure_session_analytics(self.user_id, event_id=self.event_id)
        
        # Push update to everyone interested (moderators/reports)
        push_reports_snapshot(event_id=self.event_id)
        
        print(f"[WS] OK: Conectado: {self.role} | user_id={self.user_id} | event_id={self.event_id}")

        # If there is a live poll, sync it to this client so reload/reconnect doesn't miss it.
        if getattr(self, "event_id", None) is not None and self.role in ("viewer", "moderator", "speaker", "reports"):
            try:
                live = poll_service.get_live_poll(int(self.event_id))
                if live:
                    self.write_message(json.dumps({"type": "poll_start", "poll": live}))
            except Exception:
                pass

        # Telemetry
        try:
            metrics.ws_connections_active.labels(event_id=str(self.event_id) or "global", role=self.role).inc()
            metrics.ws_connections.labels(event_id=str(self.event_id) or "global", role=self.role).inc()
        except:
            pass

    def on_close(self):
        # Safety check: if connection failed early, role might not be set
        safe_role = getattr(self, "role", None)
        if safe_role:
            WEBSOCKET_CLIENTS.get(safe_role, set()).discard(self)

        _ensure_pubsub_unsubscribe(getattr(self, "event_id", None))
        
        if safe_role == "viewer" and getattr(self, "user_id", None) is not None:
            analytics_service.mark_session_inactive(
                self.user_id,
                event_id=getattr(self, "event_id", None),
            )
            push_reports_snapshot(event_id=getattr(self, "event_id", None))
        
        print(f"[WS] OUT: Desconectado: {safe_role or 'unknown'} | user_id={getattr(self, 'user_id', '?')} | event_id={getattr(self, 'event_id', '?')}")
        
        # Telemetry
        try:
            eid = str(getattr(self, "event_id", "global"))
            role = getattr(self, "role", "unknown")
            # Safeguard: only decrement if > 0
            if metrics.ws_connections_active.labels(event_id=eid, role=role)._value.get() > 0:
                metrics.ws_connections_active.labels(event_id=eid, role=role).dec()
            
            metrics.ws_disconnects.labels(event_id=eid, role=role, reason="normal").inc()
        except:
            pass

    async def on_message(self, message):
        try:
            # Refresh/validate session on every WS message (5-min TTL safety).
            # If the session was purged in Redis, drop the socket so the client re-auths.
            if not getattr(self, "session_id", None) or not session_service.get_session(self.session_id):
                try:
                    self.close(code=4001, reason="session_expired")
                except Exception:
                    pass
                return

            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return

            msg_type = payload.get("type")
            print(f"[WS] {self.role} | Mensaje: {msg_type} | Payload: {payload}")

            # Telemetry
            try:
                metrics.ws_messages_in.labels(
                    event_id=str(self.event_id) or "global",
                    role=self.role,
                    type=msg_type or "unknown"
                ).inc()
            except:
                pass

            if msg_type == "chat":
                if users_service.is_chat_blocked(self.user_id):
                    self.write_message(json.dumps({"type": "error", "message": "Tu acceso al chat ha sido restringido."}))
                    return
                text = payload.get("message", "").strip()
                if not text:
                    return

                is_valid, error_message = await message_validation_service.validate_message(
                    event_id=self.event_id, user_id=self.user_id, message_text=text, message_type="chat"
                )
                if not is_valid:
                    self.write_message(json.dumps({"type": "error", "message": error_message}))
                    return

                chat_payload = chat_service.add_chat_message(self.user_id, text, event_id=self.event_id)
                broadcast(
                    {
                        "type": "chat",
                        **chat_payload,
                        "timestamp": now_hhmm_in_timezone(self.event_timezone),
                    },
                    event_id=self.event_id,
                )
                from app.config import CHAT_RECENT_IN_REDIS
                if CHAT_RECENT_IN_REDIS:
                    tornado.ioloop.IOLoop.current().add_callback(
                        chat_service.persist_chat_to_mysql, self.user_id, text, self.event_id
                    )
                push_reports_snapshot(event_id=self.event_id)

            elif msg_type == "ask":
                if users_service.is_qa_blocked(self.user_id):
                    self.write_message(json.dumps({"type": "error", "message": "Tu acceso a preguntas ha sido restringido."}))
                    return
                question = payload.get("question", "").strip()
                manual_user = payload.get("manual_user", "").strip()
                if not question:
                    return

                is_valid, error_message = await message_validation_service.validate_message(
                    event_id=self.event_id, user_id=self.user_id, message_text=question, message_type="qa"
                )
                if not is_valid:
                    self.write_message(json.dumps({"type": "error", "message": error_message}))
                    return

                question_payload = questions_service.add_question(
                    self.user_id,
                    question,
                    event_id=self.event_id,
                    manual_user_name=(manual_user or None),
                )
                broadcast({"type": "pending_question", **question_payload}, roles={"moderator"}, event_id=self.event_id)
                push_reports_snapshot(event_id=self.event_id)

            elif msg_type == "approve" and self.role == "moderator":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                approved_payload = questions_service.approve_question(question_id)
                if approved_payload:
                    broadcast({"type": "approved_question", **approved_payload}, roles={"viewer", "speaker", "moderator"}, event_id=self.event_id)
                push_reports_snapshot(event_id=self.event_id)

            elif msg_type == "reject" and self.role == "moderator":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                questions_service.reject_question(question_id)
                broadcast({"type": "rejected_question", "id": question_id}, roles={"moderator"}, event_id=self.event_id)
                push_reports_snapshot(event_id=self.event_id)

            elif msg_type == "read" and self.role == "speaker":
                question_id = payload.get("id")
                try:
                    question_id = int(question_id)
                except (TypeError, ValueError):
                    return
                read_payload = questions_service.mark_question_as_read(question_id)
                if read_payload:
                    broadcast({"type": "question_read", **read_payload}, roles={"viewer", "speaker", "moderator"}, event_id=self.event_id)
                push_reports_snapshot(event_id=self.event_id)

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
                push_reports_snapshot(event_id=self.event_id)

            elif msg_type == "ping":
                analytics_service.record_ping(self.user_id, event_id=self.event_id)
                # No push_reports_snapshot aquí: con 35k usuarios serían miles de consultas MySQL/s.
                # El reporte se actualiza cada 5s vía PeriodicCallback en server.py.

            elif msg_type == "poll_start" and self.role in ("moderator", "speaker"):
                try:
                    poll_id = payload.get("poll_id")
                    duration_minutes = payload.get("duration_minutes")
                    if duration_minutes is not None:
                        duration_minutes = int(duration_minutes)

                    # Launch a pre-created poll by id (preferred path for /mod UI)
                    if poll_id is not None:
                        poll_id = int(poll_id)

                        def _do_launch():
                            res = poll_service.launch_poll(self.event_id, poll_id, duration_minutes)
                            if res:
                                broadcast({"type": "poll_start", "poll": res}, event_id=self.event_id)
                                _schedule_poll_auto_close(self.event_id, poll_id, res.get("close_at"))
                            else:
                                try:
                                    self.write_message(json.dumps({"type": "error", "message": "Poll not available (must be published)"}))
                                except:
                                    pass

                        tornado.ioloop.IOLoop.current().spawn_callback(_do_launch)
                        return
                except (ValueError, TypeError):
                    self.write_message(json.dumps({"type": "error", "message": "Invalid duration"}))
                    return

                # Legacy: start an ad-hoc poll (question/options)
                question = payload.get("question", "").strip()
                options_raw = payload.get("options", [])
                try:
                    options = [opt.strip() for opt in options_raw if opt.strip()]
                    if not question or len(options) < 2:
                        self.write_message(json.dumps({"type": "error", "message": "Invalid poll data"}))
                        return
                except Exception:
                    self.write_message(json.dumps({"type": "error", "message": "Invalid poll data"}))
                    return

                def _do_start():
                    res = poll_service.start_poll(self.event_id, question, options, duration_minutes)
                    if res:
                        broadcast({"type": "poll_start", "poll": res}, event_id=self.event_id)
                        _schedule_poll_auto_close(self.event_id, res.get("poll_id"), res.get("close_at"))
                    else:
                        try:
                            self.write_message(json.dumps({"type": "error", "message": "Failed to start poll (Redis/DB error)" }))
                        except:
                            pass
                tornado.ioloop.IOLoop.current().spawn_callback(_do_start)

            elif msg_type == "poll_vote":
                try:
                    option_index = int(payload["option_index"])
                except (KeyError, ValueError):
                    self.write_message(json.dumps({"type": "error", "message": "Invalid option"}))
                    return

                def _do_vote():
                    res = poll_service.vote(self.event_id, option_index, self.user_id)
                    if res:
                        broadcast({"type": "poll_update_results", **res}, event_id=self.event_id)
                    else:
                        try:
                            self.write_message(json.dumps({"type": "error", "message": "Encuesta cerrada o voto inválido"}))
                        except Exception:
                            pass
                tornado.ioloop.IOLoop.current().spawn_callback(_do_vote)

            elif msg_type == "poll_close" and self.role in ("moderator", "speaker"):
                def _do_close():
                    res = poll_service.close_poll(self.event_id)
                    if res:
                        broadcast({"type": "poll_end", "final_results": res}, event_id=self.event_id)
                    else:
                        try:
                            self.write_message(json.dumps({"type": "error", "message": "No active poll or error"}))
                        except:
                            pass
                tornado.ioloop.IOLoop.current().spawn_callback(_do_close)
        except Exception:
            traceback.print_exc()

    def check_origin(self, origin):
        return True
