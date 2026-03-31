"""HTTP fetcher using httpx."""

from __future__ import annotations

import re
import time

import httpx

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import FetchError
from agent_web_compiler.core.interfaces import FetchResult


def _detect_encoding(content: bytes, headers: dict[str, str]) -> str:
    """Detect encoding from headers, meta tags, or BOM. Falls back to utf-8.

    Check order:
    1. Content-Type header charset
    2. <meta charset="...">
    3. <meta http-equiv="Content-Type" content="...charset=...">
    4. BOM (byte order mark)
    5. Default: utf-8
    """
    # 1. Content-Type header charset
    ct = headers.get("content-type", "")
    match = re.search(r"charset=([^\s;]+)", ct, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()

    # For meta tag detection, peek at first 4096 bytes decoded loosely
    head = content[:4096]
    try:
        head_str = head.decode("ascii", errors="ignore")
    except Exception:
        head_str = ""

    # 2. <meta charset="...">
    match = re.search(r'<meta[^>]+charset=["\']?([^"\'\s;>]+)', head_str, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()

    # 3. <meta http-equiv="Content-Type" content="...charset=...">
    match = re.search(
        r'<meta[^>]+http-equiv=["\']?Content-Type["\']?[^>]+content=["\']?[^"\']*charset=([^"\'\s;>]+)',
        head_str,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower()

    # 4. BOM detection
    if content[:3] == b"\xef\xbb\xbf":
        return "utf-8"
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"

    # 5. Default
    return "utf-8"


class HTTPFetcher:
    """Fetches web content via HTTP using httpx."""

    async def fetch(self, url: str, config: CompileConfig) -> FetchResult:
        """Fetch HTML content from a URL.

        Args:
            url: The URL to fetch.
            config: Compilation config controlling timeout, user_agent, etc.

        Returns:
            FetchResult with content, headers, and metadata.

        Raises:
            FetchError: On connection error, timeout, or non-2xx status.
        """
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(config.timeout_seconds),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": config.user_agent},
                )
        except httpx.TimeoutException as exc:
            raise FetchError(
                f"Timeout fetching {url} after {config.timeout_seconds}s",
                cause=exc,
                context={"url": url, "timeout": config.timeout_seconds},
            ) from exc
        except httpx.HTTPError as exc:
            raise FetchError(
                f"HTTP error fetching {url}: {exc}",
                cause=exc,
                context={"url": url},
            ) from exc

        elapsed = time.monotonic() - start

        if response.status_code < 200 or response.status_code >= 300:
            raise FetchError(
                f"Non-2xx status {response.status_code} fetching {url}",
                context={
                    "url": url,
                    "status_code": response.status_code,
                    "response_time_s": round(elapsed, 3),
                },
            )

        headers = dict(response.headers)
        content_type = response.headers.get("content-type", "text/html")

        return FetchResult(
            content=response.text,
            content_type=content_type,
            url=str(response.url),
            status_code=response.status_code,
            headers=headers,
            metadata={"response_time_s": round(elapsed, 3)},
        )

    def fetch_sync(self, url: str, config: CompileConfig) -> FetchResult:
        """Synchronous fetch.

        Args:
            url: The URL to fetch.
            config: Compilation config controlling timeout, user_agent, etc.

        Returns:
            FetchResult with content, headers, and metadata.

        Raises:
            FetchError: On connection error, timeout, or non-2xx status.
        """
        start = time.monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(config.timeout_seconds),
                follow_redirects=True,
            ) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": config.user_agent},
                )
        except httpx.TimeoutException as exc:
            raise FetchError(
                f"Timeout fetching {url} after {config.timeout_seconds}s",
                cause=exc,
                context={"url": url, "timeout": config.timeout_seconds},
            ) from exc
        except httpx.HTTPError as exc:
            raise FetchError(
                f"HTTP error fetching {url}: {exc}",
                cause=exc,
                context={"url": url},
            ) from exc

        elapsed = time.monotonic() - start

        if response.status_code < 200 or response.status_code >= 300:
            raise FetchError(
                f"Non-2xx status {response.status_code} fetching {url}",
                context={
                    "url": url,
                    "status_code": response.status_code,
                    "response_time_s": round(elapsed, 3),
                },
            )

        headers = dict(response.headers)
        content_type = response.headers.get("content-type", "text/html")

        return FetchResult(
            content=response.text,
            content_type=content_type,
            url=str(response.url),
            status_code=response.status_code,
            headers=headers,
            metadata={"response_time_s": round(elapsed, 3)},
        )
