"""Тесты для incident follow-up guards: token source, state reuse, identity."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live import (
    _print_state_summary,
    _archive_state,
    mask,
)
from src.sandbox.bootstrap.commands.install_live_telegram import (
    run_telegram_phase,
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
        assert state.get("_telegram_token_source") == "env"

    def test_env_token_rejected_then_prompt(self, monkeypatch):
        """TELEGRAM_BOT_TOKEN detected но rejected → падает в prompt path."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setattr("getpass.getpass", lambda prompt: "prompted-token")

        state, calls_log = self._setup_telegram_test(monkeypatch, token_in_env=False)

        ask_resps = iter([
            True,   # «Есть токен?» — Да
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
    """Account/workspace identity confirmation: reviewer/disposable checks."""

    def test_supabase_org_asks_reviewer_confirmation(self, monkeypatch):
        """После определения org запрашивается подтверждение reviewer."""
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

    def test_render_workspace_asks_reviewer_confirmation(self, monkeypatch):
        """После определения workspace запрашивается подтверждение reviewer."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )

        def fake_run_cmd(args, **kw):
            if "workspace" in args and "current" in args:
                return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "MyWorkspace"})}
            if "services" in args and "create" in args:
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
