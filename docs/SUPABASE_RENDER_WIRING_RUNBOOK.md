# Supabase + Render Wiring Runbook

This document captures the current reviewer/deployer path for wiring a public-safe Supabase project to a temporary Render runtime.

Status: **proof package prepared; combined DB-backed Render readiness is not implemented yet**.

The repository has already proven these live boundaries separately:

- Render cleanroom deployment can serve `/health` over HTTPS.
- Disposable Telegram webhook delivery to the Render endpoint can be set, observed, and cleaned up.
- A fresh reviewer Supabase project in Frankfurt can receive the public-safe schema, seed data, and pass `supabase/smoke.sql`.
- Supabase organization onboarding can be handled by CLI after browser login.

The next meaningful implementation prerequisite is a runtime readiness seam that actually validates Supabase configuration. Until that exists, setting Supabase env vars on Render and checking `/health` would only prove that the service boots, not that it uses the database.

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

## Current Wiring Gap

The current public runtime `/health` response reports sandbox process health and agent registry status. It does not read Supabase env vars and does not check database connectivity.

Therefore, the next implementation slice should add a public-safe DB readiness seam before attempting a combined Supabase + Render live proof.

Minimum useful contract:

```text
GET /health
  status: ok
  mode: sandbox
  persistence: memory | supabase
  database:
    configured: true | false
    reachable: true | false
    schema_smoke: ok | skipped | failed
```

The readiness check must:

- be safe with synthetic reviewer data only;
- avoid printing secrets;
- fail closed if required Supabase env vars are missing in `supabase` mode;
- remain optional so the offline reviewer path continues to work without secrets.

---

## Cleanup

Cleanup must be part of the proof, not a follow-up.

Recommended order:

1. Delete Telegram webhook if one was set.
2. Delete temporary Render service.
3. Delete disposable Supabase project.
4. Remove cleanroom containers.
5. Verify that Render and Supabase no longer list disposable resources.
