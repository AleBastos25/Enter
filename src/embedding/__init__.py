"""Embedding module for semantic matching."""

from .client import EmbeddingClient, HashEmbeddingClient, NoopEmbeddingClient, create_embedding_client
from .index import CosineIndex
from .policy import EmbeddingPolicy

__all__ = [
    "EmbeddingClient",
    "HashEmbeddingClient",
    "NoopEmbeddingClient",
    "create_embedding_client",
    "CosineIndex",
    "EmbeddingPolicy",
]

