"""VietJet direct REST provider (curl_cffi + ScraperAPI proxy for cloud)."""

from __future__ import annotations

import os
from datetime import date, timedelta
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
        if route.is_round_trip:
            return self._search_round_trip(route)
        return self._search_one_way(route)

    def _search_one_way(self, route: RouteConfig) -> list[FareResult]:
        merged = self._load_calendar(None, route, trip_type="onewaytrip")
        fares: list[FareResult] = []
        for month_data in merged.values():
            if not isinstance(month_data, dict):
                continue
            for date_str, price in (month_data.get("data") or {}).items():
                fd = parse_api_date(date_str)
                if not (route.date_range_start <= fd <= route.date_range_end):
                    continue
                fares.append(
                    FareResult(
                        airline="VietJet",
                        origin=route.origin,
                        destination=route.destination,
                        flight_date=fd,
                        price=float(price),
                        currency=route.currency.upper(),
                        provider=self.name,
                        booking_url=_booking_url(route, fd, trip_type="onewaytrip"),
                    )
                )
        return fares

    def _search_round_trip(self, route: RouteConfig) -> list[FareResult]:
        if route.trip_duration_min is None or route.trip_duration_max is None:
            return []
        session = _open_vietjet_session(self._rl)
        outbound_prices = self._calendar_prices(
            session,
            route,
            origin=route.origin,
            destination=route.destination,
            range_start=route.date_range_start,
            range_end=route.date_range_end,
        )
        return_start = route.date_range_start + timedelta(days=route.trip_duration_min)
        return_end = route.date_range_end + timedelta(days=route.trip_duration_max)
        return_prices = self._calendar_prices(
            session,
            route,
            origin=route.destination,
            destination=route.origin,
            range_start=return_start,
            range_end=return_end,
        )

        fares: list[FareResult] = []
        outbound = route.date_range_start
        while outbound <= route.date_range_end:
            for trip_days in range(route.trip_duration_min, route.trip_duration_max + 1):
                return_date = outbound + timedelta(days=trip_days)
                out_price = outbound_prices.get(outbound)
                ret_price = return_prices.get(return_date)
                if out_price is None or ret_price is None:
                    continue
                fares.append(
                    FareResult(
                        airline="VietJet",
                        origin=route.origin,
                        destination=route.destination,
                        flight_date=outbound,
                        price=out_price + ret_price,
                        currency=route.currency.upper(),
                        provider=self.name,
                        booking_url=_booking_url(
                            route,
                            outbound,
                            trip_type="roundtrip",
                            return_date=return_date,
                        ),
                        return_date=return_date,
                        trip_days=trip_days,
                    )
                )
            outbound += timedelta(days=1)
        return fares

    def _calendar_prices(
        self,
        session: Any,
        route: RouteConfig,
        *,
        origin: str,
        destination: str,
        range_start: date,
        range_end: date,
    ) -> dict[date, float]:
        merged = self._load_calendar(
            session,
            route,
            trip_type="onewaytrip",
            origin=origin,
            destination=destination,
            range_start=range_start,
            range_end=range_end,
        )
        prices: dict[date, float] = {}
        for month_data in merged.values():
            if not isinstance(month_data, dict):
                continue
            for date_str, price in (month_data.get("data") or {}).items():
                fd = parse_api_date(date_str)
                if range_start <= fd <= range_end:
                    prices[fd] = float(price)
        return prices

    def _load_calendar(
        self,
        session: Any | None,
        route: RouteConfig,
        *,
        trip_type: str,
        origin: str | None = None,
        destination: str | None = None,
        range_start: date | None = None,
        range_end: date | None = None,
    ) -> dict:
        leg_origin = origin or route.origin
        leg_destination = destination or route.destination
        start = range_start or route.date_range_start
        end = range_end or route.date_range_end
        anchor = format_dd_mm_yyyy(start)
        own_session = session is None
        if own_session:
            session = _open_vietjet_session(self._rl)
        merged: dict = {}
        try:
            for ym in months_in_range(start, end):
                params = [
                    ("tripType", trip_type),
                    ("from_where", leg_origin),
                    ("to_where", leg_destination),
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
                payload = _request_calendar(session, API_BASE, cfg=self._rl, params=params)
                if isinstance(payload, dict):
                    merged.update(payload)
        finally:
            if own_session and hasattr(session, "close"):
                session.close()
        return merged


def _booking_url(
    route: RouteConfig,
    outbound: date,
    *,
    trip_type: str,
    return_date: date | None = None,
) -> str:
    qs = [
        ("tripType", trip_type),
        ("currency", route.currency),
        ("from_where", route.origin),
        ("to_where", route.destination),
        ("start", format_dd_mm_yyyy(outbound)),
        ("end", format_dd_mm_yyyy(outbound)),
        ("adultCount", str(route.adults)),
        ("childCount", str(route.children)),
        ("infantCount", str(route.infants)),
        ("promoCode", route.promo_code),
        ("findLowestFare", "1"),
    ]
    if return_date is not None:
        ret = format_dd_mm_yyyy(return_date)
        qs.extend([("returnStart", ret), ("returnEnd", ret)])
    return f"https://th.vietjetair.com/select-flight-cheap?{urlencode(qs)}"


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


def _request_calendar(
    session: Any, url: str, *, cfg: RateLimitConfig, params: list[tuple[str, str]]
) -> dict:
    random_delay(cfg)
    resp = session.get(url, params=params, timeout=30)
    if resp.status_code == 403:
        key = os.environ.get("SCRAPERAPI_KEY", "").strip()
        if key:
            print("  [vietjet] HTTP 403 — retrying via ScraperAPI (residential)...")
            return _request_calendar_scraperapi(url, params, key)
        _raise_blocked()
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _request_calendar_scraperapi(
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
