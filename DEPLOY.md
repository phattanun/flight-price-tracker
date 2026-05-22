# Deploy (free) — GitHub Actions every 10 minutes

Hosting uses **GitHub Actions** (free for public repos). No server to manage.

## Repo

https://github.com/phattanun/flight-price-tracker (private)

- `SLACK_WEBHOOK_URL` secret is already set on the repo.
- App code is pushed; **you must add the workflow** (one-time) — see below.

## Already done (automated setup)

- Private repo on your GitHub account
- `SLACK_WEBHOOK_URL` repository secret
- Workflow runs every **10 minutes** (UTC cron)

## Manual setup

1. Create a repo on GitHub and push this folder.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SLACK_WEBHOOK_URL`
   - Value: your Slack incoming webhook URL
3. **Actions** tab → enable workflows if prompted.
4. Run once: **Actions → Flight price tracker → Run workflow**.

## Local run with webhook

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
python tracker.py --once
```

Or put the URL in `config.yaml` under `slack_webhook_url` (do not commit real URLs to a public repo).

## Slack on errors

The tracker posts to Slack when:
- A provider fails for a route (per-route error message)
- An entire route check crashes (with stack trace)
- The process crashes in loop mode

Deal alerts use a separate message (no warning emoji).

## Schedule note

GitHub may delay scheduled runs by a few minutes on the free tier. Minimum cron interval is 5 minutes; this project uses `*/10` (every 10 minutes UTC).


## Enable the 10-minute schedule (required once)

GitHub blocked pushing the workflow file without extra OAuth scope. Do **one** of:

### Option A — Browser auth (recommended)

1. Open https://github.com/login/device
2. Enter code **E4DC-F509** (or run `gh auth refresh -s workflow` for a new code)
3. Then in terminal:

```bash
cd "/Users/paukkarapunt/Documents/playground/vietjet tracker"
git add .github/workflows/tracker.yml
git commit -m "Add scheduled workflow"
git push origin main
```

### Option B — Paste in GitHub UI

1. Repo → **Add file** → **Create new file**
2. Path: `.github/workflows/tracker.yml`
3. Paste contents from local `.github/workflows/tracker.yml` in this project
4. Commit to `main`

Then **Actions** → enable workflows if asked → **Run workflow** to test.
