# Supabase + Render Wiring Runbook

This document captures the current reviewer/deployer path for wiring a public-safe Supabase project to a temporary Render runtime.

Status: **proof package prepared; combined DB-backed Render readiness seam is implemented**.

The repository has already proven these live boundaries separately:

- Render cleanroom deployment can serve `/health` over HTTPS.
- Disposable Telegram webhook delivery to the Render endpoint can be set, observed, and cleaned up.
- A fresh reviewer Supabase project in Frankfurt can receive the public-safe schema, seed data, and pass `supabase/smoke.sql`.
- Supabase organization onboarding can be handled by CLI after browser login.

The runtime readiness seam is implemented to validate Supabase configuration and connectivity. Setting Supabase env vars on Render and checking `/health` will verify database wiring.

---

## Regions

Use Frankfurt for reviewer infrastructure where supported:

- Supabase: `eu-central-1`.
- Render: Frankfurt / EU Central.

---

## Supabase Reviewer Flow

Run Supabase CLI from a disposable operator cleanroom. Do not mount host `$HOME`, host Supabase config, browser profile, SSH keys, password-manager exports, or production credentials.

### Browser Auth

```bash
supabase login
```

Expected UX:

1. CLI prints a browser login link if it cannot open a browser inside the container.
2. The operator opens the link manually in the reviewer browser profile.
3. If Supabase shows a verification code, the operator enters it in the cleanroom terminal.
4. CLI confirms login.

### Organization Boundary

```bash
supabase orgs list --output json
```

If the list is non-empty, use the reviewer organization only after explicit human confirmation.

If the list is empty (`[]`), create a neutral reviewer organization through CLI:

```bash
supabase orgs create "ADR Reviewer"
```

Do not ask the reviewer to create an organization in the UI unless CLI organization creation fails.

Abort if Supabase requests billing/card setup, project creation, GitHub integration, or broad OAuth scopes during this step.

### Project Creation

```bash
supabase projects create adr-supabase-smoke \
  --org-id <reviewer_org_id> \
  --region eu-central-1
```

For free-tier reviewer smoke, do not pass `--size nano`. Supabase Dashboard may display the created project as `nano`, but the CLI can reject `nano` as an invalid `--size` value.

If the CLI asks for a database password, prefer leaving it blank to let Supabase generate one. Do not write database passwords into shell scripts, reports, git, screenshots, or copied commands.

---

## Remote Schema Apply

Inside the operator cleanroom, copy or clone the public repository, then:

```bash
supabase link --project-ref <reviewer_project_ref>
supabase db push
supabase db query --linked --file supabase/seed.sql
supabase db query --linked --file supabase/smoke.sql
```

Remote `supabase db push` applies migrations but does not apply `seed.sql`. Apply `seed.sql` explicitly before `smoke.sql`, because `smoke.sql` validates synthetic seed counts.

Expected smoke result:

- schemas exist: `core`, `kitchen`, `books`, `med`, `api`;
- key tables exist;
- seed counts match;
- RLS flags and policies pass;
- auth mapping passes.

---

## Render Wiring Boundary

Render service creation and Supabase env injection must also happen from a clean operator/deployer environment.

The temporary Render service may receive only reviewer/test Supabase values for this proof. Never wire private production Supabase values into the public ADR runtime.

Forbidden in repo artifacts:

- Supabase access tokens;
- database passwords;
- anon/service role keys;
- raw connection strings;
- full project refs or dashboard URLs;
- Render API keys;
- full service IDs or URLs if not needed.

Allowed evidence:

- region;
- sanitized project/service labels;
- HTTP status codes;
- smoke result summaries;
- cleanup result.

---

## DB-Backed Readiness Seam

The public runtime `/health` response supports validating Supabase configuration and database connectivity.

Expected Contract:

```json
{
  "status": "ok",
  "mode": "sandbox",
  "persistence": "memory|supabase",
  "database": {
    "configured": true,
    "reachable": true,
    "schema_smoke": "ok|skipped|failed"
  }
}
```

### Configuration & Environment Variables

The readiness seam reads the following environment variables:
- `ADR_PERSISTENCE`: Decides the persistence layer. Default is `memory`. Set to `supabase` to enable DB-backed readiness.
- `SUPABASE_URL`: The URL of the Supabase API Gateway.
- `SUPABASE_API_KEY_PUBLISHABLE`: The public/publishable Supabase API key used for anonymous read-only readiness checks.

### Behavior & Fail-Closed Strategy

- **`memory` mode**: Checks are bypassed. Returns:
  - `http_status`: 200 OK
  - `persistence`: `"memory"`
  - `database.configured`: `false`
  - `database.reachable`: `false`
  - `database.schema_smoke`: `"skipped"`
- **`supabase` mode (Missing Environment Variables)**: If `ADR_PERSISTENCE=supabase` but either `SUPABASE_URL` or `SUPABASE_API_KEY_PUBLISHABLE` is missing or empty, the check fails closed:
  - `http_status`: 503 Service Unavailable
  - `status`: `"error"`
  - `database.configured`: `false`
  - `database.reachable`: `false`
  - `database.schema_smoke`: `"failed"`
- **`supabase` mode (Unreachable Database)**: If environment variables are present but the database connection fails:
  - `http_status`: 503 Service Unavailable
  - `status`: `"error"`
  - `database.configured`: `true`
  - `database.reachable`: `false`
  - `database.schema_smoke`: `"failed"`
- **`supabase` mode (Successful Check)**: Performs a safe read-only GET request to the `/rest/v1/persons` endpoint with a 3.0-second timeout. If it returns 200 OK:
  - `http_status`: 200 OK
  - `status`: `"ok"`
  - `database.configured`: `true`
  - `database.reachable`: `true`
  - `database.schema_smoke`: `"ok"`

> [!IMPORTANT]
> **Live Combined Proof Gate**
> Although the readiness seam is fully implemented, executing a live combined proof (deploying to live Render and wiring it to a live Supabase project) is still strictly gated and requires a separate human GO authorization. Do not run any live mutations on live cloud infrastructure without explicit approval.

---

## Cleanup

Cleanup must be part of the proof, not a follow-up.

Recommended order:

1. Delete Telegram webhook if one was set.
2. Delete temporary Render service.
3. Delete disposable Supabase project.
4. Remove cleanroom containers.
5. Verify that Render and Supabase no longer list disposable resources.
