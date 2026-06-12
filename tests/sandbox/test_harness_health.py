import pytest
import os
import json
from unittest.mock import patch, AsyncMock
from src.sandbox.harness import SandboxHarness
from src.sandbox.fake_llm import FakeLLMClient, FakeResponse
from src.sandbox.contracts import MedicalExtraction, MedicalEntry


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


@pytest.mark.asyncio
async def test_health_flow_parsed_none():
    """Тест: если provider/client вернул parsed=None"""
    harness = SandboxHarness()

    original_send = FakeLLMClient.send_with_fallback

    async def mock_send(self, *args, **kwargs):
        if self.agent_id == "health.recorder":
            return FakeResponse(text="{}", parsed=None), "fake-model"
        return await original_send(self, *args, **kwargs)

    with patch.object(FakeLLMClient, "send_with_fallback", mock_send):
        result = await harness.run_flow("Запиши мое давление 120 на 80")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: failed]" in result["trace"]
    assert "[validation: failed]" in result["trace"]
    assert "[persistence: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_incomplete_extraction_empty():
    """Тест: если extraction incomplete (entries пустые)"""
    harness = SandboxHarness()

    original_send = FakeLLMClient.send_with_fallback

    async def mock_send(self, *args, **kwargs):
        if self.agent_id == "health.recorder":
            # Используем model_construct, чтобы обойти валидацию Pydantic на пустые записи
            extraction = MedicalExtraction.model_construct(
                raw_text="Запиши мое давление",
                confidence=1.0,
                entries=[]
            )
            return FakeResponse(text="{}", parsed=extraction), "fake-model"
        return await original_send(self, *args, **kwargs)

    with patch.object(FakeLLMClient, "send_with_fallback", mock_send):
        result = await harness.run_flow("Запиши мое давление")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: success]" in result["trace"]
    assert "[validation: failed]" in result["trace"]
    assert "[persistence: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_incomplete_extraction_partial():
    """Тест: если extraction incomplete (metric fields incomplete)"""
    harness = SandboxHarness()

    original_send = FakeLLMClient.send_with_fallback

    async def mock_send(self, *args, **kwargs):
        if self.agent_id == "health.recorder":
            # metric_type = blood_pressure требует systolic и diastolic для полноты
            entry = MedicalEntry(
                metric_type="blood_pressure",
                systolic=None, # Неполное поле
                diastolic=80
            )
            extraction = MedicalExtraction(
                raw_text="Давление на 80",
                confidence=1.0,
                entries=[entry]
            )
            return FakeResponse(text=extraction.model_dump_json(), parsed=extraction), "fake-model"
        return await original_send(self, *args, **kwargs)

    with patch.object(FakeLLMClient, "send_with_fallback", mock_send):
        result = await harness.run_flow("Давление на 80")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: success]" in result["trace"]
    assert "[validation: failed]" in result["trace"]
    assert "[persistence: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_openai_malformed_json():
    """Тест: если assistant content malformed JSON (через OpenAICompatibleLLMClient)"""
    harness = SandboxHarness()

    env_vars = {
        "ADR_LLM_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    butler_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"domain_id": "medical", "agent_id": "health.recorder", "intent": "add_entry", "confidence": 0.9}'
                }
            }
        ]
    }
    health_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "not a valid json" # Malformed JSON
                }
            }
        ]
    }

    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    with patch.dict(os.environ, env_vars):
        with patch.object(OpenAICompatibleLLMClient, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [json.dumps(butler_response), json.dumps(health_response)]

            result = await harness.run_flow("Запиши мое давление 120 на 80")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: failed]" in result["trace"]
    assert "[validation: failed]" in result["trace"]
    assert "[persistence: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_openai_invalid_validation():
    """Тест: если JSON валиден, но не проходит MedicalExtraction/entry validation (через OpenAICompatibleLLMClient)"""
    harness = SandboxHarness()

    env_vars = {
        "ADR_LLM_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    butler_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"domain_id": "medical", "agent_id": "health.recorder", "intent": "add_entry", "confidence": 0.9}'
                }
            }
        ]
    }
    # Нет entries/entry, что нарушает validation
    health_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"raw_text": "Запиши мое давление", "confidence": 1.0}'
                }
            }
        ]
    }

    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    with patch.dict(os.environ, env_vars):
        with patch.object(OpenAICompatibleLLMClient, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [json.dumps(butler_response), json.dumps(health_response)]

            result = await harness.run_flow("Запиши мое давление")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_openai_valid_persists():
    """Тест: если extraction валиден и complete, то сохранение происходит успешно (через OpenAICompatibleLLMClient)"""
    harness = SandboxHarness()

    env_vars = {
        "ADR_LLM_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    butler_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"domain_id": "medical", "agent_id": "health.recorder", "intent": "add_entry", "confidence": 0.9}'
                }
            }
        ]
    }

    extraction = MedicalExtraction(
        raw_text="Давление 120 на 80",
        confidence=1.0,
        entries=[
            MedicalEntry(
                metric_type="blood_pressure",
                systolic=120,
                diastolic=80
            )
        ]
    )

    health_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": extraction.model_dump_json()
                }
            }
        ]
    }

    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    with patch.dict(os.environ, env_vars):
        with patch.object(OpenAICompatibleLLMClient, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [json.dumps(butler_response), json.dumps(health_response)]

            result = await harness.run_flow("Давление 120 на 80")

    assert result["success"] is True
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: success]" in result["trace"]
    assert "[validation: success]" in result["trace"]
    assert "[persistence: saved (1 records)]" in result["trace"]
    assert len(harness.medical_db) == 1
    assert harness.medical_db[0].systolic == 120
    assert harness.medical_db[0].diastolic == 80


