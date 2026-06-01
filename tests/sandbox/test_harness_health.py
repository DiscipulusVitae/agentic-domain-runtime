import pytest
from src.sandbox.harness import SandboxHarness


@pytest.mark.asyncio
async def test_health_flow():
    harness = SandboxHarness()
    
    # Run harness with health record metadata
    result = await harness.run_flow("Запиши мое давление 120 на 80 и пульс 70")
    
    assert result["success"] is True
    assert result["routing"]["domain_id"] == "medical"
    assert "[routing: medical]" in result["trace"]
    assert "[extraction: success]" in result["trace"]
    assert "[validation: success]" in result["trace"]
    assert "[persistence: saved" in result["trace"]
    
    # Verify records in in-memory storage
    medical_service = harness.dp["medical_service"]
    entries = await medical_service.get_recent_entries(limit=10)
    assert len(entries) > 0
    
    last_entry = entries[0]
    assert last_entry.metric_type == "blood_pressure"
    assert last_entry.systolic == 120
    assert last_entry.diastolic == 80
    assert last_entry.pulse == 70


@pytest.mark.asyncio
async def test_synthetic_subject_extraction():
    harness = SandboxHarness()

    # 1. Test "self"
    result_self = await harness.run_flow("Запиши мое давление 120 на 80")
    assert result_self["success"] is True
    # To check subject extraction, we can check the output or get raw LLM response.
    # Let's inspect the medical entries or the response directly.
    # Harness returns medical_extraction via response.parsed inside run_flow, but run_flow returns a custom dict.
    # Let's see if we can get it from storage, or we can check the printed output:
    # "❤️ Запись успешно сохранена в sandbox для субъекта: Пользователь"
    assert "субъекта: Пользователь" in result_self["output"]

    # 2. Test "partner"
    result_partner = await harness.run_flow("Запиши давление партнера 130 на 85")
    assert result_partner["success"] is True
    assert "субъекта: Партнёр" in result_partner["output"]

    # 3. Test "relative"
    result_relative = await harness.run_flow("Запиши давление родственника 140 на 90")
    assert result_relative["success"] is True
    assert "субъекта: Родственник" in result_relative["output"]
