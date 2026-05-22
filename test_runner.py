#!/usr/bin/env python3
"""Smoke test: each provider returns fares for at least one route."""

from __future__ import annotations

import sys
import yaml
from pathlib import Path

from providers import PROVIDER_REGISTRY, RouteConfig, get_provider, load_all_providers

ROOT = Path(__file__).parent
CONFIG = ROOT / "config.yaml"

SMOKE_ROUTE = dict(
    name="smoke BKK-KIX",
    **{"from": "BKK"},
    to="KIX",
    adults=1,
    children=0,
    infants=0,
    currency="thb",
    max_price_per_person=9_999_999,
    date_range_start="2027-01-01",
    date_range_end="2027-01-31",
)


def main() -> int:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["rate_limit"] = {"min_delay_seconds": 0.5, "max_delay_seconds": 1.5, "max_retries": 2}

    load_all_providers()
    route = RouteConfig.from_dict(SMOKE_ROUTE)

    print("Provider smoke tests")
    print("-" * 60)

    failed = []
    for name in sorted(PROVIDER_REGISTRY):
        try:
            provider = get_provider(name, config)
            fares = provider.search_fares(route)
            if fares:
                print(f"{name}: PASS — {len(fares)} fares")
            else:
                print(f"{name}: FAIL — 0 fares")
                failed.append(name)
        except Exception as exc:
            print(f"{name}: FAIL — {exc}")
            failed.append(name)

    print("-" * 60)
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    print("All providers returned fares.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
