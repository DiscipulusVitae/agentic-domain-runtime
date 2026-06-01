import pytest
from src.sandbox.harness import SandboxHarness


@pytest.mark.asyncio
async def test_kitchen_flow():
    harness = SandboxHarness()
    result = await harness.run_flow("Добавь рецепт лимонной пасты с базиликом")
    
    assert result["success"] is True
    assert result["routing"]["domain_id"] == "kitchen"
    assert "[routing: kitchen]" in result["trace"]
    assert "[extraction: success]" in result["trace"]
    assert "[validation: success]" in result["trace"]
    assert "[persistence: saved" in result["trace"]
    assert "Лимонная паста с базиликом" in result["output"]
    assert len(harness.kitchen_db) == 1
    assert harness.kitchen_db[0].title == "Лимонная паста с базиликом"
    assert harness.kitchen_db[0].ingredients == ["лимон", "паста", "базилик"]


@pytest.mark.asyncio
async def test_kitchen_missing_title():
    harness = SandboxHarness()
    result = await harness.run_flow("Запиши рецепт")
    
    assert result["success"] is False
    assert result["routing"]["domain_id"] == "kitchen"
    assert "[validation: failed]" in result["trace"]
    assert "Какое блюдо вы хотите приготовить?" in result["output"]
