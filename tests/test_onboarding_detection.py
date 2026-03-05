"""Tests for first-launch detection logic."""


def _needs_onboarding(env: dict) -> bool:
    """Mirrors the logic we'll add to run.py."""
    return not env["groq_api_key"] and not env["openai_api_key"]


def test_needs_onboarding_when_no_keys():
    """Returns True when both API keys are empty."""
    env = {"groq_api_key": "", "openai_api_key": ""}
    assert _needs_onboarding(env) is True


def test_no_onboarding_when_groq_key_present():
    """Returns False when Groq key is set."""
    env = {"groq_api_key": "gsk_abc123", "openai_api_key": ""}
    assert _needs_onboarding(env) is False


def test_no_onboarding_when_openai_key_present():
    """Returns False when OpenAI key is set (Groq optional)."""
    env = {"groq_api_key": "", "openai_api_key": "sk-abc123"}
    assert _needs_onboarding(env) is False


def test_wizard_not_shown_when_key_already_configured():
    env = {"groq_api_key": "gsk_existing", "openai_api_key": ""}
    assert _needs_onboarding(env) is False


def test_wizard_shown_when_both_keys_missing():
    env = {"groq_api_key": "", "openai_api_key": ""}
    assert _needs_onboarding(env) is True
