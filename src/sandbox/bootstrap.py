"""
Реализация команд doctor и plan для процесса bootstrap.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def check_command(args: list[str]) -> tuple[bool, str]:
    """Запускает системную команду и возвращает успешность и её вывод."""
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return True, res.stdout.strip()
        else:
            return False, res.stderr.strip() or res.stdout.strip()
    except FileNotFoundError:
        return False, "Команда не найдена"
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания команды"
    except Exception as e:
        return False, str(e)


def check_python() -> tuple[str, str]:
    """Проверяет соответствие версии Python требованиям (>= 3.13)."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 13):
        return "OK", f"Python версия {version} (требуется >= 3.13)"
    else:
        return "FAIL", f"Python версия {version} не удовлетворяет требованиям (требуется >= 3.13)"


def _get_version_summary(text: str) -> str:
    """Возвращает первую непустую строку из текста в качестве краткого описания версии."""
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped:
            return line_stripped
    return ""


def check_uv() -> tuple[str, str]:
    """Проверяет доступность uv."""
    ok, out = check_command(["uv", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return "OK", f"uv доступен ({version_summary})"
    if out:
        return "FAIL", f"uv не найден или не отвечает ({out})"
    return "FAIL", "uv не найден или не отвечает"


def check_docker() -> tuple[str, str]:
    """Проверяет доступность Docker CLI и запущен ли демон."""
    cli_ok, cli_out = check_command(["docker", "--version"])
    if not cli_ok:
        return "FAIL", f"Docker CLI не установлен или недоступен ({cli_out})"

    daemon_ok, daemon_out = check_command(["docker", "info"])
    if daemon_ok:
        return "OK", "Docker daemon запущен и готов"
    else:
        return "WARN", "Docker CLI доступен, но Docker daemon не запущен"


def check_supabase() -> tuple[str, str]:
    """Проверяет доступность Supabase CLI."""
    ok, out = check_command(["supabase", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return "OK", f"Supabase CLI доступен ({version_summary})"
    if out:
        return "FAIL", f"Supabase CLI не найден или не отвечает ({out})"
    return "FAIL", "Supabase CLI не найден или не отвечает"


def check_render() -> tuple[str, str]:
    """Проверяет доступность Render CLI."""
    ok, out = check_command(["render", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return "OK", f"Render CLI доступен ({version_summary})"

    ok_help, out_help = check_command(["render", "help"])
    if ok_help:
        return "OK", "Render CLI доступен (render --version недоступна, но render help работает)"

    err_details = out or out_help
    if err_details:
        return "FAIL", f"Render CLI не найден или не отвечает ({err_details})"
    return "FAIL", "Render CLI не найден или не отвечает"


def run_doctor(json_mode: bool) -> int:
    """Выполняет проверку локальных зависимостей (doctor)."""
    checks = {}

    status_py, msg_py = check_python()
    checks["python"] = {"status": status_py, "message": msg_py}

    status_uv, msg_uv = check_uv()
    checks["uv"] = {"status": status_uv, "message": msg_uv}

    status_docker, msg_docker = check_docker()
    checks["docker"] = {"status": status_docker, "message": msg_docker}

    status_sb, msg_sb = check_supabase()
    checks["supabase"] = {"status": status_sb, "message": msg_sb}

    status_render, msg_render = check_render()
    checks["render"] = {"status": status_render, "message": msg_render}

    has_fail = any(info["status"] == "FAIL" for info in checks.values())

    if json_mode:
        output = {
            "status": "failed" if has_fail else "success",
            "checks": checks
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Doctor ===")
        print("Проверка локального окружения:")
        for name, info in checks.items():
            status_str = f"[{info['status']}]"
            print(f"  {status_str:<8} {name:<10}: {info['message']}")
        print("=" * 28)

        if has_fail:
            print("\nОшибка: Обнаружены критические проблемы в локальном окружении.")
        else:
            print("\nЛокальное окружение готово к установке.")

    return 1 if has_fail else 0


class BootstrapStep:
    """Базовый класс для шагов процесса инициализации (bootstrap)."""
    boundary: str = ""

    def __init__(self, step_id: str, name: str, status: str, message: str, details: dict = None):
        self.step_id = step_id
        self.name = name
        # status: ready, blocked, skipped, requires_approval, mutation_prevented
        self.status = status
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status,
            "boundary": self.boundary,
            "message": self.message,
            "details": self.details,
        }


class OfflineDryRunStep(BootstrapStep):
    """Шаг, выполняемый полностью локально без внешних запросов."""
    boundary: str = "offline_dry_run"


class ReadOnlyExternalCheckStep(BootstrapStep):
    """Шаг, выполняющий внешние read-only проверки (например, проверка прав CLI или доступности API)."""
    boundary: str = "read_only_external_checks"


class FutureLiveMutationStep(BootstrapStep):
    """Шаг, выполняющий мутирующие действия в облаке (создание ресурсов, вебхуков)."""
    boundary: str = "future_live_mutation"


class HumanApprovalBoundaryStep(BootstrapStep):
    """Шаг, требующий явного подтверждения человека (human approval)."""
    boundary: str = "human_approval_boundary"


class BootstrapState:
    """Единая модель состояния процесса инициализации (bootstrap state)."""
    def __init__(self, dry_run: bool, message: str, steps: list[BootstrapStep], metadata: dict = None):
        self.dry_run = dry_run
        self.message = message
        self.steps = steps
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "message": self.message,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }


class BootstrapPlanModel:
    """Модель планирования развертывания (bootstrap plan)."""
    def __init__(
        self,
        suffix: str,
        supabase_project_name: str,
        supabase_organization: str,
        render_web_service_name: str,
        render_environment_group: str,
        webhook_target_url: str,
        required_auth: list[str],
        planned_env_vars: list[str],
        stages: list[dict],
    ):
        self.suffix = suffix
        self.supabase_project_name = supabase_project_name
        self.supabase_organization = supabase_organization
        self.render_web_service_name = render_web_service_name
        self.render_environment_group = render_environment_group
        self.webhook_target_url = webhook_target_url
        self.required_auth = required_auth
        self.planned_env_vars = planned_env_vars
        self.stages = stages


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
            "description": "Настройка Render: веб-сервис и группа окружения",
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


def run_plan(json_mode: bool) -> int:
    """Выполняет сухой расчет плана развертывания (plan)."""
    plan = generate_bootstrap_plan()

    if json_mode:
        output = {
            "dry_run": True,
            "resources": {
                "supabase_project_name": plan.supabase_project_name,
                "supabase_organization": plan.supabase_organization,
                "render_web_service_name": plan.render_web_service_name,
                "render_environment_group": plan.render_environment_group
            },
            "required_auth": plan.required_auth,
            "planned_env_vars": plan.planned_env_vars,
            "update_modes": {
                "local": "polling",
                "cloud": "webhook",
                "webhook_target_url": plan.webhook_target_url
            }
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Plan (DRY-RUN) ===")
        print("Внимание: Это read-only симуляция. Никакие ресурсы в облаке не будут созданы.")
        print()
        print("1. Превью имен ресурсов:")
        print(f"   - Supabase Project Name:      {plan.supabase_project_name}")
        print(f"   - Supabase Database Org:      {plan.supabase_organization}")
        print(f"   - Render Web Service Name:    {plan.render_web_service_name}")
        print(f"   - Render Environment Group:   {plan.render_environment_group}")
        print()
        print("2. Чек-лист авторизации:")
        for auth in plan.required_auth:
            print(f"   [ ] {auth}")
        print()
        print("3. Планируемые переменные окружения (только имена):")
        for var in plan.planned_env_vars:
            print(f"   - {var}")
        print()
        print("4. Политика доставки обновлений (Webhook/Polling):")
        print("   - Локальная разработка: Polling (TELEGRAM_UPDATE_MODE=polling)")
        print("   - Облако (Render): Webhook (TELEGRAM_UPDATE_MODE=webhook)")
        print(f"     Адрес вебхука: {plan.webhook_target_url}")
        print("=" * 36)

    return 0


def run_apply(dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой расчет (dry-run) или применение изменений развертывания (apply)."""
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


def run_install(dry_run: bool, json_mode: bool) -> int:
    """Выполняет сухой запуск мастера установки (install wizard)."""
    if not dry_run:
        print("Ошибка: На текущем этапе поддерживается только сухой запуск (--dry-run).", file=sys.stderr)
        return 1

    checks = {}
    status_py, msg_py = check_python()
    checks["python"] = {"status": status_py, "message": msg_py}

    status_uv, msg_uv = check_uv()
    checks["uv"] = {"status": status_uv, "message": msg_uv}

    status_docker, msg_docker = check_docker()
    checks["docker"] = {"status": status_docker, "message": msg_docker}

    status_sb, msg_sb = check_supabase()
    checks["supabase"] = {"status": status_sb, "message": msg_sb}

    status_render, msg_render = check_render()
    checks["render"] = {"status": status_render, "message": msg_render}

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

    doctor_failed = any(info["status"] == "FAIL" for info in checks.values())

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
            message="Критические проблемы не обнаружены" if not doctor_failed else "Обнаружены критические проблемы в локальном окружении",
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
        steps=steps
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
