import asyncio
from datetime import timedelta
import fcntl
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import func, select

from app.models.sources import Source, SourceCheck, SourceSnapshot, SourceStatus, utcnow
from app.services.monitor import Monitor, MonitorBusy, status_for
from app.sources.connectors import nhc_issue_time
from app.sources.http import AcquisitionError, Transport
from conftest import official_fixture


def run(coroutine):
    return asyncio.run(coroutine)


def counts(sessions):
    with sessions() as session:
        return (session.scalar(select(func.count()).select_from(SourceSnapshot)),
                session.scalar(select(func.count()).select_from(SourceCheck)))


def test_initialization_idempotent(monitor, context):
    monitor.initialize()
    with context[2]() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 4
        assert all(s.created_at.tzinfo is not None for s in session.scalars(select(Source)))


def test_snapshot_dedup_checks_and_persistence(monitor, context):
    assert all(c["changed"] for c in run(monitor.check()))
    assert counts(context[2]) == (4, 4)
    assert all(not c["changed"] for c in run(monitor.check()))
    assert counts(context[2]) == (4, 8)
    with context[2]() as session:
        for snapshot in session.scalars(select(SourceSnapshot)):
            assert Path(snapshot.storage_path).is_file()
            assert (Path(snapshot.storage_path).parent / "metadata.json").is_file()
            assert snapshot.fetched_at.utcoffset().total_seconds() == 0
    context[1].dispose()
    restarted = Monitor(context[2], context[0], monitor.client)
    restarted.initialize()
    assert all(not c["changed"] for c in run(restarted.check()))
    assert counts(context[2]) == (4, 12)


def test_changed_and_return_to_old_content(monitor, context):
    run(monitor.check("nhc_atlantic_twd"))
    def changed(request):
        return httpx.Response(200, text='<pre>TWDAT\n1205 UTC Thu Oct 08 2026</pre>')
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(changed))
    assert run(monitor.check("nhc_atlantic_twd"))[0]["changed"]
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(official_fixture))
    assert run(monitor.check("nhc_atlantic_twd"))[0]["changed"]
    assert counts(context[2]) == (2, 3)
    with context[2]() as session:
        source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
        assert status_for(session, source, context[0]) == SourceStatus.ACTUALIZADA


def test_304(monitor, context):
    run(monitor.check("nhc_atlantic_twd"))
    def unchanged(request):
        assert request.headers["if-none-match"] == '"fixture-1"'
        return httpx.Response(304)
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(unchanged))
    result = run(monitor.check("nhc_atlantic_twd"))[0]
    assert result["success"] and not result["changed"]
    assert counts(context[2]) == (1, 2)


def test_304_without_snapshot_is_failure(monitor):
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(304)))
    assert not run(monitor.check("nhc_atlantic_twd"))[0]["success"]


def test_failure_does_not_stop_other_sources(monitor, context):
    def partly_failing(request):
        if "pronostico-meteorologico-general" in request.url.path:
            return httpx.Response(503)
        return official_fixture(request)
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(partly_failing))
    results = run(monitor.check())
    assert [c["success"] for c in results] == [False, True, True, True]
    assert counts(context[2]) == (3, 4)


def test_status_age_and_fallback(monitor, context):
    settings, _, sessions = context
    with sessions() as session:
        source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
        assert status_for(session, source, settings) == SourceStatus.NO_DISPONIBLE_OBSOLETA
    run(monitor.check("nhc_atlantic_twd"))
    run(monitor.check("nhc_atlantic_twd"))
    with sessions() as session:
        assert status_for(session, source, settings) == SourceStatus.VIGENTE
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    run(monitor.check("nhc_atlantic_twd"))
    with sessions() as session:
        assert status_for(session, source, settings) == SourceStatus.VIGENTE
        assert status_for(session, source, settings, utcnow() + timedelta(hours=25)) == SourceStatus.NO_DISPONIBLE_OBSOLETA
    settings.source_max_age_hours[source.key] = 48
    with sessions() as session:
        assert status_for(session, source, settings, utcnow() + timedelta(hours=25)) == SourceStatus.VIGENTE


def test_api_and_manual_check(application):
    with TestClient(application) as client:
        assert len(client.get("/api/sources").json()) == 4
        assert client.post("/api/sources/check").status_code == 200
        sources = client.get("/api/sources").json()
        assert all(s["status"] == "ACTUALIZADA" for s in sources)
        assert all(s["last_check"].endswith("+00:00") for s in sources)
        assert "storage_path" not in str(sources)
        detail = client.get("/api/sources/nhc_atlantic_twd").json()
        assert len(detail["checks"]) == 1
        assert len(client.get("/api/sources/nhc_atlantic_twd/snapshots").json()) == 1
        assert client.post("/api/sources/nhc_atlantic_twd/check").json()["checks"][0]["changed"] is False
        assert client.post("/api/sources/not_registered/check").status_code == 404
        assert client.get("/api/sources/not_registered").status_code == 404
        assert client.get("/api/sources/nhc_atlantic_twd/snapshots?limit=101").status_code == 422
        assert client.get("/data/database/app.db").status_code == 404
        page = client.get("/").text
        assert "Estado de fuentes automáticas" in page
        assert "07 OCT 2026 - 06:05 h" in page
        assert client.post("/sources/check", follow_redirects=False).status_code == 303


