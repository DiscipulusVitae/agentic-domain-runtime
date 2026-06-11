"""Мастер очистки для живого install — guided cleanup wizard (v1).

Использует .bootstrap-state.json как source of truth.
Удаляет ресурсы в reverse dependency order: Telegram webhook → Render → Supabase → state file.
"""

import json
import os
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
)
from ..telegram_identity import validate_reviewer_bot_identity


RENDER_API = "https://api.render.com/v1"

STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"
STATUS_PENDING = "pending_verification"
STATUS_MANUAL = "manual_required"
STATUS_SKIPPED_RENDER_FAILED = "skipped_render_failed"

# Render-specific статусы — детализируют результат удаления Render сервиса
STATUS_RENDER_DELETE_VERIFIED = "render_delete_verified"
STATUS_RENDER_DELETE_FAILED = "render_delete_failed"
STATUS_RENDER_DELETE_PENDING = "render_delete_pending_verification"
STATUS_RENDER_MANUAL_REQUIRED = "render_manual_required"


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
            identity_ok = _verify_telegram_identity_before_mutation(token, state.get("telegram_bot_username"))
            if not identity_ok:
                step_fail("Telegram identity gate failed before deleteWebhook. State сохранён.")
                cleanup_results["webhook"] = STATUS_FAILED
            elif not _delete_webhook(token):
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
        render_status = _delete_render_service(sid)

        if render_status == STATUS_RENDER_DELETE_VERIFIED:
            step_pass(f"Render сервис {mask(sid)} удалён и подтверждён read-back проверкой.")
            state.pop("render_service_id", None)
            state.pop("render_service_url", None)
            cleanup_results["render"] = render_status
        elif render_status == STATUS_RENDER_DELETE_PENDING:
            step_fail(f"Render сервис {mask(sid)}: delete отправлен, но read-back не подтверждает удаление. State сохранён.")
            print(f"  Dashboard: https://dashboard.render.com/web/{sid}/settings")
            cleanup_results["render"] = render_status
        elif render_status == STATUS_RENDER_MANUAL_REQUIRED:
            step_fail(f"Render сервис {mask(sid)}: требуется ручное удаление (нет API key).")
            print(f"  Dashboard: https://dashboard.render.com/web/{sid}/settings")
            print(f"  API:       curl -X DELETE {RENDER_API}/services/{sid} -H 'Authorization: Bearer <API_KEY>'")
            cleanup_results["render"] = render_status
        else:
            step_fail(f"Не удалось удалить Render сервис {mask(sid)}.")
            print(f"  Dashboard: https://dashboard.render.com/web/{sid}/settings")
            print(f"  API:       curl -X DELETE {RENDER_API}/services/{sid} -H 'Authorization: Bearer <API_KEY>'")
            cleanup_results["render"] = render_status

    # Step 3: Supabase (только если Render удалён или не было Render)
    render_failed = cleanup_results.get("render") not in (None, STATUS_RENDER_DELETE_VERIFIED)
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

    failed_resources = {
        k: v for k, v in cleanup_results.items()
        if v not in (STATUS_VERIFIED, STATUS_RENDER_DELETE_VERIFIED)
    }
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
            STATUS_RENDER_DELETE_VERIFIED: "render verified",
            STATUS_RENDER_DELETE_FAILED: "render failed",
            STATUS_RENDER_DELETE_PENDING: "render pending verification",
            STATUS_RENDER_MANUAL_REQUIRED: "render manual required",
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


def _verify_telegram_identity_before_mutation(token: str, expected_username: str | None = None) -> bool:
    """Runs getMe before deleteWebhook and checks intended bot boundary."""
    me = _telegram_api_call(token, "getMe")
    if not me.get("ok"):
        return False

    bot_info = me.get("result") or {}
    actual_username = str(bot_info.get("username") or "").lstrip("@")
    if expected_username and actual_username != expected_username.lstrip("@"):
        return False

    identity = validate_reviewer_bot_identity(bot_info)
    return bool(identity.get("ok"))


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


