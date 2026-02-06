# Producciones Fast - Plataforma de Transmisión en Vivo

Sistema de transmisión en vivo multi-evento construido con Python Tornado y MySQL.

## 🚀 Características

- **Multi-Evento**: Soporte para múltiples eventos simultáneos completamente aislados
- **Registro y Login por Evento**: Usuarios scoped a eventos específicos
- **WebSocket en Tiempo Real**: Chat, preguntas y respuestas, analíticas
- **Roles**: Visor, Moderador, Speaker, Administrador
- **Analíticas**: Tracking de sesiones y tiempo de visualización por evento

## 📚 Documentación

- **[ARQUITECTURA.md](ARQUITECTURA.md)** - Arquitectura completa basada en eventos
- **[DESARROLLO.md](DESARROLLO.md)** - Guía rápida de desarrollo
- **[INSTRUCCIONES.md](INSTRUCCIONES.md)** - Especificación técnica original

## ⚡ Inicio Rápido

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar base de datos
mysql -u root -p < init.sql

# 3. O migrar DB existente
python3 migrate_schema.py

# 4. Ejecutar servidor
python3 server.py
```

Servidor disponible en: `http://localhost:8888`

## 🔑 Acceso por Defecto

- **Email**: `diego@produccionesfast.com`
- **Password**: `produccionesfast2050`
- **URL Admin**: `http://localhost:8888/login`

## 📦 Stack Tecnológico

- **Backend**: Python 3.x + Tornado Web Server
- **Database**: MySQL (PyMySQL)
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Real-time**: WebSocket
- **Auth**: Cookie-based sessions

## 🏗️ Estructura del Proyecto

```
app/
├── handlers/      # HTTP request handlers
├── services/      # Business logic
├── config.py      # Configuration
└── db.py          # Database connection

templates/         # HTML templates
server.py          # Entry point
init.sql           # Database schema
migrate_schema.py  # Migration script
```

## 📝 Licencia

© 2026 Producciones Fast