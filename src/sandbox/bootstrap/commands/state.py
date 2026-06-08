import datetime
import json
import sys
from pathlib import Path
from ..plan import generate_bootstrap_plan

def run_bootstrap_state(
    init: bool,
    show: bool,
    dry_run: bool,
    path: str,
    json_mode: bool,
    overwrite: bool,
) -> int:
    """Управление локальным файлом состояния (bootstrap state file contract)."""
    plan = generate_bootstrap_plan()
    state_path = Path(path)

    if init:
        # Проверяем, существует ли файл и является ли он непустым
        file_exists_and_non_empty = False
        if state_path.exists():
            try:
                content = state_path.read_text(encoding="utf-8")
                if content.strip():
                    file_exists_and_non_empty = True
            except Exception:
                file_exists_and_non_empty = True

        if file_exists_and_non_empty and not overwrite and not dry_run:
            if json_mode:
                print(json.dumps({
                    "error": "File already exists and is not empty",
                    "path": str(state_path.resolve())
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка: Файл состояния уже существует и не пуст по пути '{state_path}'. Используйте --overwrite для перезаписи.", file=sys.stderr)
            return 1

        # Формируем структуру состояния
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace("+00:00", "Z")
        state_data = {
            "schema_version": "1.0.0",
            "status": "initialized",
            "generated_at": timestamp,
            "resources": {
                "supabase_project_name": plan.supabase_project_name,
                "supabase_organization": plan.supabase_organization,
                "render_web_service_name": plan.render_web_service_name,
                "render_environment_group": plan.render_environment_group,
                "webhook_target_url": plan.webhook_target_url
            },
            "steps_skeleton": [stage["stage"] for stage in plan.stages],
            "applied_steps": []
        }

        if dry_run:
            if json_mode:
                print(json.dumps({
                    "dry_run": True,
                    "will_create": True,
                    "path": str(state_path),
                    "state": state_data
                }, indent=2, ensure_ascii=False))
            else:
                print("=== ADR Bootstrap State Init (DRY-RUN) ===")
                print(f"Путь к файлу: {state_path}")
                print("Файл состояния был бы инициализирован со следующими данными:")
                print(json.dumps(state_data, indent=2, ensure_ascii=False))
                print("=" * 42)
            return 0

        # Запись в файл
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            if json_mode:
                print(json.dumps({
                    "error": f"Failed to write file: {str(e)}",
                    "path": str(state_path)
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка при записи файла состояния: {e}", file=sys.stderr)
            return 1

        if json_mode:
            print(json.dumps({
                "success": True,
                "path": str(state_path),
                "state": state_data
            }, indent=2, ensure_ascii=False))
        else:
            print("=== ADR Bootstrap State Init ===")
            print(f"Файл состояния успешно инициализирован по пути: {state_path}")
            print(f"Статус: {state_data['status']}")
            print(f"Имя проекта Supabase: {state_data['resources']['supabase_project_name']}")
            print(f"Имя сервиса Render: {state_data['resources']['render_web_service_name']}")
            print("=" * 32)
        return 0

    elif show:
        if not state_path.exists():
            if json_mode:
                print(json.dumps({
                    "error": "State file not found",
                    "path": str(state_path)
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка: Файл состояния не найден по пути '{state_path}'. Выполните --init сначала.", file=sys.stderr)
            return 1

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except Exception as e:
            if json_mode:
                print(json.dumps({
                    "error": f"Failed to read file: {str(e)}",
                    "path": str(state_path)
                }, indent=2, ensure_ascii=False), file=sys.stderr)
            else:
                print(f"Ошибка при чтении файла состояния: {e}", file=sys.stderr)
            return 1

        if json_mode:
            print(json.dumps(state_data, indent=2, ensure_ascii=False))
        else:
            print("=== ADR Bootstrap State Show ===")
            print(f"Путь к файлу:      {state_path}")
            print(f"Версия схемы:      {state_data.get('schema_version', 'unknown')}")
            print(f"Статус:            {state_data.get('status', 'unknown')}")
            print(f"Создан в:          {state_data.get('generated_at', 'unknown')}")
            print("Ресурсы:")
            resources = state_data.get("resources", {})
            print(f"  - Supabase Project:  {resources.get('supabase_project_name', 'n/a')}")
            print(f"  - Supabase Org:      {resources.get('supabase_organization', 'n/a')}")
            print(f"  - Render Service:    {resources.get('render_web_service_name', 'n/a')}")
            print(f"  - Render Env Group:  {resources.get('render_environment_group', 'n/a')}")
            print(f"  - Webhook URL:       {resources.get('webhook_target_url', 'n/a')}")
            print("Скелет шагов:")
            steps_skeleton = state_data.get("steps_skeleton", [])
            if not steps_skeleton:
                print("  (нет скелета шагов)")
            else:
                for step in steps_skeleton:
                    print(f"  - {step}")
            print("Примененные шаги:")
            applied_steps = state_data.get("applied_steps", [])
            if not applied_steps:
                print("  (нет примененных шагов)")
            else:
                for step in applied_steps:
                    print(f"  - {step}")
            print("=" * 32)
        return 0

    return 1
