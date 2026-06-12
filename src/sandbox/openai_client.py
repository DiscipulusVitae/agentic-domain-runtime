import os
import urllib.request
import urllib.error
import json
import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("sandbox.openai_client")

class FakeResponse:
    """Stub response object containing .text and .parsed attributes."""
    def __init__(self, text: str, parsed: Any = None):
        self.text = text
        self.parsed = parsed

class FakeAsyncChat:
    """Stub chat session object."""
    pass

class OpenAICompatibleLLMClient:
    """
    OpenAI-compatible LLM Client for local sandbox.
    Supports model fallback and error handling.
    """
    def __init__(self, agent_id: str = "core.butler", config: Optional[Any] = None):
        self.agent_id = agent_id
        from src.sandbox.config import SandboxConfig
        self.config = config or SandboxConfig()
        self.system_prompt = ""
        self.schema_class = None

    def create_chat(
        self,
        model: str,
        history: Optional[list] = None,
        extra_context: Optional[str] = None,
    ) -> FakeAsyncChat:
        return FakeAsyncChat()

    async def send_with_fallback(
        self,
        chat: Any,
        message: Any,
        current_model: str,
        history: list,
        extra_context: Optional[str] = None,
    ) -> tuple[FakeResponse, str]:
        # Parse message to string
        if isinstance(message, str):
            message_str = message
        elif hasattr(message, "text") and message.text:
            message_str = message.text
        elif isinstance(message, list):
            text_parts = [p.text for p in message if hasattr(p, "text") and p.text]
            message_str = " ".join(text_parts) if text_parts else str(message)
        else:
            if hasattr(message, "parts") and message.parts:
                text_parts = [p.text for p in message.parts if hasattr(p, "text") and p.text]
                message_str = " ".join(text_parts) if text_parts else str(message)
            else:
                message_str = str(message)

        # Get the priority list of models
        models = getattr(self.config, "models_priority", [])
        if not models:
            models = getattr(self.config, "gemini_models_priority", [])
        if not models:
            models = ["fake-model"]

        base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("OPENAI_COMPATIBLE_BASE_URL environment variable is not set.")

        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json"
        }
        api_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        for h in history:
            if isinstance(h, dict):
                messages.append(h)
            elif hasattr(h, "role") and hasattr(h, "content"):
                messages.append({"role": h.role, "content": h.content})

        messages.append({"role": "user", "content": message_str})

        # Try models in order
        for model in models:
            payload = {
                "model": model,
                "messages": messages
            }
            try:
                response_text = await self._send_request(url, headers, payload)
                if not response_text:
                    logger.warning(f"Empty response from model {model}, trying next.")
                    continue

                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.warning(f"Malformed JSON response from model {model}, trying next.")
                    continue

                if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
                    logger.warning(f"Missing choices in response from model {model}, trying next.")
                    continue

                choice = data["choices"][0]
                if "message" not in choice or "content" not in choice["message"]:
                    logger.warning(f"Missing message content in response from model {model}, trying next.")
                    continue

                content = choice["message"]["content"]
                if content is None:
                    logger.warning(f"None content in response from model {model}, trying next.")
                    continue

                # Parse schemas if appropriate
                parsed_obj = None
                if self.agent_id == "books.librarian":
                    from src.sandbox.contracts import BookExtraction
                    try:
                        parsed_obj = BookExtraction.model_validate_json(content)
                    except Exception:
                        pass
                elif self.agent_id == "health.recorder":
                    from src.sandbox.contracts import MedicalExtraction
                    try:
                        parsed_obj = MedicalExtraction.model_validate_json(content)
                    except Exception:
                        pass
                elif self.agent_id == "kitchen.recorder":
                    from src.sandbox.contracts import RecipeDraft
                    try:
                        parsed_obj = RecipeDraft.model_validate_json(content)
                    except Exception:
                        pass

                return FakeResponse(text=content, parsed=parsed_obj), model

            except Exception as e:
                logger.warning(f"Request failed for model {model} due to error: {e}. Trying next.")
                continue

        # If all models failed
        raise RuntimeError("All models failed to return a valid response.")

    async def _send_request(self, url: str, headers: dict, payload: dict) -> str:
        def _sync_request():
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10.0) as response:
                return response.read().decode("utf-8")
        return await asyncio.to_thread(_sync_request)
