# Resume Claims Evidence

This file maps safe public claims to concrete files in this repository. Claims that require private production code, private data, live deployment logs, or internal task history are out of scope for the public repository.

| Claim | Public evidence |
| :--- | :--- |
| Multi-domain agentic runtime with butler-first routing | `src/sandbox/contracts.py`, `src/sandbox/harness.py`, `tests/sandbox/test_cli_routing.py` |
| Domain assemblies are isolated behind typed contracts | `src/sandbox/contracts.py`, `tests/sandbox/test_harness_books.py`, `tests/sandbox/test_harness_health.py`, `tests/sandbox/test_harness_kitchen.py` |
| LLM-style extraction is separated from deterministic validation and persistence | `src/sandbox/fake_llm.py`, `src/sandbox/harness.py`, `tests/sandbox/test_fake_llm.py` |
| Reviewer path runs offline with synthetic data and in-memory persistence | `docs/REVIEWER_GUIDE.md`, `docs/SYNTHETIC_DATA_POLICY.md`, `tests/sandbox/` |
| Health-log capture is limited to structural data capture, not medical advice | `docs/PUBLIC_SURFACE.md`, `docs/ARCHITECTURE.md`, `tests/sandbox/test_harness_health.py` |

Do not claim that the public repository includes production Telegram runtime, live Supabase/PostgreSQL operation, real LLM credentials, real user data, or medical decision support.
