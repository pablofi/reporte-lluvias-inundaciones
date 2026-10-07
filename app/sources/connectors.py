from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import hashlib
from urllib.parse import urlsplit

from app.sources.http import AcquisitionError
from app.sources.smn import normalize_text, official_resource_urls, select_product, smn_issue_time


@dataclass
class Resource:
    url: str
    content: bytes
    content_type: str


@dataclass
class Acquisition:
    content: bytes
    content_type: str
    source_url: str
    http_status: int
    etag: str | None = None
    last_modified: str | None = None
    issue_time: datetime | None = None
    resources: list[Resource] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    not_modified: bool = False
    product_text: str | None = None


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pre_depth = 0
        self.product = []
        self.resources = []
        self.content_depth = 0
        self.stack = []
        self.found_content = False
        self.issue_times = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "pre":
            self.pre_depth += 1
        marker = attrs.get("class", "") + " " + attrs.get("itemprop", "")
        starts_content = tag == "article" or "item-page" in marker or "articleBody" in marker
        # Track only non-void elements so img/br do not corrupt depth.
        if tag not in {"img", "br", "hr", "input", "meta", "link", "source", "embed", "area", "base", "wbr"}:
            self.stack.append((tag, starts_content))
        if starts_content:
            self.content_depth += 1
            self.found_content = True
        if self.content_depth:
            if tag == "time" and attrs.get("datetime"):
                try:
                    value = datetime.fromisoformat(attrs["datetime"].replace("Z", "+00:00"))
                    if value.tzinfo is not None:
                        self.issue_times.append(value.astimezone(timezone.utc))
                except ValueError:
                    pass
            if tag in ("a", "iframe", "embed", "object"):
                target = attrs.get("href") or attrs.get("src") or attrs.get("data")
                if target:
                    self.resources.append(target)
            if tag == "img":
                target = attrs.get("src")
                if target:
                    self.resources.append(target)

    def handle_endtag(self, tag):
        if tag == "pre":
            self.pre_depth = max(0, self.pre_depth - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                removed = self.stack[i:]
                self.content_depth -= sum(start for _, start in removed)
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.pre_depth:
            self.product.append(data)


def nhc_issue_time(text):
    # Official issuance line: 1205 UTC Wed Oct 07 2026 (never infer local abbreviations).
    match = re.search(r"\b(\d{3,4}) UTC [A-Za-z]{3} ([A-Za-z]{3}) (\d{1,2}) (\d{4})\b", text)
    if not match:
        return None
    clock, month, day, year = match.groups()
    months = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
    try:
        return datetime(int(year), months[month], int(day), int(clock[:-2]), int(clock[-2:]), tzinfo=timezone.utc)
    except (ValueError, KeyError):
        return None


class Connector:
    async def acquire(self, transport, source, previous=None):
        raise NotImplementedError


class NHCConnector(Connector):
    def __init__(self, product):
        self.product = product

    async def acquire(self, transport, source, previous=None):
        headers = {}
        if previous:
            if previous.etag:
                headers["If-None-Match"] = previous.etag
            if previous.last_modified:
                headers["If-Modified-Since"] = previous.last_modified
        response = await transport.get(source.url, headers)
        if response.status_code == 304:
            return Acquisition(b"", "text/plain", source.url, 304,
                               response.headers.get("etag"), response.headers.get("last-modified"), not_modified=True)
        parser = ProductParser()
        parser.feed(response.text)
        product = "".join(parser.product).strip()
        if not product or self.product not in product:
            raise AcquisitionError("Producto NHC esperado no encontrado", response.status_code)
        return Acquisition(product.encode("utf-8"), "text/plain; charset=utf-8", str(response.url), response.status_code,
                           response.headers.get("etag"), response.headers.get("last-modified"), nhc_issue_time(product),
                           metadata={"method": "official_product_pre", "product": self.product,
                                     "wrapper_sha256": hashlib.sha256(response.content).hexdigest()})


class SMNConnector(Connector):
    def __init__(self, require_images=False):
        self.require_images = require_images

    async def acquire(self, transport, source, previous=None):
        # Re-fetch resources even if page/ETag did not change: PDFs/images may be overwritten in place.
        response = await transport.get(source.url)
        try:
            product = select_product(response.text, storms=self.require_images)
        except ValueError as exc:
            raise AcquisitionError(str(exc), response.status_code) from exc
        urls = official_resource_urls(product, str(response.url))
        if self.require_images and not any(urlsplit(u).path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) for u in urls):
            raise AcquisitionError("No se localizaron imágenes oficiales en el contenido SMN", response.status_code)
        if len(urls) > 30:
            raise AcquisitionError("Demasiados recursos asociados; revisar estructura SMN", response.status_code)
        resources = []
        for url in sorted(urls):
            asset = await transport.get(url)
            kind = asset.headers.get("content-type", "application/octet-stream")
            if not (kind.startswith("image/") or kind.split(";")[0] == "application/pdf"):
                raise AcquisitionError("Tipo inesperado del recurso SMN", asset.status_code)
            resources.append(Resource(url, asset.content, kind))
        issue_time = smn_issue_time(product)
        product_text = normalize_text(product.text)
        if self.require_images:
            # Storm products are the image set, plus unambiguous issuance metadata.
            # Unrelated page prose must never produce an image-product update.
            product_text = issue_time.isoformat() if issue_time else ""
        return Acquisition(response.content, response.headers.get("content-type", "text/html"), str(response.url),
                           response.status_code, response.headers.get("etag"), response.headers.get("last-modified"),
                           issue_time=issue_time, product_text=product_text,
                           resources=resources, metadata={"method": "official_html_and_linked_resources",
                           "selection": product.method, "content_hash_strategy": "smn_product_v2",
                           "wrapper_sha256": hashlib.sha256(response.content).hexdigest(),
                           "issue_time_note": "Fecha/emisión inequívocas del producto; hora local America/Mexico_City o zona explícita"})


CONNECTORS = {
    "nhc_atlantic": NHCConnector("TWDAT"),
    "nhc_pacific": NHCConnector("TWDEP"),
    "smn_general": SMNConnector(),
    "smn_storms": SMNConnector(require_images=True),
}
