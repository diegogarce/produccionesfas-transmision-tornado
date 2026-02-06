# Arquitectura Basada en Eventos

## Resumen
Este sistema implementa una **plataforma de transmisión en vivo multi-evento** donde cada evento es completamente independiente y tiene sus propios usuarios, chat, preguntas y analíticas.

## Conceptos Clave

### 1. Eventos (Events)
Cada evento representa una transmisión en vivo independiente con:
- **Slug único**: Identificador URL-friendly (ej: `demo-fast`)
- **Título**: Nombre del evento
- **Logo**: URL del logo del evento
- **Video**: URL de la transmisión (YouTube embed, etc.)
- **Estado**: Activo/Inactivo

### 2. Usuarios por Evento (Event-Scoped Users)
Los usuarios están **aislados por evento**:
- Un mismo email puede registrarse en múltiples eventos
- Cada registro crea una entrada separada en la base de datos
- El `event_id` en la tabla `users` determina a qué evento pertenece el usuario
- Los usuarios globales (administradores) tienen `event_id = NULL` y pueden acceder a todos los eventos

### 3. Roles de Usuario
- **visor**: Usuario regular que ve la transmisión, puede hacer preguntas y chatear
- **moderador**: Aprueba/rechaza preguntas, ve métricas de audiencia en tiempo real
- **speaker**: Ve las preguntas aprobadas en pantalla grande
- **administrador**: Acceso completo a todos los eventos, puede crear/editar eventos

## Flujo de Registro y Login

### Registro (`/e/{slug}`)
1. Usuario visita `/e/demo-fast` (página de registro del evento)
2. Llena formulario: nombre, email, teléfono
3. Sistema valida:
   - Email debe terminar en `@produccionesfast.com` (restricción de dominio)
   - Verifica si el email ya existe para este evento específico
4. Si el email existe para este evento → redirige a login
5. Si es nuevo → crea usuario con `role='visor'` y `event_id` del evento
6. Establece cookies de sesión y redirige a `/e/{slug}/watch`

### Login (`/e/{slug}/login`)
1. Usuario ingresa email y contraseña genérica (`produccionesfast2050`)
2. Sistema busca usuario por `email` Y `event_id` del evento
3. Si es administrador global (`event_id IS NULL`) → puede entrar a cualquier evento
4. Si autenticación exitosa:
   - Establece cookies: `user_id`, `user_name`, `user_role`, `current_event_id`
   - Redirige según rol:
     - `administrador` → `/admin/events`
     - `speaker` → `/e/{slug}/speaker`
     - `moderador` → `/e/{slug}/mod`
     - `visor` → `/e/{slug}/watch`

## Rutas por Evento

Todas las rutas están scoped al evento usando el slug:

```
/e/{slug}/         → Registro para el evento
/e/{slug}/login    → Login al evento
/e/{slug}/watch    → Sala de visualización (visor)
/e/{slug}/mod      → Dashboard de moderador
/e/{slug}/speaker  → Dashboard de speaker
/e/{slug}/reports  → Reportes y analíticas
```

## WebSocket y Aislamiento de Eventos

### Conexión WebSocket
```javascript
ws://domain/ws?role=viewer&event_id=1
```

El `event_id` se pasa como parámetro para aislar las comunicaciones:
- Los mensajes de chat solo se envían a usuarios del mismo evento
- Las preguntas solo se muestran a moderadores/speakers del mismo evento
- Las analíticas solo cuentan usuarios del evento específico

### Tipos de Mensajes WebSocket

#### Cliente → Servidor
```json
{"type": "chat", "message": "Hola!"}
{"type": "ask", "question": "¿Cuándo empieza?"}
{"type": "approve", "id": 123}  // Solo moderadores
{"type": "reject", "id": 123}   // Solo moderadores
{"type": "read", "id": 123}     // Solo speakers
{"type": "ping"}                // Heartbeat cada 60s
```

#### Servidor → Cliente
```json
{"type": "chat", "user_name": "Juan", "message": "Hola!", "timestamp": "14:30"}
{"type": "pending_question", "id": 123, "question": "..."} // Solo a moderadores
{"type": "approved_question", "id": 123, "question": "..."} // A todos
{"type": "active_sessions", "sessions": [...]} // Analíticas
{"type": "event_closed", "message": "Transmisión finalizada"} // Cierre de evento
```

## Analíticas por Evento

### Tracking de Sesión
- Cuando un visor se conecta → `session_analytics` registra `user_id` + `event_id`
- Cada ping (60s) actualiza `last_ping` e incrementa `total_minutes`
- Las analíticas están completamente aisladas por evento

