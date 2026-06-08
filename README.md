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
- **Removes**: Cloud/live production infrastructure (production-managed PostgreSQL/Supabase, Redis, Render configs), Telegram bot runtime wrapper, private keys, database credentials, production IDs, personal names, real user data, and raw LLM trace logs.
- **Preserves**: Reusable runtime architecture, including free-form Butler routing, typed domain extraction contracts, deterministic validation logic, storage seams, and a fully local offline reviewer harness.
- **Provides**: An optional local Supabase configuration for verifying relational schemas, migrations, and RLS policies locally.

## Core Features

- **Multi-Domain LLM Runtime**: Routes and processes unstructured, free-form text input through a fully local offline reviewer sandbox using a fake LLM provider.
- **Butler-first Free-input Routing**: Incoming requests are classified by the Butler Core to determine the target domain (Kitchen, Books, Medical) and intent, eliminating the need for rigid command trees.
- **Domain Assemblies**: Independent, isolated functional modules. Shipped examples include:
  - **Kitchen**: Synthetic recipe capture and ingredient extraction.
  - **Books**: Book library metadata extraction.
  - **Medical/Health Capture**: Structural health-related metric recording (strictly limited to event logging, avoiding any clinical decision support).
- **LLM Extraction + Deterministic Validation**: Turns unstructured text inputs into structured, typed models, validating them before persistence.
- **Decoupled Persistence Seams**: Abstracted database interfaces that map in-memory mock storage directly to conceptual relational boundaries.

## Reviewer Paths

The codebase supports three verification paths for technical reviewers:
1. **Docker Reviewer Path (Primary & Recommended)**: A fully sandboxed, safe environment that runs all offline checks, tests, scenario runs, and state simulation inside a Docker container. Requires no secrets, local Python setup, or host modifications.
2. **Native Ubuntu 26.04 Path (Secondary & Debug)**: Runs checks, tests, and scenarios natively on the host machine. Requires Python 3.13 and the `uv` package manager.
3. **Optional Local Supabase (Database Schema Validation)**: Allows verifying relational schemas, migrations, RLS policies, seeds, and SQL smoke scripts locally using Docker and Supabase CLI.

## Milestone Status & Roadmap

The development of the system's infrastructure configuration and setup wizard is split into phases:
* **Phase 4: Bootstrap Safe Path (Current Milestone - COMPLETE)**: Focuses on establishing a comprehensive, local-first review environment. All dependency preflight checks, resource topology planning, local Supabase plan configurations, and Telegram webhook readiness validations run entirely in dry-run/offline sandbox mode, requiring zero secrets or cloud resources.
* **Phase 5: Live Apply (Future Horizon - DESIGN ONLY)**: Encompasses the activation of live cloud resource mutations (actual Supabase cloud database creations, Render environment variable writes, live Telegram bot webhook updates, and production deployment pipeline activation). This remains in a future horizon and is explicitly out of scope for the current public portfolio execution. For detailed architectural specifications and security boundaries of this future milestone, see the **[Live Apply Design Spec](docs/LIVE_APPLY_DESIGN.md)**.
* **First Live GO Package (Technical Smoke + Next Gate)**: The first Render `/health` technical smoke succeeded once, but clean reviewer/operator validation remains pending because future live gates require isolated operator credentials and explicit account verification. See **[First Live GO Package](docs/FIRST_LIVE_GO_PACKAGE.md)**.
* **Operator Cleanroom (Prepared, Dry-Run Only)**: Defines the clean deployment shell and account-verification gate required before repeating the Render `/health` smoke from a reviewer account. See **[Operator Cleanroom](docs/OPERATOR_CLEANROOM.md)**.

## Quickstart

### Path A: Preferred Docker Reviewer Path (Primary)
Provides a fully containerized, reproducible, and safe environment for verifying the system. It runs completely offline with zero secrets and requires no local Python installation.

> [!NOTE]
> **Docker vs. Browser Security Boundary:**
> - **Inside Docker Container**: Safe offline CLI validation, test suite execution, scenario runs, plan dry-runs, and simulate/cleanup previews. No live mutations, cloud calls, or secrets required.
> - **Outside Docker (Host/Browser Profile)**: Creating accounts or signing up for Supabase, Render, Google AI Studio (Gemini), or Telegram (BotFather) if you plan future live cloud deployment integration.

1. **Build the Reviewer Image**
   ```bash
   docker build -t agentic-domain-runtime-reviewer .
   ```

2. **Run the Offline Test Suite**
   ```bash
   docker run --rm agentic-domain-runtime-reviewer uv run pytest tests/sandbox -q
   ```

3. **Run Multi-Domain Scenarios**
   ```bash
   # Run full mock scenarios for each domain (Kitchen, Books, Health)
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario kitchen --full
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario books --full
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario health --full
   ```

4. **Verify Bootstrap Simulation & Checks**
   ```bash
   # Verify local environment readiness (doctor checks CLI presence in the container)
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap doctor

   # Dry-run apply stages (generates plan/checklist without mutations)
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap apply --preflight --read-only

   # Run end-to-end plan -> preflight -> apply -> verify -> rollback cycle
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap simulate --local

   # Preview cleanup/rollback steps
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap cleanup --preview --local --json

   # Preview operator/deployer cleanroom rules before any live Render mutation
   docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap operator --render --dry-run
   ```

