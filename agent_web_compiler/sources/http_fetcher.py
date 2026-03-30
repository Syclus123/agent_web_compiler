"""HTTP fetcher using httpx."""

from __future__ import annotations

import time

import httpx

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import FetchError
from agent_web_compiler.core.interfaces import FetchResult


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
