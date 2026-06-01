from dataclasses import dataclass, field

@dataclass
class SandboxConfig:
    """
    Configuration for the local reviewer sandbox environment.
    Does not require a .env file or real LLM credentials.
    """
    llm_provider: str = "fake"
    enabled_domains: list[str] = field(default_factory=lambda: ["kitchen", "books", "medical"])
    gemini_models_priority: list[str] = field(default_factory=lambda: ["fake-model"])
