import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_dry_run(capsys):
    """Проверяет успешный запуск команды smoke --dry-run и человекочитаемый вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Smoke (DRY-RUN) ===" in out
    assert "Внимание: Это read-only симуляция smoke-тестов. Никакие внешние запросы не выполнялись." in out
    assert "Проверка локального рантайма" in out
    assert "http://127.0.0.1:8765/health" in out
    assert "Проверка облачного рантайма" in out
    assert "https://adr-bootstrap-app-" in out
    assert "/health" in out
    assert "Синтетический запрос к Telegram вебхуку" in out
    assert "/telegram-webhook" in out
    assert "Контролируемый запрос с невалидной нагрузкой" in out
    assert "Final Status Classification" in out
    assert "SUCCESS" in out
    assert "DEGRADED_WEBHOOK" in out
    assert "FAILURE" in out
    assert "Никакие секреты не выводятся, реальные вызовы не производятся." in out

    # Проверка отсутствия плейсхолдеров секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_dry_run_json(capsys):
    """Проверяет успешный запуск команды smoke --dry-run --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск smoke-тестов" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 4
    assert "local_runtime_health" in steps
    assert "cloud_runtime_health" in steps
    assert "synthetic_telegram_webhook" in steps
    assert "controlled_invalid_payload" in steps

    assert steps["local_runtime_health"]["details"]["expected_status"] == 200
    assert steps["local_runtime_health"]["boundary"] == "read_only_external_checks"
    assert steps["cloud_runtime_health"]["details"]["expected_status"] == 200
    assert steps["cloud_runtime_health"]["boundary"] == "read_only_external_checks"
    assert steps["synthetic_telegram_webhook"]["details"]["expected_status"] == 200
    assert steps["synthetic_telegram_webhook"]["boundary"] == "future_live_mutation"
    assert steps["controlled_invalid_payload"]["details"]["expected_status"] == 400
    assert steps["controlled_invalid_payload"]["boundary"] == "future_live_mutation"

    assert "success" in data["metadata"]["final_status_classification"]
    assert "degraded_webhook" in data["metadata"]["final_status_classification"]
    assert "failure" in data["metadata"]["final_status_classification"]


@pytest.mark.asyncio
async def test_cli_bootstrap_smoke_no_dry_run_fail(capsys):
    """Проверяет, что запуск bootstrap smoke без --dry-run падает с соответствующей ошибкой."""
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда smoke требует указания флага --dry-run" in captured.err


@pytest.mark.asyncio
async def test_bootstrap_smoke_plan_consistency(capsys):
    """Проверяет согласованность plan и smoke --dry-run по вебхуку и cloud health."""
    # Получаем plan
    with patch("sys.argv", ["cli.py", "bootstrap", "plan", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_plan = capsys.readouterr()
    plan_data = json.loads(captured_plan.out.strip())

    # Получаем smoke
    with patch("sys.argv", ["cli.py", "bootstrap", "smoke", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured_smoke = capsys.readouterr()
    smoke_data = json.loads(captured_smoke.out.strip())

    webhook_url = plan_data["update_modes"]["webhook_target_url"]
    expected_cloud_health = webhook_url.replace("/telegram-webhook", "/health")

    steps = {s["step_id"]: s for s in smoke_data["steps"]}

    assert steps["synthetic_telegram_webhook"]["details"]["target_url"] == webhook_url
    assert steps["controlled_invalid_payload"]["details"]["target_url"] == webhook_url
    assert steps["cloud_runtime_health"]["details"]["target_url"] == expected_cloud_health
