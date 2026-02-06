# Guía Rápida de Desarrollo

## Inicio Rápido

### 1. Configuración Inicial

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env  # (si existe)
# Editar .env con tu configuración de DB

# Inicializar la base de datos
mysql -u root -p < init.sql

# O si ya tienes una DB existente, migrar:
python3 migrate_schema.py
```

### 2. Ejecutar el Servidor

```bash
python3 server.py
```

El servidor estará disponible en `http://localhost:8888`

## Flujos Principales

### Crear un Nuevo Evento

**Opción 1: Via Admin UI**
1. Accede como admin: `http://localhost:8888/login`
   - Email: `diego@produccionesfast.com`
   - Password: `produccionesfast2050`
2. Ve a `/admin/events`
3. Click en "Crear Nuevo Evento"
4. Llena: slug, título, logo URL, video URL

**Opción 2: Via SQL Directa**
```sql
INSERT INTO events (slug, title, logo_url, video_url, is_active)
VALUES (
    'mi-evento',
    'Mi Evento de Prueba',
    'https://example.com/logo.png',
    'https://www.youtube.com/embed/VIDEO_ID',
    1
);
```

### Agregar un Staff Member (Moderador/Speaker)

```sql
-- Primero, crear/obtener el user_id
INSERT INTO users (name, email, password, role, event_id)
VALUES (
    'María López',
    'maria@produccionesfast.com',
    'produccionesfast2050',
    'moderador',  -- o 'speaker'
    1  -- ID del evento
);
```

### Rutas de Prueba

| Rol | URL de Acceso |
|-----|---------------|
| Visor | `/e/demo-fast` (registro) → `/e/demo-fast/watch` |
| Moderador | `/e/demo-fast/login` → `/e/demo-fast/mod` |
| Speaker | `/e/demo-fast/login` → `/e/demo-fast/speaker` |
| Admin | `/login` → `/admin/events` |

## Estructura del Código

```
app/
├── __init__.py           # Configuración de rutas
├── config.py             # Configuración general
├── db.py                 # Conexión a MySQL
├── handlers/             # Controladores HTTP
│   ├── auth.py          # Registro y login
│   ├── watch.py         # Sala de visualización
│   ├── moderator.py     # Dashboard moderador
│   ├── speaker.py       # Dashboard speaker
│   ├── reports.py       # Analíticas
│   ├── admin.py         # Admin de eventos
│   └── ws.py            # WebSocket handler
└── services/            # Lógica de negocio
    ├── events_service.py
    ├── users_service.py
    ├── chat_service.py
    ├── questions_service.py
    └── analytics_service.py

templates/               # Templates HTML
├── register.html
├── login.html
├── watch.html
├── moderator.html
├── speaker.html
└── reports.html

server.py               # Punto de entrada
init.sql                # Schema inicial
migrate_schema.py       # Script de migración
```

## Desarrollo de Nuevas Features

### Agregar un Nuevo Campo al Usuario

1. **Actualizar Schema**:
```sql
ALTER TABLE users ADD COLUMN mi_campo VARCHAR(255);
```

2. **Actualizar Registration Handler** (`app/handlers/auth.py`):
```python
mi_campo = self.get_body_argument("mi_campo", strip=True)
cursor.execute(
    "INSERT INTO users (..., mi_campo) VALUES (..., %s)",
    (..., mi_campo)
)
```

3. **Actualizar Template** (`templates/register.html`):
```html
<input type="text" name="mi_campo" required>
```

### Agregar Nuevo Tipo de Mensaje WebSocket

1. **Cliente** (en `templates/watch.html` o similar):
```javascript
ws.send(JSON.stringify({
    type: "mi_nuevo_mensaje",
    data: "..."
}));
```

2. **Servidor** (`app/handlers/ws.py`):
```python
def on_message(self, message):
    # ...
    elif msg_type == "mi_nuevo_mensaje":
        data = payload.get("data")
        # Procesar...
        broadcast({"type": "respuesta", "data": data}, event_id=self.event_id)
```

3. **Cliente - Recibir** (JavaScript):
```javascript
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === "respuesta") {
        console.log(data.data);
    }
};
```

## Testing Local

### Simular Múltiples Usuarios

1. Abre ventanas de incógnito separadas
2. Registra diferentes usuarios:
   - Usuario 1: `viewer1@produccionesfast.com`
   - Usuario 2: `viewer2@produccionesfast.com`
   - etc.

### Probar WebSocket

```javascript
// En la consola del navegador
ws.send(JSON.stringify({type: "chat", message: "Test"}));
```

### Verificar Analíticas

```sql
-- Ver sesiones activas
SELECT u.name, sa.start_time, sa.last_ping, sa.total_minutes
FROM session_analytics sa
JOIN users u ON sa.user_id = u.id
WHERE sa.event_id = 1;
```

## Troubleshooting

### WebSocket no conecta

1. Verificar que el servidor esté corriendo
2. Revisar la consola del navegador
3. Verificar que las cookies estén establecidas:
   - `user_id`
   - `current_event_id`

### Usuario no puede registrarse

1. Verificar restricción de dominio: email debe terminar en `@produccionesfast.com`
2. Verificar que el evento esté activo (`is_active = 1`)

### Migración de DB falla

```bash
# Ver estado actual de la DB
mysql -u root -p -e "USE transmision_tornado; DESCRIBE users;"

# Aplicar manualmente si es necesario
mysql -u root -p transmision_tornado < init.sql
```

## Variables de Entorno

```bash
# .env
DB_HOST=db.transmisionesfast.com
DB_USER=root
DB_PASSWORD=Pr0ducc10n35F45t2050
DB_NAME=transmisionesfast_tornado
COOKIE_SECRET=Pr0ducc10n35F45t2050
```

## Comandos Útiles

```bash
# Ver logs del servidor
python3 server.py | tee server.log

# Resetear DB (¡CUIDADO!)
mysql -u root -p -e "DROP DATABASE transmision_tornado; CREATE DATABASE transmision_tornado;"
mysql -u root -p transmision_tornado < init.sql

# Backup de DB
mysqldump -u root -p transmision_tornado > backup_$(date +%Y%m%d).sql

# Ver usuarios conectados en tiempo real
mysql -u root -p -e "
  SELECT COUNT(*) as activos 
  FROM session_analytics 
  WHERE last_ping > NOW() - INTERVAL 2 MINUTE 
  AND event_id = 1;
"
```

## Recursos Adicionales

- [ARQUITECTURA.md](ARQUITECTURA.md) - Documentación completa de la arquitectura
- [INSTRUCCIONES.md](INSTRUCCIONES.md) - Especificación original del proyecto
- [Tornado Docs](https://www.tornadoweb.org/) - Documentación de Tornado

## Contacto

Para preguntas o soporte, contactar a: `diego@produccionesfast.com`
