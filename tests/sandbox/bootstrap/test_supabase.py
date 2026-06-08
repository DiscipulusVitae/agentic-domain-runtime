import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_local_dry_run(capsys):
    """Проверяет успешный текстовый вывод команды bootstrap supabase --local --dry-run."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Supabase Local Plan (DRY-RUN) ===" in out
    assert "Внимание: Это сухой запуск локального плана Supabase" in out
    assert "[OK] supabase/config.toml" in out
    assert "supabase start" in out
    assert "supabase stop" in out
    assert "disk-safe note" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_local_dry_run_json(capsys):
    """Проверяет успешный JSON вывод команды bootstrap supabase --local --dry-run --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск локального плана Supabase" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert "supabase_assets_check" in steps
    assert "supabase_command_plan" in steps
    assert steps["supabase_assets_check"]["status"] == "ready"
    assert steps["supabase_command_plan"]["status"] == "ready"
    assert steps["supabase_assets_check"]["details"]["assets"]["config"]["exists"] is True


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_flags_blocked(capsys):
    """Проверяет, что запуск без необходимых флагов блокируется."""
    for args in [
        ["cli.py", "bootstrap", "supabase"],
        ["cli.py", "bootstrap", "supabase", "--local"],
        ["cli.py", "bootstrap", "supabase", "--dry-run"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code != 0

        captured = capsys.readouterr()
        assert "Команда supabase требует указания флагов --local и --dry-run" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run")
async def test_cli_bootstrap_supabase_no_subprocess(mock_run, capsys):
    """Проверяет, что команда не выполняет системные вызовы (subprocess)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_file_failure(capsys):
    """Проверяет, что при отсутствии файлов возвращается код 1 и в выводе есть FAIL."""
    with patch("pathlib.Path.is_file", return_value=False):
        with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_supabase_missing_file_failure_json(capsys):
    """Проверяет, что в JSON при отсутствии файлов статус шага 'blocked' и возвращается код 1."""
    with patch("pathlib.Path.is_file", return_value=False):
        with patch("sys.argv", ["cli.py", "bootstrap", "supabase", "--local", "--dry-run", "--json"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["steps"][0]["status"] == "blocked"
