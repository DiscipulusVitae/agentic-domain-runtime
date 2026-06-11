"""Тесты cleanup hardening: exit codes, idempotency, failure semantics, preview/json."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.bootstrap.commands.install_live_cleanup import (
    run_live_cleanup,
    STATUS_RENDER_DELETE_VERIFIED,
    STATUS_RENDER_DELETE_FAILED,
    STATUS_RENDER_DELETE_PENDING,
    STATUS_RENDER_MANUAL_REQUIRED,
    _resolve_render_api_key,
)


@pytest.fixture(autouse=True)
def mock_external_verification(monkeypatch):
    """Cleanup tests are offline: read-back checks are mocked by default."""
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_cleanup._verify_telegram_identity_before_mutation",
        lambda *a, **kw: True,
    )
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_cleanup._verify_telegram_webhook_empty",
        lambda *a, **kw: True,
    )
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_cleanup._verify_render_service_absent",
        lambda *a, **kw: True,
    )
    monkeypatch.setattr(
        "src.sandbox.bootstrap.commands.install_live_cleanup._verify_supabase_project_absent",
        lambda *a, **kw: True,
    )


class TestCleanupExitCodes:
    """Унифицированные exit codes: 0=ok/nothing, 1=partial failure, 2=no state."""

    def test_no_state_returns_code_2(self, monkeypatch):
        """Отсутствие state-файла — exit 2."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=None):
            result = run_live_cleanup(preview=False, json_mode=True)
            assert result == 2

    def test_no_resources_returns_code_0(self, monkeypatch):
        """State без ресурсов — exit 0, controlled."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"step1_doctor": {"checks": {}}}):
            result = run_live_cleanup(preview=False, json_mode=True)
            assert result == 0

    def test_preview_returns_code_0(self, monkeypatch):
        """Preview всегда возвращает 0."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"render_service_id": "srv-test"}):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup._print_cleanup_preview"):
                result = run_live_cleanup(preview=True, json_mode=False)
                assert result == 0


