import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import initialize_database
from app.main import create_app
from app.services.monitor import Monitor


@pytest.fixture(autouse=True)
def prohibit_real_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unit tests must not access Internet")
    async def async_denied(*args, **kwargs):
        raise AssertionError("Unit tests must not access Internet")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_denied)


@pytest.fixture
def context(tmp_path):
    settings = Settings(_env_file=None, source_monitor_enabled=False, source_http_retries=0,
                        source_storage_dir=str(tmp_path / "sources"))
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    initialize_database(engine)
    sessions = sessionmaker(bind=engine)
    yield settings, engine, sessions
    engine.dispose()


def official_fixture(request):
    # Synthetic acquisition fixtures: issuance headers only, no forecast/weather data.
    if request.url.host == "www.nhc.noaa.gov":
        product = "TWDAT" if "TWDAT" in request.url.path else "TWDEP"
        return httpx.Response(200, text=f"<pre>{product}\n1205 UTC Wed Oct 07 2026\n</pre>", headers={"etag": '"fixture-1"'})
    if request.url.path.endswith(".png"):
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nfixture", headers={"content-type": "image/png"})
    text = '<article><img src="/fixture.png"></article>'
    if "pronostico-meteorologico-general" in request.url.path:
        text = '<article><h1>Pronóstico Meteorológico General</h1><p>No. Aviso: fixture</p><p>Emisión: 12:00</p><img src="/fixture.png"></article>'
    return httpx.Response(200, text=text, headers={"content-type": "text/html"})


@pytest.fixture
def application(context):
    settings, engine, sessions = context
    client = httpx.AsyncClient(transport=httpx.MockTransport(official_fixture))
    return create_app(settings, engine, sessions, client)


@pytest.fixture
def monitor(context):
    settings, engine, sessions = context
    monitor = Monitor(sessions, settings, httpx.AsyncClient(transport=httpx.MockTransport(official_fixture)))
    monitor.initialize()
    return monitor