5. **Interact with the Container CLI (Optional)**
   You can start an interactive bash session inside the container:
   ```bash
   docker run --rm -it agentic-domain-runtime-reviewer
   # Inside the container, you can run any command directly:
   # uv run pytest tests/sandbox -q
   # uv run python -m src.sandbox "Добавь рецепт борща"
   ```

### Path B: Native Ubuntu 26.04 Path (Secondary / Debug)
Runs completely offline with zero infrastructure dependencies. It uses a local fake LLM provider and in-memory persistence mocks to demonstrate the domain routing, extraction, validation, and storage workflows without needing external APIs or a live database.

1. **Fresh Machine Prerequisites**
   If you are running on a clean/fresh machine (e.g., a clean `ubuntu:26.04` container or VM), you need to install basic system dependencies and the `uv` package manager before setting up the repository.
   ```bash
   sudo apt-get update && sudo apt-get install -y ca-certificates git curl
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Restart your shell or source the env:
   source $HOME/.local/bin/env
   ```

2. **Synchronize dependencies & run tests**
   ```bash
   # Sync dependencies
   uv sync

   # Run offline test suite
   uv run pytest tests/sandbox -q
   ```

3. **Execute the CLI sandbox**
   Directly test the multi-domain routing and data-extraction parsing of free-text inputs:
   ```bash
   # Kitchen: recipe processing
   uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"

   # Books: library cataloging
   uv run python -m src.sandbox "Добавь книгу Хроники Зеленого Архива, Виктор Классик"

   # Health: health-log event capture
   uv run python -m src.sandbox "Запиши давление родственника 120 на 80 и пульс 70"
   ```

4. **Run complete validation scenarios**
   ```bash
   # Run full mock scenarios for each domain
   uv run python -m src.sandbox --scenario kitchen --full
   uv run python -m src.sandbox --scenario books --full
   uv run python -m src.sandbox --scenario health --full
   ```

5. **Smoke test the Runtime HTTP Server**
   Start the local HTTP sandbox runtime server (emulates webhook integration):
   ```bash
   uv run python -m src.sandbox runtime serve --host 127.0.0.1 --port 8000
   ```
   In another terminal, run these verification requests:
   ```bash
   # 1. Health check (Verify registered agents & server status)
   curl -sS -i http://127.0.0.1:8000/health

   # 2. Valid Webhook Payload (Simulate Telegram message routing)
   curl -sS -i -X POST http://127.0.0.1:8000/webhook/telegram \
     -H 'Content-Type: application/json' \
     -d '{"message":{"text":"Добавь рецепт борща"}}'

   # 3. Invalid Webhook Payload (Verify error handling and controlled 400 response)
   curl -sS -i -X POST http://127.0.0.1:8000/webhook/telegram \
     -H 'Content-Type: application/json' \
     -d '{"message":{}}'
   ```

6. **Run bootstrap verification commands**
   ```bash
   # Verify dependencies
   uv run python -m src.sandbox bootstrap doctor

   # Inspect resource plan
   uv run python -m src.sandbox bootstrap plan

   # Simulate full installation wizard flow (10 key steps)
   uv run python -m src.sandbox bootstrap install --dry-run

   # Dry-run apply stages (deterministic plan/checklist generation)
   uv run python -m src.sandbox bootstrap apply --dry-run

   # Dry-run smoke test validation
   uv run python -m src.sandbox bootstrap smoke --dry-run
   ```

### Path C: Optional Local Supabase
Allows verifying database schemas, RLS policies, and SQL smoke scripts locally.

```bash
# Start local Supabase (requires Docker and Supabase CLI installed)
supabase start

# Reset database & apply local-only migrations/seeds
supabase db reset

# Run smoke test SQL script
supabase db query --local --file supabase/smoke.sql

# Stop local Supabase
supabase stop
```

## Reviewer Navigation Map

To quickly evaluate the codebase, follow these key architectural maps and evidence documents:
- **[Reviewer Guide](docs/REVIEWER_GUIDE.md)**: Detailed step-by-step local validation instructions.
- **[Live Apply Design Spec](docs/LIVE_APPLY_DESIGN.md)**: Architecture blueprint, state transitions, security boundaries, and rollback plans for the future live deployment horizon.
- **[First Live GO Package](docs/FIRST_LIVE_GO_PACKAGE.md)**: Minimal Telegram-only live mutation package prepared for explicit human GO review.
- **[Local Supabase Package](supabase/README.md)**: Public-safe ready-to-run local Supabase package containing migrations, RLS policies, seeds, and configuration.
- **[Local Supabase Runbook](docs/RUNBOOK_LOCAL_SUPABASE.md)**: Guide on how to run a local Supabase / PostgreSQL instance to verify database boundaries and RLS policies.
- **[Resume Claims Evidence](docs/RESUME_CLAIMS.md)**: Direct mapping of resume/portfolio statements to files and tests.
- **[Private-to-Public Lineage](docs/PRIVATE_TO_PUBLIC_LINEAGE.md)**: Traceability map showing how this clean runtime relates to the production system.
- **[Supabase Schema Lineage](docs/SUPABASE_SCHEMA_LINEAGE.md)**: Explanation of database schemas, namespaces, and mock mapping.
- **[Public Surface Contract](docs/PUBLIC_SURFACE.md)**: Rules, safety limits, and boundaries established for the public repository.

## Project Boundaries & Safety

- This system is a deterministic data-capture tool. It does not provide medical, diagnostic, or therapeutic feedback.
- The reviewer sandbox operates exclusively on synthetic data and offline fixtures.
