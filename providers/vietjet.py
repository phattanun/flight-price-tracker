"""VietJet direct REST provider (curl_cffi + ScraperAPI proxy for cloud)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from providers import (
    BaseProvider,
    FareResult,
    RouteConfig,
    format_dd_mm_yyyy,
    months_in_range,
    parse_api_date,
    register_provider,
)
from providers.anti_ratelimit import RateLimitConfig, default_headers, pick_proxy, random_delay

API_BASE = "https://th.vietjetair.com/flight/getLowFareCalendar"
HOME_URL = "https://th.vietjetair.com/en"
VIETJET_HEADERS = {
    "Referer": "https://th.vietjetair.com/",
    "Origin": "https://th.vietjetair.com",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
    "Accept": "application/json, text/plain, */*",
}


@register_provider
class VietJetProvider(BaseProvider):
    name = "vietjet"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._rl = RateLimitConfig((config or {}).get("rate_limit"))

    def search_fares(self, route: RouteConfig) -> list[FareResult]:
        if _should_skip_vietjet():
            return []
        anchor = format_dd_mm_yyyy(route.date_range_start)
        merged: dict = {}
        session = _open_vietjet_session(self._rl)
        for ym in months_in_range(route.date_range_start, route.date_range_end):
            params = [
                ("tripType", "onewaytrip"),
                ("from_where", route.origin),
                ("to_where", route.destination),
                ("start", anchor),
                ("end", anchor),
                ("adultCount", str(route.adults)),
                ("childCount", str(route.children)),
                ("infantCount", str(route.infants)),
                ("promoCode", route.promo_code),
                ("currency", route.currency),
                ("year_months[]", ym),
                ("findLowestFare", "1"),
            ]
            payload = _fetch_calendar(session, API_BASE, cfg=self._rl, params=params)
            if isinstance(payload, dict):
                merged.update(payload)

        fares: list[FareResult] = []
        for month_data in merged.values():
            if not isinstance(month_data, dict):
                continue
            for date_str, price in (month_data.get("data") or {}).items():
                fares.append(
                    FareResult(
                        airline="VietJet",
                        origin=route.origin,
                        destination=route.destination,
                        flight_date=parse_api_date(date_str),
                        price=float(price),
                        currency=route.currency.upper(),
                        provider=self.name,
                        booking_url=(
                            f"https://th.vietjetair.com/select-flight-cheap?"
                            f"from_where={route.origin}&to_where={route.destination}"
                        ),
                    )
                )
        return fares


def _open_vietjet_session(cfg: RateLimitConfig) -> Any:
    headers = default_headers(VIETJET_HEADERS)
    random_delay(cfg)
    proxies = pick_proxy(cfg) or (
        {"http": p, "https": p}
        if (p := os.environ.get("VIETJET_PROXY", "").strip())
        else None
    )
    try:
        from curl_cffi import requests as cffi_requests

        session = cffi_requests.Session(impersonate="chrome120")
        session.get(HOME_URL, headers=headers, timeout=30, proxies=proxies)
        return session
    except ImportError:
        session = requests.Session()
        session.headers.update(headers)
        session.get(HOME_URL, timeout=30, proxies=proxies)
        return session


def _fetch_calendar(
    session: Any, url: str, *, cfg: RateLimitConfig, params: list[tuple[str, str]]
) -> dict:
    random_delay(cfg)
    resp = session.get(url, params=params, timeout=30)
    if resp.status_code == 403:
        key = os.environ.get("SCRAPERAPI_KEY", "").strip()
        if key:
            print("  [vietjet] HTTP 403 — retrying via ScraperAPI (residential)...")
            return _fetch_calendar_scraperapi(url, params, key)
        _raise_blocked()
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _fetch_calendar_scraperapi(
    url: str, params: list[tuple[str, str]], api_key: str
) -> dict:
    """ScraperAPI free tier: https://www.scraperapi.com/ (1000 req/mo)."""
    target = f"{url}?{urlencode(params)}"
    proxy_resp = requests.get(
        "https://api.scraperapi.com",
        params={"api_key": api_key, "url": target, "country_code": "th"},
        timeout=120,
    )
    if proxy_resp.status_code == 403:
        _raise_blocked()
    proxy_resp.raise_for_status()
    data = proxy_resp.json()
    return data if isinstance(data, dict) else {}


def _should_skip_vietjet() -> bool:
    """Skip VietJet on GitHub Actions when no ScraperAPI key is available.

    VietJet blocks non-Thai IPs. Without a proxy key, attempting the request
    just wastes time and produces noisy 403 logs.
    """
    on_github = os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
    if not on_github:
        return False
    return not bool(os.environ.get("SCRAPERAPI_KEY", "").strip())


def _fake_response(status: int) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    return r


def _raise_blocked() -> None:
    raise requests.HTTPError(
        "VietJet blocked (HTTP 403) from this host",
        response=_fake_response(403),
    )
