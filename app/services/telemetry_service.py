"""
Telemetría: snapshots de métricas (Prometheus) y registro de errores HTTP.

Backend:
- redis: guarda en Redis (Sorted Set snapshots + List errores). No escribe en MySQL.
  Recomendado para no saturar MySQL con escrituras y espacio.
- mysql: guarda en tablas telemetry_snapshots y telemetry_errors (legacy).
"""
import json
import time
from datetime import datetime, timedelta, timezone
from prometheus_client import REGISTRY
from app.db import create_db_connection
from app.config import TELEMETRY_BACKEND

# Redis client for telemetry (db=1; sesiones están en db=0).
# Para ver keys: redis-cli -n 1 → KEYS telemetry:*
_redis_telemetry = None

def _get_redis_telemetry():
    global _redis_telemetry
    if _redis_telemetry is not None:
        return _redis_telemetry
    if TELEMETRY_BACKEND != "redis":
        return None
    try:
        import redis
        from app.config import REDIS_CONFIG
        _redis_telemetry = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=1,  # telemetry in db=1, sessions in db=0
            decode_responses=True,
        )
        _redis_telemetry.ping()
        print("[Telemetry] Backend Redis conectado (db=1).")
        return _redis_telemetry
    except Exception as e:
        print(f"[Telemetry] Redis no disponible, fallback a MySQL: {e}")
        return None


def create_telemetry_table():
    """Asegura que existan las tablas en MySQL (solo si backend es mysql o como fallback)."""
    if TELEMETRY_BACKEND == "redis":
        return
    sql = """
    CREATE TABLE IF NOT EXISTS telemetry_snapshots (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        metrics_json JSON NOT NULL,
        INDEX idx_telemetry_timestamp (timestamp)
    );
    """
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
        print("[Telemetry] Tablas de telemetría (MySQL) aseguradas.")
    except Exception as e:
        print(f"[Telemetry] Error creando tabla: {e}")


def create_telemetry_errors_table():
    """Asegura la tabla de errores en MySQL (solo si backend es mysql)."""
    if TELEMETRY_BACKEND == "redis":
        return
    sql = """
    CREATE TABLE IF NOT EXISTS telemetry_errors (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        handler VARCHAR(120) NULL,
        method VARCHAR(16) NULL,
        status INT NULL,
        exception_type VARCHAR(120) NULL,
        message VARCHAR(500) NULL,
        path VARCHAR(500) NULL,
        INDEX idx_telemetry_errors_timestamp (timestamp),
        INDEX idx_telemetry_errors_status (status)
    );
    """
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
        print("[Telemetry] Tabla de errores (MySQL) asegurada.")
    except Exception as e:
        print(f"[Telemetry] Error creando tabla de errores: {e}")


import os
import psutil
from app import metrics

TELEMETRY_RETENTION_DAYS = int(os.getenv("TELEMETRY_RETENTION_DAYS", "0"))
TELEMETRY_SNAPSHOT_HOURS = int(os.getenv("TELEMETRY_SNAPSHOT_HOURS", "6"))
TELEMETRY_ERRORS_MAX = int(os.getenv("TELEMETRY_ERRORS_MAX", "500"))
_last_cleanup_at = None

REDIS_KEY_SNAPSHOTS = "telemetry:snapshots"
REDIS_KEY_ERRORS = "telemetry:errors"


def _maybe_cleanup_telemetry_mysql():
    """Limpieza por retención en MySQL (solo backend mysql)."""
    global _last_cleanup_at
    if TELEMETRY_BACKEND != "mysql" or TELEMETRY_RETENTION_DAYS <= 0:
        return
    now = datetime.now()
    if _last_cleanup_at and (now - _last_cleanup_at) < timedelta(hours=6):
        return
    cutoff = now - timedelta(days=TELEMETRY_RETENTION_DAYS)
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM telemetry_snapshots WHERE timestamp < %s",
                    (cutoff,)
                )
            conn.commit()
        _last_cleanup_at = now
        print(f"[Telemetry] Retención MySQL aplicada (>{TELEMETRY_RETENTION_DAYS} días)")
    except Exception as e:
        print(f"[Telemetry] Error en limpieza de retención: {e}")


