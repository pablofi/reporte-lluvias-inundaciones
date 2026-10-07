# Fuentes automáticas — FASE 02

| Clave | URL oficial | Adquisición | Almacenamiento / metadatos |
| --- | --- | --- | --- |
| smn_pronostico_general | https://smn.conagua.gob.mx/es/pronosticos/pronosticossubmenu/pronostico-meteorologico-general | HTML editorial y PDF/imágenes oficiales enlazadas | HTML original + recursos binarios, hashes, URLs, ETag, Last-Modified |
| smn_potencial_tormentas | https://smn.conagua.gob.mx/es/pronosticos/avisos/aviso-de-potencial-de-tormentas | HTML editorial y productos de imagen enlazados | HTML + imágenes originales y PDF si presente, hashes, URLs y validadores |
| nhc_atlantic_twd | https://www.nhc.noaa.gov/text/MIATWDAT.shtml | Producto oficial NHC, bloque pre TWDAT | Texto de emisión UTF-8 sin resumen; emisión UTC explícita, hash del wrapper, validadores |
| nhc_eastern_pacific_twd | https://www.nhc.noaa.gov/text/MIATWDEP.shtml | Producto oficial NHC, bloque pre TWDEP | Texto de emisión UTF-8 sin resumen; emisión UTC explícita, hash del wrapper, validadores |

## Metadatos y límites

SMN: solo se buscan recursos del artículo/item-page/articleBody, no todos los logos de la página.
PDFs e imágenes deben estar enlazados explícitamente y alojados en smn.conagua.gob.mx por HTTPS.
No se inventan rutas de productos. Se detectan enlaces, img/src, iframe/src, embed/src y object/data
con extensión reconocida. Recursos construidos por JavaScript, lazy-loading no estándar, fechas en
texto ambiguo y productos sin extensión requieren adaptación posterior al HTML oficial observado.
Sin navegador automatizado. Pronóstico conserva el HTML y recursos asociados disponibles;
tormentas requiere al menos una imagen en el área editorial. Fallo de recurso asociado falla
la adquisición completa; se conserva el último snapshot utilizable según umbral.
Emisión SMN solo de un time[datetime] único con zona explícita dentro del artículo; en otro caso null.
No se extrae fecha desde PDF ni se hace OCR.

NHC: se usa el endpoint oficial de producto, no una búsqueda web ni scraping de portales ajenos.
Se extrae el bloque pre conservando texto (recorte del whitespace exterior, sin resumir).
Emisión: línea HHMM UTC día-semana mes día año. Si no es explícita/válida queda null.
Validez inicio/fin quedan null para todas las fuentes: no se infieren umbrales meteorológicos.
Los SHA de SMN comparan la adquisición compuesta; los de NHC el texto conservado.

## Acceso real observado en esta nube

La prueba administrativa real se ejecutó por separado de pytest. SMN rechazó la conexión
por proxy y NHC devolvió HTTP 403 de CloudFront. No se descargaron productos reales válidos;
no se afirma que los selectores SMN hayan sido validados sobre contenido vigente real.
Los conectores registran estos fallos y la interfaz mantiene NO DISPONIBLE / OBSOLETA sin
snapshot previo. Son límites de acceso real; los flujos de persistencia se validan con fixtures
HTTP sintéticas identificadas como tales, sin pronósticos meteorológicos inventados.

GFS no se implementa. SEMAR GOLF/PAC son cargas manuales futuras, no parte del monitor.
Tampoco se interpretan textos/imágenes ni se calculan lluvias/riesgos.
