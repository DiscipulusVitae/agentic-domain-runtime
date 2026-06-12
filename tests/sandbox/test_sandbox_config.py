from src.sandbox.config import SandboxConfig
import os
from unittest.mock import patch

def test_default_values():
    """SandboxConfig() can be instantiated without arguments."""
    config = SandboxConfig()
    assert config is not None

def test_llm_provider_default_fake():
    """llm_provider defaults to 'fake'."""
    config = SandboxConfig()
    assert config.llm_provider == "fake"

def test_enabled_domains_default():
    """All three domains (kitchen, books, medical) are enabled by default."""
    config = SandboxConfig()
    assert config.enabled_domains == ["kitchen", "books", "medical"]

def test_llm_provider_env_override():
    """llm_provider is overridden by ADR_LLM_PROVIDER."""
    with patch.dict(os.environ, {"ADR_LLM_PROVIDER": "openai_compatible"}):
        config = SandboxConfig()
        assert config.llm_provider == "openai_compatible"

def test_models_priority_env_parsing():
    """models_priority is correctly parsed from ADR_LLM_MODELS including tiers."""
    with patch.dict(os.environ, {"ADR_LLM_MODELS": "model-x:free,model-y:premium, model-z"}):
        config = SandboxConfig()
        assert config.models_priority == ["model-x:free", "model-y:premium", "model-z"]
        assert config.gemini_models_priority == ["model-x:free", "model-y:premium", "model-z"]
