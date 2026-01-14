import os

import tornado.web

from app.config import COOKIE_SECRET
from app.handlers.auth import LoginHandler, LogoutHandler, RegistrationHandler
from app.handlers.admin import EventsAdminHandler, APIEventsHandler
from app.handlers.moderator import (
    APIChatsHandler,
    APIParticipantsHandler,
    APIQuestionsHandler,
    APIUserStatusHandler,
    ModeratorHandler,
)
from app.handlers.reports import ReportsExportHandler, ReportsHandler
from app.handlers.speaker import SpeakerHandler
from app.handlers.watch import WatchHandler
from app.handlers.ws import LiveWebSocket


def make_app():
	base_dir = os.path.dirname(os.path.dirname(__file__))
	template_path = os.path.join(base_dir, "templates")

	return tornado.web.Application(
		[
			(r"/", RegistrationHandler),
			(r"/login", LoginHandler),
			(r"/logout", LogoutHandler),
			(r"/watch", WatchHandler),
			(r"/mod", ModeratorHandler),
			(r"/speaker", SpeakerHandler),
			(r"/reports", ReportsHandler),
			(r"/reports/export", ReportsExportHandler),
			(r"/ws", LiveWebSocket),
			(r"/api/questions", APIQuestionsHandler),
			(r"/api/participants", APIParticipantsHandler),
			(r"/api/chats", APIChatsHandler),
			(r"/api/user/status", APIUserStatusHandler),
			(r"/admin/events", EventsAdminHandler),
			(r"/api/admin/events", APIEventsHandler),
			# Dynamic Event Routes
			(r"/e/([^/]+)/?", RegistrationHandler),
			(r"/e/([^/]+)/login", LoginHandler),
			(r"/e/([^/]+)/watch", WatchHandler),
			(r"/e/([^/]+)/mod", ModeratorHandler),
			(r"/e/([^/]+)/speaker", SpeakerHandler),
			(r"/e/([^/]+)/reports", ReportsHandler),
		],
		cookie_secret=COOKIE_SECRET,
		login_url="/",
		template_path=template_path,
		xsrf_cookies=False,
		debug=True,
	)
