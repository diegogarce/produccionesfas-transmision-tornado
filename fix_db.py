from app.db import create_db_connection

def fix_schema():
    print("Conectando a la base de datos...")
    conn = create_db_connection()
    try:
        with conn.cursor() as cursor:
            print("Verificando tabla 'questions'...")
            # Modificamos la columna para aceptar 'read'
            # Asumimos que es un ENUM. Si fuera VARCHAR no daría error de truncamiento por 'read' (4 chars)
            # a menos que fuera VARCHAR(3). Pero lo más probable es ENUM.
            sql = "ALTER TABLE questions MODIFY COLUMN status ENUM('pending', 'approved', 'rejected', 'read') NOT NULL DEFAULT 'pending'"
            print(f"Ejecutando: {sql}")
            cursor.execute(sql)
            print("¡Esquema actualizado correctamente! Ahora soporta el estado 'read'.")
    except Exception as e:
        print(f"Error al actualizar esquema: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_schema()
