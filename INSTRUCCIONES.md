# PYTHON TORNADO DEMO: FULL SCOPE SPECIFICATION

## 1. Project Context
Create a **Live Streaming Demo Platform** using **Python (Tornado)** and **MySQL** on Windows.
The system requires User Registration, a Video Player with Real-time interactions, Roles (Moderator/Speaker), and Analytics Reports.

## 2. Technical Stack
- **Backend:** Python 3.x, Tornado Web Server.
- **Database:** MySQL (via `pymysql` driver).
- **Frontend:** HTML5, CSS3, Vanilla JS (No frameworks).
- **Auth:** Cookie-based session after Registration.

## Timezone Policy (Importante)
- La base de datos almacena timestamps en **UTC**.
- La aplicación convierte a hora local usando `events.timezone` (IANA, por ejemplo `America/Mexico_City`) al momento de **presentar** datos (UI, WS, reportes/export).
- En `app/db.py` se fuerza `SET time_zone = '+00:00'` por conexión para que `NOW()` y `CURRENT_TIMESTAMP` sean consistentes.
- El runtime debe tener base de zonas horarias disponible (IANA). En contenedores mínimos o Windows, `ZoneInfo` puede fallar si falta tzdata; por eso el proyecto incluye `tzdata` en `requirements.txt` y el Dockerfile instala `tzdata` a nivel sistema.

## 3. Database Schema (Already created)
- `users`: id, name, email, phone.
- `chat_messages`: id, user_id, user_name, message.
- `questions`: id, user_id, user_name, question_text, status.
- `session_analytics`: id, user_id, start_time, last_ping, total_minutes.

Nota: el schema real incluye `events.timezone` y tablas adicionales (p.ej. `events`, `event_staff`).

## Roles por Evento (RBAC)
- `users.role` define rol **global**. Se usa `superadmin` (y por compatibilidad `administrador`) para ver/administrar todos los eventos.
- `event_staff` define permisos **por evento**:
    - `admin`: administra ese evento (configuración/toggle/reportes) y puede operar como moderator/speaker.
    - `moderator`: acceso a `/e/<slug>/mod`.
    - `speaker`: acceso a `/e/<slug>/speaker`.
- Un usuario con rol global `superadmin` ve todos los eventos (todas las slugs).

### Asignación de staff (superadmin)
API: `POST /api/admin/event-staff`
- Body JSON ejemplo:
    - `{ "event_id": 1, "email": "alguien@produccionesfast.com", "role": "admin" }`

Listar staff por evento: `GET /api/admin/event-staff?event_id=1`

Eliminar asignación: `DELETE /api/admin/event-staff?event_id=1&user_id=123`

## 4. Required Pages (Routes & Logic)

### A. Registration (`/`) - ENTRY POINT
- Form fields: **Name**, **Email**, **Phone**.
- **Logic:**
    - Check if email exists. If yes, log user in. If no, create user and log in.
    - Set a secure cookie with `user_id`.
    - Redirect to `/watch`.

### B. Player Room (`/watch`) - Protected
- **Layout:** Video Iframe (left), Tabs for Chat & Q&A (right).
- **Real-Time Logic:**
    - **Chat:** Send/Receive messages via WebSocket.
    - **Q&A:** Ask questions (User view). See approved questions.
    - **Heartbeat (Analytics):**
        - JavaScript must send a JSON `{type: 'ping'}` every 60 seconds via WebSocket.
        - Backend updates `session_analytics` table: Update `last_ping` and increment `total_minutes`.

### C. Moderator Dashboard (`/mod`)
- **Chat View:** See all messages.
- **Q&A Management:** List "Pending" questions with an "Approve" button.
- **Logic:** Clicking approve sends a WS message `{type: 'approve', id: ...}` which moves it to the Speaker view.

### D. Speaker Dashboard (`/speaker`)
- **View:** Clean, large font list of ONLY `status='approved'` questions. Real-time updates.

### E. Reports Section (`/reports`)
- **Tab 1: Registered Users:** Table showing Name, Email, Phone, Reg Date (Select from `users`).
- **Tab 2: Analytics:** Table showing User Name, Login Time, Last Active, **Total Minutes Watched** (Select from `session_analytics` JOIN `users`).

## 5. WebSocket Handler Logic (`ws`)
Handle JSON payloads:
1.  `chat`: Insert DB -> Broadcast to All.
2.  `ask`: Insert DB -> Broadcast to Moderators.
3.  `approve`: Update DB -> Broadcast to Speaker/Viewers.
4.  `ping`: Update `session_analytics` for the current `user_id`. Do NOT broadcast.

## 6. Deliverables
Generate the following files:
1.  `server.py`: Complete Tornado application with MySQL connection, Handlers, and WebSocket logic.
2.  `templates/register.html`: CSS styled registration form.
3.  `templates/watch.html`: Player with Chat/Q&A and **JS Heartbeat interval**.
4.  `templates/moderator.html`: Mod controls.
5.  `templates/speaker.html`: Speaker view.
6.  `templates/reports.html`: Tables for data reporting.