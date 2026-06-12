import pytest
import os
import json
from unittest.mock import AsyncMock, patch
from src.sandbox.config import SandboxConfig
from src.sandbox.openai_client import OpenAICompatibleLLMClient

def json_dumps(data):
    return json.dumps(data)

@pytest.mark.asyncio
async def test_openai_client_success_first_model():
    """Client successfully returns response from the first model if it succeeds."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a", "model-b"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    # Mock response payload
    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"domain_id": "kitchen", "agent_id": "kitchen.recorder", "confidence": 0.9}'
                }
            }
        ]
    }

    env_vars = {
        "OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com",
        "OPENAI_COMPATIBLE_API_KEY": "test-key"
    }

    with patch.dict(os.environ, env_vars):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json_dumps(mock_response)

            response, active_model = await client.send_with_fallback(
                chat=None,
                message="hello",
                current_model="model-a",
                history=[]
            )

            assert active_model == "model-a"
            assert "kitchen" in response.text
            mock_send.assert_called_once()

            # Check headers
            args, kwargs = mock_send.call_args
            headers = args[1]
            assert headers["Authorization"] == "Bearer test-key"

            # Check payload model
            payload = args[2]
            assert payload["model"] == "model-a"

@pytest.mark.asyncio
async def test_openai_client_fallback_on_exception():
    """Client falls back to the next model if the first model fails with exception."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a", "model-b"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "success-content"
                }
            }
        ]
    }

    with patch.dict(os.environ, {"OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com"}):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            # First call raises an exception, second call succeeds
            mock_send.side_effect = [Exception("Transient error"), json_dumps(mock_response)]

            response, active_model = await client.send_with_fallback(
                chat=None,
                message="hello",
                current_model="model-a",
                history=[]
            )

            assert active_model == "model-b"
            assert response.text == "success-content"
            assert mock_send.call_count == 2

@pytest.mark.asyncio
async def test_openai_client_fallback_on_malformed_json():
    """Client falls back to the next model if the response JSON is malformed."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a", "model-b"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "success-content"
                }
            }
        ]
    }

    with patch.dict(os.environ, {"OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com"}):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            # First returns malformed JSON, second succeeds
            mock_send.side_effect = ["{invalid_json}", json_dumps(mock_response)]

            response, active_model = await client.send_with_fallback(
                chat=None,
                message="hello",
                current_model="model-a",
                history=[]
            )

            assert active_model == "model-b"
            assert response.text == "success-content"
            assert mock_send.call_count == 2

@pytest.mark.asyncio
async def test_openai_client_fallback_on_empty_choices():
    """Client falls back to the next model if the choices list is empty."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a", "model-b"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "success-content"
                }
            }
        ]
    }

    with patch.dict(os.environ, {"OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com"}):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            # First returns empty choices, second succeeds
            mock_send.side_effect = [json_dumps({"choices": []}), json_dumps(mock_response)]

            response, active_model = await client.send_with_fallback(
                chat=None,
                message="hello",
                current_model="model-a",
                history=[]
            )

            assert active_model == "model-b"
            assert response.text == "success-content"
            assert mock_send.call_count == 2

@pytest.mark.asyncio
async def test_openai_client_controlled_failure():
    """Client raises RuntimeError if all priority models fail."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a", "model-b"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    with patch.dict(os.environ, {"OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com"}):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [Exception("Error A"), Exception("Error B")]

            with pytest.raises(RuntimeError) as exc_info:
                await client.send_with_fallback(
                    chat=None,
                    message="hello",
                    current_model="model-a",
                    history=[]
                )

            assert "All models failed" in str(exc_info.value)
            assert mock_send.call_count == 2

@pytest.mark.asyncio
async def test_openai_client_no_authorization_header():
    """Client does not send Authorization header if API key is not configured."""
    config = SandboxConfig(
        llm_provider="openai_compatible",
        models_priority=["model-a"]
    )
    client = OpenAICompatibleLLMClient(agent_id="core.butler", config=config)

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "success"
                }
            }
        ]
    }

    # Remove API key from env using clear=True
    with patch.dict(os.environ, {"OPENAI_COMPATIBLE_BASE_URL": "http://mock-api.com"}, clear=True):
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = json_dumps(mock_response)

            await client.send_with_fallback(
                chat=None,
                message="hello",
                current_model="model-a",
                history=[]
            )

            args, kwargs = mock_send.call_args
            headers = args[1]
            assert "Authorization" not in headers
