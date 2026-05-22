# Flight Price Tracker

Monitors fares from Bangkok/DMK and Singapore to Japan via **VietJet** (direct API) and **Google Flights** (aggregator covering all airlines). Alerts via Slack when prices fall below your threshold.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Slack Webhook Setup

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. Name it (e.g. "Flight Tracker") and pick your workspace
4. In the left sidebar, click **"Incoming Webhooks"**
5. Toggle **"Activate Incoming Webhooks"** to ON
6. Click **"Add New Webhook to Workspace"** at the bottom
7. Pick the channel you want alerts in (e.g. `#flight-deals`) → click **Allow**
8. Copy the webhook URL — it looks like:
   ```
   https://hooks.slack.com/services/T0XXXXXXX/B0XXXXXXX/xxxxxxxxxxxxxxxxxxx
   ```
9. Paste it in `config.yaml`:
   ```yaml
   slack_webhook_url: "https://hooks.slack.com/services/T0XXXXXXX/B0XXXXXXX/xxxxxxxxxxxxxxxxxxx"
   ```

## Commands

```bash
# Dry run — shows deals, no Slack
python tracker.py --once --dry-run

# Actually send Slack alerts
python tracker.py --once

# Loop mode (checks every 2 hours by default)
python tracker.py

# Run smoke tests
python test_runner.py
```

## Config

Edit `config.yaml` to add/remove routes.

**All providers (default)** — omit `providers`; every provider is queried with the same `max_price_per_person`:

```yaml
- name: "BKK-KIX"
  from: BKK
  to: KIX
  max_price_per_person: 6000
  # ...
```

**Per-provider limits** — only listed providers are queried, each with its own threshold:

```yaml
- name: "BKK-NRT"
  from: BKK
  to: NRT
  max_price_per_person: 5000   # fallback if you use list form below
  providers:
    vietjet: 5000
    google_flights: 500
```

**Subset of providers, same limit** — list names; each uses `max_price_per_person`:

```yaml
  providers:
    - vietjet
    - google_flights
  max_price_per_person: 6000
```

| Field | Example | Description |
|-------|---------|-------------|
| `from` / `to` | `BKK` / `NRT` | Airport IATA codes |
| `max_price_per_person` | `6000` | Default threshold (all providers, or list form) |
| `providers` | see above | Optional filter + per-provider max |
| `date_range_start` / `end` | `"2027-01-01"` | Search window |

## Providers

| Provider | How it works |
|----------|-------------|
| **vietjet** | Direct REST API (`getLowFareCalendar`) — fast, reliable, no browser needed |
| **google_flights** | `fast-flights` library — aggregates fares from all airlines on Google Flights |

Google Flights covers ANA, JAL, Thai Airways, Singapore Airlines, AirAsia, Scoot, Zipair, etc. — so you still see all airlines' prices through this one provider.
