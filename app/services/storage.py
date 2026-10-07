import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


def content_hash(acquisition):
    # Text product hash is the exact stored UTF-8 bytes. Bundles include URLs and raw resource hashes.
    if not acquisition.resources:
        return hashlib.sha256(acquisition.content).hexdigest()
    manifest = [(acquisition.source_url, hashlib.sha256(acquisition.content).hexdigest())]
    manifest += [(r.url, hashlib.sha256(r.content).hexdigest()) for r in acquisition.resources]
    return hashlib.sha256(json.dumps(sorted(manifest), ensure_ascii=False).encode()).hexdigest()


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def store_snapshot(root, key, now, digest, acquisition):
    folder = root / key / now.strftime("%Y/%m/%d") / digest
    primary = folder / ("original.txt" if acquisition.content_type.startswith("text/plain") else "original.html")
    atomic_write(primary, acquisition.content)
    metadata = dict(acquisition.metadata)
    metadata.update(content_hash=digest, fetched_at=now.isoformat(), source_url=acquisition.source_url,
                    detected_issue_time=acquisition.issue_time.isoformat() if acquisition.issue_time else None,
                    primary_sha256=hashlib.sha256(acquisition.content).hexdigest(), resources=[])
    for resource in acquisition.resources:
        resource_hash = hashlib.sha256(resource.content).hexdigest()
        suffix = Path(urlsplit(resource.url).path).suffix.lower()
        filename = resource_hash + suffix
        atomic_write(folder / filename, resource.content)
        metadata["resources"].append({"url": resource.url, "filename": filename,
                                      "content_type": resource.content_type, "sha256": resource_hash})
    atomic_write(folder / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2).encode())
    return str(primary), metadata


def snapshot_usable(snapshot):
    if snapshot is None:
        return False
    primary = Path(snapshot.storage_path)
    metadata = snapshot.metadata_json or {}
    paths = [(primary, metadata.get("primary_sha256"))]
    paths += [(primary.parent / item["filename"], item["sha256"])
              for item in metadata.get("resources", [])]
    try:
        for path, expected in paths:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
            if expected and digest.hexdigest() != expected:
                return False
        return True
    except OSError:
        return False