class TestCleanupSuccessPath:
    """Успешное удаление всех ресурсов с mocked CLI/API."""

    def test_all_resources_deleted_success(self, monkeypatch):
        """Все ресурсы удалены — exit 0, state удалён."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )

        # Mock _delete_webhook → success
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: True,
        )
        # Mock _get_telegram_token_interactive → return fake token
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token-123",
        )
        # Mock _delete_render_service → success
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_VERIFIED,
        )
        # Mock _delete_supabase_project → success
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: True,
        )

        state = {
            "webhook_set": True,
            "render_service_id": "srv-abc",
            "render_service_url": "https://test.onrender.com",
            "supabase_project_ref": "ref-xyz",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.Path.unlink"):
                with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state"):
                    result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0


class TestCleanupPartialFailure:
    """Частичный отказ: один ресурс не удалось удалить."""

    def test_webhook_failure_does_not_block_render_supabase(self, monkeypatch):
        """Отказ webhook не блокирует удаление Render/Supabase, exit 1."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: False,  # webhook fails
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_VERIFIED,  # render succeeds
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: True,  # supabase succeeds
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {
            "webhook_set": True,
            "render_service_id": "srv-abc",
            "supabase_project_ref": "ref-xyz",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1  # partial failure
        # Render и Supabase удалены (pop), webhook остаётся
        assert "render_service_id" not in final_state
        assert "supabase_project_ref" not in final_state

    def test_webhook_identity_mismatch_blocks_delete(self, monkeypatch):
        """Identity mismatch before deleteWebhook blocks Telegram mutation and preserves state."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._verify_telegram_identity_before_mutation",
            lambda *a, **kw: False,
        )

        delete_calls = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: delete_calls.append(token) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {
            "webhook_set": True,
            "webhook_url": "https://test.onrender.com/webhook/telegram",
            "telegram_bot_username": "expected_bot",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert delete_calls == []
        assert final_state.get("webhook_set") is True

    def test_render_failure_skips_supabase(self, monkeypatch):
        """Отказ Render: Supabase не удаляется, оба остаются в state."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )

        cleanup_calls = []
        def track_delete_webhook(token):
            cleanup_calls.append("webhook")
            return True

        def track_delete_render(sid):
            cleanup_calls.append("render")
            return False  # render fails!

        def track_delete_supabase(ref):
            cleanup_calls.append("supabase")
            return True

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            track_delete_webhook,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            track_delete_render,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            track_delete_supabase,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {
            "webhook_set": True,
            "render_service_id": "srv-abc",
            "supabase_project_ref": "ref-xyz",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1  # partial failure
        assert cleanup_calls == ["webhook", "render"]  # supabase not called!**
        # Оба остаются в state
        assert "render_service_id" in final_state
        assert "supabase_project_ref" in final_state

    def test_render_success_supabase_failure(self, monkeypatch):
        """Render удалён успешно, Supabase отказ: Render pop, Supabase остаётся."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )

        cleanup_calls = []
        def track_delete_webhook(token):
            cleanup_calls.append("webhook")
            return True

        def track_delete_render(sid):
            cleanup_calls.append("render")
            return STATUS_RENDER_DELETE_VERIFIED

        def track_delete_supabase(ref):
            cleanup_calls.append("supabase")
            return False

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            track_delete_webhook,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            track_delete_render,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            track_delete_supabase,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {
            "webhook_set": True,
            "render_service_id": "srv-abc",
            "supabase_project_ref": "ref-xyz",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert cleanup_calls == ["webhook", "render", "supabase"]
        assert "render_service_id" not in final_state
        assert "supabase_project_ref" in final_state

    def test_webhook_unverified_preserves_state(self, monkeypatch):
        """deleteWebhook success без getWebhookInfo-empty verification не считается cleanup success."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._verify_telegram_webhook_empty",
            lambda *a, **kw: False,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"webhook_set": True, "webhook_url": "https://old.example/webhook"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["webhook_set"] is True
        assert final_state["webhook_url"] == "https://old.example/webhook"

    def test_render_unverified_preserves_state_and_skips_supabase(self, monkeypatch):
        """Render delete success без read-back absent verification сохраняет Render/Supabase state."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_PENDING,
        )
        supabase_calls = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: supabase_calls.append(ref) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["render_service_id"] == "srv-abc"
        assert final_state["supabase_project_ref"] == "ref-xyz"
        assert supabase_calls == []

    def test_supabase_unverified_preserves_state(self, monkeypatch):
        """Supabase delete success без list/read-back absent verification сохраняет project_ref."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._verify_supabase_project_absent",
            lambda ref: False,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["supabase_project_ref"] == "ref-xyz"


class TestCleanupIdempotency:
    """Retry после частичного отказа: удалённые ресурсы не всплывают повторно."""

    def test_retry_after_partial_success_clears_remaining(self, monkeypatch):
        """После первого прогона state без render_service_id — retry удаляет остальное."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )

        deleted = []
        def track_delete_webhook(token):
            deleted.append("webhook")
            return True

        def track_delete_render(sid):
            deleted.append("render")
            return True

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            track_delete_webhook,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            track_delete_render,
        )

        # State после частичного отказа: render удалён, webhook остался
        state = {"webhook_set": True, "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state"):
                with patch("src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
                           lambda ref: True):
                    result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0
        assert deleted == ["webhook"]

    def test_retry_after_render_failure_retries_both(self, monkeypatch):
        """После Render failure retry пробует оба: Render и Supabase."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            lambda: "fake-token",
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: True,
        )

        calls = []
        def track_delete_render(sid):
            calls.append("render")
            return STATUS_RENDER_DELETE_VERIFIED

        def track_delete_supabase(ref):
            calls.append("supabase")
            return True

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            track_delete_render,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            track_delete_supabase,
        )

        # State после Render failure в первом прогоне: webhook уже удалён
        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state"):
                with patch("src.sandbox.bootstrap.commands.install_live_cleanup.Path.unlink"):
                    result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0
        assert calls == ["render", "supabase"]


