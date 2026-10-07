import asyncio
from datetime import timedelta
import fcntl
import logging
from pathlib import Path
import ssl

import httpx
from sqlalchemy import select

from app.models.sources import Source, SourceCheck, SourceSnapshot, SourceStatus, utcnow
from app.services.storage import content_hash, snapshot_usable, store_snapshot
from app.sources.connectors import CONNECTORS
from app.sources.http import AcquisitionError, Transport
from app.sources.registry import initialize_sources

logger = logging.getLogger(__name__)


class MonitorBusy(Exception):
    pass


def latest_check(session, source_id, successful=False):
    stmt = select(SourceCheck).where(SourceCheck.source_id == source_id)
    if successful:
        stmt = stmt.where(SourceCheck.success.is_(True))
    return session.scalar(stmt.order_by(SourceCheck.id.desc()).limit(1))


def current_snapshot(session, source_id):
    check = latest_check(session, source_id, successful=True)
    return session.get(SourceSnapshot, check.snapshot_id) if check and check.snapshot_id else None


def status_for(session, source, settings, now=None):
    check = latest_check(session, source.id)
    success = latest_check(session, source.id, successful=True)
    snapshot = current_snapshot(session, source.id)
    age = settings.source_max_age_hours.get(source.key, 24)
    if not snapshot or not snapshot_usable(snapshot) or not success:
        return SourceStatus.NO_DISPONIBLE_OBSOLETA
    if (now or utcnow()) - success.checked_at > timedelta(hours=age):
        return SourceStatus.NO_DISPONIBLE_OBSOLETA
    if check and check.success and check.changed:
        return SourceStatus.ACTUALIZADA
    return SourceStatus.VIGENTE


class Monitor:
    def __init__(self, sessions, settings, client=None):
        self.sessions = sessions
        self.settings = settings
        self.client = client
        self.lock = asyncio.Lock()
        self.task = None

    def initialize(self):
        with self.sessions() as session:
            initialize_sources(session)

    async def check(self, key=None):
        if self.lock.locked():
            raise MonitorBusy
        async with self.lock:
            root = Path(self.settings.source_storage_dir)
            root.mkdir(parents=True, exist_ok=True)
            with (root / ".monitor.lock").open("a") as lockfile:
                try:
                    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise MonitorBusy from exc
                try:
                    if self.client is not None:
                        return await self._cycle(Transport(self.client, self.settings.source_http_retries), key)
                    # Use supplied trust store if present, keeping TLS verification enabled.
                    import os
                    trust = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
                    async with httpx.AsyncClient(timeout=self.settings.source_http_timeout_seconds,
                        headers={"User-Agent": "ReporteLluviasInundaciones/0.2 (official-source-monitor)"}, verify=trust) as client:
                        return await self._cycle(Transport(client, self.settings.source_http_retries), key)
                finally:
                    fcntl.flock(lockfile, fcntl.LOCK_UN)

    async def _cycle(self, transport, key):
        with self.sessions() as session:
            query = select(Source).where(Source.enabled.is_(True)).order_by(Source.id)
            if key:
                query = query.where(Source.key == key)
            sources = list(session.scalars(query))
        results = []
        for source in sources:
            logger.info("check_started source=%s", source.key)
            with self.sessions() as session:
                check = SourceCheck(source_id=source.id, checked_at=utcnow(), success=False, changed=False)
                try:
                    previous = latest_check(session, source.id, successful=True)
                    current = current_snapshot(session, source.id)
                    validators = previous if snapshot_usable(current) else None
                    acquisition = await CONNECTORS[source.source_type].acquire(transport, source, validators)
                    check.http_status = acquisition.http_status
                    check.etag = acquisition.etag or (previous.etag if previous and acquisition.not_modified else None)
                    check.last_modified = acquisition.last_modified or (previous.last_modified if previous and acquisition.not_modified else None)
                    if acquisition.not_modified:
                        if not current or not snapshot_usable(current):
                            raise AcquisitionError("HTTP 304 sin snapshot utilizable", 304)
                        snapshot = current
                    else:
                        digest = content_hash(acquisition)
                        check.changed = current is None or current.content_hash != digest
                        snapshot = session.scalar(select(SourceSnapshot).where(SourceSnapshot.source_id == source.id,
                                                                                 SourceSnapshot.content_hash == digest))
                        if snapshot is None:
                            path, metadata = store_snapshot(Path(self.settings.source_storage_dir), source.key,
                                                            check.checked_at, digest, acquisition)
                            snapshot = SourceSnapshot(source_id=source.id, fetched_at=check.checked_at,
                                detected_issue_time=acquisition.issue_time, content_hash=digest,
                                content_type=acquisition.content_type, original_filename=None,
                                storage_path=path, source_url=acquisition.source_url, metadata_json=metadata)
                            session.add(snapshot)
                            session.flush()
                        elif not snapshot_usable(snapshot):
                            store_snapshot(Path(self.settings.source_storage_dir), source.key,
                                           snapshot.fetched_at, digest, acquisition)
                    check.snapshot_id = snapshot.id
                    check.content_hash = snapshot.content_hash
                    check.detected_issue_time = snapshot.detected_issue_time
                    check.success = True
                    logger.info("%s source=%s", "check_changed" if check.changed else "check_unchanged", source.key)
                    logger.info("check_success source=%s", source.key)
                except asyncio.CancelledError:
                    session.rollback()
                    check.id = None
                    check.success = False
                    check.changed = False
                    check.snapshot_id = None
                    check.error_message = "Comprobación interrumpida al detener el monitor"
                    session.add(check)
                    session.commit()
                    logger.warning("check_failed source=%s reason=cancelled", source.key)
                    raise
                except Exception as exc:
                    session.rollback()
                    check.id = None
                    check.snapshot_id = None
                    check.success = False
                    check.changed = False
                    check.content_hash = None
                    check.detected_issue_time = None
                    check.http_status = exc.status if isinstance(exc, AcquisitionError) else check.http_status
                    check.error_message = str(exc) if isinstance(exc, AcquisitionError) else type(exc).__name__
                    logger.warning("check_failed source=%s reason=%s", source.key, check.error_message)
                session.add(check)
                session.commit()
                results.append({"key": source.key, "success": check.success, "changed": check.changed,
                                "http_status": check.http_status, "error_message": check.error_message})
        return results

    async def _run(self):
        while True:
            try:
                await self.check()
            except MonitorBusy:
                logger.info("monitor_cycle_skipped busy")
            except Exception as exc:
                logger.error("monitor_cycle_failed reason=%s", type(exc).__name__)
            await asyncio.sleep(self.settings.source_check_interval_minutes * 60)

    def start(self):
        if self.settings.source_monitor_enabled:
            self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
