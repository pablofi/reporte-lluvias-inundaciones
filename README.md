# Reporte de Lluvias e Inundaciones

Herramienta web interna para elaborar reportes de México sobre una plantilla institucional PPTX.
El desarrollo es incremental. **Estado actual: FASE 01 — bootstrap**. Solo hay una página HTML,
un endpoint de salud y preparación de configuración y SQLite. No hay datos ni reportes meteorológicos.

## Arquitectura

Python 3.12, FastAPI, Jinja2, SQLAlchemy/SQLite, Pydantic, httpx y pytest.
HTML servido desde el backend; HTMX se incorporará únicamente cuando sea necesario.
Sin Node ni framework SPA. Docker es la ejecución normal en WSL/Linux y futura VM Ubuntu.

## Arranque en WSL

Requisitos: Git y Docker Engine con Compose v2, o Docker Desktop con integración WSL2.
Mantener el checkout en el sistema de archivos Linux de WSL.
Desde la raíz del repositorio:

```bash
cp .env.example .env
# El contenedor usa UID/GID 1000. Si tu usuario tiene otro UID/GID:
# sudo chown -R 1000:1000 data
# Aplicar solo a los directorios de datos de esta aplicación.
docker compose build
docker compose up -d --wait
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/
docker compose exec -T web python -m pytest
docker compose logs web
```

También se puede iniciar en primer plano con `docker compose up --build`.
Visitar `http://localhost:8000`. El puerto se publica solo en loopback.
Para detener: `docker compose down`. Los archivos de `./data` permanecen en el host.
El bind mount persiste SQLite en `data/database/app.db`; no hay tablas de negocio todavía.
El healthcheck consulta `/health` y usa el puerto configurado.
Si `APP_PORT` cambia, utilizar ese puerto también en curl y el navegador.

`.env` contiene configuración local, nunca se versiona. No se necesita ninguna credencial
para esta fase. OPENAI_API_KEY y OPENAI_MODEL están reservadas para fases futuras y no se usan.
`APP_HOST` se fuerza a `0.0.0.0` en Compose para permitir el acceso al contenedor.
`APP_TIMEZONE` es la zona de presentación; SQLite y el bootstrap aún no guardan timestamps.

## Desarrollo y tests locales

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev]'
cp .env.example .env  # Solo si .env no existe; preservar configuración existente.
python -m pytest
python -m app
```

Para recarga automática: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.
Ese comando fija host/puerto explícitamente. `python -m app` usa la configuración de entorno.
Las dependencias directas tienen versiones exactas; la imagen base y las dependencias transitivas
no están bloqueadas por digest/lockfile todavía.

## Estructura

- `app/main.py`, `config.py`, `db.py`: web, configuración y sesiones SQLAlchemy.
- `app/api`, `models`, `schemas`, `services`: módulos reservados para fases posteriores.
- `app/sources`, `meteorology`, `rendering`, `pptx`: separación de responsabilidades futura.
- `app/templates`, `static`: página inicial Jinja2 y CSS.
- `assets/template`, `reference`, `cartography`: recursos institucionales pendientes.
- `data/sources`, `uploads`, `reports`, `database`: datos persistentes ignorados por Git.
- `docs/`: especificación, arquitectura, fuentes, desarrollo y roadmap.
- `tests/`: salud y página inicial, ejecutables localmente o en el contenedor.

## Alcance

No se implementan scraping, monitor, cargas SEMAR, NOAA/NHC, GFS, OpenAI, análisis meteorológico,
riesgos, mapas, infografía, PowerPoint ni generación real de reportes.
No hay autenticación; este bootstrap no debe exponerse a Internet.
La plantilla y referencia institucional se incorporarán posteriormente.
Ver [especificación](docs/SPECIFICATION.md) y [roadmap](docs/ROADMAP.md).
