"""Telegram token source and bot identity guards for live reviewer proof."""

import os

REVIEWER_TOKEN_SOURCES_ALLOWED_WITH_CONFIRMATION = {
    "prompt",
    "scoped_env_file",
    "shell_env",
    "session_state",
}
DEFAULT_DENIED_REVIEWER_BOT_USERNAMES = {
    "adr_private_prod_bot",
    "adr_private_dev_bot",
}
REVIEWER_TOKEN_SOURCES_DENIED = {
    "dotenv",
    "generic_dotenv",
    "unknown",
    "ambiguous",
}


def normalize_token_source(source: str | None) -> str:
    """Normalize token source labels for reviewer proof."""
    normalized = (source or "").strip().lower().replace("-", "_")
    aliases = {
        "env": "shell_env",
        "environment": "shell_env",
        "state": "session_state",
        "prompted": "prompt",
        "manual": "prompt",
        "local_env": "dotenv",
        ".env": "dotenv",
    }
    return aliases.get(normalized, normalized or "unknown")


def validate_reviewer_token_source(source: str | None) -> dict:
    """Fail-closed classification for reviewer/live proof Telegram token source."""
    normalized = normalize_token_source(source)
    if normalized in REVIEWER_TOKEN_SOURCES_DENIED:
        return {
            "ok": False,
            "source": normalized,
            "message": (
                f"Telegram token source '{normalized}' is not allowed for reviewer proof. "
                "Use an explicit prompt token or a deliberately scoped proof env file."
            ),
        }
    if normalized in REVIEWER_TOKEN_SOURCES_ALLOWED_WITH_CONFIRMATION:
        return {
            "ok": True,
            "source": normalized,
            "message": f"Telegram token source classified as '{normalized}'.",
        }
    return {
        "ok": False,
        "source": normalized,
        "message": (
            f"Telegram token source '{normalized}' is ambiguous for reviewer proof. "
            "Use an explicit prompt token or a deliberately scoped proof env file."
        ),
    }


def validate_reviewer_bot_identity(bot_info: dict) -> dict:
    """Check getMe result against reviewer/disposable proof boundary."""
    username = str(bot_info.get("username") or "").lstrip("@")
    bot_id = bot_info.get("id")
    if not username:
        return {"ok": False, "username": username, "id": bot_id, "message": "Telegram bot username is missing."}
    if username.lower() in denied_reviewer_bot_usernames():
        return {
            "ok": False,
            "username": username,
            "id": bot_id,
            "message": f"Denied Telegram bot @{username} is not allowed in reviewer proof.",
        }
    return {
        "ok": True,
        "username": username,
        "id": bot_id,
        "message": f"Telegram identity gate passed: @{username} (id={bot_id}).",
    }


def denied_reviewer_bot_usernames() -> set[str]:
    """Return built-in synthetic deny-list plus optional operator-supplied bot usernames."""
    configured = {
        item.strip().lstrip("@").lower()
        for item in os.environ.get("ADR_DENIED_TELEGRAM_BOT_USERNAMES", "").split(",")
        if item.strip()
    }
    return DEFAULT_DENIED_REVIEWER_BOT_USERNAMES | configured
