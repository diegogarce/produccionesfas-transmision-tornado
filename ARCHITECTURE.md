# Transmisión Tornado - Proyecto de Streaming en Vivo

Este documento sirve como un "mapa" técnico para que otros agentes de IA y desarrolladores puedan comprender rápidamente la estructura, el flujo de datos y los protocolos del proyecto.

---

## 1. Arquitectura de Alto Nivel
El sistema es una plataforma de streaming interactivo construida con **Python (Tornado)** que maneja conexiones WebSocket persistentes para interacciones en tiempo real.

- **Servidor Web:** Tornado (Asíncrono)
- **Base de Datos:** MySQL (Almacenamiento en UTC)
- **Caché/Sesiones:** Redis (Vía `session_service.py`)
- **Protocolo Tiempo Real:** WebSockets (`/ws`)

---

## 2. Mapa de Directorios
- `/app`: Código fuente principal del backend.
    - `/handlers`: Controladores de rutas HTTP y WebSocket.
    - `/services`: Lógica de negocio (DB, Analytics, Chat, Staff).
- `/templates`: Vistas HTML (Tornado Templates).
- `/static`: Archivos estáticos (JS, CSS, Imágenes).
- `/transmisiion`: Versiones estáticas o previas de la interfaz (referencia).

---

## 3. Flujo del Usuario
1. **Acceso:** El usuario entra vía `/e/<slug>` (Registro dinámico por evento).
2. **Autenticación:** El `RegistrationHandler` crea/valida al usuario y guarda la sesión en Redis + Cookie Segura.
3. **Transmisión:** Redirección a `/e/<slug>/watch` donde se carga el reproductor y se abre el WebSocket.
4. **Interacción:** El frontend envía mensajes JSON por el WS (Chat/Preguntas/Pings).
5. **Cierre:** Los administradores pueden finalizar el evento, lo que desconecta a todos los clientes.

---

## 4. Esquema de Base de Datos (Relaciones)
- `events`: Tabla maestra de eventos. Define slugs, URLs de stream y configuración visual.
- `users`: Usuarios globales.
- `event_staff`: Relación (N:M) entre `users` y `events` con roles específicos (`admin`, `moderator`, `speaker`).
- `chat_messages`: Mensajes vinculados a `user_id` y `event_id`.
- `questions`: Preguntas con estados (`pending`, `approved`, `rejected`, `read`).
- `session_analytics`: Seguimiento de tiempo de visualización (`total_minutes`) y pings de actividad.

---

## 5. Protocolo WebSocket (`/ws`)
Todos los mensajes son JSON con un campo `type`.

### Mensajes de Cliente -> Servidor
- `ping`: Actualiza `last_ping` en `session_analytics`.
- `chat`: Envía un nuevo mensaje al chat.
- `ask`: Envía una nueva pregunta para moderación.
- `approve` (Mod): Aprueba una pregunta para que el Speaker la vea.
- `reject` (Mod): Rechaza una pregunta.
- `read` (Speaker): Marca una pregunta aprobada como "leída".

### Mensajes de Servidor -> Cliente
- `chat`: Broadcast de mensaje nuevo a todos en el evento.
- `pending_question`: Notifica a moderadores de una nueva pregunta.
- `approved_question`: Notifica a todos (especialmente Speaker) de una pregunta aprobada.
- `active_sessions`: (A Mod/Reportes) Actualización del número de personas conectadas.
- `reports_metrics`: (A Reportes) Estadísticas generales del evento.

### Registro de Eventos Dinámico
- El administrador puede definir qué datos solicitar en el registro mediante un **Constructor de Formulario (Visual Form Builder)**.
- Este constructor genera un `registration_schema` en formato JSON que el backend procesa para validar y almacenar los datos en `event_registration_data`.
- Permite agregar campos personalizados con tipos específicos (text, email, tel, number) y marcarlos como obligatorios.

---

## 6. Configuración de Desarrollo
- **Entorno:** El archivo `.env` controla `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `REDIS_HOST`, y `COOKIE_SECRET`.
- **Zonas Horarias:** Se fuerza `+00:00` en MySQL. El backend convierte a la zona horaria definida en `events.timezone` antes de enviar datos al cliente.
- **Métricas:** El sistema expone métricas internas para monitorear latencia del IOLoop y conexiones activas.
