"""Тесты Telegram phase gate по verified Render URL."""
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live_telegram import run_telegram_phase


def _setup(monkeypatch, *, env_result=True):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    calls = []

    def fake_api_call(token_, method, data=None):
        calls.append(method)
        return {"ok": True, "result": {"first_name": "TB", "username": "test_bot"}}

    env_calls = []
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_telegram._telegram_api_call",
        fake_api_call,
    )
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_telegram._set_render_env_vars",
        lambda *a, **kw: env_calls.append(a) or env_result,
    )
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_telegram._webhook_smoke",
        lambda *a: None,
    )
    monkeypatch.setattr("time.sleep", lambda *_: None)
    return calls, env_calls


def test_unverified_render_url_blocks_webhook_setup(monkeypatch):
    """Telegram phase не использует Render URL без render_url_status=url_verified."""
    calls, env_calls = _setup(monkeypatch)
    ask_resps = iter([True, True, True])
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
        lambda *a, **kw: next(ask_resps),
    )

    state = {
        "render_service_url": "https://adr-inferred.onrender.com",
        "render_url_status": "url_pending",
        "render_url_verified": False,
    }
    with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
        run_telegram_phase(MagicMock(), state)

    assert "getMe" in calls
    assert env_calls == []
    assert state.get("telegram_skipped") is True


def test_explicit_render_url_override_allows_webhook_setup(monkeypatch):
    """Явный Live Mutation Gate override разрешает unverified URL path."""
    calls, env_calls = _setup(monkeypatch, env_result=False)
    ask_resps = iter([True, True])
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
        lambda *a, **kw: next(ask_resps),
    )

    state = {
        "render_service_url": "https://adr-override.onrender.com",
        "render_url_status": "url_pending",
        "render_url_verified": False,
        "render_url_override_accepted": True,
    }
    with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
        run_telegram_phase(MagicMock(), state)

    assert "getMe" in calls
    assert len(env_calls) == 1
    assert state.get("telegram_env_failed") is True
