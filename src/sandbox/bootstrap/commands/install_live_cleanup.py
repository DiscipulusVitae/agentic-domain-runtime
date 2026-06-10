"""Мастер очистки для живого install — guided cleanup wizard (v1).

Использует .bootstrap-state.json как source of truth.
Удаляет ресурсы в reverse dependency order: Telegram webhook → Render → Supabase → state file.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    step_header,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    mask,
)


RENDER_API = "https://api.render.com/v1"


def run_live_cleanup(preview: bool = False, json_mode: bool = False) -> int:
    """Живой мастер очистки."""
    state = _load_bootstrap_state()
    if state is None:
        if json_mode:
            print(json.dumps({"error": ".bootstrap-state.json не найден"}, ensure_ascii=False))
        else:
            print("Ошибка: .bootstrap-state.json не найден. Нечего очищать.")
        return 1

    webhook_set = state.get("webhook_set", False)
    service_id = state.get("render_service_id")
    project_ref = state.get("supabase_project_ref")
    bot_username = state.get("telegram_bot_username", "?")
    service_url = state.get("render_service_url", "?")

    has_any = bool(webhook_set or service_id or project_ref)

    if not has_any:
        if json_mode:
            print(json.dumps({"status": "nothing_to_cleanup"}, ensure_ascii=False))
        else:
            print("В state-файле нет созданных ресурсов. Нечего очищать.")
            print("Удалить .bootstrap-state.json? [y/N]")
            answer = input("  > ").strip().lower()
            if answer == "y":
                Path(".bootstrap-state.json").unlink(missing_ok=True)
                print("Файл состояния удалён.")
        return 0

    # --- Preview ---
    print("=" * 55)
    print("  ADR Bootstrap — Мастер очистки (cleanup wizard)")
    print("=" * 55)
    print()

    _print_cleanup_preview(state, webhook_set, service_id, project_ref, bot_username, service_url)

    if preview:
        print()
        print("Это был preview-режим. Никакие ресурсы не были удалены.")
        print("Для реальной очистки запустите: bootstrap cleanup --live")
        return 0

    print()
    if not ask_yes_no("Выполнить очистку этих ресурсов?", default=False):
        print("Очистка отменена.")
        return 0

    print()

    # Step 1: Telegram webhook
    if webhook_set:
        step_header(1, 4, "Telegram webhook")
        token = _get_telegram_token_interactive()
        if token:
            if _delete_webhook(token):
                step_pass("Webhook удалён.")
                state.pop("webhook_set", None)
                state.pop("webhook_url", None)
                state.pop("webhook_verified", None)
            else:
                step_fail("Не удалось удалить webhook.")
        else:
            step_skip("Токен не предоставлен — webhook не удалён.")
            print("  Удалите вручную:")
            print(f"  curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook")

    # Step 2: Render
    if service_id:
        step_header(2, 4, "Render сервис")
        sid = state["render_service_id"]
        if _delete_render_service(sid):
            step_pass(f"Render сервис {mask(sid)} удалён.")
            state.pop("render_service_id", None)
            state.pop("render_service_url", None)
        else:
            step_fail(f"Не удалось удалить Render сервис {mask(sid)}.")
            print(f"  Dashboard: https://dashboard.render.com/web/srv-{sid}/settings")
            print(f"  API:       curl -X DELETE {RENDER_API}/services/{sid}")

    # Step 3: Supabase
    if project_ref:
        step_header(3, 4, "Supabase проект")
        if _delete_supabase_project(project_ref):
            step_pass(f"Supabase проект {mask(project_ref)} удалён.")
            state.pop("supabase_project_ref", None)
        else:
            step_fail(f"Не удалось удалить Supabase проект {mask(project_ref)}.")
            print(f"  Ручная команда:")
            print(f"  supabase projects delete {project_ref} --yes")

    # Step 4: State file
    step_header(4, 4, "Локальное состояние")
    try:
        Path(".bootstrap-state.json").unlink(missing_ok=True)
        step_pass(".bootstrap-state.json удалён.")
    except OSError:
        step_fail("Не удалось удалить файл состояния.")

    print()
    print("=" * 55)
    print("  Очистка завершена.")
    print("=" * 55)

    return 0


def _load_bootstrap_state() -> dict | None:
    """Загружает .bootstrap-state.json."""
    path = Path(".bootstrap-state.json")
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _print_cleanup_preview(state, webhook_set, service_id, project_ref, bot_username, service_url) -> None:
    """Выводит preview очистки."""
    print("Ресурсы к удалению:")
    print()

    if webhook_set:
        print(f"  [1] Telegram webhook: {state.get('webhook_url', 'установлен')}")
        print(f"      Бот: @{bot_username}")
    else:
        print("  [1] Telegram webhook: не настроен — пропускается")

    if service_id:
        print(f"  [2] Render сервис:    {mask(service_id)}")
        print(f"      URL: {service_url}")
    else:
        print("  [2] Render сервис:    не создан — пропускается")

    if project_ref:
        print(f"  [3] Supabase проект:  {mask(project_ref)}")
    else:
        print("  [3] Supabase проект:  не создан — пропускается")

    print("  [4] .bootstrap-state.json (локальный файл)")
    print()

    print("Порядок: webhook → Render → Supabase → state file")
    print()


def _get_telegram_token_interactive() -> str | None:
    """Запрашивает токен Telegram бота. Не выводит и не сохраняет."""
    import getpass

    print()
    print("Для удаления webhook нужен токен Telegram бота.")
    print("Он не сохраняется и не выводится.")
    if not ask_yes_no("Ввести токен?"):
        return None

    token = getpass.getpass("  Токен (ввод скрыт): ").strip()
    return token if token else None


def _delete_webhook(token: str) -> bool:
    """Удаляет Telegram webhook через Bot API."""
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        return data.get("ok", False) and data.get("result", False)
    except Exception:
        return False


def _delete_render_service(service_id: str) -> bool:
    """Удаляет Render сервис через CLI."""
    result = run_cmd(
        ["render", "services", "delete", service_id, "--confirm"],
        timeout=30,
    )
    if result["ok"]:
        return True

    # Fallback: попробовать REST API
    print("  Render CLI не сработал — пробую REST API...")
    try:
        req = urllib.request.Request(
            f"{RENDER_API}/services/{service_id}",
            method="DELETE",
        )
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status in (200, 204)
    except urllib.error.HTTPError as e:
        step_info(f"REST API: HTTP {e.code}")
        return False
    except Exception:
        return False


def _delete_supabase_project(project_ref: str) -> bool:
    """Удаляет Supabase проект через CLI."""
    result = run_cmd(
        ["supabase", "projects", "delete", project_ref, "--yes"],
        timeout=30,
    )
    return result["ok"]



