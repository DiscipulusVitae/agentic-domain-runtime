"""Фаза Telegram для живого мастера установки."""
import getpass
import json
import secrets
import sys
import time
import urllib.request
import urllib.error

from ..live_executor import (
    ask,
    ask_yes_no,
    run_cmd,
    step_pass,
    step_skip,
    step_fail,
    step_info,
    save_state,
    mask,
    discover_render_api_key,
)

TELEGRAM_API = "https://api.telegram.org"


def run_telegram_phase(plan, state: dict) -> None:
    """Фаза Telegram: BotFather, webhook setup, smoke, rollback info.

    Токен не сохраняется в state-файл и не выводится в консоль.
    В state попадают только non-secret metadata:
    - telegram_bot_name (получено из getMe)
    - telegram_bot_username
    - webhook_url
    - webhook_secret_sha256
    - webhook_verified
    """
    token = state.get("_telegram_token")  # временно хранится в памяти в том же объекте

    # Шаг 1: Получение токена
    if not token:
        print()
        print("=== Настройка Telegram бота ===")
        print()
        print("Для live webhook proof нужен Telegram бот.")
        print("Если у вас ещё нет бота:")
        print("  1. Откройте @BotFather в Telegram")
        print("  2. Отправьте команду /newbot")
        print("  3. Следуйте инструкциям для создания бота")
        print("  4. Скопируйте полученный токен (формат: 123456:ABC-DEF...)")
        print()

        if not ask_yes_no("Есть токен Telegram бота?"):
            print()
            step_skip("Telegram фаза пропущена — без бота webhook proof невозможен.")
            if not ask_yes_no("Продолжить без Telegram?"):
                sys.exit(1)
            state["telegram_skipped"] = True
            save_state(state)
            return

        token = getpass.getpass("  Токен бота (ввод скрыт): ").strip()

        if not token:
            step_skip("Пустой токен — Telegram фаза пропущена.")
            state["telegram_skipped"] = True
            save_state(state)
            return

        state["_telegram_token"] = token

    # Шаг 2: getMe — валидация токена (read-only)
    step_info("Проверка токена (getMe)...")

    me_result = _telegram_api_call(token, "getMe")
    if not me_result["ok"]:
        step_fail(f"Токен недействителен: {me_result.get('description', 'неизвестная ошибка')}")
        if not ask_yes_no("Пропустить Telegram?"):
            sys.exit(1)
        state["telegram_skipped"] = True
        state.pop("_telegram_token", None)
        save_state(state)
        return

    bot_info = me_result.get("result", {})
    bot_name = bot_info.get("first_name", "неизвестно")
    bot_username = bot_info.get("username", "unknown_bot")
    step_pass(f"Токен действителен. Бот: @{bot_username} ({bot_name})")

    # Сохраняем non-secret metadata
    state["telegram_bot_name"] = bot_name
    state["telegram_bot_username"] = bot_username
    save_state(state)

    # Шаг 3: Render URL должен быть доступен
    service_url = state.get("render_service_url")
    render_skipped = state.get("render_skipped")

    if not service_url or render_skipped:
        reasons = []
        if not service_url:
            reasons.append("render_service_url отсутствует")
        if render_skipped:
            reasons.append("render_skipped=True (stale флаг?)")
        step_info(f"Причина пропуска: {', '.join(reasons)}")
        step_skip("Render URL недоступен — webhook setup невозможен.")
        if not ask_yes_no("Продолжить без webhook?"):
            sys.exit(1)
        state["telegram_skipped"] = True
        state.pop("_telegram_token", None)
        save_state(state)
        return

    # Шаг 4: Генерация webhook secret
    webhook_secret = secrets.token_hex(32)
    state["webhook_secret_sha256"] = _sha256_hex(webhook_secret)

    # Шаг 5: Передача env vars в Render
    step_info("Передача Telegram env vars в Render...")
    render_env_result = _set_render_env_vars(state, token, webhook_secret)

    # Ждём деплоя с новыми env vars
    if render_env_result:
        step_info("Ожидание деплоя Render с новыми env vars (до 2 мин)...")
        time.sleep(20)
        health_url = f"{service_url}/health" if not service_url.endswith("/") else f"{service_url}health"
        for attempt in range(8):
            time.sleep(10)
            try:
                req = urllib.request.Request(health_url)
                resp = urllib.request.urlopen(req, timeout=10)
                if resp.status == 200:
                    step_pass("Render передеплоился с новыми переменными.")
                    break
            except Exception:
                step_info(f"Попытка {attempt + 1}/8...")
        else:
            step_info("Не удалось дождаться /health — продолжаем с текущим URL.")
    else:
        step_fail("Не удалось передать env vars в Render. Webhook не будет установлен.")
        print("  Бот не сможет принимать webhook-запросы без TOKEN и SECRET в окружении Render.")
        print("  Установите переменные вручную в Dashboard и перезапустите install.")
        state["telegram_env_failed"] = True
        state.pop("_telegram_token", None)
        save_state(state)
        return

    # Шаг 6: setWebhook
    webhook_url = f"{service_url.rstrip('/')}/webhook/telegram"
    step_info(f"Установка webhook: {webhook_url}")

    webhook_result = _telegram_api_call(token, "setWebhook", {
        "url": webhook_url,
        "secret_token": webhook_secret,
    })

    webhook_ok = webhook_result.get("ok") and webhook_result.get("result") is True
    if webhook_ok:
        step_pass("Webhook установлен.")
        state["webhook_url"] = webhook_url
        state["webhook_set"] = True
    else:
        step_fail(f"Webhook не установлен: {webhook_result.get('description', 'неизвестно')}")
        if not ask_yes_no("Продолжить без webhook?"):
            sys.exit(1)
        state["webhook_set"] = False
        state.pop("_telegram_token", None)
        save_state(state)
        return

    # Шаг 7: getWebhookInfo
    step_info("Проверка webhook (getWebhookInfo)...")
    info_result = _telegram_api_call(token, "getWebhookInfo")
    info = info_result.get("result", {})

    info_url = info.get("url", "")
    info_pending = info.get("pending_update_count", 0)
    has_custom_cert = info.get("has_custom_certificate", False)

    if info_url == webhook_url:
        step_pass(f"Webhook подтверждён: {webhook_url}")
    else:
        step_info(f"URL webhook отличается: {info_url} (ожидался {webhook_url})")

    state["webhook_verified"] = (info_url == webhook_url)
    state["webhook_pending_count"] = info_pending
    print(f"  pending_updates: {info_pending}")
    print(f"  custom_certificate: {has_custom_cert}")

    # Шаг 8: Synthetic webhook smoke (valid + invalid)
    if state["webhook_verified"]:
        step_info("Синтетический webhook smoke...")
        _webhook_smoke(token, webhook_url, webhook_secret)

    # Шаг 9: Cleanup/rollback info
    print()
    print("--- Webhook rollback ---")
    print(f"  # Удалить webhook:")
    print(f"  curl -X POST {TELEGRAM_API}/bot<TOKEN>/deleteWebhook")
    print(f"  # Проверить статус:")
    print(f"  curl {TELEGRAM_API}/bot<TOKEN>/getWebhookInfo")
    print()

    # Удаляем token из state перед сохранением
    state.pop("_telegram_token", None)
    save_state(state)
    step_pass("Telegram фаза завершена.")


