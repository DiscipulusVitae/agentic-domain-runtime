"""Мастер очистки для живого install — guided cleanup wizard (v1).

Использует .bootstrap-state.json как source of truth.
Удаляет ресурсы в reverse dependency order: Telegram webhook → Render → Supabase → state file.
"""

import json
import sys
import urllib.error
import urllib.request
import time
from pathlib import Path

from ..env_checks import is_tty_available, TTY_ERROR_MESSAGE
from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    step_header,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    save_state,
    mask,
    discover_render_api_key,
)


RENDER_API = "https://api.render.com/v1"

STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"
STATUS_PENDING = "pending_verification"
STATUS_MANUAL = "manual_required"
STATUS_SKIPPED_RENDER_FAILED = "skipped_render_failed"


def run_live_cleanup(preview: bool = False, json_mode: bool = False) -> int:
    """Живой мастер очистки."""
    state = _load_bootstrap_state()
    if state is None:
        if json_mode:
            print(json.dumps({"error": ".bootstrap-state.json не найден"}, ensure_ascii=False))
        else:
            print("Ошибка: .bootstrap-state.json не найден. Нечего очищать.")
        return 2

    webhook_set = state.get("webhook_set", False)
    service_id = state.get("render_service_id")
    project_ref = state.get("supabase_project_ref")
    bot_username = state.get("telegram_bot_username", "?")
    service_url = state.get("render_service_url", "?")

    has_any = bool(webhook_set or service_id or project_ref)

    # --- Preview ---
    # Preview не требует TTY: только печать плана, без input() и мутаций
    if preview:
        if not has_any:
            if json_mode:
                print(json.dumps({"status": "nothing_to_cleanup"}, ensure_ascii=False))
            else:
                print("В state-файле нет созданных ресурсов. Нечего очищать.")
            return 0

        print("=" * 55)
        print("  ADR Bootstrap — Мастер очистки (cleanup wizard)")
        print("=" * 55)
        print()
        _print_cleanup_preview(state, webhook_set, service_id, project_ref, bot_username, service_url)
        print()
        print("Это был preview-режим. Никакие ресурсы не были удалены.")
        print("Для реальной очистки запустите: bootstrap cleanup --live")
        return 0

    # --- TTY gate ---
    # Все интерактивные ветки (input, ask_yes_no) — только после этой точки
    if not is_tty_available():
        if json_mode:
            print(json.dumps({"error": "tty_required", "message": TTY_ERROR_MESSAGE.split(chr(10))[0]}, ensure_ascii=False))
        else:
            print(TTY_ERROR_MESSAGE, file=sys.stderr)
        return 1

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

    # --- Live cleanup ---
    print("=" * 55)
    print("  ADR Bootstrap — Мастер очистки (cleanup wizard)")
    print("=" * 55)
    print()

    _print_cleanup_preview(state, webhook_set, service_id, project_ref, bot_username, service_url)

    print()
    if not ask_yes_no("Выполнить очистку этих ресурсов?", default=False):
        print("Очистка отменена.")
        return 0

    print()

    # Сбор результатов очистки: какие ресурсы удалены, не удалены, пропущены
    cleanup_results = {}

    # Step 1: Telegram webhook
    if webhook_set:
        step_header(1, 4, "Telegram webhook")
        token = _get_telegram_token_interactive()
        if token:
            if not _delete_webhook(token):
                step_fail("Не удалось вызвать deleteWebhook. State сохранён для повторной очистки.")
                cleanup_results["webhook"] = STATUS_FAILED
            elif _verify_telegram_webhook_empty(token, state.get("telegram_bot_username")):
                step_pass("Webhook удалён и проверен через getWebhookInfo.")
                state.pop("webhook_set", None)
                state.pop("webhook_url", None)
                state.pop("webhook_verified", None)
                cleanup_results["webhook"] = STATUS_VERIFIED
            else:
                step_fail("Webhook не подтверждён как удалённый. State сохранён для повторной очистки.")
                cleanup_results["webhook"] = STATUS_PENDING
        else:
            step_skip("Токен не предоставлен — webhook не удалён.")
            print("  Удалите вручную:")
            print(f"  curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook")
            cleanup_results["webhook"] = STATUS_MANUAL

    # Step 2: Render (must succeed before Supabase deletion)
    if service_id:
        step_header(2, 4, "Render сервис")
        sid = state["render_service_id"]
        if not _delete_render_service(sid):
            step_fail(f"Не удалось удалить Render сервис {mask(sid)}.")
            print(f"  Dashboard: https://dashboard.render.com/web/{sid}/settings")
            print(f"  API:       curl -X DELETE {RENDER_API}/services/{sid} -H 'Authorization: Bearer <API_KEY>'")
            cleanup_results["render"] = STATUS_FAILED
        elif _verify_render_service_absent(sid):
            step_pass(f"Render сервис {mask(sid)} удалён и подтверждён read-back проверкой.")
            state.pop("render_service_id", None)
            state.pop("render_service_url", None)
            cleanup_results["render"] = STATUS_VERIFIED
        else:
            step_fail(f"Render сервис {mask(sid)} не подтверждён как удалённый. State сохранён.")
            print(f"  Dashboard: https://dashboard.render.com/web/{sid}/settings")
            print(f"  API:       curl -X DELETE {RENDER_API}/services/{sid} -H 'Authorization: Bearer <API_KEY>'")
            cleanup_results["render"] = STATUS_PENDING

    # Step 3: Supabase (только если Render удалён или не было Render)
    render_failed = cleanup_results.get("render") not in (None, STATUS_VERIFIED)
    if project_ref and not render_failed:
        step_header(3, 4, "Supabase проект")
        if not _delete_supabase_project(project_ref):
            step_fail(f"Не удалось удалить Supabase проект {mask(project_ref)}.")
            print(f"  Ручная команда:")
            print(f"  supabase projects delete {project_ref} --yes")
            cleanup_results["supabase"] = STATUS_FAILED
        elif _verify_supabase_project_absent(project_ref):
            step_pass(f"Supabase проект {mask(project_ref)} удалён и подтверждён read-back проверкой.")
            state.pop("supabase_project_ref", None)
            cleanup_results["supabase"] = STATUS_VERIFIED
        else:
            step_fail(f"Supabase проект {mask(project_ref)} не подтверждён как удалённый. State сохранён.")
            print(f"  Ручная команда:")
            print(f"  supabase projects delete {project_ref} --yes")
            cleanup_results["supabase"] = STATUS_PENDING
    elif project_ref and render_failed:
        step_header(3, 4, "Supabase проект")
        step_skip("Render не удалён — Supabase сохранён для целостности.")
        print("  Render сервис зависит от Supabase DB. Supabase не удалён.")
        cleanup_results["supabase"] = STATUS_SKIPPED_RENDER_FAILED

    # Step 4: State file (conditional)
    step_header(4, 4, "Локальное состояние")

    failed_resources = {k: v for k, v in cleanup_results.items() if v != STATUS_VERIFIED}
    all_cleared = not failed_resources

    if all_cleared:
        try:
            Path(".bootstrap-state.json").unlink(missing_ok=True)
            step_pass(".bootstrap-state.json удалён — все ресурсы очищены.")
        except OSError:
            step_fail("Не удалось удалить файл состояния.")
    else:
        # Сохраняем обновлённое состояние без удалённых ресурсов
        save_state(state)
        step_info("State file сохранён с оставшимися ресурсами.")
        print()
        print("  Не все ресурсы удалены:")
        for resource, status in failed_resources.items():
            print(f"    - {resource}: {status}")
        print()
        print("  Повторный запуск 'bootstrap cleanup --live' продолжит очистку.")

    print()
    print("--- Итоги очистки ---")
    for resource, status in cleanup_results.items():
        label_map = {
            STATUS_VERIFIED: "verified",
            STATUS_FAILED: "failed",
            STATUS_PENDING: "pending verification",
            STATUS_MANUAL: "manual required",
            STATUS_SKIPPED_RENDER_FAILED: "skipped (Render not verified)",
        }
        label = label_map.get(status, status)
        print(f"  {resource:<15} {label}")

    if "state_file" not in cleanup_results:
        print(f"  state_file       {'удалён' if all_cleared else 'сохранён с оставшимися ресурсами'}")

    print()
    print("=" * 55)
    print("  Очистка завершена.")
    print("=" * 55)

    return 1 if failed_resources else 0


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
    data = _telegram_api_call(token, "deleteWebhook")
    return data.get("ok", False) and data.get("result", False)


