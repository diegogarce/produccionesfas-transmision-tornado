# Diagrama de Flujo - Arquitectura de Eventos

## Estructura General del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    MÚLTIPLES EVENTOS                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐    ┌──────────────────┐               │
│  │  Evento 1        │    │  Evento 2        │               │
│  │  slug: demo-fast │    │  slug: webinar-1 │               │
│  │  event_id: 1     │    │  event_id: 2     │               │
│  └──────────────────┘    └──────────────────┘               │
│           │                        │                          │
│           ├─── Users ──────────────┤                         │
│           │   (event_id scoped)    │                         │
│           │                        │                          │
│     ┌─────▼─────┐            ┌────▼──────┐                  │
│     │ maria@... │            │ maria@... │                   │
│     │ user_id:10│            │ user_id:15│                   │
│     │ role:visor│            │role:speaker│                  │
│     └───────────┘            └───────────┘                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Flujo de Registro

```
Usuario
  │
  ├─► GET /e/demo-fast
  │   (Formulario de registro)
  │
  ├─► POST /e/demo-fast
  │   name: Juan Pérez
  │   email: juan@produccionesfast.com
  │   phone: 555-0100
  │
  ├─► Validaciones:
  │   ✓ Email termina en @produccionesfast.com?
  │   ✓ Evento existe y está activo?
  │   ✓ Email ya registrado en ESTE evento?
  │
  ├─► SI ya existe → redirect /e/demo-fast/login?email=...
  │
  ├─► SI es nuevo →
  │   INSERT INTO users (
  │     name, email, phone, 
  │     role='visor', 
  │     event_id=1,
  │     password='produccionesfast2050'
  │   )
  │
  ├─► Set Cookies:
  │   user_id = 10
  │   user_name = "Juan Pérez"
  │   user_role = "visor"
  │   current_event_id = 1
  │
  └─► REDIRECT /e/demo-fast/watch
```

## Flujo de Login

```
Usuario
  │
  ├─► GET /e/demo-fast/login
  │   (Formulario de login)
  │
  ├─► POST /e/demo-fast/login
  │   email: maria@produccionesfast.com
  │   password: produccionesfast2050
  │
  ├─► Query DB:
  │   SELECT * FROM users 
  │   WHERE email = 'maria@...' 
  │   AND event_id = 1
  │
  ├─► Verificar password
  │
  ├─► Set Cookies basado en role:
  │   user_id, user_name, user_role, current_event_id
  │
  └─► REDIRECT según role:
      ├─ administrador → /admin/events
      ├─ speaker → /e/demo-fast/speaker
      ├─ moderador → /e/demo-fast/mod
      └─ visor → /e/demo-fast/watch
```

## Flujo de WebSocket (Chat Example)

```
Visor A (event_id=1)          WebSocket Server          Visor B (event_id=2)
     │                               │                         │
     ├─► CONNECT ws://host/ws?      │                         │
     │   role=viewer&event_id=1     │                         │
     │                               │   CONNECT ◄─────────────┤
     │                               │   role=viewer&event_id=2│
     │                               │                         │
     │   Store in pool:              │                         │
     │   {"viewer": [clientA]}       │   {"viewer": [clientB]} │
     │                               │                         │
     ├─► SEND: {type:"chat",         │                         │
     │   message:"Hola!"}            │                         │
     │                               │                         │
     │   INSERT chat_messages        │                         │
     │   (event_id=1)                │                         │
     │                               │                         │
     │   broadcast(message,          │                         │
     │   event_id=1)                 │                         │
     │                               │                         │
     │   Filter: only clients        │                         │
     │   with event_id=1             │                         │
     │                               │                         │
     ├─◄ RECEIVE: {type:"chat",...} │                         │
     │   (clientA gets it)           │   (clientB NO lo ve)    │
     │                               │                         │
```

## Aislamiento por Evento

```
                    ┌─────────────────────┐
                    │   WebSocket Pool    │
                    └─────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
      event_id=1        event_id=2        event_id=3
            │                 │                 │
    ┌───────┴────────┐ ┌──────┴──────┐ ┌───────┴────────┐
    │ Clients: 45    │ │ Clients: 23 │ │ Clients: 12    │
    │ Chat: isolated │ │ Chat: ...   │ │ Chat: ...      │
    │ Q&A: isolated  │ │ Q&A: ...    │ │ Q&A: ...       │
    │ Analytics: ... │ │ Analytics...│ │ Analytics: ... │
    └────────────────┘ └─────────────┘ └────────────────┘
```

## Roles y Permisos

