"""Embedding client interface and adapters."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import numpy as np

try:
    import yaml
except ImportError:
    yaml = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _normalize_text(s: str, lowercase: bool = True, strip_accents: bool = True, collapse_spaces: bool = True) -> str:
    """Normalize text for embedding.

    Args:
        s: Input string.
        lowercase: Convert to lowercase.
        strip_accents: Remove accents.
        collapse_spaces: Collapse multiple spaces.

    Returns:
        Normalized string.
    """
    if lowercase:
        s = s.lower()

    if strip_accents:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")

    if collapse_spaces:
        s = re.sub(r"\s+", " ", s).strip()

    return s


class EmbeddingClient(ABC):
    """Abstract interface for embedding providers."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Return embedding dimension."""
        pass

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return L2-normalized embeddings (unit vectors).

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors (unit norm, L2-normalized).
        """
        pass


class NoopEmbeddingClient(EmbeddingClient):
    """No-op client that raises error if used."""

    @property
    def dim(self) -> int:
        """Return 384 as default."""
        return 384

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Raise error - embeddings disabled."""
        raise RuntimeError("Embeddings disabled (provider='none' or enabled=false)")


class HashEmbeddingClient(EmbeddingClient):
    """Hash-based embedding client (deterministic, no external deps).

    Useful for testing and development without sentence-transformers.
    """

    def __init__(self, dim: int = 384):
        """Initialize hash-based embedder.

        Args:
            dim: Embedding dimension.
        """
        self._dim = dim

    @property
    def dim(self) -> int:
        """Return embedding dimension."""
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic embeddings from hash.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors (unit norm).
        """
        embeddings = []
        for text in texts:
            # Normalize text
            text_norm = _normalize_text(text, lowercase=True, strip_accents=True, collapse_spaces=True)
            # Hash to bytes
            hash_bytes = hashlib.sha256(text_norm.encode()).digest()
            # Create vector from hash (deterministic)
            vec = np.frombuffer(hash_bytes, dtype=np.uint8).astype(np.float32)
            # Pad or truncate to dim
            if len(vec) < self._dim:
                # Extend with additional hashes
                extended = hash_bytes
                while len(extended) < self._dim * 4:
                    extended += hashlib.sha256(extended).digest()
                vec = np.frombuffer(extended[: self._dim * 4], dtype=np.uint8).astype(np.float32)[: self._dim]
            else:
                vec = vec[: self._dim]

            # Normalize to unit vector (L2 norm = 1)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            else:
                vec = np.zeros(self._dim, dtype=np.float32)
                vec[0] = 1.0  # Unit vector

            embeddings.append(vec.tolist())

        return embeddings


class LocalSentenceTransformerClient(EmbeddingClient):
    """Local sentence-transformers client."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize local sentence transformer.

        Args:
            model_name: Model name (e.g., "all-MiniLM-L6-v2").
        """
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers not installed. Install with: pip install sentence-transformers")

        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

    @property
    def dim(self) -> int:
        """Return embedding dimension."""
        return self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using sentence-transformers.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors (unit norm).
        """
        # Normalize texts
        texts_norm = [_normalize_text(t, lowercase=True, strip_accents=True, collapse_spaces=True) for t in texts]

        # Generate embeddings
        embeddings = self.model.encode(texts_norm, normalize_embeddings=True, convert_to_numpy=True)

        # Convert to list of lists
        return embeddings.tolist()


class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI embedding client (remote)."""

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536):
        """Initialize OpenAI embedding client.

        Args:
            model: Model name (e.g., "text-embedding-3-small").
            dim: Expected dimension (varies by model).
        """
        if OpenAI is None:
            raise ImportError("openai package not installed. Install with: pip install openai")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Try secrets.yaml
            if yaml:
                secrets_path = Path("configs/secrets.yaml")
                if secrets_path.exists():
                    try:
                        with open(secrets_path, "r", encoding="utf-8") as f:
                            secrets = yaml.safe_load(f) or {}
                            api_key = secrets.get("openai_api_key")
                    except Exception:
                        pass

        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or configs/secrets.yaml")

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        """Return embedding dimension."""
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors (unit norm).
        """
        # Normalize texts
        texts_norm = [_normalize_text(t, lowercase=True, strip_accents=True, collapse_spaces=True) for t in texts]

        # Call API
        response = self.client.embeddings.create(model=self.model, input=texts_norm)

        # Extract embeddings
        embeddings = [item.embedding for item in response.data]

        # Normalize to unit vectors
        embeddings_norm = []
        for emb in embeddings:
            vec = np.array(emb)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings_norm.append(vec.tolist())

        return embeddings_norm


def create_embedding_client(provider: str, model: str = "all-MiniLM-L6-v2", dim: int = 384) -> EmbeddingClient:
    """Factory function to create embedding client.

    Args:
        provider: Provider name ("local", "openai", "hash", "none").
        model: Model name (provider-specific).
        dim: Expected dimension (for hash/openai).

    Returns:
        EmbeddingClient instance.
    """
    if provider == "none" or not provider:
        return NoopEmbeddingClient()

    if provider == "hash":
        return HashEmbeddingClient(dim=dim)

    if provider == "local":
        try:
            return LocalSentenceTransformerClient(model_name=model)
        except (ImportError, Exception):
            # Fallback to hash if sentence-transformers not available
            return HashEmbeddingClient(dim=dim)

    if provider == "openai":
        try:
            return OpenAIEmbeddingClient(model=model, dim=dim)
        except (ImportError, ValueError):
            # Fallback to no-op
            return NoopEmbeddingClient()

    # Unknown provider -> hash fallback
    return HashEmbeddingClient(dim=dim)

