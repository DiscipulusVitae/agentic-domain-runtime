"""Тесты для incident follow-up guards: token source, state reuse, identity."""
import json
import os
import urllib
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live import (
    _print_state_summary,
    _archive_state,
    mask,
)
from src.sandbox.bootstrap.commands.install_live_telegram import (
    run_telegram_phase,
    _set_render_env_vars,
)
from src.sandbox.bootstrap.telegram_identity import (
    validate_reviewer_bot_identity,
    validate_reviewer_token_source,
)
from src.sandbox.bootstrap.commands.install_live_supabase import (
    run_supabase_phase,
)
from src.sandbox.bootstrap.commands.install_live_render import (
    run_render_phase,
)


class TestTokenSourceGuard:
    """Token source: env / state / prompt detection + confirmation."""

    def _setup_telegram_test(self, monkeypatch, token_in_env=False,
                              token_in_state=False, getme_ok=True,
                              ask_responses_override=None):
        """Common setup для всех token source тестов."""
        if token_in_env:
            monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-env-token")
        else:
            monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        state = {}
        if token_in_state:
            state["_telegram_token"] = "fake-state-token"
            state["_telegram_token_source"] = "prompt"

        calls_log = []

        def fake_step_info(msg):
            calls_log.append(("step_info", msg))

        def fake_step_pass(msg):
            calls_log.append(("step_pass", msg))

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.step_info",
            fake_step_info,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.step_pass",
            fake_step_pass,
        )

        def fake_api_call(token_, method, data=None):
            calls_log.append(("api", method))
            return {"ok": True, "result": {
                "first_name": "TB", "username": "test_bot",
                "url": "https://test.onrender.com/webhook/telegram",
            }}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram._telegram_api_call",
            fake_api_call,
        )

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask",
            lambda *a, **kw: "",
        )

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram._webhook_smoke",
            lambda *a: None,
        )

        monkeypatch.setattr("time.sleep", lambda s: None)

        return state, calls_log

    def test_env_token_accepted_skips_prompt(self, monkeypatch):
        """TELEGRAM_BOT_TOKEN в env → detected, accepted → getMe без prompt."""
        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_env=True)

        ask_resps = iter([
            True,   # «Использовать обнаруженный токен?»
            True,   # identity gate confirmation
            True, True, True, True, True, True, True,  # остальные
        ])
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: next(ask_resps),
        )

        state["render_skipped"] = True  # не пытается сделать webhook setup
        state["render_service_url"] = "https://test.onrender.com"
        state["telegram_skipped"] = True  # не пытается setWebhook

        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        api_methods = [c[1] for c in calls_log if c[0] == "api"]
        assert "getMe" in api_methods
        assert state.get("_telegram_token_source") == "shell_env"

    def test_env_token_rejected_then_prompt(self, monkeypatch):
        """TELEGRAM_BOT_TOKEN detected но rejected → падает в prompt path."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setattr("getpass.getpass", lambda prompt: "prompted-token")

        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_env=False)

        ask_resps = iter([
            True,   # «Есть токен?» — Да
            True,   # identity gate confirmation
            True, True, True, True, True, True, True, True,
        ])
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: next(ask_resps),
        )

        state["render_skipped"] = True
        state["render_service_url"] = "https://test.onrender.com"
        state["telegram_skipped"] = True

        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        assert state.get("_telegram_token_source") == "prompt"

    def test_state_token_used_with_confirmation(self, monkeypatch):
        """_telegram_token в state → detected, accepted → getMe."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_state=True)

        ask_resps = iter([
            True,   # «Использовать обнаруженный токен?»
            True,   # identity gate confirmation
            True, True, True, True, True, True, True,
        ])
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: next(ask_resps),
        )

        state["render_skipped"] = True
        state["render_service_url"] = "https://test.onrender.com"
        state["telegram_skipped"] = True

        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        api_methods = [c[1] for c in calls_log if c[0] == "api"]
        assert "getMe" in api_methods

    def test_env_token_rejected_skip_telegram(self, monkeypatch):
        """TELEGRAM_BOT_TOKEN detected, rejected, «Есть токен?» → Нет → skip."""
        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_env=True)

        ask_resps = iter([
            False,  # «Использовать обнаруженный токен?» → Нет
            False,  # «Есть токен?» → Нет
            True,   # «Продолжить без Telegram?» → Да
        ])
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: next(ask_resps),
        )

        state["render_service_url"] = "https://test.onrender.com"

        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        assert state.get("telegram_skipped") is True
        assert "_telegram_token" not in state

    def test_state_token_clean_start_ignores_token(self, monkeypatch):
        """state token detected but rejected → clean prompt path."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setattr("getpass.getpass", lambda prompt: "clean-token")

        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_state=True)

        ask_resps = iter([
            False,  # «Использовать обнаруженный токен?» → Нет
            True,   # «Есть токен?» → Да
            True,   # identity gate confirmation
            True, True, True, True, True, True, True,
        ])
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: next(ask_resps),
        )

        state["render_skipped"] = True
        state["render_service_url"] = "https://test.onrender.com"
        state["telegram_skipped"] = True

        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        assert state.get("_telegram_token_source") == "prompt"

    def test_reviewer_token_source_prompt_allowed(self):
        """Explicit prompt token source is allowed for reviewer proof."""
        result = validate_reviewer_token_source("prompt")
        assert result["ok"] is True
        assert result["source"] == "prompt"

    def test_reviewer_token_source_shell_env_requires_confirmation(self):
        """Shell env token source is classified explicitly, not silently treated as .env."""
        result = validate_reviewer_token_source("env")
        assert result["ok"] is True
        assert result["source"] == "shell_env"

    def test_reviewer_token_source_dotenv_denied(self):
        """Generic local .env token source is fail-closed in reviewer proof."""
        result = validate_reviewer_token_source(".env")
        assert result["ok"] is False
        assert result["source"] == "dotenv"

    def test_reviewer_token_source_unknown_denied(self):
        """Unknown token source is fail-closed in reviewer proof."""
        result = validate_reviewer_token_source("")
        assert result["ok"] is False
        assert result["source"] == "unknown"

    def test_denied_bot_identity_blocked_in_reviewer_proof(self):
        """Denied bot identity is blocked before Telegram mutation."""
        result = validate_reviewer_bot_identity({"id": 42, "username": "adr_private_prod_bot"})
        assert result["ok"] is False

    def test_disposable_bot_identity_allowed(self):
        """Synthetic/reviewer bot identity passes the identity classifier."""
        result = validate_reviewer_bot_identity({"id": 42, "username": "adr_reviewer_bot"})
        assert result["ok"] is True

    def test_identity_denied_blocks_before_render_env_and_webhook(self, monkeypatch):
        """Known private bot in reviewer proof stops before Render env vars and setWebhook."""
        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_env=True)

        def fake_api_call(token_, method, data=None):
            calls_log.append(("api", method))
            return {"ok": True, "result": {
                "first_name": "Private",
                "username": "adr_private_prod_bot",
            }}

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram._telegram_api_call",
            fake_api_call,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.ask_yes_no",
            lambda *a, **kw: True,
        )
        env_calls = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram._set_render_env_vars",
            lambda *a, **kw: env_calls.append(a) or True,
        )

        state["render_service_url"] = "https://test.onrender.com"
        with patch("src.sandbox.bootstrap.commands.install_live_telegram.save_state"):
            run_telegram_phase(MagicMock(), state)

        assert "getMe" in [c[1] for c in calls_log if c[0] == "api"]
        assert env_calls == []
        assert state.get("telegram_skipped") is True


class TestStateReuseGuard:
    """State reuse: summary display + confirmation при существующем .bootstrap-state.json."""

    def test_state_summary_includes_known_resources(self, capsys):
        """_print_state_summary выводит Supabase ref, Render service, Telegram bot."""
        state = {
            "supabase_project_ref": "ref-abc",
            "supabase_project_name": "my-sb-proj",
            "render_service_id": "srv-xyz",
            "render_service_name": "my-render-svc",
            "render_service_url": "https://test.onrender.com",
            "render_service_source": "created_fresh",
            "telegram_bot_username": "test_bot",
            "webhook_url": "https://test.onrender.com/webhook/telegram",
            "health_ok": True,
            "step1_doctor": {"checks": {}},
        }
        _print_state_summary(state)
        captured = capsys.readouterr().out
        assert "my-sb-proj" in captured
        assert "my-render-svc" in captured
        assert "@test_bot" in captured

    def test_state_summary_empty_no_output(self, capsys):
        """Пустое состояние = пустая строка."""
        _print_state_summary({})
        captured = capsys.readouterr().out
        assert captured.strip() == ""

    def test_state_summary_partial(self, capsys):
        """Частичное состояние — выводит только доступное."""
        _print_state_summary({"supabase_project_ref": "ref-abc"})
        captured = capsys.readouterr().out
        assert "Supabase" in captured

    def test_archive_state_renames_file(self, monkeypatch, tmp_path):
        """_archive_state переименовывает .bootstrap-state.json."""
        state_path = str(tmp_path / ".bootstrap-state.json")
        with open(state_path, "w") as f:
            json.dump({"test": 1}, f)
        assert os.path.exists(state_path)

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live.step_info",
            lambda msg: None,
        )
        _archive_state(state_path)
        assert not os.path.exists(state_path)
        assert os.path.exists(state_path + ".old")


class TestIdentityConfirmation:
    """Account/workspace identity confirmation: fail-closed gate."""

    def test_supabase_org_confirmed_proceeds(self, monkeypatch):
        """reviewer подтверждён → фаза продолжается."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )

        def fake_run_cmd(args, **kw):
            if "orgs" in args and "list" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "MyOrg"}])}
            if "projects" in args and "create" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ref-new", "name": "test"})}
            return {"ok": True, "stdout": "{}", "combined": ""}
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )

        yes_no_calls = []
        def track_yes_no(prompt, *a, **kw):
            yes_no_calls.append(prompt)
            return True
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
            track_yes_no,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.step_info",
            lambda msg: None,
        )

        state = {}
        plan = MagicMock()
        plan.supabase_organization = "MyOrg"
        plan.supabase_project_name = "test-proj"

        with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
            with patch("secrets.token_urlsafe", return_value="pw"):
                with patch("src.sandbox.bootstrap.commands.install_live_supabase.run_interactive"):
                    with patch("src.sandbox.bootstrap.commands.install_live_supabase.get_supabase_api_keys",
                               return_value={"anon_key": "fake-key"}):
                        run_supabase_phase(plan, state)

        reviewer_prompts = [p for p in yes_no_calls if "reviewer" in p.lower()]
        assert len(reviewer_prompts) >= 1

    def test_supabase_org_denied_aborts(self, monkeypatch):
        """reviewer не подтверждён → sys.exit(1), мутации не выполняются."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.check_cli_logged_in",
            lambda *a: True,
        )

        create_calls = []
        def fake_run_cmd(args, **kw):
            if "orgs" in args and "list" in args:
                return {"ok": True, "stdout": json.dumps([{"id": "org-1", "name": "MyOrg"}])}
            if "projects" in args and "create" in args:
                create_calls.append(args)
                return {"ok": True, "stdout": json.dumps({"id": "ref-new", "name": "test"})}
            return {"ok": True, "stdout": "{}", "combined": ""}
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.run_cmd",
            fake_run_cmd,
        )

        def track_yes_no(prompt, *a, **kw):
            if "reviewer" in prompt.lower():
                return False  # denial
            return True
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.ask_yes_no",
            track_yes_no,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_supabase.step_info",
            lambda msg: None,
        )

        state = {}
        plan = MagicMock()
        plan.supabase_organization = "MyOrg"
        plan.supabase_project_name = "test-proj"

        with pytest.raises(SystemExit) as exc_info:
            with patch("src.sandbox.bootstrap.commands.install_live_supabase.save_state"):
                with patch("secrets.token_urlsafe", return_value="pw"):
                    run_supabase_phase(plan, state)

        assert exc_info.value.code == 1
        assert len(create_calls) == 0  # не дошло до создания проекта

    def test_render_workspace_confirmed_proceeds(self, monkeypatch):
        """reviewer workspace подтверждён → фаза продолжается."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )

        create_calls = []
        def fake_run_cmd(args, **kw):
            if "workspace" in args and "current" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "MyWorkspace"})}
            if "services" in args and "create" in args:
                create_calls.append(args)
                return {"ok": True, "stdout": json.dumps({"service": {"id": "srv-new"}}), "combined": ""}
            if "services" in args and "--output" in args:
                return {"ok": True, "stdout": json.dumps([]), "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            fake_run_cmd,
        )

        yes_no_calls = []
        def track_yes_no(prompt, *a, **kw):
            yes_no_calls.append(prompt)
            return True
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.ask_yes_no",
            track_yes_no,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.step_info",
            lambda msg: None,
        )

        state = {
            "supabase_project_ref": "ref",
            "supabase_anon_key": "key",
        }
        plan = MagicMock()
        plan.render_web_service_name = "test-svc"

        with patch("src.sandbox.bootstrap.commands.install_live_render.save_state"):
            with patch("urllib.request.urlopen") as mock_open:
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = json.dumps({
                    "status": "ok", "runtime": "python-stdlib",
                    "mode": "sandbox", "persistence": "supabase",
                    "database": {"configured": True, "reachable": True, "schema_smoke": "ok"},
                    "enabled_domains": [], "agent_ids": [],
                }).encode()
                mock_open.return_value = resp
                run_render_phase(plan, state)

        reviewer_prompts = [p for p in yes_no_calls if "reviewer" in p.lower()]
        assert len(reviewer_prompts) >= 1

    def test_render_workspace_denied_aborts(self, monkeypatch):
        """reviewer workspace не подтверждён → sys.exit(1)."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )

        create_calls = []
        def fake_run_cmd(args, **kw):
            if "workspace" in args and "current" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "MyWorkspace"})}
            if "services" in args and "create" in args:
                create_calls.append(args)
                return {"ok": True, "stdout": json.dumps({"service": {"id": "srv-new"}}), "combined": ""}
            if "services" in args and "--output" in args:
                return {"ok": True, "stdout": json.dumps([]), "combined": ""}
            return {"ok": True, "stdout": "{}", "combined": ""}
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            fake_run_cmd,
        )

        def track_yes_no(prompt, *a, **kw):
            if "reviewer" in prompt.lower():
                return False  # denial
            return True
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.ask_yes_no",
            track_yes_no,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.step_info",
            lambda msg: None,
        )

        state = {
            "supabase_project_ref": "ref",
            "supabase_anon_key": "key",
        }
        plan = MagicMock()
        plan.render_web_service_name = "test-svc"

        with pytest.raises(SystemExit) as exc_info:
            with patch("src.sandbox.bootstrap.commands.install_live_render.save_state"):
                run_render_phase(plan, state)

        assert exc_info.value.code == 1
        assert len(create_calls) == 0  # не дошло до создания сервиса


class TestRenderEnvMerge:
    """T307.1: Render env-var merge (GET → merge → PUT)."""

    def _setup_merge_mock(self, monkeypatch, existing_vars, mute_output=True):
        """Общий setup: мокает Render API GET/PUT с существующими vars."""
        captured_reqs = []
        get_body = json.dumps(existing_vars).encode()

        def fake_urlopen(req, timeout=None):
            captured_reqs.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = get_body if captured_reqs[0] is req else b"[]"
            return resp

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: "rk_test_fake",
        )
        if mute_output:
            for attr in ["step_info", "step_pass", "step_fail"]:
                monkeypatch.setattr(
                    f"src.sandbox.bootstrap.commands.install_live_telegram.{attr}",
                    lambda msg: None,
                )
        return captured_reqs

    def test_merge_supabase_env_survives(self, monkeypatch):
        """GET Supabase vars → merge не ломается."""
        self._setup_merge_mock(monkeypatch, [{"key": "SUPABASE_URL", "value": "x"}])
        result = _set_render_env_vars({"render_service_id": "srv-abc123"}, "tg", "ws")
        assert result is True

    def test_merge_preserves_supabase_vars(self, monkeypatch):
        """PUT содержит Supabase vars + Telegram vars."""
        existing = [
            {"key": "SUPABASE_URL", "value": "https://db.supabase.co"},
            {"key": "SUPABASE_ANON_KEY", "value": "key123"},
            {"key": "ADR_PERSISTENCE", "value": "supabase"},
        ]
        captured = self._setup_merge_mock(monkeypatch, existing)
        result = _set_render_env_vars({"render_service_id": "srv-abc123"}, "tg-token-999", "ws-secret-999")
        assert result is True
        assert len(captured) == 2
        assert captured[0].get_method() == "GET"
        assert captured[1].get_method() == "PUT"
        put_keys = {v["key"]: v["value"] for v in json.loads(captured[1].data.decode())}
        assert put_keys.get("SUPABASE_URL") == "https://db.supabase.co"
        assert put_keys.get("TELEGRAM_BOT_TOKEN") == "tg-token-999"

    def test_telegram_vars_overwrite_existing(self, monkeypatch):
        """Telegram vars перезаписывают существующие."""
        captured = self._setup_merge_mock(monkeypatch, [
            {"key": "TELEGRAM_BOT_TOKEN", "value": "old"},
            {"key": "SUPABASE_URL", "value": "https://db.co"},
        ])
        result = _set_render_env_vars({"render_service_id": "srv-abc123"}, "new", "new-ws")
        assert result is True
        put_keys = {v["key"]: v["value"] for v in json.loads(captured[1].data.decode())}
        assert put_keys["TELEGRAM_BOT_TOKEN"] == "new"
        assert put_keys["SUPABASE_URL"] == "https://db.co"
        assert "old" not in put_keys.values()

    def test_get_failure_prevents_put(self, monkeypatch):
        """GET failure → PUT не вызывается."""
        captured = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: "rk_test_fake",
        )
        for attr in ["step_info", "step_fail"]:
            monkeypatch.setattr(
                f"src.sandbox.bootstrap.commands.install_live_telegram.{attr}", lambda m: None,
            )

        class FH(urllib.error.HTTPError):
            def read(self): return b'{"error":"fail"}'

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            raise FH(url=req.full_url, code=500, msg="err", hdrs=MagicMock(), fp=MagicMock())

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = _set_render_env_vars({"render_service_id": "srv-abc123"}, "tg", "ws")
        assert result is False
        assert len(captured) == 1
        assert captured[0].get_method() == "GET"

    def test_malformed_get_prevents_put(self, monkeypatch):
        """GET возвращает не-список → PUT не вызывается."""
        captured = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_telegram.discover_render_api_key",
            lambda: "rk_test_fake",
        )
        for attr in ["step_info", "step_fail"]:
            monkeypatch.setattr(
                f"src.sandbox.bootstrap.commands.install_live_telegram.{attr}", lambda m: None,
            )
        def fake_urlopen(req, timeout=None):
            captured.append(req)
            resp = MagicMock(); resp.status = 200; resp.read.return_value = b'{"not":"list"}'
            return resp
        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = _set_render_env_vars({"render_service_id": "srv-abc123"}, "tg", "ws")
        assert result is False
        assert len(captured) == 1

    def test_secret_not_in_stdout(self, monkeypatch, capsys):
        """Значения токена/секрета не выводятся."""
        self._setup_merge_mock(monkeypatch, [{"key": "SUPABASE_URL", "value": "x"}], mute_output=False)
        _set_render_env_vars({"render_service_id": "srv-abc123"}, "TG_SECRET_123", "WS_SECRET_456")
        captured = capsys.readouterr()
        assert "TG_SECRET_123" not in captured.out
        assert "WS_SECRET_456" not in captured.out
