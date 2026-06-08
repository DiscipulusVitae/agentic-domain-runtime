# Operator Cleanroom

This document defines the operator/deployer environment required before live cloud or API mutations.

Status: **prepared, dry-run only**.

No login, API call, deploy, webhook update, or cloud mutation is authorized by this document.

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
  has: render CLI, curl, git/public repo URL if needed
  does not have: host HOME, host CLI configs, tokens, SSH keys
  first live step: render login
  first account check: render whoami
  first mutation: only after human account confirmation and explicit GO
```

Do not add Render CLI or credentials to the runtime Dockerfile.

---

## Next Live Gate

The next acceptable live gate is:

```text
GO Phase 1: Render minimal HTTPS runtime smoke from clean reviewer account
```

That GO must happen only after the operator cleanroom is started, the intended account is confirmed, and the local runtime preflight is green.

Telegram webhook smoke remains a later separate GO.
