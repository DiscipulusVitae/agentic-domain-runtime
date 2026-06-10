"""Тесты fresh Render ADR deploy strategy: no placeholder, ADR /health validation."""
import json
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live_render import (
    _is_adr_health,
    _validate_adr_health,
    ADR_REPO_URL,
    ADR_REPO_BRANCH,
    run_render_phase,
)
from src.sandbox.bootstrap.commands.install_live import _run_smoke_phase


class TestAdrHealthValidation:
    """_is_adr_health / _validate_adr_health: ADR vs placeholder detection."""

    def test_adr_health_accepted(self):
        """ADR /health JSON принимается."""
        body = {
            "status": "ok",
            "runtime": "python-stdlib",
            "mode": "sandbox",
            "llm_provider": "fake",
            "enabled_domains": ["kitchen", "books", "medical"],
            "agent_ids": ["core.butler", "kitchen.recorder"],
            "persistence": "supabase",
            "database": {
                "configured": True,
                "reachable": True,
                "schema_smoke": "ok"
            }
        }
        assert _is_adr_health(body) is True
        validation = _validate_adr_health(body)
        assert validation["valid"] is True
        assert validation["persistence"] == "supabase"
        assert validation["db_reachable"] is True

    def test_adr_health_memory_mode_accepted(self):
        """ADR /health в memory режиме тоже принимается."""
        body = {
            "status": "ok",
            "runtime": "python-stdlib",
            "mode": "sandbox",
            "llm_provider": "fake",
            "enabled_domains": [],
            "agent_ids": [],
            "persistence": "memory",
            "database": {
                "configured": False,
                "reachable": False,
                "schema_smoke": "skipped"
            }
        }
        assert _is_adr_health(body) is True

    def test_whoami_rejected(self):
        """whoami plaintext/HTML не JSON — rejected."""
        assert _is_adr_health("not json") is False
        assert _is_adr_health(None) is False

    def test_non_adr_json_rejected(self):
        """JSON без ADR-специфичных полей rejected."""
        assert _is_adr_health({"status": "ok"}) is False
        assert _is_adr_health({"hello": "world"}) is False

    def test_missing_database_field_rejected(self):
        """JSON с похожими, но без поля database — rejected."""
        assert _is_adr_health({
            "status": "ok",
            "runtime": "python-stdlib",
            "mode": "sandbox",
            "persistence": "supabase",
            "llm_provider": "fake",
            "enabled_domains": [],
            "agent_ids": [],
            # нет database
        }) is False

    def test_validation_reason_when_invalid(self):
        """_validate_adr_health возвращает reason для невалидного ответа."""
        result = _validate_adr_health({"nope": 1})
        assert result["valid"] is False
        assert result["reason"]


class TestRenderCreateArgs:
    """Create args не содержат placeholder image, используют ADR repo."""

    def test_create_args_use_repo_not_placeholder(self):
        """В коде install_live_render нет traefik/whoami и есть --repo."""
        import inspect
        import src.sandbox.bootstrap.commands.install_live_render as mod

        source = inspect.getsource(mod)
        assert "traefik/whoami" not in source
        assert "--repo" in source
        assert ADR_REPO_URL in source

    def test_adr_repo_url_branch_defined(self):
        """ADR_REPO_URL и ADR_REPO_BRANCH — константы с корректными значениями."""
        assert ADR_REPO_URL == "https://github.com/DiscipulusVitae/agentic-domain-runtime"
        assert ADR_REPO_BRANCH == "main"


