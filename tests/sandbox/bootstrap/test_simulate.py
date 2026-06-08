import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_no_local():
    """Проверяет, что simulate без --local завершается с ошибкой (код 2 из argparse)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_happy_path(capsys):
    """Проверяет успешный happy path симуляции (human-readable)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Simulation (LOCAL-ONLY) ===" in captured.out
    assert "PLAN [SUCCESS]" in captured.out
    assert "PREFLIGHT [SUCCESS]" in captured.out
    assert "APPLY [SUCCESS]" in captured.out
    assert "VERIFY [SUCCESS]" in captured.out
    assert "ROLLBACK [SUCCESS]" in captured.out
    assert "Симуляция завершена УСПЕШНО" in captured.out

    # Проверим, что временный файл состояния симуляции был корректно удален
    assert not Path(".bootstrap-state-sim.json").exists()


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_happy_path_json(capsys):
    """Проверяет успешный happy path симуляции в формате JSON."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["simulation"] == "local-only-synthetic"
    assert data["fail_after_apply"] is False
    assert data["success"] is True
    assert data["final_state"] == "ROLLED_BACK"

    # Проверяем фазы
    phases = [step["phase"] for step in data["steps"]]
    assert phases == ["plan", "preflight", "apply", "verify", "rollback"]

    # Все фазы должны быть success
    for step in data["steps"]:
        assert step["status"] == "success"

    assert not Path(".bootstrap-state-sim.json").exists()


@pytest.mark.asyncio
async def test_cli_bootstrap_simulate_fail_path_json(capsys):
    """Проверяет сбой верификации и автоматический откат в формате JSON."""
    with patch("sys.argv", ["cli.py", "bootstrap", "simulate", "--local", "--fail-after-apply", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["simulation"] == "local-only-synthetic"
    assert data["fail_after_apply"] is True
    assert data["success"] is False
    assert data["final_state"] == "ROLLED_BACK"

    # Verify фаза должна быть failed, а apply и rollback - success
    steps = {step["phase"]: step for step in data["steps"]}
    assert steps["apply"]["status"] == "success"
    assert steps["verify"]["status"] == "failed"
    assert steps["rollback"]["status"] == "success"

    assert not Path(".bootstrap-state-sim.json").exists()


def test_gitignore_contains_bootstrap_state_sim():
    """Проверяет, что .bootstrap-state-sim.json добавлен в .gitignore."""
    gitignore_path = Path(__file__).parent.parent.parent.parent / ".gitignore"
    assert gitignore_path.exists()
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".bootstrap-state-sim.json" in content, ".bootstrap-state-sim.json не найден в .gitignore"
