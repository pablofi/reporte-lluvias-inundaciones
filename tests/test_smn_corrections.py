import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.models.sources import Source, SourceSnapshot, SourceStatus, utcnow
from app.services.monitor import status_for
from app.services.storage import content_hash
from app.sources.connectors import SMNConnector
from app.sources.http import Transport
from app.sources.registry import initialize_sources
from app.sources.smn import SMNProduct, select_product, smn_issue_time

FIXTURES = Path(__file__).parent / "fixtures"


def acquire(html, storms=False, asset=b"fixture-resource"):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if "/fixtures/" in request.url.path or request.url.path == "/download":
            kind = "image/jpeg" if request.url.path.endswith(".jpg") else "application/pdf"
            return httpx.Response(200, content=asset + request.url.path.encode(), headers={"content-type": kind})
        return httpx.Response(200, text=html)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            source = Source(url="https://smn.conagua.gob.mx/product")
            return await SMNConnector(require_images=storms).acquire(Transport(client), source)
    return asyncio.run(scenario()), calls


def test_general_without_article_and_official_pdf():
    html = (FIXTURES / "smn_general.html").read_text()
    acquisition, calls = acquire(html)
    assert acquisition.content == html.encode()
    assert acquisition.issue_time == datetime(2026, 10, 7, 18, tzinfo=timezone.utc)
    assert acquisition.metadata["selection"] == "product_markers"
    assert len(acquisition.resources) == 1
    assert calls[-1] == "https://smn.conagua.gob.mx/fixtures/boletin.pdf"
    assert "Texto de prueba" in acquisition.product_text
    assert "editorial ajeno" not in acquisition.product_text
    assert "Navegación" not in acquisition.product_text


def test_explicit_pdf_link_without_extension_and_no_invented_url():
    html = (FIXTURES / "smn_general.html").read_text()
    acquisition, calls = acquire(html.replace("/fixtures/boletin.pdf", "/download?id=1"))
    assert len(acquisition.resources) == 1
    assert calls[-1] == "https://smn.conagua.gob.mx/download?id=1"
    acquisition, calls = acquire(html.replace('<a href="/fixtures/boletin.pdf">Descargar <span>en PDF</span></a>', ''))
    assert acquisition.resources == []
    assert len(calls) == 1


@pytest.mark.parametrize("target", ["http://smn.conagua.gob.mx/boletin.pdf", "https://example.com/boletin.pdf"])
def test_pdf_url_validation(target):
    html = (FIXTURES / "smn_general.html").read_text().replace("/fixtures/boletin.pdf", target)
    acquisition, calls = acquire(html)
    assert acquisition.resources == []
    assert len(calls) == 1


@pytest.mark.parametrize("fixture,storms", [("smn_general.html", False), ("smn_storms.html", True)])
def test_wrapper_changes_do_not_change_product_hash(fixture, storms):
    html = (FIXTURES / fixture).read_text()
    original, _ = acquire(html, storms)
    wrapper_changed = html.replace("variable", "otro diseño").replace('class="boletin"', 'class="otra-clase"')
    modified, _ = acquire(wrapper_changed, storms)
    assert content_hash(original) == content_hash(modified)
    assert original.metadata["wrapper_sha256"] != modified.metadata["wrapper_sha256"]


def test_general_product_or_pdf_changes_update_hash():
    html = (FIXTURES / "smn_general.html").read_text()
    original, _ = acquire(html)
    changed, _ = acquire(html.replace("Texto de prueba", "Texto actualizado"))
    assert content_hash(original) != content_hash(changed)
    changed_pdf, _ = acquire(html, asset=b"new-resource")
    assert content_hash(original) != content_hash(changed_pdf)
    reformatted, _ = acquire(html.replace("Texto de prueba", "Texto   de\n prueba"))
    assert content_hash(original) == content_hash(reformatted)


def test_all_five_storm_images_and_metadata_retained():
    html = (FIXTURES / "smn_storms.html").read_text()
    acquisition, calls = acquire(html, storms=True)
    assert len(acquisition.resources) == 5
    assert [Path(r.url).name for r in acquisition.resources] == [f"Nacional_{n}.jpg" for n in range(21, 26)]
    assert acquisition.issue_time.isoformat() == "2026-10-07T18:00:00+00:00"
    changed, _ = acquire(html, storms=True, asset=b"changed-image")
    assert content_hash(acquisition) != content_hash(changed)


