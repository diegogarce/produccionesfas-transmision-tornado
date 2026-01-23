from app.services.telemetry_service import create_telemetry_table, create_telemetry_errors_table

if __name__ == "__main__":
    print("Inicializando tablas de telemetría...")
    create_telemetry_table()
    create_telemetry_errors_table()
    print("Listo.")
