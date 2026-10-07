# Fuentes automáticas — FASE 02

| Clave / rol | URL oficial | Adquisición y formato |
| --- | --- | --- |
| smn_pronostico_general / principal | https://smn.conagua.gob.mx/es/pronosticos/pronosticossubmenu/pronostico-meteorologico-general | HTML original, texto específico normalizado y PDF/recursos oficiales enlazados |
| smn_potencial_tormentas / complementaria | https://smn.conagua.gob.mx/es/pronosticos/avisos/aviso-de-potencial-de-tormentas | HTML original e imágenes/productos oficiales, sin interpretar |
| nhc_atlantic_twd / complementaria | https://www.nhc.noaa.gov/text/MIATWDAT.shtml | Texto original del bloque pre del producto TWDAT |
| nhc_eastern_pacific_twd / complementaria | https://www.nhc.noaa.gov/text/MIATWDEP.shtml | Texto original del bloque pre del producto TWDEP |

## SMN

Pronóstico General se reconoce mediante marcadores propios del boletín, sin requerir article,
item-page o articleBody. Cuando están presentes se considera conjuntamente título, No. Aviso,
Emisión, Pronóstico de lluvias, Próxima emisión y Descargar en PDF, evitando seleccionar solo
una caja de encabezado. Se delimita el contenido y se excluyen elementos ajenos.

El enlace Descargar en PDF se obtiene del HTML, incluso si la URL no termina en .pdf.
Solo se descargan destinos HTTPS permitidos del host smn.conagua.gob.mx; nunca se inventa
la URL. Se validan redirecciones y tipo de recurso. Se conservan los productos oficiales de
imagen y otros recursos asociados. Tormentas mantiene el flujo de descarga de las cinco
imágenes reportadas: Nacional_21.jpg, Nacional_22.jpg, Nacional_23.jpg, Nacional_24.jpg y
Nacional_25.jpg, sin construir esas URLs por nombre.

Hash de producto smn_product_v2: Pronóstico = texto normalizado + hashes binarios de recursos;
tormentas = conjunto ordenado de hashes de imágenes/productos + emisión inequívoca si existe.
El orden HTML o las URLs de los mismos recursos no forman parte de la identidad. Navbar,
footer y banners no provocan actualizaciones. HTML original, wrapper_sha256, texto usado,
URLs, tipos, hashes, ETag y Last-Modified se conservan como metadatos/auditoría del snapshot.
El HTML de una versión es su primera adquisición; envolturas posteriores con el mismo producto
no generan otra versión. Snapshots anteriores permanecen; el paso a v2 puede crear una versión
canónica vinculada al registro anterior. Si su contenido permite probar equivalencia, no se marca
cambio y se conserva fetched_at original. Sin evidencia suficiente no se presume equivalencia.

La fecha española visible (día, mes nominal, año) combinada con Emisión: HH:MM se convierte
desde America/Mexico_City a UTC. Se admite fecha de emisión explícitamente rotulada y fecha
inline junto a la hora. Próxima emisión no se usa como emisión actual. Sin una fecha/hora
inequívocas, con datos contradictorios o zona ambigua, la emisión queda null. Se conserva
soporte de time[datetime] con zona explícita; no se hace OCR ni lectura de fechas de PDFs.

Límites: formatos de fecha no reconocidos permanecen null; no se ejecuta JavaScript, ni se
resuelven lazy-loading no estándar o recursos no enlazados. Una firma editorial no reconocida
produce error de adquisición; no implica que el producto requiera un navegador.
Fallos de recursos asociados fallan la adquisición completa, con reutilización solo dentro del
umbral del producto anterior. No hay interpretación meteorológica.

## NHC y edad del producto

Se mantiene el producto oficial, extrayendo pre sin resumir y recortando whitespace exterior.
Se detecta la línea HHMM UTC día-semana mes día año cuando es válida. ETag/Last-Modified y
HTTP 304 reutilizan el snapshot sin cambiar su emisión ni fetched_at. Validez inicio/fin
permanece null, no inferida.

SOURCE_MAX_AGE_HOURS usa detected_issue_time o, cuando falta, fetched_at. Un HTTP 200 repetido
no rejuvenece el producto. Umbral 24h por fuente provisional y configurable; no representa
validez meteorológica oficial. SEMAR GOLF/PAC obligatorias serán cargas de una fase posterior;
GFS será auxiliar futuro. No se implementa ninguno en FASE 02.

## Evidencia real y validación pendiente

La prueba previa en Codex cloud tuvo ProxyError en SMN y HTTP 403 en NHC, propios de esa ruta;
no representa el acceso directo de WSL.

El usuario reportó en WSL HTTP 200 para las cuatro fuentes: Pronóstico General falló por el
selector editorial antiguo; Tormentas descargó las cinco imágenes; NHC Atlántico detectó
2026-10-07T18:15:00+00:00 y Pacífico 2026-10-07T16:05:00+00:00.
Las correcciones actuales están probadas con fixtures sintéticas representativas de los marcadores
y nombres reportados, no con una copia del HTML operativo completo. **La validación real definitiva
se repetirá en WSL** con python -m app.cli check-sources o el equivalente Docker; comprobar success,
emisión detectada, recursos asociados y segundo ciclo sin cambio.
