# First Live GO Package

This document defines the first minimal live-mutation package for `agentic-domain-runtime`.

Status: **technical Render `/health` smoke completed once; clean reviewer/operator smoke still pending**.

No further live mutation is authorized by this document. A separate explicit GO is required before any cloud or API mutation.

> [!IMPORTANT]
> A previous Phase 1 run proved that the public Docker runtime can deploy on Render and serve `/health` over HTTPS. That run is **technical evidence only**, not a clean reviewer onboarding validation, because the Render CLI was executed from an already-authenticated host session. Future live gates must use a clean operator/deployer environment with explicit account verification before mutation.

---

## 1. Targets and Strategy

The live testing is divided into two distinct phases to ensure isolation and minimize risks:

- **Phase 1 (First Live Target): Render-only `/health` HTTPS smoke via CLI.**
- **Phase 2 (Second Live Target): Telegram webhook smoke against the Render endpoint.**

This package focuses on **Phase 1** as the initial mutation boundary, while defining Phase 2 as a subsequent step.

### Target Candidates Comparison

| Candidate | Decision | Reason |
|---|---|---|
| **Telegram-only local tunnel** | Deferred / Rejected | Artificial tunnel setup (e.g. temporary HTTPS tunnels) does not represent the production deployment architecture. Exposes unnecessary tunnel provider setup risks. |
| **Render-only `/health` smoke (Phase 1)** | **Selected Target** | Representative HTTPS deployment boundary using the target cloud environment (Render). Validates the Docker runtime deployability without DB, external API, or Telegram keys. |
| **Render + Telegram in one GO** | Rejected | Too broad for the first live mutation; complicates failure isolation and recovery. |

---

## 2. Operator / Runtime Boundary

There are two separate containers/environments:

1. **Runtime/app container**
   - Built from this repository's `Dockerfile`.
   - Runs the sandbox runtime server and serves `/health`.
   - Must not contain Render, Supabase, Telegram, Gemini, or GitHub credentials.

2. **Operator/deployer cleanroom**
   - Runs external CLIs/API calls such as `render`, `supabase`, `curl`, or live smoke commands.
   - Must start without host `$HOME`, host CLI config, browser credentials, or previous production/development sessions.
   - Must verify account identity before any live mutation.

Do not put deployment credentials or cloud CLIs into the runtime Docker image. If a future task needs a repeatable operator environment, use a separate operator-cleanroom image or documented shell environment.

### Account Verification Gate

Before any live mutation with Render, Supabase, Telegram, Gemini, or another external service:

1. Start from a clean operator/deployer environment.
2. Authenticate intentionally for the target reviewer/prod/dev account.
3. Run the relevant identity check, for example:
   ```bash
   render whoami
   ```
4. Human operator confirms that the shown account is the intended account for this GO.
5. Abort on mismatch or uncertainty.

An already-authenticated host CLI session is not consent to use that account.

---

## 3. Phase 1: Render Minimal HTTPS Runtime Smoke (CLI-first)

This phase validates that `agentic-domain-runtime` can be successfully built and deployed as a Docker container to Render, serving public HTTPS requests on the `/health` endpoint.

### 3.1. Render Assumptions & Constraints
- **Billing:** Render Free Tier must be used. No credit card should be requested or linked for this smoke. If a billing prompt or card requirement appears, abort immediately.
- **Service Type:** Web Service.
- **Deployment Source:** Public Git repository URL (`https://github.com/DiscipulusVitae/agentic-domain-runtime.git`). Do not use the GitHub provider connection to avoid auto-deploy/PR preview setups.
- **Docker Command:** The default Dockerfile CMD is configured to serve the runtime on `${PORT:-10000}`, so no start command override is required in the CLI command.
- **Environment Variables:** None are required for `/health` smoke (disables DB and API dependencies).

### 3.2. Pre-mutation Local Validation
Before requesting a live GO, the reviewer/operator must verify the local container builds and runs successfully:

```bash
docker build -t agentic-domain-runtime-reviewer .
docker run --rm agentic-domain-runtime-reviewer uv run pytest tests/sandbox -q
docker run --rm -p 8000:8000 agentic-domain-runtime-reviewer uv run python -m src.sandbox runtime serve --host 0.0.0.0 --port 8000
```
Verify local endpoint:
```bash
curl -sS -i http://127.0.0.1:8000/health
```
Expected: `HTTP 200` with JSON body.

### 3.3. Explicit GO Boundary for Phase 1
No live deployment or Render service creation should occur without an explicit human review and authorization message:
```text
GO Phase 1: Render minimal HTTPS runtime smoke
```

### 3.4. Deployment & Verification Steps (Live Mutation)
1. **Authenticate in a clean operator/deployer environment:**
   Run the interactive login command for the intended reviewer/prod/dev account:
   ```bash
   render login
   ```
   Verify authentication:
   ```bash
   render whoami
   ```
   Abort unless the human operator explicitly confirms the account is intended for this GO.
