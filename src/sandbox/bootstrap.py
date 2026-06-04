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


def run_plan(json_mode: bool) -> int:
    """Выполняет сухой расчет плана развертывания (plan)."""
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

    if json_mode:
        output = {
            "dry_run": True,
            "resources": {
                "supabase_project_name": sb_project,
                "supabase_organization": sb_org,
                "render_web_service_name": render_service,
                "render_environment_group": render_env
            },
            "required_auth": required_auth,
            "planned_env_vars": planned_env_vars,
            "update_modes": {
                "local": "polling",
                "cloud": "webhook",
                "webhook_target_url": webhook_url
            }
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=== ADR Bootstrap Plan (DRY-RUN) ===")
        print("Внимание: Это read-only симуляция. Никакие ресурсы в облаке не будут созданы.")
        print()
        print("1. Превью имен ресурсов:")
        print(f"   - Supabase Project Name:      {sb_project}")
        print(f"   - Supabase Database Org:      {sb_org}")
        print(f"   - Render Web Service Name:    {render_service}")
        print(f"   - Render Environment Group:   {render_env}")
        print()
        print("2. Чек-лист авторизации:")
        for auth in required_auth:
            print(f"   [ ] {auth}")
        print()
        print("3. Планируемые переменные окружения (только имена):")
        for var in planned_env_vars:
            print(f"   - {var}")
        print()
        print("4. Политика доставки обновлений (Webhook/Polling):")
        print("   - Локальная разработка: Polling (TELEGRAM_UPDATE_MODE=polling)")
        print("   - Облако (Render): Webhook (TELEGRAM_UPDATE_MODE=webhook)")
        print(f"     Адрес вебхука: {webhook_url}")
        print("=" * 36)

    return 0
