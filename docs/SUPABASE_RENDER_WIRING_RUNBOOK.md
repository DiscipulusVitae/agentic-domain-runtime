# Supabase + Render Wiring Runbook

This document captures the current reviewer/deployer path for wiring a public-safe Supabase project to a temporary Render runtime.

Status: **proven on disposable reviewer/test resources with full cleanup (T299)**.

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
supabase config push                 # expose schemas in PostgREST (see below)
supabase db query --linked --file supabase/seed.sql
supabase db query --linked --file supabase/smoke.sql
```

Remote `supabase db push` applies migrations but does not apply `seed.sql`. Apply `seed.sql` explicitly before `smoke.sql`, because `smoke.sql` validates synthetic seed counts.

### PostgREST Schema Exposure

By default, remote Supabase PostgREST exposes only `public` and `graphql_public` schemas. If the runtime health check queries non-public schemas (e.g. `core`, `kitchen`), the REST API returns HTTP 406:

```json
{"code":"PGRST106","message":"Invalid schema: core",
 "hint":"Only the following schemas are exposed: public, graphql_public"}
```

Expose the required schemas via `supabase config push`, which pushes the full local `supabase/config.toml` to the remote project. The relevant section:

```toml
[api]
schemas = ["public", "core", "kitchen", "books", "med", "api", "graphql_public"]
extra_search_path = ["public", "core", "extensions"]
```

> **Caveat:** `supabase config push` applies the entire config, including auth settings. It is acceptable for reviewer-path proof but not an automatic production migration pattern without review.

Expected smoke result:

- schemas exist: `core`, `kitchen`, `books`, `med`, `api`;
- key tables exist;
- seed counts match;
- RLS flags and policies pass;
- auth mapping passes.

---

## Render Wiring Boundary

Render service creation and Supabase env injection must also happen from a clean operator/deployer environment.

When using Docker as a cleanroom:
- Install `xdg-utils` in the container for `render login` browser device-code flow:
  ```bash
  apt-get install -y xdg-utils
  ```
- Free-tier Render with Docker runtime does not require a credit card (`--plan free`).

The temporary Render service may receive only reviewer/test Supabase values for this proof. Never wire private production Supabase values into the public ADR runtime.

### Render URL Read-Back

Render may return an empty service URL immediately after service creation or during early list/read-back calls. The installer therefore treats the URL as a verified fact only when Render CLI/API read-back returns a non-empty `url` field.

Required state semantics:

- `render_service_status=service_created|service_existing`: service identity is known and cleanup can target it.
- `render_url_status=url_verified`: a real Render URL was read back and may be used for `/health` and Telegram webhook wiring.
- `render_url_status=url_pending|url_missing_or_unverified`: service identity is preserved, but webhook setup remains blocked by default.
- `render_url_override_accepted=true`: exceptional Live Mutation Gate override, set only after explicit human acceptance of an unverified URL.

The installer must not infer `https://<service>.onrender.com` from the service name. If URL verification stays pending, safe next steps are to wait for Render Dashboard/API to expose the URL, rerun the installer, or perform a Live Mutation Gate override with explicit human acceptance.

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

> The readiness seam is implemented and proven. A live combined proof (Supabase + Render + DB-backed `/health`) was completed on disposable resources with full cleanup. See the Reviewer Guide for the cloud bootstrap path summary.

---

## Cleanup

Cleanup must be part of the proof, not a follow-up.

Recommended order:

1. Delete Telegram webhook if one was set.
2. Delete temporary Render service (via REST API: `DELETE /v1/services/{id}` — HTTP 204 on success; Render CLI does not expose a native delete command).
3. Delete disposable Supabase project (`supabase projects delete <ref> --yes`).
4. Remove cleanroom containers.
5. Verify that Render and Supabase no longer list disposable resources.
