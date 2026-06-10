import os
import subprocess
import sys


TTY_ERROR_MESSAGE = (
    "TTY/PTY требуется для интерактивных live-потоков установщика.\n"
    "Эта среда вероятно запускает команды без терминала (no-TTY).\n"
    "\n"
    "TTY-capable среды: Antigravity IDE, Codex VSC Ext, обычный терминал.\n"
    "No-TTY среды: OpenCode GUI/TUI, Kilo Code GUI/TUI.\n"
    "\n"
    "Альтернативы для no-TTY:\n"
    "  - uv run python -m src.sandbox bootstrap install --dry-run\n"
    "  - Ручной runbook: docs/SUPABASE_RENDER_WIRING_RUNBOOK.md\n"
)


def is_tty_available() -> bool:
    """Проверяет, доступен ли TTY для интерактивного ввода/вывода.

    Возвращает True если stdin, stdout И stderr — все TTY.
    В no-TTY окружениях (pipe, IDE без терминала) возвращает False.
    """
    try:
        return sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()
    except Exception:
        return False


def _is_wsl() -> bool:
    """Определяет, запущена ли программа в WSL (Windows Subsystem for Linux)."""
    try:
        with open("/proc/version", "r") as f:
            content = f.read().lower()
        return "microsoft" in content or "wsl" in content
    except OSError:
        pass
    return "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ


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
    """Проверяет доступность Docker CLI и запущен ли демон.
    В WSL2 даёт специфичные подсказки для Docker Desktop."""
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

    is_wsl = _is_wsl()
    if is_wsl:
        return {
            "status": "WARN",
            "message": "Docker CLI доступен, но демон не отвечает (WSL2)",
            "hint": (
                "Docker Desktop WSL integration, вероятно, не включена. "
                "Откройте Docker Desktop в Windows → Settings → Resources → "
                "WSL Integration → включите для текущего дистрибутива WSL. "
                "Затем перезапустите WSL терминал."
            ),
            "action": "Проверьте Docker Desktop WSL Integration в настройках Windows"
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
        "hint": "Скачайте Render CLI с GitHub: https://github.com/render-oss/cli/releases (zip-архив linux_amd64, извлеките render в ~/.local/bin/)",
        "action": "См. scripts/adr_bootstrap_wsl2.sh — автоматическая установка Render CLI"
    }
