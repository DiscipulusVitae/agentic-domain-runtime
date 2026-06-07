# First Live GO Package

This document defines the first minimal live-mutation package for `agentic-domain-runtime`.

Status: **ready for human review, not approved for execution**.

No live mutation is performed by this document. A separate explicit GO is required before the first external API mutation.

## 1. Target

### Selected target

**Telegram-only webhook boundary with a disposable reviewer bot.**

The live mutation is limited to the Telegram Bot API:

- read current webhook state with `getWebhookInfo`;
- set a webhook URL for a disposable bot token;
- verify webhook state;
- delete or restore the webhook during cleanup.

The target runtime endpoint is a local sandbox runtime exposed by a temporary HTTPS tunnel controlled by the reviewer/operator. The package does not create Supabase projects, Render services, databases, production deployments, or long-lived public infrastructure.

### Why this target

- Lowest blast radius: one disposable Telegram bot can be cleaned up manually.
- No private data: only synthetic reviewer messages are used.
- No billing dependency.
- No database migration or cloud hosting coupling.
- Rollback is simple and observable through `getWebhookInfo`.
- It exercises the live boundary that matters for deployment UX: human credentials, external API mutation, endpoint reachability, smoke, and cleanup.

### Targets explicitly not selected

| Candidate | Decision | Reason |
|---|---|---|
| Supabase-only project/schema apply | Deferred | Creates a long-lived cloud resource and introduces schema cleanup, access-token, project-link, and billing/organization ambiguity. |
| Render-only service/env mutation | Deferred | Creates a deployable cloud service and env surface before the smallest external API boundary is proven. |
| Full Render + Telegram + Supabase flow | Rejected for first live package | Too broad for the first live mutation; failure attribution and cleanup would be unnecessarily complex. |

## 2. Preconditions

### Human-owned credential prep

The reviewer/operator may prepare credentials before the explicit GO, but must not place secrets in git, reports, chats, or state files.

Required:

- a disposable Telegram bot created through BotFather;
- its bot token stored in a password manager;
- Docker installed and running;
- ability to expose local port `8000` through a temporary HTTPS tunnel.

Allowed token input locations after explicit GO:

- shell environment for one terminal session;
- an interactive masked prompt if implemented later.

Forbidden token locations:

- `.env`;
- `.bootstrap-state.json`;
- task/report files;
- docs;
- screenshots/logs shared for review;
- command history containing the literal token.

### Local safe checks before GO

From a clean checkout:

```bash
docker build -t agentic-domain-runtime-reviewer .
docker run --rm agentic-domain-runtime-reviewer uv run pytest tests/sandbox -q
docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap apply --preflight --read-only
docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap cleanup --preview --local --json
```

Expected:

- tests pass;
- preflight shows no cloud mutations;
- cleanup preview is local-only;
- no token is requested or printed.

## 3. Exact Commands / Human Steps

### Phase A: Start local sandbox runtime

Read-only/local mutation only: starts a local process.

```bash
docker run --rm -p 8000:8000 agentic-domain-runtime-reviewer \
  uv run python -m src.sandbox runtime serve --host 0.0.0.0 --port 8000
```

In another terminal, verify local health:

```bash
curl -sS -i http://127.0.0.1:8000/health
```

Expected: `HTTP 200`.

### Phase B: Open a temporary HTTPS tunnel

Local/network step. Use any temporary tunnel that the reviewer controls, for example an installed tunnel tool.

The target public URL must be HTTPS and temporary:

```text
https://<temporary-host>/webhook/telegram
```

Verify the tunneled health endpoint:

```bash
curl -sS -i https://<temporary-host>/health
```

Expected: `HTTP 200`.

Abort if the tunnel requires broad OAuth scopes, persistent account linking, paid plan, or exposes unrelated local services.

### Phase C: Export token for the current shell only

Secret handling step. Do not paste the token into a report or committed file.

```bash
read -rsp "Telegram bot token: " TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
printf '\n'
```

### Phase D: Pre-mutation read-only Telegram check

Read-only external API call.

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Record only sanitized evidence:

- whether `ok` is true;
- whether an existing webhook URL is empty or non-empty;
- do not record token;
- do not record full URL if it contains sensitive tunnel/account identifiers.

If an existing webhook is present and is not known to belong to this disposable reviewer bot, abort.

### Explicit GO Boundary

Stop here.

