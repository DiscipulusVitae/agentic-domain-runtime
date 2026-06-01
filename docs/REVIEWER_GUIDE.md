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
The reviewer path exposes a local sandbox CLI that exercises the runtime with synthetic payloads:
```bash
uv run python -m src.sandbox "Добавь книгу 1984, Джордж Оруэлл"
```

The sandbox uses a fake/offline LLM provider by default and in-memory storage for persistence checks. Telegram, live LLM keys, production Supabase, Docker, and local Postgres are not required for the default reviewer path.

## Verification

Run the sandbox tests:
```bash
uv run pytest tests/sandbox -q
```

Run the main smoke scenarios:
```bash
uv run python -m src.sandbox "Добавь книгу 1984, Джордж Оруэлл"
uv run python -m src.sandbox "Запиши давление родственника 120 на 80 и пульс 70"
uv run python -m src.sandbox --scenario books
uv run python -m src.sandbox --scenario health --full
```

The synthetic fixtures validate:
- Butler intent routing.
- LLM orchestration/extraction payloads.
- The health-log capture flow, including deterministic validation and persistence boundaries.
- In-memory persistence and inspection using synthetic data.

All test suites must run purely against these synthetic datasets, ensuring no production data or credentials are required.

## Publication Gates

Before public push, the checkout must pass:
- `uv sync`
- `uv run pytest tests/sandbox -q`
- sandbox CLI smoke commands above
- private-data and secret scans
