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

## Путь 3 — Пройти live deploy proof (человек + CLI)

Human-authorized dry-run preview и/или полный cloud proof на disposable ресурсах.

**Dry-run preview (без мутаций):**

```bash
uv run python -m src.sandbox bootstrap install --dry-run
uv run python -m src.sandbox bootstrap plan
uv run python -m src.sandbox bootstrap doctor
```

**Live deploy proof (требует explicit GO и reviewer/test аккаунты):**

Доказан на disposable ресурсах (Supabase + Render + Telegram) с полным cleanup.
Автоматический live installer находится в разработке. Пока live path — через ручной runbook.

→ Подробнее: [Reviewer Guide](docs/REVIEWER_GUIDE.md), Path C.
→ Операционные находки: [Wiring Runbook](docs/SUPABASE_RENDER_WIRING_RUNBOOK.md).

---

## Что сейчас в разработке

- **`bootstrap install`** — сегодня это dry-run preview/checklist. Полноценный live installer (с guided wizard, проверкой окружения и пошаговым deploy) — в roadmap на ближайший горизонт.
- **AI-reviewer simulation** — следующий шаг после installer productization.

---

## Состояние proof layers

| Proof | Статус | Режим |
|:---|:---|:---|
| Offline sandbox (тесты, сценарии, HTTP server) | работает | fully offline |
| Docker reviewer path | работает | полностью контейнеризован |
| Local Supabase (схема, RLS, smoke.sql) | работает | Docker + Supabase CLI |
| Cloud bootstrap (Supabase + Render + Telegram) | доказан | ручной runbook, human-authorized |
| Live installer (единый guided wizard) | в разработке | см. roadmap |