def _resolve_render_api_key() -> tuple[str | None, str]:
    """Возвращает (api_key, source_description).

    Приоритет источников:
      1. RENDER_API_KEY из переменной окружения — trusted explicit source.
      2. ~/.render/cli.yaml — host config, допустим только НЕ в reviewer proof mode.
      3. ~/.render/api-key, ~/.config/render/auth.json — fallback host paths.

    В reviewer proof mode host config считается небезопасным:
    агент мог использовать чужой CLI-профиль.
    """
    env_key = os.environ.get("RENDER_API_KEY")
    if env_key:
        return env_key.strip(), "env:RENDER_API_KEY"

    # Проверяем, не запущен ли reviewer proof
    reviewer_proof = (
        os.environ.get("ADR_REVIEWER_PROOF", "").lower() in ("1", "true", "yes")
    )

    yaml_file = os.path.expanduser("~/.render/cli.yaml")
    try:
        with open(yaml_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("key:"):
                    key = stripped[4:].strip().strip('"').strip("'")
                    if reviewer_proof:
                        step_info("Render API key обнаружен в host config, но reviewer proof mode — пропущен.")
                        return None, "host_config_blocked_reviewer_proof"
                    return key, "host:cli.yaml"
    except OSError:
        pass

    for path_desc in [
        ("~/.render/api-key", os.path.expanduser("~/.render/api-key")),
        ("~/.config/render/auth.json", os.path.expanduser("~/.config/render/auth.json")),
    ]:
        desc, full_path = path_desc
        try:
            with open(full_path) as f:
                content = f.read().strip()
                if content:
                    if reviewer_proof:
                        step_info(f"Render API key обнаружен в {desc}, но reviewer proof mode — пропущен.")
                        continue
                    return content, f"host:{desc}"
        except OSError:
            pass

    return None, "absent"


def _delete_render_service(service_id: str) -> str:
    """Удаляет Render сервис через REST API (Render CLI v2.20+ не имеет 'services delete').

    Returns один из render-специфичных статусов:
      - STATUS_RENDER_DELETE_VERIFIED
      - STATUS_RENDER_DELETE_FAILED
      - STATUS_RENDER_MANUAL_REQUIRED
      - STATUS_RENDER_DELETE_PENDING
    """
    api_key, source = _resolve_render_api_key()

    if not api_key:
        if source == "absent":
            step_info("RENDER_API_KEY не задан, host config не найден.")
            step_info(
                "Сгенерируйте Personal Access Token в Render Dashboard: "
                "Account Settings → API Keys → Create API Key."
            )
        else:
            step_info(f"Render API key недоступен (source: {source}).")
        step_info(f"Ручное удаление: https://dashboard.render.com/web/{service_id}/settings")
        return STATUS_RENDER_MANUAL_REQUIRED

    try:
        req = urllib.request.Request(
            f"{RENDER_API}/services/{service_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        if resp.status not in (200, 204):
            step_info(f"REST API DELETE: HTTP {resp.status}")
            return STATUS_RENDER_DELETE_FAILED
    except urllib.error.HTTPError as e:
        step_info(f"REST API DELETE: HTTP {e.code}")
        return STATUS_RENDER_DELETE_FAILED
    except Exception as e:
        step_info(f"REST API DELETE: {e}")
        return STATUS_RENDER_DELETE_FAILED

    if not _verify_render_service_absent(service_id):
        step_info("Render сервис не подтверждён как удалённый — read-back verification failed.")
        return STATUS_RENDER_DELETE_PENDING

    step_info(f"Render сервис удалён через REST API (key source: {source}).")
    return STATUS_RENDER_DELETE_VERIFIED


def _verify_render_service_absent(service_id: str, attempts: int = 3, delay: float = 2.0) -> bool:
    """Read-back verification that Render service is absent/deleted."""
    api_key, _ = _resolve_render_api_key()
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
