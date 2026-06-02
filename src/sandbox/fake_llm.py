import json
import re
from typing import Any, Optional

from src.sandbox.contracts import BookExtraction, MedicalExtraction, MedicalEntry, RecipeDraft


class FakeResponse:
    """Stub response object containing .text and .parsed attributes."""
    def __init__(self, text: str, parsed: Any = None):
        self.text = text
        self.parsed = parsed


class FakeAsyncChat:
    """Stub chat session object."""
    pass


class FakeLLMConfig:
    """Stub config object with priority models list."""
    def __init__(self):
        self.gemini_models_priority = ["fake-model"]


class FakeLLMClient:
    """
    Fake LLM Client conforming to LLMClientProtocol by duck typing.
    Provides mock classification and structured data extraction for the sandbox.
    """
    def __init__(self, agent_id: str = "core.butler"):
        self.agent_id = agent_id
        self.config = FakeLLMConfig()
        
        self.agent_config = None
        self.system_prompt = ""
        self.messages = {
            "processing": "Обрабатываю запрос...",
            "processing_voice": "Обрабатываю голосовое сообщение...",
            "model_switched": "Переключено на модель {model}",
            "infra_error": "Временная ошибка ИИ. Пожалуйста, попробуйте позже.",
            "app_error": "Произошла ошибка приложения.",
            "parse_error": "Не удалось распознать ответ ИИ."
        }
        self.schema_class = None

    def create_chat(
        self,
        model: str,
        history: Optional[list] = None,
        extra_context: Optional[str] = None,
    ) -> FakeAsyncChat:
        """Create a stub chat session."""
        return FakeAsyncChat()

    async def send_with_fallback(
        self,
        chat: Any,
        message: Any,
        current_model: str,
        history: list,
        extra_context: Optional[str] = None,
    ) -> tuple[FakeResponse, str]:
        """
        Simulate sending a message to the LLM.
        """
        # Ensure we work with string message
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
        msg_lower = message_str.lower()

        # Extract input_kind if embedded in the prompt format (e.g. from Butler classifier)
        input_kind = "text"
        match = re.search(r"\[Тип ввода:\s*([^\]]+)\]", message_str)
        if match:
            input_kind = match.group(1).strip()

        if self.agent_id == "core.butler":
            # Keyword matching rules for router
            kitchen_keywords = ["рецепт", "блюдо", "кухн", "готов", "ингредиент", "борщ", "паст"]
            books_keywords = ["книг", "читал", "читаю", "автор", "страниц", "оруэлл", "пушкин"]
            medical_keywords = ["давлен", "пульс", "вес", "сон", "шаг", "здоров", "сахар", "глюкоз", "давление"]

            if any(kw in msg_lower for kw in kitchen_keywords):
                decision = {
                    "domain_id": "kitchen",
                    "agent_id": "kitchen.assistant",
                    "intent": "add_dish",
                    "confidence": 0.92,
                    "input_kind": input_kind,
                    "requires_clarification": False,
                    "clarification_question": None,
                }
            elif any(kw in msg_lower for kw in books_keywords):
                decision = {
                    "domain_id": "books",
                    "agent_id": "books.cataloger",
                    "intent": "add_book",
                    "confidence": 0.90,
                    "input_kind": input_kind,
                    "requires_clarification": False,
                    "clarification_question": None,
                }
            elif any(kw in msg_lower for kw in medical_keywords):
                decision = {
                    "domain_id": "medical",
                    "agent_id": "medical.recorder",
                    "intent": "capture_medical",
                    "confidence": 0.91,
                    "input_kind": input_kind,
                    "requires_clarification": False,
                    "clarification_question": None,
                }
            else:
                decision = {
                    "domain_id": None,
                    "agent_id": "core.butler",
                    "intent": "ambiguous",
                    "confidence": 0.3,
                    "input_kind": input_kind,
                    "requires_clarification": True,
                    "clarification_question": "Пожалуйста, уточните: это про рецепт, книгу или медицинскую запись?",
                }

            response_json = json.dumps(decision, ensure_ascii=False)
            return FakeResponse(text=response_json), "fake-model"

        elif self.agent_id == "books.cataloger":
            # Clean up typical command prefixes from the message first
            prefix_pattern = r'^(?:добавь(?:ть)?\s+(?:книгу\s+)?|добавить\s+(?:книгу\s+)?|книга\s+)'
            content_str = re.sub(prefix_pattern, '', message_str, flags=re.IGNORECASE).strip()

            title = None
            author = None
            description = None
            year = None

            # Look for quotes for title
            quotes_match = re.search(r'["\'«»“”]([^"\'«»“”]+)["\'«»“”]', content_str)
            if quotes_match:
                title = quotes_match.group(1).strip()
                remaining_str = content_str.replace(quotes_match.group(0), "")
            else:
                remaining_str = content_str

            parts = [p.strip() for p in remaining_str.split(",") if p.strip()]

            if not title and len(parts) > 0:
                title = parts[0]
                parts = parts[1:]

            if len(parts) > 0:
                author = parts[0]
                parts = parts[1:]

            # Extract year from the remaining parts
            for i, part in enumerate(parts):
                year_match = re.search(r'\b(1\d{3}|20[0-2]\d)\b', part)
                if year_match:
                    year = int(year_match.group(1))
                    parts[i] = part.replace(year_match.group(0), "").strip()
                    break

            # If year wasn't found in remaining parts, but was found in content_str (excluding title)
            if year is None and title:
                clean_content = content_str.replace(title, "")
                year_match = re.search(r'\b(1\d{3}|20[0-2]\d)\b', clean_content)
                if year_match:
                    year = int(year_match.group(1))

            # Filter out empty strings from parts for description
            remaining_parts = [p for p in parts if p]
            if len(remaining_parts) > 0:
                description = ", ".join(remaining_parts)

            if title:
                title = title.strip('"\'«»“”')
            if author:
                author = author.strip('"\'«»“”')

            # Provide fallbacks if missing but matches typical names
            if not title:
                title = "2094"
            if not author:
                if "оруэлл" in msg_lower or "дистопик" in msg_lower:
                    author = "Артур Дистопик"
                elif "толстой" in msg_lower or "классик" in msg_lower:
                    author = "Виктор Классик"
                elif "пушкин" in msg_lower or "поэт" in msg_lower:
                    author = "Александр Поэт"
                else:
                    author = "Неизвестный Автор"

            ready_to_save = bool(title and author)
            next_question = None if ready_to_save else "Пожалуйста, укажите автора книги."

            parsed_obj = BookExtraction(
                title=title,
                author=author,
                description=description,
                year=year,
                ready_to_save=ready_to_save,
                next_question=next_question
            )

            # Return serialized JSON and the parsed Pydantic object
            response_json = parsed_obj.model_dump_json()
            return FakeResponse(text=response_json, parsed=parsed_obj), "fake-model"

        elif self.agent_id == "medical.recorder":
            # Extract subject
            subject_key = None
            subject_label = None
            if any(alias in msg_lower for alias in ["я", "self", "пользователь", "мое", "моё", "мой", "у меня", "меня"]):
                subject_key = "self"
                subject_label = "Пользователь"
            elif any(alias in msg_lower for alias in ["partner", "партнер", "партнёр", "супруг", "муж", "жена"]):
                subject_key = "partner"
                subject_label = "Партнёр"
            elif any(alias in msg_lower for alias in ["relative", "родственник", "мама", "папа", "сын", "дочь", "брат", "сестра"]):
                subject_key = "relative"
                subject_label = "Родственник"

            entries = []
            
            # Detect what metrics are present in the text
            has_bp = any(kw in msg_lower for kw in ["давлен", "пульс"]) or re.search(r'\b\d{2,3}\s*(?:на|/|\\)\s*\d{2,3}\b', msg_lower)
            has_glucose = any(kw in msg_lower for kw in ["сахар", "глюкоз"]) or re.search(r'\b\d{1,2}[.,]\d{1,2}\b', msg_lower)

            if has_bp:
                systolic = None
                diastolic = None
                pulse = None

                # Find BP e.g. 120/80, 120 на 80
                bp_match = re.search(r'(\d{2,3})\s*(?:на|/|\\)\s*(\d{2,3})', msg_lower)
                if bp_match:
                    systolic = int(bp_match.group(1))
                    diastolic = int(bp_match.group(2))
                else:
                    nums = re.findall(r'\b\d{2,3}\b', msg_lower)
                    if len(nums) >= 2:
                        systolic = int(nums[0])
                        diastolic = int(nums[1])
                
                # Find pulse
                pulse_match = re.search(r'(?:пульс|p|п)\s*[:=-]?\s*(\d{2,3})', msg_lower)
                if pulse_match:
                    pulse = int(pulse_match.group(1))
                else:
                    nums = re.findall(r'\b\d{2,3}\b', msg_lower)
                    if len(nums) >= 3:
                        pulse = int(nums[2])

                # Fallback defaults if they couldn't be parsed
                if systolic is None:
                    systolic = 120
                if diastolic is None:
                    diastolic = 80

                entries.append(MedicalEntry(
                    metric_type="blood_pressure",
                    systolic=systolic,
                    diastolic=diastolic,
                    pulse=pulse,
                    measured_at=None
                ))

            if has_glucose:
                glucose_value = None
                glucose_context = None

                # Find decimal number
                g_match = re.search(r'(\d+(?:[.,]\d+)?)', msg_lower)
                if g_match:
                    val_str = g_match.group(1).replace(",", ".")
                    try:
                        glucose_value = float(val_str)
                    except ValueError:
                        pass
                
                if glucose_value is None:
                    g_match_int = re.search(r'\b\d{1,2}\b', msg_lower)
                    if g_match_int:
                        glucose_value = float(g_match_int.group(0))

                if glucose_value is None:
                    glucose_value = 5.5

                contexts = ["натощак", "после еды", "перед сном", "утром", "вечером"]
                for ctx in contexts:
                    if ctx in msg_lower:
                        glucose_context = ctx
                        break

                entries.append(MedicalEntry(
                    metric_type="glucose",
                    glucose_value=glucose_value,
                    glucose_unit="mmol/L",
                    glucose_context=glucose_context,
                    measured_at=None
                ))

            if not entries:
                # Default to note if nothing else
                entries.append(MedicalEntry(
                    metric_type="note",
                    note_text=message_str,
                    measured_at=None
                ))

            parsed_obj = MedicalExtraction(
                raw_text=message_str,
                subject_key=subject_key,
                subject_label=subject_label,
                entries=entries,
                confidence=1.0,
                needs_confirmation=False,
                next_question=None
            )

            response_json = parsed_obj.model_dump_json()
            return FakeResponse(text=response_json, parsed=parsed_obj), "fake-model"

        elif self.agent_id == "kitchen.assistant":
            # Clean up typical command prefixes from the message first
            prefix_pattern = r'^(?:добавь(?:ть)?(?:\s+рецепт)?|добавить(?:\s+рецепт)?|запиши(?:ть)?(?:\s+рецепт)?|записать(?:\s+рецепт)?|рецепт)\b\s*'
            content_str = re.sub(prefix_pattern, '', message_str, flags=re.IGNORECASE).strip()

            title = None
            ingredients = []
            instructions = None

            # Detect by keywords first for higher accuracy in scenarios
            if "лимонной пасты" in msg_lower or "лимонная паста" in msg_lower:
                title = "Лимонная паста с базиликом"
                ingredients = ["лимон", "паста", "базилик"]
            elif "яблочного пирога" in msg_lower or "яблочный пирог" in msg_lower:
                title = "Яблочный пирог с корицей"
                ingredients = ["яблоки", "корица", "мука", "сахар"]
            elif "салат" in msg_lower:
                title = "Салат"
                ingredients = ["огурец", "помидор", "оливковое масло"]
            elif "борщ" in msg_lower:
                title = "Борщ"
                ingredients = ["свекла", "капуста", "картофель", "мясо"]
            elif "пюре" in msg_lower:
                title = "Пюре"
                ingredients = ["картофель", "молоко", "сливочное масло"]
            elif "суп" in msg_lower:
                title = "Суп"
                ingredients = []

            # If there's a colon, we try parsing ingredients from the second part
            if ":" in content_str:
                parts = content_str.split(":", 1)
                before_colon = parts[0].strip()
                after_colon = parts[1].strip()
                
                # If title is not set by keyword, try extracting it from before_colon
                if not title:
                    # Clean before_colon
                    clean_title = re.sub(r'^(?:ингредиенты для\s+|ингредиенты\s+)', '', before_colon, flags=re.IGNORECASE).strip()
                    if clean_title:
                        title = clean_title
                
                # Parse ingredients from after_colon
                if after_colon:
                    parsed_ingredients = [i.strip() for i in after_colon.split(",") if i.strip()]
                    if parsed_ingredients:
                        ingredients = parsed_ingredients

            # If title is still not extracted, use content_str as title
            if not title and content_str:
                title = content_str

            ready_to_save = bool(title)
            next_question = None if ready_to_save else "Какое блюдо вы хотите приготовить?"

            parsed_obj = RecipeDraft(
                title=title,
                ingredients=ingredients if ingredients else None,
                instructions=instructions,
                ready_to_save=ready_to_save,
                next_question=next_question
            )

            response_json = parsed_obj.model_dump_json()
            return FakeResponse(text=response_json, parsed=parsed_obj), "fake-model"

        else:
            # Fallback for any other agent
            decision = {
                "domain_id": None,
                "agent_id": self.agent_id,
                "intent": "unknown",
                "confidence": 0.0,
                "input_kind": input_kind,
                "requires_clarification": True,
                "clarification_question": "Unknown agent routing",
            }
            response_json = json.dumps(decision, ensure_ascii=False)
            return FakeResponse(text=response_json), "fake-model"
