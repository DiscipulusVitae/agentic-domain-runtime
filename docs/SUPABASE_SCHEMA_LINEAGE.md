# Supabase Schema Lineage

This document describes the logical database schema layout and storage architecture used in the private production environment and explains how the public repository's mock persistence layers map conceptually to PostgreSQL boundaries.

---

## 1. Conceptual Namespaces

The production database is structured into isolated logical database schemas/namespaces. This prevents tight coupling and ensures clean boundaries between independent domain assemblies:

- **`core` Schema / Namespace**:
  - Manages tenant contexts, user preferences, and Butler FSM conversational sessions.
  - Conceptual tables: `core.users`, `core.sessions`, `core.preferences`.

- **`kitchen` Schema / Namespace**:
  - Stores recipe metadata, structured ingredient indexes, cooking instructions, and links to photo attachments.
  - Conceptual tables: `kitchen.recipes`, `kitchen.ingredients`, `kitchen.recipe_ingredients`, `kitchen.photos`.

- **`books` Schema / Namespace**:
  - Stores book metadata, library catalogs, and user reading progress events.
  - Conceptual tables: `books.library`, `books.reading_sessions`, `books.authors`.

- **`med` Schema / Namespace**:
  - Stores structured logs of health-related metrics (e.g., blood pressure, heart rate, blood glucose) with high-granularity timestamps.
  - Conceptual tables: `med.metric_logs`, `med.subject_profiles`.

- **`api` Schema / Namespace**:
  - Handles integration mapping, request logs, and telemetry indexes.
  - Conceptual tables: `api.request_logs`, `api.token_scopes`.

---

## 2. Public-to-Private Storage Mapping

The public sandbox utilizes an in-memory repository pattern to simulate data persistence:

| Public Sandbox Class | Conceptual Relational Map | Production Implementation Seam |
| :--- | :--- | :--- |
| `FakeBooksService` | `books_library` table | Executes Supabase query inside `asyncio.to_thread` |
| `FakeMedicalService` | `med_metric_logs` table | Executes a multi-row insert query matching standard columns |
| `FakeKitchenService` | `kitchen_recipes` & `kitchen_ingredients` | Runs an atomic transaction to insert recipe and ingredients |

### In-Memory Mocks vs. Live Transactions
- **Mocks**: In-memory Python `list` appends with automatic object instantiation. Excellent for rapid offline validation and pytest assertions.
- **Production**: Async database connectors translating Pydantic models into SQL parameters. RLS policies automatically filter rows based on `auth.uid()` or the verified Telegram user ID extracted during request bootstrap.

---

## 3. Why Production Migrations Are Omitted

To maintain a secure posture:
- **Private References**: Production SQL migration scripts contain hardcoded Telegram IDs of administrators, RLS exception rules, external storage bucket names, and API references that are sensitive.
- **Safety Margin**: Production migrations are not copied or published to the public repository. This prevents any minor schema leakage (e.g., specific user flags or system extensions).
- **Separation of Concerns**: This repository demonstrates the domain runtime engine, not DevOps/database provisioning scripts.

---

## 4. Database Schema & Verification Artifacts

To bridge the gap between in-memory mock structures and PostgreSQL boundaries, refer to the public-safe:
- **[Database Schema Sketches](schema/schema_sketches.sql)**: Logical DDL layout sketches and conceptual schemas.
- **[Local Supabase Package](../../supabase/README.md)**: Runnable migrations, RLS policies, seeds, and local Docker configurations.
- **[Local Supabase Runbook](RUNBOOK_LOCAL_SUPABASE.md)**: Optional local-first verification path guide.
