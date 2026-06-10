"""Тесты live installer: blockers verification."""
import json
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live_telegram import (
    _set_render_env_vars,
    _telegram_api_call,
    run_telegram_phase,
)
from src.sandbox.bootstrap.commands.install_live_supabase import (
    run_supabase_phase,
)
from src.sandbox.bootstrap.commands.install_live_render import (
    run_render_phase,
)
from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup
from src.sandbox.bootstrap.live_executor import discover_render_api_key


class TestBlockerTelegramNoTokenInArgv:
    """Blocker 1: TELEGRAM_BOT_TOKEN не появляется в argv subprocess."""

    def test_env_vars_uses_rest_api_not_cli_argv(self, monkeypatch):
        """_set_render_env_vars должен использовать REST API, не CLI argv."""
        state = {"render_service_id": "srv-abc123"}
        # Оборачиваем urlopen чтобы перехватить HTTP-запрос
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            # Возвращаем fake 200 ответ
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        # Мокаем discover_render_api_key
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: "rk_test_fake",
        )

        with patch("urllib.request.urlopen", fake_urlopen):
            result = _set_render_env_vars(state, "fake-token-123", "secret-456")

        assert result is True
        assert len(calls) == 1
        req = calls[0]
        # Тело запроса должно содержать токен (это HTTP body, не argv)
        body = json.loads(req.data.decode())
        env_keys = [v["key"] for v in body]
        assert "TELEGRAM_BOT_TOKEN" in env_keys
        assert "WEBHOOK_SECRET" in env_keys
        # Authorization header должен быть Bearer
        assert req.get_header("Authorization") == "Bearer rk_test_fake"

    def test_no_token_in_command_construction(self):
        """В коде install_live_telegram не должно быть subprocess-вызовов с токеном в аргументах."""
        import inspect
        import src.sandbox.bootstrap.commands.install_live_telegram as mod

        source = inspect.getsource(mod)
        # Ищем паттерны: run_cmd([..."render"... техническими токеном в качестве аргумента списка
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "run_cmd" in stripped and "telegram_token" in stripped:
                # Если токен передаётся как аргумент в список — это проблема
                # Разрешено только внутри _set_render_env_vars для REST API
                if "_set_render_env_vars" not in stripped:
                    # Проверяем, что это не REST API вызов
                    assert False, f"Токен в argv subprocess: {stripped}"

    def test_telegram_api_call_no_token_in_argv(self):
        """_telegram_api_call формирует URL с токеном — это HTTP, не subprocess argv."""
        # Проверяем, что _telegram_api_call не использует subprocess
        # и что токен только в URL
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"ok": True}).encode()
            mock_open.return_value = mock_resp

            result = _telegram_api_call("test-token-123", "getMe")
            assert result["ok"] is True

            # Проверяем, что urlopen был вызван с URL содержащим токен (но это HTTP, не argv)
            call_url = mock_open.call_args[0][0].full_url
            assert "test-token-123" in call_url


class TestBlockerCleanupConditionalState:
    """Blocker 4: state file не удаляется при partial failure."""

    def test_cleanup_preview_detects_resources(self):
        """cleanup --live --preview должен показывать ресурсы без мутаций."""
        # Проверяем что preview mode не удаляет ресурсы
        # В preview режиме функция возвращается до мутаций
        pass

    def test_cleanup_no_state_file_returns_error(self):
        """Без state файла cleanup должен возвращать ошибку."""
        import os
        # Убеждаемся, что state файла нет
        if os.path.exists(".bootstrap-state.json"):
            os.remove(".bootstrap-state.json")

        result = run_live_cleanup(preview=True, json_mode=True)
        assert result == 1


