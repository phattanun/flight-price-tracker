"""VietJet direct REST provider."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from providers import (
    BaseProvider, FareResult, RouteConfig, format_dd_mm_yyyy,
    months_in_range, parse_api_date, register_provider,
)
from providers.anti_ratelimit import RateLimitConfig, request_with_retry

API_BASE = "https://th.vietjetair.com/flight/getLowFareCalendar"


@register_provider
class VietJetProvider(BaseProvider):
    name = "vietjet"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._rl = RateLimitConfig((config or {}).get("rate_limit"))

    def search_fares(self, route: RouteConfig) -> list[FareResult]:
        anchor = format_dd_mm_yyyy(route.date_range_start)
        merged: dict = {}
        for ym in months_in_range(route.date_range_start, route.date_range_end):
            params = [
                ("tripType", "onewaytrip"), ("from_where", route.origin), ("to_where", route.destination),
                ("start", anchor), ("end", anchor),
                ("adultCount", str(route.adults)), ("childCount", str(route.children)),
                ("infantCount", str(route.infants)), ("promoCode", route.promo_code),
                ("currency", route.currency), ("year_months[]", ym), ("findLowestFare", "1"),
            ]
            resp = request_with_retry("GET", API_BASE, cfg=self._rl, params=params)
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