def capture_snapshot():
    """
    Lee las métricas actuales de Prometheus y las guarda.
    - Redis: Sorted Set por timestamp; se recorta a últimas TELEMETRY_SNAPSHOT_HOURS.
    - MySQL: INSERT en telemetry_snapshots (legacy).
    """
    try:
        from app.metrics import _PROC
        metrics.process_cpu_usage.set(_PROC.cpu_percent())
        metrics.process_memory_rss.set(_PROC.memory_info().rss)
    except Exception as e:
        print(f"[Telemetry] Warning updating system metrics: {e}")

    snapshot = {}
    for metric in REGISTRY.collect():
        metric_data = []
        for sample in metric.samples:
            metric_data.append({
                "name": sample.name,
                "labels": sample.labels,
                "value": sample.value
            })
        snapshot[metric.name] = metric_data

    if TELEMETRY_BACKEND == "redis":
        r = _get_redis_telemetry()
        if r:
            try:
                ts = time.time()
                member = json.dumps({"ts": ts, "metrics": snapshot})
                r.zadd(REDIS_KEY_SNAPSHOTS, {member: ts})
                cutoff = ts - (TELEMETRY_SNAPSHOT_HOURS * 3600)
                r.zremrangebyscore(REDIS_KEY_SNAPSHOTS, "-inf", cutoff)
                try:
                    with open("telemetry_heartbeat.txt", "w") as f:
                        f.write(str(datetime.now()))
                except Exception:
                    pass
                return
            except Exception as e:
                print(f"[Telemetry] Error guardando snapshot en Redis: {e}")
                try:
                    metrics.db_errors.labels(operation="capture_snapshot").inc()
                except Exception:
                    pass
        return

    # MySQL path (TELEMETRY_BACKEND == "mysql")
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO telemetry_snapshots (metrics_json) VALUES (%s)",
                    (json.dumps(snapshot),)
                )
            conn.commit()
        _maybe_cleanup_telemetry_mysql()
        try:
            with open("telemetry_heartbeat.txt", "w") as f:
                f.write(str(datetime.now()))
        except Exception:
            pass
    except Exception as e:
        print(f"[Telemetry] Error guardando snapshot en MySQL: {e}")
        try:
            metrics.db_errors.labels(operation="capture_snapshot").inc()
        except Exception:
            pass


def get_recent_history(hours=24):
    """
    Devuelve lista de dicts con keys: timestamp (datetime UTC), metrics_json (dict).
    Origen: Redis (Sorted Set) o MySQL según TELEMETRY_BACKEND.
    """
    if TELEMETRY_BACKEND == "redis":
        r = _get_redis_telemetry()
        if not r:
            return []
        try:
            cutoff = time.time() - (hours * 3600)
            raw = r.zrangebyscore(REDIS_KEY_SNAPSHOTS, cutoff, "+inf")
            result = []
            for member in raw:
                try:
                    data = json.loads(member)
                    ts = data.get("ts")
                    metrics_data = data.get("metrics", {})
                    if ts is not None:
                        result.append({
                            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                            "metrics_json": metrics_data,
                        })
                except (json.JSONDecodeError, TypeError):
                    continue
            result.sort(key=lambda x: x["timestamp"])
            return result
        except Exception as e:
            print(f"[Telemetry] Error leyendo historial desde Redis: {e}")
        return []

    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT timestamp, metrics_json
                    FROM telemetry_snapshots
                    WHERE timestamp > DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY timestamp ASC
                    """,
                    (hours,)
                )
                return cursor.fetchall()
    except Exception as e:
        print(f"[Telemetry] Error obteniendo historial desde MySQL: {e}")
        return []


def record_http_exception(handler, method, status, exception_type, message, path):
    """Registra un error HTTP para el panel. Redis (List) o MySQL."""
    safe_message = (str(message) if message is not None else "")[:500]
    safe_path = (str(path) if path is not None else "")[:500]

    if TELEMETRY_BACKEND == "redis":
        r = _get_redis_telemetry()
        if r:
            try:
                doc = {
                    "ts": time.time(),
                    "handler": handler,
                    "method": method,
                    "status": status,
                    "exception_type": exception_type,
                    "message": safe_message,
                    "path": safe_path,
                }
                r.lpush(REDIS_KEY_ERRORS, json.dumps(doc))
                r.ltrim(REDIS_KEY_ERRORS, 0, TELEMETRY_ERRORS_MAX - 1)
            except Exception as e:
                print(f"[Telemetry] Error guardando excepción en Redis: {e}")
        return

    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telemetry_errors (handler, method, status, exception_type, message, path)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (handler, method, status, exception_type, safe_message, safe_path)
                )
            conn.commit()
    except Exception as e:
        print(f"[Telemetry] Error guardando evento de error en MySQL: {e}")


def get_recent_errors(limit=50):
    """
    Devuelve lista de dicts con timestamp, handler, method, status, exception_type, message, path.
    Origen: Redis (List) o MySQL.
    """
    if TELEMETRY_BACKEND == "redis":
        r = _get_redis_telemetry()
        if not r:
            return []
        try:
            raw = r.lrange(REDIS_KEY_ERRORS, 0, limit - 1)
            result = []
            for member in raw:
                try:
                    data = json.loads(member)
                    ts = data.get("ts")
                    result.append({
                        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else None,
                        "handler": data.get("handler"),
                        "method": data.get("method"),
                        "status": data.get("status"),
                        "exception_type": data.get("exception_type"),
                        "message": data.get("message"),
                        "path": data.get("path"),
                    })
                except (json.JSONDecodeError, TypeError):
                    continue
            return result
        except Exception as e:
            print(f"[Telemetry] Error leyendo errores desde Redis: {e}")
        return []

    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT timestamp, handler, method, status, exception_type, message, path
                    FROM telemetry_errors
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
                return cursor.fetchall()
    except Exception as e:
        print(f"[Telemetry] Error obteniendo errores desde MySQL: {e}")
        return []
