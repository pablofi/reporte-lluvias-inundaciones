import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


def content_hash(acquisition):
    if acquisition.product_text is not None:
        manifest = {"strategy": "smn_product_v2", "text": acquisition.product_text,
                    "resources": sorted({hashlib.sha256(r.content).hexdigest() for r in acquisition.resources})}
        return hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
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
    if acquisition.product_text is not None:
        metadata["normalized_product_text"] = acquisition.product_text
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


def legacy_smn_product_hash(snapshot, storms=False):
    """Compare a retained v1 archive with v2 without modifying historical files."""
    import httpx
    from app.sources.connectors import Acquisition, Resource
    from app.sources.smn import normalize_text, official_resource_urls, select_product, smn_issue_time

    try:
        body = Path(snapshot.storage_path).read_bytes()
        html = httpx.Response(200, content=body, headers={"content-type": snapshot.content_type}).text
        product = select_product(html, storms=storms)
        metadata = snapshot.metadata_json or {}
        archived = {item["url"]: item for item in metadata.get("resources", [])}
        resources = []
        for url in sorted(official_resource_urls(product, snapshot.source_url)):
            item = archived.get(url)
            if item:
                resources.append(Resource(url, (Path(snapshot.storage_path).parent / item["filename"]).read_bytes(), item["content_type"]))
            else:
                return None  # Cannot prove equivalence without the associated archived resource.
        issue = smn_issue_time(product)
        text = (issue.isoformat() if issue else "") if storms else normalize_text(product.text)
        return content_hash(Acquisition(body, snapshot.content_type, snapshot.source_url, 200,
                                        resources=resources, product_text=text))
    except (OSError, ValueError, KeyError):
        return None
