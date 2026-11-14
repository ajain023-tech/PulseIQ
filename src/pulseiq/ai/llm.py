"""Provider-agnostic LLM client: gemini (default) | anthropic | openai | mock | offline.

Configuration (environment only - never commit keys):
  PULSEIQ_LLM_PROVIDER   gemini | anthropic | openai | mock | offline   (default gemini)
  PULSEIQ_LLM_MODEL      optional model override
  GEMINI_API_KEY / GOOGLE_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY
A provider whose key is missing degrades to the offline template engine.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

from . import offline

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-4.1-mini",
}
KEY_VARS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


class LLMError(RuntimeError):
    """Provider call failed."""


def parse_json(text: str) -> dict:
    """Strictly parse the first JSON object in ``text`` (tolerates ```json fences)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise LLMError("Model did not return JSON.") from None
        obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise LLMError("Model JSON must be an object.")
    return obj


@dataclass
class LLMClient:
    """Base client: ``complete(system, user) -> str``."""

    provider: str
    model: str

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class GeminiClient(LLMClient):
    """Google Gemini via the public REST generateContent endpoint."""

    def __init__(self, model: str, key: str):
        super().__init__("gemini", model)
        self._key = key

    def complete(self, system: str, user: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        r = httpx.post(url, params={"key": self._key}, json=body, timeout=30)
        if r.status_code != 200:
            raise LLMError(f"Gemini HTTP {r.status_code}")
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicClient(LLMClient):
    """Claude via the official ``anthropic`` SDK (optional dependency)."""

    def __init__(self, model: str):
        super().__init__("anthropic", model)
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str) -> str:
        a = self._anthropic
        try:
            resp = self._client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.RateLimitError as e:
            raise LLMError("Anthropic rate limited") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic HTTP {e.status_code}") from e
        except a.APIConnectionError as e:
            raise LLMError("Anthropic connection error") from e
        if resp.stop_reason == "refusal":
            return json.dumps({"refuse": "The model declined this request."})
        return "".join(b.text for b in resp.content if b.type == "text")


class OpenAIClient(LLMClient):
    """OpenAI chat completions via REST (JSON mode)."""

    def __init__(self, model: str, key: str):
        super().__init__("openai", model)
        self._key = key

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise LLMError(f"OpenAI HTTP {r.status_code}")
        return r.json()["choices"][0]["message"]["content"]


class MockLLM(LLMClient):
    """Deterministic stand-in for an LLM: answers via the offline templates in LLM JSON format.

    ``script`` (optional) is a list of raw replies returned in order - used in tests to
    exercise malformed output, guard rejections and the retry path.
    """

    def __init__(self, script: list[str] | None = None):
        super().__init__("mock", "offline-templates")
        self.script = list(script or [])
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append(user)
        if self.script:
            return self.script.pop(0)
        if system.startswith("You write a short answer"):
            return json.dumps({"answer": "", "caveats": []})
        m = re.search(r"<question>(.*)</question>", user, re.S)
        p = offline.plan(m.group(1) if m else user)
        if p.refuse:
            return json.dumps({"refuse": p.refuse})
        if p.tool == "get_experiment_report":
            return json.dumps({"tool": p.tool, **p.tool_args})
        if p.tool:
            return json.dumps({"tool": p.tool})
        return json.dumps({"intent": p.intent, "sql": p.sql, "chart": p.chart, "notes": p.notes})


def get_client(provider: str | None = None) -> LLMClient | None:
    """Return a configured client, or None for offline mode (no key / provider=offline)."""
    provider = (provider or os.environ.get("PULSEIQ_LLM_PROVIDER") or "gemini").lower()
    if provider == "offline":
        return None
    if provider == "mock":
        return MockLLM()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unknown provider {provider!r}")
    key = next((os.environ[v] for v in KEY_VARS[provider] if os.environ.get(v)), None)
    if not key:
        return None
    model = os.environ.get("PULSEIQ_LLM_MODEL") or DEFAULT_MODELS[provider]
    if provider == "gemini":
        return GeminiClient(model, key)
    if provider == "anthropic":
        try:
            return AnthropicClient(model)
        except ImportError:
            return None
    return OpenAIClient(model, key)
