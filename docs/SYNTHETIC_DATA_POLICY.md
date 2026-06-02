# Synthetic Data Policy

This document defines the policy, rules, and boundaries for creating and using synthetic reviewer data within the public `agentic-domain-runtime` repository.

## 1. Core Principles

### Synthetic-Only Principle
To ensure clean reproducibility, showcase security discipline, and maintain a professional curated boundary, all data fixtures, seed databases, test payloads, and reviewer examples published in the repository are constructed using synthetic personas and operational records, with public-literature examples where useful. This avoids cluttering the portfolio with raw personal logs, casual recipes, or operational history, and guarantees that the entire test suite can be run out-of-the-box in any local environment.

### Strict Prohibition of Anonymized Real Data
The anonymization or masking of real user data for use as public fixtures is strictly prohibited. Even when scrubbed of direct identifiers (such as names or dates), real data may contain unique behavioral patterns, specific custom recipes, or complex health histories that could compromise user privacy or expose sensitive contexts. All reviewer assets must be generated from scratch.

### Safe Reviewer Personas Policy
Any reviewer scenario involving user profiles must employ clearly fictional personas.
- Fictional names (e.g., "Alice Vance", "Bob Miller") must be used.
- Fictional Telegram identifiers (e.g., user ID `123456789`) must be used.
- Coincidences with real developers, family members, or system testers are entirely accidental and must be avoided during fixture generation.

---

## 2. Forbidden Data Sources

Under no circumstances should the public repository draw data from the following internal sources:
- Active or archived family database records (PostgreSQL / Supabase exports).
- Private Telegram message histories, user logs, or interaction audits.
- Real health journals, symptom trackers, or medication histories.
- Real personal libraries, book progress charts, and imported notes.
- Private system configurations, hosting logs, and active environment variables.

---

## 3. Allowed Data Classes

Synthetic files and tests may include:

### Kitchen Domain
- Artificial culinary recipes (e.g., "Fictional Galactic Pancakes", "Mock Garden Salad").
- Generated ingredient lists, batching guides, and placeholder image assets.

### Books Domain
- Common public domain books (e.g., "Alice in Wonderland", "The Time Machine").
- Fictional custom reading lists and synthetic reading session steps.

### Health-Log Capture Domain
- Structured records of standard daily metrics (e.g., step counts like 10,000 steps, sleep duration, water intake).
- Mock physical logs (e.g., standard height, weight, activity notes) formatted for parser validation.

### System & Metadata
- Non-active test credentials, mock API parameters, and offline placeholder configurations.
- Fictional timestamps (e.g., `2026-05-28T12:00:00Z`).

---

## 4. Pre-Publication Verification and Scrubbing

Before any release branch is pushed to the public platform, a mandatory audit sequence must verify the following:

- **Credential Scanning**: Automated checks to ensure that no active bot authorization parameters, platform credentials, or API secret structures are present in the files.
- **Identity Cleansing**: Scrutiny of all text blocks to remove any real names, email addresses, or actual messaging identifiers.
- **Environmental Scrubbing**: Removal of any unique cloud hosting configuration properties, project endpoint domains, or back-end platform identifiers.
- **Medical Claim Validation**: Ensuring that the terminology in health-log documents conforms strictly to the safe boundaries defined below.

---

## 5. Generated Content Guidelines

When utilizing LLMs to generate synthetic test cases:
- **Image Generation**: Any mock media (such as kitchen recipes or dish photos) must be fully artificial, containing no real human faces, identifiable metadata, or external watermarks.
- **Text Extraction Mocks**: Unstructured message mocks must be crafted to resemble casual, generic conversations rather than real private chats.

---

## 6. Health-Log Capture Safety Boundaries

To ensure regulatory compliance and align with safety standards, all descriptions, test payloads, and user interface representations of the health-log feature are strictly constrained.

### Approved Terminology
All public documents must refer to the feature using only the following approved terms:
- `health-log capture`
- `capture/extraction`
- `deterministic validation and persistence`
- `LLM orchestration/extraction`

### Prohibited Functionality & Statements
The health-log domain must be presented purely as a data-entry automation utility. To enforce this boundary:
- The system must never be described as a clinical helper or virtual care assistant.
- No references to analyzing health symptoms to determine underlying causes (identifying conditions or clinical assessment) are allowed.
- No suggestions on therapy, medication regimens, or clinical instructions are permitted.
- No healthcare guidelines or professional health suggestions are allowed.
- No computer-aided clinical analysis or practitioner support systems are permitted.
- No acute sorting of symptoms or urgent care prioritization is allowed.

### Negative Boundary Clause
The system is designed strictly for deterministic event capturing and storage of health parameters. It does not provide medical conclusions, therapy plans, healthcare guidance, automated clinical judgment, or urgent care sorting.
