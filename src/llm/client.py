"""LLM client interface and adapters (OpenAI, Noop)."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, *, max_tokens: int, timeout: float) -> str:
        """Generate text from prompt.

        Args:
            prompt: Input prompt text.
            max_tokens: Maximum tokens to generate.
            timeout: Maximum seconds to wait for response.

        Returns:
            Generated text (empty string if timeout/error).
        """
        pass


class NoopClient(LLMClient):
    """No-op client that returns empty string (for running without API key)."""

    def generate(self, prompt: str, *, max_tokens: int, timeout: float) -> str:
        """Return empty string (no-op)."""
        return ""


def _load_api_key() -> Optional[str]:
    """Load OpenAI API key from secrets.yaml or environment variable.

    Returns:
        API key string, or None if not found.
    """
    # First try environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key

    # Fallback to secrets.yaml
    if yaml is None:
        return None

    secrets_path = Path("configs/secrets.yaml")
    if secrets_path.exists():
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = yaml.safe_load(f) or {}
                api_key = secrets.get("openai_api_key")
                if api_key:
                    return api_key
        except Exception:
            pass

    return None


class OpenAIClient(LLMClient):
    """OpenAI client adapter with timeout and retry."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):
        """Initialize OpenAI client.

        Args:
            model: Model name (e.g., "gpt-4o-mini").
            temperature: Sampling temperature (0.0 for deterministic).
        """
        if OpenAI is None:
            raise ImportError("openai package not installed. Install with: pip install openai")

        api_key = _load_api_key()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found. Set environment variable OPENAI_API_KEY "
                "or create configs/secrets.yaml with 'openai_api_key: sk-...'"
            )

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def generate(self, prompt: str, *, max_tokens: int, timeout: float) -> str:
        """Generate text with timeout.

        Args:
            prompt: Input prompt text.
            max_tokens: Maximum tokens to generate.
            timeout: Maximum seconds to wait.

        Returns:
            Generated text, or empty string on timeout/error.
        """
        start_time = time.time()

        try:
            # Use threading or async for timeout, but for simplicity, use a try/except
            # In production, you'd use concurrent.futures or similar
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=self.temperature,
                timeout=timeout,
            )

            elapsed = time.time() - start_time
            if elapsed > timeout:
                return ""

            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content or ""

        except Exception as e:
            # Timeout or other error - return empty
            # In production, you might want to log this
            return ""

        return ""


def create_client(provider: str, model: str = "gpt-4o-mini", temperature: float = 0.0) -> LLMClient:
    """Factory function to create LLM client.

    Args:
        provider: Provider name ("openai", "none", etc.).
        model: Model name (for OpenAI).
        temperature: Sampling temperature.

    Returns:
        LLMClient instance (NoopClient if provider is "none" or invalid).
    """
    if provider == "none" or not provider:
        return NoopClient()

    if provider == "openai":
        try:
            return OpenAIClient(model=model, temperature=temperature)
        except (ImportError, ValueError):
            # Fallback to no-op if API key missing or package not installed
            return NoopClient()

    # Unknown provider -> no-op
    return NoopClient()

