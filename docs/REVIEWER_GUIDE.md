# Reviewer Quickstart Guide: agentic-domain-runtime

This document describes the unified verification paths for technical reviewers of `agentic-domain-runtime`. The guide is structured around a **Single Sequential Safe Path** requiring zero external mutations, secrets, or live network calls.

---

## 1. Mode Matrix

The codebase operates in distinct modes to allow safe review at different levels of infrastructure availability:

| Mode | Network Required | Secrets Required | State Mutations | Purpose | Key Commands |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Offline** | **No** | **No** | **None** (In-memory mock only) | Offline logic verification, tests, and CLI mock runs | `pytest`, `--scenario <domain> --full`, `runtime serve` |
| **Read-Only** | **No** | **No** | **None** | Environment diagnostics, state check, and local setup readiness verification | `bootstrap checks --read-only`, `bootstrap doctor`, `bootstrap state --show` |
| **Dry-Run** | **No** | **No** | **None** (Generates plan/checklist only) | Simulating cloud deployments, DB configurations, and API webhook setups | `bootstrap install --dry-run`, `bootstrap supabase --local --dry-run`, `bootstrap telegram --webhook --dry-run`, `bootstrap apply --dry-run`, `bootstrap smoke --dry-run`, `bootstrap state --init --dry-run`, `bootstrap simulate --local`, `bootstrap cleanup --preview --local` |
| **Future Live** | **Yes** (Cloud/API) | **Yes** (Render, Supabase, Telegram keys) | Cloud resources, Database schemas, Bot webhooks | Production deployments and live cloud management (Design Only) | Planned `bootstrap apply` (without `--dry-run`), live production deploy (see [LIVE_APPLY_DESIGN.md](LIVE_APPLY_DESIGN.md)) |

---

## 2. Safety Guarantees

Every step in the default reviewer path comes with the following safety guarantees:
* **No Secrets Required**: Reviewers do not need to supply any live database passwords, API keys (e.g., Gemini, Telegram, Render), or tokens. Placeholder configs are fully sufficient.
* **No Live API Calls**: No outbound requests to external services (such as Telegram Bot API, Render API, or live LLM endpoints) are executed.
* **No Cloud/DB/Telegram Mutations**: No state is written or changed in any cloud databases, telegram webhook settings, or hosting servers.
* **No Private Data**: The sandbox operates entirely on artificial (synthetic) data.

---

## 3. Future Live Boundaries (Design Only)

The following capabilities are **explicitly out of scope** for active code execution in this public milestone, but their target architecture, rollback strategy, and gates are defined in the **[Live Apply Design Spec](LIVE_APPLY_DESIGN.md)**:
* **Live Supabase Apply**: Execution of `supabase db push` or direct cloud schema mutations.
* **Render Resource/Env Mutation**: Provisioning web services, setting env groups, or altering deploy parameters in Render.
* **Telegram Bot API Webhook Mutation**: Outbound `setWebhook` API operations or modifying live bot handlers.
* **Production Deploy**: Merging, building, and deploying the application stack into a live production environment.

---

## 4. The Unified Reviewer Safe Path (Step-by-Step)

Reviewers can verify the entire system safely using either the **Preferred Docker-first Path (Path A)** or the **Native Ubuntu Path (Path B)**.

> [!NOTE]
> **Docker vs. Browser Security Boundary:**
> * **Docker Container (Safe Validation Zone)**: All CLI checks, pytest suites, domain scenario runs, bootstrap plans, preflight dry-runs, synthetic state initialization, and deployment rollback simulations run completely offline and locally. No secrets, tokens, or live cloud mutations are ever required or executed.
> * **Host Browser (Manual Setup Zone)**: Outside the container, human-driven signup, token handoffs, and OAuth authorizations (Supabase, Render, Google AI Studio, Telegram BotFather) remain separate and are only needed for future live production deployments.

---

### Step 1: Environment Setup

Choose your preferred environment:

#### Path A: Docker Reviewer Path (Primary & Recommended)
Requires only Docker installed on the host. Eliminates the need for local Python, `uv`, or host OS packages.
```bash
# Build the self-contained reviewer image
docker build -t agentic-domain-runtime-reviewer .
```

