"""Tests for PostHog SDK settings initialization."""

import posthog
import pytest

from find.settings import Base


@pytest.fixture(autouse=True)
def cleanup_test_index():
    """Shadow the conftest OpenSearch fixture — these tests don't need it."""
    yield


@pytest.fixture(autouse=True)
def _reset_posthog_module_state():
    """Reset posthog module-global state after each test to prevent leakage."""
    yield
    posthog.api_key = None
    posthog.host = None


@pytest.mark.parametrize(
    "env_vars",
    [
        {"POSTHOG_API_KEY": "phc_test"},
        {"POSTHOG_HOST": "https://eu.i.posthog.com"},
        {"POSTHOG_API_KEY": "", "POSTHOG_HOST": "https://eu.i.posthog.com"},
        {"POSTHOG_API_KEY": "phc_test", "POSTHOG_HOST": ""},
    ],
)
def test_posthog_stays_disabled_when_partial_config(monkeypatch, env_vars):
    """PostHog SDK must NOT initialize when config is incomplete."""
    for key, value in env_vars.items():
        monkeypatch.setattr(Base, key, value)
    Base.post_setup()
    assert posthog.api_key is None
    assert posthog.host is None


def test_posthog_initialized_when_both_set(monkeypatch):
    """PostHog SDK must initialize when both API key and host are set."""
    monkeypatch.setattr(Base, "POSTHOG_API_KEY", "phc_test_xyz")
    monkeypatch.setattr(Base, "POSTHOG_HOST", "https://eu.i.posthog.com")
    Base.post_setup()
    assert posthog.api_key == "phc_test_xyz"
    assert posthog.host == "https://eu.i.posthog.com"
