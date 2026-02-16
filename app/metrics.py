from prometheus_client import Gauge, Counter, Histogram

# We can use a custom registry if we want to avoid mixing with default collector
# but for simplicity, we'll use the default one and just collect it for MySQL.
# registry = Registry()

# --- 1) WebSocket (tiempo real) ---
ws_connections_active = Gauge(
    "ws_connections_active", 
    "Current active WS connections", 
    ["event_id", "role"]
)
ws_connections = Counter(
    "ws_connections", 
    "Total WS connections opened", 
    ["event_id", "role"]
)
ws_disconnects = Counter(
    "ws_disconnects", 
    "Total WS connections closed", 
    ["event_id", "role", "reason"]
)
ws_messages_in = Counter(
    "ws_messages_in", 
    "Total messages received via WS", 
    ["event_id", "role", "type"]
)
ws_messages_out = Counter(
    "ws_messages_out", 
    "Total messages sent via WS", 
    ["event_id", "role", "type"]
)

# --- 2) Audiencia / Watch ---
watch_live_viewers = Gauge(
    "watch_live_viewers", 
    "Live viewers estimated by pings", 
    ["event_id"]
)

# --- 3) HTTP (Tornado handlers) ---
http_requests = Counter(
    "http_requests", 
    "Total HTTP requests handled", 
    ["handler", "method", "status"]
)
http_request_duration_ms = Histogram(
    "http_request_duration_ms", 
    "HTTP request latency in milliseconds", 
    ["handler"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000)
)
http_exceptions = Counter(
    "http_exceptions", 
    "Total HTTP exceptions", 
    ["handler", "exception_type"]
)

# --- 4) Moderación / Q&A / Chat ---
chat_messages = Counter(
    "chat_messages", 
    "Total chat messages sent", 
    ["event_id"]
)
qna_questions = Counter(
    "qna_questions", 
    "Total questions asked", 
    ["event_id"]
)
qna_actions = Counter(
    "qna_actions", 
    "Questions moderated (approved/rejected/read)", 
    ["event_id", "action"]
)

# --- 5) Base de Datos ---
db_query_duration_ms = Histogram(
    "db_query_duration_ms", 
    "Database query duration in milliseconds", 
    ["operation", "table"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000)
)
db_errors = Counter(
    "db_errors", 
    "Total database errors", 
    ["operation"]
)

# --- 6) Exportaciones ---
exports = Counter(
    "exports", 
    "Total exports generated", 
    ["format"]
)

# --- 7) Sistema (CPU / RAM) ---
process_cpu_usage = Gauge(
    "process_cpu_usage_percent",
    "Current CPU usage of the process in percent"
)
process_memory_rss = Gauge(
    "process_memory_rss_bytes",
    "Resident Set Size memory usage in bytes"
)

# Global process object for reused CPU tracking
import psutil
import os
_PROC = psutil.Process(os.getpid())
_PROC.cpu_percent() # Prime it

# --- 8) Internos de Tornado ---
tornado_ioloop_latency_ms = Histogram(
    "tornado_ioloop_latency_ms",
    "Latency of Tornado IOLoop callbacks in ms",
    buckets=(1, 5, 10, 20, 50, 100, 200, 500)
)

# --- Force Registration of all metrics ---
# Prometheus client lazy-registers metrics. We force a dummy access to ensure they appear
# in WRITES immediately, initialized at 0.
try:
    # Gauges
    ws_connections_active.labels(event_id="global", role="init").set(0)
    watch_live_viewers.labels(event_id="global").set(0)
    process_cpu_usage.set(0)
    process_memory_rss.set(0)

    # Counters (initializing counters with 0 is good practice)
    # We use a dummy label that won't interfere much with real stats or just rely on definition
    pass
except Exception as e:
    print(f"[Metrics] Warning initializing metrics: {e}")
