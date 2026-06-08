import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_checks_ok(patch_subprocess_run_ok, capsys):
    """Проверяет успешный запуск команды checks --read-only и человекочитаемый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Checks (READ-ONLY) ===" in out
    assert "Внимание: Это read-only проверка готовности окружения. Никакие ресурсы не создаются." in out
    assert "Проверка наличия и версий CLI инструментов" in out
    assert "Наличие авторизации и переменных окружения" in out
    assert "Параметры планируемых целевых ресурсов" in out
    assert "Будущая проверка Supabase API" in out
    assert "Будущая проверка Render API" in out
    assert "Будущая проверка Telegram API" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_checks_json(patch_subprocess_run_ok, capsys):
    """Проверяет запуск команды checks --read-only --json, структуру JSON и отсутствие изменений."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "read_only" in data["metadata"]
    assert data["metadata"]["read_only"] is True

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 6

    expected_steps = [
        "cli_tools",
        "auth_env_presence",
        "planned_targets",
        "future_supabase_api_check",
        "future_render_api_check",
        "future_telegram_api_check"
    ]
    for step_name in expected_steps:
        assert step_name in steps

    assert steps["cli_tools"]["status"] == "ready"
    assert steps["cli_tools"]["boundary"] == "read_only_external_checks"
    assert steps["auth_env_presence"]["status"] == "ready"
    assert steps["auth_env_presence"]["boundary"] == "offline_dry_run"
    assert steps["planned_targets"]["status"] == "ready"
    assert steps["planned_targets"]["boundary"] == "offline_dry_run"

    for step_name in ["future_supabase_api_check", "future_render_api_check", "future_telegram_api_check"]:
        assert steps[step_name]["status"] == "mutation_prevented"
        assert steps[step_name]["boundary"] == "future_live_mutation"


@pytest.mark.asyncio
async def test_cli_bootstrap_checks_blocked(capsys):
    """Проверяет, что запуск bootstrap checks без --read-only заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда checks требует указания флага --read-only" in captured.err


@pytest.mark.asyncio
async def test_cli_bootstrap_checks_no_secrets(patch_subprocess_run_ok, capsys):
    """Проверяет, что секретные значения не выводятся в выводе checks."""
    # Установим фейковые переменные окружения
    with patch.dict("os.environ", {
        "SUPABASE_ACCESS_TOKEN": "secret_supabase_token_123",
        "RENDER_API_KEY": "secret_render_key_456",
        "TELEGRAM_BOT_TOKEN": "secret_bot_token_789",
        "DATABASE_URL": "postgresql://user:secret_password@host:5432/db"
    }):
        with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        out = captured.out
        # Убедимся, что сами секреты не выводятся
        assert "secret_supabase_token_123" not in out
        assert "secret_render_key_456" not in out
        assert "secret_bot_token_789" not in out
        assert "secret_password" not in out
        # Но наличие определяется корректно (present)
        assert "supabase_access_token_present : присутствует" in out
        assert "render_api_key_present        : присутствует" in out
        assert "telegram_bot_token_present    : присутствует" in out
        assert "database_url_present          : присутствует" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_checks_critical_missing(patch_subprocess_run_critical_fail, capsys):
    """Проверяет падение checks при отсутствии критического uv CLI (exit code 1)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "checks", "--read-only"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Checks (READ-ONLY) ===" in captured.out
    assert "Критические CLI инструменты не найдены" in captured.out
