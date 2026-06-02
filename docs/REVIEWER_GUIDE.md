# Reviewer Quickstart Guide: agentic-domain-runtime

This document describes the local verification path for technical reviewers of `agentic-domain-runtime`.

## Local Setup

The default path uses a local reviewer sandbox. Telegram bot runtime, Render deployment, production Supabase, Docker, local PostgreSQL, and live LLM keys are not part of this path.

### 1. Dependency Synchronization
The project uses `uv` for Python dependency management:
```bash
uv sync
```

### 2. Environment Profile Template
A sandbox-first `.env.example` is included. It does not require Telegram credentials, production Supabase credentials, Render config, or a live LLM key:
```bash
cp .env.example .env
```

### 3. Local Sandbox
The reviewer path exposes a local sandbox CLI that exercises the runtime with synthetic payloads. You can trigger single domain-routing classification runs:
```bash
# Kitchen: recipe processing
uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"

# Books: library cataloging
uv run python -m src.sandbox "Добавь книгу 1984, Джордж Оруэлл"

# Health: health-log event capture
uv run python -m src.sandbox "Запиши давление родственника 120 на 80 и пульс 70"
```

The sandbox uses a fake/offline LLM provider by default and in-memory storage for persistence checks. Telegram, live LLM keys, production Supabase, Docker, and local Postgres are not required for the default reviewer path.

## Verification

Run the sandbox tests:
```bash
uv run pytest tests/sandbox -q
```

### Smoke Scenario Suites
To execute complete multi-step validation flows using synthetic mock datasets, run the following:

- **Kitchen domain validation suite**:
  ```bash
  uv run python -m src.sandbox --scenario kitchen --full
  ```

- **Books domain validation suite**:
  ```bash
  uv run python -m src.sandbox --scenario books --full
  ```

- **Health-Log (medical) domain validation suite**:
  ```bash
  uv run python -m src.sandbox --scenario health --full
  ```

The synthetic fixtures validate:
- Butler intent routing and classification.
- LLM orchestration/extraction payloads and schema parsing.
- Domain assembly capture flow, including deterministic validation rules and persistence boundaries.
- In-memory persistence mock inspection using synthetic data.

All test suites must run purely against these synthetic datasets, ensuring no production data or credentials are required.

## Database Schema & Local Supabase
For reviewers analyzing our PostgreSQL/Supabase boundaries, we provide a public-safe ready-to-run Supabase package, a local SQL smoke script, and a runbook:
- Refer to **[Local Supabase Package](../../supabase/README.md)** for local migrations, RLS policies, configuration, seeds, and the `smoke.sql` validation script.
- Refer to the **[Local Supabase Runbook](RUNBOOK_LOCAL_SUPABASE.md)** for the optional local-first verification path guide.

## Publication Gates

Before public push, the checkout must pass:
- `uv sync`
- `uv run pytest tests/sandbox -q`
- sandbox CLI smoke commands above (all three `--scenario <domain> --full` suites)
- private-data and secret scans (using tools like `gitleaks`)
