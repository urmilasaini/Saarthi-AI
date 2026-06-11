"""Unified LLM entry point: try Gemini first, fall back to Groq.

If neither key is configured, raises LLMUnavailable — callers degrade to
deterministic output so the app never hard-fails in a demo.
"""

import logging

from app import config
from app.providers import gemini, groq
from app.providers.gemini import ProviderError

logger = logging.getLogger("saarthi.llm")


class LLMUnavailable(Exception):
    pass


def available():
    return bool(config.gemini_key() or config.groq_key())


def chat(messages, tools=None, json_mode=False, temperature=0.3):
    """Try every (provider, model) pair in order until one answers:

    gemini-2.5-flash → gemini-2.5-flash-lite → llama-3.3-70b → llama-3.1-8b
    """
    attempts = []
    if config.gemini_key():
        attempts += [("gemini", gemini.chat, model) for model in config.GEMINI_MODELS]
    if config.groq_key():
        attempts += [("groq", groq.chat, model) for model in config.GROQ_MODELS]

    errors = []
    for provider_name, chat_func, model in attempts:
        try:
            return chat_func(
                messages, tools=tools, json_mode=json_mode,
                temperature=temperature, model=model,
            )
        except ProviderError as error:
            logger.warning("%s/%s failed, trying next: %s", provider_name, model, error)
            errors.append(f"{provider_name}/{model}: {error}")
        except Exception as error:  # adapter bug — still fall through the chain
            logger.exception("%s/%s adapter crashed: %s", provider_name, model, error)
            errors.append(f"{provider_name}/{model}: {error}")

    raise LLMUnavailable("; ".join(errors) or "no LLM API keys configured")
