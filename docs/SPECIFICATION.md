# Especificación funcional acordada

## Producto futuro

Aplicación web interna «Reporte de Lluvias e Inundaciones» para México.
El producto final es un `.pptx` basado SIEMPRE en la plantilla institucional existente de dos diapositivas.
Conservar exactamente la plantilla y únicamente actualizar fecha/hora de ambas diapositivas,
generar una imagen nueva para la diapositiva 2 e insertarla en la ubicación correspondiente.
Plantilla y referencia visual pendientes de incorporación.

La imagen de la diapositiva 2 solo contiene mapa de México con precipitación estimada,
leyenda de lluvia acumulada, tabla de acumulados y tabla de riesgo potencial de inundaciones.
No contiene título general adicional, periodo de validez adicional, síntesis meteorológica,
banda de prioridad ni pie de fuentes. Aproximar su aspecto a la referencia institucional futura.
No incorporar ríos/presas. El mapa solo representa precipitación meteorológica, sin huracanes,
frentes, bajas presiones, ondas, trayectorias ni simbología sinóptica.

## Operación futura

Comprobar fuentes automáticas cada 15 minutos:
CONAGUA/SMN Pronóstico Meteorológico General y Aviso de Potencial de Tormentas;
NOAA/NHC Atlantic y Eastern North Pacific Tropical Weather Discussion;
NOAA/NCEP GFS como soporte geoespacial de precipitación.
Cargar manualmente Síntesis SEMAR GOLF y Síntesis SEMAR PAC; ambas son obligatorias.

Estados: `ACTUALIZADA`, `VIGENTE`, `NO_DISPONIBLE_OBSOLETA`.
Una fuente VIGENTE puede reutilizarse. Una fuente principal NO_DISPONIBLE_OBSOLETA bloquea generación.
GFS es auxiliar: su fallo no bloquea; implementar posteriormente un modo degradado.
No se han definido todavía umbrales de vigencia ni algoritmos de riesgo.

Reportes ordinarios a las 06:00 y 18:00, con generación manual en cualquier momento.
Presentación en `America/Mexico_City`, timestamps internos UTC con zona horaria.
Fecha visible: `07 OCT 2026 - 06:00 h`.
Archivo: `REPORTE_LLUVIAS_INUNDACIONES_YYYY-MM-DD_HHMM.pptx`, con fecha/hora de presentación;
ejemplo `REPORTE_LLUVIAS_INUNDACIONES_2026-10-07_0600.pptx`.

## Fase 01

Python 3.12, FastAPI, Jinja2, SQLite, SQLAlchemy, Pydantic, httpx, pytest, Docker y Compose.
HTMX cuando sea necesario en fases posteriores. Sin React/Vue/Angular/Node sin aprobación expresa.
Despliegue inicial WSL, migrable a Ubuntu.

`GET /health`: HTTP 200 y JSON `{"status":"ok","service":"reporte-lluvias-inundaciones"}`.
`GET /`: HTML con «Sistema de Reporte de Lluvias e Inundaciones» y «Fase inicial del sistema».
Configuración de entorno, persistencia de ./data, usuario no root y healthcheck Docker.
Tests locales y en contenedor. No hay interfaz definitiva, datos simulados, scraping,
llamadas OpenAI, procesamiento meteorológico, mapas o generación PowerPoint/reportes.
La fase 02 requiere nueva instrucción tras revisión manual.


## Fase 02 implementada

Registro idempotente de las cuatro fuentes automáticas anteriores (sin GFS), conectores independientes
httpx, contenido original sin análisis, checks históricos y snapshots SQLite/filesystem privados.
SHA-256 y deduplicación por fuente; escritura atómica y referencia de DB. Metadatos desconocidos null.
UTC aware internamente/API y America/Mexico_City en la tabla temporal de estados.
Monitor automático con primer ciclo al iniciar e intervalo configurable (default 15 minutos),
checks manuales globales/por clave y CLI explícita. Lock impide ciclos simultáneos; fallos aislados.

ACTUALIZADA: último check exitoso produjo adquisición nueva respecto al snapshot anterior.
VIGENTE: éxito sin cambio, o snapshot utilizable tras fallo con último éxito reciente.
NO_DISPONIBLE_OBSOLETA: falta snapshot local utilizable o último éxito supera umbral por fuente.
SOURCE_MAX_AGE_HOURS define un umbral operativo inicial de 24h por fuente; no equivale a
validez meteorológica. Umbrales exactos pendientes de refinamiento. Validity_start/end no se infieren.

API: GET /api/sources, GET /api/sources/{key}, POST /api/sources/check,
POST /api/sources/{key}/check y GET /api/sources/{key}/snapshots.
Tabla temporal y botón de check manual. No rutas arbitrarias, no data como static.
Fase 02 completada en implementación; acceso real bloqueado según DATA_SOURCES.md.
FASE 03 no iniciada: siguen fuera SEMAR, OpenAI, análisis, GFS, mapas, riesgo, infografía y PPTX.
