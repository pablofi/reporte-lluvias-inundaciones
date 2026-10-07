import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "reporte-lluvias-inundaciones",
    }


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Sistema de Reporte de Lluvias e Inundaciones" in response.text
    assert "Fase inicial del sistema" in response.text
    assert client.get("/static/style.css").status_code == 200
