#!/usr/bin/env python3
"""
Migration script to update the database schema to match the event-based architecture.
This adds the missing columns (password, role, event_id) to the users table
and updates the events table structure.
"""

from app.db import create_db_connection


def migrate_schema():
    print("🔄 Iniciando migración de esquema...")
    conn = create_db_connection()
    
    try:
        with conn.cursor() as cursor:
            # Check current schema
            print("\n📋 Verificando esquema actual...")
            
            # Check if users table needs migration
            cursor.execute("DESCRIBE users")
            user_columns = {row['Field'] for row in cursor.fetchall()}
            
            needs_user_migration = not all(
                col in user_columns for col in ['password', 'role', 'event_id']
            )
            
            if needs_user_migration:
                print("\n🔧 Actualizando tabla 'users'...")
                
                # Add password column if missing
                if 'password' not in user_columns:
                    print("  ➕ Agregando columna 'password'...")
                    cursor.execute(
                        "ALTER TABLE users ADD COLUMN password VARCHAR(255) DEFAULT 'produccionesfast2050' AFTER phone"
                    )
                
                # Add role column if missing
                if 'role' not in user_columns:
                    print("  ➕ Agregando columna 'role'...")
                    cursor.execute(
                        "ALTER TABLE users ADD COLUMN role ENUM('visor', 'moderador', 'speaker', 'administrador') DEFAULT 'visor' AFTER password"
                    )
                
                # Add event_id column if missing
                if 'event_id' not in user_columns:
                    print("  ➕ Agregando columna 'event_id'...")
                    cursor.execute(
                        "ALTER TABLE users ADD COLUMN event_id INT AFTER role"
                    )
                
                # Add index for better query performance
                print("  📊 Agregando índice para (email, event_id)...")
                try:
                    cursor.execute(
                        "ALTER TABLE users ADD INDEX idx_email_event (email, event_id)"
                    )
                except Exception as e:
                    if "Duplicate key name" in str(e):
                        print("    ℹ️  Índice ya existe, omitiendo...")
                    else:
                        raise
                
                print("  ✅ Tabla 'users' actualizada")
            else:
                print("  ℹ️  Tabla 'users' ya tiene todas las columnas necesarias")
            
            # Check if events table needs migration
            cursor.execute("DESCRIBE events")
            event_columns = {row['Field'] for row in cursor.fetchall()}
            
            needs_event_migration = (
                'title' not in event_columns or 
                'logo_url' not in event_columns or 
                'video_url' not in event_columns
            )
            
            if needs_event_migration:
                print("\n🔧 Actualizando tabla 'events'...")
                
                # Rename or add columns as needed
                if 'name' in event_columns and 'title' not in event_columns:
                    print("  🔄 Renombrando 'name' a 'title'...")
                    cursor.execute("ALTER TABLE events CHANGE COLUMN name title VARCHAR(255) NOT NULL")
                elif 'title' not in event_columns:
                    print("  ➕ Agregando columna 'title'...")
                    cursor.execute("ALTER TABLE events ADD COLUMN title VARCHAR(255) NOT NULL AFTER slug")
                
                if 'stream_url' in event_columns and 'video_url' not in event_columns:
                    print("  🔄 Renombrando 'stream_url' a 'video_url'...")
                    cursor.execute("ALTER TABLE events CHANGE COLUMN stream_url video_url VARCHAR(500)")
                elif 'video_url' not in event_columns:
                    print("  ➕ Agregando columna 'video_url'...")
                    cursor.execute("ALTER TABLE events ADD COLUMN video_url VARCHAR(500)")
                
                if 'description' in event_columns and 'logo_url' not in event_columns:
                    print("  🔄 Reemplazando 'description' con 'logo_url'...")
                    cursor.execute("ALTER TABLE events DROP COLUMN description")
                    cursor.execute("ALTER TABLE events ADD COLUMN logo_url VARCHAR(500)")
                elif 'logo_url' not in event_columns:
                    print("  ➕ Agregando columna 'logo_url'...")
                    cursor.execute("ALTER TABLE events ADD COLUMN logo_url VARCHAR(500)")
                
                print("  ✅ Tabla 'events' actualizada")
            else:
                print("  ℹ️  Tabla 'events' ya tiene todas las columnas necesarias")
            
            # Migrate data from event_staff to users if needed
            cursor.execute("SHOW TABLES LIKE 'event_staff'")
            if cursor.fetchone():
                print("\n🔄 Migrando datos de 'event_staff' a 'users'...")
                
                # Get event_staff data
                cursor.execute("SELECT user_id, event_id, role FROM event_staff")
                staff_rows = cursor.fetchall()
                
                if staff_rows:
                    print(f"  📦 Encontrados {len(staff_rows)} registros en event_staff")
                    
                    # Update users with role and event_id from event_staff
                    for row in staff_rows:
                        user_id = row['user_id']
                        event_id = row['event_id']
                        role = row['role']
                        
                        # Map old role names to new ones
                        role_map = {
                            'admin': 'administrador',
                            'moderator': 'moderador',
                            'speaker': 'speaker'
                        }
                        new_role = role_map.get(role, role)
                        
                        cursor.execute(
                            "UPDATE users SET role = %s, event_id = %s WHERE id = %s AND event_id IS NULL",
                            (new_role, event_id, user_id)
                        )
                    
                    print(f"  ✅ Datos migrados de event_staff a users")
                    print("  ⚠️  Puedes eliminar la tabla event_staff manualmente si ya no la necesitas")
                else:
                    print("  ℹ️  No hay datos para migrar")
            
            conn.commit()
            print("\n✅ ¡Migración completada exitosamente!")
            print("\n📌 Resumen del esquema actualizado:")
            print("   • users: ahora incluye 'password', 'role' y 'event_id'")
            print("   • events: ahora usa 'title', 'logo_url' y 'video_url'")
            print("   • El sistema ahora soporta múltiples eventos con usuarios aislados por evento")
            
    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_schema()