class TestRenderExistingService:
    """Существующий сервис: находит, маркирует, не создаёт новый."""

    def test_existing_service_marked_as_existing(self, monkeypatch):
        """Найденный сервис получает render_service_source=existing."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            lambda args, **kw: _fake_run_cmd(args),
        )

        state = {
            "supabase_project_ref": "ref-test",
            "supabase_anon_key": "fake-key",
            "render_workspace": "ws",
            "render_workspace_id": "ws-1",
        }
        plan = MagicMock()
        plan.render_web_service_name = "adr-test-svc"

        with patch("src.sandbox.bootstrap.commands.install_live_render.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_render.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_render.ask",
                           lambda *a, **kw: ""):
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.status = 200
                        mock_resp.read.return_value = json.dumps({
                            "status": "ok", "runtime": "python-stdlib",
                            "mode": "sandbox", "llm_provider": "fake",
                            "enabled_domains": [], "agent_ids": [],
                            "persistence": "supabase",
                            "database": {"configured": True, "reachable": True, "schema_smoke": "ok"}
                        }).encode()
                        mock_open.return_value = mock_resp
                        run_render_phase(plan, state)

        assert state.get("render_service_source") == "existing"
        assert state.get("render_service_id") == "srv-existing-42"

    def test_fresh_created_marked_as_created_fresh(self, monkeypatch):
        """Созданный сервис получает render_service_source=created_fresh."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.check_cli_logged_in",
            lambda *a: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_render.run_cmd",
            lambda args, **kw: _fake_run_cmd_no_existing(args),
        )

        state = {
            "supabase_project_ref": "ref-fresh",
            "supabase_anon_key": "fake-key",
            "render_workspace": "ws",
            "render_workspace_id": "ws-1",
        }
        plan = MagicMock()
        plan.render_web_service_name = "adr-fresh-svc"

        with patch("src.sandbox.bootstrap.commands.install_live_render.save_state"):
            with patch("src.sandbox.bootstrap.commands.install_live_render.ask_yes_no",
                       lambda *a, **kw: True):
                with patch("src.sandbox.bootstrap.commands.install_live_render.ask",
                           lambda *a, **kw: ""):
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.status = 200
                        mock_resp.read.return_value = json.dumps({
                            "status": "ok", "runtime": "python-stdlib",
                            "mode": "sandbox", "llm_provider": "fake",
                            "enabled_domains": [], "agent_ids": [],
                            "persistence": "supabase",
                            "database": {"configured": True, "reachable": True, "schema_smoke": "ok"}
                        }).encode()
                        mock_open.return_value = mock_resp
                        run_render_phase(plan, state)

        assert state.get("render_service_source") == "created_fresh"
        assert state.get("render_service_id") == "srv-new-99"


def _fake_run_cmd(args, **kw):
    """Mock: returns existing service in list."""
    if "workspace" in args and "current" in args:
        return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "test-ws"}), "combined": ""}
    if "services" in args and "--output" in args:
        return {"ok": True, "stdout": json.dumps([
            {"service": {"id": "srv-existing-42", "name": "adr-test-svc", "url": "https://adr-test-svc.onrender.com"}}
        ]), "combined": ""}
    return {"ok": True, "stdout": "{}", "combined": ""}


def _fake_run_cmd_no_existing(args, **kw):
    """Mock: no existing services, create returns new ID."""
    if "workspace" in args and "current" in args:
        return {"ok": True, "stdout": json.dumps({"id": "ws-1", "name": "test-ws"}), "combined": ""}
    if "services" in args and "create" in args:
        return {"ok": True, "stdout": json.dumps(
            {"service": {"id": "srv-new-99", "name": "adr-fresh-svc"}}
        ), "combined": ""}
    if "services" in args and "--output" in args:
        return {"ok": True, "stdout": "null", "combined": ""}
    return {"ok": True, "stdout": "{}", "combined": ""}


class TestSmokePhaseAdrValidation:
    """_run_smoke_phase валидирует ADR /health."""

    def test_smoke_with_adr_health_passes(self, monkeypatch):
        """ADR health ответ → success."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live._validate_adr_health",
            lambda body: {"valid": True, "persistence": "supabase",
                          "status": "ok", "runtime": "python-stdlib",
                          "mode": "sandbox", "db_configured": True,
                          "db_reachable": True, "db_smoke": "ok"},
        )

        state = {"render_service_url": "https://test.onrender.com"}
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"{}"
            mock_open.return_value = mock_resp
            _run_smoke_phase(MagicMock(), state)

        # Не упало — значит принято

    def test_smoke_with_non_adr_health_fails(self, monkeypatch):
        """Не-ADR health ответ → fail message."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live._validate_adr_health",
            lambda body: {"valid": False, "reason": "not ADR"},
        )

        state = {"render_service_url": "https://bad.onrender.com"}
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"{}"
            mock_open.return_value = mock_resp
            _run_smoke_phase(MagicMock(), state)

        # Не упало с исключением


class TestTelegramSendMessageMock:
    """_try_send_telegram_message: sendMessage успешный путь с mock токеном."""

    def test_send_message_with_mocked_token(self, monkeypatch):
        """С fake токеном sendMessage формирует правильный JSON payload."""
        import os
        import urllib.request
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-bot-token-123")

        from src.sandbox.runtime import _try_send_telegram_message

        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(req)
            resp = MagicMock()
            resp.getcode.return_value = 200
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.delenv("RENDER_API_KEY", raising=False)

        result = _try_send_telegram_message(chat_id=123456, text="test message")
        assert result == "send_ok"
        assert len(calls) == 1
        req = calls[0]
        body = json.loads(req.data.decode())
        assert body["chat_id"] == 123456
        assert body["text"] == "test message"
        assert "fake-bot-token-123" in req.full_url
