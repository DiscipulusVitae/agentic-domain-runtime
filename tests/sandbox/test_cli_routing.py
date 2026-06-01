import json
from pathlib import Path
from unittest.mock import patch
import pytest

from src.sandbox.fake_llm import FakeLLMClient
from src.sandbox.contracts import ButlerClassifierService
from src.sandbox.cli import find_scenario_file, run_scenario, async_main

FIXTURES_DIR = Path(__file__).parent.parent.parent / "src" / "sandbox" / "fixtures"


def load_all_scenarios():
    """Загружает все сценарии из JSON-файлов для параметризованных тестов."""
    scenarios = []
    # Если директория не существует в тестовом окружении, вернем пустой список
    if not FIXTURES_DIR.exists():
        return scenarios

    for path in FIXTURES_DIR.glob("*_scenarios.json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for idx, item in enumerate(data):
                # Добавляем id для лучшего отображения в pytest
                scenario_id = f"{path.stem}_{idx}"
                scenarios.append(pytest.param(item, id=scenario_id))
    return scenarios


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", load_all_scenarios())
async def test_parametrized_routing(scenario):
    """Параметризованный тест: проверяет классификацию каждого сценария."""
    client = FakeLLMClient(agent_id="core.butler")
    classifier = ButlerClassifierService(llm_client=client)
    result = await classifier.classify(scenario["input"], "text")
    assert result.domain == scenario["expected_domain"]
    assert result.agent == scenario["expected_agent"]


@pytest.mark.asyncio
async def test_cli_single_text_routing(capsys):
    """Проверяет работу CLI при классификации одиночного текста."""
    with patch("sys.argv", ["cli.py", "Добавь рецепт борща: свёкла, капуста"]):
        await async_main()

    captured = capsys.readouterr()
    assert "=== Sandbox Harness: Full Flow Run ===" in captured.out
    assert "Trace:  [routing: kitchen] -> [extraction: success] -> [validation: success] -> [persistence: saved (1 records)]" in captured.out
    assert "Domain:     kitchen" in captured.out
    assert "Agent:      kitchen.assistant" in captured.out
    assert "Confidence: 0.92" in captured.out
    assert "Success:      True" in captured.out


def test_cli_scenario_loading():
    """Проверяет загрузку и поиск файлов сценариев."""
    path = find_scenario_file("kitchen")
    assert path is not None
    assert path.exists()
    assert "kitchen_scenarios.json" in path.name

    path_by_full_name = find_scenario_file("kitchen_scenarios.json")
    assert path_by_full_name == path

    path_non_existent = find_scenario_file("non_existent_domain")
    assert path_non_existent is None


@pytest.mark.asyncio
async def test_cli_run_scenario(capsys):
    """Проверяет корректность запуска сценария через CLI."""
    path = find_scenario_file("kitchen")
    assert path is not None
    await run_scenario(path)

    captured = capsys.readouterr()
    assert "Запуск сценария: kitchen_scenarios.json" in captured.out
    assert "Expected Domain" in captured.out
    assert "kitchen.assistant" in captured.out
    assert "Итог: 4 из 4 пройдено." in captured.out
