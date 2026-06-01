# Reviewer Schema Package: Database Sketches & Synthetic Seeds

This directory contains public-safe schema sketches and synthetic data seeds designed to demonstrate the database architecture layout of the **family-ai** project.

---

## What is in this package?

1. **`schema_sketches.sql`**: Conceptual DDL definitions for logical namespaces (`core`, `kitchen`, `books`, `med`, `api`) used by the Agentic Domain Runtime (ADR).
2. **`synthetic_seeds.sql`**: Fully artificial database inserts designed for system flow tests, demonstration, and offline validation.

---

## Why this is NOT a Production Migration

For operational security and architectural integrity, the live PostgreSQL/Supabase production migration scripts are omitted from this public surface. Here is how this package differs:

- **No Secrets or Identifiers**: Unlike live migrations, this package contains zero Telegram user IDs of actual family administrators, no live Supabase Storage bucket URLs, and no production API tokens.
- **Conceptual RLS Policies**: Row Level Security (RLS) examples in `schema_sketches.sql` illustrate how security boundaries are checked dynamically using request parameters, but without live target subjects.
- **Offline / Sandbox First**: This schema aligns with the in-memory persistence models implemented in `src/sandbox/` and verified during offline reviewer scenario execution.

---

## Database Namespace Overview

Our persistence layout is divided into isolated logical namespaces (schemas) to keep domain boundaries clean:

| Namespace (Schema) | Purpose | Key Tables |
| :--- | :--- | :--- |
| **`core`** | Bot FSM context, user mappings, and conversation audit trails. | `app_users`, `runtime_app_sessions`, `telegram_chat_audit` |
| **`kitchen`** | Cooking metadata, recipes, and image asset references. | `dishes` |
| **`books`** | Library catalogs, authors, highlights/notes, and reading sessions. | `books`, `authors`, `notes`, `reading_sessions` |
| **`med`** | High-granularity health journals (BP, pulse, glucose levels). | `medical_entries` |
| **`api`** | Telemetry tracking and external synchronization scopes. | `token_scopes`, `request_logs` |

---

## How to Read and Verify

The offline sandbox verifies logic flows against memory models that mirror this schema. You can run checks inside the sandbox directory:

```bash
# Execute local sandbox smoke tests
uv run pytest tests/sandbox -q

# Execute specific scenario validations
uv run python -m src.sandbox --scenario kitchen --full
uv run python -m src.sandbox --scenario books --full
uv run python -m src.sandbox --scenario health --full
```
