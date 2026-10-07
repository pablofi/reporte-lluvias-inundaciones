"""Conservative SMN product selection and issuance metadata, without weather analysis."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlsplit

from app.sources.http import AcquisitionError, validate_url


VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source", "embed", "area", "base", "wbr"}
IGNORED_TAGS = {"head", "script", "style", "nav", "footer", "aside", "noscript"}


def fold(value):
    # One-character replacements preserve offsets for selecting the original visible text.
    return value.translate(str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")).lower()


def normalize_text(value):
    return " ".join(value.split())


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "Element | None" = None
    ignored: bool = False
    start: int = 0
    end: int = 0

    def visible_text(self):
        if self.ignored:
            return ""
        return "\n".join(c.visible_text() if isinstance(c, Element) else c for c in self.children)

    def walk(self):
        if self.ignored:
            return
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()


class SMNPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tokens = set((attrs.get("class", "") + " " + attrs.get("id", "")).lower().split())
        ignored = (self.stack[-1].ignored or tag in IGNORED_TAGS
                   or attrs.get("role") in {"navigation", "banner", "contentinfo"}
                   or bool(tokens & {"navbar", "footer", "breadcrumb", "breadcrumbs", "banner", "site-header", "site-footer"})
                   or any(token.startswith("banner") for token in tokens))
        node = Element(tag, attrs, parent=self.stack[-1], ignored=ignored)
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        if not self.stack[-1].ignored and value.strip():
            self.stack[-1].children.append(value.strip())


def render_region(node):
    parts = []
    length = 0

    def visit(element):
        nonlocal length
        element.start = length
        if not element.ignored:
            for child in element.children:
                if isinstance(child, Element):
                    visit(child)
                else:
                    parts.append(child + "\n")
                    length += len(child) + 1
        element.end = length

    visit(node)
    return "".join(parts)


GENERAL_MARKERS = (
    r"pronostico\s+meteorologico\s+general",
    r"emision\s*:",
    r"(?:no\.?|numero)\s*(?:de\s+)?aviso\s*:",
    r"pronostico\s+de\s+lluvias",
    r"proxima\s+emision",
    r"descargar\s+(?:en\s+)?pdf",
)
STORM_TITLE = r"aviso\s+de\s+potencial\s+de\s+tormentas"


@dataclass
class SMNProduct:
    text: str
    resources: list[tuple[str, bool]]
    issue_times: list[datetime]
    method: str


def select_product(html, storms=False):
    parser = SMNPageParser()
    parser.feed(html)
    nodes = list(parser.root.walk())
    all_text = fold(parser.root.visible_text())
    selected = None
    if not storms and re.search(GENERAL_MARKERS[0], all_text):
        # Require a product signature, then retain *all* available bulletin markers.
        # This avoids selecting a small heading/issuance box while losing the forecast/PDF.
        available = [pattern for pattern in GENERAL_MARKERS if re.search(pattern, all_text)]
        if GENERAL_MARKERS[1] in available and (GENERAL_MARKERS[2] in available or GENERAL_MARKERS[3] in available):
            candidates = [node for node in nodes if all(re.search(p, fold(node.visible_text())) for p in available)]
            if candidates:
                selected = min(candidates, key=lambda n: (len(n.visible_text()), -depth(n)))
    elif storms and re.search(STORM_TITLE, all_text):
        candidates = [node for node in nodes if re.search(STORM_TITLE, fold(node.visible_text()))
                      and any(child.tag == "img" for child in node.walk())]
        if candidates:
            selected = min(candidates, key=lambda n: (len(n.visible_text()), -depth(n)))
    method = "product_markers"
    if selected is None:
        # Preserve existing SMN article acquisition (including the five observed storm images).
        candidates = [n for n in nodes if n.tag == "article" or "item-page" in n.attrs.get("class", "").split()
                      or n.attrs.get("itemprop") == "articleBody"]
        if not storms:
            candidates = [n for n in candidates if re.search(GENERAL_MARKERS[0], fold(n.visible_text()))
                          and (re.search(GENERAL_MARKERS[2], fold(n.visible_text()))
                               or re.search(GENERAL_MARKERS[3], fold(n.visible_text())))]
        if not candidates:
            raise ValueError("No se identificaron marcadores inequívocos del producto SMN")
        selected = min(candidates, key=lambda n: (len(n.visible_text()), -depth(n)))
        method = "editorial_container"
    text = render_region(selected)
    folded = fold(text)
    start, end = 0, len(text)
    if method == "product_markers" and not storms:
        start = re.search(GENERAL_MARKERS[0], folded).start()
        ends = list(re.finditer(r"proxima\s+emision|descargar\s+(?:en\s+)?pdf", folded))
        if ends:
            last = ends[-1]
            containing = [n for n in selected.walk() if n.start <= last.start() and n.end >= last.end()
                          and n.tag in {"p", "div", "td", "a", "span"}]
            end = min((n.end for n in containing), default=len(text))
        elif selected.tag in {"root", "html", "body"}:
            raise ValueError("No se pudo delimitar el boletín SMN frente al contenido ajeno")
    resources, times = [], []
    for node in selected.walk():
        inside = node.start >= start and node.start <= end
        if node.tag in {"a", "iframe", "embed", "object", "img"}:
            target = node.attrs.get("href") or node.attrs.get("src") or node.attrs.get("data")
            pdf_label = bool(re.search(GENERAL_MARKERS[-1], fold(node.visible_text())))
            if target and (inside or pdf_label):
                resources.append((target, pdf_label))
        if inside and node.tag == "time" and node.attrs.get("datetime"):
            try:
                value = datetime.fromisoformat(node.attrs["datetime"].replace("Z", "+00:00"))
                if value.tzinfo is not None:
                    times.append(value.astimezone(timezone.utc))
            except ValueError:
                pass
    return SMNProduct(text[start:end], resources, times, method)


def depth(node):
    count = 0
    while node.parent is not None:
        count += 1
        node = node.parent
    return count


MONTHS = {name: i for i, name in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
DATE_PATTERN = r"\b(\d{1,2})\s+(?:de\s+)?(" + "|".join(MONTHS) + r")\s+(?:de(?:l)?\s+)?(\d{4})\b"
CLOCK_PATTERN = r"(\d{1,2}):(\d{2})(?![:\d])"


def smn_issue_time(product):
    text = fold(product.text)
    # A clearly labelled next issuance cannot supply the date/time of the current product.
    current = re.split(r"proxima\s+emision\s*:", text, maxsplit=1)[0]
    labelled_dates = list(re.finditer(r"(?:fecha(?:\s+de\s+emision)?|emision)\s*:\s*" + DATE_PATTERN, current))
    date_matches = labelled_dates or list(re.finditer(DATE_PATTERN, current))
    dates = set()
    for match in date_matches:
        day, month, year = match.groups()
        try:
            dates.add(datetime(int(year), MONTHS[month], int(day)).date())
        except ValueError:
            return None
    clocks = set()
    patterns = (r"\bemision\s*:\s*" + CLOCK_PATTERN,
                r"\bemision\s*:\s*" + DATE_PATTERN + r"[\s,;-]+" + CLOCK_PATTERN)
    for pattern in patterns:
        for match in re.finditer(pattern, current):
            if current[:match.start()].rstrip().endswith(("proxima", "siguiente")):
                continue
            hour, minute = map(int, match.groups()[-2:])
            if re.match(r"\s*(?:h\.?\s*)?(?:utc|gmt)\s*[+-]", current[match.end():]):
                return None  # Unsupported textual offset: never treat UTC-6 as plain UTC.
            zone = re.match(r"\s*(?:h\.?\s*)?(UTC|GMT|CST|CDT|EST|EDT)\b", current[match.end():], re.I)
            if zone and zone.group(1).upper() not in {"UTC", "GMT"}:
                return None
            clocks.add((hour, minute, "UTC" if zone else "America/Mexico_City"))
    iso_times = set(product.issue_times)
    if len(iso_times) == 1 and (not dates or not clocks):
        explicit = next(iter(iso_times))
        if len(dates) > 1 or len(clocks) > 1:
            return None
        if dates and next(iter(dates)) not in {explicit.date(), explicit.astimezone(ZoneInfo("America/Mexico_City")).date()}:
            return None
        if clocks:
            hour, minute, zone = next(iter(clocks))
            local = explicit.astimezone(ZoneInfo(zone))
            if (local.hour, local.minute) != (hour, minute):
                return None
        return explicit
    text_issue = None
    if dates or clocks:
        if len(dates) != 1 or len(clocks) != 1:
            return None
        date = next(iter(dates))
        hour, minute, zone = next(iter(clocks))
        try:
            naive = datetime(date.year, date.month, date.day, hour, minute)
            tz = ZoneInfo(zone)
            local = naive.replace(tzinfo=tz)
            if local.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
                return None
            text_issue = local.astimezone(timezone.utc)
            if text_issue.astimezone(tz).replace(tzinfo=None) != naive:
                return None
        except ValueError:
            return None
    candidates = set(product.issue_times)
    if text_issue:
        candidates.add(text_issue)
    return next(iter(candidates)) if len(candidates) == 1 else None


def official_resource_urls(product, base_url):
    urls = set()
    for target, pdf_label in product.resources:
        url = urljoin(base_url, target)
        suffix = urlsplit(url).path.lower()
        if pdf_label or suffix.endswith((".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp")):
            try:
                validate_url(url)
            except AcquisitionError:
                continue
            if urlsplit(url).hostname == "smn.conagua.gob.mx":
                urls.add(url)
    return urls