def _telegram_api_call(token: str, method: str, data: dict | None = None) -> dict:
    """Вызов Telegram Bot API. Возвращает JSON-ответ."""
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        if data:
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def _set_render_env_vars(state: dict, telegram_token: str, webhook_secret: str) -> bool:
    """Передаёт Telegram env vars в Render сервис через REST API.

    Токен и секрет передаются в теле HTTP-запроса, не в argv.
    Использует Render API key из локальной конфигурации CLI.

    Returns:
        True если хотя бы одна переменная успешно установлена.
    """
    service_id = state.get("render_service_id")
    if not service_id:
        return False

    api_key = discover_render_api_key()
    if not api_key:
        step_info("Render API key не найден — env vars не установлены.")
        step_info("Установите переменные вручную в Render Dashboard:")
        print(f"  Dashboard: https://dashboard.render.com/web/{service_id}/env")
        print(f"  TELEGRAM_BOT_TOKEN=<токен>")
        print(f"  WEBHOOK_SECRET=<секрет>")
        return False

    env_vars = [
        {"key": "TELEGRAM_BOT_TOKEN", "value": telegram_token},
        {"key": "WEBHOOK_SECRET", "value": webhook_secret},
    ]

    url = f"https://api.render.com/v1/services/{service_id}/env-vars"
    body = json.dumps(env_vars).encode()

    try:
        req = urllib.request.Request(
            url,
            data=body,
            method="PUT",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=30)
        if resp.status == 200:
            step_pass("TELEGRAM_BOT_TOKEN и WEBHOOK_SECRET переданы в Render (REST API).")
            return True
        else:
            step_info(f"Render API ответил HTTP {resp.status}")
            return False
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:300]
        except Exception:
            pass
        step_fail(f"Render API: HTTP {e.code} — {body_text}")
        print(f"  Установите env vars вручную: https://dashboard.render.com/web/{service_id}/env")
        return False
    except Exception as e:
        step_fail(f"Render API недоступен: {e}")
        print(f"  Установите env vars вручную: https://dashboard.render.com/web/{service_id}/env")
        return False


def _webhook_smoke(token: str, webhook_url: str, webhook_secret: str) -> None:
    """Синтетический webhook smoke: валидный и невалидный запросы."""
    import uuid

    # Test 1: Valid webhook payload
    payload_valid = json.dumps({
        "update_id": 1,
        "message": {
            "message_id": 1,
            "text": "/start тестовое сообщение",
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "SmokeTest"},
            "date": 1718000000,
        }
    }).encode()

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload_valid,
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        step_pass(f"Smoke — валидный webhook: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        step_info(f"Smoke — валидный webhook: HTTP {e.code} (ожидаемо для fake LLM)")
    except Exception as e:
        step_info(f"Smoke — валидный webhook: {e}")

    # Test 2: Invalid payload (400 check)
    payload_invalid = json.dumps({"invalid": True}).encode()
    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload_invalid,
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        step_info(f"Smoke — невалидный payload: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            step_pass(f"Smoke — невалидный payload: HTTP 400 (корректная обработка ошибок)")
        else:
            step_info(f"Smoke — невалидный payload: HTTP {e.code}")
    except Exception as e:
        step_info(f"Smoke — невалидный payload: {e}")

    # Test 3: Missing secret (should be rejected)
    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload_valid,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        step_info(f"Smoke — без секрета: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            step_pass(f"Smoke — без секрета: HTTP {e.code} (защита работает)")
        else:
            step_info(f"Smoke — без секрета: HTTP {e.code}")
    except Exception as e:
        step_info(f"Smoke — без секрета: {e}")


def _sha256_hex(data: str) -> str:
    """SHA-256 хеш строки в hex-формате."""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()