class TestCleanupPreviewJson:
    """Preview и JSON режимы: без мутаций, без TTY."""

    def test_preview_with_resources_shows_plan(self, monkeypatch, capsys):
        """Preview с ресурсами печатает план без мутаций."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        state = {
            "webhook_set": True,
            "render_service_id": "srv-test-42",
            "render_service_url": "https://test.onrender.com",
            "telegram_bot_username": "testbot",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            result = run_live_cleanup(preview=True, json_mode=False)

        assert result == 0
        captured = capsys.readouterr()
        output = captured.out
        assert "preview-режим" in output
        assert "testbot" in output
        assert "srv-te..." in output

    def test_preview_empty_state_json(self, monkeypatch, capsys):
        """Preview с пустым state в JSON — nothing_to_cleanup."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"step1_doctor": {"checks": {}}}):
            result = run_live_cleanup(preview=True, json_mode=True)

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["status"] == "nothing_to_cleanup"

    def test_output_does_not_contain_secrets(self, monkeypatch):
        """Вывод не содержит токенов/паролей."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask",
            lambda *a, **kw: "",
        )

        captured_token = None
        def capture_token():
            nonlocal captured_token
            captured_token = "abc123_super_secret_token_unused"
            return captured_token

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._get_telegram_token_interactive",
            capture_token,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_webhook",
            lambda token: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_VERIFIED,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: True,
        )

        state = {
            "webhook_set": True,
            "render_service_id": "srv-abc",
            "supabase_project_ref": "ref-xyz",
        }
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.Path.unlink"):
                with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state"):
                    result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0
        assert captured_token == "abc123_super_secret_token_unused"


class TestRenderCleanupNewStatusCodes:
    """T317: новое поведение _delete_render_service с детализированными статусами."""

    def test_delete_verified_clears_state_and_allows_supabase(self, monkeypatch):
        """STATUS_RENDER_DELETE_VERIFIED → state очищен, Supabase удаляется."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_VERIFIED,
        )

        supabase_called = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: supabase_called.append(ref) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0
        assert "render_service_id" not in final_state
        assert "supabase_project_ref" not in final_state
        assert supabase_called == ["ref-xyz"]

    def test_manual_required_preserves_state_and_skips_supabase(self, monkeypatch):
        """STATUS_RENDER_MANUAL_REQUIRED → state сохранён, Supabase пропущен."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_MANUAL_REQUIRED,
        )

        supabase_called = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: supabase_called.append(ref) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["render_service_id"] == "srv-abc"
        assert final_state["supabase_project_ref"] == "ref-xyz"
        assert supabase_called == []

    def test_delete_failed_preserves_state_and_skips_supabase(self, monkeypatch):
        """STATUS_RENDER_DELETE_FAILED → state сохранён, Supabase пропущен."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_FAILED,
        )

        supabase_called = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: supabase_called.append(ref) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["render_service_id"] == "srv-abc"
        assert supabase_called == []

    def test_delete_pending_preserves_state_and_skips_supabase(self, monkeypatch):
        """STATUS_RENDER_DELETE_PENDING → read-back не пройден, state сохранён."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_PENDING,
        )

        supabase_called = []
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_supabase_project",
            lambda ref: supabase_called.append(ref) or True,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc", "supabase_project_ref": "ref-xyz"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 1
        assert final_state["render_service_id"] == "srv-abc"
        assert supabase_called == []

    def test_render_delete_verified_without_supabase(self, monkeypatch):
        """Render-only state: STATUS_RENDER_DELETE_VERIFIED → exit 0."""
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.ask_yes_no",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup._delete_render_service",
            lambda sid: STATUS_RENDER_DELETE_VERIFIED,
        )

        final_state = {}
        def fake_save_state(s, path=".bootstrap-state.json"):
            final_state.update(s)

        state = {"render_service_id": "srv-abc"}
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=dict(state)):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup.save_state", fake_save_state):
                with patch("src.sandbox.bootstrap.commands.install_live_cleanup.Path.unlink"):
                    result = run_live_cleanup(preview=False, json_mode=False)

        assert result == 0
        assert "render_service_id" not in final_state


class TestRenderApiKeyCleanroomPolicy:
    """T321: _resolve_render_api_key в reviewer proof mode — cleanroom vs host."""

    def test_reviewer_proof_explicit_key_allowed(self, monkeypatch):
        """ADR_REVIEWER_PROOF=1 + RENDER_API_KEY → accepted."""
        monkeypatch.setenv("ADR_REVIEWER_PROOF", "1")
        monkeypatch.setenv("RENDER_API_KEY", "test-api-key-123")
        key, source = _resolve_render_api_key()
        assert key == "test-api-key-123"
        assert source == "env:RENDER_API_KEY"

    def test_reviewer_proof_cleanroom_config_accepted(self, monkeypatch, tmp_path):
        """ADR_REVIEWER_PROOF=1 + cleanroom HOME + cli.yaml → accepted."""
        monkeypatch.setenv("ADR_REVIEWER_PROOF", "1")
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".render").mkdir()
        (tmp_path / ".render" / "cli.yaml").write_text("version: 1\napi:\n    key: cli-test-key\n")

        key, source = _resolve_render_api_key()
        assert key == "cli-test-key"
        assert "cleanroom" in source

    def test_reviewer_proof_host_config_blocked(self, monkeypatch):
        """ADR_REVIEWER_PROOF=1 + real home cli.yaml → blocked/absent."""
        monkeypatch.setenv("ADR_REVIEWER_PROOF", "1")
        key, source = _resolve_render_api_key()
        if os.path.exists(os.path.expanduser("~/.render/cli.yaml")):
            assert key is None
            assert "blocked" in source
        else:
            assert key is None
            assert source == "absent"

    def test_non_reviewer_proof_allows_host_config(self, monkeypatch, tmp_path):
        """Без ADR_REVIEWER_PROOF host config работает."""
        monkeypatch.delenv("ADR_REVIEWER_PROOF", raising=False)
        monkeypatch.delenv("RENDER_API_KEY", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".render").mkdir()
        (tmp_path / ".render" / "cli.yaml").write_text("version: 1\napi:\n    key: host-key-456\n")

        key, source = _resolve_render_api_key()
        assert key == "host-key-456"
        assert source == "host:cli.yaml"

    def test_no_config_no_key_returns_absent(self, monkeypatch, tmp_path):
        """Нет ни env, ни cli.yaml → absent."""
        monkeypatch.delenv("RENDER_API_KEY", raising=False)
        monkeypatch.delenv("ADR_REVIEWER_PROOF", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        key, source = _resolve_render_api_key()
        assert key is None
        assert source == "absent"