def test_overlap_and_disabled(application, context):
    with TestClient(application) as client:
        root = Path(context[0].source_storage_dir)
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".monitor.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert client.post("/api/sources/check").status_code == 409
        with context[2]() as session:
            source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
            source.enabled = False
            session.commit()
        assert client.post("/api/sources/nhc_atlantic_twd/check").status_code == 409
        assert len(client.post("/api/sources/check").json()["checks"]) == 3


def test_http_retry_and_unofficial_redirect():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, content=b"fixture")
    transport = Transport(httpx.AsyncClient(transport=httpx.MockTransport(handler)), retries=1)
    assert run(transport.get("https://www.nhc.noaa.gov/text/MIATWDAT.shtml")).status_code == 200
    assert len(calls) == 2
    transport.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r:
        httpx.Response(302, headers={"location": "http://127.0.0.1/private"})))
    with pytest.raises(AcquisitionError):
        run(transport.get("https://www.nhc.noaa.gov/text/MIATWDAT.shtml"))


def test_unparseable_source_is_not_success(monitor):
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r:
        httpx.Response(200, text="<html>Access denied</html>")))
    assert not any(c["success"] for c in run(monitor.check()))


def test_issue_time_requires_utc():
    assert nhc_issue_time("1205 UTC Wed Oct 07 2026").isoformat() == "2026-10-07T12:05:00+00:00"
    assert nhc_issue_time("1205 EDT Wed Oct 07 2026") is None
    assert nhc_issue_time("9965 UTC Wed Oct 07 2026") is None


def test_scheduler_start_stop(context):
    async def scenario():
        settings, _, sessions = context
        settings.source_monitor_enabled = True
        monitor = Monitor(sessions, settings)
        calls = []
        async def check():
            calls.append(1)
            return []
        monitor.check = check
        monitor.start()
        await asyncio.sleep(0.01)
        assert len(calls) == 1
        await monitor.stop()
        assert monitor.task.cancelled()
        assert settings.source_check_interval_minutes == 15
    run(scenario())


def test_smn_linked_asset_change_and_issue_time(monitor, context):
    marker = [b"first"]
    def resource_fixture(request):
        if request.url.path.endswith(".png"):
            return httpx.Response(200, content=marker[0], headers={"content-type": "image/png"})
        return httpx.Response(200, text='<article><time datetime="2026-10-07T06:00:00-06:00"></time><img src="/fixture.png"></article>')
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(resource_fixture))
    assert run(monitor.check("smn_potencial_tormentas"))[0]["changed"]
    marker[0] = b"second"
    assert run(monitor.check("smn_potencial_tormentas"))[0]["changed"]
    assert counts(context[2]) == (2, 2)
    with context[2]() as session:
        snapshot = session.scalar(select(SourceSnapshot).order_by(SourceSnapshot.id.desc()))
        assert snapshot.detected_issue_time.isoformat() == "2026-10-07T12:00:00+00:00"
        assert len(snapshot.metadata_json["resources"]) == 1


def test_missing_snapshot_reacquired(monitor, context):
    run(monitor.check("nhc_atlantic_twd"))
    with context[2]() as session:
        snapshot = session.scalar(select(SourceSnapshot))
        Path(snapshot.storage_path).unlink()
    def fixture(request):
        assert "if-none-match" not in request.headers
        return official_fixture(request)
    monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(fixture))
    assert run(monitor.check("nhc_atlantic_twd"))[0]["success"]
    assert Path(snapshot.storage_path).is_file()
    assert counts(context[2]) == (1, 2)


def test_corrupt_snapshot_not_reusable_and_repaired(monitor, context):
    run(monitor.check("nhc_atlantic_twd"))
    with context[2]() as session:
        source = session.scalar(select(Source).where(Source.key == "nhc_atlantic_twd"))
        snapshot = session.scalar(select(SourceSnapshot))
        Path(snapshot.storage_path).write_bytes(b"corrupt")
        assert status_for(session, source, context[0]) == SourceStatus.NO_DISPONIBLE_OBSOLETA
    assert run(monitor.check("nhc_atlantic_twd"))[0]["success"]
    with context[2]() as session:
        assert status_for(session, source, context[0]) == SourceStatus.VIGENTE
    assert counts(context[2]) == (1, 2)


def test_shutdown_records_interrupted_attempt(monitor, context):
    async def scenario():
        entered = asyncio.Event()
        async def slow(request):
            entered.set()
            await asyncio.Future()
        monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
        context[0].source_monitor_enabled = True
        monitor.start()
        await entered.wait()
        await monitor.stop()
        with context[2]() as session:
            check = session.scalar(select(SourceCheck))
            assert check is not None and not check.success
            assert "interrumpida" in check.error_message
        assert not monitor.lock.locked()
    run(scenario())
