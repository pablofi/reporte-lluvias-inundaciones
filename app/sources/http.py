import asyncio
from urllib.parse import urlsplit

import httpx

ALLOWED_HOSTS = {"smn.conagua.gob.mx", "www.nhc.noaa.gov"}


class AcquisitionError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def validate_url(url):
    parsed = urlsplit(str(url))
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise AcquisitionError("Destino no oficial o no permitido")


class Transport:
    def __init__(self, client, retries=2, max_bytes=20 * 1024 * 1024):
        self.client = client
        self.retries = retries
        self.max_bytes = max_bytes

    async def get(self, url, headers=None):
        validate_url(url)
        for attempt in range(self.retries + 1):
            try:
                current = url
                for _ in range(6):
                    validate_url(current)
                    async with self.client.stream("GET", current, headers=headers, follow_redirects=False) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            current = str(response.url.join(response.headers.get("location", "")))
                            continue
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise AcquisitionError("Recurso supera el límite de descarga", response.status_code)
                        headers_copy = dict(response.headers)
                        headers_copy.pop("content-encoding", None)
                        headers_copy.pop("content-length", None)
                        result = httpx.Response(response.status_code, headers=headers_copy,
                                                content=bytes(body), request=response.request)
                        if result.status_code == 304:
                            return result
                        result.raise_for_status()
                        if not body:
                            raise AcquisitionError("Recurso vacío", result.status_code)
                        return result
                raise AcquisitionError("Demasiadas redirecciones")
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code not in (408, 429, 500, 502, 503, 504) or attempt == self.retries:
                    raise AcquisitionError(f"HTTP {code}", code) from exc
            except httpx.TransportError as exc:
                if attempt == self.retries:
                    # No registrar mensajes del proxy que puedan contener credenciales.
                    raise AcquisitionError(f"Error de transporte: {type(exc).__name__}") from exc
            await asyncio.sleep(0.25 * 2 ** attempt)
