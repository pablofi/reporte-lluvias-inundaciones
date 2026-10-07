# Arquitectura — FASE 02

Monolito Python 3.12/FastAPI/Jinja2 con SQLite persistente y SQLAlchemy. Sin nuevas dependencias.
El esquema aditivo se crea con initialize_database encapsulado; no hay Alembic porque no se modifica
un esquema previo de negocio. Futuras modificaciones necesitarán migraciones explícitas.

## Datos

Source registra clave única, nombre, organismo, tipo, URL oficial, habilitación, principal y timestamps.
SourceCheck registra cada intento: fecha UTC, HTTP, éxito, error seguro, validadores, emisión/hash,
cambio y referencia nullable al snapshot. SourceSnapshot conserva fecha de adquisición, emisión
nullable, vigencia nullable, hash, formato, ruta interna, URL y metadatos JSON. Índices por fuente/tiempo;
unique(source_id, content_hash) evita repetir versiones incluso si reaparecen.
UTCDateTime exige entrada aware y reconstruye UTC al leer SQLite, que no preserva offsets nativamente.

## Flujo

Registro idempotente al iniciar → adquisición por conector → SHA-256 → snapshot atómico si nuevo →
check persistido siempre. Los recursos SMN se reconsultarán aunque la página siga igual.
El texto NHC procede del bloque pre del producto oficial, sin interpretación ni resumen.
NHC usa ETag/Last-Modified cuando existen; 304 reutiliza snapshot. Sin archivo local, se suprimen
validadores para volver a descargarlo. Snapshots antiguos permanecen auditables.

Almacenamiento: data/sources/<key>/YYYY/MM/DD/<sha256>/original.txt o original.html,
metadata.json y recursos nombrados por hash y extensión. Escritura temporal, fsync y os.replace.
DB referencia el archivo privado. Fallos entre filesystem/DB pueden dejar archivos huérfanos;
no se eliminan automáticamente para conservar trazabilidad. No hay limpieza/retención en esta fase.

## Monitor

Una tarea asyncio con primer ciclo inmediato y espera SOURCE_CHECK_INTERVAL_MINUTES entre ciclos.
Lock async y flock no bloqueante coordinan ciclos y procesos del mismo host que comparten storage.
El CLI usa el mismo servicio. Un fallo individual queda registrado y no interrumpe otras fuentes.
Detención cancela la tarea; no hay cola distribuida ni soporte de réplicas multi-host.

## Seguridad y presentación

Solo URLs registradas y recursos HTTPS en hosts oficiales permitidos. Cada redirección se valida;
no se acepta URL del frontend. Timeout, tamaño máximo 20 MiB/recurso, hasta 30 recursos,
2 reintentos default con backoff para timeout/transporte/408/429/5xx seleccionados.
Datos originales privados: no se montan como static ni se publica storage_path en API.
Logs por fuente sin cuerpos ni mensajes de proxy con posibles secretos.
API devuelve UTC; HTML convierte a America/Mexico_City con meses españoles.
Snapshot VIGENTE tras fallo solo si último éxito reciente según configuración; no es validación
meteorológica ni verificación de autenticidad científica. Umbral provisional 24h por fuente.
Las fases SEMAR, extracción/normalización meteorológica, OpenAI, riesgo, mapas, render y PPTX no se iniciaron.
