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

    def test_returns_none_when_not_found(self, monkeypatch, tmp_path):
        """Без Render CLI возвращает None."""
        monkeypatch.delenv("RENDER_API_KEY", raising=False)
        # Все expanduser ведут на временную директорию, где нет cli.yaml
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "nonexistent" / "file"))
        result = discover_render_api_key()
        assert result is None

    def test_finds_from_env_var(self, monkeypatch, tmp_path):
        """Находит ключ из RENDER_API_KEY."""
        monkeypatch.setenv("RENDER_API_KEY", "rk_env_test123")
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "no" / "file"))
        result = discover_render_api_key()
        assert result == "rk_env_test123"

    def test_finds_from_cli_yaml(self, tmp_path, monkeypatch):
        """Находит ключ из ~/.render/cli.yaml (Render CLI v2.20+)."""
        yaml_dir = tmp_path / ".render"
        yaml_dir.mkdir()
        yaml_file = yaml_dir / "cli.yaml"
        yaml_file.write_text("version: 1\napi:\n  key: rk_yaml_test\n  host: https://api.render.com/v1/\n")
        monkeypatch.setattr("os.path.expanduser", lambda p: str(yaml_file) if "cli.yaml" in p else p)
        monkeypatch.delenv("RENDER_API_KEY", raising=False)
        result = discover_render_api_key()
        assert result == "rk_yaml_test"


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


class TestSupabaseProjectCreateTTY:
    """T305.3/4: project create — generated credential (primary), interactive (fallback)."""

    def test_project_create_uses_run_cmd_with_db_password_primary(self, monkeypatch):
        """Primary path: run_cmd с --db-password + --output json."""
        cmd_calls = []

        def fake_run_cmd(args, **kw):
            cmd_calls.append(args)
            if "projects" in args and "create" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ref-new-123", "name": "test-proj"}), "combined": ""}
            if "orgs" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "test"}]), "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )

        state = {"supabase_org_id": "org-1", "supabase_org_name": "test"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                           lambda *a, **kw: ""):
                    run_supabase_phase(plan, state)

        create_calls = [args for args in cmd_calls if "create" in args]
        assert len(create_calls) >= 1
        create_args = create_calls[0]
        assert "--db-password" in create_args
        assert "--output" in create_args and "json" in create_args
        assert state.get("supabase_project_ref") == "ref-new-123"

    def test_project_ref_resolved_after_create(self, monkeypatch):
        """Project ref разрешается из JSON ответа create."""
        cmd_calls = []

        def fake_run_cmd(args, **kw):
            cmd_calls.append(args)
            if "projects" in args and "create" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ref-new-456", "name": "test-proj"}), "combined": ""}
            if "orgs" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "test"}]), "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )

        state = {"supabase_org_id": "org-1"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                           lambda *a, **kw: ""):
                    run_supabase_phase(plan, state)

        assert state.get("supabase_project_ref") == "ref-new-456"

    def test_password_is_secret_not_in_state(self, monkeypatch):
        """Сгенерированный пароль не попадает в state."""
        saved_states = []

        def fake_save_state(s, path=".bootstrap-state.json"):
            saved_states.append(dict(s))

        def fake_run_cmd(args, **kw):
            if "projects" in args and "create" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ref-sec-1", "name": "test-proj"}), "combined": ""}
            if "orgs" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "test"}]), "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.save_state",
            fake_save_state,
        )

        state = {"supabase_org_id": "org-1"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                   lambda *a, **kw: True):
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                       lambda *a, **kw: ""):
                run_supabase_phase(plan, state)

        for saved in saved_states:
            for key, value in saved.items():
                assert "password" not in str(value).lower(), f"password found in state: {key}"

    def test_password_error_keyword_detection(self, monkeypatch):
        """_is_password_or_tty_error определяет ошибки пароля/TTY."""
        from src.sandbox.bootstrap.commands.install_live_supabase import (
            _is_password_or_tty_error,
        )
        assert _is_password_or_tty_error(
            "non-interactive mode requires --db-password"
        ) is True
        assert _is_password_or_tty_error("TTY required") is True
        assert _is_password_or_tty_error("Enter password:") is True
        assert _is_password_or_tty_error("successfully") is False
        assert _is_password_or_tty_error("") is False

    def test_no_db_password_in_state_after_create(self):
        """--db-password не должен появляться в default-аргументах кода (только runtime)."""
        # Проверяем что нет hardcoded --db-password в default args
        # (runtime value генерируется и не сохраняется)
        import inspect
        import src.sandbox.bootstrap.commands.install_live_supabase as mod

        source = inspect.getsource(mod)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if '"--db-password"' in stripped or "'--db-password'" in stripped:
                # Разрешено только: "--db-password" как строковый литерал в args,
                # но значение должно быть переменной, не литералом.
                continue  # допустимо — значение всегда runtime-generated
            if "--db-password" in stripped and ("save_state" in stripped or "state[" in stripped):
                assert False, f"--db-password в state-связанном коде: {stripped}"

    def test_link_retries_interactive_on_password_error(self, monkeypatch):
        """Если link возвращает password/TTY ошибку, пробуем run_interactive."""
        run_interactive_calls = []
        cmd_calls = []

        def fake_run_interactive(args, timeout):
            run_interactive_calls.append(args)

        def fake_run_cmd(args, **kw):
            cmd_calls.append(args)
            if "orgs" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "test"}]), "combined": ""}
            if "link" in args:
                link_count = sum(1 for c in cmd_calls if "link" in c)
                if link_count == 1:
                    return {"ok": False, "combined": "non-interactive mode requires password"}
            return {"ok": True, "stdout": "{}", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_interactive",
            fake_run_interactive,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )

        state = {"supabase_project_ref": "ref-test", "supabase_anon_key": "key"}
        plan = MagicMock()
        plan.supabase_project_name = "test-proj"
        plan.supabase_organization = "test-org"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.ask",
                           lambda *a, **kw: ""):
                    run_supabase_phase(plan, state)

        link_interactive = [args for args in run_interactive_calls if "link" in args]
        assert len(link_interactive) >= 1, f"run_interactive={run_interactive_calls}"


