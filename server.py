import tornado.ioloop
from tornado.ioloop import PeriodicCallback
import os


if __name__ == "__main__":
    from app import make_app
    from app.handlers.ws import push_reports_snapshot
    from app.services.telemetry_service import capture_snapshot, create_telemetry_table
    from app.config import TELEMETRY_BACKEND
    import app.metrics

    app = make_app()
    # Create HTTP server with xheaders=True to correctly handle X-Forwarded-Proto/For
    import tornado.httpserver
    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    port = int(os.environ.get("PORT", "8888"))
    server.listen(port)
    print(f"Tornado live platform running on http://localhost:{port}")

    # Solo crear tablas de telemetría en MySQL si se usa backend mysql (por defecto: Redis)
    if TELEMETRY_BACKEND == "mysql":
        create_telemetry_table()
    capture_snapshot()

    # Keep reports refreshed even if pings are sparse.
    PeriodicCallback(push_reports_snapshot, 5000).start()
    
    # Telemetry snapshots every 10 seconds for debugging
    PeriodicCallback(capture_snapshot, 10000).start()
    
    # Monitor IOLoop latency
    def monitor_ioloop_latency():
        from app import metrics
        start = tornado.ioloop.IOLoop.current().time()
        tornado.ioloop.IOLoop.current().add_callback(
            lambda: metrics.tornado_ioloop_latency_ms.observe((tornado.ioloop.IOLoop.current().time() - start) * 1000)
        )
    PeriodicCallback(monitor_ioloop_latency, 1000).start()
    
    tornado.ioloop.IOLoop.current().start()