@pytest.mark.parametrize("text,expected", [
    ("07 de octubre de 2026\nEmisión: 12:00", "2026-10-07T18:00:00+00:00"),
    ("Fecha: 07 de octubre de 2026\nEmisión: 12:00", "2026-10-07T18:00:00+00:00"),
    ("Emisión: 07 de octubre de 2026, 12:00", "2026-10-07T18:00:00+00:00"),
    ("07 de octubre de 2026\nEmisión: 12:00 UTC", "2026-10-07T12:00:00+00:00"),
    ("07 de octubre de 2026\nEmisión: 12:00\nPróxima emisión: 18:00 del 08 de octubre de 2026", "2026-10-07T18:00:00+00:00"),
    ("07 de octubre de 2026\n08 de octubre de 2026\nEmisión: 12:00", None),
    ("07 de octubre de 2026\nEmisión: 12:00\nEmisión: 13:00", None),
    ("Emisión: 12:00", None),
    ("07 de octubre de 2026", None),
    ("31 de febrero de 2026\nEmisión: 12:00", None),
    ("07 de octubre de 2026\nEmisión: 25:00", None),
    ("07 de octubre de 2026\nEmisión: 12:00 CST", None),
])
def test_spanish_issue_time_conservative(text, expected):
    issue = smn_issue_time(SMNProduct(text, [], [], "fixture"))
    assert (issue.isoformat() if issue else None) == expected


def test_product_signature_cannot_be_navigation_only():
    html = '<nav>Pronóstico Meteorológico General No. Aviso: 1 Emisión: 12:00</nav><p>Otra página</p>'
    with pytest.raises(ValueError):
        select_product(html)


def test_classification_updates_existing_sources_and_preserves_enabled(monitor, context):
    with context[2]() as session:
        for source in session.scalars(select(Source)):
            source.is_primary = True
            source.enabled = False
        session.commit()
        initialize_sources(session)
        sources = list(session.scalars(select(Source)))
        assert {s.key: s.is_primary for s in sources} == {
            "smn_pronostico_general": True, "smn_potencial_tormentas": False,
            "nhc_atlantic_twd": False, "nhc_eastern_pacific_twd": False}
        assert all(not source.enabled for source in sources)
        initialize_sources(session)
        assert len(list(session.scalars(select(Source)))) == 4


@pytest.mark.parametrize("has_issue", [True, False])
def test_successful_200_cannot_refresh_old_product(monitor, context, has_issue):
    asyncio.run(monitor.check("nhc_atlantic_twd"))
    now = utcnow()
    with context[2]() as session:
        snapshot = session.scalar(select(SourceSnapshot))
        snapshot.detected_issue_time = now - timedelta(hours=48) if has_issue else None
        snapshot.fetched_at = now - timedelta(hours=48)
        session.commit()
    result = asyncio.run(monitor.check("nhc_atlantic_twd"))[0]
    assert result["success"] and not result["changed"]
    with context[2]() as session:
        source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
        assert status_for(session, source, context[0], now) == SourceStatus.NO_DISPONIBLE_OBSOLETA


@pytest.mark.parametrize("has_issue", [True, False])
def test_recent_product_reference_remains_reusable(monitor, context, has_issue):
    asyncio.run(monitor.check("nhc_atlantic_twd"))
    asyncio.run(monitor.check("nhc_atlantic_twd"))
    now = utcnow()
    with context[2]() as session:
        snapshot = session.scalar(select(SourceSnapshot))
        snapshot.fetched_at = now - timedelta(hours=48) if has_issue else now - timedelta(hours=1)
        snapshot.detected_issue_time = now - timedelta(hours=1) if has_issue else None
        session.commit()
        source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
        assert status_for(session, source, context[0], now) == SourceStatus.VIGENTE


