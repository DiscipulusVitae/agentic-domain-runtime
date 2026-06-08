import json
import sys
from ..plan import generate_bootstrap_plan
from ..models import (
    ReadOnlyExternalCheckStep,
    FutureLiveMutationStep,
    BootstrapState,
)

def run_smoke(dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой запуск smoke-тестов (dry-run)."""
    if not dry_run:
        print("Ошибка: На текущем этапе поддерживается только сухой запуск (--dry-run).", file=sys.stderr)
        return 1

    plan = generate_bootstrap_plan()

    cloud_health_url = plan.webhook_target_url.replace("/telegram-webhook", "/health")
    local_health_url = "http://127.0.0.1:8765/health"

    steps = [
        ReadOnlyExternalCheckStep(
            step_id="local_runtime_health",
            name="Проверка локального рантайма (/health)",
            status="skipped",
            message="Запрос к локальному рантайму пропущен в dry-run",
            details={
                "target_url": local_health_url,
                "expected_status": 200
            }
        ),
        ReadOnlyExternalCheckStep(
            step_id="cloud_runtime_health",
            name="Проверка облачного рантайма (/health)",
            status="skipped",
            message="Запрос к облачному рантайму пропущен в dry-run",
            details={
                "target_url": cloud_health_url,
                "expected_status": 200
            }
        ),
        FutureLiveMutationStep(
            step_id="synthetic_telegram_webhook",
            name="Синтетический запрос к Telegram вебхуку с валидной нагрузкой",
            status="mutation_prevented",
            message="Запрос к вебхуку заблокирован в dry-run",
            details={
                "target_url": plan.webhook_target_url,
                "expected_status": 200
            }
        ),
        FutureLiveMutationStep(
            step_id="controlled_invalid_payload",
            name="Контролируемый запрос с невалидной нагрузкой (проверка возврата 400)",
            status="mutation_prevented",
            message="Некорректный запрос к вебхуку заблокирован в dry-run",
            details={
                "target_url": plan.webhook_target_url,
                "expected_status": 400
            }
        )
    ]

    state = BootstrapState(
        dry_run=True,
        message="Это сухой запуск smoke-тестов (dry-run). Никакие внешние запросы не выполнялись.",
        steps=steps,
        metadata={
            "final_status_classification": {
                "success": "Все проверки вернули ожидаемые ответы (health и webhook отвечают корректно)",
                "degraded_webhook": "Рантайм доступен (/health отвечает 200), но вебхук возвращает ошибки или недоступен",
                "failure": "Рантайм полностью недоступен (/health возвращает ошибку или тайм-аут)"
            }
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Smoke (DRY-RUN) ===")
        print("Внимание: Это read-only симуляция smoke-тестов. Никакие внешние запросы не выполнялись.")
        print()
        print("Планируемые проверки после развертывания:")

        for idx, step in enumerate(state.steps, 1):
            print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
            print(f"   Цель: {step.message}")
            print(f"   Адрес: {step.details.get('target_url')}")
            print(f"   Ожидаемый статус: {step.details.get('expected_status')}")
            print()

        print("Классификация итогового статуса (Final Status Classification):")
        for key, desc in state.metadata["final_status_classification"].items():
            print(f"  - {key.upper()}: {desc}")
        print()
        print("Никакие секреты не выводятся, реальные вызовы не производятся.")
        print("=" * 38)

    return 0
