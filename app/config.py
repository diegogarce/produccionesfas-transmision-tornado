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

# Validación mínima para evitar errores críticos
if not MYSQL_CONFIG["host"]:
    print("ERROR: DB_HOST no definido en .env", file=sys.stderr)