@pytest.mark.asyncio
async def test_health_flow_openai_all_models_failed_exception():
    """Тест: если все модели упали с исключением (исчерпан models fallback)"""
    harness = SandboxHarness()

    env_vars = {
        "ADR_LLM_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    butler_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"domain_id": "medical", "agent_id": "health.recorder", "intent": "add_entry", "confidence": 0.9}'
                }
            }
        ]
    }

    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    with patch.dict(os.environ, env_vars):
        with patch.object(OpenAICompatibleLLMClient, "_send_request", new_callable=AsyncMock) as mock_send:
            # Первый вызов (butler) успешен, второй (health.recorder) бросает RuntimeError
            mock_send.side_effect = [
                json.dumps(butler_response),
                RuntimeError("All models failed to return a valid response.")
            ]

            result = await harness.run_flow("Запиши мое давление 120 на 80")

    assert result["success"] is False
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: failed]" in result["trace"]
    assert "[validation: failed]" in result["trace"]
    assert "[persistence: failed]" in result["trace"]
    assert len(harness.medical_db) == 0


@pytest.mark.asyncio
async def test_health_flow_openai_markdown_json_cleaning():
    """Тест: очистка markdown-оберток ```json в OpenAICompatibleLLMClient"""
    harness = SandboxHarness()

    env_vars = {
        "ADR_LLM_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    butler_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '```json\n{"domain_id": "medical", "agent_id": "health.recorder", "intent": "add_entry", "confidence": 0.9}\n```'
                }
            }
        ]
    }

    extraction = MedicalExtraction(
        raw_text="Давление 120 на 80",
        confidence=1.0,
        entries=[
            MedicalEntry(
                metric_type="blood_pressure",
                systolic=120,
                diastolic=80
            )
        ]
    )

    health_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"```json\n{extraction.model_dump_json()}\n```"
                }
            }
        ]
    }

    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    with patch.dict(os.environ, env_vars):
        with patch.object(OpenAICompatibleLLMClient, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [json.dumps(butler_response), json.dumps(health_response)]

            result = await harness.run_flow("Давление 120 на 80")

    assert result["success"] is True
    assert result["routing"]["domain_id"] == "medical"
    assert "[extraction: success]" in result["trace"]
    assert "[validation: success]" in result["trace"]
    assert len(harness.medical_db) == 1
    assert harness.medical_db[0].systolic == 120
    assert harness.medical_db[0].diastolic == 80


@pytest.mark.asyncio
async def test_openai_client_default_system_prompts():
    """Тест: проверка заполнения system_prompt по умолчанию для разных агентов в OpenAICompatibleLLMClient"""
    from src.sandbox.openai_client import OpenAICompatibleLLMClient

    env_vars = {
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
    }

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "{}"
                }
            }
        ]
    }

    with patch.dict(os.environ, env_vars):
        client_butler = OpenAICompatibleLLMClient(agent_id="core.butler")
        with patch.object(client_butler, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json.dumps(mock_response)
            # Trigger system prompt initialization
            await client_butler.send_with_fallback(
                chat=None,
                message="test",
                current_model="test-model",
                history=[]
            )
            assert "Butler Core" in client_butler.system_prompt
            assert "domain_id" in client_butler.system_prompt

        client_health = OpenAICompatibleLLMClient(agent_id="health.recorder")
        with patch.object(client_health, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json.dumps(mock_response)
            await client_health.send_with_fallback(
                chat=None,
                message="test",
                current_model="test-model",
                history=[]
            )
            assert "Health Assistant" in client_health.system_prompt
            assert "entries" in client_health.system_prompt

        client_books = OpenAICompatibleLLMClient(agent_id="books.librarian")
        with patch.object(client_books, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json.dumps(mock_response)
            await client_books.send_with_fallback(
                chat=None,
                message="test",
                current_model="test-model",
                history=[]
            )
            assert "Librarian Assistant" in client_books.system_prompt

        client_kitchen = OpenAICompatibleLLMClient(agent_id="kitchen.recorder")
        with patch.object(client_kitchen, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json.dumps(mock_response)
            await client_kitchen.send_with_fallback(
                chat=None,
                message="test",
                current_model="test-model",
                history=[]
            )
            assert "Kitchen Assistant" in client_kitchen.system_prompt
