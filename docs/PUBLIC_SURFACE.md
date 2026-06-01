# Public Surface Contract

This contract defines the strict boundaries, strategy, and rules for publishing `agentic-domain-runtime` as a curated technical portfolio derived from the private source repository.

## 1. Purpose
The purpose of the public repository is to showcase a reusable agentic domain runtime and act as a technical portfolio artifact for professional review and resume validation. The public reviewer path must be local-first and must not require Telegram credentials, production Supabase, Render, or live LLM keys. The private source repository contains private task history, agent prompts, operational notes, credentials, and real personal/health data. It is therefore unsuitable for direct publication. The public repository must be a curated, clean version of the runtime, documentation, local reviewer sandbox, and synthetic fixtures.

## 2. Publication Strategy
- **Clean Repository / Squashed Branch**: The codebase will be published to a separate public repository or as a squashed public branch with a completely fresh git history.
- **Git History Boundary**: Under no circumstances shall the existing private git history be preserved or published as public history.
- **Curated Staging**: A curated staging directory will be created to verify the allowed file set and run automated scrub rules prior to final publication.

## 3. Allowlist-First Public File Set
We enforce a strict allowlist-first principle: **a file is private and non-public unless it is explicitly allowed**.
The allowlist of publishable assets includes:
- Cleaned and audited codebase files under `src/` (reusable core runtime, butler routing, and domain logic).
- Non-sensitive tests in `tests/` that run purely using synthetic data without active database credentials.
- Project metadata and config files: `pyproject.toml`, `uv.lock`, `.env.example`, CI config, and license.
- Public documentation files under `docs/public/*` (including this contract).
- Synthetic data fixtures and local reviewer sandbox configurations.
- Local in-memory sandbox storage for reviewer verification.

## 4. Internal-Only / Denylist File Set
The following files and paths must remain private and are strictly forbidden from appearing in the public repository:
- All agent instructions and prompts under `.agents/`.
- The `tasks/` directory, developer notes, and task progress folders.
- Any task reports, coder/tester reports, and agent activity history.
- Private system prompts, developer operational guides, and raw LLM traces.
- Telegram audit/session logs, console logs, and deployment logs.
- Real family recipe texts, private comments, and personal notes.
- Real book details, reading history, and notes imported from external tools.
- Real medical logs, health parameters, symptom diaries, and personal health data.
- Supabase backups, database exports, and production migration history.
- The `.env` file, actual credentials, keys (`BOT_TOKEN`, `GEMINI_API_KEY`, etc.), and secrets.
- Production environment configurations and operational identifiers (e.g., Render service IDs, Supabase project URLs, connection strings).
- Application screenshots containing real personal names, dates, or sensitive health data.

## 5. Scrub Rules
Before any file is copied to the public repository, it must be scanned and scrubbed for:
- API tokens, passwords, database credentials, and service keys.
- Real Telegram User IDs and usernames.
- Real family names, personal emails, or recognizable personal identifiers.
- Production Supabase/Render project domains and URLs.
- Real text from recipes, personal books, or private health records.
- Unsafe medical terminology, references to clinical treatments, or specific diseases.
- Alignment with the health safety wording boundaries.

## 6. Synthetic Fixtures Policy
- **Artificial Data Only**: All fixtures, seed databases, reviewer scenarios, and example payloads must be constructed entirely from scratch as artificial (synthetic) data.
- **No Anonymized Real Data**: Anonymizing real recipes, reading lists, or health logs is strictly prohibited. Synthetic files must contain clearly artificial, mock entries (e.g., generic recipes, generic book titles, fictional health logs).
- **Labeling**: All synthetic files and databases must be explicitly documented and labeled as synthetic.

## 7. Health-Log Safety Boundaries
To avoid regulatory, safety, and operational risks, the public terminology and scope of the health-log feature are strictly constrained.
- **Approved Wording**:
  - `health-log capture`
  - `capture/extraction`
  - `deterministic validation and persistence`
  - `LLM orchestration/extraction`
- **Strictly Prohibited Claims**:
  The project must never be marketed, described, or documented as providing:
  - Medical assistant capabilities
  - Diagnosis or diagnostic support
  - Treatment advice
  - Medical recommendations
  - Clinical decision support (CDS)
  - Emergency triage or urgent health assistance
- **Negative Boundary Statement**:
  The system is a deterministic data-capture tool for health events. It does not provide diagnosis, treatment advice, medical recommendations, clinical decision support, or emergency triage.

## 8. Local Sandbox / CI / Reviewer Path Requirements
The public repository must provide a clear and executable path for reviewers to verify the system without production credentials.
- **Local Verification**: Reviewers must be able to run:
  ```bash
  uv sync
  uv run pytest
  ```
- **Local Sandbox**: The default reviewer flow should run through a local reviewer harness/API/CLI with in-memory persistence.
- **No Live DB Dependencies**: Automated tests must be executable offline, using synthetic seed data without relying on live Supabase secrets or local database setup.
- **No Required Telegram Runtime**: Telegram bot runtime is not part of the default public reviewer path.
- **No Required Live LLM Provider**: The default reviewer path uses a fake/offline LLM provider. Real LLM providers are optional and must require explicit local environment configuration.
- **Reviewer Guide**: A quickstart guide with a `.env.example` must contain placeholder configurations to guide local setup.

## 9. Resume Claims Policy
All claims made in resumes, portfolios, or external project profiles must be strictly backed by code and documentation present in the public repository.
- **Permitted Claims**:
  - Reusable platform runtime and clean domain assembly architecture.
  - Multi-domain LLM-assisted runtime.
  - Hybrid orchestration: LLM orchestrates extraction while deterministic services validate and persist data.
  - Supabase/PostgreSQL domain namespace isolation.
  - Health-log capture domain with strict safety boundaries.
  - Test coverage using synthetic fixtures.
- **Prohibited Claims**:
  - Autonomous medical AI assistant.
  - Diagnostic/treatment advice engine.
  - High-consequence agentic autonomy.
  - Claims that rely on private code, internal metrics, or private logs.

## 10. Publish Gate Checklist
Before public release, the repository must pass the following audits:
- [ ] **Allowlist Check**: Only files matching the allowlist exist in the release branch.
- [ ] **Denylist Audit**: All forbidden files (e.g. `.agents/`, `tasks/`, internal logs, backups) are completely removed.
- [ ] **Secret Scan**: Running automated tools (e.g. `gitleaks`) returns no credentials.
- [ ] **Private Data Audit**: Checks confirm zero instances of real family, recipe, books, Telegram, or health-log data.
- [ ] **Wording Audit**: Prohibited medical terms (diagnosis, treatment, emergency, etc.) are absent from code and docs.
- [ ] **Offline Tests Pass**: Ensure `uv run pytest` runs cleanly with synthetic seed data and no active production connections.
- [ ] **Reviewer Path Ready**: The quickstart instructions and offline sandbox are fully verified.
- [ ] **Evidence Check**: All resume claims correspond directly to the public code artifacts.
