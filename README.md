# Reporte de Lluvias e Inundaciones

Aplicación web interna para futuros reportes de México sobre una plantilla institucional PPTX.
Desarrollo incremental: **FASE 02 — monitor de fuentes automáticas** implementada; FASE 03 no iniciada.
La interfaz es temporal. No se generan reportes ni se interpreta meteorología.

## Arquitectura

Python 3.12, FastAPI, Jinja2, SQLAlchemy/SQLite, Pydantic Settings, httpx y pytest.
Conectores separados del transporte HTTP, monitor async sin cola distribuida, snapshots atómicos
con SHA-256 e historial en SQLite. No se añadieron dependencias ni framework frontend.

## Arranque en WSL

Requisitos: Git y Docker Engine con Compose v2, o Docker Desktop con integración WSL2.
Checkout dentro del filesystem Linux de WSL. Desde la raíz:

```bash
cp .env.example .env  # Solo si no existe; preservar configuración local.
# El contenedor usa UID/GID 1000; data debe ser escribible por ese usuario.
# Si es necesario, aplicar sudo chown -R 1000:1000 data solo a datos de esta aplicación.
docker compose build
docker compose up -d --wait
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/sources
docker compose exec -T web python -m pytest
```

También `docker compose up --build` en primer plano. Visitar `http://localhost:8000`.
El puerto se publica solo en loopback; ajustar URLs si cambia APP_PORT.
Para detener: `docker compose down`. `./data` persiste SQLite y snapshots en el host.
La imagen ejecuta un usuario no root y tiene healthcheck de /health.

El monitor inicia al arrancar, realiza un primer ciclo y luego espera 15 minutos después de cada
ciclo, configurables con SOURCE_CHECK_INTERVAL_MINUTES. Fallos individuales no detienen otros conectores.
No ejecutar múltiples réplicas en hosts diferentes. Un lock de archivo Linux coordina servidor y CLI
que comparten data; el scheduler se cancela limpiamente al apagar. Los ciclos concurrentes manuales
reciben 409. Para pruebas operativas deterministas se puede desactivar el scheduler con
SOURCE_MONITOR_ENABLED=false; los checks manuales siguen disponibles.

## Comprobación real explícita

```bash
curl --fail -X POST http://localhost:8000/api/sources/check
curl --fail -X POST http://localhost:8000/api/sources/nhc_atlantic_twd/check
docker compose exec -T web python -m app.cli check-sources
```

La CLI imprime resumen por fuente y devuelve 0 si todas tuvieron éxito, 1 si alguna falló,
2 si el monitor está ocupado. pytest nunca utiliza Internet. Un HTTP 200 en el POST significa
ciclo realizado; revisar success/error_message de cada fuente, no inferir éxito de adquisición global.
La tabla temporal muestra fuentes, comprobación, emisión detectada, estado y cambios.

## Configuración y estados

.env.example recoge todas las variables. No se requieren claves; OPENAI_API_KEY y OPENAI_MODEL
siguen reservadas y no se utilizan. SECRETOS no se versionan ni se entregan al frontend.
SOURCE_MAX_AGE_HOURS configura por clave la edad desde detected_issue_time o, si falta, fetched_at;
default 24 horas operativo provisional, sin afirmar vigencia meteorológica. Emisiones y vigencias
desconocidas quedan null. UTC aware en almacenamiento/API; America/Mexico_City en HTML.

- ACTUALIZADA: última comprobación exitosa con contenido diferente al snapshot anterior.
- VIGENTE: éxito sin cambio o snapshot reutilizable tras fallo dentro del umbral configurado.
- NO_DISPONIBLE_OBSOLETA: sin snapshot local utilizable o producto fuera del umbral.

SHA-256 usa bytes exactos de texto NHC extraído. En SMN compara el producto: texto normalizado del
Pronóstico General y hashes binarios de sus recursos; para tormentas, conjunto ordenado de hashes
de imágenes/productos y emisión inequívoca cuando existe. Navbar/footer/banners no son parte del hash.
El HTML original de la primera adquisición de cada versión se conserva y wrapper_sha256 es auditoría.
La estrategia smn_product_v2 sustituye al hash de envoltura anterior; los snapshots históricos se conservan
sin reescribirlos. La primera adquisición puede crear una representación canónica vinculada al snapshot anterior;
si el archivo permite demostrar equivalencia, changed permanece false y fetched_at no se renueva.
La misma adquisición no crea otro snapshot; una versión reaparecida también reutiliza el archivo existente.

## Desarrollo local

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev]'
python -m pytest
python -m app
# Prueba de Internet separada:
python -m app.cli check-sources
```

Dependencias directas fijadas; imagen base y transitivas aún sin lock/digest.
Para reload: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.

## Estructura

- app/models/sources.py: Source, SourceCheck, SourceSnapshot y timestamps UTC.
- app/sources: registro idempotente, transporte y cuatro conectores.
- app/services: monitor, estados y almacenamiento; app/api: consulta y check manual.
- app/templates y static: tabla temporal ligera; app/cli.py: diagnóstico real.
- assets/template, reference, cartography: recursos institucionales pendientes.
- data/sources, uploads, reports, database: almacenamiento persistente fuera de Git.
- docs: especificación, arquitectura, fuentes, desarrollo y roadmap; tests: suite offline.

## Alcance y limitaciones

Consultar docs/DATA_SOURCES.md para URLs, formatos y limitaciones. La red de esta nube requiere
override de proxy/DNS/CA externo al checkout; no desactivar TLS. Dockerfile admite CA BuildKit
opcional pip_ca, sin copiarla a la imagen. WSL/Ubuntu con red normal usa Compose estándar.
Las restricciones de esta nube no representan WSL: el usuario verificó HTTP 200 para las cuatro URLs,
descarga de las cinco imágenes de tormentas y emisiones NHC. El Pronóstico General fallaba al depender
del contenedor HTML; ahora se reconoce por marcadores propios y se detecta el PDF enlazado.
La corrección está validada offline; **la validación real definitiva debe repetirse en WSL**.
Solo Pronóstico General es is_primary=true; tormentas/NHC son complementarias. Un HTTP 200 o 304
repetido no rejuvenece la emisión/fetched_at del snapshot.
Sin autenticación: usar solo en entorno interno, sin exposición pública.
No hay SEMAR uploads, OpenAI, análisis/riesgo, GFS, cartografía, infografía, PPTX ni interfaz definitiva.
