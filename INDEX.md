# 📚 Índice de Documentación

Bienvenido a la documentación completa del sistema de transmisiones en vivo de Producciones Fast.

## 🚀 Para Empezar

Si es tu primera vez aquí, sigue estos pasos:

1. **[README.md](README.md)** - Inicio rápido y overview del proyecto
2. **[DESARROLLO.md](DESARROLLO.md)** - Guía práctica para configurar y desarrollar
3. **[ARQUITECTURA.md](ARQUITECTURA.md)** - Entender cómo funciona el sistema

## 📖 Documentación por Tipo

### Para Desarrolladores Nuevos
- 📄 **[README.md](README.md)** - Introducción, stack tecnológico, comandos básicos
- 🛠️ **[DESARROLLO.md](DESARROLLO.md)** - Setup, estructura del código, troubleshooting
- 📊 **[DIAGRAMAS.md](DIAGRAMAS.md)** - Diagramas visuales de flujos y arquitectura

### Para Entender la Arquitectura
- 🏗️ **[ARQUITECTURA.md](ARQUITECTURA.md)** - Documentación completa de diseño
  - Conceptos de eventos
  - Usuarios por evento
  - WebSocket y aislamiento
  - Roles y permisos
  - Seguridad
- 📊 **[DIAGRAMAS.md](DIAGRAMAS.md)** - Representación visual
  - Flujo de registro
  - Flujo de login
  - Comunicación WebSocket
  - Schema de base de datos

### Para Revisar Cambios
- 📝 **[RESUMEN_CAMBIOS.md](RESUMEN_CAMBIOS.md)** - Qué se cambió y por qué
  - Problema identificado
  - Solución implementada
  - Impacto de los cambios
  - Próximos pasos

### Especificaciones Originales
- 📋 **[INSTRUCCIONES.md](INSTRUCCIONES.md)** - Especificación técnica original del proyecto

## 🔍 Encuentra Información por Tema

