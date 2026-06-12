# START HERE

Три пути для reviewer или developer. Выберите один.

---

## Путь 1 — Проверить архитектуру offline

Без Docker, без API-ключей, без внешних сервисов. Работает везде, где есть Python 3.13+ и `uv`.

```bash
uv sync
uv run pytest tests/sandbox -q
uv run python -m src.sandbox --scenario kitchen --full
```

Результат: 99+ тестов, 4 сценария на домен. Все на синтетических данных.

*Примечание:* Поддерживается опциональный запуск через совместимый с OpenAI API-провайдер (`openai_compatible`). Подробнее см. в [README.md](README.md).

→ Подробнее: [Reviewer Guide](docs/REVIEWER_GUIDE.md), Path A.

---

## Путь 2 — Проверить локальную инфраструктуру (Supabase)

Docker + Supabase CLI. Проверить схему БД, миграции, RLS, smoke.sql локально.

```bash
supabase start
supabase db reset
supabase db query --local --file supabase/smoke.sql
```

Результат: 26/26 smoke checks pass.

→ Подробнее: [Local Supabase Package](supabase/README.md), [Local Supabase Runbook](docs/RUNBOOK_LOCAL_SUPABASE.md).

---

## Путь 3 — Live cloud proof (guided wizard, alpha)

Для reviewer/test аккаунтов. Guided wizard: doctor → план → Supabase → Render → smoke.

**Dry-run preview (без мутаций):**

```bash
uv run python -m src.sandbox bootstrap install --dry-run
uv run python -m src.sandbox bootstrap plan
uv run python -m src.sandbox bootstrap doctor
```

**Live installer v1 alpha (требует explicit GO и reviewer/test аккаунты):**

```bash
uv run python -m src.sandbox bootstrap install --yes
```

Operational proof на disposable ресурсах (Supabase + Render + Telegram /health) — выполнен.
Installer v1 alpha — реализован. Win+WSL2 proof run выполнен с caveats: guided wizard + Supabase live path proven, fresh Render ADR deploy pending.

**Ручной runbook (fallback):**

Если guided wizard не покрывает сценарий, доступен прямой manual путь через Supabase CLI + Render CLI. См. runbook.

→ Подробнее: [Reviewer Guide](docs/REVIEWER_GUIDE.md), Path C.
→ Операционные находки: [Wiring Runbook](docs/SUPABASE_RENDER_WIRING_RUNBOOK.md).

---

## Что сейчас в разработке

- **Live installer v1 alpha** — принят. Guided wizard (7 шагов: doctor → plan → Supabase → Render → Telegram webhook → smoke → summary) доказан на Win+WSL2. Fresh Render ADR deploy — pending.
- **Cleanup wizard** — `bootstrap cleanup --live`, guided удаление ресурсов. Ждёт live validation.
- **Security hardening** — Render REST API для secrets, conditional state deletion, fail-safe webhook. Завершён.
- **AI-reviewer simulation** — следующий горизонт.

---

## Состояние proof layers

| Proof | Статус | Режим |
|:---|:---|:---|
| Offline sandbox (тесты, сценарии, HTTP server) | работает | fully offline |
| Docker reviewer path | работает | полностью контейнеризован |
| Local Supabase (схема, RLS, smoke.sql) | работает | Docker + Supabase CLI |
| Cloud bootstrap (Supabase + Render + Telegram /health) | доказан (существующий сервис) | ручной runbook, human-authorized |
| Live installer (guided wizard) | v1 alpha | `bootstrap install --yes` |
| Win+WSL2 proof run | выполнен с caveats | guided wizard + Supabase proven, fresh Render pending |
| Optional OpenAI-compatible LLM path | implemented | manual config, mocked tests, validation-gated |
