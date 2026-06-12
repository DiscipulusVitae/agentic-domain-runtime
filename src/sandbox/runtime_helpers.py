"""Вспомогательные функции для sandbox runtime: сравнение, Telegram API."""
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger("sandbox.runtime")


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time сравнение строк для защиты от timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


def _try_send_telegram_message(chat_id, text) -> str:
    """Пытается отправить сообщение через Telegram Bot API.

    Без live токена — возвращает send_deferred/send_skipped.
    С токеном — делает HTTP POST к sendMessage.
    Возвращает строку статуса для trace.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return "send_skipped_no_token"

    try:
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.getcode() != 200:
                return f"send_failed_http_{resp.getcode()}"
            try:
                body = json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return "send_ok_not_parsed"
            if body.get("ok"):
                return "send_ok"
            error_code = body.get("error_code", "unknown")
            description = body.get("description", "")
            safe_desc = description[:80].replace(" ", "_") if description else "no_description"
            status = f"send_failed_tg_{error_code}_{safe_desc}"
            logger.warning("Telegram sendMessage failed: error_code=%s, description=%s", error_code, description)
            return status
    except urllib.error.URLError:
        return "send_deferred_network_unavailable"
    except Exception as e:
        return f"send_deferred_{type(e).__name__}"
