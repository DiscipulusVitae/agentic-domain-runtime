import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_install_dry_run(patch_subprocess_run_ok, capsys):
    """Проверяет успешный запуск install --dry-run и человекочитаемый вывод (все 10 шагов)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "=== ADR Bootstrap Install Wizard (DRY-RUN) ===" in out
    assert "1. Подготовительный чек-лист (Upfront Checklist):" in out
    assert "2. Проверка локальных зависимостей (Doctor Prerequisites):" in out
    assert "3. Руководство по авторизации Supabase (Supabase Auth Guidance):" in out
    assert "4. Руководство по авторизации Render (Render Auth Guidance):" in out
    assert "5. Регистрация бота в Telegram (Telegram Bot Setup):" in out
    assert "6. Превью плана развертывания (Plan Preview):" in out
    assert "7. Граница явного подтверждения (Explicit Approval Boundary):" in out
    assert "8. Применение конфигурации (Apply Stage):" in out
    assert "9. Проверка работоспособности (Smoke Stage):" in out
    assert "10. Политика локального состояния (Local Ignored State Policy):" in out

    # Проверка отсутствия плейсхолдеров секретов
    assert ("TELEGRAM_" + "BOT_TOKEN=") not in out
    assert ("RENDER_" + "API_KEY=") not in out
    assert ("SUPABASE_" + "ACCESS_TOKEN=") not in out


@pytest.mark.asyncio
async def test_cli_bootstrap_install_dry_run_json(patch_subprocess_run_ok, capsys):
    """Проверяет успешный запуск install --dry-run --json и JSON вывод."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск мастера установки" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert len(steps) == 10

    expected_steps = [
        "upfront_checklist",
        "doctor_prerequisites",
        "supabase_auth_guidance",
        "render_auth_guidance",
        "telegram_botfather_step",
        "plan_preview",
        "explicit_approval_boundary",
        "apply_stage",
        "smoke_stage",
        "local_ignored_state_policy"
    ]
    for step_name in expected_steps:
        assert step_name in steps
        if step_name in ["upfront_checklist", "doctor_prerequisites", "supabase_auth_guidance", "render_auth_guidance", "telegram_botfather_step", "plan_preview"]:
            assert steps[step_name]["status"] == "ready"
        elif step_name == "explicit_approval_boundary":
            assert steps[step_name]["status"] == "requires_approval"
            assert steps[step_name]["boundary"] == "human_approval_boundary"
        elif step_name in ["apply_stage", "smoke_stage"]:
            assert steps[step_name]["status"] == "mutation_prevented"
            assert steps[step_name]["boundary"] == "future_live_mutation"
        elif step_name == "local_ignored_state_policy":
            assert steps[step_name]["status"] == "skipped"
            assert steps[step_name]["boundary"] == "offline_dry_run"

    # Проверка отсутствия секретных значений
    assert "token" not in captured.out.lower() or "запрашивается в install или через telegram_bot_token" in captured.out.lower()


@pytest.mark.asyncio
async def test_cli_bootstrap_install_no_dry_run_blocked(capsys):
    """Проверяет, что запуск bootstrap install без --dry-run заблокирован."""
    with patch("sys.argv", ["cli.py", "bootstrap", "install"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code != 0

    captured = capsys.readouterr()
    assert "Команда install требует указания флага --dry-run" in captured.err
