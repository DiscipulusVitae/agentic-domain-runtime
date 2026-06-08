import json
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
    OfflineDryRunStep,
    ReadOnlyExternalCheckStep,
    HumanApprovalBoundaryStep,
    FutureLiveMutationStep,
    BootstrapState,
)

def run_install(dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой запуск мастера установки (install wizard)."""
    if not dry_run:
        print("Ошибка: На текущем этапе поддерживается только сухой запуск (--dry-run).", file=sys.stderr)
        return 1

    checks = {}
    checks["python"] = check_python()
    checks["uv"] = check_uv()
    checks["docker"] = check_docker()
    checks["supabase"] = check_supabase()
    checks["render"] = check_render()

    plan = generate_bootstrap_plan()

    cloud_health_url = plan.webhook_target_url.replace("/telegram-webhook", "/health")
    local_health_url = "http://127.0.0.1:8765/health"
    smoke_checks = [
        {
            "name": "local_runtime_health",
            "description": "Проверка локального рантайма (/health)",
            "target_url": local_health_url,
            "expected_status": 200
        },
        {
            "name": "cloud_runtime_health",
            "description": "Проверка облачного рантайма (/health)",
            "target_url": cloud_health_url,
            "expected_status": 200
        },
        {
            "name": "synthetic_telegram_webhook",
            "description": "Синтетический запрос к Telegram вебхуку с валидной нагрузкой",
            "target_url": plan.webhook_target_url,
            "expected_status": 200
        },
        {
            "name": "controlled_invalid_payload",
            "description": "Контролируемый запрос с невалидной нагрузкой (проверка возврата 400)",
            "target_url": plan.webhook_target_url,
            "expected_status": 400
        }
    ]

    doctor_failed = any(checks[name]["status"] == "FAIL" for name in ("python", "uv"))
    has_optional_fail = any(checks[name]["status"] == "FAIL" for name in ("docker", "supabase", "render"))

    steps = [
        OfflineDryRunStep(
            step_id="upfront_checklist",
            name="Подготовительный чек-лист перед установкой",
            status="ready",
            message="Чек-лист подготовки перед установкой",
            details={
                "prerequisites": [
                    "Docker CLI & Daemon",
                    "uv package manager",
                    "Supabase CLI",
                    "Render CLI",
                    "Telegram аккаунт и доступ к @BotFather"
                ]
            }
        ),
        OfflineDryRunStep(
            step_id="doctor_prerequisites",
            name="Проверка локального окружения",
            status="blocked" if doctor_failed else "ready",
            message=(
                "Обнаружены критические проблемы в локальном окружении" if doctor_failed else
                "Критические проблемы не обнаружены. Опциональные инструменты отсутствуют (допустимо для offline-пути)." if has_optional_fail else
                "Критические проблемы не обнаружены"
            ),
            details={"checks": checks}
        ),
        ReadOnlyExternalCheckStep(
            step_id="supabase_auth_guidance",
            name="Supabase авторизация",
            status="ready",
            message="Supabase авторизация: используйте 'supabase login' или SUPABASE_ACCESS_TOKEN"
        ),
        ReadOnlyExternalCheckStep(
            step_id="render_auth_guidance",
            name="Render авторизация",
            status="ready",
            message="Render авторизация: используйте 'render login' или RENDER_API_KEY"
        ),
        ReadOnlyExternalCheckStep(
            step_id="telegram_botfather_step",
            name="Telegram Bot Setup",
            status="ready",
            message="Telegram Bot Setup: создание бота у @BotFather и сохранение токена без вывода секретов"
        ),
        OfflineDryRunStep(
            step_id="plan_preview",
            name="Превью плана развертывания",
            status="ready",
            message="Превью плана развертывания",
            details={
                "resources": {
                    "supabase_project_name": plan.supabase_project_name,
                    "supabase_organization": plan.supabase_organization,
                    "render_web_service_name": plan.render_web_service_name,
                    "render_environment_group": plan.render_environment_group
                },
                "required_auth": plan.required_auth,
                "planned_env_vars": plan.planned_env_vars,
                "webhook_target_url": plan.webhook_target_url
            }
        ),
        HumanApprovalBoundaryStep(
            step_id="explicit_approval_boundary",
            name="Граница явного подтверждения пользователя перед развертыванием",
            status="requires_approval",
            message="Требуется явное подтверждение пользователя для выполнения live mutation. В dry-run одобрено автоматически."
        ),
        FutureLiveMutationStep(
            step_id="apply_stage",
            name="Сухой запуск применения конфигурации",
            status="mutation_prevented",
            message="Применение конфигурации заблокировано в dry-run",
            details={"stages": plan.stages}
        ),
        FutureLiveMutationStep(
            step_id="smoke_stage",
            name="Сухой запуск проверки работоспособности",
            status="mutation_prevented",
            message="Проверка работоспособности заблокирована в dry-run",
            details={"checks": smoke_checks}
        ),
        OfflineDryRunStep(
            step_id="local_ignored_state_policy",
            name="Политика локального состояния",
            status="skipped",
            message="Запись метаданных в '.bootstrap-state.json' пропущена в dry-run"
        )
    ]

    state = BootstrapState(
        dry_run=True,
        message="Это сухой запуск мастера установки (dry-run). Изменения не вносились.",
        steps=steps,
        metadata={
            "read_only_checks_relationship": {
                "command": "bootstrap checks --read-only",
                "description": "Используйте эту команду для отдельного запуска read-only readiness проверок без симуляции установки."
            }
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Install Wizard (DRY-RUN) ===")
        print("Внимание: Выполняется сухой запуск мастера установки. Реальные изменения не вносятся.")
        print()

        print("1. Подготовительный чек-лист (Upfront Checklist):")
        for prereq in steps[0].details["prerequisites"]:
            print(f"   [ ] {prereq}")
        print()

        print("2. Проверка локальных зависимостей (Doctor Prerequisites):")
        for name, info in checks.items():
            print(f"   - {name:<10}: [{info['status']}] {info['message']}")
            if info["status"] == "FAIL" and "hint" in info:
                print(f"                Подсказка: {info['hint']}")
                if info.get("action"):
                    print(f"                Команда:   {info['action']}")
        print()

        print("3. Руководство по авторизации Supabase (Supabase Auth Guidance):")
        print(f"   - {steps[2].message}")
        print()

        print("4. Руководство по авторизации Render (Render Auth Guidance):")
        print(f"   - {steps[3].message}")
        print()

        print("5. Регистрация бота в Telegram (Telegram Bot Setup):")
        print(f"   - {steps[4].message}")
        print()

        print("6. Превью плана развертывания (Plan Preview):")
        preview_details = steps[5].details
        print(f"   - Supabase Project Name:      {preview_details['resources']['supabase_project_name']}")
        print(f"   - Supabase Database Org:      {preview_details['resources']['supabase_organization']}")
        print(f"   - Render Web Service Name:    {preview_details['resources']['render_web_service_name']}")
        print(f"   - Render Environment Group:   {preview_details['resources']['render_environment_group']}")
        print("   - Необходимая авторизация:")
        for auth in preview_details["required_auth"]:
            print(f"     * {auth}")
        print("   - Планируемые переменные окружения:")
        for var in preview_details["planned_env_vars"]:
            print(f"     * {var}")
        print()

        print("7. Граница явного подтверждения (Explicit Approval Boundary):")
        print(f"   - {steps[6].message}")
        print()

        print("8. Применение конфигурации (Apply Stage):")
        for idx, stage in enumerate(plan.stages, 1):
            print(f"   Шаг {idx}. {stage['description']} [{stage['status'].upper()}]")
            for action in stage['actions']:
                print(f"     [ ] {action}")
        print()

        print("9. Проверка работоспособности (Smoke Stage):")
        print("   Планируемые проверки после развертывания:")
        print(f"   - Локальный рантайм: GET {local_health_url}")
        print(f"   - Облачный рантайм:  GET {cloud_health_url}")
        print(f"   - Webhook Telegram:  POST {plan.webhook_target_url} (с валидной нагрузкой)")
        print(f"   - Валидация ошибок:  POST {plan.webhook_target_url} (с невалидной нагрузкой)")
        print()

        print("10. Политика локального состояния (Local Ignored State Policy):")
        print(f"    - {steps[9].message}")
        print()
        print("=" * 46)

    return 0
