import os
from dataclasses import dataclass, field

@dataclass
class SandboxConfig:
    """
    Configuration for the local reviewer sandbox environment.
    Does not require a .env file or real LLM credentials.
    """
    llm_provider: str = "fake"
    enabled_domains: list[str] = field(default_factory=lambda: ["kitchen", "books", "medical"])
    models_priority: list[str] = field(default_factory=list)
    gemini_models_priority: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Override defaults with environment variables if present
        if self.llm_provider == "fake":
            self.llm_provider = os.environ.get("ADR_LLM_PROVIDER", "fake")

        # Parse ADR_LLM_MODELS
        if not self.models_priority:
            env_models = os.environ.get("ADR_LLM_MODELS")
            if env_models:
                parsed_models = []
                for m in env_models.split(","):
                    m = m.strip()
                    if m:
                        parsed_models.append(m)
                self.models_priority = parsed_models
            else:
                self.models_priority = ["fake-model"]

        if not self.gemini_models_priority:
            self.gemini_models_priority = self.models_priority
