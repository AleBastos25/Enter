"""Cosine similarity index for embeddings with SVD acceleration."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


class CosineIndex:
    """Cosine similarity index using matrix multiplication with optional SVD acceleration.

    When SVD is enabled and the index is large enough, uses truncated SVD to reduce
    dimensionality for faster similarity computations while preserving most information.
    """

    def __init__(
        self,
        dim: int,
        svd_enabled: bool = False,
        svd_n_components: Optional[int] = None,
        svd_min_size: int = 100,
        svd_variance_threshold: float = 0.95,
    ):
        """Initialize cosine index.

        Args:
            dim: Embedding dimension.
            svd_enabled: If True, use SVD for acceleration when index is large enough.
            svd_n_components: Number of SVD components (if None, auto-select based on variance).
            svd_min_size: Minimum index size before SVD is applied.
            svd_variance_threshold: Minimum variance to retain when auto-selecting components.
        """
        self.dim = dim
        self.ids: list[int] = []
        self.matrix: Optional[np.ndarray] = None  # (N, D) - unit norm vectors
        
        # SVD settings
        self.svd_enabled = svd_enabled
        self.svd_n_components = svd_n_components
        self.svd_min_size = svd_min_size
        self.svd_variance_threshold = svd_variance_threshold
        
        # SVD state (computed lazily when needed)
        self._svd_components: Optional[np.ndarray] = None  # (D, k) - projection matrix
        self._svd_mean: Optional[np.ndarray] = None  # (D,) - mean for centering
        self._svd_reduced_dim: Optional[int] = None  # Reduced dimension k
        self._svd_fitted: bool = False

    def add(self, ids: list[int], mat: np.ndarray) -> None:
        """Add embeddings to index.

        Args:
            ids: List of block IDs (length N).
            mat: Embedding matrix (N, dim) - should be unit norm.
        """
        if len(ids) != mat.shape[0]:
            raise ValueError(f"ids length ({len(ids)}) != matrix rows ({mat.shape[0]})")

        if mat.shape[1] != self.dim:
            raise ValueError(f"matrix dim ({mat.shape[1]}) != index dim ({self.dim})")

        # Ensure unit norm
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # Avoid division by zero
        mat = mat / norms

        if self.matrix is None:
            self.matrix = mat
            self.ids = ids
        else:
            self.matrix = np.vstack([self.matrix, mat])
            self.ids.extend(ids)
        
        # Invalidate SVD when new data is added
        self._svd_fitted = False
        self._svd_components = None

    def _fit_svd(self) -> None:
        """Fit SVD on the current matrix if enabled and large enough."""
        if not self.svd_enabled or self.matrix is None:
            return
        
        N = len(self.ids)
        if N < self.svd_min_size:
            return
        
        # Center the data (subtract mean)
        # Note: For unit vectors, mean centering is approximate but helps SVD
        self._svd_mean = np.mean(self.matrix, axis=0)
        X_centered = self.matrix - self._svd_mean
        
        # Compute SVD: X_centered = U @ S @ Vt
        # We want Vt (components) and S (singular values)
        try:
            U, s, Vt = np.linalg.svd(X_centered, full_matrices=False)
            
            # Determine number of components
            if self.svd_n_components is not None:
                k = min(self.svd_n_components, len(s))
            else:
                # Auto-select based on variance threshold
                cumvar = np.cumsum(s ** 2) / np.sum(s ** 2)
                k = np.searchsorted(cumvar, self.svd_variance_threshold) + 1
                k = min(k, len(s), N - 1)  # Don't exceed matrix rank
            
            # Store top-k components (Vt[:k] is (k, D), transpose to (D, k))
            self._svd_components = Vt[:k].T  # (D, k)
            self._svd_reduced_dim = k
            self._svd_fitted = True
            
        except Exception:
            # If SVD fails, disable it for this index
            self._svd_fitted = False
            self._svd_components = None

    def search(self, queries: np.ndarray, top_k: int, refine_top_k: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Search for top-K similar vectors, optionally using SVD acceleration.

        Args:
            queries: Query matrix (Q, dim) - should be unit norm.
            top_k: Number of top results per query.
            refine_top_k: If SVD is used, refine top-K candidates using full dimension.
                         If None, uses 2 * top_k for refinement.

        Returns:
            Tuple of (top_ids, top_scores):
            - top_ids: (Q, K) array of block IDs
            - top_scores: (Q, K) array of cosine scores [0, 1]
        """
        if self.matrix is None or len(self.ids) == 0:
            # Return empty results
            Q = queries.shape[0]
            return np.zeros((Q, top_k), dtype=np.int32), np.zeros((Q, top_k), dtype=np.float32)

        # Ensure queries are unit norm
        norms = np.linalg.norm(queries, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        queries = queries / norms

        # Check if we should fit SVD (lazy fitting)
        if (
            self.svd_enabled
            and len(self.ids) >= self.svd_min_size
            and not self._svd_fitted
        ):
            self._fit_svd()
        
        if self._svd_fitted and self._svd_components is not None:
            # Use SVD-accelerated search
            # Project queries to reduced space
            queries_centered = queries - self._svd_mean
            queries_reduced = queries_centered @ self._svd_components  # (Q, k)
            
            # Project matrix to reduced space
            matrix_centered = self.matrix - self._svd_mean
            matrix_reduced = matrix_centered @ self._svd_components  # (N, k)
            
            # Normalize reduced vectors
            norms_q = np.linalg.norm(queries_reduced, axis=1, keepdims=True)
            norms_q[norms_q == 0] = 1.0
            queries_reduced = queries_reduced / norms_q
            
            norms_m = np.linalg.norm(matrix_reduced, axis=1, keepdims=True)
            norms_m[norms_m == 0] = 1.0
            matrix_reduced = matrix_reduced / norms_m
            
            # Compute approximate cosine similarity in reduced space
            scores_approx = queries_reduced @ matrix_reduced.T  # (Q, N)
            
            # Get more candidates than needed for refinement
            refine_k = refine_top_k if refine_top_k is not None else max(top_k * 2, 10)
            refine_k = min(refine_k, len(self.ids))
            
            top_indices_approx = np.argsort(-scores_approx, axis=1)[:, :refine_k]  # (Q, refine_k)
            
            # Refine top candidates using full dimension
            Q = queries.shape[0]
            top_ids = np.zeros((Q, top_k), dtype=np.int32)
            top_scores_out = np.zeros((Q, top_k), dtype=np.float32)
            
            for q_idx in range(Q):
                # Get candidate indices from approximate search
                candidate_indices = top_indices_approx[q_idx]
                
                # Compute exact similarity only for candidates
                query_vec = queries[q_idx:q_idx+1]  # (1, D)
                candidate_matrix = self.matrix[candidate_indices]  # (refine_k, D)
                exact_scores = (query_vec @ candidate_matrix.T).flatten()  # (refine_k,)
                
                # Get top-K from exact scores
                top_k_in_candidates = min(top_k, len(exact_scores))
                top_local_indices = np.argsort(-exact_scores)[:top_k_in_candidates]
                
                for k_idx, local_idx in enumerate(top_local_indices):
                    global_idx = candidate_indices[local_idx]
                    top_ids[q_idx, k_idx] = self.ids[global_idx]
                    top_scores_out[q_idx, k_idx] = float(exact_scores[local_idx])
            
            return top_ids, top_scores_out
        else:
            # Standard search without SVD
            # Compute cosine similarity: queries @ matrix.T
            # Result: (Q, N) where each row is cosine scores for one query
            scores = queries @ self.matrix.T  # (Q, N)

            # Get top-K for each query
            Q = scores.shape[0]
            top_indices = np.argsort(-scores, axis=1)[:, :top_k]  # (Q, K) - descending order

            # Extract top IDs and scores
            top_ids = np.zeros((Q, top_k), dtype=np.int32)
            top_scores_out = np.zeros((Q, top_k), dtype=np.float32)

            for q_idx in range(Q):
                for k_idx in range(top_k):
                    if k_idx < len(self.ids):
                        idx = top_indices[q_idx, k_idx]
                        top_ids[q_idx, k_idx] = self.ids[idx]
                        top_scores_out[q_idx, k_idx] = float(scores[q_idx, idx])

            return top_ids, top_scores_out

    def size(self) -> int:
        """Return number of vectors in index."""
        return len(self.ids) if self.ids else 0

