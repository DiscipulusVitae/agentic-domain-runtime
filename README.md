# agentic-domain-runtime

`agentic-domain-runtime` is a multi-domain LLM-assisted runtime designed to route, process, validate, and store structured data across isolated domain assemblies.

## Quickstart

The default reviewer path is fully local and offline: fake LLM, synthetic payloads, and in-memory persistence. It does not require Telegram, Docker, PostgreSQL/Supabase, Render, or live LLM keys.

```bash
uv sync
uv run pytest tests/sandbox -q
uv run python -m src.sandbox "Добавь книгу 1984, Джордж Оруэлл"
uv run python -m src.sandbox "Запиши давление родственника 120 на 80 и пульс 70"
uv run python -m src.sandbox --scenario books
uv run python -m src.sandbox --scenario health --full
```

## Core Features

- **Multi-Domain LLM Runtime**: A runtime for handling free-form inputs through a local reviewer sandbox, using a fake/offline LLM provider to demonstrate extraction and orchestration boundaries.
- **Reusable Core**: The system separates platform-level concerns (bootstrap, session state, LLM clients, error boundaries, and observability) from domain-specific features.
- **Domain Assemblies**: Independent business logic modules (domains) that register with the core runtime. Standard domain assemblies include:
  - **Kitchen**: Synthetic recipe capture stub showing a domain boundary.
  - **Books**: Library capture and reading-progress style payloads.
  - **Health-log capture**: Structural capture of synthetic health-related metrics and events.
- **Butler-first Free-input Routing**: Incoming free-form messages are first processed by the Butler Core. The Butler determines the user's intent and routes the payload to the appropriate domain assembly without hardcoded command trees.
- **LLM orchestration/extraction + deterministic validation and persistence**: LLM-style extraction turns unstructured inputs into typed data models, while deterministic validation and in-memory persistence verify the resulting structures.

## Project Boundaries & Safety

To ensure compliance with strict privacy and safety guidelines:
- The system is a deterministic data-capture tool for capturing events and domain entities.
- It is strictly limited to structured event capturing and data storage without providing automated feedback, reasoning, or therapeutic routing.
- The reviewer sandbox uses exclusively synthetic fixtures and mock data.
