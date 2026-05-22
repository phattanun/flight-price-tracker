# Set up cron-job.org (reliable every 10 min)

GitHub schedule is unreliable. Use cron-job.org (free) to call the GitHub API every 10 minutes.

## Step 1: Create a GitHub token

1. Go to: https://github.com/settings/tokens?type=beta
2. **Generate new token** (Fine-grained)
   - Name: `flight-tracker-cron`
   - Expiration: 90 days (max) or No expiration (classic token)
   - Repository access: **Only select repositories** → `flight-price-tracker`
   - Permissions: **Actions → Read and write**
3. Copy the token (starts with `github_pat_...`)

## Step 2: Create the cron job

1. Go to: https://cron-job.org (sign up free)
2. **Create cronjob**
   - Title: `Flight price tracker`
   - URL: `https://api.github.com/repos/phattanun/flight-price-tracker/dispatches`
   - Schedule: **Every 10 minutes**
   - Request method: **POST**
   - Request headers:
     ```
     Authorization: Bearer YOUR_GITHUB_PAT_HERE
     Accept: application/vnd.github+json
     Content-Type: application/json
     ```
   - Request body:
     ```json
     {"event_type":"run-tracker"}
     ```
3. Save and **enable** the job

## Step 3: Verify

- cron-job.org → History → should show **204 No Content** responses (success)
- GitHub → Actions → runs should appear as **repository_dispatch** every 10 min
- Slack → deal alerts when prices are under your limits

## Notes

- Free cron-job.org allows 1-minute minimum interval
- 204 = GitHub accepted the dispatch (not the tracker result)
- If the token expires, runs will get 401 — renew the token and update cron-job.org
- You can disable GitHub's built-in schedule if you want (or leave both — concurrency prevents overlap)
