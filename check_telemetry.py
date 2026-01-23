from app.db import create_db_connection
import json

def check_db():
    try:
        with create_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM telemetry_snapshots")
                res = cursor.fetchone()
                print(f"Total snapshots in DB: {res['cnt']}")
                
                if res['cnt'] > 0:
                    cursor.execute("SELECT metrics_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1")
                    row = cursor.fetchone()
                    metrics = json.loads(row['metrics_json'])
                    print(f"Latest snapshot keys count: {len(metrics.keys())}")
                    print(f"Sample metric (ws_connections_active): {metrics.get('ws_connections_active', 'Not found')}")
    except Exception as e:
        print(f"Error checking DB: {e}")

if __name__ == "__main__":
    check_db()
