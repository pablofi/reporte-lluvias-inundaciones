# Desarrollo — FASE 02

Seguir AGENTS.md. Python 3.12, Docker normal en WSL/Linux, rama codex/02-source-monitor.
No avanzar a fase 03. No versionar .env, DB ni datos operativos. No se necesitan claves.

## Checks offline

```bash
python -m pytest
docker compose build
docker compose up -d --wait
docker compose exec -T web python -m pytest
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/sources
```

Tests utilizan DB/directorio temporales y httpx.MockTransport. Una fixture autouse bloquea
transportes reales, y el scheduler se desactiva en pruebas web. Se conservan tests de fase 01.
Se prueban idempotencia, snapshots, dedup, reaparición de una versión, 304, fallo independiente,
UTC, estados/reutilización, persistencia/reinicio, API/manual, locks, reintentos, bloqueo de
redirecciones no oficiales, parser de emisión y ciclo/cancelación de scheduler.
Fixtures son cabeceras de emisión y bytes de prueba, no datos meteorológicos operativos.

## Prueba real explícita, nunca dentro de pytest

```bash
docker compose exec -T web python -m app.cli check-sources
# Local:
python -m app.cli check-sources
# API:
curl --fail -X POST http://localhost:8000/api/sources/check
curl --fail -X POST http://localhost:8000/api/sources/nhc_atlantic_twd/check
```

Revisar success y error_message por fuente; HTTP 200 del ciclo no garantiza acceso a todas.
Un ciclo ya activo devuelve 409 en API; CLI devuelve 2. Para CLI exclusivo, puede desactivarse
SOURCE_MONITOR_ENABLED en .env y recrearse web. SOURCE_CHECK_INTERVAL_MINUTES default 15.

Logs: check_started, check_success, check_unchanged, check_changed, check_failed con clave de fuente,
sin cuerpos ni secretos. GET /api/sources/{key} devuelve 20 checks y snapshots recientes.
GET /api/sources/{key}/snapshots pagina con limit (1–100) y offset no negativo.
No se sirve data ni se aceptan URLs del navegador.

## Redes restringidas

En esta nube el build requiere un override externo para proxy, resolución DNS y CA, enlazado localmente como docker-compose.override.yml ignorado por Git; permite usar docker compose build también aquí.
Dockerfile usa un secreto BuildKit opcional pip_ca; no lo copia a la imagen. El runtime necesita
su proxy/CA igualmente cuando la red lo exige. Mantener TLS verificado. No versionar datos de
proxy ni rutas del entorno. En WSL/Ubuntu con red normal usar Compose estándar del README.

Umbral SOURCE_MAX_AGE_HOURS por clave: edad desde detected_issue_time o fetched_at, no validez científica.
Modificar esos umbrales requiere revisión operativa. Creación de tablas automática encapsulada;
las migraciones de cambios futuros deberán ser explícitas. No implementar retención ni borrar
snapshots para hacer pasar tests.


Fixtures SMN de tests/fixtures son representaciones sintéticas de los marcadores y nombres
reportados en WSL, no copias del HTML oficial vigente. Prueban selección sin article, PDF,
fechas españolas inequívocas, hash de producto y antigüedad. Repetir la CLI real en WSL tras
esta corrección; los rechazos de Codex cloud no sustituyen esa validación.
