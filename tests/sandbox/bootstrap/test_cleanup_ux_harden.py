"""Тесты для live_executor: ask_yes_no, ask, save_state, load_state."""
import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAskYesNoHarden:
    """ask_yes_no: зацикливание, token-shape rejection, валидный ввод."""

    def test_valid_yes_inputs(self, monkeypatch):
        """y, yes, д, да — возвращают True."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        for answer in ("y", "Y", "yes", "YES", "Yes", "д", "Д", "да", "ДА", "Да"):
            def fake_input(prompt: str) -> str:
                return answer

            monkeypatch.setattr("builtins.input", fake_input)
            result = ask_yes_no("Test")
            assert result is True, f"answer={answer} → expected True, got {result}"

    def test_valid_no_inputs(self, monkeypatch):
        """n, no, н, нет — возвращают False."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        for answer in ("n", "N", "no", "NO", "No", "н", "Н", "нет", "НЕТ", "Нет"):
            def fake_input(prompt: str) -> str:
                return answer

            monkeypatch.setattr("builtins.input", fake_input)
            result = ask_yes_no("Test")
            assert result is False, f"answer={answer} → expected False, got {result}"

    def test_empty_returns_default_false(self, monkeypatch):
        """Пустой ввод возвращает default=False."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        monkeypatch.setattr("builtins.input", lambda p: "")
        result = ask_yes_no("Test")
        assert result is False

    def test_empty_returns_default_true(self, monkeypatch):
        """Пустой ввод возвращает default=True."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        monkeypatch.setattr("builtins.input", lambda p: "")
        result = ask_yes_no("Test", default=True)
        assert result is True

    def test_unrecognized_re_prompts_then_accepts_yes(self, monkeypatch):
        """Невалидный ввод → re-prompt → потом 'y' → True."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        inputs = iter(["maybe", "хз", "y"])
        monkeypatch.setattr("builtins.input", lambda p: next(inputs))
        result = ask_yes_no("Test")
        assert result is True

    def test_unrecognized_re_prompts_then_accepts_no(self, monkeypatch):
        """Невалидный ввод → re-prompt → потом 'n' → False."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        inputs = iter(["random", "n"])
        monkeypatch.setattr("builtins.input", lambda p: next(inputs))
        result = ask_yes_no("Test")
        assert result is False

    def test_token_shaped_rejection_re_prompts(self, monkeypatch):
        """Длинный ввод >50 символов → reject → re-prompts → потом принимает 'y'."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        long_string = "1234567890" * 6  # 60 chars — выглядит как токен
        inputs = iter([long_string, "y"])
        calls = []

        def fake_input(prompt: str) -> str:
            calls.append(prompt)
            return next(inputs)

        monkeypatch.setattr("builtins.input", fake_input)
        result = ask_yes_no("Test")
        assert result is True
        assert len(calls) >= 2  # первый prompt + re-prompt

    def test_token_shaped_followed_by_empty(self, monkeypatch):
        """Токен → reject → пустой ввод → default=False."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        long_string = "5" * 51
        inputs = iter([long_string, ""])
        monkeypatch.setattr("builtins.input", lambda p: next(inputs))
        result = ask_yes_no("Test")
        assert result is False

    def test_token_shaped_rejection_message_to_stderr(self, monkeypatch, capsys):
        """Token-shaped rejection выводит предупреждающее сообщение."""
        from src.sandbox.bootstrap.live_executor import ask_yes_no

        long_string = "A" * 80
        inputs = iter([long_string, "n"])

        monkeypatch.setattr("builtins.input", lambda p: next(inputs))
        ask_yes_no("Продолжить?")
        captured = capsys.readouterr()
        assert "учётные данные" in captured.out.lower() or "учетные данные" in captured.out.lower()


class TestCleanupPreviewLiveState:
    """cleanup --preview --local: state-файл с live-ключами не показывает planned_not_created."""

    def test_preview_with_live_resource_keys(self, tmp_path, capsys):
        """State-файл с supabase_project_ref, render_service_id, webhook_set → статус created."""
        state_file = tmp_path / ".bootstrap-state.json"
        state_data = {
            "schema_version": "1.0.0",
            "status": "applied",
            "resources": {
                "supabase_project_name": "my-sb-proj",
                "supabase_organization": "my-org",
                "render_web_service_name": "my-render-svc",
                "render_environment_group": "my-env",
                "webhook_target_url": "https://my-svc.onrender.com/webhook/telegram",
            },
            "supabase_project_ref": "ref-live-abc",
            "render_service_id": "srv-live-xyz",
            "webhook_set": True,
            "webhook_url": "https://my-svc.onrender.com/webhook/telegram",
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f)

        with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
            from src.sandbox.cli import async_main
            import asyncio
            import pytest
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(async_main())
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "supabase_project_name: my-sb-proj (Статус: created)" in captured.out, (
            f"Expected 'created' for supabase, got:\n{captured.out}"
        )
        assert "render_web_service_name: my-render-svc (Статус: created)" in captured.out
        assert "webhook_target_url: https://my-svc.onrender.com/webhook/telegram (Статус: created)" in captured.out
        assert "planned_not_created" not in captured.out
        assert "[MANUAL/FUTURE-LIVE]" in captured.out

    def test_preview_with_simulate_steps_still_works(self, tmp_path, capsys):
        """State-файл только с applied_steps (simulate режим) — по-прежнему created."""
        state_file = tmp_path / ".bootstrap-state.json"
        state_data = {
            "schema_version": "1.0.0",
            "status": "applied",
            "resources": {
                "supabase_project_name": "sim-sb-proj",
                "supabase_organization": "sim-org",
                "render_web_service_name": "sim-render-svc",
                "render_environment_group": "sim-env",
                "webhook_target_url": "https://sim-svc.local/webhook",
            },
            "applied_steps": [
                "supabase_sim_db_created",
                "render_sim_service_created",
                "telegram_sim_webhook_configured",
            ],
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f)

        with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
            from src.sandbox.cli import async_main
            import asyncio
            import pytest
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(async_main())
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "supabase_project_name: sim-sb-proj (Статус: created)" in captured.out
        assert "render_web_service_name: sim-render-svc (Статус: created)" in captured.out
        assert "webhook_target_url: https://sim-svc.local/webhook (Статус: created)" in captured.out
        assert "planned_not_created" not in captured.out