def _telegram_api_call(token: str, method: str) -> dict:
    """Выполняет Telegram Bot API call. Токен не выводится."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception:
        return {"ok": False}


def _verify_telegram_webhook_empty(token: str, expected_username: str | None = None) -> bool:
    """Проверяет identity бота и что webhook URL пуст после cleanup."""
    me = _telegram_api_call(token, "getMe")
    if not me.get("ok"):
        return False

    actual_username = (me.get("result") or {}).get("username")
    if expected_username and actual_username != expected_username.lstrip("@"):
        return False

    info = _telegram_api_call(token, "getWebhookInfo")
    if not info.get("ok"):
        return False

    result = info.get("result") or {}
    return result.get("url", "") == ""


def _delete_render_service(service_id: str) -> bool:
    """Удаляет Render сервис: сначала CLI, затем REST API с авторизацией."""
    result = run_cmd(
        ["render", "services", "delete", service_id, "--confirm"],
        timeout=30,
    )
    if result["ok"]:
        return True

    # Fallback: REST API с Bearer авторизацией
    api_key = discover_render_api_key()
    if api_key:
        print("  Render CLI не сработал — пробую REST API...")
        try:
            req = urllib.request.Request(
                f"{RENDER_API}/services/{service_id}",
                method="DELETE",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            step_info(f"REST API: HTTP {e.code}")
        except Exception as e:
            step_info(f"REST API: {e}")

    # Оба пути не сработали — инструкции
    step_info("Render CLI и REST API не сработали.")
    return False


def _verify_render_service_absent(service_id: str, attempts: int = 3, delay: float = 2.0) -> bool:
    """Read-back verification that Render service is absent/deleted."""
    api_key = discover_render_api_key()
    if not api_key:
        step_info("Render verification skipped: API key not available.")
        return False

    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                f"{RENDER_API}/services/{service_id}",
                method="GET",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            if resp.status == 404:
                return True
            if resp.status in (200, 202):
                if attempt < attempts - 1:
                    time.sleep(delay)
                continue
            return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return True
            if e.code in (409, 429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(delay)
                continue
            step_info(f"Render verification: HTTP {e.code}")
            return False
        except Exception as e:
            if attempt < attempts - 1:
                time.sleep(delay)
                continue
            step_info(f"Render verification: {e}")
            return False

    return False


def _delete_supabase_project(project_ref: str) -> bool:
    """Удаляет Supabase проект через CLI."""
    result = run_cmd(
        ["supabase", "projects", "delete", project_ref, "--yes"],
        timeout=30,
    )
    return result["ok"]


def _verify_supabase_project_absent(project_ref: str, attempts: int = 3, delay: float = 2.0) -> bool:
    """Read-back verification that Supabase project is absent from project list."""
    for attempt in range(attempts):
        result = run_cmd(["supabase", "projects", "list", "--output", "json"], timeout=30)
        if result["ok"]:
            try:
                projects = json.loads(result["stdout"])
            except json.JSONDecodeError:
                return False

            if not any(p.get("id") == project_ref or p.get("ref") == project_ref for p in projects):
                return True

            if attempt < attempts - 1:
                time.sleep(delay)
                continue
            return False

        if attempt < attempts - 1:
            time.sleep(delay)
            continue
        step_info("Supabase verification failed: projects list unavailable.")
        return False

    return False

