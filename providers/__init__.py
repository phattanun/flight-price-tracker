"""Flight price provider plugin system."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
import calendar
from datetime import date, datetime, timedelta
from typing import Any

import requests


@dataclass
class FareResult:
    airline: str
    origin: str
    destination: str
    flight_date: date
    price: float
    currency: str
    provider: str
    flight_number: str | None = None
    booking_url: str | None = None
    return_date: date | None = None
    trip_days: int | None = None


@dataclass
class RouteConfig:
    name: str
    origin: str
    destination: str
    adults: int
    children: int
    infants: int
    currency: str
    max_price_per_person: float
    date_range_start: date
    date_range_end: date
    promo_code: str = ""
    trip_type: str = "one_way"
    trip_duration_min: int | None = None
    trip_duration_max: int | None = None
    provider_limits: dict[str, float] | None = None
    date_windows: list[tuple[date, date]] | None = None
    extra: dict[str, Any] | None = None

    @property
    def is_round_trip(self) -> bool:
        return self.trip_type == "round_trip"

    def providers_to_query(self) -> dict[str, float]:
        if self.provider_limits:
            return dict(self.provider_limits)
        return {name: self.max_price_per_person for name in PROVIDER_REGISTRY}

    def outbound_windows(self) -> list[tuple[date, date]]:
        if self.date_windows:
            return self.date_windows
        return [(self.date_range_start, self.date_range_end)]

    def outbound_date_in_range(self, d: date) -> bool:
        return any(start <= d <= end for start, end in self.outbound_windows())

    def return_range_start(self) -> date:
        stay = self.trip_duration_min or 0
        return min(start + timedelta(days=stay) for start, _ in self.outbound_windows())

    def return_range_end(self) -> date:
        stay = self.trip_duration_max or 0
        return max(end + timedelta(days=stay) for _, end in self.outbound_windows())

    def return_date_in_range(self, d: date) -> bool:
        return self.return_range_start() <= d <= self.return_range_end()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RouteConfig:
        provider_limits = _parse_provider_limits(raw)
        if "max_price_per_person" in raw:
            max_price = float(raw["max_price_per_person"])
        elif provider_limits:
            max_price = max(provider_limits.values())
        else:
            raise ValueError(
                f"route {raw.get('name')}: set max_price_per_person or providers with limits"
            )
        trip_type = str(raw.get("trip_type", "one_way")).replace("-", "_").lower()
        duration_min = raw.get("trip_duration_min")
        duration_max = raw.get("trip_duration_max")
        trip_duration_min = int(duration_min) if duration_min is not None else None
        trip_duration_max = int(duration_max) if duration_max is not None else None
        if trip_type == "round_trip":
            if trip_duration_min is None or trip_duration_max is None:
                raise ValueError(
                    f"route {raw.get('name')}: round_trip requires trip_duration_min and trip_duration_max"
                )
            if trip_duration_min > trip_duration_max:
                raise ValueError(
                    f"route {raw.get('name')}: trip_duration_min cannot exceed trip_duration_max"
                )
        elif trip_duration_min is not None or trip_duration_max is not None:
            raise ValueError(
                f"route {raw.get('name')}: trip_duration_min/max only valid with trip_type: round_trip"
            )

        date_windows = None
        if raw.get("date_ranges"):
            date_windows = [
                (parse_iso_date(w["start"]), parse_iso_date(w["end"]))
                for w in raw["date_ranges"]
            ]
            date_range_start = min(s for s, _ in date_windows)
            date_range_end = max(e for _, e in date_windows)
        else:
            date_range_start = parse_iso_date(raw["date_range_start"])
            date_range_end = parse_iso_date(raw["date_range_end"])

        return cls(
            name=raw.get("name") or f"{raw['from']} -> {raw['to']}",
            origin=raw["from"],
            destination=raw["to"],
            adults=int(raw.get("adults", 1)),
            children=int(raw.get("children", 0)),
            infants=int(raw.get("infants", 0)),
            currency=str(raw.get("currency", "thb")).lower(),
            max_price_per_person=max_price,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            promo_code=str(raw.get("promo_code", "")),
            trip_type=trip_type,
            trip_duration_min=trip_duration_min,
            trip_duration_max=trip_duration_max,
            provider_limits=provider_limits,
            date_windows=date_windows,
            extra={k: v for k, v in raw.items() if k not in _ROUTE_KEYS},
        )


def is_provider_geo_blocked(exc: Exception) -> bool:
    """True when the remote site blocks this network (common on cloud/datacenter IPs)."""
    if isinstance(exc, requests.HTTPError):
        if exc.response is not None:
            return exc.response.status_code in (403, 451)
        msg = str(exc).lower()
        return "403" in msg or "blocked" in msg
    msg = str(exc).lower()
    return "403" in msg and ("blocked" in msg or "geo" in msg)


def providers_for_check(route: RouteConfig) -> dict[str, float]:
    """Optional SKIP_PROVIDERS env (comma-separated), e.g. SKIP_PROVIDERS=vietjet."""
    raw = route.providers_to_query()
    skip_env = os.getenv("SKIP_PROVIDERS", "").strip()
    if not skip_env:
        return raw
    skip = {p.strip() for p in skip_env.split(",") if p.strip()}
    if skip:
        skipped = [p for p in raw if p in skip]
        if skipped:
            print(f"  Skipping provider(s): {', '.join(skipped)} (SKIP_PROVIDERS)")
    return {k: v for k, v in raw.items() if k not in skip}


_ROUTE_KEYS = frozenset({
    "name", "provider", "providers", "from", "to", "adults", "children", "infants",
    "currency", "max_price_per_person", "date_range_start", "date_range_end", "promo_code",
    "trip_type", "trip_duration_min", "trip_duration_max", "date_ranges",
})


def _parse_provider_limits(raw: dict[str, Any]) -> dict[str, float] | None:
    spec = raw.get("providers")
    if spec is None:
        legacy = raw.get("provider")
        if legacy:
            return {str(legacy): float(raw["max_price_per_person"])}
        return None
    if isinstance(spec, dict):
        return {str(k): float(v) for k, v in spec.items()}
    if isinstance(spec, list):
        if "max_price_per_person" not in raw:
            raise ValueError(
                f"route {raw.get('name')}: max_price_per_person required when providers is a list"
            )
        default = float(raw["max_price_per_person"])
        return {str(p): default for p in spec}
    raise ValueError(f"route {raw.get('name')}: providers must be a dict or list")


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_api_date(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def months_in_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def format_dd_mm_yyyy(d: date) -> str:
    return d.strftime("%d/%m/%Y")



def round_trip_stays_to_search(route: RouteConfig, outbound: date) -> range:
    """Stay lengths to query for one outbound date.

    Returns may fall in the next calendar month (e.g. depart 28 Feb, return 10 Mar).
    On large scans we still trim API calls mid-month, but always search the full
    stay range near month-end and whenever the minimum stay crosses a month boundary.
    """
    lo = route.trip_duration_min
    hi = route.trip_duration_max
    if lo is None or hi is None:
        return range(0)
    total_days = sum((end - start).days + 1 for start, end in route.outbound_windows())
    if total_days <= 45:
        return range(lo, hi + 1)
    last_day = calendar.monthrange(outbound.year, outbound.month)[1]
    min_return = outbound + timedelta(days=lo)
    crosses_month = min_return.month != outbound.month or min_return.year != outbound.year
    near_month_end = outbound.day > last_day - hi
    if crosses_month or near_month_end:
        return range(lo, hi + 1)
    if lo == hi:
        return range(lo, lo + 1)
    return range(lo, hi + 1, hi - lo)


def best_round_trip_per_month(matches: list[FareResult]) -> list[FareResult]:
    """Cheapest deal per provider and departure month (return may be the next month)."""
    best: dict[tuple[str, int, int], FareResult] = {}
    for fare in matches:
        key = (fare.provider, fare.flight_date.year, fare.flight_date.month)
        if key not in best or fare.price < best[key].price:
            best[key] = fare
    return sorted(best.values(), key=lambda f: (f.provider, f.flight_date, f.trip_days or 0))

class BaseProvider(ABC):
    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def search_fares(self, route: RouteConfig) -> list[FareResult]:
        pass

    def filter_deals(
        self,
        route: RouteConfig,
        fares: list[FareResult],
        *,
        max_price_per_person: float | None = None,
    ) -> list[FareResult]:
        limit = route.max_price_per_person if max_price_per_person is None else max_price_per_person
        if route.is_round_trip:
            return [
                f for f in fares
                if route.outbound_date_in_range(f.flight_date)
                and f.return_date is not None
                and route.return_date_in_range(f.return_date)
                and route.trip_duration_min <= (f.trip_days or 0) <= route.trip_duration_max
                and f.price <= limit
            ]
        return [
            f for f in fares
            if route.date_range_start <= f.flight_date <= route.date_range_end
            and f.price <= limit
        ]


PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {}


def register_provider(cls: type[BaseProvider]) -> type[BaseProvider]:
    PROVIDER_REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str, config: dict[str, Any] | None = None) -> BaseProvider:
    if name not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider '{name}'. Available: {sorted(PROVIDER_REGISTRY)}")
    return PROVIDER_REGISTRY[name](config)


def load_all_providers() -> None:
    from providers import google_flights, vietjet  # noqa: F401
