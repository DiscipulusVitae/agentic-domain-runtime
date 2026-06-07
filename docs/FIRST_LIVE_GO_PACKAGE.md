# First Live GO Package

This document defines the first minimal live-mutation package for `agentic-domain-runtime`.

Status: **ready for human review, not approved for execution**.

No live mutation is performed by this document. A separate explicit GO is required before any cloud or API mutation.

---

## 1. Targets and Strategy

The live testing is divided into two distinct phases to ensure isolation and minimize risks:

- **Phase 1 (First Live Target): Render-only `/health` HTTPS smoke.**
- **Phase 2 (Second Live Target): Telegram webhook smoke against the Render endpoint.**

This package focuses on **Phase 1** as the initial mutation boundary, while defining Phase 2 as a subsequent step.

### Target Candidates Comparison

| Candidate | Decision | Reason |
|---|---|---|
| **Telegram-only local tunnel** | Deferred / Rejected | Artificial tunnel setup (e.g. temporary HTTPS tunnels) does not represent the production deployment architecture. Exposes unnecessary tunnel provider setup risks. |
| **Render-only `/health` smoke (Phase 1)** | **Selected Target** | Representative HTTPS deployment boundary using the target cloud environment (Render). Validates the Docker runtime deployability without DB, external API, or Telegram keys. |
| **Render + Telegram in one GO** | Rejected | Too broad for the first live mutation; complicates failure isolation and recovery. |

---

## 2. Phase 1: Render Minimal HTTPS Runtime Smoke

This phase validates that `agentic-domain-runtime` can be successfully built and deployed as a Docker container to Render, serving public HTTPS requests on the `/health` endpoint.

### 2.1. Render Assumptions & Constraints
- **Billing:** Render Free Tier must be used. No credit card should be requested or linked for this smoke. If a billing prompt or card requirement appears, abort immediately.
- **Service Type:** Web Service.
- **Deployment Source:**
  - Repository: Public Git repository URL (`https://github.com/DiscipulusVitae/agentic-domain-runtime.git`). Do not use the GitHub provider connection to avoid auto-deploy/PR preview setups and permissions request.
  - Branch: `main` (or a designated release branch).
  - Runtime: Docker (detected via `Dockerfile` in the root).
- **Docker Command:** Specify the custom start command because the default Dockerfile CMD launches an interactive shell (`/bin/bash`):
  ```bash
  /bin/sh -c 'uv run python -m src.sandbox runtime serve --host 0.0.0.0 --port ${PORT:-10000}'
  ```
- **Environment Variables:** None are required for `/health` smoke (disables DB and API dependencies).

### 2.2. Pre-mutation Local Validation
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

### 2.3. Explicit GO Boundary for Phase 1
No live deployment or Render service creation should occur without an explicit human review and authorization message:
```text
GO Phase 1: Render minimal HTTPS runtime smoke
```

### 2.4. Deployment & Verification Steps (Live Mutation)
1. **Create Render Service:**
   - Log into the Render Dashboard.
   - Create a new **Web Service**.
   - Select **Public Git repository** (do not connect your GitHub account) and enter the URL: `https://github.com/DiscipulusVitae/agentic-domain-runtime.git`.
   - Choose the **Docker** runtime.
   - Set the custom **Docker Command**:
     ```bash
     /bin/sh -c 'uv run python -m src.sandbox runtime serve --host 0.0.0.0 --port ${PORT:-10000}'
     ```
   - Select the **Free** instance type.
   - Click **Deploy Web Service**.
2. **Monitor Build & Deploy Logs:**
   - Verify that the Docker build succeeds on Render.
   - Verify that the service starts and logs no startup crashes.
3. **Verify Public HTTPS endpoint:**
   - Locate the public URL provided by Render (e.g., `https://<service-name>.onrender.com`).
   - Query the `/health` endpoint:
     ```bash
     curl -sS -i https://<service-name>.onrender.com/health
     ```
   - Expected: `HTTP 200` and JSON response.

### 2.5. Phase 1 Cleanup Plan
The Render Web Service is temporary and must be cleaned up immediately after verification:
1. In the Render Dashboard, navigate to **Settings** for the service.
2. Scroll to the bottom and click **Delete Web Service**.
3. Confirm deletion.
4. Verify cleanup:
   - Ensure the service is shown as deleted/inactive in the Render Dashboard.
   - Query the URL:
     ```bash
     curl -sS -i https://<service-name>.onrender.com/health
     ```
     Expected: The endpoint no longer returns a healthy response (e.g. connection failure, timeout, or DNS resolution failure).

---

## 3. Phase 2: Telegram Webhook Smoke against Render URL

This phase is executed **only** after Phase 1 is completed, verified, and cleaned up, and requires a separate explicit GO.

### 3.1. Telegram Assumptions & Prep
- A disposable Telegram bot created via `@BotFather`.
- Bot token kept strictly in the operator's shell memory/password manager.
- No tokens stored in `.env`, state files, git, or reports.

### 3.2. Explicit GO Boundary for Phase 2
```text
GO Phase 2: Telegram webhook smoke against Render URL
```

### 3.3. Phase 2 Execution Steps
1. Re-deploy the Render Web Service (similar to Phase 1).
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
7. Verify Render service logs to confirm it received and processed the webhook update.

### 3.4. Phase 2 Cleanup Plan
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

## 4. Abort & Rollback Conditions

### Abort Before Mutation if:
- Any billing or credit card requirement is prompted on Render.
- Render requests elevated permissions to your personal GitHub repositories (access should be restricted to this public repository only).
- Local container preflight `/health` check fails.

### Rollback on Failure:
- If deployment fails or `/health` returns non-200, delete the Render service immediately.
- If Phase 2 webhook fails to set or respond, execute `deleteWebhook` immediately, verify the empty state, and delete the Render service.

---

## 5. Allowed Evidence
To keep credentials and infrastructure details private:
- Allowed: Statement that `/health` returned `HTTP 200`.
- Allowed: Screenshot of the `/health` JSON response (hiding the Render domain name if it contains sensitive identifiers).
- Forbidden: Bot tokens, full Render service URLs, Render account IDs, or raw Telegram user IDs in screenshots or logs.
