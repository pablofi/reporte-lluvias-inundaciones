# Reglas permanentes de desarrollo

1. Trabajar incrementalmente y respetar el alcance de la fase solicitada.
2. No implementar funciones fuera de la tarea actual. Fase actual: 01, bootstrap.
3. No modificar la plantilla PPTX institucional salvo instrucciones expresas.
4. Nunca inventar ni simular datos meteorológicos.
5. Separar adquisición, extracción, análisis, validación, cartografía y presentación.
6. Conservar trazabilidad de todas las fuentes meteorológicas.
7. Vincular todo dato derivado con su fuente.
8. No almacenar secretos en Git, imágenes Docker, logs o documentación.
9. OPENAI_API_KEY y demás secretos solo mediante variables de entorno.
10. El frontend nunca recibirá la API key de OpenAI.
11. Presentar fechas en America/Mexico_City y almacenar timestamps UTC con zona horaria.
12. Escribir tests para funciones críticas.
13. Documentar cambios de arquitectura o dependencias importantes.
14. Mantener compatibilidad WSL/Linux; no añadir React, Vue, Angular o Node sin aprobación expresa.
15. Docker es la forma normal de ejecución; Python 3.12 es la versión base.
16. No incorporar ríos ni presas a este producto.
17. El mapa final representará solo precipitación meteorológica: sin huracanes, frentes, bajas presiones, ondas, trayectorias ni simbología sinóptica.
18. Priorizar reproducibilidad y exactitud sobre creatividad visual.
19. Ejecutar tests antes de finalizar cada tarea. Informar fallos o checks no ejecutados.
20. En el PR explicar cambios, cómo probarlos y qué quedó expresamente fuera de alcance.

Usar el checkout existente del entorno aislado; no crear worktrees salvo petición expresa.
Trabajar en ramas codex/*, evitando main. No avanzar a fase 02 sin nueva instrucción.
Validar con `python -m pytest` y, cuando Docker esté disponible, `docker compose build`,
`docker compose up -d --wait`, consultas a / y /health y `docker compose exec -T web python -m pytest`.
