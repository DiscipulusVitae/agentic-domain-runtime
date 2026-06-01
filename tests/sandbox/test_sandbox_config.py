from src.sandbox.config import SandboxConfig

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