The first mutation is the next command. It must not run without an explicit human message:

```text
GO first live Telegram webhook apply
```

### Phase E: Set webhook

Live mutation.

```bash
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://<temporary-host>/webhook/telegram"
```

Expected:

- Telegram response `ok=true`;
- no token printed except in the command line typed by the operator;
- runtime terminal receives webhook updates only after the reviewer sends messages to the disposable bot.

### Phase F: Verify webhook state

Read-only external API call.

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:

- `ok=true`;
- webhook URL points to the temporary tunnel.

### Phase G: Human smoke

Manual Telegram action.

Send one synthetic message to the disposable bot:

```text
Добавь рецепт лимонной пасты с базиликом
```

Expected:

- local runtime receives the update;
- response is deterministic and synthetic;
- no real personal data is sent.

## 4. Expected Mutations

External mutations:

- Telegram webhook URL for the disposable bot is set to the temporary tunnel endpoint.

Local/runtime mutations:

- local runtime process handles synthetic request logs in terminal output;
- no git-tracked file changes are expected;
- no `.env` or state file changes are expected.

No Supabase, Render, Gemini, cloud database, or repository settings are modified.

## 5. Rollback / Cleanup Plan

### Normal cleanup

Live mutation rollback.

```bash
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

Verify cleanup:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:

- `ok=true`;
- webhook URL is empty.

Then stop:

- local runtime process;
- temporary HTTPS tunnel;
- shell session containing `TELEGRAM_BOT_TOKEN`.

### Partial failure handling

| Failure | Action |
|---|---|
| Tunnel dies after webhook is set | Run `deleteWebhook`, verify empty webhook, then stop. |
| Runtime returns non-200 | Run `deleteWebhook`; preserve sanitized runtime output for diagnosis. |
| `setWebhook` returns `ok=false` | Do not retry blindly; inspect sanitized error description and abort. |
| `deleteWebhook` fails | Retry once after 30 seconds. If still failing, use BotFather or Telegram API manually from a clean shell and record sanitized failure. |
| Existing webhook found before apply | Abort unless it is explicitly known to be disposable and safe to overwrite. |

## 6. Smoke Criteria

PASS if all are true:

- local runtime `/health` returns `HTTP 200`;
- temporary HTTPS `/health` returns `HTTP 200`;
- `getWebhookInfo` before apply is understood and safe;
- `setWebhook` returns `ok=true`;
- `getWebhookInfo` after apply points to the temporary endpoint;
- one synthetic Telegram message reaches the local runtime;
- `deleteWebhook` returns `ok=true`;
- final `getWebhookInfo` shows no active webhook;
- no secrets are written to git, docs, task artifacts, or shared screenshots.

FAIL if any are true:

- token value appears in committed files, logs intended for sharing, reports, or chat;
- Telegram webhook remains configured after cleanup;
- tunnel or account flow requests unexpected permissions;
- any Supabase/Render/Gemini mutation occurs;
- non-synthetic personal data is sent through the disposable bot.

## 7. Abort Conditions

Abort before mutation if:

- a billing/card requirement appears;
- OAuth permission scope is broader than expected;
- a tool requests storing token in a file;
- the operator cannot verify rollback;
- a non-disposable bot token is used;
- the temporary URL is not HTTPS;
- local runtime health check fails;
- public/private boundary is unclear.

Abort after mutation and immediately run cleanup if:

- runtime endpoint is unhealthy;
- Telegram response shows unexpected webhook target;
- synthetic smoke cannot be completed quickly;
- any unexpected external resource appears.

## 8. Evidence After Run

Allowed evidence:

- final PASS/FAIL summary;
- sanitized `ok=true/false` Telegram API status;
- sanitized webhook host category, for example `temporary HTTPS tunnel`;
- local runtime status codes;
- statement that final webhook is empty after cleanup.

Do not commit or share:

- bot token;
- full temporary tunnel URL if it embeds account or random identifiers;
- raw Telegram update payload containing user identifiers;
- screenshots with token, bot username, account profile, or tunnel dashboard.

## 9. Current Implementation Caveat

The public runtime currently supports local HTTP webhook simulation. It does not yet provide a first-class CLI subcommand that performs `getWebhookInfo`, `setWebhook`, or `deleteWebhook`.

Therefore this GO package is a human/operator decision package, not an automated live deployer. Automating these API calls should be a later task after this manual live boundary is validated.
