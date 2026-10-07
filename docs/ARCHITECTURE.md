# Arquitectura

Monolito sencillo Python 3.12/FastAPI con HTML Jinja2, configuración Pydantic Settings
(y SecretStr para el campo reservado de clave), sesiones SQLAlchemy y SQLite persistente.
El arranque valida acceso a SQLite con SELECT 1; no crea tablas de negocio ni datos ficticios.
`/health` informa salud básica del servicio, no estado meteorológico ni disponibilidad de fuentes.
La DB se comprueba al iniciar, no en cada healthcheck. No hay scheduler en fase 01.

Separación prevista:
- sources: adquisición y trazabilidad de originales.
- services/schemas: extracción, normalización, validación y coordinación.
- meteorology: análisis y riesgo, con datos vinculados a fuentes.
- rendering: cartografía e imagen institucional.
- pptx: presentación mediante plantilla preservada.
- models/db: almacenamiento; api/templates/static: acceso web.

Estos paquetes están vacíos deliberadamente. No se establecen contratos aún no definidos.
HTMX, autenticación, migraciones, GIS y bibliotecas PPTX quedan para fases correspondientes.
Docker publica loopback y ejecuta con UID/GID 1000; ./data requiere permisos de escritura para ese usuario.
Secretos solo mediante variables de entorno, sin envío al frontend. Timestamps futuros UTC;
presentación America/Mexico_City. Dependencias directas fijadas; lock transitivo pendiente.