#### Path B: Native Ubuntu 26.04 Path (Secondary & Fallback)
Requires Python >= 3.13 and the `uv` package manager installed on the host.
```bash
# 1. Install system utilities
sudo apt-get update && sudo apt-get install -y ca-certificates git curl

# 2. Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 3. Synchronize Python dependencies
uv sync

# 4. Copy the environment profile template
cp .env.example .env
```

---

### Step 2: Offline Sandbox Setup & Unit Tests

Verify the offline logic by running the complete unit test suite.

*   **Docker Path A**:
    ```bash
    docker run --rm agentic-domain-runtime-reviewer uv run pytest tests/sandbox -q
    ```
*   **Native Path B**:
    ```bash
    uv run pytest tests/sandbox -q
    ```
*   *Expected Result*: The entire test suite passes successfully.

---

### Step 3: Multi-Domain CLI Scenario Runs

Exercise the runtime domain routing, LLM-assisted data extraction, validation, and storage mocks.

*   **Docker Path A**:
    ```bash
    # Run full mock scenarios for each domain (Kitchen, Books, Health)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario kitchen --full
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario books --full
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox --scenario health --full

    # Test single domain routing inputs directly
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"
    ```
*   **Native Path B**:
    ```bash
    # Run full mock scenarios for each domain
    uv run python -m src.sandbox --scenario kitchen --full
    uv run python -m src.sandbox --scenario books --full
    uv run python -m src.sandbox --scenario health --full

    # Test single domain routing inputs directly
    uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"
    ```
*   *Expected Result*: The CLI parses, validates, and simulates saving to the in-memory database, returning a complete routing trace and simulated agent response.

---

### Step 4: Local Runtime HTTP Server Smoke Verification

Start the local HTTP sandbox runtime server (emulating webhook listener interfaces) and execute verification requests.

*   **Docker Path A**:
    ```bash
    # 1. Start the server (expose port 8000)
    docker run --rm -p 8000:8000 agentic-domain-runtime-reviewer uv run python -m src.sandbox runtime serve --host 0.0.0.0 --port 8000
    ```
    *In another terminal (Terminal 2), run the verification requests below.*
*   **Native Path B**:
    ```bash
    # 1. Start the server
    uv run python -m src.sandbox runtime serve --host 127.0.0.1 --port 8000
    ```
    *In another terminal (Terminal 2), run the verification requests below.*

**Verification Requests (Terminal 2)**:
```bash
# 2. Health check (Verify registered agents & server status)
curl -sS -i http://127.0.0.1:8000/health

# 3. Debug Storage Check (Verify initial counts)
curl -sS -i http://127.0.0.1:8000/debug/storage

# 4. Valid Webhook Payload (Simulate Telegram message routing)
curl -sS -i -X POST http://127.0.0.1:8000/webhook/telegram \
  -H 'Content-Type: application/json' \
  -d '{"message":{"text":"Добавь рецепт борща"}}'

# 5. Invalid Webhook Payload (Verify error handling and controlled 400 response)
curl -sS -i -X POST http://127.0.0.1:8000/webhook/telegram \
  -H 'Content-Type: application/json' \
  -d '{"message":{}}'
```
*Expected Result*: `/health` and valid webhook return `HTTP 200 OK`, while invalid webhook returns `HTTP 400 Bad Request`.
*(Once completed, stop the server in Terminal 1 using `Ctrl+C`)*

---

### Step 5: Bootstrap Preflight Checks & Local State Management

Verify environment tools and read-only preflight checks.

*   **Docker Path A**:
    ```bash
    # Verify local tool dependency readiness (within container)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap doctor

    # Run read-only preflight checks (verifies presence of variables safely)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap checks --read-only

    # Dry-run initializing the local non-secret state file
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap state --init --dry-run
    ```
*   **Native Path B**:
    ```bash
    # Verify local tool dependency readiness
    uv run python -m src.sandbox bootstrap doctor

    # Run read-only preflight checks
    uv run python -m src.sandbox bootstrap checks --read-only

    # Dry-run initializing the local non-secret state file
    uv run python -m src.sandbox bootstrap state --init --dry-run
    ```
