"""Тесты fresh Render ADR deploy strategy: no placeholder, ADR /health validation."""
import json
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live_render import (
    _is_adr_health,
    _validate_adr_health,
    _validate_live_render_health,
    ADR_REPO_URL,
    ADR_REPO_BRANCH,
    run_render_phase,
)
from src.sandbox.bootstrap.render_url_readback import (
    service_url,
    verify_render_service_url,
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


class TestLiveRenderHealthValidation:
    """Строгая валидация: требует Supabase persistence + DB reachable."""

    def _supabase_health(self, **overrides):
        body = {
            "status": "ok",
            "runtime": "python-stdlib",
            "mode": "sandbox",
            "llm_provider": "fake",
            "enabled_domains": ["kitchen"],
            "agent_ids": ["core.butler"],
            "persistence": "supabase",
            "database": {
                "configured": True,
                "reachable": True,
                "schema_smoke": "ok"
            }
        }
        body.update(overrides)
        return body

    def test_supabase_health_accepted(self):
        """Supabase-backed health с configured/reachable/smoke=ok — accepted."""
        result = _validate_live_render_health(self._supabase_health())
        assert result["valid"] is True

    def test_memory_mode_rejected(self):
        """ADR memory mode rejected в live Render validator."""
        body = self._supabase_health()
        body["persistence"] = "memory"
        result = _validate_live_render_health(body)
        assert result["valid"] is False
        assert "supabase" in result["reason"]

    def test_db_not_configured_rejected(self):
        """database.configured=false rejected."""
        body = self._supabase_health()
        body["database"]["configured"] = False
        result = _validate_live_render_health(body)
        assert result["valid"] is False
        assert "configured" in result["reason"]

    def test_db_not_reachable_rejected(self):
        """database.reachable=false rejected."""
        body = self._supabase_health()
        body["database"]["reachable"] = False
        result = _validate_live_render_health(body)
        assert result["valid"] is False
        assert "reachable" in result["reason"]

    def test_db_smoke_failed_rejected(self):
        """database.schema_smoke=failed rejected."""
        body = self._supabase_health()
        body["database"]["schema_smoke"] = "failed"
        result = _validate_live_render_health(body)
        assert result["valid"] is False
        assert "smoke" in result["reason"]

    def test_db_smoke_skipped_rejected(self):
        """database.schema_smoke=skipped rejected."""
        body = self._supabase_health()
        body["database"]["schema_smoke"] = "skipped"
        result = _validate_live_render_health(body)
        assert result["valid"] is False

    def test_memory_accepted_by_generic_rejected_by_strict(self):
        """Generic _validate_adr_health принимает memory; strict — нет."""
        body = self._supabase_health()
        body["persistence"] = "memory"
        generic = _validate_adr_health(body)
        assert generic["valid"] is True
        strict = _validate_live_render_health(body)
        assert strict["valid"] is False


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
        monkeypatch.setattr("time.sleep", lambda *_: None)

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
        assert state.get("render_service_status") == "service_existing"
        assert state.get("render_url_status") == "url_verified"
        assert state.get("render_url_verified") is True
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
        monkeypatch.setattr("time.sleep", lambda *_: None)

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
        assert state.get("render_service_status") == "service_created"
        assert state.get("render_service_id") == "srv-new-99"


class TestRenderUrlReadback:
    """Render URL read-back: no inferred URL, bounded pending states."""

    def test_service_url_accepts_only_actual_url(self):
        """_service_url не создаёт fallback из имени сервиса."""
        assert service_url({"name": "adr-test-svc", "url": "https://actual.onrender.com"}) == "https://actual.onrender.com"
        assert service_url({"name": "adr-test-svc", "url": ""}) == ""
        assert service_url({"name": "adr-test-svc"}) == ""
        assert service_url({"name": "adr-test-svc", "url": "adr-test-svc.onrender.com"}) == ""

    def test_url_immediately_available_verified(self, monkeypatch):
        """Render list сразу отдаёт url → state становится url_verified."""
        def fake_run_cmd(args, **kw):
            return {
                "ok": True,
                "stdout": json.dumps([
                    {"service": {"id": "srv-1", "name": "adr-svc", "url": "https://adr-svc.onrender.com"}}
                ]),
                "combined": "",
            }

        state = {}
        url = verify_render_service_url(
            state=state,
            run_cmd=fake_run_cmd,
            step_info=lambda *_: None,
            service_id="srv-1",
            service_name="adr-svc",
            attempts=2,
            interval_seconds=0,
        )

        assert url == "https://adr-svc.onrender.com"
        assert state["render_service_url"] == url
        assert state["render_url_status"] == "url_verified"
        assert state["render_url_verified"] is True

    def test_url_appears_after_retry_verified(self, monkeypatch):
        """Render url появляется после retry → verified без inferred fallback."""
        calls = {"n": 0}

        def fake_run_cmd(args, **kw):
            calls["n"] += 1
            url = "" if calls["n"] == 1 else "https://adr-late.onrender.com"
            return {
                "ok": True,
                "stdout": json.dumps([
                    {"service": {"id": "srv-2", "name": "adr-late", "url": url}}
                ]),
                "combined": "",
            }

        monkeypatch.setattr("time.sleep", lambda *_: None)

        state = {}
        url = verify_render_service_url(
            state=state,
            run_cmd=fake_run_cmd,
            step_info=lambda *_: None,
            service_id="srv-2",
            service_name="adr-late",
            attempts=3,
            interval_seconds=0,
        )

        assert calls["n"] == 2
        assert url == "https://adr-late.onrender.com"
        assert state["render_url_status"] == "url_verified"

    def test_url_missing_preserves_state_as_pending(self, monkeypatch):
        """Если Render не отдаёт url, state остаётся recoverable и без inferred URL."""
        def fake_run_cmd(args, **kw):
            return {
                "ok": True,
                "stdout": json.dumps([
                    {"service": {"id": "srv-3", "name": "adr-empty", "url": ""}}
                ]),
                "combined": "",
            }
        monkeypatch.setattr("time.sleep", lambda *_: None)

        state = {"render_service_id": "srv-3", "render_service_status": "service_created"}
        url = verify_render_service_url(
            state=state,
            run_cmd=fake_run_cmd,
            step_info=lambda *_: None,
            service_id="srv-3",
            service_name="adr-empty",
            attempts=2,
            interval_seconds=0,
        )

        assert url == ""
        assert "render_service_url" not in state
        assert state["render_service_id"] == "srv-3"
        assert state["render_url_status"] == "url_pending"
        assert state["render_url_verified"] is False
        assert "adr-empty.onrender.com" not in json.dumps(state)


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
    """_run_smoke_phase валидирует live Render ADR /health."""

    def test_smoke_with_adr_health_passes(self, monkeypatch):
        """Supabase-backed ADR health ответ → success."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live._validate_live_render_health",
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

    def test_smoke_with_non_adr_health_fails(self, monkeypatch):
        """Memory mode ADR health → fail в live smoke."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live._validate_live_render_health",
            lambda body: {"valid": False, "reason": "persistence=memory not supabase"},
        )

        state = {"render_service_url": "https://bad.onrender.com"}
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"{}"
            mock_open.return_value = mock_resp
            _run_smoke_phase(MagicMock(), state)


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
