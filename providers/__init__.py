"""Flight price provider plugin system."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
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
    provider_limits: dict[str, float] | None = None
    extra: dict[str, Any] | None = None

    def providers_to_query(self) -> dict[str, float]:
        if self.provider_limits:
            return dict(self.provider_limits)
        return {name: self.max_price_per_person for name in PROVIDER_REGISTRY}

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
        return cls(
            name=raw.get("name") or f"{raw['from']} -> {raw['to']}",
            origin=raw["from"],
            destination=raw["to"],
            adults=int(raw.get("adults", 1)),
            children=int(raw.get("children", 0)),
            infants=int(raw.get("infants", 0)),
            currency=str(raw.get("currency", "thb")).lower(),
            max_price_per_person=max_price,
            date_range_start=parse_iso_date(raw["date_range_start"]),
            date_range_end=parse_iso_date(raw["date_range_end"]),
            promo_code=str(raw.get("promo_code", "")),
            provider_limits=provider_limits,
            extra={k: v for k, v in raw.items() if k not in _ROUTE_KEYS},
        )


def is_provider_geo_blocked(exc: Exception) -> bool:
    """True when the remote site blocks this network (common on cloud/datacenter IPs)."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (403, 451)
    return False


def providers_for_check(route: RouteConfig) -> dict[str, float]:
    """Apply SKIP_PROVIDERS / auto-skip vietjet on GitHub Actions runners."""
    raw = route.providers_to_query()
    skip: set[str] = set()
    if os.getenv("GITHUB_ACTIONS") == "true":
        skip.update(
            p.strip()
            for p in os.getenv("SKIP_PROVIDERS", "vietjet").split(",")
            if p.strip()
        )
    elif os.getenv("SKIP_PROVIDERS"):
        skip.update(
            p.strip() for p in os.getenv("SKIP_PROVIDERS", "").split(",") if p.strip()
        )
    if skip:
        skipped = [p for p in raw if p in skip]
        if skipped:
            print(f"  Skipping provider(s) on this host: {', '.join(skipped)}")
    return {k: v for k, v in raw.items() if k not in skip}


_ROUTE_KEYS = frozenset({
    "name", "provider", "providers", "from", "to", "adults", "children", "infants",
    "currency", "max_price_per_person", "date_range_start", "date_range_end", "promo_code",
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
