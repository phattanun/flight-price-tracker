"""Anti-rate-limit utilities."""

from __future__ import annotations

import random
import time
from typing import Any

import requests

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class RateLimitConfig:
    def __init__(self, raw: dict[str, Any] | None = None) -> None:
        raw = raw or {}
        self.min_delay_seconds = float(raw.get("min_delay_seconds", 3))
        self.max_delay_seconds = float(raw.get("max_delay_seconds", 10))
        self.max_retries = int(raw.get("max_retries", 3))
        self.backoff_multiplier = float(raw.get("backoff_multiplier", 2.0))
        self.proxies: list[str] = list(raw.get("proxies") or [])
        self.max_concurrent_providers = int(raw.get("max_concurrent_providers", 3))


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def random_delay(cfg: RateLimitConfig) -> None:
    time.sleep(random.uniform(cfg.min_delay_seconds, cfg.max_delay_seconds))


def pick_proxy(cfg: RateLimitConfig) -> dict[str, str] | None:
    if not cfg.proxies:
        return None
    p = random.choice(cfg.proxies)
    return {"http": p, "https": p}


def default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"User-Agent": random_user_agent(), "Accept": "application/json, text/plain, */*"}
    if extra:
        h.update(extra)
    return h


def request_with_retry(method: str, url: str, *, cfg: RateLimitConfig | None = None,
                       session: requests.Session | None = None, **kwargs: Any) -> requests.Response:
    cfg = cfg or RateLimitConfig()
    random_delay(cfg)
    kwargs.setdefault("headers", {})
    kwargs["headers"] = default_headers(kwargs["headers"])
    proxies = pick_proxy(cfg)
    if proxies:
        kwargs["proxies"] = proxies
    sess = session or requests
    last: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            resp = sess.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if resp.status_code in (429, 503) and attempt < cfg.max_retries:
                time.sleep(cfg.backoff_multiplier ** attempt + random.uniform(0, 1))
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last = e
            if attempt >= cfg.max_retries:
                raise
            time.sleep(cfg.backoff_multiplier ** attempt + random.uniform(0, 1))
    if last:
        raise last
    raise RuntimeError("request failed")