### Setup y Configuración
- Instalación de dependencias → [DESARROLLO.md - Inicio Rápido](DESARROLLO.md#1-configuración-inicial)
- Variables de entorno → [DESARROLLO.md - Variables](DESARROLLO.md#variables-de-entorno)
- Inicializar base de datos → [DESARROLLO.md - Configuración](DESARROLLO.md#1-configuración-inicial)

### Base de Datos
- Schema actual → [init.sql](init.sql)
- Migración desde schema anterior → [migrate_schema.py](migrate_schema.py)
- Diagrama de relaciones → [DIAGRAMAS.md - Base de Datos](DIAGRAMAS.md#base-de-datos---relaciones)

### Conceptos de Eventos
- ¿Qué es un evento? → [ARQUITECTURA.md - Eventos](ARQUITECTURA.md#1-eventos-events)
- Usuarios por evento → [ARQUITECTURA.md - Usuarios](ARQUITECTURA.md#2-usuarios-por-evento-event-scoped-users)
- Aislamiento → [ARQUITECTURA.md - WebSocket](ARQUITECTURA.md#websocket-y-aislamiento-de-eventos)

### Registro y Login
- Flujo de registro → [DIAGRAMAS.md - Flujo de Registro](DIAGRAMAS.md#flujo-de-registro)
- Flujo de login → [DIAGRAMAS.md - Flujo de Login](DIAGRAMAS.md#flujo-de-login)
- Código de autenticación → [app/handlers/auth.py](app/handlers/auth.py)

### WebSocket y Real-Time
- Comunicación WebSocket → [ARQUITECTURA.md - WebSocket](ARQUITECTURA.md#websocket-y-aislamiento-de-eventos)
- Tipos de mensajes → [ARQUITECTURA.md - Mensajes](ARQUITECTURA.md#tipos-de-mensajes-websocket)
- Flujo visual → [DIAGRAMAS.md - WebSocket](DIAGRAMAS.md#flujo-de-websocket-chat-example)
- Código del handler → [app/handlers/ws.py](app/handlers/ws.py)

### Roles y Permisos
- Descripción de roles → [ARQUITECTURA.md - Roles](ARQUITECTURA.md#3-roles-de-usuario)
- Permisos por rol → [DIAGRAMAS.md - Roles](DIAGRAMAS.md#roles-y-permisos)
- Implementación → [app/handlers/base.py](app/handlers/base.py)

### Analíticas
- Sistema de tracking → [ARQUITECTURA.md - Analíticas](ARQUITECTURA.md#analíticas-por-evento)
- Flujo de tracking → [DIAGRAMAS.md - Tracking](DIAGRAMAS.md#tracking-de-analíticas)
- Código → [app/services/analytics_service.py](app/services/analytics_service.py)

### Seguridad
- Consideraciones → [ARQUITECTURA.md - Seguridad](ARQUITECTURA.md#seguridad)
- Checklist de producción → [ARQUITECTURA.md - Producción](ARQUITECTURA.md#️-consideraciones-de-seguridad-adicionales)
- Notas en migration → [migrate_schema.py](migrate_schema.py)

### Desarrollo de Features
- Agregar campos → [DESARROLLO.md - Nuevas Features](DESARROLLO.md#agregar-un-nuevo-campo-al-usuario)
- Mensajes WebSocket → [DESARROLLO.md - WebSocket](DESARROLLO.md#agregar-nuevo-tipo-de-mensaje-websocket)
- Testing → [DESARROLLO.md - Testing](DESARROLLO.md#testing-local)

## 🎯 Casos de Uso Rápidos

### "Quiero entender cómo funciona el sistema"
1. Lee [ARQUITECTURA.md](ARQUITECTURA.md)
2. Revisa [DIAGRAMAS.md](DIAGRAMAS.md) para visualizar

### "Quiero configurar mi entorno de desarrollo"
1. Sigue [DESARROLLO.md - Inicio Rápido](DESARROLLO.md#inicio-rápido)
2. Revisa [DESARROLLO.md - Troubleshooting](DESARROLLO.md#troubleshooting) si hay problemas

### "Quiero crear un nuevo evento"
1. Método UI → [DESARROLLO.md - Crear Evento](DESARROLLO.md#crear-un-nuevo-evento)
2. Método SQL → [DESARROLLO.md - Opción 2](DESARROLLO.md#crear-un-nuevo-evento)

### "Quiero migrar mi base de datos existente"
1. Ejecuta [migrate_schema.py](migrate_schema.py)
2. Lee [RESUMEN_CAMBIOS.md](RESUMEN_CAMBIOS.md) para contexto

### "¿Qué cambió en este PR?"
1. Lee [RESUMEN_CAMBIOS.md](RESUMEN_CAMBIOS.md)
2. Revisa commits en [git log](../../commits/)

## 📁 Estructura de Archivos

```
produccionesfas-transmision-tornado/
│
├── 📚 Documentación
│   ├── README.md              ← Empieza aquí
│   ├── INDEX.md               ← Este archivo
│   ├── ARQUITECTURA.md        ← Diseño del sistema
│   ├── DESARROLLO.md          ← Guía de desarrollo
│   ├── DIAGRAMAS.md           ← Visualizaciones
│   ├── RESUMEN_CAMBIOS.md     ← Log de cambios
│   └── INSTRUCCIONES.md       ← Spec original
│
├── 🗄️ Base de Datos
│   ├── init.sql               ← Schema inicial
│   ├── migrate_schema.py      ← Script de migración
│   └── fix_db.py              ← Fix específico (legacy)
│
├── 🐍 Código Python
│   ├── server.py              ← Punto de entrada
│   └── app/
│       ├── __init__.py        ← Configuración de rutas
│       ├── handlers/          ← HTTP handlers
│       │   ├── auth.py        ← Login/registro
│       │   ├── watch.py       ← Sala de visualización
│       │   ├── moderator.py   ← Dashboard moderador
│       │   ├── speaker.py     ← Dashboard speaker
│       │   ├── reports.py     ← Analíticas
│       │   ├── admin.py       ← Admin de eventos
│       │   └── ws.py          ← WebSocket handler
│       └── services/          ← Lógica de negocio
│           ├── events_service.py
│           ├── users_service.py
│           ├── chat_service.py
│           ├── questions_service.py
│           └── analytics_service.py
│
└── 🎨 Frontend
    └── templates/             ← HTML templates
        ├── register.html
        ├── login.html
        ├── watch.html
        ├── moderator.html
        ├── speaker.html
        └── reports.html
```

## 💡 Tips de Navegación

- **Usa Ctrl+F** para buscar términos específicos en cualquier documento
- **Los enlaces internos** te llevan directamente a las secciones relevantes
- **Los diagramas** en [DIAGRAMAS.md](DIAGRAMAS.md) son ASCII art, fáciles de copiar/modificar
- **Los ejemplos de código** están en bloques de código con syntax highlighting

## 🤝 Contribuir

Si vas a agregar features o hacer cambios:
1. Lee [ARQUITECTURA.md](ARQUITECTURA.md) para entender el diseño
2. Sigue las convenciones en [DESARROLLO.md](DESARROLLO.md)
3. Mantén el aislamiento por evento en cualquier feature nueva
4. Actualiza la documentación relevante

## 📞 Soporte

Si tienes dudas que no están cubiertas en la documentación:
1. Revisa [DESARROLLO.md - Troubleshooting](DESARROLLO.md#troubleshooting)
2. Busca en los archivos con `grep` (ejemplos en [DESARROLLO.md](DESARROLLO.md))
3. Contacta al administrador del proyecto

---

**Última actualización**: Febrero 2026  
**Versión del sistema**: Multi-evento con aislamiento por event_id
