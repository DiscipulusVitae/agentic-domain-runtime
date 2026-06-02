# Local Supabase Package

This directory contains a public-safe, runnable local Supabase scaffold. It enables verification of the database structure, custom schemas, Row Level Security (RLS) policies, and API endpoints locally.

## Contents

- `config.toml`: Configures the local Supabase environment, exposes custom logical schemas (`core`, `kitchen`, `books`, `med`, `api`), and enables automatic database seeding.
- `migrations/0001_schema.sql`: Contains the DDL scripts defining schemas, tables, constraints, RLS policies, and role grants.
- `seed.sql`: Seeds the local database with synthetic and public-safe identity and operational data.

## Running Locally

> [!NOTE]
> Running the local Supabase path requires [Docker](https://www.docker.com/) and the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) installed.

Ensure your Docker daemon is running, then execute the following from the root of the extracted public repository:

```bash
# Start the local Supabase containers (PostgreSQL, Auth, Studio, REST API, etc.)
supabase start

# Reset the database state (applies migrations and seeds data)
supabase db reset
```

The database seeds will be applied automatically, creating mock users and mock domain entries. You can then access the local Supabase Studio dashboard at [http://localhost:54323](http://localhost:54323).
