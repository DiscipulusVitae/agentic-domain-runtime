# Reviewer Quickstart Guide: agentic-domain-runtime

This document describes the unified verification paths for technical reviewers of `agentic-domain-runtime`. The guide is structured around a **Single Sequential Safe Path** requiring zero external mutations, secrets, or live network calls.

---

## 1. Mode Matrix

The codebase operates in distinct modes to allow safe review at different levels of infrastructure availability:

| Mode | Network Required | Secrets Required | State Mutations | Purpose | Key Commands |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Offline** | **No** | **No** | **None** (In-memory mock only) | Offline logic verification, tests, and CLI mock runs | `pytest`, `--scenario <domain> --full`, `runtime serve` |
| **Read-Only** | **No** | **No** | **None** | Environment diagnostics, state check, and local setup readiness verification | `bootstrap checks --read-only`, `bootstrap doctor`, `bootstrap state --show` |
| **Dry-Run** | **No** | **No** | **None** (Generates plan/checklist only) | Simulating cloud deployments, DB configurations, and API webhook setups | `bootstrap install --dry-run`, `bootstrap supabase --local --dry-run`, `bootstrap telegram --webhook --dry-run`, `bootstrap apply --dry-run`, `bootstrap smoke --dry-run`, `bootstrap state --init --dry-run` |
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

Follow these steps in sequence to verify the entire system safely.

### Step 1: Offline Sandbox Setup & Unit Tests
Initialize the environment using `uv` and run the offline unit test suite:
```bash
# 1. Synchronize Python dependencies
uv sync

# 2. Copy the sandbox-first environment profile template
cp .env.example .env

# 3. Run the offline test suite
uv run pytest tests/sandbox -q
```
*Expected Result:* The sandbox test suite passes successfully.

### Step 2: Multi-Domain CLI Scenario Runs
Exercise the runtime domain routing, LLM-assisted data extraction, validation, and storage mocks using the sandbox CLI:
```bash
# Run full mock scenarios for each domain (Kitchen, Books, Health)
uv run python -m src.sandbox --scenario kitchen --full
uv run python -m src.sandbox --scenario books --full
uv run python -m src.sandbox --scenario health --full

# Test single domain routing inputs directly
uv run python -m src.sandbox "Добавь рецепт лимонной пасты с базиликом"
```
*Expected Result:* The CLI will parse, validate, and simulate saving to the in-memory database, returning a complete routing trace and simulated agent response.

### Step 3: Local Runtime HTTP Server Smoke Verification
Start the local HTTP sandbox runtime server (which emulates the webhook listener interface) and execute verification requests:
```bash
# 1. Start the server (run this in Terminal 1)
uv run python -m src.sandbox runtime serve --host 127.0.0.1 --port 8000
```
In another terminal (Terminal 2), run the following tests:
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
*Expected Result:*
* `/health` returns `HTTP 200 OK` with registered agent names.
* `/webhook/telegram` (valid) returns `HTTP 200 OK` containing routing details and bot response.
* `/webhook/telegram` (invalid) returns `HTTP 400 Bad Request` with an explanation.

*(Once completed, stop the server in Terminal 1 using `Ctrl+C`)*

### Step 4: Bootstrap Preflight Checks & Local State Management
Run read-only preflight checks to diagnose local workspace readiness, dependency CLI presence, and verify the local non-secret state file contract:
```bash
# Verify local tool dependency readiness (Python, Docker, Supabase, Render CLIs)
uv run python -m src.sandbox bootstrap doctor

# Run read-only preflight checks (verifies presence of variables safely without mutating anything)
uv run python -m src.sandbox bootstrap checks --read-only

# Dry-run initializing the local non-secret state file
uv run python -m src.sandbox bootstrap state --init --dry-run

# Initialize the local state file (.bootstrap-state.json is git-ignored)
uv run python -m src.sandbox bootstrap state --init --path .bootstrap-state.json

# Read and print a summary of the initialized state file
uv run python -m src.sandbox bootstrap state --show --path .bootstrap-state.json
```
*Expected Result:* Diagnostics and tool readiness are displayed, and the `.bootstrap-state.json` file is successfully initialized locally and verified without storing any secrets.

### Step 5: Local Supabase Dry-Run Plan
Verify the local Supabase configuration, relational schemas, migrations, seeds, and SQL smoke scripts:
```bash
# Inspect the target resource topology plan
uv run python -m src.sandbox bootstrap plan

# Verify local Supabase asset layout (validates migrations, config, and seed files locally)
uv run python -m src.sandbox bootstrap supabase --local --dry-run

# Simulate the interactive install wizard flow (simulates the 10-step bootstrap checklist)
uv run python -m src.sandbox bootstrap install --dry-run
```
*Expected Result:* The simulator outputs a list of validated migrations, config layouts, and the planned wizard execution checklist.

### Step 6: Telegram Webhook Readiness Simulation
Simulate the final webhook deployment configuration, verification checklists, and smoke checks without calling live APIs:
```bash
# Dry-run Telegram Bot API token handoff and webhook target mapping
uv run python -m src.sandbox bootstrap telegram --webhook --dry-run

# Dry-run end-to-end apply stages (prepares the final deployment checklist)
uv run python -m src.sandbox bootstrap apply --dry-run

# Safe preflight check before future live apply (verifies environment readiness, read-only)
uv run python -m src.sandbox bootstrap apply --preflight --read-only

# Dry-run post-deployment smoke validation simulation
uv run python -m src.sandbox bootstrap smoke --dry-run
```
*Expected Result:* All commands complete successfully, producing a detailed plan/checklist of target steps and validations.

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
