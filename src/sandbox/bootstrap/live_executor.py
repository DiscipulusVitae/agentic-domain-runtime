"""Утилиты для живого выполнения CLI-команд и управления состоянием."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def ask(prompt: str) -> str:
    """Запрашивает ввод у пользователя."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Запрашивает y/N подтверждение."""
    suffix = " [y/N] " if not default else " [Y/n] "
    response = ask(prompt + suffix).lower()
    if not response:
        return default
    return response in ("y", "yes", "д", "да")


def run_cmd(args: list[str], timeout: int = 120, cwd: Optional[str] = None,
            env: Optional[dict] = None, check: bool = True, capture: bool = True) -> dict:
    """Запускает команду и возвращает результат."""
    kwargs = {"text": True, "timeout": timeout}
    if capture:
        kwargs["capture_output"] = True
    if cwd:
        kwargs["cwd"] = cwd
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
        kwargs["env"] = full_env

    try:
        res = subprocess.run(args, **kwargs)
        return {
            "ok": res.returncode == 0,
            "code": res.returncode,
            "stdout": (res.stdout or "").strip(),
            "stderr": (res.stderr or "").strip(),
            "combined": ((res.stdout or "") + (res.stderr or "")).strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "stdout": "", "stderr": "timeout", "combined": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "code": -1, "stdout": "", "stderr": "command not found", "combined": "command not found"}


def run_interactive(args: list[str], timeout: int = 300, cwd: Optional[str] = None) -> int:
    """Запускает команду с интерактивным I/O. Возвращает код возврата."""
    try:
        kwargs = {}
        if cwd:
            kwargs["cwd"] = cwd
        return subprocess.run(args, check=False, timeout=timeout, **kwargs).returncode
    except subprocess.TimeoutExpired:
        return -1
    except FileNotFoundError:
        return -1


def check_cli_logged_in(command: str, test_args: list[str]) -> bool:
    """Проверяет, залогинен ли CLI, через тестовую read-only команду."""
    result = run_cmd([command] + test_args, timeout=15)
    return result["ok"]


def step_header(step_num: int, total: int, title: str) -> None:
    """Выводит заголовок шага."""
    print()
    print(f"[{step_num}/{total}] {title}")
    print("-" * 60)


def step_pass(message: str) -> None:
    """Выводит успешный результат шага."""
    print(f"  OK   {message}")


def step_skip(message: str) -> None:
    """Выводит пропуск шага."""
    print(f"  SKIP {message}")


def step_fail(message: str) -> None:
    """Выводит ошибку шага (не прерывает выполнение)."""
    print(f"  FAIL {message}", file=sys.stderr)


def step_info(message: str) -> None:
    """Выводит информационное сообщение."""
    print(f"  ...  {message}")


def save_state(state: dict, path: str = ".bootstrap-state.json") -> None:
    """Сохраняет состояние установки в JSON-файл (без секретов)."""
    safe = {}
    for key, value in state.items():
        if any(s in key.lower() for s in ("token", "password", "secret", "key")):
            continue
        safe[key] = value

    safe["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Убираем потенциальные секреты из env (только имена переменных)
    if "env" in safe and isinstance(safe["env"], dict):
        safe["env"] = {k: "***" if any(s in k.lower() for s in ("token", "secret", "password", "key")) else v
                       for k, v in safe["env"].items()}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)


def load_state(path: str = ".bootstrap-state.json") -> dict:
    """Загружает состояние установки из JSON-файла."""
    if not Path(path).exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def mask(s: str, show: int = 6) -> str:
    """Маскирует строку: первые show символов + '...'."""
    if len(s) <= show:
        return s
    return s[:show] + "..."


def get_supabase_api_keys(project_ref: str) -> dict:
    """Получает анонимный ключ Supabase через CLI."""
    result = run_cmd(["supabase", "projects", "list", "--output", "json"], timeout=15)
    if not result["ok"]:
        return {}

    try:
        projects = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}

    # После supabase link, получаем ключи через status
    status = run_cmd(["supabase", "status", "--output", "json"], timeout=15)
    if not status["ok"]:
        # Альтернативный путь: получить через API
        anon_result = run_cmd(
            ["supabase", "projects", "api-keys", "--project-ref", project_ref, "--output", "json"],
            timeout=15
        )
        if anon_result["ok"]:
            try:
                keys = json.loads(anon_result["stdout"])
                anon = ""
                for k in keys:
                    if "anon" == k.get("name", "").lower() or "publishable" in k.get("name", "").lower():
                        anon = k.get("api_key", "")
                return {"anon_key": anon}
            except json.JSONDecodeError:
                pass

        # Fallback: возвращаем ошибку
        return {"anon_key": "", "error": "Не удалось получить API ключи"}

    try:
        status_data = json.loads(status["stdout"])
        return {
            "anon_key": status_data.get("anon_key", ""),
            "url": status_data.get("api_url", ""),
        }
    except json.JSONDecodeError:
        return {"anon_key": "", "error": "Не удалось разобрать supabase status"}
