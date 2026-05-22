# Deploy (free) — every 10 minutes with full VietJet

**VietJet blocks datacenter IPs** (GitHub `ubuntu-latest`, Render, Railway, etc.). Your Mac home IP works.

## Repo

https://github.com/phattanun/flight-price-tracker (private) — `SLACK_WEBHOOK_URL` secret is set.

## Option A — Self-hosted GitHub runner on your Mac (recommended)

Keeps GitHub cron + secrets; **VietJet is not skipped**.

1. **`scripts/SETUP-RUNNER.md`**
2. https://github.com/phattanun/flight-price-tracker/settings/actions/runners/new → macOS
3. Run GitHub’s `./config.sh` then `./run.sh` (or `./svc.sh install`)
4. Test: **Actions → Flight price tracker → Run workflow**

Jobs queue until your runner is online.

## Option B — Local launchd (no runner)

```bash
./scripts/install-macos-launchd.sh
```

Set `SLACK_WEBHOOK_URL` in env or `config.yaml`.

## Free cloud-only?

| Host | VietJet |
|------|---------|
| GitHub ubuntu-latest | 403 |
| Render / Railway / Fly / Oracle free | Usually 403 |
| Your Mac | Works |

No reliable free datacenter path for VietJet without a paid residential proxy.

## Local test

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
python tracker.py --once
```

## Slack

- Deal alerts when price under your per-provider limits
- Errors when a provider or route fails (403 geo-blocks are not spammed to Slack)
