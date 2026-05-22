# If GitHub Schedule does not run every 10 min

GitHub `schedule` on private repos is often delayed or skipped. Backup: **cron-job.org** triggers the workflow via API.

## One-time setup

1. GitHub → Settings → Developer settings → Fine-grained token
   - Repository access: `flight-price-tracker`
   - Permissions: **Actions: Read and write**
2. Repo → Settings → Secrets → Actions → `GH_WORKFLOW_PAT` = that token
3. [cron-job.org](https://cron-job.org) → Create cronjob:
   - URL: `https://api.github.com/repos/phattanun/flight-price-tracker/dispatches`
   - Schedule: every 10 minutes
   - Request method: **POST**
   - Headers: `Authorization: Bearer YOUR_PAT`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"event_type":"run-tracker"}`

Runs show in Actions as **repository_dispatch**.
