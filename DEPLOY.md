# Deploy online (free)

## Recommended: GitHub Actions (already wired)

- Repo: https://github.com/phattanun/flight-price-tracker
- Runs every **10 minutes** on `ubuntu-latest`
- Secret: `SLACK_WEBHOOK_URL`
- VietJet: REST + **Playwright** fallback if HTTP 403

**Test:** Actions → Flight price tracker → Run workflow

## Also: Render / Fly.io (always-on URL)

1. Connect repo on [Render](https://render.com) or `fly launch` (region `sin`)
2. Set env: `SLACK_WEBHOOK_URL`, optional `CRON_SECRET`
3. Ping every 10 min with [cron-job.org](https://cron-job.org) (free):
   - URL: `https://YOUR-APP.onrender.com/run?secret=YOUR_CRON_SECRET`
   - Method: GET or POST

Render **free web** sleeps when idle; cron-job.org wakes it each run.

## VietJet on cloud

Many datacenter IPs get HTTP 403. This repo tries:

1. `curl_cffi` Chrome impersonation + homepage cookies
2. Headless Chromium (Playwright) on 403
3. Optional `VIETJET_PROXY` env (residential proxy URL)

Google Flights usually works from cloud even when VietJet is blocked.

## Local

```bash
export SLACK_WEBHOOK_URL="..."
python tracker.py --once
```
