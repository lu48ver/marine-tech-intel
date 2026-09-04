"""Tests for the shared LLM client: provider selection and lenient JSON parsing."""

import pytest

from scripts import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Isolate from real keys/files so tests never depend on local config."""
    for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "PROJECT_ROOT", tmp_path)


# ---------- provider selection ----------

def test_no_key_returns_none():
    assert llm.resolve_provider() is None


def test_openrouter_preferred_over_openai(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    provider = llm.resolve_provider()
    assert provider["name"] == "openrouter"
    assert provider["base_url"] == llm.OPENROUTER_BASE_URL
    assert all(m.endswith(":free") for m in provider["models"])


def test_openai_used_when_only_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    provider = llm.resolve_provider()
    assert provider["name"] == "openai"
    assert provider["base_url"] is None
    assert provider["models"] == [llm.OPENAI_DEFAULT_MODEL]


def test_key_read_from_local_file(tmp_path):
    (tmp_path / ".openrouter_key").write_text("file-key\n", encoding="utf-8")
    provider = llm.resolve_provider()
    assert provider["name"] == "openrouter"
    assert provider["api_key"] == "file-key"


def test_llm_model_override_builds_chain(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("LLM_MODEL", "a/model:free, b/model:free")
    assert llm.resolve_provider()["models"] == ["a/model:free", "b/model:free"]


def test_legacy_openai_model_env_still_honoured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    assert llm.resolve_provider()["models"] == ["gpt-4o"]


# ---------- lenient JSON parsing (free models are chattier) ----------

def test_parse_plain_json():
    assert llm.parse_json_loose('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    assert llm.parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_surrounding_prose():
    text = 'Sure! Here is the result:\n{"a": 1, "b": "x"}\nHope that helps.'
    assert llm.parse_json_loose(text) == {"a": 1, "b": "x"}


def test_parse_unparseable_returns_empty():
    assert llm.parse_json_loose("no json at all") == {}
    assert llm.parse_json_loose("") == {}


# ---------- 429 classification ----------

def test_daily_quota_detected():
    assert llm._is_daily_quota("Rate limit exceeded: free-models-per-day")
    assert llm._is_daily_quota("You have no credits remaining. Add credits...")


def test_per_minute_rate_limit_not_treated_as_quota():
    assert not llm._is_daily_quota("Rate limit exceeded: 20 requests per minute")
