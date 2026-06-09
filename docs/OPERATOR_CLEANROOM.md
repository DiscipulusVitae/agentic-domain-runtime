# Operator Cleanroom

This document defines the operator/deployer environment required before live cloud or API mutations.

Status: **required for live gates**.

This document defines the environment boundary. It does not authorize a live mutation by itself; each mutation still requires a task-specific GO package.

---

## Why This Exists

The runtime container and the operator environment have different jobs:

- The **runtime/app container** runs the application and serves `/health`.
- The **operator/deployer cleanroom** runs deployment CLIs and live smoke commands.

The runtime image must not contain deployment credentials. The operator environment must not reuse host CLI sessions or hidden credentials from a developer machine.

---

## Required Boundary

Before any live mutation:

1. Start an operator shell with no host `$HOME` mount.
2. Do not mount host CLI config such as:
   - `~/.config/render`
   - `~/.config/supabase`
   - host GitHub credentials
   - SSH keys
   - password-manager exports
3. Authenticate intentionally for the target account.
4. Run identity check:
   ```bash
   render whoami
   ```
   or:
   ```bash
   supabase orgs list --output json
   ```
5. Human operator confirms that the account is the intended reviewer/prod/dev account.
6. Abort on mismatch, uncertainty, billing/card prompts, or unexpected OAuth scopes.

An already-authenticated host CLI session is not consent to use that account.

---

## Dry-Run Check

The public sandbox exposes a dry-run operator plan:

```bash
uv run python -m src.sandbox bootstrap operator --render --dry-run
```

JSON form:

```bash
uv run python -m src.sandbox bootstrap operator --render --dry-run --json
```

This command performs no login and no external API call. It only prints the required boundaries and future gates.

---

## Suggested Clean Shell Shape

The exact operator image can evolve, but the safety properties must remain:

```text
operator cleanroom
  has: render CLI and/or supabase CLI, curl, git/public repo URL if needed
  does not have: host HOME, host CLI configs, tokens, SSH keys
  first live step: render login or supabase login
  first account check: render whoami or supabase orgs list
  first mutation: only after human account confirmation and explicit GO
```

Do not add Render/Supabase deployment CLIs or credentials to the runtime Dockerfile.

---

## Browser Auth UX

Render and Supabase CLI auth may print a browser URL when running inside Docker. This is expected.

Safe flow:

```text
container prints auth URL -> operator opens it manually in reviewer browser profile -> CLI receives or asks for verification code -> identity check -> human confirms account
```

Do not mount host browser profile, DBus, or host `$HOME` into the cleanroom to make browser opening automatic.

---

## Region Defaults

Use Frankfurt where supported:

- Render: Frankfurt / EU Central.
- Supabase: `eu-central-1`.

---

## Next Live Gate

The next acceptable combined infrastructure gate is:

```text
Supabase + Render wiring after DB-backed readiness exists
```

Before that, use separate proof gates for Render, Telegram, and Supabase.
