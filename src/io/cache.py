"""Cache for embeddings (disk-based)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np


def key_for_block(pdf_id: str, block_id: int, model_name: str) -> str:
    """Generate cache key for a block embedding.

    Args:
        pdf_id: Document ID.
        block_id: Block ID.
        model_name: Model name (e.g., "all-MiniLM-L6-v2").

    Returns:
        Cache key string.
    """
    key_str = f"{pdf_id}:{block_id}:{model_name}"
    return hashlib.md5(key_str.encode()).hexdigest()


def key_for_query(field_name: str, query_text: str, model_name: str) -> str:
    """Generate cache key for a query embedding.

    Args:
        field_name: Field name.
        query_text: Query text.
        model_name: Model name.

    Returns:
        Cache key string.
    """
    key_str = f"query:{field_name}:{query_text}:{model_name}"
    return hashlib.md5(key_str.encode()).hexdigest()


def load_vec(cache_dir: str, key: str) -> Optional[np.ndarray]:
    """Load cached embedding vector.

    Args:
        cache_dir: Cache directory path.
        key: Cache key.

    Returns:
        Embedding vector (numpy array), or None if not found.
    """
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return None

    vec_file = cache_path / f"{key}.npy"
    if vec_file.exists():
        try:
            return np.load(vec_file)
        except Exception:
            pass

    return None


def save_vec(cache_dir: str, key: str, vec: np.ndarray) -> None:
    """Save embedding vector to cache.

    Args:
        cache_dir: Cache directory path.
        key: Cache key.
        vec: Embedding vector (numpy array).
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    vec_file = cache_path / f"{key}.npy"
    try:
        np.save(vec_file, vec)
    except Exception:
        pass