2. **Create Render Service via CLI:**
   Run the creation command targeting the public Git URL, setting auto-deploy to false (no start command override is needed since it is defined in the Dockerfile):
   ```bash
   render services create \
     --name adr-runtime-smoke \
     --type web_service \
     --repo https://github.com/DiscipulusVitae/agentic-domain-runtime.git \
     --runtime docker \
     --branch main \
     --plan free \
     --auto-deploy=false \
     --health-check-path /health \
     --confirm \
     --output json
   ```
   *Note: Capture the service ID (`srv-...`) from the JSON response for logging/monitoring.*
3. **Monitor Deploy Status & Logs:**
   - List services to see deployment status:
     ```bash
     render services --output json
     ```
   - Stream deployment/application logs to verify successful container start:
     ```bash
     render logs <service-id-or-name>
     ```
4. **Verify Public HTTPS endpoint:**
   - Retrieve the public URL from the service details (or locate it in the Render Dashboard).
   - Query the `/health` endpoint:
     ```bash
     curl -sS -i https://<service-name>.onrender.com/health
     ```
   - Expected: `HTTP 200` and JSON response.

### 3.5. Phase 1 Cleanup Plan
The Render Web Service is temporary and must be cleaned up immediately after verification. Since the Render CLI does not currently support service deletion, this step is performed via the dashboard:
1. Log into the Render Dashboard.
2. Navigate to the **adr-runtime-smoke** service.
3. Go to **Settings**, scroll to the bottom, and click **Delete Web Service**.
4. Confirm deletion.
5. Verify cleanup:
   - Ensure the service is shown as deleted/inactive in the Render Dashboard.
   - Query the URL:
     ```bash
     curl -sS -i https://<service-name>.onrender.com/health
     ```
     Expected: The endpoint no longer returns a healthy response (e.g. connection failure, timeout, or DNS resolution failure).

---

---

## 4. Phase 2: Telegram Webhook Smoke against Render URL

This phase is executed **only** after Phase 1 is completed, verified, and cleaned up, and requires a separate explicit GO.

Phase 2 must not proceed from a reused host CLI session. It requires the same operator/deployer account verification gate as Phase 1.

### 4.1. Telegram Assumptions & Prep
- A disposable Telegram bot created via `@BotFather`.
- Bot token kept strictly in the operator's shell memory/password manager.
- No tokens stored in `.env`, state files, git, or reports.

### 4.2. Explicit GO Boundary for Phase 2
```text
GO Phase 2: Telegram webhook smoke against Render URL
```

### 4.3. Phase 2 Execution Steps
1. Re-deploy the Render Web Service via Render CLI (similar to Phase 1).
2. Export the disposable bot token locally:
   ```bash
   read -rsp "Telegram bot token: " TELEGRAM_BOT_TOKEN
   export TELEGRAM_BOT_TOKEN
   ```
3. Query pre-mutation webhook state:
   ```bash
   curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
   ```
   Abort if any existing configured webhook belongs to a non-disposable bot.
4. Set Webhook to Render endpoint:
   ```bash
   curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
     -d "url=https://<service-name>.onrender.com/webhook/telegram"
   ```
   Expected: `ok=true`.
5. Verify webhook registration:
   ```bash
   curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
   ```
   Expected: Webhook URL points to the Render service.
6. Send one synthetic test message to the disposable bot on Telegram (e.g., "Add lemon pasta recipe").
7. View application logs via Render CLI to confirm webhook update receipt:
   ```bash
   render logs <service-id-or-name>
   ```

### 4.4. Phase 2 Cleanup Plan
1. Delete the webhook:
   ```bash
   curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
   ```
2. Verify empty webhook:
   ```bash
   curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
   ```
   Expected: Webhook URL is empty.
3. Delete the Render Web Service in the dashboard.
4. Clear the local token from the terminal session.

---

---

## 5. Abort & Rollback Conditions

### Abort Before Mutation if:
- Any billing or credit card requirement is prompted on Render or via CLI.
- CLI authentication requests elevated or unexpected OAuth scopes.
- `render whoami` or another identity check shows an unexpected account.
- The operator environment reuses host credentials when the GO package expected a clean reviewer account.
- Local container preflight `/health` check fails.

### Rollback on Failure:
- If deployment fails or `/health` returns non-200, delete the Render service via the dashboard immediately.
- If Phase 2 webhook fails to set or respond, execute `deleteWebhook` immediately, verify the empty state, and delete the Render service.

---

---

## 6. Allowed Evidence
To keep credentials and infrastructure details private:
- Allowed: Statement that `/health` returned `HTTP 200`.
- Allowed: Screenshot of the `/health` JSON response (hiding the Render domain name if it contains sensitive identifiers).
- Forbidden: Bot tokens, full Render service URLs, Render account IDs, or raw Telegram user IDs in screenshots or logs.
