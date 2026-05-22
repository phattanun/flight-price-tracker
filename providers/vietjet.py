"""VietJet direct REST provider (curl_cffi + Playwright fallback on cloud WAF)."""

from __future__ import annotations

import json
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
        print("  [vietjet] HTTP 403 on REST — retrying via headless browser...")
        return _fetch_calendar_playwright(url, params, cfg)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _fetch_calendar_playwright(
    url: str, params: list[tuple[str, str]], cfg: RateLimitConfig
) -> dict:
    random_delay(cfg)
    full_url = f"{url}?{urlencode(params)}"
    headers = default_headers(VIETJET_HEADERS)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise requests.HTTPError(
            "403 from VietJet and playwright is not installed", response=None
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=headers.get("User-Agent"),
            locale="en-US",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90_000)
        api_resp = page.request.get(full_url, headers=headers, timeout=90_000)
        status = api_resp.status
        body = api_resp.text()
        browser.close()

    if status == 403:
        raise requests.HTTPError(f"VietJet blocked (HTTP 403) from this host", response=None)
    if status >= 400:
        raise requests.HTTPError(f"VietJet API HTTP {status}", response=None)
    data = json.loads(body)
    return data if isinstance(data, dict) else {}
