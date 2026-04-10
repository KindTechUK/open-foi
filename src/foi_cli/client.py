"""HTTP client for WhatDoTheyKnow feed API with rate limiting, retries, and caching."""

import json
import logging
import time
from urllib.parse import quote

import httpx

from foi_cli import __version__
from foi_cli.cache import Cache
from foi_cli.config import Config, load_config

logger = logging.getLogger(__name__)

BASE_URL = "https://www.whatdotheyknow.com"


class WDTKError(Exception):
    """Base error for WDTK API issues."""


class WDTKClient:
    def __init__(self, config: Config | None = None, cache: Cache | None = None):
        self._config = config or load_config()
        self._cache = cache
        self._last_request_at = 0.0
        self._http = httpx.Client(
            timeout=self._config.timeout,
            headers={"User-Agent": f"open-foi/{__version__}"},
            follow_redirects=True,
        )

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self._config.rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _get_json(self, url: str, cache_key: str | None = None, cache_ttl: int = 3600) -> list:
        if cache_key and self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return json.loads(cached)

        self._rate_limit()
        last_err = None
        for attempt in range(self._config.max_retries):
            try:
                resp = self._http.get(url)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limited (429), waiting %ds", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Server error %d, retrying in %ds", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                if resp.status_code == 403:
                    raise WDTKError(
                        f"Blocked by Cloudflare (403). URL: {url}\n"
                        "This endpoint may not be accessible programmatically."
                    )
                resp.raise_for_status()
                data = resp.json()
                if cache_key and self._cache:
                    self._cache.set(cache_key, json.dumps(data), cache_ttl)
                return data
            except httpx.HTTPStatusError as e:
                raise WDTKError(f"HTTP {e.response.status_code}: {url}") from e
            except httpx.RequestError as e:
                last_err = e
                wait = 2 ** (attempt + 1)
                logger.warning("Request error: %s, retrying in %ds", e, wait)
                time.sleep(wait)
        raise WDTKError(f"Failed after {self._config.max_retries} retries: {last_err}")

    def _get_text(self, url: str, cache_key: str | None = None, cache_ttl: int = 86400) -> str:
        if cache_key and self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WDTKError(f"HTTP {e.response.status_code}: {url}") from e
        except httpx.RequestError as e:
            raise WDTKError(f"Request failed: {url}: {e}") from e
        text = resp.text
        if cache_key and self._cache:
            self._cache.set(cache_key, text, cache_ttl)
        return text

    def search_feed(self, query: str, page: int = 1) -> list[dict]:
        encoded = quote(query, safe="")
        url = f"{BASE_URL}/feed/search/{encoded}.json?page={page}"
        cache_key = f"feed:search:{query}:page={page}"
        return self._get_json(url, cache_key)

    def body_feed(self, url_name: str, page: int = 1) -> list[dict]:
        url = f"{BASE_URL}/feed/body/{url_name}.json?page={page}"
        cache_key = f"feed:body:{url_name}:page={page}"
        return self._get_json(url, cache_key)

    def user_feed(self, url_name: str, page: int = 1) -> list[dict]:
        url = f"{BASE_URL}/feed/user/{url_name}.json?page={page}"
        cache_key = f"feed:user:{url_name}:page={page}"
        return self._get_json(url, cache_key)

    def all_authorities_csv(self) -> str:
        url = f"{BASE_URL}/body/all-authorities.csv"
        return self._get_text(url, cache_key="authorities:csv", cache_ttl=86400)

    def close(self) -> None:
        self._http.close()
        if self._cache:
            self._cache.close()
