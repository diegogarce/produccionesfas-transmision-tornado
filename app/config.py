import os
from pymysql.cursors import DictCursor

COOKIE_SECRET = os.environ.get("COOKIE_SECRET", "change-me-please")
MYSQL_CONFIG = {
    "host": os.environ.get("DB_HOST", "db.transmisionesfast.com"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Pr0ducc10n35F45t2050"),
    "db": os.environ.get("DB_NAME", "transmision_tornado"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}