### Métricas Disponibles
1. **Usuarios Activos**: Viewers conectados ahora mismo (WebSocket abierto)
2. **Total Participantes**: Todos los que se registraron al evento
3. **Tiempo de Visualización**: Minutos acumulados por usuario

## Seguridad

### Restricción de Dominio
```python
if not email.endswith("@produccionesfast.com"):
    return error("Registro restringido")
```

### Controles de Acceso
- Usuarios pueden ser bloqueados del chat (`chat_blocked`)
- Usuarios pueden ser bloqueados de Q&A (`qa_blocked`)
- Usuarios pueden ser baneados completamente (`banned`)

### Cierre de Eventos
Cuando un evento se marca como `is_active = 0`:
- Nuevos usuarios no pueden registrarse
- Visores no pueden entrar (excepto staff)
- Todos los WebSockets del evento se desconectan automáticamente

### ⚠️ Consideraciones de Seguridad Adicionales

**Para Producción, se recomienda implementar:**

1. **Password Hashing**: 
   - Actualmente las contraseñas se guardan en texto plano
   - **IMPLEMENTAR**: bcrypt o argon2 para hash de contraseñas
   - Modificar `auth.py` para hashear en registro y verificar en login

2. **Secrets Management**:
   - No incluir `COOKIE_SECRET` en el código
   - Usar variables de entorno o gestores de secretos
   - Rotar secretos periódicamente

3. **HTTPS Obligatorio**:
   - Forzar HTTPS en producción
   - WebSocket debe usar WSS (secure)
   - Configurar headers de seguridad (HSTS, CSP, etc.)

4. **Rate Limiting**:
   - Limitar intentos de login por IP
   - Limitar mensajes de chat/preguntas por usuario
   - Prevenir flood de conexiones WebSocket

5. **Input Validation**:
   - Sanitizar todos los inputs de usuario
   - Validar formato de email más estrictamente
   - Escapar contenido en templates para prevenir XSS

6. **SQL Injection**:
   - Actualmente usa consultas parametrizadas (✅ correcto)
   - Mantener esta práctica en todas las queries

7. **Session Security**:
   - Implementar timeout de sesión
   - Regenerar session ID después de login
   - Secure y HttpOnly cookies en producción

## Esquema de Base de Datos

### users
```sql
id, name, email, phone, password, role, event_id,
chat_blocked, qa_blocked, banned, created_at
```
- `event_id = NULL` → Usuario global (administrador)
- `event_id = N` → Usuario específico del evento N

### events
```sql
id, slug, title, logo_url, video_url, is_active, created_at
```

### questions
```sql
id, user_id, user_name, question_text, status, event_id, created_at
```
- `status`: 'pending' → 'approved' → 'read'

### chat_messages
```sql
id, user_id, user_name, message, event_id, created_at
```

### session_analytics
```sql
id, user_id, event_id, start_time, last_ping, total_minutes
```
- UNIQUE KEY (user_id, event_id) → Un registro por usuario por evento

## Ejemplo de Uso

### Crear un Nuevo Evento
1. Admin accede a `/admin/events`
2. Crea evento con slug `webinar-marzo-2026`
3. Comparte URL: `https://domain.com/e/webinar-marzo-2026`

### Asistentes se Registran
1. Usuarios visitan `/e/webinar-marzo-2026`
2. Se registran con email `@produccionesfast.com`
3. Son redirigidos a `/e/webinar-marzo-2026/watch`

### Durante la Transmisión
- Visores envían preguntas y chatean
- Moderador aprueba preguntas desde `/e/webinar-marzo-2026/mod`
- Speaker ve preguntas aprobadas en `/e/webinar-marzo-2026/speaker`
- Sistema trackea tiempo de visualización automáticamente

### Después del Evento
1. Admin marca evento como inactivo
2. Todos los WebSockets se cierran
3. Datos quedan guardados en `/e/webinar-marzo-2026/reports`

## Ventajas de esta Arquitectura

1. **Escalabilidad**: Múltiples eventos simultáneos sin conflictos
2. **Aislamiento**: Datos completamente separados por evento
3. **Flexibilidad**: Mismo email puede participar en diferentes eventos
4. **Simplicidad**: URLs intuitivas y fáciles de compartir
5. **Analíticas**: Métricas precisas por evento

## Migración

Si tienes una base de datos existente con el esquema anterior, ejecuta:

```bash
python3 migrate_schema.py
```

Esto agregará las columnas faltantes y migrará datos de `event_staff` a `users`.