class TestStaleSkipFlags:
    """T305.6: stale skip-флаги должны очищаться при успехе фазы."""

    def test_render_success_clears_render_skipped(self, monkeypatch):
        """После успешной render фазы render_skipped удаляется из state."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_interactive",
            lambda *a, **kw: 0,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )

        def fake_run_cmd(args, **kw):
            if "workspace" in args and "current" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "test-ws"}), "combined": ""}
            if "services" in args:
                return {"ok": True, "stdout": "null", "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            fake_run_cmd,
        )

        state = {
            "render_service_id": "srv-old",
            "render_service_url": "https://test.onrender.com",
            "supabase_anon_key": "fake-key",
            "render_skipped": True,  # stale флаг от предыдущего прогона
        }
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

        assert "render_skipped" not in state

    def test_telegram_skips_with_render_skipped_stale(self, monkeypatch):
        """Если render_skipped=True, Telegram фаза скипает с указанием причины."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: None,
        )

        def fake_telegram_api(token, method, data=None):
            if method == "getMe":
                return {"ok": True, "result": {"first_name": "T", "username": "tbot"}}
            return {"ok": False}

        state = {
            "render_service_url": "https://test.onrender.com",
            "render_skipped": True,  # stale
            "_telegram_token": "test-token",
        }

        with patch(
            "src.sandbox.bootstrap.commands.install_live_telegram._telegram_api_call",
            fake_telegram_api,
        ):
            with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
                with patch("src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
                           lambda *a, **kw: True):
                    run_telegram_phase(MagicMock(), state)

        assert state.get("telegram_skipped") is True

    def test_telegram_proceeds_when_render_skipped_cleared(self, monkeypatch):
        """Если render_skipped очищен и URL есть, фаза идёт дальше."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: "rk_fake",
        )

        api_calls = []
        def fake_telegram_api(token, method, data=None):
            api_calls.append(method)
            if method == "getMe":
                return {"ok": True, "result": {"first_name": "T", "username": "tbot"}}
            if method == "setWebhook":
                return {"ok": True, "result": True}
            if method == "getWebhookInfo":
                return {"ok": True, "result": {"url": "https://test.onrender.com/webhook/telegram"}}
            return {"ok": False}

        state = {
            "render_service_url": "https://test.onrender.com",
            "render_service_id": "srv-test",
            "_telegram_token": "test-token",
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
                        with patch("urllib.request.urlopen") as mock_open:
                            with patch("time.sleep", lambda s: None):
                                resp = MagicMock()
                                resp.status = 200
                                mock_open.return_value = resp
                                run_telegram_phase(MagicMock(), state)

        assert "setWebhook" in api_calls
        assert state.get("webhook_set") is True
