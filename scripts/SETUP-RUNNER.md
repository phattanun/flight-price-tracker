# Run on your Mac (free) — full VietJet + Google Flights every 10 min

GitHub cloud = 403 from VietJet. **Self-hosted runner on your Mac** = same workflow, your home IP.

## Setup (~5 min)

1. https://github.com/phattanun/flight-price-tracker/settings/actions/runners/new
2. macOS → ARM64 or x64
3. Run the commands GitHub shows (download runner, `./config.sh`, `./run.sh` or `./svc.sh install`)

## Or local cron (no GitHub runner)

```bash
./scripts/install-macos-launchd.sh
```

## Other free clouds (Render, Railway, Oracle)

Still datacenter IPs — VietJet usually 403. Self-hosted or local cron are the free paths that work.
