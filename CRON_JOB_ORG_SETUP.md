# cron-job.org setup for the DLTLLY ticket monitor

This configuration makes cron-job.org trigger the existing GitHub Actions
workflow every five minutes. cron-job.org only submits the trigger; GitHub
continues to run `monitor.py`, store the Discord secret, and commit ticket state.

## Before you start

1. Commit and push the local repository changes to the `main` branch.
2. Open the repository's **Actions** tab and confirm that **DLTLLY Ticket
   Monitor** still offers the **Run workflow** button.
3. Confirm that the repository secret `DISCORD_WEBHOOK_URL` still exists under
   **Settings > Secrets and variables > Actions**.

## 1. Create a restricted GitHub token

1. Sign in to GitHub.
2. Open your profile menu and select **Settings**.
3. In the left sidebar, open **Developer settings**.
4. Open **Personal access tokens > Fine-grained tokens**.
5. Select **Generate new token**. GitHub may ask you to authenticate again.
6. Use a descriptive name such as `cron-job.org dltlly dispatcher`.
7. Choose an expiration date. A 90-day expiration limits exposure, but requires
   regular rotation. Record the expiry date somewhere you will notice it.
8. Set **Resource owner** to `nbrandtner`.
9. Under **Repository access**, choose **Only select repositories** and select
   `dltlly-ticket-monitor`.
10. Under **Repository permissions**, set **Actions** to **Read and write**.
    Leave every other optional permission at **No access**. GitHub adds the
    read-only Metadata permission automatically.
11. Select **Generate token**.
12. Copy the token immediately. GitHub will not show it again.

Treat this token like a password. Never add it to this repository, a screenshot,
or a Discord message. It will be stored as a secret request header in your
cron-job.org account.

## 2. Create the cron-job.org job

1. Sign in to <https://cron-job.org/> and open the dashboard.
2. Select **Create cronjob**.
3. Enter the title `DLTLLY Ticket Monitor`.
4. Set the URL to:

   ```text
   https://api.github.com/repos/nbrandtner/dltlly-ticket-monitor/actions/workflows/ticket-monitor.yml/dispatches
   ```

5. Set the request method to **POST**.
6. Add these request headers, replacing `YOUR_TOKEN` with the token created
   above:

   ```text
   Accept: application/vnd.github+json
   Authorization: Bearer YOUR_TOKEN
   Content-Type: application/json
   X-GitHub-Api-Version: 2026-03-10
   ```

7. Set the request body to:

   ```json
   {"ref":"main"}
   ```

8. Configure the schedule for every five minutes, all day, every day. If the UI
   asks for specific minutes, select `2, 7, 12, 17, 22, 27, 32, 37, 42, 47,
   52, 57`. The time zone does not affect an all-day five-minute interval.
9. A short request timeout is sufficient because GitHub's API only accepts the
   dispatch request; it does not wait for the workflow to finish. Use 30 seconds
   if cron-job.org asks for a value.
10. Enable failure notification after the first failed execution.
11. Enable notification when the job is automatically disabled and when it
    succeeds again after a failure.
12. Save and enable the cron job.

## 3. Validate the complete path

1. Use cron-job.org's manual/test execution once.
2. Confirm that cron-job.org records an HTTP success response. GitHub may return
   `200` or `204`; either means the dispatch was accepted.
3. Open <https://github.com/nbrandtner/dltlly-ticket-monitor/actions>.
4. Confirm that a new **DLTLLY Ticket Monitor** run appears on the `main` branch
   and that its event is a manual/workflow dispatch rather than a schedule.
5. Open the run and confirm that all steps finish successfully.
6. After at least 15 minutes, verify that cron-job.org has triggered three more
   executions at roughly five-minute intervals.

Do not intentionally change `known_tickets.json` to test Discord delivery. That
can create a real notification and alter the monitor state. The existing GitHub
Actions logs are enough to verify the scheduler path.

## 4. Ongoing maintenance

- Before the token expires, create a replacement with the same repository and
  permission restrictions, update the Authorization header in cron-job.org,
  test it once, and then revoke the old token.
- If cron-job.org starts returning `401`, the token is invalid or expired.
- If it returns `403`, confirm the token's resource owner, selected repository,
  and **Actions: Read and write** permission.
- If it returns `404`, confirm the repository owner, repository name, workflow
  filename, and that the workflow exists on `main`.
- If cron-job.org reports success but no run appears, inspect the workflow's
  status in GitHub Actions and confirm that Actions are enabled for the repo.
- Review cron-job.org execution history and GitHub Actions failures whenever a
  failure notification arrives.

## Revoke access immediately if needed

1. In GitHub, open **Settings > Developer settings > Personal access tokens >
   Fine-grained tokens**.
2. Open the `cron-job.org dltlly dispatcher` token and revoke or delete it.
3. Disable the cron-job.org job until a replacement token is configured.

Revoking this token stops new external dispatches. It does not reveal or revoke
the separate Discord webhook stored in GitHub Actions secrets.
