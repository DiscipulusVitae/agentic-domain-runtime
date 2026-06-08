import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_flags_blocked():
    """Проверяет, что cleanup без --preview или --local блокируется (код 2)."""
    for args in [
        ["cli.py", "bootstrap", "cleanup"],
        ["cli.py", "bootstrap", "cleanup", "--preview"],
        ["cli.py", "bootstrap", "cleanup", "--local"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_state_preview(capsys):
    """Проверяет no-state preview (без файла состояния, человекочитаемый вывод)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Rollback/Cleanup Preview ===" in captured.out
    assert "Источник состояния:  deterministic_plan" in captured.out
    assert "SKIPPED/NOT-CREATED" in captured.out
    assert "Созданные ресурсы отсутствуют, локальное состояние не требует изменений." in captured.out
    assert "локальное превью" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_existing_state_preview(tmp_path, capsys):
    """Проверяет existing-state preview с файлом состояния."""
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "applied",
        "resources": {
            "supabase_project_name": "test-sb-project",
            "supabase_organization": "test-sb-org",
            "render_web_service_name": "test-render-service",
            "render_environment_group": "test-render-env",
            "webhook_target_url": "https://test-render-service.local/webhook"
        },
        "applied_steps": ["supabase_sim_db_created", "render_sim_service_created"]
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "=== ADR Bootstrap Rollback/Cleanup Preview ===" in captured.out
    assert f"Источник состояния:  state_file: {state_file.name}" in captured.out
    assert "supabase_project_name: test-sb-project (Статус: created)" in captured.out
    assert "render_web_service_name: test-render-service (Статус: created)" in captured.out
    assert "webhook_target_url: https://test-render-service.local/webhook (Статус: planned_not_created)" in captured.out

    assert "[MANUAL/FUTURE-LIVE] Удаление веб-сервиса Render" in captured.out
    assert "[MANUAL/FUTURE-LIVE] Удаление проекта Supabase" in captured.out
    assert "[AUTOMATIC/LOCAL] Удаление локального файла состояния" in captured.out


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_json_shape(tmp_path, capsys):
    """Проверяет структуру JSON-вывода."""
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "initialized",
        "resources": {
            "supabase_project_name": "test-sb-proj",
            "supabase_organization": "test-sb-org",
            "render_web_service_name": "test-render-srv",
            "render_environment_group": "test-render-env",
            "webhook_target_url": "https://test-render-srv.local/webhook"
        },
        "applied_steps": []
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file), "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["source"] == f"state_file: {state_file.name}"
    assert data["state_path"] == state_file.name
    assert "supabase_project_name" in data["synthetic_resources"]
    assert data["synthetic_resources"]["supabase_project_name"]["value"] == "test-sb-proj"
    assert data["synthetic_resources"]["supabase_project_name"]["status"] == "planned_not_created"

    assert len(data["cleanup_steps"]) == 4
    step_ids = [step["step_id"] for step in data["cleanup_steps"]]
    assert step_ids == ["telegram", "render", "supabase", "state_file"]

    assert data["cleanup_steps"][0]["type"] == "skipped/not-created"
    assert data["cleanup_steps"][3]["type"] == "automatic/local"

    assert data["live_mutations_present"] is False
    assert "Внимание" in data["warning"]


@pytest.mark.asyncio
async def test_cli_bootstrap_cleanup_no_secrets_or_path_leak(tmp_path, capsys):
    """Проверяет отсутствие утечек абсолютных путей или секретов в выводе."""
    secret_token = "SUPABASE_" + "ACCESS_TOKEN" + "=" + "secret12345"
    state_file = tmp_path / "test-state.json"
    state_data = {
        "schema_version": "1.0.0",
        "status": "applied",
        "resources": {
            "supabase_project_name": "sb-proj",
            "supabase_organization": "sb-org",
            "render_web_service_name": "render-srv",
            "render_environment_group": "render-env",
            "webhook_target_url": "https://render-srv.local/webhook"
        },
        "applied_steps": []
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f)

    with patch("sys.argv", ["cli.py", "bootstrap", "cleanup", "--preview", "--local", "--state-path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()

    assert str(tmp_path) not in captured.out
    assert secret_token not in captured.out
    assert "SUPABASE_" + "ACCESS_TOKEN" not in captured.out
