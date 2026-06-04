import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.sandbox.cli import async_main
from src.sandbox.bootstrap import run_doctor, run_plan


def mock_subprocess_run_ok(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = "render v2.18.0"
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


def mock_subprocess_run_fail(args, **kwargs):
    mock_res = MagicMock()
    cmd = args[0]
    if cmd == "supabase":
        mock_res.returncode = 1
        mock_res.stderr = "supabase not found"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "info":
        # CLI есть, но демон лежит
        mock_res.returncode = 1
        mock_res.stderr = "Cannot connect to the Docker daemon"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "--version":
        # Docker CLI нет совсем
        mock_res.returncode = 127
        mock_res.stderr = "docker command not found"
        mock_res.stdout = ""
    else:
        mock_res.returncode = 0
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_doctor_ok(mock_run, capsys):
    """Проверяет успешное прохождение doctor через CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[OK]     python" in captured.out
    assert "[OK]     uv" in captured.out
    assert "[OK]     docker" in captured.out
    assert "[OK]     supabase" in captured.out
    assert "[OK]     render" in captured.out
    assert "Локальное окружение готово к установке." in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_doctor_json_ok(mock_run, capsys):
    """Проверяет doctor --json в случае успеха."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["python"]["status"] == "OK"
    assert data["checks"]["docker"]["status"] == "OK"


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_fail)
async def test_cli_bootstrap_doctor_fail(mock_run, capsys):
    """Проверяет падение doctor при отсутствии supabase CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   supabase" in captured.out
    assert "Ошибка: Обнаружены критические проблемы в локальном окружении." in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_plan(mock_run, capsys):
    """Проверяет генерацию плана через CLI."""
    with patch("sys.argv", ["cli.py", "bootstrap", "plan"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Plan (DRY-RUN) ===" in captured.out
    assert "Внимание: Это read-only симуляция. Никакие ресурсы в облаке не будут созданы." in captured.out
    assert "Supabase Project Name:      adr-bootstrap-db-" in captured.out
    assert "TELEGRAM_UPDATE_MODE" in captured.out
    assert "BOT_TOKEN" in captured.out
    # Проверяем, что вывод read-only и не содержит реальных секретных значений (только имена)
    assert "token" not in captured.out.lower() or "telegram bot token (запрашивается в install или через telegram_bot_token)" in captured.out.lower()
    # Проверим, что нет никаких реальных значений для BOT_TOKEN или других секретных переменных
    assert "BOT_TOKEN=" not in captured.out


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_ok)
async def test_cli_bootstrap_plan_json(mock_run, capsys):
    """Проверяет plan --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "plan", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "adr-bootstrap-db-" in data["resources"]["supabase_project_name"]
    assert "TELEGRAM_UPDATE_MODE" in data["planned_env_vars"]
    assert "BOT_TOKEN" in data["planned_env_vars"]
    # Проверка на отсутствие секретных значений
    for var_name in data["planned_env_vars"]:
        assert var_name not in data or data[var_name] is None


def mock_subprocess_run_render_update_notice(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = (
            "render v2.18.0\n"
            "A newer version of the Render CLI is available.\n"
            "Please run 'npm install -g @renderinc/cli' to update."
        )
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.mark.asyncio
@patch("subprocess.run", side_effect=mock_subprocess_run_render_update_notice)
async def test_cli_bootstrap_doctor_render_with_update_notice(mock_run, capsys):
    """Проверяет, что doctor фильтрует update notice от render и оставляет только первую строку (версию)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["render"]["status"] == "OK"
    assert data["checks"]["render"]["message"] == "Render CLI доступен (render v2.18.0)"
