import json
import os
from ..env_checks import (
    check_python,
    check_uv,
    check_docker,
    check_supabase,
    check_render,
)
from ..plan import generate_bootstrap_plan
from ..models import (
    ReadOnlyExternalCheckStep,
    OfflineDryRunStep,
    FutureLiveMutationStep,
    BootstrapState,
)

def run_checks(json_mode: bool) -> int:
    """Выполняет read-only readiness проверки окружения и авторизации."""
    checks = {}
    checks["python"] = check_python()
    checks["uv"] = check_uv()
    checks["docker"] = check_docker()
    checks["supabase"] = check_supabase()
    checks["render"] = check_render()

    has_critical_fail = any(checks[name]["status"] == "FAIL" for name in ("python", "uv"))
    has_optional_fail = any(checks[name]["status"] == "FAIL" for name in ("docker", "supabase", "render"))

    details_cli = {
        "python": {"present": checks["python"]["status"] == "OK", "version_info": checks["python"]["message"]},
        "uv": {"present": checks["uv"]["status"] == "OK", "version_info": checks["uv"]["message"]},
        "docker": {"present": checks["docker"]["status"] in ("OK", "WARN"), "version_info": checks["docker"]["message"]},
        "supabase": {"present": checks["supabase"]["status"] == "OK", "version_info": checks["supabase"]["message"]},
        "render": {"present": checks["render"]["status"] == "OK", "version_info": checks["render"]["message"]}
    }

    if has_critical_fail:
        msg_cli = "Критические CLI инструменты не найдены"
    elif has_optional_fail:
        msg_cli = "Опциональные CLI инструменты отсутствуют (допустимо для offline-пути)"
    else:
        msg_cli = "Все CLI инструменты доступны"

    step_cli = ReadOnlyExternalCheckStep(
        step_id="cli_tools",
        name="Проверка наличия и версий CLI инструментов",
        status="blocked" if has_critical_fail else "ready",
        message=msg_cli,
        details=details_cli
    )

    auth_env_details = {
        "supabase_access_token_present": bool(os.environ.get("SUPABASE_ACCESS_TOKEN")),
        "render_api_key_present": bool(os.environ.get("RENDER_API_KEY")),
        "telegram_bot_token_present": bool(os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")),
        "database_url_present": bool(os.environ.get("DATABASE_URL")),
    }

    step_auth = OfflineDryRunStep(
        step_id="auth_env_presence",
        name="Наличие авторизации и переменных окружения (без вывода значений)",
        status="ready",
        message="Проверено наличие необходимых токенов в окружении",
        details=auth_env_details
    )

    plan = generate_bootstrap_plan()
    planned_details = {
        "supabase_project_name": plan.supabase_project_name,
        "supabase_organization": plan.supabase_organization,
        "render_web_service_name": plan.render_web_service_name,
        "render_environment_group": plan.render_environment_group,
        "webhook_target_url": plan.webhook_target_url
    }

    step_targets = OfflineDryRunStep(
        step_id="planned_targets",
        name="Параметры планируемых целевых ресурсов",
        status="ready",
        message="Сгенерированы целевые имена ресурсов и URL на основе рабочей директории",
        details=planned_details
    )

    step_sb_api = FutureLiveMutationStep(
        step_id="future_supabase_api_check",
        name="Будущая проверка Supabase API (создание проекта)",
        status="mutation_prevented",
        message="Вызовы к Supabase API заблокированы в режиме read-only"
    )

    step_render_api = FutureLiveMutationStep(
        step_id="future_render_api_check",
        name="Будущая проверка Render API (создание сервиса)",
        status="mutation_prevented",
        message="Вызовы к Render API заблокированы в режиме read-only"
    )

    step_tg_api = FutureLiveMutationStep(
        step_id="future_telegram_api_check",
        name="Будущая проверка Telegram API (getMe и вебхук)",
        status="mutation_prevented",
        message="Вызовы к Telegram API заблокированы в режиме read-only"
    )

    steps = [
        step_cli,
        step_auth,
        step_targets,
        step_sb_api,
        step_render_api,
        step_tg_api
    ]

    state = BootstrapState(
        dry_run=True,
        message="Выполнены read-only readiness проверки. Ресурсы не создавались, мутации предотвращены.",
        steps=steps,
        metadata={
            "read_only": True,
            "relationship": {
                "type": "preflight_readiness_checks",
                "target_command": "bootstrap install --dry-run",
                "description": "Эта команда выполняет исключительно read-only проверки локального окружения перед процессом установки."
            }
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Checks (READ-ONLY) ===")
        print("Внимание: Это read-only проверка готовности окружения. Никакие ресурсы не создаются.")
        print()

        for idx, step in enumerate(state.steps, 1):
            print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
            print(f"   Сообщение: {step.message}")
            if step.step_id == "cli_tools":
                for tool, info in step.details.items():
                    present_str = "доступен" if info["present"] else "НЕ доступен"
                    print(f"   - {tool:<10}: {present_str} ({info['version_info']})")
            elif step.step_id == "auth_env_presence":
                for env_var, present in step.details.items():
                    present_str = "присутствует" if present else "отсутствует"
                    print(f"   - {env_var:<30}: {present_str}")
            elif step.step_id == "planned_targets":
                for key, val in step.details.items():
                    print(f"   - {key:<26}: {val}")
            print()
        print("=" * 40)

    has_critical_fail = any(checks[name]["status"] == "FAIL" for name in ("python", "uv"))
    return 1 if has_critical_fail else 0
