# Resume Claims Evidence

This document maps engineering resume claims to concrete evidence in this repository, separating directly verifiable public code/tests from private production lineage.

---

## 1. Directly Evidenced in this Repository

These claims are directly verifiable by running the tests, reading the codebase, and inspecting the local reviewer CLI:

| Resume Claim | Verifiable Files & Paths | Test Suite Coverage |
| :--- | :--- | :--- |
| **Multi-domain routing with free-input classification** | `src/sandbox/contracts.py`, `src/sandbox/harness.py`, `src/sandbox/cli.py` | `tests/sandbox/test_cli_routing.py` |
| **Domain assemblies isolated behind strict typed contracts** | `src/sandbox/contracts.py` | `tests/sandbox/test_harness_books.py`, `tests/sandbox/test_harness_health.py`, `tests/sandbox/test_harness_kitchen.py` |
| **Separation of LLM extraction from validation and persistence** | `src/sandbox/fake_llm.py`, `src/sandbox/harness.py` | `tests/sandbox/test_fake_llm.py` |
| **Offline reviewer harness running on synthetic data** | `src/sandbox/fixtures/`, `docs/SYNTHETIC_DATA_POLICY.md` | `tests/sandbox/` |
| **Non-clinical health logging data capture boundaries** | `src/sandbox/contracts.py` (MedicalEntry), `docs/PUBLIC_SURFACE.md` | `tests/sandbox/test_harness_health.py` |
| **Optional OpenAI-compatible provider integration with model fallback** | `src/sandbox/openai_client.py`, `src/sandbox/fake_llm.py`, `src/sandbox/config.py` | `tests/sandbox/test_openai_client.py`, `tests/sandbox/test_sandbox_config.py` |
| **Validation-gated persistence for unstructured data extraction** | `src/sandbox/harness.py` (health flow persistence checks), `src/sandbox/contracts.py` | `tests/sandbox/test_harness_health.py` (`test_health_flow_openai_valid_persists`, `test_health_flow_openai_malformed_json`, `test_health_flow_openai_invalid_validation`) |


---

## 2. Private-Source Lineage (Documented Architecture)

These claims represent production-tested patterns from the private codebase. They are documented in this public repository but are not directly shipped as runnable code to ensure privacy:

- **Telegram Bot / Mini App Integration**: The production interface using `aiogram` 3.x and custom React components is replaced by the local CLI harness. (See [Private-to-Public Lineage](PRIVATE_TO_PUBLIC_LINEAGE.md)).
- **Supabase / PostgreSQL Logical Relational Schema**: The production multi-namespace database layout and Row-Level Security (RLS) policies are demonstrated via a runnable local Supabase package, while the default offline sandbox uses local in-memory persistence mocks. (See [Supabase Schema Lineage](SUPABASE_SCHEMA_LINEAGE.md)).
- **Redis State Machine & Queue Batching**: Production FSM session locks and batching queues are removed in the public sandbox to stay offline.
- **Render-based DevOps Pipeline**: Production automated container deployments and render configuration scripts are omitted from this public slice.
