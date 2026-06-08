import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_doctor_ok(patch_subprocess_run_ok, capsys):
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
async def test_cli_bootstrap_doctor_json_ok(patch_subprocess_run_ok, capsys):
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
async def test_cli_bootstrap_doctor_optional_missing(patch_subprocess_run_fail, capsys):
    """Проверяет прохождение doctor при отсутствии опционального supabase CLI (неблокирующий FAIL)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   supabase" in captured.out
    assert "Внимание: Отсутствуют некоторые опциональные инструменты" in captured.out
    assert "Подсказка: Установите Supabase CLI через npm" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_doctor_critical_missing(patch_subprocess_run_critical_fail, capsys):
    """Проверяет падение doctor при отсутствии критического uv."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   uv" in captured.out
    assert "Ошибка: Обнаружены критические проблемы в локальном окружении" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_doctor_json_optional_missing(patch_subprocess_run_fail, capsys):
    """Проверяет doctor --json в случае отсутствия опциональных утилит."""
    with patch("sys.argv", ["cli.py", "bootstrap", "doctor", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["status"] == "success"
    assert data["checks"]["supabase"]["status"] == "FAIL"
    assert "hint" in data["checks"]["supabase"]
    assert "action" in data["checks"]["supabase"]


@pytest.mark.asyncio
async def test_cli_bootstrap_doctor_render_with_update_notice(patch_subprocess_run_render_update_notice, capsys):
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


@pytest.mark.asyncio
async def test_cli_bootstrap_doctor_python_fail(patch_subprocess_run_ok, capsys):
    """Проверяет падение doctor при версии Python < 3.13 (exit code 1)."""
    from collections import namedtuple
    VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro"])
    mock_version = VersionInfo(3, 12, 5)
    with patch("src.sandbox.bootstrap.sys.version_info", mock_version):
        with patch("sys.argv", ["cli.py", "bootstrap", "doctor"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Doctor ===" in captured.out
    assert "[FAIL]   python" in captured.out
    assert "Python версия 3.12.5 не удовлетворяет требованиям" in captured.out
