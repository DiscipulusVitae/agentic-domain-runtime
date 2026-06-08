import json
from pathlib import Path
from ..models import (
    OfflineDryRunStep,
    BootstrapState,
)

def run_supabase_bootstrap(local: bool, dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой запуск локального плана Supabase."""
    assets = {
        "config": "supabase/config.toml",
        "migrations": "supabase/migrations/0001_schema.sql",
        "seed": "supabase/seed.sql",
        "smoke": "supabase/smoke.sql",
        "readme": "supabase/README.md",
        "runbook": "docs/RUNBOOK_LOCAL_SUPABASE.md",
    }

    # Проверяем файлы
    asset_details = {}
    has_fail = False
    for key, rel_path in assets.items():
        p = Path(rel_path)
        exists = p.is_file()
        if not exists:
            has_fail = True
        asset_details[key] = {
            "path": rel_path,
            "exists": exists
        }

    # Создаем шаги BootstrapStep
    step_assets = OfflineDryRunStep(
        step_id="supabase_assets_check",
        name="Проверка наличия файлов Supabase пакета",
        status="blocked" if has_fail else "ready",
        message="Некоторые локальные ассеты Supabase отсутствуют" if has_fail else "Все локальные ассеты Supabase найдены",
        details={"assets": asset_details}
    )

    command_plan = [
        "supabase start",
        "supabase db reset",
        "supabase db query --local --file supabase/smoke.sql",
        "supabase stop"
    ]
    disk_safe_note = "local simulator runs fully offline and does not spawn Docker containers/services unless docker daemon is started"
    service_exclusion_hint = "to exclude services use flags in supabase/config.toml or stop unused services manually"

    step_plan = OfflineDryRunStep(
        step_id="supabase_command_plan",
        name="Локальный план команд Supabase",
        status="ready",
        message="План команд сформирован для локального тестирования Supabase",
        details={
            "command_plan": command_plan,
            "disk_safe_note": disk_safe_note,
            "service_exclusion_hint": service_exclusion_hint
        }
    )

    steps = [step_assets, step_plan]

    state = BootstrapState(
        dry_run=True,
        message="Это сухой запуск локального плана Supabase (dry-run). Команды не выполнялись.",
        steps=steps,
        metadata={
            "local": True,
            "mutation_prevented": True
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Supabase Local Plan (DRY-RUN) ===")
        print("Внимание: Это сухой запуск локального плана Supabase. Никакие команды не выполнялись.")
        print()
        print("1. Статус локальных файлов Supabase:")
        for key, details in asset_details.items():
            status_str = "[OK]" if details["exists"] else "[FAIL]"
            print(f"   {status_str} {details['path']}")
        print()
        print("2. План команд локального Supabase:")
        for cmd in command_plan:
            print(f"   - {cmd}")
        print()
        print("3. Примечания по безопасности (Safety Hints):")
        print(f"   - disk-safe note: {disk_safe_note}")
        print(f"   - service-exclusion hint: {service_exclusion_hint}")
        print("=" * 50)

    return 1 if has_fail else 0
