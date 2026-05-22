#!/usr/bin/env python3
"""Multi-airline flight price tracker with Slack alerts."""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from providers import FareResult, PROVIDER_REGISTRY, RouteConfig, get_provider, load_all_providers
from providers.anti_ratelimit import RateLimitConfig

CONFIG_NAME = "config.yaml"


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_webhook(config: dict[str, Any]) -> str:
    env = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if env:
        return env
    return (config.get("slack_webhook_url") or "").strip()


def webhook_configured(webhook: str) -> bool:
    return bool(webhook) and "YOUR/WEBHOOK" not in webhook


def send_slack(webhook_url: str, text: str) -> None:
    requests.post(webhook_url, json={"text": text}, timeout=15).raise_for_status()


def notify_slack(webhook: str, title: str, body: str, *, dry_run: bool) -> None:
    if dry_run or not webhook_configured(webhook):
        print(f"[slack dry-run] {title}\n{body}", file=sys.stderr)
        return
    try:
        send_slack(webhook, f":warning: *{title}*\n{body}")
        print("  Slack error notification sent.")
    except Exception as exc:
        print(f"  Failed to send Slack notification: {exc}", file=sys.stderr)


def format_slack_message(route: RouteConfig, matches: list[FareResult]) -> str:
    guest_parts = [f"{route.adults} adult{'s' if route.adults != 1 else ''}"]
    if route.children:
        guest_parts.append(f"{route.children} child{'ren' if route.children != 1 else ''}")
    if route.infants:
        guest_parts.append(f"{route.infants} infant{'s' if route.infants != 1 else ''}")
    lines = [
        f"*Flight Deal: {route.name}*",
        f"{route.origin} -> {route.destination} ({', '.join(guest_parts)})",
    ]
    providers = route.providers_to_query()
    if len(providers) == 1:
        pname, limit = next(iter(providers.items()))
        lines.append(f"Threshold: <= {limit:,.0f} {route.currency.upper()}/person via {pname}")
    else:
        thresh = ", ".join(f"{p} <= {lim:,.0f}" for p, lim in sorted(providers.items()))
        lines.append(f"Thresholds ({route.currency.upper()}/person): {thresh}")
    for f in sorted(matches, key=lambda x: (x.provider, x.flight_date)):
        extra = f" ({f.airline})" if f.airline else ""
        lines.append(f"- {f.flight_date.isoformat()}: {f.price:,.0f} {f.currency}{extra} [{f.provider}]")
    book = next((f.booking_url for f in matches if f.booking_url), None)
    if book:
        lines.append(f"<{book}|Book now>")
    return "\n".join(lines)


def check_route(
    route_raw: dict[str, Any],
    config: dict[str, Any],
    dry_run: bool,
    webhook: str,
) -> tuple[bool, list[str]]:
    route = RouteConfig.from_dict(route_raw)
    providers = route.providers_to_query()
    print(f"Checking {route.name} ({', '.join(providers)})...")

    all_matches: list[FareResult] = []
    errors: list[str] = []

    for provider_name, max_price in providers.items():
        if provider_name not in PROVIDER_REGISTRY:
            msg = f"{route.name} / {provider_name}: unknown provider"
            errors.append(msg)
            print(f"  [{provider_name}] skip — unknown provider", file=sys.stderr)
            continue
        try:
            provider = get_provider(provider_name, config)
            fares = provider.search_fares(route)
            matches = provider.filter_deals(route, fares, max_price_per_person=max_price)
            if matches:
                print(f"  [{provider_name}] {len(matches)} fare(s) <= {max_price:,.0f}")
            all_matches.extend(matches)
        except Exception as exc:
            msg = f"{route.name} / {provider_name}: {exc}"
            errors.append(msg)
            print(f"  [{provider_name}] Error: {exc}", file=sys.stderr)

    if errors:
        notify_slack(
            webhook,
            f"Flight tracker errors — {route.name}",
            "\n".join(errors),
            dry_run=dry_run,
        )

    if not all_matches:
        print("  No matching fares.")
        return False, errors

    print(f"  Found {len(all_matches)} matching fare(s) total.")
    message = format_slack_message(route, all_matches)
    if dry_run:
        print(message)
        return True, errors

    if webhook_configured(webhook):
        send_slack(webhook, message)
        print("  Slack deal notification sent.")
    return True, errors


def run_check(config: dict[str, Any], dry_run: bool = False) -> int:
    webhook = resolve_webhook(config)
    if not dry_run and not webhook_configured(webhook):
        print("Error: Set SLACK_WEBHOOK_URL env or slack_webhook_url in config.yaml", file=sys.stderr)
        return 1

    routes = config.get("routes") or []
    if not routes:
        print("No routes configured.", file=sys.stderr)
        return 1

    load_all_providers()
    rl = RateLimitConfig(config.get("rate_limit"))
    max_workers = min(rl.max_concurrent_providers, len(routes))
    any_alert = False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(check_route, r, config, dry_run, webhook): r for r in routes
        }
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                alerted, _errs = fut.result()
                if alerted:
                    any_alert = True
            except Exception as exc:
                msg = f"{r.get('name', '?')}: {exc}"
                print(f"  Failed {r.get('name')}: {exc}", file=sys.stderr)
                notify_slack(
                    webhook,
                    f"Flight tracker route failed — {r.get('name', '?')}",
                    f"{msg}\n```\n{traceback.format_exc()}\n```",
                    dry_run=dry_run,
                )

    if not any_alert:
        print("Done. No deal alerts triggered.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-airline flight price tracker")
    parser.add_argument("--once", action="store_true", help="Single check and exit")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent / CONFIG_NAME)
    parser.add_argument("--dry-run", action="store_true", help="Print matches, no Slack")
    args = parser.parse_args()

    config_path = args.config
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    config = load_config(config_path)
    webhook = resolve_webhook(config)

    try:
        if args.once or args.dry_run:
            return run_check(config, dry_run=args.dry_run)

        interval = config.get("check_interval_minutes", 10)
        print(f"Loop mode: every {interval} min. Ctrl+C to stop.")
        while True:
            code = run_check(config, dry_run=False)
            if code != 0:
                notify_slack(
                    webhook,
                    "Flight tracker check failed",
                    f"run_check exited with code {code} at {datetime.now(timezone.utc).isoformat()}",
                    dry_run=False,
                )
            time.sleep(interval * 60)
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        notify_slack(webhook, "Flight tracker crashed", f"```\n{tb}\n```", dry_run=args.dry_run)
        return 1


if __name__ == "__main__":
    sys.exit(main())
