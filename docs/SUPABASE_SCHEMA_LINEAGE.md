# Supabase Schema Lineage

This document describes the logical database schema layout and storage architecture used in the private production environment and explains how the public repository's mock persistence layers map conceptually to PostgreSQL boundaries.

---

## 1. Conceptual Namespaces

The production database is structured into isolated logical namespaces using table prefixes. This prevents tight coupling and ensures clean boundaries between independent domain assemblies:

- **`core` Namespace**:
  - Manages tenant contexts, user preferences, and Butler FSM conversational sessions.
  - Conceptual tables: `core_users`, `core_sessions`, `core_preferences`.

- **`kitchen` Namespace**:
  - Stores recipe metadata, structured ingredient indexes, cooking instructions, and links to photo attachments.
  - Conceptual tables: `kitchen_recipes`, `kitchen_ingredients`, `kitchen_recipe_ingredients`, `kitchen_photos`.

- **`books` Namespace**:
  - Stores book metadata, library catalogs, and user reading progress events.
  - Conceptual tables: `books_library`, `books_reading_sessions`, `books_authors`.

- **`med` Namespace**:
  - Stores structured logs of health-related metrics (e.g., blood pressure, heart rate, blood glucose) with high-granularity timestamps.
  - Conceptual tables: `med_metric_logs`, `med_subject_profiles`.

- **`api` Namespace**:
  - Handles integration mapping, request logs, and telemetry indexes.
  - Conceptual tables: `api_request_logs`, `api_token_scopes`.

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
- **Safety Margin**: A port of standard database migrations to the public repo could risk minor schema leakage (e.g., specific user flags).
- **Separation of Concerns**: This repository demonstrates the domain runtime engine, not DevOps/database provisioning scripts.
