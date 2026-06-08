import json
import os
import sys
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
    HumanApprovalBoundaryStep,
    BootstrapState,
)

def run_apply(dry_run: bool, json_mode: bool, preflight: bool = False, read_only: bool = False) -> int:
    """Выполняет сухой расчет (dry-run), проверку готовности (preflight) или применение изменений (apply)."""
    if preflight:
        chk_py = check_python()
        chk_uv = check_uv()
        chk_docker = check_docker()
        chk_sb = check_supabase()
        chk_render = check_render()
        has_fail = chk_py["status"] == "FAIL" or chk_uv["status"] == "FAIL"
        has_optional_fail = any(chk["status"] == "FAIL" for chk in (chk_docker, chk_sb, chk_render))

        plan = generate_bootstrap_plan()

        if has_fail:
            msg_cli = "Критические CLI инструменты (Python >= 3.13 или uv) не найдены. См. 'bootstrap doctor' для подробностей."
        elif has_optional_fail:
            msg_cli = "Опциональные CLI инструменты отсутствуют (допускается для offline-пути). См. 'bootstrap doctor' для подробностей."
        else:
            msg_cli = "Все CLI инструменты доступны"

        step_cli = ReadOnlyExternalCheckStep(
            step_id="cli_tools",
            name="Проверка наличия и версий CLI инструментов",
            status="blocked" if has_fail else "ready",
            message=msg_cli,
            details={
                "python": {"present": chk_py["status"] == "OK", "version_info": chk_py["message"]},
                "uv": {"present": chk_uv["status"] == "OK", "version_info": chk_uv["message"]},
                "docker": {"present": chk_docker["status"] in ("OK", "WARN"), "version_info": chk_docker["message"]},
                "supabase": {"present": chk_sb["status"] == "OK", "version_info": chk_sb["message"]},
                "render": {"present": chk_render["status"] == "OK", "version_info": chk_render["message"]}
            }
        )

        auth_env_details = {
            "supabase_access_token_present": bool(os.environ.get("SUPABASE_ACCESS_TOKEN")),
            "render_api_key_present": bool(os.environ.get("RENDER_API_KEY")),
            "telegram_bot_token_present": bool(os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")),
        }

        step_auth = OfflineDryRunStep(
            step_id="auth_presence",
            name="Наличие токенов авторизации",
            status="ready",
            message="Проверено наличие необходимых токенов в окружении (без вывода значений)",
            details=auth_env_details
        )

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

        step_supabase = FutureLiveMutationStep(
            step_id="supabase_mutation",
            name="Применение изменений в Supabase (создание проекта и миграции)",
            status="requires_approval",
            message="Будущее создание проекта Supabase и применение миграций базы данных (требует подтверждения)",
            details={"actions": plan.stages[0]["actions"]}
        )

        step_render = FutureLiveMutationStep(
            step_id="render_mutation",
            name="Применение изменений в Render (веб-сервис и группа окружения)",
            status="requires_approval",
            message="Будущее создание веб-сервиса Render и группы окружения (требует подтверждения)",
            details={"actions": plan.stages[1]["actions"]}
        )

        step_telegram = FutureLiveMutationStep(
            step_id="telegram_mutation",
            name="Настройка Telegram бота (вебхук и команды)",
            status="requires_approval",
            message="Будущая установка вебхука Telegram и регистрация команд (требует подтверждения)",
            details={"actions": plan.stages[2]["actions"]}
        )

        step_smoke = FutureLiveMutationStep(
            step_id="smoke_test_mutation",
            name="Проверка работоспособности (Smoke Test)",
            status="requires_approval",
            message="Будущая отправка тестовых запросов для валидации (требует подтверждения)",
            details={"actions": plan.stages[3]["actions"]}
        )

        step_gate = HumanApprovalBoundaryStep(
            step_id="live_apply_gate",
            name="Explicit Approval Gate for Live Apply",
            status="blocked",
            message="Будущее реальное применение изменений (live apply) требует отдельного явного подтверждения и в данный момент не реализовано."
        )

        steps = [
            step_cli,
            step_auth,
            step_targets,
            step_supabase,
            step_render,
            step_telegram,
            step_smoke,
            step_gate
        ]

        state = BootstrapState(
            dry_run=True,
            message="Выполнены preflight проверки перед будущим live apply. Изменения в облачных ресурсах не производились.",
            steps=steps,
            metadata={
                "read_only": True,
                "preflight": True,
                "explicit_next_gate": "future live apply requires separate approval and is not implemented"
            }
        )

        if json_mode:
            print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("=== ADR Bootstrap Apply Preflight (READ-ONLY) ===")
            print("Внимание: Выполняются preflight проверки готовности. Никаких изменений в реальной инфраструктуре не производится.")
            print("Ссылка на полную диагностику: 'bootstrap doctor' or 'bootstrap checks'.")
            print()

            for idx, step in enumerate(state.steps, 1):
                print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
                print(f"   Сообщение: {step.message}")
                if step.step_id == "cli_tools":
                    for tool, info in step.details.items():
                        present_str = "доступен" if info["present"] else "НЕ доступен"
                        print(f"   - {tool:<10}: {present_str} ({info['version_info']})")
                elif step.step_id == "auth_presence":
                    for env_var, present in step.details.items():
                        present_str = "присутствует" if present else "отсутствует"
                        print(f"   - {env_var:<30}: {present_str}")
                elif step.step_id == "planned_targets":
                    for key, val in step.details.items():
                        print(f"   - {key:<26}: {val}")
                elif "actions" in step.details:
                    for action in step.details["actions"]:
                        print(f"   [ ] {action}")
                print()

            print("-" * 50)
            print("GATE: Future live apply requires separate approval and is not implemented.")
            print("=" * 38)

        return 1 if has_fail else 0

    if not dry_run:
        print("Ошибка: На текущем этапе поддерживается только сухой запуск (--dry-run).", file=sys.stderr)
        return 1

    plan = generate_bootstrap_plan()

    steps = [
        FutureLiveMutationStep(
            step_id="supabase",
            name="Настройка Supabase: проект и схема данных",
            status="mutation_prevented",
            message="Создание проекта Supabase и применение миграций базы данных заблокировано в dry-run",
            details={"actions": plan.stages[0]["actions"]}
        ),
        FutureLiveMutationStep(
            step_id="render",
            name="Настройка Render: веб-сервис и группа окружения",
            status="mutation_prevented",
            message="Создание веб-сервиса Render и группы окружения заблокировано в dry-run",
            details={"actions": plan.stages[1]["actions"]}
        ),
        FutureLiveMutationStep(
            step_id="telegram",
            name="Настройка Telegram: вебхук и команды бота",
            status="mutation_prevented",
            message="Установка вебхука Telegram заблокирована в dry-run",
            details={"actions": plan.stages[2]["actions"]}
        ),
        FutureLiveMutationStep(
            step_id="smoke_test",
            name="Проверка работоспособности (Runtime Smoke Test)",
            status="mutation_prevented",
            message="Выполнение smoke-тестов заблокировано в dry-run",
            details={"actions": plan.stages[3]["actions"]}
        ),
        OfflineDryRunStep(
            step_id="state_policy",
            name="Локальное состояние (Local Ignored State File Policy)",
            status="skipped",
            message="Сохранение локального файла состояния пропущено в dry-run",
            details={"actions": plan.stages[4]["actions"]}
        ),
        OfflineDryRunStep(
            step_id="rollback_caveat",
            name="Политика отката изменений (Rollback/Cleanup Caveat)",
            status="skipped",
            message="Автоматический откат не требуется в dry-run",
            details={"actions": plan.stages[5]["actions"]}
        ),
    ]

    state = BootstrapState(
        dry_run=True,
        message="Это сухой запуск (dry-run). Изменения в облачных ресурсах не производились.",
        steps=steps,
        metadata={
            "resources": {
                "supabase_project_name": plan.supabase_project_name,
                "supabase_organization": plan.supabase_organization,
                "render_web_service_name": plan.render_web_service_name,
                "render_environment_group": plan.render_environment_group
            }
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Apply (DRY-RUN) ===")
        print("Внимание: Выполняется сухой запуск. Никаких изменений в реальной инфраструктуре не производится.")
        print()

        for idx, step in enumerate(state.steps, 1):
            print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
            print(f"   Сообщение: {step.message}")
            if "actions" in step.details:
                for action in step.details["actions"]:
                    print(f"   [ ] {action}")
            print()

        print("-" * 50)
        print("Для выполнения реального развертывания потребуется отдельное подтверждение (live approval),")
        print("которое сейчас заблокировано на уровне кода.")
        print("=" * 38)

    return 0
