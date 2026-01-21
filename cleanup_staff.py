import os
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

def cleanup_duplicates():
    # Cargar .env manualmente
    load_dotenv()
    
    db_config = {
        "host": os.environ.get("DB_HOST"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
        "db": os.environ.get("DB_NAME"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": True
    }

    if not db_config["host"]:
        print("Error: No se encontró DB_HOST en el archivo .env")
        return

    print(f"Conectando a la base de datos en {db_config['host']}...")
    try:
        conn = pymysql.connect(**db_config)
    except Exception as e:
        print(f"Error de conexión: {e}")
        return

    try:
        with conn.cursor() as cursor:
            # Encontrar emails duplicados
            cursor.execute("""
                SELECT email, COUNT(*) as count 
                FROM users 
                WHERE email IS NOT NULL AND email != ''
                GROUP BY email 
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()
            
            if not duplicates:
                print("No se encontraron emails duplicados.")
                return

            for dup in duplicates:
                email = dup['email']
                print(f"Limpiando duplicados para: {email}")
                
                # Obtener todos los IDs para este email, ordenados por ID (el más viejo primero)
                cursor.execute("SELECT id FROM users WHERE email=%s ORDER BY id ASC", (email,))
                ids = [r['id'] for r in cursor.fetchall()]
                
                keep_id = ids[0]
                remove_ids = ids[1:]
                
                print(f"  Manteniendo ID: {keep_id}, eliminando IDs: {remove_ids}")
                
                # Mover posibles referencias en otras tablas
                for rid in remove_ids:
                    # Mover staff de eventos
                    cursor.execute("UPDATE IGNORE event_staff SET user_id=%s WHERE user_id=%s", (keep_id, rid))
                    cursor.execute("DELETE FROM event_staff WHERE user_id=%s", (rid,))
                    
                    # Mover preguntas
                    cursor.execute("UPDATE questions SET user_id=%s WHERE user_id=%s", (keep_id, rid))
                    
                    # Mover mensajes de chat
                    cursor.execute("UPDATE chat_messages SET user_id=%s WHERE user_id=%s", (keep_id, rid))
                    
                    # Mover analytics
                    cursor.execute("UPDATE IGNORE session_analytics SET user_id=%s WHERE user_id=%s", (keep_id, rid))
                    cursor.execute("DELETE FROM session_analytics WHERE user_id=%s", (rid,))
                    
                    # Eliminar el usuario duplicado
                    cursor.execute("DELETE FROM users WHERE id=%s", (rid,))
                
            print("¡Limpieza completada!")
    except Exception as e:
        print(f"Error durante la limpieza: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_duplicates()