*   *Expected Result*: Tool readiness statuses are displayed, and dry-runs succeed without modifying the host workspace.

---

### Step 6: Local Supabase Dry-Run Plan

Inspect target resource topologies and verify local asset layouts.

*   **Docker Path A**:
    ```bash
    # Inspect the target resource topology plan
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap plan

    # Verify local Supabase asset layout (validates migrations, config, and seed files)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap supabase --local --dry-run

    # Simulate the interactive install wizard flow (dry-run checklist)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap install --dry-run
    ```
*   **Native Path B**:
    ```bash
    # Inspect the target resource topology plan
    uv run python -m src.sandbox bootstrap plan

    # Verify local Supabase asset layout
    uv run python -m src.sandbox bootstrap supabase --local --dry-run

    # Simulate the interactive install wizard flow
    uv run python -m src.sandbox bootstrap install --dry-run
    ```
*   *Expected Result*: The command outputs target deployment checklists and validation summaries without creating cloud databases.

---

### Step 7: Telegram Webhook Readiness Simulation

Dry-run target configuration steps and readiness check gates.

*   **Docker Path A**:
    ```bash
    # Dry-run Telegram webhook mapping
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap telegram --webhook --dry-run

    # Dry-run apply stages (produces final deployment checklist)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap apply --dry-run

    # Safe preflight check (verifies env readiness, read-only)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap apply --preflight --read-only
    ```
*   **Native Path B**:
    ```bash
    # Dry-run Telegram webhook mapping
    uv run python -m src.sandbox bootstrap telegram --webhook --dry-run

    # Dry-run apply stages
    uv run python -m src.sandbox bootstrap apply --dry-run

    # Safe preflight check
    uv run python -m src.sandbox bootstrap apply --preflight --read-only
    ```
*   *Expected Result*: Plans are successfully built, and the preflight gate reports status.

---

### Step 8: Local-only Apply/Rollback Simulation

Verify the end-to-end simulation of the `plan → preflight → apply → verify → rollback` cycle on synthetic resources.

*   **Docker Path A**:
    ```bash
    # Run successful (happy path) simulation of the deployment and cleanup cycle
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap simulate --local

    # Run JSON-formatted output of the successful simulation
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap simulate --local --json

    # Run failure simulation where verify fails, triggering automatic rollback of applied steps
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap simulate --local --fail-after-apply --json
    ```
*   **Native Path B**:
    ```bash
    # Run successful simulation
    uv run python -m src.sandbox bootstrap simulate --local

    # Run failure simulation
    uv run python -m src.sandbox bootstrap simulate --local --fail-after-apply --json
    ```
*   *Expected Result*: The simulator executes all phases sequentially. In the failure path, it automatically rolls back all applied synthetic resources.

---

### Step 9: Rollback & Cleanup Preview (Dry-Run)

Verify the local preview of the rollback/cleanup plan before future live apply operations.

*   **Docker Path A**:
    ```bash
    # Preview rollback/cleanup without a state file (builds preview from deterministic plan)
    docker run --rm agentic-domain-runtime-reviewer uv run python -m src.sandbox bootstrap cleanup --preview --local
    ```
*   **Native Path B**:
    ```bash
    # Preview rollback/cleanup
    uv run python -m src.sandbox bootstrap cleanup --preview --local
    ```
*   *Expected Result*: Structured cleanup plan preview is displayed in reverse dependency order, showing that no resources are left in the cloud.

---

## Path B: Optional Local Supabase Setup & Verification

For reviewers analyzing our PostgreSQL/Supabase boundaries:
* Refer to **[Local Supabase Package](../supabase/README.md)** for local migrations, RLS policies, configuration, seeds, and the `smoke.sql` validation script.
* Refer to the **[Local Supabase Runbook](RUNBOOK_LOCAL_SUPABASE.md)** for the optional local-first verification path guide.

---

## Publication Gates

Before any public push, the checkout must pass:
* `uv sync`
* `uv run pytest tests/sandbox -q`
* Sandbox CLI smoke commands above (`--scenario <domain> --full` suites)
* HTTP server smoke tests (/health, valid webhook, invalid webhook)
* Private-data and secret scans (using tools like `gitleaks`)
