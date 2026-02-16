import os
import sys
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# Determinar la ruta a la raíz del proyecto
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
env_path = os.path.join(basedir, '.env')

# Cargar el archivo .env
load_dotenv(env_path)

# Mostrar en consola qué variables se detectaron (sin mostrar secretos sensibles)
print(f"--- Configuración cargada desde: {env_path} ---")
print(f"DB_HOST detected: {'Yes' if os.environ.get('DB_HOST') else 'No'}")
print(f"COOKIE_SECRET detected: {'Yes' if os.environ.get('COOKIE_SECRET') else 'No'}")

COOKIE_SECRET = os.environ.get("COOKIE_SECRET", "default-secret-if-missing")

MYSQL_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "db": os.environ.get("DB_NAME"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

REDIS_CONFIG = {
    "host": os.environ.get("REDIS_HOST", "localhost"),
    # Default local port set to 6380 to match docker-compose mapping
    "port": int(os.environ.get("REDIS_PORT", 6380)),
    "db": 0,
}

# Telemetría: por defecto solo Redis (no toca MySQL). Para legacy: TELEMETRY_BACKEND=mysql
TELEMETRY_BACKEND = os.environ.get("TELEMETRY_BACKEND", "redis")

# Ping/heartbeat: "redis" evita miles de writes/s en MySQL con muchos usuarios. "mysql" = session_analytics.
PING_BACKEND = os.environ.get("PING_BACKEND", "redis" if os.environ.get("REDIS_HOST") else "mysql")

# Fase A: Chat reciente en Redis; caché de watch
CHAT_RECENT_IN_REDIS = os.environ.get("CHAT_RECENT_IN_REDIS", "1") == "1"
CHAT_REDIS_MAX_MESSAGES = int(os.environ.get("CHAT_REDIS_MAX_MESSAGES", "100"))
WATCH_CACHE_TTL_SECONDS = int(os.environ.get("WATCH_CACHE_TTL_SECONDS", "5"))

# Fase B: Caché del snapshot de reportes por evento
REPORTS_CACHE_TTL_SECONDS = int(os.environ.get("REPORTS_CACHE_TTL_SECONDS", "5"))

# Fase C: Broadcast vía Redis Pub/Sub para escalar horizontalmente
BROADCAST_PUBSUB = os.environ.get("BROADCAST_PUBSUB", "1") == "1" if os.environ.get("REDIS_HOST") else False

# Validación mínima para evitar errores críticos
if not MYSQL_CONFIG["host"]:
    print("ERROR: DB_HOST no definido en .env", file=sys.stderr)
