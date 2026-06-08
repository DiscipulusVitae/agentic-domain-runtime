import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.sandbox.cli import async_main

@pytest.mark.asyncio
async def test_cli_bootstrap_state_lifecycle(tmp_path, capsys):
    """Тестирует жизненный цикл команды bootstrap state: dry-run, init, overwrite block, show, и отсутствие секретов."""
    state_file = tmp_path / ".bootstrap-state.json"

    # 1. dry-run не создает файл
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--dry-run", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert not state_file.exists()

    # 2. init создает файл
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert state_file.exists()

    # Проверим структуру созданного файла
    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema_version"] == "1.0.0"
    assert data["status"] == "initialized"
    assert "generated_at" in data
    assert "resources" in data
    assert "supabase_project_name" in data["resources"]
    assert "applied_steps" in data
    assert "steps_skeleton" in data

    # 3. init без флага --overwrite выдает ошибку при существующем НЕПУСТОМ файле
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    # 3b. init без флага --overwrite успешно выполняется на пустом существующем файле
    empty_state_file = tmp_path / "empty-state.json"
    empty_state_file.write_text("", encoding="utf-8")
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(empty_state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert empty_state_file.exists()

    # 3c. init без флага --overwrite успешно выполняется на файле, содержащем только whitespace
    whitespace_state_file = tmp_path / "whitespace-state.json"
    whitespace_state_file.write_text("   \n  \t ", encoding="utf-8")
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(whitespace_state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    assert whitespace_state_file.exists()

    # 4. init с флагом --overwrite работает на существующем НЕПУСТОМ файле
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--overwrite", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    # 5. show выводит человекочитаемый отчет
    capsys.readouterr()  # Сбросить кэш вывода
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "=== ADR Bootstrap State Show ===" in captured.out
    assert "Supabase Project:" in captured.out
    assert "Скелет шагов:" in captured.out

    # 6. show с флагом --json выводит JSON
    capsys.readouterr()
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--json", "--path", str(state_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    show_data = json.loads(captured.out.strip())
    assert show_data["schema_version"] == "1.0.0"
    assert show_data["status"] == "initialized"

    # 7. Секретные переменные окружения не записываются в файл и не считываются
    with patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "secret-bot-token-12345",
        "SUPABASE_ACCESS_TOKEN": "secret-sb-token-abcde",
        "RENDER_API_KEY": "secret-render-key-xyz"
    }):
        secret_state_file = tmp_path / ".bootstrap-state-secret.json"
        with patch("sys.argv", ["cli.py", "bootstrap", "state", "--init", "--path", str(secret_state_file)]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0

        # Проверим, что секреты не записались в файл
        with open(secret_state_file, "r", encoding="utf-8") as f:
            secret_content = f.read()
        assert "secret-bot-token-12345" not in secret_content
        assert "secret-sb-token-abcde" not in secret_content
        assert "secret-render-key-xyz" not in secret_content

        # Проверим, что секреты не выводятся в show
        capsys.readouterr()
        with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--json", "--path", str(secret_state_file)]):
            with pytest.raises(SystemExit) as exc_info:
                await async_main()
            assert exc_info.value.code == 0
        captured_show = capsys.readouterr()
        assert "secret-bot-token-12345" not in captured_show.out
        assert "secret-sb-token-abcde" not in captured_show.out
        assert "secret-render-key-xyz" not in captured_show.out

    # 8. Попытка вызвать show на несуществующем файле завершается с ошибкой
    non_existent_file = tmp_path / "does-not-exist.json"
    with patch("sys.argv", ["cli.py", "bootstrap", "state", "--show", "--path", str(non_existent_file)]):
        with pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1


def test_gitignore_contains_bootstrap_state():
    """Проверяет, что .bootstrap-state.json добавлен в .gitignore."""
    gitignore_path = Path(__file__).parent.parent.parent.parent / ".gitignore"
    assert gitignore_path.exists(), "Файл .gitignore не найден"
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".bootstrap-state.json" in content, ".bootstrap-state.json не найден в .gitignore"
