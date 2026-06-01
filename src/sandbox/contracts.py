import json
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator, field_validator


# --- Butler Classifier contracts ---

class ButlerDecision(BaseModel):
    """
    Structured Butler Core decision.
    """
    domain_id: Optional[Literal["kitchen", "books", "medical"]] = Field(
        default=None,
        description="Domain identifier: kitchen | books | medical | null"
    )
    agent_id: Literal["kitchen.assistant", "books.cataloger", "medical.recorder", "core.butler"] = Field(
        default="core.butler",
        description="Agent identifier: kitchen.assistant | books.cataloger | medical.recorder | core.butler"
    )
    intent: str = Field(description="Brief intent description in Russian")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level 0.0-1.0")
    input_kind: Literal["text", "voice", "photo", "document", "unknown"] = Field(
        default="text",
        description="Input type: text | voice | photo | document | unknown"
    )
    requires_clarification: bool = Field(default=False, description="True if clarification is needed")
    clarification_question: Optional[str] = Field(default=None, description="Clarification question in Russian")

    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class ButlerClassifierResult:
    """
    Result of input classification by Butler classifier.
    """
    def __init__(
        self,
        decision: ButlerDecision = None,
        raw_llm_output: str = "",
        parse_error_type: str | None = None,
        parse_error_detail: str | None = None,
        llm_call_failed: bool = False
    ):
        self.decision = decision or ButlerDecision(
            domain_id=None,
            agent_id="core.butler",
            intent="unknown",
            confidence=0.0,
            input_kind="unknown",
            requires_clarification=True,
        )
        self.raw_llm_output = raw_llm_output
        self.parse_error_type = parse_error_type
        self.parse_error_detail = parse_error_detail
        self.llm_call_failed = llm_call_failed

    @property
    def is_valid(self) -> bool:
        return not self.llm_call_failed and self.parse_error_type is None

    @property
    def needs_clarification(self) -> bool:
        return self.decision.requires_clarification

    @property
    def domain(self) -> str | None:
        return self.decision.domain_id

    @property
    def agent(self) -> str:
        return self.decision.agent_id

    @property
    def confidence(self) -> float:
        return self.decision.confidence


class ButlerClassifierService:
    """
    Service for classifying free text input under Butler Core for local sandbox.
    """
    def __init__(self, confidence_threshold: float = 0.55, llm_client=None):
        self.confidence_threshold = confidence_threshold
        self.llm_client = llm_client

    async def classify(self, raw_text: str, input_kind: str = "text") -> ButlerClassifierResult:
        if self.llm_client is None:
            return ButlerClassifierResult(
                parse_error_type="llm_call",
                parse_error_detail="llm_client_not_configured",
                llm_call_failed=True,
            )

        try:
            priority = self.llm_client.config.gemini_models_priority
        except AttributeError:
            return ButlerClassifierResult(
                parse_error_type="llm_call",
                parse_error_detail="unavailable_config",
                llm_call_failed=True,
            )

        if not priority:
            return ButlerClassifierResult(
                parse_error_type="llm_call",
                parse_error_detail="empty_gemini_models_priority",
                llm_call_failed=True,
            )

        initial_model = priority[0]

        try:
            chat = self.llm_client.create_chat(model=initial_model)
        except Exception as e:
            return ButlerClassifierResult(
                parse_error_type="llm_call",
                parse_error_detail=type(e).__name__,
                llm_call_failed=True,
            )

        prompt = (
            f"[Тип ввода: {input_kind}]\n"
            f"[Длина: {len(raw_text)} символов]\n"
            f"{raw_text}"
        )

        try:
            response, active_model = await self.llm_client.send_with_fallback(
                chat=chat,
                message=prompt,
                current_model=initial_model,
                history=[],
            )
            llm_output = response.text or ""
        except Exception as e:
            return ButlerClassifierResult(
                raw_llm_output="",
                parse_error_type="llm_call",
                parse_error_detail=type(e).__name__,
                llm_call_failed=True,
            )

        try:
            data = json.loads(llm_output)
            decision = ButlerDecision(**data)
        except Exception as e:
            return ButlerClassifierResult(
                raw_llm_output=llm_output,
                parse_error_type="parse_error",
                parse_error_detail=str(e),
            )

        # Validate confidence threshold
        if decision.confidence < self.confidence_threshold:
            return ButlerClassifierResult(
                decision=self._fallback_decision(input_kind),
                raw_llm_output=llm_output,
                parse_error_type="low_confidence",
                parse_error_detail=f"confidence={decision.confidence:.2f}, threshold={self.confidence_threshold:.2f}"
            )

        return ButlerClassifierResult(
            decision=decision,
            raw_llm_output=llm_output,
        )

    def _fallback_decision(self, input_kind: str) -> ButlerDecision:
        return ButlerDecision(
            domain_id=None,
            agent_id="core.butler",
            intent="ambiguous",
            confidence=0.0,
            input_kind=input_kind,
            requires_clarification=True,
            clarification_question="Пожалуйста, уточните: это про рецепт, книгу или медицинскую запись?",
        )

    def is_confident(self, result: ButlerClassifierResult) -> bool:
        return result.is_valid and not result.needs_clarification and result.confidence >= self.confidence_threshold


