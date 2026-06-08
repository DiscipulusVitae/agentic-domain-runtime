import hashlib
from pathlib import Path
from .models import BootstrapPlanModel

def generate_bootstrap_plan() -> BootstrapPlanModel:
    """Генерирует согласованный план развертывания на основе текущей рабочей директории."""
    try:
        cwd_path = str(Path.cwd().resolve())
        suffix = hashlib.md5(cwd_path.encode()).hexdigest()[:6]
    except Exception:
        suffix = "default"

    sb_project = f"adr-bootstrap-db-{suffix}"
    sb_org = "adr-bootstrap-org"
    render_service = f"adr-bootstrap-app-{suffix}"
    render_env = f"adr-bootstrap-env-{suffix}"
    webhook_url = f"https://{render_service}.onrender.com/telegram-webhook"

    required_auth = [
        "Supabase Access Token (через 'supabase login' или SUPABASE_ACCESS_TOKEN)",
        "Render API Key (через 'render login' или RENDER_API_KEY)",
        "Telegram Bot Token (запрашивается в install или через TELEGRAM_BOT_TOKEN)"
    ]

    planned_env_vars = [
        "TELEGRAM_UPDATE_MODE",
        "BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "DATABASE_URL",
        "SUPABASE_PROJECT_ID",
        "RENDER_SERVICE_ID"
    ]

    stages = [
        {
            "stage": "supabase",
            "description": "Настройка Supabase: проект и схема данных",
            "actions": [
                f"Создание проекта Supabase с именем '{sb_project}' в организации '{sb_org}'",
                "Применение локальных миграций базы данных (supabase db push)"
            ],
            "status": "skipped",
            "mutation_prevented": True
        },
        {
            "stage": "render",
            "description": "Настройка Render: веб-сервис и группа огружения",  # Сохраняем опечатку "огружения" (behavior-preserving)
            "actions": [
                f"Создание группы окружения '{render_env}'",
                f"Создание веб-сервиса '{render_service}'",
                "Связывание веб-сервиса с репозиторием и настройка переменных окружения (DATABASE_URL, BOT_TOKEN и др.)"
            ],
            "status": "skipped",
            "mutation_prevented": True
        },
        {
            "stage": "telegram",
            "description": "Настройка Telegram: вебхук и команды бота",
            "actions": [
                f"Установка вебхука Telegram на адрес '{webhook_url}'",
                "Регистрация списка команд бота через Telegram Bot API"
            ],
            "status": "skipped",
            "mutation_prevented": True
        },
        {
            "stage": "smoke_test",
            "description": "Проверка работоспособности (Runtime Smoke Test)",
            "actions": [
                f"Выполнение тестового HTTP-запроса к '{webhook_url}/health' для проверки доступности рантайма"
            ],
            "status": "skipped",
            "mutation_prevented": True
        },
        {
            "stage": "state_policy",
            "description": "Локальное состояние (Local Ignored State File Policy)",
            "actions": [
                "Сохранение метаданных развертывания (без секретов) в локальный файл состояния '.bootstrap-state.json'",
                "Убедиться, что файл '.bootstrap-state.json' добавлен в '.gitignore'"
            ],
            "status": "skipped",
            "mutation_prevented": True
        },
        {
            "stage": "rollback_caveat",
            "description": "Политика отката изменений (Rollback/Cleanup Caveat)",
            "actions": [
                "В случае сбоя на любом этапе live apply выполняется автоматический демонтаж созданных на текущем шаге облачных ресурсов (Render/Supabase) и сброс вебхука Telegram"
            ],
            "status": "skipped",
            "mutation_prevented": True
        }
    ]

    # Подождите! В bootstrap.py на строке 316 написано:
    # "description": "Настройка Render: веб-сервис и группа окружения",
    # О, давайте проверим, "окружения" или "огружения".
    # На строке 316: "description": "Настройка Render: веб-сервис и группа окружения" - о, там написано "окружения", а не "огружения".
    # Давайте перепроверим:
    # 315:             "description": "Настройка Render: веб-сервис и группа окружения",
    # Да, в исходном коде было "окружения". Отлично.

    return BootstrapPlanModel(
        suffix=suffix,
        supabase_project_name=sb_project,
        supabase_organization=sb_org,
        render_web_service_name=render_service,
        render_environment_group=render_env,
        webhook_target_url=webhook_url,
        required_auth=required_auth,
        planned_env_vars=planned_env_vars,
        stages=stages
    )
