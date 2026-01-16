import tornado.ioloop

from tornado.ioloop import PeriodicCallback
import os

from app import make_app
from app.handlers.ws import push_reports_snapshot


if __name__ == "__main__":
    app = make_app()
    # Create HTTP server with xheaders=True to correctly handle X-Forwarded-Proto/For
    import tornado.httpserver
    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    port = int(os.environ.get("PORT", "8888"))
    server.listen(port)
    print(f"Tornado live platform running on http://localhost:{port}")

    # Keep reports refreshed even if pings are sparse.
    PeriodicCallback(push_reports_snapshot, 5000).start()
    tornado.ioloop.IOLoop.current().start()