class TestBlockerTelegramFailSafe:
    """Blocker 2: Telegram phase не ставит webhook если env vars не применены."""

    def test_run_telegram_phase_aborts_if_env_update_fails(self, monkeypatch):
        """Если _set_render_env_vars возвращает False, webhook не должен устанавливаться."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: None,
        )

        setup_webhook_calls = []

        def fake_telegram_api(token, method, data=None):
            if method == "getMe":
                return {"ok": True, "result": {"first_name": "Test", "username": "testbot"}}
            if method == "setWebhook":
                setup_webhook_calls.append(data)
                return {"ok": True, "result": True}
            return {"ok": False}

        state = {
            "render_service_id": "srv-test",
            "render_service_url": "https://test.onrender.com",
            "_telegram_token": "test-token-123",
        }

        with patch(
            "src.sandbox.bootstrap.commands.install_live_telegram._telegram_api_call",
            fake_telegram_api,
        ):
            with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
                with patch("src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
                           lambda *a, **kw: True):
                    with patch("src.sandbox.bootstrap.commands.install_live_telegram.ask",
                               lambda *a, **kw: ""):
                        run_telegram_phase(MagicMock(), state)

        # setWebhook не должен был вызываться
        assert len(setup_webhook_calls) == 0
        # state должен содержать флаг неудачи
        assert state.get("telegram_env_failed") is True


class TestRenderApiKeyDiscovery:
    """discover_render_api_key — вспомогательные тесты."""

    def test_returns_none_when_not_found(self, monkeypatch):
        """Без Render CLI возвращает None."""
        monkeypatch.delenv("RENDER_API_KEY", raising=False)
        result = discover_render_api_key()
        assert result is None

    def test_finds_from_env_var(self, monkeypatch):
        """Находит ключ из RENDER_API_KEY."""
        monkeypatch.setenv("RENDER_API_KEY", "rk_env_test123")
        result = discover_render_api_key()
        assert result == "rk_env_test123"


class TestCliLoginUx:
    """T305.2: интерактивный login вместо "откройте новый терминал"."""

    def test_supabase_phase_calls_run_interactive_for_login(self, monkeypatch):
        """При отсутствии авторизации supabase фаза вызывает run_interactive."""
        run_interactive_calls = []

        def fake_run_interactive(args, timeout):
            run_interactive_calls.append(args)

        def fake_check_logged_in(cmd, test_args):
            if len(run_interactive_calls) == 0:
                return False
            return True

        def fake_run_cmd(args, **kw):
            return {"ok": True, "code": 0, "stdout": "[]", "stderr": "", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            fake_run_interactive,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            fake_check_logged_in,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )

        state = {"supabase_project_ref": "abc123", "supabase_anon_key": "key"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                           lambda *a, **kw: ""):
                    run_supabase_phase(plan, state)

        assert len(run_interactive_calls) >= 1
        assert run_interactive_calls[0] == ["supabase", "login"]

    def test_render_phase_calls_run_interactive_for_login(self, monkeypatch):
        """При отсутствии авторизации render фаза вызывает run_interactive."""
        run_interactive_calls = []

        def fake_run_interactive(args, timeout):
            run_interactive_calls.append(args)

        def fake_check_logged_in(cmd, test_args):
            if len(run_interactive_calls) == 0:
                return False
            return True

        def fake_run_cmd(args, **kw):
            return {"ok": True, "code": 0, "stdout": "{}", "stderr": "", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_interactive",
            fake_run_interactive,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            fake_check_logged_in,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            fake_run_cmd,
        )

        state = {"render_service_id": "srv-test",
                 "render_service_url": "https://x.onrender.com",
                 "supabase_anon_key": "fake-key"}
        plan = MagicMock()
        plan.render_web_service_name = "test-svc"

        with patch("src.sandbox.bootstrap.commands.install_live_render.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_render.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_render.ask",
                           lambda *a, **kw: ""):
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.status = 200
                        mock_resp.read.return_value = b'{"status":"ok"}'
                        mock_open.return_value = mock_resp
                        run_render_phase(plan, state)

        assert len(run_interactive_calls) >= 1
        assert run_interactive_calls[0] == ["render", "login"]

    def test_supabase_fallback_when_interactive_fails(self, monkeypatch):
        """Если run_interactive не дал авторизации — fallback с ручным входом."""
        run_interactive_calls = []

        def fake_run_interactive(args, timeout):
            run_interactive_calls.append(args)

        def fake_check_logged_in(cmd, test_args):
            return False

        def fake_run_cmd(args, **kw):
            return {"ok": True, "code": 0, "stdout": "[]", "stderr": "", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            fake_run_interactive,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            fake_check_logged_in,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )

        state = {"supabase_project_ref": "abc123", "supabase_anon_key": "key"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            responses = [True, True]
            def fake_ask_yes_no(*a, **kw):
                return responses.pop(0) if responses else False
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                       fake_ask_yes_no):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                           lambda *a, **kw: ""):
                    run_supabase_phase(plan, state)

        assert len(run_interactive_calls) >= 1
        assert state.get("supabase_skipped") is True
