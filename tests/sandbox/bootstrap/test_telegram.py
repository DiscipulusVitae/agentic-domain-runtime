import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_dry_run(capsys):
    """Проверяет успешный текстовый вывод команды bootstrap telegram --webhook --dry-run."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "=== ADR Bootstrap Telegram Webhook Readiness (DRY-RUN) ===" in out
    assert "Внимание: Это сухой запуск (dry-run) настройки Telegram вебхука" in out
    assert "Ручная настройка бота через @BotFather (guidance only)" in out
    assert "Token Handoff Policy" in out
    assert "Планируемый URL для вебхука Telegram" in out
    assert "Планируемые действия с Telegram API" in out
    assert "Связь готовности с проверками smoke" in out


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_dry_run_json(capsys):
    """Проверяет успешный JSON вывод команды bootstrap telegram --webhook --dry-run --json."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run", "--json"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["dry_run"] is True
    assert "Это сухой запуск (dry-run) настройки Telegram вебхука" in data["message"]

    steps = {s["step_id"]: s for s in data["steps"]}
    assert "telegram_botfather_guidance" in steps
    assert "token_handoff_policy" in steps
    assert "planned_webhook_url" in steps
    assert "future_telegram_api_actions" in steps
    assert "smoke_readiness_relation" in steps

    assert steps["telegram_botfather_guidance"]["status"] == "requires_approval"
    assert steps["token_handoff_policy"]["status"] == "ready"
    assert steps["planned_webhook_url"]["status"] == "ready"
    assert steps["future_telegram_api_actions"]["status"] == "mutation_prevented"
    assert steps["smoke_readiness_relation"]["status"] == "ready"


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_missing_flags_blocked(capsys):
    """Проверяет, что запуск команды telegram без необходимых флагов блокируется."""
    for args in [
        ["cli.py", "bootstrap", "telegram"],
        ["cli.py", "bootstrap", "telegram", "--webhook"],
        ["cli.py", "bootstrap", "telegram", "--dry-run"],
    ]:
        with patch("sys.argv", args):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code != 0

        captured = capsys.readouterr()
        assert "Команда telegram требует указания флагов --webhook и --dry-run" in captured.err


@pytest.mark.asyncio
@patch("subprocess.run")
async def test_cli_bootstrap_telegram_no_subprocess(mock_run, capsys):
    """Проверяет, что команда telegram не выполняет системные вызовы (subprocess)."""
    with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_cli_bootstrap_telegram_no_token_leak(capsys):
    """Проверяет, что в выводе команды telegram нет значений токенов, даже если они заданы."""
    custom_env = {
        "TELEGRAM_BOT_TOKEN": "leak_secret_tg_token_987",
        "BOT_TOKEN": "leak_secret_bot_token_654"
    }
    with patch.dict("os.environ", custom_env):
        with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        out = captured.out
        assert "leak_secret_tg_token_987" not in out
        assert "leak_secret_bot_token_654" not in out

        # Также проверим для JSON вывода
        with patch("sys.argv", ["cli.py", "bootstrap", "telegram", "--webhook", "--dry-run", "--json"]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        captured_json = capsys.readouterr()
        assert "leak_secret_tg_token_987" not in captured_json.out
        assert "leak_secret_bot_token_654" not in captured_json.out
