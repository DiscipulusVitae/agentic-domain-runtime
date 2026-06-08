import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_operator_render_dry_run(capsys):
    """Проверяет Render operator cleanroom plan без login/API/mutation."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "=== ADR Operator Cleanroom Plan (RENDER / DRY-RUN) ===" in out
    assert "No login, external API call, or cloud mutation is executed." in out
    assert "Runtime image remains application-only" in out
    assert "Start clean operator/deployer shell" in out
    assert "Render CLI presence" in out
    assert "Render login and account confirmation" in out
    assert "Future Phase 1 Render /health smoke" in out
    assert "render whoami" in out
    assert "GATE: future Render mutation requires clean account confirmation and separate explicit GO." in out

    assert "TELEGRAM_" + "BOT_TOKEN=" not in out
    assert "RENDER_" + "API_KEY=" not in out
    assert "SUPABASE_" + "ACCESS_TOKEN=" not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_operator_render_dry_run_json(capsys):
    """Проверяет JSON-вывод Render operator cleanroom plan."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["dry_run"] is True
    assert data["metadata"]["target"] == "render"
    assert data["metadata"]["live_mutation_executed"] is False

    steps = {step["step_id"]: step for step in data["steps"]}
    assert steps["separate_runtime_image"]["boundary"] == "offline_dry_run"
    assert steps["operator_cleanroom_start"]["boundary"] == "offline_dry_run"
    assert steps["render_cli_presence"]["boundary"] == "read_only_external_checks"
    assert steps["render_login_identity_gate"]["boundary"] == "human_approval_boundary"
    assert steps["render_login_identity_gate"]["status"] == "requires_approval"
    assert steps["phase1_render_smoke_gate"]["boundary"] == "future_live_mutation"
    assert steps["phase1_render_smoke_gate"]["status"] == "requires_approval"


@pytest.mark.asyncio
async def test_cli_bootstrap_operator_requires_flags(capsys):
    """Проверяет, что operator без обязательных флагов заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "operator", "--render"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда operator требует указания флагов --render и --dry-run" in captured.err
