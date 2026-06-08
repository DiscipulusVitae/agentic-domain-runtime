import json
import sys
from pathlib import Path
from ..plan import generate_bootstrap_plan

def run_cleanup(
    preview: bool,
    local: bool,
    state_path: str | None,
    json_mode: bool,
) -> int:
    """Локальный preview плана rollback/cleanup перед будущим live apply.

    Не взаимодействует с внешними API, БД или облачными провайдерами.
    """
    if not preview or not local:
        print("Ошибка: Команда cleanup требует обязательного указания флагов --preview и --local.", file=sys.stderr)
        return 1

    actual_state_path = None
    state_file_exists = False

    if state_path is not None:
        p = Path(state_path)
        if p.exists():
            actual_state_path = p
            state_file_exists = True
        else:
            safe_name = p.name
            if json_mode:
                print(json.dumps({
                    "error": "State file not found",
                    "path": safe_name
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка: Файл состояния не найден по пути '{safe_name}'.", file=sys.stderr)
            return 1
    else:
        p = Path(".bootstrap-state.json")
        if p.exists():
            actual_state_path = p
            state_file_exists = True

    plan = generate_bootstrap_plan()

    source = "deterministic_plan"
    state_data = None
    safe_path_name = None

    if state_file_exists and actual_state_path is not None:
        safe_path_name = actual_state_path.name
        source = f"state_file: {safe_path_name}"
        try:
            with open(actual_state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except Exception as e:
            if json_mode:
                print(json.dumps({
                    "error": f"Failed to read state file: {str(e)}",
                    "path": safe_path_name
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка при чтении файла состояния '{safe_path_name}': {e}", file=sys.stderr)
            return 1

    applied_steps = []
    resources = {}

    if state_data is not None:
        resources_raw = state_data.get("resources", {})
        applied_steps = state_data.get("applied_steps", [])

        resources = {
            "supabase_project_name": resources_raw.get("supabase_project_name"),
            "supabase_organization": resources_raw.get("supabase_organization"),
            "render_web_service_name": resources_raw.get("render_web_service_name"),
            "render_environment_group": resources_raw.get("render_environment_group"),
            "webhook_target_url": resources_raw.get("webhook_target_url")
        }
    else:
        resources = {
            "supabase_project_name": plan.supabase_project_name,
            "supabase_organization": plan.supabase_organization,
            "render_web_service_name": plan.render_web_service_name,
            "render_environment_group": plan.render_environment_group,
            "webhook_target_url": plan.webhook_target_url
        }

    has_supabase = any(s in applied_steps for s in ["supabase", "supabase_sim_db_created"])
    has_render = any(s in applied_steps for s in ["render", "render_sim_service_created"])
    has_telegram = any(s in applied_steps for s in ["telegram", "telegram_sim_webhook_configured"])

    resources_status = {}
    for key, val in resources.items():
        if state_data is None:
            resources_status[key] = {
                "value": val,
                "status": "planned_not_created"
            }
        else:
            if "supabase" in key:
                status = "created" if has_supabase else "planned_not_created"
            elif "render" in key:
                status = "created" if has_render else "planned_not_created"
            elif "webhook" in key:
                status = "created" if has_telegram else "planned_not_created"
            else:
                status = "planned_not_created"

            resources_status[key] = {
                "value": val,
                "status": status
            }

    cleanup_steps = []

    tg_action_type = "manual/future-live" if has_telegram else "skipped/not-created"
    tg_outcome = "Вебхук Telegram будет удален, команды бота очищены" if has_telegram else "skipped"
    cleanup_steps.append({
        "step_id": "telegram",
        "name": "Снятие вебхука Telegram и очистка команд бота",
        "type": tg_action_type,
        "outcome": tg_outcome
    })

    render_action_type = "manual/future-live" if has_render else "skipped/not-created"
    render_outcome = "Веб-сервис Render и группа окружения будут удалены" if has_render else "skipped"
    cleanup_steps.append({
        "step_id": "render",
        "name": "Удаление веб-сервиса Render и группы окружения",
        "type": render_action_type,
        "outcome": render_outcome
    })

    sb_action_type = "manual/future-live" if has_supabase else "skipped/not-created"
    sb_outcome = "Проект Supabase и таблицы базы данных будут удалены" if has_supabase else "skipped"
    cleanup_steps.append({
        "step_id": "supabase",
        "name": "Удаление проекта Supabase и очистка базы данных",
        "type": sb_action_type,
        "outcome": sb_outcome
    })

    state_action_type = "automatic/local" if state_file_exists else "skipped/not-created"
    state_outcome = f"Локальный файл состояния '{safe_path_name}' будет удален" if state_file_exists else "skipped"
    cleanup_steps.append({
        "step_id": "state_file",
        "name": "Удаление локального файла состояния",
        "type": state_action_type,
        "outcome": state_outcome
    })

    if state_file_exists:
        if has_telegram or has_render or has_supabase:
            expected_outcome = "Все созданные ресурсы будут удалены (требует live-запуска), локальный файл состояния удален."
        else:
            expected_outcome = "Созданные ресурсы отсутствуют, локальный файл состояния удален."
    else:
        expected_outcome = "Созданные ресурсы отсутствуют, локальное состояние не требует изменений."

    warning_msg = "Внимание: Это исключительно локальное превью (dry-run). Никакие реальные запросы к API Telegram, Render или Supabase не выполняются. Изменения в облаке отсутствуют."

    if json_mode:
        output_json = {
            "source": source,
            "state_path": safe_path_name,
            "synthetic_resources": resources_status,
            "cleanup_steps": cleanup_steps,
            "expected_outcome": expected_outcome,
            "live_mutations_present": False,
            "warning": warning_msg
        }
        print(json.dumps(output_json, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Rollback/Cleanup Preview ===")
        print(f"Источник состояния:  {source}")
        print(f"Путь к файлу:        {safe_path_name or 'n/a'}")
        print()
        print("Синтетические ресурсы:")
        for res_name, info in resources_status.items():
            print(f"  - {res_name}: {info['value']} (Статус: {info['status']})")
        print()
        print("Порядок очистки (reverse dependency order):")
        for idx, step in enumerate(cleanup_steps, 1):
            print(f"  {idx}. [{step['type'].upper()}] {step['name']}")
            print(f"     Ожидаемый результат: {step['outcome']}")
        print()
        print(f"Итоговый статус:     {expected_outcome}")
        print()
        print("ПРЕДУПРЕЖДЕНИЕ:")
        print(f"  {warning_msg}")
        print("=" * 46)

    return 0
