FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app
COPY pyproject.toml ./
COPY app ./app
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --no-cache-dir '.[dev]'
COPY tests ./tests
RUN mkdir -p data/sources data/uploads data/reports data/database && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('APP_PORT', '8000') + '/health', timeout=3)"
CMD ["python", "-m", "app"]
