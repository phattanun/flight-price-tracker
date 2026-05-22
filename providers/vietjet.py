"""VietJet direct REST provider."""

from __future__ import annotations

from typing import Any

from providers import (
    BaseProvider, FareResult, RouteConfig, format_dd_mm_yyyy,
    months_in_range, parse_api_date, register_provider,
)
from providers.anti_ratelimit import RateLimitConfig, default_headers, random_delay

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
                ("tripType", "onewaytrip"), ("from_where", route.origin), ("to_where", route.destination),
                ("start", anchor), ("end", anchor),
                ("adultCount", str(route.adults)), ("childCount", str(route.children)),
                ("infantCount", str(route.infants)), ("promoCode", route.promo_code),
                ("currency", route.currency), ("year_months[]", ym), ("findLowestFare", "1"),
            ]
            resp = _vietjet_get(session, API_BASE, cfg=self._rl, params=params)
            payload = resp.json()
            if isinstance(payload, dict):
                merged.update(payload)

        fares: list[FareResult] = []
        for month_data in merged.values():
            if not isinstance(month_data, dict):
                continue
            for date_str, price in (month_data.get("data") or {}).items():
                fares.append(FareResult(
                    airline="VietJet", origin=route.origin, destination=route.destination,
                    flight_date=parse_api_date(date_str), price=float(price), currency=route.currency.upper(),
                    provider=self.name,
                    booking_url=f"https://th.vietjetair.com/select-flight-cheap?from_where={route.origin}&to_where={route.destination}",
                ))
        return fares


def _open_vietjet_session(cfg: RateLimitConfig) -> Any:
    """Warm up cookies from the homepage (required on some networks)."""
    headers = default_headers(VIETJET_HEADERS)
    random_delay(cfg)
    try:
        from curl_cffi import requests as cffi_requests

        session = cffi_requests.Session(impersonate="chrome120")
        session.get(HOME_URL, headers=headers, timeout=30)
        return session
    except ImportError:
        import requests

        session = requests.Session()
        session.headers.update(headers)
        session.get(HOME_URL, timeout=30)
        return session


def _vietjet_get(session: Any, url: str, *, cfg: RateLimitConfig, params: list[tuple[str, str]]) -> Any:
    random_delay(cfg)
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp
