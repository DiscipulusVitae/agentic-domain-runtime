"""Тесты TTY preflight gate: блокировка live interactive flows без TTY."""
import sys
from unittest.mock import patch

from src.sandbox.bootstrap.env_checks import is_tty_available, TTY_ERROR_MESSAGE


class TestTtyGate:
    """TTY preflight gate: блокирует live interactive flows без TTY."""

    def test_is_tty_available_when_all_fds_are_tty(self, monkeypatch):
        """is_tty_available возвращает True когда все fd — TTY."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
        assert is_tty_available() is True

    def test_is_tty_available_false_when_stdin_not_tty(self, monkeypatch):
        """is_tty_available возвращает False когда stdin не TTY (pipe)."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
        assert is_tty_available() is False

    def test_is_tty_available_false_when_stdout_not_tty(self, monkeypatch):
        """is_tty_available возвращает False когда stdout не TTY."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
        assert is_tty_available() is False

    def test_is_tty_available_false_when_stderr_not_tty(self, monkeypatch):
        """is_tty_available возвращает False когда stderr не TTY."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
        assert is_tty_available() is False

    def test_is_tty_available_safe_on_exception(self, monkeypatch):
        """is_tty_available не падает при исключении в isatty."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: 1 / 0)
        assert is_tty_available() is False

    def test_install_live_blocks_when_no_tty(self, monkeypatch):
        """run_install_live возвращает 1 в no-TTY окружении."""
        from src.sandbox.bootstrap.commands.install_live import run_install_live

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live.is_tty_available",
            lambda: False,
        )
        result = run_install_live(json_mode=False)
        assert result == 1

    def test_install_live_blocks_json_mode_when_no_tty(self, monkeypatch, capsys):
        """run_install_live в json_mode возвращает 1 + JSON error при no-TTY."""
        from src.sandbox.bootstrap.commands.install_live import run_install_live

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live.is_tty_available",
            lambda: False,
        )
        result = run_install_live(json_mode=True)
        assert result == 1
        captured = capsys.readouterr()
        output = captured.out.strip()
        assert '"error"' in output
        assert "tty_required" in output

    def test_error_message_stable(self):
        """TTY_ERROR_MESSAGE стабильно содержит ключевые фразы."""
        assert "TTY/PTY требуется" in TTY_ERROR_MESSAGE
        assert "no-TTY" in TTY_ERROR_MESSAGE
        assert "--dry-run" in TTY_ERROR_MESSAGE
        assert "runbook" in TTY_ERROR_MESSAGE.lower()

    def test_dry_run_not_affected_by_tty_gate(self):
        """--dry-run не проверяет TTY (gate только в run_install_live)."""
        from src.sandbox.bootstrap.commands.install import run_install

        result = run_install(dry_run=True, json_mode=False)
        assert result == 0

    def test_cleanup_live_blocks_when_no_tty(self, monkeypatch):
        """run_live_cleanup возвращает 1 в no-TTY окружении при наличии ресурсов."""
        from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"render_service_id": "srv-test"}):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup._print_cleanup_preview"):
                result = run_live_cleanup(preview=False, json_mode=False)
                assert result == 1

    def test_cleanup_no_resources_no_tty_no_input(self, monkeypatch):
        """cleanup без ресурсов + no-TTY: не вызывает input(), controlled return."""
        from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"supabase_skipped": True}):
            result = run_live_cleanup(preview=False, json_mode=False)
            assert result == 1

    def test_cleanup_missing_state_returns_code_2(self, monkeypatch):
        """Отсутствие state-файла — exit code 2."""
        from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value=None):
            result = run_live_cleanup(preview=False, json_mode=True)
            assert result == 2

    def test_cleanup_no_resources_json_mode_non_interactive(self, monkeypatch, capsys):
        """cleanup без ресурсов + json_mode: не вызывает input() даже с TTY."""
        from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: True,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"supabase_skipped": True}):
            result = run_live_cleanup(preview=False, json_mode=True)
            assert result == 0
            captured = capsys.readouterr()
            output = captured.out.strip()
            assert "nothing_to_cleanup" in output

    def test_cleanup_preview_not_affected_by_tty_gate(self, monkeypatch):
        """cleanup --live --preview bypass TTY gate (preview не требует TTY)."""
        from src.sandbox.bootstrap.commands.install_live_cleanup import run_live_cleanup

        monkeypatch.setattr(
            "src.sandbox.bootstrap.commands.install_live_cleanup.is_tty_available",
            lambda: False,
        )
        with patch("src.sandbox.bootstrap.commands.install_live_cleanup._load_bootstrap_state",
                   return_value={"render_service_id": "srv-test"}):
            with patch("src.sandbox.bootstrap.commands.install_live_cleanup._print_cleanup_preview"):
                result = run_live_cleanup(preview=True, json_mode=False)
                assert result == 0