```
┌────────────────────────────────────────────────────────────┐
│ ROL: administrador (event_id = NULL)                        │
├────────────────────────────────────────────────────────────┤
│ • Acceso a TODOS los eventos                                │
│ • Puede crear/editar eventos en /admin/events              │
│ • Ve todas las analíticas                                  │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ROL: speaker (event_id = X)                                 │
├────────────────────────────────────────────────────────────┤
│ • Solo evento X                                             │
│ • Ve preguntas APROBADAS en pantalla grande                │
│ • Puede marcar preguntas como "leídas"                     │
│ • Puede devolver pregunta a moderador                      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ROL: moderador (event_id = X)                               │
├────────────────────────────────────────────────────────────┤
│ • Solo evento X                                             │
│ • Ve preguntas PENDIENTES                                  │
│ • Aprueba/rechaza preguntas                                │
│ • Ve analíticas en tiempo real (usuarios activos)          │
│ • Ve todo el chat                                          │
│ • Puede bloquear usuarios (chat/Q&A/banear)                │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ROL: visor (event_id = X)                                   │
├────────────────────────────────────────────────────────────┤
│ • Solo evento X                                             │
│ • Ve video en vivo                                         │
│ • Puede chatear (si no está bloqueado)                     │
│ • Puede hacer preguntas (si no está bloqueado)            │
│ • Ve preguntas APROBADAS                                   │
└────────────────────────────────────────────────────────────┘
```

## Tracking de Analíticas

```
Usuario conecta a /e/demo-fast/watch
        │
        ├─► WebSocket CONNECT
        │   event_id=1, user_id=10
        │
        ├─► ensure_session_analytics(user_id=10, event_id=1)
        │   INSERT INTO session_analytics (user_id, event_id, start_time, last_ping)
        │   ON DUPLICATE KEY UPDATE last_ping=NOW()
        │
        ├─► Cada 60 segundos:
        │   JavaScript envía {type: "ping"}
        │
        ├─► Backend:
        │   UPDATE session_analytics
        │   SET last_ping=NOW(), 
        │       total_minutes = total_minutes + 1
        │   WHERE user_id=10 AND event_id=1
        │
        ├─► Broadcast actualización:
        │   broadcast({type: "active_sessions", sessions: [...]}, 
        │             roles={"moderator", "reports"}, 
        │             event_id=1)
        │
        └─► WebSocket DISCONNECT
            mark_session_inactive(user_id=10)
```

## Rutas URL - Mapa Completo

```
┌─ PÚBLICAS ────────────────────────────────────────────┐
│  /                      → HomeHandler                 │
│  /e/{slug}              → RegistrationHandler        │
│  /e/{slug}/login        → LoginHandler               │
│  /logout                → LogoutHandler              │
└───────────────────────────────────────────────────────┘

┌─ AUTENTICADAS (Cookie required) ──────────────────────┐
│  /e/{slug}/watch        → WatchHandler (visor)       │
│  /e/{slug}/mod          → ModeratorHandler           │
│  /e/{slug}/speaker      → SpeakerHandler             │
│  /e/{slug}/reports      → ReportsHandler             │
│  /admin/events          → EventsAdminHandler         │
└───────────────────────────────────────────────────────┘

┌─ API ENDPOINTS ───────────────────────────────────────┐
│  /api/ping              → APIPingHandler (heartbeat) │
│  /api/questions         → APIQuestionsHandler        │
│  /api/participants      → APIParticipantsHandler     │
│  /api/chats             → APIChatsHandler            │
│  /api/user/status       → APIUserStatusHandler       │
│  /api/admin/events      → APIEventsHandler           │
└───────────────────────────────────────────────────────┘

┌─ WEBSOCKET ───────────────────────────────────────────┐
│  /ws?role=X&event_id=Y  → LiveWebSocket              │
└───────────────────────────────────────────────────────┘
```

## Base de Datos - Relaciones

```
┌────────────────┐
│    events      │
│ ─────────────  │
│ id (PK)        │
│ slug (UNIQUE)  │◄──────────┐
│ title          │           │
│ logo_url       │           │ FK: event_id
│ video_url      │           │
│ is_active      │           │
└────────────────┘           │
                             │
┌────────────────────────┐   │
│       users            │   │
│ ────────────────────── │   │
│ id (PK)                │   │
│ name                   │   │
│ email                  │   │
│ phone                  │   │
│ password               │   │
│ role                   │   │
│ event_id (FK) ─────────┼───┘
│ chat_blocked           │
│ qa_blocked             │
│ banned                 │
└────┬───────────────────┘
     │                      
     │ FK: user_id         
     │                      
     ├─────────────────────────────────┐
     │                                 │
     │                                 │
┌────▼──────────────┐  ┌──────────────▼─────────┐
│  chat_messages    │  │  questions             │
│ ───────────────── │  │ ────────────────────── │
│ id (PK)           │  │ id (PK)                │
│ user_id (FK)      │  │ user_id (FK)           │
│ message           │  │ question_text          │
│ event_id          │  │ status                 │
│ created_at        │  │ event_id               │
└───────────────────┘  │ created_at             │
                       └────────────────────────┘
┌───────────────────────────┐
│  session_analytics        │
│ ───────────────────────── │
│ id (PK)                   │
│ user_id (FK)              │
│ event_id                  │
│ start_time                │
│ last_ping                 │
│ total_minutes             │
│ UNIQUE (user_id,event_id) │
└───────────────────────────┘
```

---

## Leyenda

- `→` : Flujo/Redirección
- `├─►` : Paso del proceso
- `◄─` : Respuesta/Retorno
- `PK` : Primary Key
- `FK` : Foreign Key
- `✓` : Validación exitosa
