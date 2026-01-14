import tornado.ioloop

from tornado.ioloop import PeriodicCallback

from app import make_app
from app.handlers.ws import push_reports_snapshot


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Tornado live platform running on http://localhost:8888")

    # Keep reports refreshed even if pings are sparse.
    PeriodicCallback(push_reports_snapshot, 5000).start()
    tornado.ioloop.IOLoop.current().start()