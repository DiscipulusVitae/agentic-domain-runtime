# agentic-domain-runtime

`agentic-domain-runtime` is a curated, public-safe slice of a private, production-used FamilyAI system. It demonstrates the reusable core architectural patterns for multi-domain routing, LLM-assisted data extraction, deterministic validation, and decoupled persistence.

> [!NOTE]
> This repository is designed to serve as a portfolio artifact, demonstrating clean engineering practices, robust boundaries, and the core runtime patterns utilized in the larger private production environment.

## Context & Lineage

The private production-scale system utilizes:
- **Telegram Bot / Mini App** interaction interfaces for daily user communications.
- **Supabase / PostgreSQL** storage layer structured around clean domain namespaces.
- **Redis / FSM / Batching** concerns to manage conversational flow and database request queues.
- **Render-style** automated cloud deployment.

To ensure compliance with strict privacy and safety guidelines, the public slice:
- **Removes**: Live infrastructure (PostgreSQL/Supabase, Redis, Render configs), Telegram bot runtime wrapper, private keys, database credentials, production IDs, personal names, real user data, and raw LLM trace logs.
- **Preserves**: Reusable runtime architecture, including free-form Butler routing, typed domain extraction contracts, deterministic validation logic, storage seams, and a fully local offline reviewer harness.

## Core Features

- **Multi-Domain LLM Runtime**: Routes and processes unstructured, free-form text input through a fully local offline reviewer sandbox using a fake LLM provider.
- **Butler-first Free-input Routing**: Incoming requests are classified by the Butler Core to determine the target domain (Kitchen, Books, Medical) and intent, eliminating the need for rigid command trees.
- **Domain Assemblies**: Independent, isolated functional modules. Shipped examples include:
  - **Kitchen**: Synthetic recipe capture and ingredient extraction.
  - **Books**: Book library metadata extraction.
  - **Medical/Health Capture**: Structural health-related metric recording (strictly limited to event logging, avoiding any clinical decision support).
- **LLM Extraction + Deterministic Validation**: Turns unstructured text inputs into structured, typed models, validating them before persistence.
- **Decoupled Persistence Seams**: Abstracted database interfaces that map in-memory mock storage directly to conceptual relational boundaries.

## Quickstart

The default reviewer path runs completely local and offline (no external API calls, no live databases required).

```bash
# Sync dependencies
uv sync

# Run tests
uv run pytest tests/sandbox -q

# Run CLI with a single free-text input
uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"
uv run python -m src.sandbox "Добавь книгу 1984, Джордж Оруэлл"
uv run python -m src.sandbox "Запиши давление родственника 120 на 80 и пульс 70"

# Run full domain scenarios
uv run python -m src.sandbox --scenario kitchen --full
uv run python -m src.sandbox --scenario books --full
uv run python -m src.sandbox --scenario health --full
```

## Reviewer Navigation Map

To quickly evaluate the codebase, follow these key architectural maps and evidence documents:
- **[Reviewer Guide](docs/REVIEWER_GUIDE.md)**: Detailed step-by-step local validation instructions.
- **[Database Schema Package](docs/schema/README.md)**: Public-safe conceptual SQL schemas and synthetic seed data.
- **[Resume Claims Evidence](docs/RESUME_CLAIMS.md)**: Direct mapping of resume/portfolio statements to files and tests.
- **[Private-to-Public Lineage](docs/PRIVATE_TO_PUBLIC_LINEAGE.md)**: Traceability map showing how this clean runtime relates to the production system.
- **[Supabase Schema Lineage](docs/SUPABASE_SCHEMA_LINEAGE.md)**: Explanation of database schemas, namespaces, and mock mapping.
- **[Public Surface Contract](docs/PUBLIC_SURFACE.md)**: Rules, safety limits, and boundaries established for the public repository.



## Project Boundaries & Safety

- This system is a deterministic data-capture tool. It does not provide medical, diagnostic, or therapeutic feedback.
- The reviewer sandbox operates exclusively on synthetic data and offline fixtures.
