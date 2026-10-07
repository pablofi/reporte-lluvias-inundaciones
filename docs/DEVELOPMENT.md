# Desarrollo

Seguir AGENTS.md y limitar cada tarea a su fase. Ejecución normal Docker;
comandos completos WSL y local en README.md. Usar Python 3.12 y ramas codex/*.
No versionar .env, DB ni archivos operativos de data. No solicitar claves para fase 01.

Validación antes de entregar:

```bash
docker compose build
docker compose up -d --wait
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/
docker compose exec -T web python -m pytest
python -m pytest  # Con el entorno local activado.
```

Tests usan TestClient con lifespan y comprueban inicio con SQLite, JSON de salud,
página HTML y acceso CSS. Mantener un directorio data escribible para las pruebas.
No usar datos meteorológicos ficticios. Documentar pruebas ejecutadas, fallos y checks no realizados.

Futuras decisiones pendientes: autenticación, vigencia de fuentes, formato de cargas,
esquemas de extracción, algoritmos de riesgo, migraciones y recursos institucionales.
No anticipar estas implementaciones. El PR debe incluir alcance, archivos, arquitectura,
comandos WSL, resultados, limitaciones y exclusiones.

## Redes restringidas de compilación

Dockerfile admite opcionalmente un secreto BuildKit `pip_ca` con el certificado CA de
la red de compilación. No se copia a la imagen. En esta nube, el contenedor de build
requiere el proxy suministrado, su resolución DNS y red host mediante un override local
fuera del repositorio. No desactivar TLS ni almacenar credenciales en overrides.
El Compose estándar se conserva para WSL/Ubuntu con conectividad normal.
