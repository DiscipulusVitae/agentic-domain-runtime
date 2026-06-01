import pytest
from src.sandbox.harness import SandboxHarness


@pytest.mark.asyncio
async def test_kitchen_stub():
    harness = SandboxHarness()
    result = await harness.run_flow("Запиши рецепт борща")
    
    assert result["success"] is True
    assert result["routing"]["domain_id"] == "kitchen"
    assert "kitchen: stub — interactive batching not included" in result["trace"]
    assert result.get("stub") is True