# --- Books Domain contracts ---

class BookExtraction(BaseModel):
    """
    Result of book metadata extraction from free text.
    """
    title: Optional[str] = Field(default=None, description="Book title")
    author: Optional[str] = Field(default=None, description="Book author")
    description: Optional[str] = Field(default=None, description="Short book description")
    year: int | None = Field(default=None, ge=1000, le=3000, description="Publication year")
    ready_to_save: bool = Field(default=False, description="True if enough data is available to save")
    next_question: str | None = Field(default=None, description="Clarification question for missing data")

    @model_validator(mode="after")
    def ensure_ready_requires_required_fields(self) -> "BookExtraction":
        if self.ready_to_save:
            if not self.title or not self.author:
                raise ValueError("ready_to_save=True требует непустые title и author")
        return self


# --- Medical/Health Domain contracts ---

class MedicalEntry(BaseModel):
    """
    Single medical metric entry.
    """
    metric_type: Literal["blood_pressure", "glucose", "note"]
    systolic: Optional[int] = Field(default=None, ge=0, le=300, description="Systolic blood pressure")
    diastolic: Optional[int] = Field(default=None, ge=0, le=200, description="Diastolic blood pressure")
    pulse: Optional[int] = Field(default=None, ge=0, le=250, description="Pulse rate")
    glucose_value: Optional[float] = Field(default=None, ge=0, le=50, description="Glucose level (mmol/L)")
    glucose_unit: str = Field(default="mmol/L", description="Glucose units")
    glucose_context: Optional[str] = Field(default=None, max_length=100, description="Glucose context (e.g. fasting)")
    note_text: Optional[str] = Field(default=None, max_length=500, description="Note text")
    measured_at: Optional[str] = Field(default=None, description="Measurement ISO timestamp")


class MedicalExtraction(BaseModel):
    """
    Result of medical data extraction from free text.
    """
    raw_text: str = Field(description="Raw user text input")
    subject_label: Optional[str] = Field(default=None, max_length=50, description="Subject display label")
    subject_key: Optional[Literal["self", "partner", "relative"]] = Field(default=None, description="Subject key")
    entry: Optional[MedicalEntry] = Field(default=None, description="Backward compatibility single entry")
    entries: Optional[list[MedicalEntry]] = Field(default=None, description="List of extracted medical entries")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence 0.0-1.0")
    needs_confirmation: bool = Field(default=False, description="True if user confirmation is needed")
    next_question: Optional[str] = Field(default=None, max_length=200, description="Clarification question")

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def normalize_entry_and_entries(self) -> "MedicalExtraction":
        if self.entries is not None and len(self.entries) > 0:
            object.__setattr__(self, "entry", self.entries[0])
        elif self.entry is not None:
            object.__setattr__(self, "entries", [self.entry])
        return self

    @model_validator(mode="after")
    def ensure_entries_not_empty(self) -> "MedicalExtraction":
        if self.entries is None or len(self.entries) == 0:
            raise ValueError("extraction must contain at least one entry (установи entry или entries)")
        return self

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 2)

    @property
    def primary_entry(self) -> MedicalEntry:
        if self.entries is None or len(self.entries) == 0:
            raise AttributeError("No entries available")
        return self.entries[0]

    def is_complete(self) -> bool:
        if not self.entries:
            return False
        for e in self.entries:
            if e.metric_type == "blood_pressure":
                if e.systolic is None or e.diastolic is None:
                    return False
            elif e.metric_type == "glucose":
                if e.glucose_value is None:
                    return False
            elif e.metric_type == "note":
                if not (e.note_text and e.note_text.strip()):
                    return False
            else:
                return False
        return True
