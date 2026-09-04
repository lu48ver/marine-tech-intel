"""Shared LLM client for summarize.py / digest.py.

Supports two providers, picked automatically from whichever key is present:

  OpenRouter  OPENROUTER_API_KEY or .openrouter_key  — free models (":free"),
              no card required. Limits: 20 requests/min and 50 requests/day
              (1000/day once you have purchased $10+ of credits).
  OpenAI      OPENAI_API_KEY or .openai_key          — paid, gpt-4o-mini.

OpenRouter speaks the OpenAI API, so the same SDK is used for both; only the
base_url and model differ. OpenRouter is preferred when both keys exist.

Free models come and go, so the OpenRouter path takes a CHAIN of models and
falls through to the next one when a model is missing or has no provider
capacity. Whichever model answered is returned to the caller so it can be
recorded in the summary cache.

Robustness the callers rely on:
  * requests are throttled to stay under the per-minute cap;
  * a per-minute 429 is retried with backoff, while a daily-quota 429 raises
    LLMUnavailable so the caller can stop cleanly and resume next run;
  * models that ignore response_format are retried without it, and their
    replies are parsed leniently (markdown fences / surrounding prose).
"""

import json
import logging
import os
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Tried in order; the first one that answers is used. Chosen for Chinese
# fluency and instruction-following. Override with LLM_MODEL (comma-separated
# for a custom chain). Check https://openrouter.ai/models?q=free for the
# current line-up if these ever disappear.
OPENROUTER_FREE_MODELS = [
    "z-ai/glm-5.2:free",
    "minimax/minimax-m3:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# Free tier allows 20 requests/minute; leave a margin.
OPENROUTER_MIN_INTERVAL_SEC = 3.5

logger = logging.getLogger("llm")

_last_call_at = 0.0


class LLMUnavailable(RuntimeError):
    """The provider cannot serve any more calls this run (quota/auth/outage).

    Callers should stop making calls, save what they have, and report — the
    URL-keyed cache makes the next run resume where this one stopped.
    """


def _read_key(env_name: str, key_file: str) -> str:
    """API key from the environment (CI secret) or a gitignored local file."""
    key = os.environ.get(env_name, "").strip()
    if key:
        return key
    path = PROJECT_ROOT / key_file
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def resolve_provider() -> dict | None:
    """Return {name, api_key, base_url, models} for the configured provider."""
    models_override = [m.strip() for m in os.environ.get("LLM_MODEL", "").split(",") if m.strip()]

    key = _read_key("OPENROUTER_API_KEY", ".openrouter_key")
    if key:
        return {
            "name": "openrouter",
            "api_key": key,
            "base_url": OPENROUTER_BASE_URL,
            "models": models_override or list(OPENROUTER_FREE_MODELS),
            "min_interval": OPENROUTER_MIN_INTERVAL_SEC,
        }

    key = _read_key("OPENAI_API_KEY", ".openai_key")
    if key:
        # OPENAI_MODEL kept for backwards compatibility with older configs
        legacy = os.environ.get("OPENAI_MODEL", "").strip()
        return {
            "name": "openai",
            "api_key": key,
            "base_url": None,
            "models": models_override or [legacy or OPENAI_DEFAULT_MODEL],
            "min_interval": 0.0,
        }
    return None


def build_client() -> tuple[object, dict] | tuple[None, None]:
    """Build an OpenAI-SDK client for the configured provider."""
    provider = resolve_provider()
    if provider is None:
        return None, None
    from openai import OpenAI

    kwargs = {"api_key": provider["api_key"]}
    if provider["base_url"]:
        kwargs["base_url"] = provider["base_url"]
        # Optional attribution headers used by OpenRouter's dashboard
        kwargs["default_headers"] = {
            "HTTP-Referer": "https://lu48ver.github.io/marine-tech-intel/",
            "X-Title": "Marine Tech Intel",
        }
    logger.info(
        "LLM provider: %s (models: %s)", provider["name"], ", ".join(provider["models"])
    )
    return OpenAI(**kwargs), provider


def parse_json_loose(text: str) -> dict:
    """Parse JSON from a model reply that may wrap it in prose or fences."""
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    # outermost {...}
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _is_daily_quota(message: str) -> bool:
    """True when a 429 means 'done for today', not 'slow down'."""
    lowered = message.lower()
    return any(
        s in lowered
        for s in ("per day", "per-day", "daily", "quota", "credit", "add credits", "billing")
    )


def _throttle(min_interval: float) -> None:
    global _last_call_at
    if min_interval <= 0:
        return
    wait = min_interval - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def chat_json(
    client,
    provider: dict,
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    retries: int = 3,
) -> tuple[dict, str]:
    """Ask for a JSON object; return (parsed_dict, model_that_answered).

    Raises LLMUnavailable when no model can serve the request (auth failure,
    daily quota exhausted, or every model in the chain failing).
    """
    from openai import APIStatusError, APIConnectionError

    last_error = "no model attempted"
    for model in provider["models"]:
        use_json_mode = True
        for attempt in range(1, retries + 1):
            kwargs = {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                _throttle(provider["min_interval"])
                resp = client.chat.completions.create(**kwargs)
            except APIStatusError as exc:
                message = str(exc)
                status = getattr(exc, "status_code", None)
                if status in (401, 403):
                    raise LLMUnavailable(f"authentication failed: {message[:200]}") from exc
                if status == 429:
                    if _is_daily_quota(message):
                        raise LLMUnavailable(f"quota exhausted: {message[:200]}") from exc
                    backoff = 20 * attempt
                    logger.warning("rate limited, waiting %ds (%s)", backoff, model)
                    time.sleep(backoff)
                    last_error = message
                    continue
                if status == 400 and "response_format" in message.lower() and use_json_mode:
                    logger.info("%s rejects response_format — retrying without it", model)
                    use_json_mode = False
                    last_error = message
                    continue
                # 404 (unknown model) / 502 / 503 (no capacity): try next model
                logger.warning("model %s failed (%s): %s", model, status, message[:150])
                last_error = message
                break
            except APIConnectionError as exc:
                last_error = str(exc)
                logger.warning("connection error on %s: %s", model, last_error[:150])
                time.sleep(5 * attempt)
                continue

            content = (resp.choices[0].message.content or "") if resp.choices else ""
            parsed = parse_json_loose(content)
            if parsed:
                return parsed, model
            # Empty/garbled reply: once without JSON mode, then give up on it
            logger.warning("model %s returned unparseable output", model)
            last_error = f"unparseable output from {model}"
            if use_json_mode:
                use_json_mode = False
                continue
            break

    raise LLMUnavailable(f"all models failed — last error: {last_error[:250]}")
