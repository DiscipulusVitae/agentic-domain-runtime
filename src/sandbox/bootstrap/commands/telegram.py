import json
from ..plan import generate_bootstrap_plan
from ..models import (
    OfflineDryRunStep,
    HumanApprovalBoundaryStep,
    FutureLiveMutationStep,
    BootstrapState,
)

def run_telegram_bootstrap(webhook: bool, dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой запуск (dry-run) настройки Telegram вебхука."""
    # Генерируем согласованный план развертывания
    plan = generate_bootstrap_plan()

    # Шаг 1: Руководство по BotFather
    step_botfather = HumanApprovalBoundaryStep(
        step_id="telegram_botfather_guidance",
        name="Ручная настройка бота через @BotFather (guidance only)",
        status="requires_approval",
        message="Создание Telegram-бота выполняется вручную через официального бота @BotFather.",
        details={
            "instructions": [
                "1. Откройте Telegram и найдите бота @BotFather.",
                "2. Отправьте команду /newbot и следуйте инструкциям для создания нового бота.",
                "3. Скопируйте полученный API-токен (Bot Token)."
            ]
        }
    )

    # Шаг 2: Безопасная передача токена
    step_token = OfflineDryRunStep(
        step_id="token_handoff_policy",
        name="Token Handoff Policy",
        status="ready",
        message="Передача токена осуществляется безопасным способом без сохранения в системе контроля версий или логирования.",
        details={
            "rules": [
                "Токен считывается из переменной окружения TELEGRAM_BOT_TOKEN во время исполнения.",
                "Токен никогда не сохраняется в git, не пишется в логи и не выводится в CLI-outputs.",
                "В текущем dry-run режиме токен не запрашивается и не проверяется."
            ]
        }
    )

    # Шаг 3: Спланированный URL вебхука
    step_url = OfflineDryRunStep(
        step_id="planned_webhook_url",
        name="Планируемый URL для вебхука Telegram",
        status="ready",
        message="URL вебхука автоматически планируется на основе имени сервиса в Render.",
        details={
            "webhook_target_url": plan.webhook_target_url
        }
    )

    # Шаг 4: Будущие действия с API Telegram
    step_api_actions = FutureLiveMutationStep(
        step_id="future_telegram_api_actions",
        name="Планируемые действия с Telegram API (getMe, setWebhook, регистрация команд)",
        status="mutation_prevented",
        message="Действия, требующие взаимодействия с Telegram Bot API, заблокированы в dry-run.",
        details={
            "actions": [
                "Вызов getMe для верификации токена",
                f"Вызов setWebhook с целевым URL {plan.webhook_target_url}",
                "Вызов setMyCommands для регистрации списка команд бота"
            ]
        }
    )

    # Шаг 5: Связь со smoke-тестированием вебхука
    step_smoke = OfflineDryRunStep(
        step_id="smoke_readiness_relation",
        name="Связь готовности с проверками smoke",
        status="ready",
        message="Локальная верификация готовности вебхука производится без внешних запросов к API Telegram.",
        details={
            "relation_hint": "Команда 'bootstrap smoke' выполняет синтетический POST-запрос к локальному вебхуку (runtime smoke) для проверки готовности обработчика.",
            "smoke_check_command": "bootstrap smoke --dry-run"
        }
    )

    steps = [
        step_botfather,
        step_token,
        step_url,
        step_api_actions,
        step_smoke
    ]

    state = BootstrapState(
        dry_run=True,
        message="Это сухой запуск (dry-run) настройки Telegram вебхука. Команды не выполнялись, мутации предотвращены.",
        steps=steps,
        metadata={
            "webhook": True,
            "mutation_prevented": True
        }
    )

    if json_mode:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Telegram Webhook Readiness (DRY-RUN) ===")
        print("Внимание: Это сухой запуск (dry-run) настройки Telegram вебхука. Никакие реальные запросы к API не выполнялись.")
        print("Никакие секретные ключи или токены не считывались и не выводились.")
        print()

        for idx, step in enumerate(state.steps, 1):
            print(f"{idx}. {step.name} [{step.status.upper()}] (Boundary: {step.boundary})")
            print(f"   Сообщение: {step.message}")
            if step.step_id == "telegram_botfather_guidance":
                print("   Инструкции:")
                for inst in step.details.get("instructions", []):
                    print(f"   - {inst}")
            elif step.step_id == "token_handoff_policy":
                print("   Правила:")
                for rule in step.details.get("rules", []):
                    print(f"   - {rule}")
            elif step.step_id == "planned_webhook_url":
                print(f"   Планируемый URL: {step.details.get('webhook_target_url')}")
            elif step.step_id == "future_telegram_api_actions":
                print("   Планируемые действия с API:")
                for action in step.details.get("actions", []):
                    print(f"   - {action}")
            elif step.step_id == "smoke_readiness_relation":
                print(f"   Связь со smoke: {step.details.get('relation_hint')}")
                print(f"   Команда проверки: {step.details.get('smoke_check_command')}")
            print()
        print("=" * 60)

    return 0
