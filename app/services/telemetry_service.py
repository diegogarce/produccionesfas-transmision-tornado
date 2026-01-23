import json
from datetime import datetime, timedelta
from prometheus_client import REGISTRY
from app.db import create_db_connection

def create_telemetry_table():
    """Ensure the telemetry table exists."""
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
        print("[Telemetry] Tablas de telemetría aseguradas.")
    except Exception as e:
        print(f"[Telemetry] Error creando tabla: {e}")

def create_telemetry_errors_table():
    """Ensure the telemetry errors table exists."""
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
        print("[Telemetry] Tabla de errores asegurada.")
    except Exception as e:
        print(f"[Telemetry] Error creando tabla de errores: {e}")

import os
import psutil
from app import metrics

# Retention settings (disabled by default)
TELEMETRY_RETENTION_DAYS = int(os.getenv("TELEMETRY_RETENTION_DAYS", "0"))
_last_cleanup_at = None

def _maybe_cleanup_telemetry():
    """Optional retention cleanup (throttled)."""
    global _last_cleanup_at
    if TELEMETRY_RETENTION_DAYS <= 0:
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
        print(f"[Telemetry] Retención aplicada (>{TELEMETRY_RETENTION_DAYS} días)")
    except Exception as e:
        print(f"[Telemetry] Error en limpieza de retención: {e}")

def capture_snapshot():
    """
    Lee las métricas actuales de Prometheus y las guarda en JSON en MySQL.
    Filtra los datos para que el JSON sea legible y no demasiado pesado.
    """
    # Actualizar métricas de sistema antes de capturar
    try:
        from app.metrics import _PROC
        # cpu_percent(None) uses the interval since the last call on this specific object.
        metrics.process_cpu_usage.set(_PROC.cpu_percent())
        metrics.process_memory_rss.set(_PROC.memory_info().rss)
    except Exception as e:
        print(f"[Telemetry] Warning updating system metrics: {e}")

    snapshot = {}
    
    # REGISTRY.collect() returns generators of Metric objects
    for metric in REGISTRY.collect():
        # Metric structure: name, documentation, type, and samples
        # samples is a list of Sample namedtuples (name, labels, value, timestamp, exemplar)
        metric_data = []
        for sample in metric.samples:
            # We only care about name, labels and value
            metric_data.append({
                "name": sample.name,
                "labels": sample.labels,
                "value": sample.value
            })
        snapshot[metric.name] = metric_data

    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                sql = "INSERT INTO telemetry_snapshots (metrics_json) VALUES (%s)"
                cursor.execute(sql, (json.dumps(snapshot),))
            conn.commit()
        _maybe_cleanup_telemetry()
        
        # Verbose logging for debugging
        keys = list(snapshot.keys())
        print(f"[Telemetry] Snapshot capturado: {len(keys)} métricas encontradas.")
        if len(keys) > 0:
            print(f"[Telemetry] Métricas: {keys}")

        try:
            with open("telemetry_heartbeat.txt", "w") as f:
                f.write(str(datetime.now()))
        except:
            pass
    except Exception as e:
        print(f"[Telemetry] Error guardando snapshot: {e}")
        try:
            metrics.db_errors.labels(operation="capture_snapshot").inc()
        except:
            pass

def get_recent_history(hours=24):
    """Obtiene el historial de snapshots para graficar."""
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                SELECT timestamp, metrics_json 
                FROM telemetry_snapshots 
                WHERE timestamp > DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY timestamp ASC
                """
                cursor.execute(sql, (hours,))
                return cursor.fetchall()
    except Exception as e:
        print(f"[Telemetry] Error obteniendo historial: {e}")
        return []

def record_http_exception(handler, method, status, exception_type, message, path):
    """Stores a sanitized error event for UI listing."""
    try:
        safe_message = (str(message) if message is not None else "")[:500]
        safe_path = (str(path) if path is not None else "")[:500]
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
        print(f"[Telemetry] Error guardando evento de error: {e}")

def get_recent_errors(limit=50):
    """Obtiene errores recientes para el panel de telemetría."""
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
        print(f"[Telemetry] Error obteniendo errores recientes: {e}")
        return []
