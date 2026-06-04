import pytest
from src.sandbox.fake_llm import FakeLLMClient
from src.sandbox.contracts import ButlerClassifierService


@pytest.mark.asyncio
async def test_kitchen_keyword_routing():
    """Input with kitchen-related keyword 'рецепт' resolves to kitchen domain."""
    client = FakeLLMClient(agent_id="core.butler")
    classifier = ButlerClassifierService(llm_client=client)
    result = await classifier.classify("Добавь новый рецепт пирога")
    assert result.domain == "kitchen"
    assert result.agent == "kitchen.recorder"
    assert result.confidence == 0.92
    assert not result.needs_clarification


@pytest.mark.asyncio
async def test_books_keyword_routing():
    """Input with book-related keyword 'книга' resolves to books domain."""
    client = FakeLLMClient(agent_id="core.butler")
    classifier = ButlerClassifierService(llm_client=client)
    result = await classifier.classify("Я прочитал интересную книгу вчера")
    assert result.domain == "books"
    assert result.agent == "books.librarian"
    assert result.confidence == 0.90
    assert not result.needs_clarification


@pytest.mark.asyncio
async def test_medical_keyword_routing():
    """Input with medical-related keyword 'давление' resolves to medical domain."""
    client = FakeLLMClient(agent_id="core.butler")
    classifier = ButlerClassifierService(llm_client=client)
    result = await classifier.classify("Моё давление сегодня 120/80")
    assert result.domain == "medical"
    assert result.agent == "health.recorder"
    assert result.confidence == 0.91
    assert not result.needs_clarification


@pytest.mark.asyncio
async def test_ambiguous_fallback():
    """Input with no keywords falls back to core.butler requesting clarification."""
    client = FakeLLMClient(agent_id="core.butler")
    classifier = ButlerClassifierService(llm_client=client)
    result = await classifier.classify("Привет, как дела?")
    assert result.domain is None
    assert result.agent == "core.butler"
    assert result.needs_clarification is True
    assert result.decision.requires_clarification is True


def test_create_chat_returns_stub():
    """create_chat does not crash and returns a stub object."""
    client = FakeLLMClient()
    chat = client.create_chat(model="fake-model")
    assert chat is not None


def test_config_attribute_exists():
    """config.gemini_models_priority is available and correct."""
    client = FakeLLMClient()
    assert hasattr(client, "config")
    assert client.config.gemini_models_priority == ["fake-model"]