def test_wrapper_only_check_deduplicates_snapshot(monitor, context):
    html = (FIXTURES / "smn_general.html").read_text()
    page = [html]
    def handler(request):
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=b"fixture-pdf", headers={"content-type": "application/pdf"})
        return httpx.Response(200, text=page[0])
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(monitor.check("smn_pronostico_general"))[0]["changed"]
    page[0] = html.replace("variable", "otro diseño")
    assert not asyncio.run(monitor.check("smn_pronostico_general"))[0]["changed"]
    with context[2]() as session:
        snapshots = list(session.scalars(select(SourceSnapshot)))
        assert len(snapshots) == 1
        assert Path(snapshots[0].storage_path).read_bytes() == html.encode()
        assert snapshots[0].metadata_json["content_hash_strategy"] == "smn_product_v2"


def test_generic_article_is_not_a_general_bulletin():
    with pytest.raises(ValueError):
        select_product("<article>Servicio temporalmente no disponible</article>")


def test_explicit_iso_time_remains_supported_with_visible_date():
    product = select_product('<article><h1>Aviso de Potencial de Tormentas</h1><time datetime="2026-10-07T12:00:00-06:00">07 de octubre de 2026</time><img src="/fixture.jpg"></article>', storms=True)
    assert smn_issue_time(product).isoformat() == "2026-10-07T18:00:00+00:00"


def test_conflicting_text_and_iso_issuance_is_unknown():
    iso = datetime(2026, 10, 7, 19, tzinfo=timezone.utc)
    product = SMNProduct("07 de octubre de 2026 Emisión: 12:00", [], [iso], "fixture")
    assert smn_issue_time(product) is None


@pytest.mark.parametrize("clock", ["12:001", "12:00:30", "12:00 UTC-6"])
def test_unsupported_clock_format_not_guessed(clock):
    assert smn_issue_time(SMNProduct(f"07 de octubre de 2026 Emisión: {clock}", [], [], "fixture")) is None


@pytest.mark.parametrize("has_issue", [True, False])
def test_legacy_hash_transition_not_a_product_change_or_freshness_reset(monitor, context, has_issue):
    from app.models.sources import SourceCheck
    from app.sources.connectors import Acquisition, Resource
    html = (FIXTURES / "smn_storms.html").read_text()
    if not has_issue:
        html = html.replace('<p>07 de octubre de 2026</p>', '').replace('<p>Emisión: 12:00 h</p>', '')
    def handler(request):
        if request.url.path.endswith(".jpg"):
            return httpx.Response(200, content=request.url.path.encode(), headers={"content-type": "image/jpeg"})
        return httpx.Response(200, text=html)
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    asyncio.run(monitor.check("smn_potencial_tormentas"))
    now = datetime(2026, 10, 7, 19, tzinfo=timezone.utc)
    original_fetched_at = now - timedelta(hours=48)
    with context[2]() as session:
        old = session.scalar(select(SourceSnapshot))
        metadata = dict(old.metadata_json)
        metadata.pop("content_hash_strategy")
        metadata.pop("normalized_product_text")
        resources = [Resource(item["url"], (Path(old.storage_path).parent / item["filename"]).read_bytes(), item["content_type"])
                     for item in metadata["resources"]]
        legacy_hash = content_hash(Acquisition(html.encode(), old.content_type, old.source_url, 200, resources=resources))
        old.content_hash = legacy_hash
        old.metadata_json = metadata
        old.fetched_at = original_fetched_at
        old.detected_issue_time = None  # Old parser did not extract the visible date/time.
        session.scalar(select(SourceCheck)).content_hash = legacy_hash
        old_id = old.id
        session.commit()
    result = asyncio.run(monitor.check("smn_potencial_tormentas"))[0]
    assert result["success"] and not result["changed"]
    with context[2]() as session:
        snapshots = list(session.scalars(select(SourceSnapshot).order_by(SourceSnapshot.id)))
        assert len(snapshots) == 2
        assert snapshots[0].content_hash == legacy_hash  # Old audit record remains intact.
        current = snapshots[-1]
        assert current.fetched_at == original_fetched_at
        assert current.metadata_json["canonicalized_from_snapshot_id"] == old_id
        source = session.scalar(select(Source).where(Source.key == "smn_potencial_tormentas"))
        expected = SourceStatus.VIGENTE if has_issue else SourceStatus.NO_DISPONIBLE_OBSOLETA
        assert status_for(session, source, context[0], now) == expected
