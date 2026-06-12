import os
import urllib.request
import urllib.error
import json
import asyncio
import logging
import re
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
        if not self.system_prompt:
            self.system_prompt = self._get_default_system_prompt(self.agent_id)

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

                # Strip markdown json blocks if present (e.g. ```json ... ```)
                content_clean = content.strip()
                if content_clean.startswith("```"):
                    content_clean = re.sub(r"^```(?:json)?\s*", "", content_clean)
                    content_clean = re.sub(r"\s*```$", "", content_clean)
                content_clean = content_clean.strip()

                # Parse schemas if appropriate
                parsed_obj = None
                if self.agent_id == "books.librarian":
                    from src.sandbox.contracts import BookExtraction
                    try:
                        parsed_obj = BookExtraction.model_validate_json(content_clean)
                    except Exception:
                        pass
                elif self.agent_id == "health.recorder":
                    from src.sandbox.contracts import MedicalExtraction
                    try:
                        parsed_obj = MedicalExtraction.model_validate_json(content_clean)
                    except Exception:
                        pass
                elif self.agent_id == "kitchen.recorder":
                    from src.sandbox.contracts import RecipeDraft
                    try:
                        parsed_obj = RecipeDraft.model_validate_json(content_clean)
                    except Exception:
                        pass

                return FakeResponse(text=content_clean, parsed=parsed_obj), model

            except Exception as e:
                logger.warning(f"Request failed for model {model} due to error: {e}. Trying next.")
                continue

        # If all models failed
        raise RuntimeError("All models failed to return a valid response.")

    def _get_default_system_prompt(self, agent_id: str) -> str:
        if agent_id == "core.butler":
            return (
                "You are Butler Core, a classifier and router for user messages.\n"
                "Analyze the user's input and respond with a JSON object conforming to the following structure:\n"
                "{\n"
                '  "domain_id": "kitchen" | "books" | "medical" | null,\n'
                '  "agent_id": "kitchen.recorder" | "books.librarian" | "health.recorder" | "core.butler",\n'
                '  "intent": "Brief intent description in Russian",\n'
                '  "confidence": float between 0.0 and 1.0,\n'
                '  "input_kind": "text" | "voice" | "photo" | "document" | "unknown",\n'
                '  "requires_clarification": boolean,\n'
                '  "clarification_question": "Russian clarification question if requires_clarification is true, else null"\n'
                "}\n\n"
                "Rules:\n"
                "1. If the input is about cooking, recipes, dishes, ingredients, route to domain_id=\"kitchen\", agent_id=\"kitchen.recorder\".\n"
                "2. If the input is about books, reading progress, authors, route to domain_id=\"books\", agent_id=\"books.librarian\".\n"
                "3. If the input is about health metrics (blood pressure, pulse, glucose, symptoms, notes), route to domain_id=\"medical\", agent_id=\"health.recorder\".\n"
                "4. If the input is ambiguous or not clear, set domain_id=null, agent_id=\"core.butler\", requires_clarification=true and ask a clarification question in Russian.\n"
                "5. Your response must be a single, valid JSON object without any additional text or formatting."
            )
        elif agent_id == "health.recorder":
            return (
                "You are Health Assistant. Extract medical metrics from the user's text and respond with a JSON object conforming to the following structure:\n"
                "{\n"
                '  "raw_text": "exactly the raw user input",\n'
                '  "subject_label": "Пользователь" | "Партнёр" | "Родственник" | null,\n'
                '  "subject_key": "self" | "partner" | "relative" | null,\n'
                '  "entries": [\n'
                "    {\n"
                '      "metric_type": "blood_pressure" | "glucose" | "note",\n'
                '      "systolic": integer or null,\n'
                '      "diastolic": integer or null,\n'
                '      "pulse": integer or null,\n'
                '      "glucose_value": float or null,\n'
                '      "glucose_unit": "mmol/L",\n'
                '      "glucose_context": "fasting" | "postprandial" | string context or null,\n'
                '      "note_text": string or null\n'
                "    }\n"
                "  ],\n"
                '  "confidence": float between 0.0 and 1.0,\n'
                '  "needs_confirmation": boolean,\n'
                '  "next_question": "Russian clarification question if data is missing or incomplete, else null"\n'
                "}\n\n"
                "Rules:\n"
                "1. Analyze the text for blood pressure (e.g., \"120 на 80\" or \"120/80\") or glucose values (e.g., \"5.6 натощак\") or simple notes.\n"
                "2. For blood pressure, metric_type must be \"blood_pressure\". Extract systolic, diastolic, pulse.\n"
                "3. For glucose, metric_type must be \"glucose\". Extract glucose_value (convert to float, e.g., 5.6) and context if present.\n"
                "4. If no specific metrics are found, create a \"note\" entry with note_text.\n"
                "5. Provide a list of \"entries\" (at least one entry is required).\n"
                "6. Set subject_key and subject_label based on the text: \"self\"/\"Пользователь\" for my/me/я/мое/у меня, \"partner\"/\"Партнёр\" for partner/spouse/husband/wife, \"relative\"/\"Родственник\" for other relatives.\n"
                "7. Return a single, valid JSON object without any additional text or formatting."
            )
        elif agent_id == "books.librarian":
            return (
                "You are Librarian Assistant. Extract book information from the user's text and respond with a JSON object conforming to the following structure:\n"
                "{\n"
                '  "title": string or null,\n'
                '  "author": string or null,\n'
                '  "description": string or null,\n'
                '  "year": integer or null,\n'
                '  "ready_to_save": boolean,\n'
                '  "next_question": "Russian clarification question if title or author is missing, else null"\n'
                "}\n\n"
                "Rules:\n"
                "1. Extract the title, author, description, and publication year if mentioned.\n"
                "2. Your response must be a single, valid JSON object without any additional text or formatting."
            )
        elif agent_id == "kitchen.recorder":
            return (
                "You are Kitchen Assistant. Extract recipe information from the user's text and respond with a JSON object conforming to the following structure:\n"
                "{\n"
                '  "title": string or null,\n'
                '  "ingredients": list of strings or null,\n'
                '  "instructions": string or null,\n'
                '  "ready_to_save": boolean,\n'
                '  "next_question": "Russian clarification question if title is missing, else null"\n'
                "}\n\n"
                "Rules:\n"
                "1. Extract the recipe title, list of ingredients, and instructions.\n"
                "2. Your response must be a single, valid JSON object without any additional text or formatting."
            )
        return ""

    async def _send_request(self, url: str, headers: dict, payload: dict) -> str:
        def _sync_request():
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10.0) as response:
                return response.read().decode("utf-8")
        return await asyncio.to_thread(_sync_request)
