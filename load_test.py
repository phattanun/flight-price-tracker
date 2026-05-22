#!/usr/bin/env python3
"""Stress-test providers to discover rate-limit thresholds."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

from providers import RouteConfig, get_provider, load_all_providers
from providers.anti_ratelimit import RateLimitConfig


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def stress_provider(provider_name: str, route_raw: dict, config: dict, requests_count: int) -> None:
    load_all_providers()
    route = RouteConfig.from_dict({**route_raw, "provider": provider_name})
    provider = get_provider(provider_name, config)
    rl = RateLimitConfig({"min_delay_seconds": 0.5, "max_delay_seconds": 1.5, "max_retries": 1})
    config = {**config, "rate_limit": vars(rl)}

    ok = fail = 0
    latencies: list[float] = []
    for i in range(requests_count):
        t0 = time.perf_counter()
        try:
            provider.search_fares(route)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [{i+1}] FAIL: {e}")
        latencies.append(time.perf_counter() - t0)
        time.sleep(0.5)

    avg = sum(latencies) / len(latencies) if latencies else 0
    print(f"\n{provider_name}: {ok} ok, {fail} fail, avg {avg:.2f}s")
    if fail and ok == 0:
        print("  Likely rate-limited or auth required.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provider load tester")
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "config.yaml")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    config = load_config(args.config)
    routes = [r for r in config.get("routes", []) if r.get("provider") == args.provider]
    if not routes:
        print(f"No routes for provider {args.provider}", file=sys.stderr)
        sys.exit(1)

    stress_provider(args.provider, routes[0], config, args.count)


if __name__ == "__main__":
    main()
