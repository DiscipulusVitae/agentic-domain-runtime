"""
Реализация команд doctor и plan для процесса bootstrap.
"""

import hashlib
import json
import os
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


def check_python() -> dict:
    """Проверяет соответствие версии Python требованиям (>= 3.13)."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 13):
        return {
            "status": "OK",
            "message": f"Python версия {version} (требуется >= 3.13)"
        }
    else:
        return {
            "status": "FAIL",
            "message": f"Python версия {version} не удовлетворяет требованиям (требуется >= 3.13)",
            "hint": "Установите Python версии 3.13 или выше.",
            "action": "sudo apt-get update && sudo apt-get install -y python3.13"
        }


def _get_version_summary(text: str) -> str:
    """Возвращает первую непустую строку из текста в качестве краткого описания версии."""
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped:
            return line_stripped
    return ""


def check_uv() -> dict:
    """Проверяет доступность uv."""
    ok, out = check_command(["uv", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return {
            "status": "OK",
            "message": f"uv доступен ({version_summary})"
        }
    err_details = out if out else "uv не найден или не отвечает"
    return {
        "status": "FAIL",
        "message": f"uv не найден или не отвечает ({err_details})" if out else "uv не найден или не отвечает",
        "hint": "Установите uv с помощью официального скрипта установки.",
        "action": "curl -LsSf https://astral.sh/uv/install.sh | sh"
    }


def check_docker() -> dict:
    """Проверяет доступность Docker CLI и запущен ли демон."""
    cli_ok, cli_out = check_command(["docker", "--version"])
    if not cli_ok:
        err_msg = f"Docker CLI не установлен или недоступен ({cli_out})" if cli_out else "Docker CLI не установлен или недоступен"
        return {
            "status": "FAIL",
            "message": err_msg,
            "hint": "Установите Docker Engine: https://docs.docker.com/engine/install/ubuntu/",
            "action": "sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io"
        }

    daemon_ok, daemon_out = check_command(["docker", "info"])
    if daemon_ok:
        return {
            "status": "OK",
            "message": "Docker daemon запущен и готов"
        }
    else:
        return {
            "status": "WARN",
            "message": "Docker CLI доступен, но Docker daemon не запущен",
            "hint": "Запустите службу docker с помощью systemctl.",
            "action": "sudo systemctl start docker"
        }


def check_supabase() -> dict:
    """Проверяет доступность Supabase CLI."""
    ok, out = check_command(["supabase", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return {
            "status": "OK",
            "message": f"Supabase CLI доступен ({version_summary})"
        }
    err_details = out if out else "Supabase CLI не найден или не отвечает"
    return {
        "status": "FAIL",
        "message": f"Supabase CLI не найден или не отвечает ({err_details})" if out else "Supabase CLI не найден или не отвечает",
        "hint": "Установите Supabase CLI через npm или скачайте с GitHub: https://github.com/supabase/cli",
        "action": "npm install -g supabase"
    }


def check_render() -> dict:
    """Проверяет доступность Render CLI."""
    ok, out = check_command(["render", "--version"])
    if ok:
        version_summary = _get_version_summary(out)
        return {
            "status": "OK",
            "message": f"Render CLI доступен ({version_summary})"
        }

    ok_help, out_help = check_command(["render", "help"])
    if ok_help:
        return {
            "status": "OK",
            "message": "Render CLI доступен (render --version недоступна, но render help работает)"
        }

    err_details = out or out_help
    err_msg = f"Render CLI не найден или не отвечает ({err_details})" if err_details else "Render CLI не найден или не отвечает"
    return {
        "status": "FAIL",
        "message": err_msg,
        "hint": "Установите Render CLI через npm.",
        "action": "npm install -g @renderinc/cli"
    }


def run_doctor(json_mode: bool) -> int:
    """Выполняет проверку локальных зависимостей (doctor)."""
    checks = {}

    checks["python"] = check_python()
    checks["uv"] = check_uv()
    checks["docker"] = check_docker()
    checks["supabase"] = check_supabase()
    checks["render"] = check_render()

    has_critical_fail = any(checks[name]["status"] == "FAIL" for name in ("python", "uv"))
    has_optional_fail = any(checks[name]["status"] == "FAIL" for name in ("docker", "supabase", "render"))

    if json_mode:
        output = {
            "status": "failed" if has_critical_fail else "success",
            "checks": checks
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Doctor ===")
        print("Проверка локального окружения:")
        for name, info in checks.items():
            status_str = f"[{info['status']}]"
            print(f"  {status_str:<8} {name:<10}: {info['message']}")
            if info["status"] == "FAIL" and "hint" in info:
                print(f"           Подсказка: {info['hint']}")
                if info.get("action"):
                    print(f"           Команда:   {info['action']}")
        print("=" * 28)

        if has_critical_fail:
            print("\nОшибка: Обнаружены критические проблемы в локальном окружении (отсутствует Python >= 3.13 или uv).")
            print("Без них невозможно запустить локальный offline sandbox.")
        elif has_optional_fail:
            print("\nВнимание: Отсутствуют некоторые опциональные инструменты (Docker, Supabase CLI, Render CLI).")
            print("Базовый offline-путь доступен, но эти инструменты потребуются для локального запуска Supabase или деплоя.")
        else:
            print("\nЛокальное окружение готово к установке.")

    return 1 if has_critical_fail else 0


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
            print("Ссылка на полную диагностику: 'bootstrap doctor' или 'bootstrap checks'.")
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


def run_bootstrap_state(
    init: bool,
    show: bool,
    dry_run: bool,
    path: str,
    json_mode: bool,
    overwrite: bool,
) -> int:
    """Управление локальным файлом состояния (bootstrap state file contract)."""
    import datetime

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


def run_bootstrap_simulate(local: bool, fail_after_apply: bool, json_mode: bool) -> int:
    """Выполняет локальную синтетическую симуляцию цикла plan -> preflight -> apply -> verify -> rollback.

    Не взаимодействует с внешними API, БД или облачными провайдерами.
    """
    if not local:
        print("Ошибка: Локальная симуляция требует флага --local.", file=sys.stderr)
        return 1

    import datetime

    # 1. Plan Phase
    suffix = "sim123"
    sb_project = f"adr-sim-db-{suffix}"
    sb_org = "adr-sim-org"
    render_service = f"adr-sim-app-{suffix}"
    render_env = f"adr-sim-env-{suffix}"
    webhook_url = f"https://{render_service}.local/telegram-webhook"

    plan_details = {
        "supabase_project_name": sb_project,
        "supabase_organization": sb_org,
        "render_web_service_name": render_service,
        "render_environment_group": render_env,
        "webhook_target_url": webhook_url
    }

    steps_log = []

    steps_log.append({
        "phase": "plan",
        "status": "success",
        "message": "Локальный синтетический план успешно сгенерирован",
        "details": plan_details
    })

    # 2. Preflight Phase
    preflight_details = {
        "local_environment_checks": {
            "python_version_ok": True,
            "uv_available": True,
            "docker_available": True
        },
        "mock_endpoints_reachable": {
            "supabase_api": True,
            "render_api": True,
            "telegram_api": True
        }
    }
    steps_log.append({
        "phase": "preflight",
        "status": "success",
        "message": "Локальные preflight-проверки успешно завершены (имитация доступности API)",
        "details": preflight_details
    })

    # 3. Apply Phase
    state_path = Path(".bootstrap-state-sim.json")

    # Имитируем создание синтетических локальных ресурсов и запись их в файл состояния
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace("+00:00", "Z")
    sim_state = {
        "mode": "local-simulation",
        "status": "applying",
        "generated_at": timestamp,
        "resources": plan_details,
        "applied_steps": []
    }

    # Записываем промежуточное состояние (для демонстрации частичного apply)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        if json_mode:
            print(json.dumps({"error": f"Failed to initialize sim state: {str(e)}"}, indent=2), file=sys.stderr)
        else:
            print(f"Ошибка инициализации состояния симуляции: {e}", file=sys.stderr)
        return 1

    # Шаг Apply 1: Supabase
    sim_state["applied_steps"].append("supabase_sim_db_created")
    # Шаг Apply 2: Render
    sim_state["applied_steps"].append("render_sim_service_created")
    # Шаг Apply 3: Telegram
    sim_state["applied_steps"].append("telegram_sim_webhook_configured")

    sim_state["status"] = "applied"

    # Сохраняем финальное состояние apply
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        if json_mode:
            print(json.dumps({"error": f"Failed to save applied sim state: {str(e)}"}, indent=2), file=sys.stderr)
        else:
            print(f"Ошибка сохранения состояния симуляции: {e}", file=sys.stderr)
        return 1

    steps_log.append({
        "phase": "apply",
        "status": "success",
        "message": "Синтетические локальные ресурсы успешно созданы (состояние записано в .bootstrap-state-sim.json)",
        "details": {
            "applied_steps": sim_state["applied_steps"],
            "state_file_written": True
        }
    })

    # 4. Verify Phase
    verify_success = not fail_after_apply
    verify_status = "success" if verify_success else "failed"
    verify_msg = (
        "Синтетические smoke-тесты успешно пройдены (локальный рантайм вернул HTTP 200 OK)"
        if verify_success else
        "Синтетический smoke-тест провален: Локальный синтетический сервис вернул HTTP 500 Internal Server Error (Симуляция ошибки)"
    )

    # Обновляем состояние в файле перед rollback
    sim_state["status"] = "verified" if verify_success else "failed"
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(sim_state, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception:
        pass

    steps_log.append({
        "phase": "verify",
        "status": verify_status,
        "message": verify_msg,
        "details": {
            "local_health_check": "passed" if verify_success else "failed_http_500",
            "synthetic_telegram_webhook": "passed" if verify_success else "skipped"
        }
    })

    # 5. Rollback Phase
    # Читаем состояние из файла перед откатом, чтобы убедиться в консистентности
    rollback_steps = []
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded_state = json.load(f)

            # Revert steps in reverse order
            for step in reversed(loaded_state.get("applied_steps", [])):
                rollback_steps.append(f"reverted_{step}")

            # Удаляем файл состояния
            os.remove(state_path)
        except Exception as e:
            rollback_steps.append(f"rollback_failed: {str(e)}")

    steps_log.append({
        "phase": "rollback",
        "status": "success",
        "message": "Автоматический локальный откат успешно выполнен. Локальное состояние очищено.",
        "details": {
            "reverted_steps": rollback_steps,
            "state_file_removed": not state_path.exists()
        }
    })

    # Итоговый статус симуляции
    simulation_success = verify_success

    if json_mode:
        output = {
            "simulation": "local-only-synthetic",
            "fail_after_apply": fail_after_apply,
            "success": simulation_success,
            "steps": steps_log,
            "final_state": "ROLLED_BACK"
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Simulation (LOCAL-ONLY) ===")
        print("Режим: Локальная синтетическая симуляция цикла развертывания.")
        print("Внимание: Данная команда не производит никаких изменений во внешней инфраструктуре.")
        print()

        for idx, step in enumerate(steps_log, 1):
            phase_name = step["phase"].upper()
            status_str = f"[{step['status'].upper()}]"
            print(f"{idx}. Фаза {phase_name} {status_str}")
            print(f"   Сообщение: {step['message']}")
            if step["phase"] == "plan":
                for k, v in step["details"].items():
                    print(f"   - {k}: {v}")
            elif step["phase"] == "apply":
                print("   Примененные шаги:")
                for s in step["details"]["applied_steps"]:
                    print(f"   [x] {s}")
            elif step["phase"] == "rollback":
                print("   Откаченные шаги:")
                for s in step["details"]["reverted_steps"]:
                    print(f"   [x] {s}")
            print()

        print("-" * 50)
        if simulation_success:
            print("Симуляция завершена УСПЕШНО. Все фазы пройдены, ресурсы очищены.")
        else:
            print("Симуляция завершена со СБОЕМ на фазе верификации. Выполнен автоматический ОТКАТ.")
        print("=" * 45)

    return 0 if simulation_success else 1


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
