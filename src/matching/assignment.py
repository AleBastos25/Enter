"""Global field-to-block assignment using optimal transport and linear algebra.

This module provides a global assignment approach that solves the field-to-block
matching problem as an optimal transport problem, combining semantic similarity
with spatial priors for consistent, globally optimal assignments.
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple

from ..core.models import Block, FieldCandidate, LayoutGraph, SchemaField


def build_semantic_matrix(
    schema_fields: List[SchemaField],
    blocks: List[Block],
    semantic_seeds: Optional[Dict[str, List[Tuple[int, float]]]] = None,
) -> np.ndarray:
    """Build semantic similarity matrix from seeds.

    Args:
        schema_fields: List of F schema fields.
        blocks: List of N blocks.
        semantic_seeds: Optional dict mapping field_name -> list of (block_id, cosine_score).

    Returns:
        Semantic similarity matrix S_sem ∈ [0,1]^{F×N}.
    """
    F = len(schema_fields)
    N = len(blocks)
    S_sem = np.zeros((F, N))

    if semantic_seeds is None:
        return S_sem

    block_id_to_idx = {b.id: idx for idx, b in enumerate(blocks)}

    for f_idx, field in enumerate(schema_fields):
        field_seeds = semantic_seeds.get(field.name, [])
        for block_id, cosine_score in field_seeds:
            if block_id in block_id_to_idx:
                n_idx = block_id_to_idx[block_id]
                # Remap from [-1,1] to [0,1] and store
                score_norm = (cosine_score + 1) / 2
                S_sem[f_idx, n_idx] = max(S_sem[f_idx, n_idx], score_norm)

    return S_sem


def build_spatial_priors(
    schema_fields: List[SchemaField],
    blocks: List[Block],
    layout: LayoutGraph,
    matching_cfg: Dict,
) -> np.ndarray:
    """Build spatial prior matrix P_spatial ∈ [0,1]^{F×N}.

    Args:
        schema_fields: List of F schema fields.
        blocks: List of N blocks.
        layout: Layout graph with neighborhood and metadata.
        matching_cfg: Matching configuration dict.

    Returns:
        Spatial prior matrix P_spatial ∈ [0,1]^{F×N}.
    """
    F = len(schema_fields)
    N = len(blocks)
    P_spatial = np.zeros((F, N))

    neighborhood = getattr(layout, "neighborhood", {})
    column_by_block = getattr(layout, "column_id_by_block", {})
    section_by_block = getattr(layout, "section_id_by_block", {})
    paragraph_by_block = getattr(layout, "paragraph_id_by_block", {})
    block_by_id = {b.id: b for b in blocks}

    for f_idx, field in enumerate(schema_fields):
        # Build synonyms and find label blocks
        from .matcher import _build_synonyms, _find_label_blocks

        synonyms = _build_synonyms(field)
        label_block_ids = _find_label_blocks(blocks, synonyms)

        if not label_block_ids:
            continue

        # For each label block, find spatial neighbors
        for label_block_id in label_block_ids[:3]:  # Limit to top 3 label blocks
            if label_block_id not in block_by_id:
                continue

            label_block = block_by_id[label_block_id]
            nb = neighborhood.get(label_block_id)

            if not nb:
                continue

            label_col = column_by_block.get(label_block_id)
            label_sec = section_by_block.get(label_block_id)
            label_para = paragraph_by_block.get(label_block_id)

            # Check right_on_same_line (highest priority)
            if nb.right_on_same_line is not None:
                dst_id = nb.right_on_same_line
                if dst_id in block_by_id:
                    dst_idx = next((i for i, b in enumerate(blocks) if b.id == dst_id), None)
                    if dst_idx is not None:
                        prior = 1.0  # same_line_right_of baseline

                        # Add column/section/paragraph bonuses
                        dst_col = column_by_block.get(dst_id)
                        dst_sec = section_by_block.get(dst_id)
                        dst_para = paragraph_by_block.get(dst_id)

                        if label_col is not None and dst_col is not None:
                            if label_col == dst_col:
                                prior += matching_cfg.get("prefer_same_column_bonus", 0.08)
                            else:
                                prior -= matching_cfg.get("cross_column_penalty", 0.06)

                        if label_sec is not None and dst_sec is not None:
                            if label_sec == dst_sec:
                                prior += matching_cfg.get("prefer_same_section_bonus", 0.05)
                            else:
                                prior -= matching_cfg.get("cross_section_penalty", 0.04)

                        if label_para is not None and dst_para is not None:
                            if label_para == dst_para:
                                prior += matching_cfg.get("prefer_same_paragraph_bonus", 0.03)

                        P_spatial[f_idx, dst_idx] = max(P_spatial[f_idx, dst_idx], np.clip(prior, 0, 1))

            # Check below_on_same_column (lower priority)
            if nb.below_on_same_column is not None:
                dst_id = nb.below_on_same_column
                if dst_id in block_by_id:
                    dst_idx = next((i for i, b in enumerate(blocks) if b.id == dst_id), None)
                    if dst_idx is not None:
                        prior = 0.7  # first_below_same_column baseline

                        # Add bonuses/penalties
                        dst_col = column_by_block.get(dst_id)
                        dst_sec = section_by_block.get(dst_id)
                        dst_para = paragraph_by_block.get(dst_id)

                        if label_col is not None and dst_col is not None:
                            if label_col == dst_col:
                                prior += matching_cfg.get("prefer_same_column_bonus", 0.08)
                            else:
                                prior -= matching_cfg.get("cross_column_penalty", 0.06)

                        if label_sec is not None and dst_sec is not None:
                            if label_sec == dst_sec:
                                prior += matching_cfg.get("prefer_same_section_bonus", 0.05)
                            else:
                                prior -= matching_cfg.get("cross_section_penalty", 0.04)

                        if label_para is not None and dst_para is not None:
                            if label_para == dst_para:
                                prior += matching_cfg.get("prefer_same_paragraph_bonus", 0.03)

                        # Only update if not already set by same_line (which has higher priority)
                        if P_spatial[f_idx, dst_idx] < 0.5:
                            P_spatial[f_idx, dst_idx] = max(P_spatial[f_idx, dst_idx], np.clip(prior, 0, 1))

            # Check same_block (if block contains label token)
            # Only add if not already set by spatial relations
            if label_block_id in block_by_id:
                label_idx = next((i for i, b in enumerate(blocks) if b.id == label_block_id), None)
                if label_idx is not None and P_spatial[f_idx, label_idx] < 0.5:
                    # Check if block contains label token
                    label_text = label_block.text or ""
                    import unicodedata
                    import re

                    def normalize(s):
                        s = unicodedata.normalize("NFD", s)
                        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
                        return s.lower()

                    label_text_norm = normalize(label_text)
                    has_label = any(normalize(syn) in label_text_norm for syn in synonyms if syn)

                    if has_label:
                        prior = 0.85  # same_block baseline
                        P_spatial[f_idx, label_idx] = max(P_spatial[f_idx, label_idx], prior)

    return P_spatial


def build_similarity_matrix(
    schema_fields: List[SchemaField],
    blocks: List[Block],
    semantic_similarity: Optional[np.ndarray] = None,
    spatial_priors: Optional[np.ndarray] = None,
    alpha: float = 0.7,
    beta: float = 0.3,
) -> np.ndarray:
    """Build combined similarity matrix S ∈ [0,1]^{F×N}.

    Args:
        schema_fields: List of F schema fields.
        blocks: List of N blocks.
        semantic_similarity: Optional F×N matrix of semantic (embedding) similarities.
        spatial_priors: Optional F×N matrix of spatial priors.
        alpha: Weight for semantic similarity (default 0.7).
        beta: Weight for spatial priors (default 0.3).

    Returns:
        Combined similarity matrix S ∈ [0,1]^{F×N}.
    """
    F = len(schema_fields)
    N = len(blocks)

    # Initialize S_sem (semantic similarity)
    if semantic_similarity is not None:
        S_sem = semantic_similarity.copy()
        # Ensure shape matches
        if S_sem.shape != (F, N):
            # Pad or truncate if needed
            S_sem = S_sem[:F, :N]
            if S_sem.shape != (F, N):
                S_sem = np.pad(S_sem, ((0, F - S_sem.shape[0]), (0, N - S_sem.shape[1])), mode="constant")
        # Remap from [-1,1] to [0,1] if needed
        if S_sem.min() < 0:
            S_sem = (S_sem + 1) / 2
        S_sem = np.clip(S_sem, 0, 1)
    else:
        S_sem = np.zeros((F, N))

    # Initialize P_spatial (spatial priors)
    if spatial_priors is not None:
        P_spatial = spatial_priors.copy()
        if P_spatial.shape != (F, N):
            P_spatial = P_spatial[:F, :N]
            if P_spatial.shape != (F, N):
                P_spatial = np.pad(
                    P_spatial, ((0, F - P_spatial.shape[0]), (0, N - P_spatial.shape[1])), mode="constant"
                )
        P_spatial = np.clip(P_spatial, 0, 1)
    else:
        P_spatial = np.zeros((F, N))

    # Combine: S = α·S_sem + β·P_spatial
    S = alpha * S_sem + beta * P_spatial
    S = np.clip(S, 0, 1)

    return S


def apply_type_gates(
    S: np.ndarray,
    schema_fields: List[SchemaField],
    blocks: List[Block],
) -> np.ndarray:
    """Apply type-aware gates to filter out incompatible block-field pairs.

    Args:
        S: Similarity matrix F×N.
        schema_fields: List of F schema fields.
        blocks: List of N blocks.

    Returns:
        Filtered similarity matrix with incompatible pairs set to 0.
    """
    S_filtered = S.copy()
    F, N = S.shape

    # Types that require digits
    REQUIRES_DIGITS = {"id_simple", "cep", "money", "date", "int", "float", "percent"}

    for f in range(F):
        field = schema_fields[f]
        field_type = (field.type or "text").lower()

        if field_type in REQUIRES_DIGITS:
            # Set to 0 for blocks without digits
            for n in range(N):
                block_text = blocks[n].text or ""
                if not any(c.isdigit() for c in block_text):
                    S_filtered[f, n] = 0.0

    return S_filtered


def topk_mask_rows(S: np.ndarray, k: int = 6) -> np.ndarray:
    """Keep only top-K columns per row, zero out the rest.

    Args:
        S: Similarity matrix F×N.
        k: Number of top columns to keep per row.

    Returns:
        Masked similarity matrix.
    """
    S_masked = S.copy()
    F, N = S.shape

    for f in range(F):
        row = S[f, :]
        if N <= k:
            continue  # Keep all if N <= k

        # Get indices of top-K
        topk_indices = np.argpartition(row, -k)[-k:]
        # Zero out others
        mask = np.zeros(N, dtype=bool)
        mask[topk_indices] = True
        S_masked[f, ~mask] = 0.0

    return S_masked


def add_null_column(S: np.ndarray, null_value: float = 0.35) -> np.ndarray:
    """Add a null column to allow fields to have no match.

    Args:
        S: Similarity matrix F×N.
        null_value: Similarity value for the null column (default 0.35).

    Returns:
        Extended similarity matrix F×(N+1) with null column.
    """
    F, N = S.shape
    S_ext = np.zeros((F, N + 1))
    S_ext[:, :N] = S
    S_ext[:, N] = null_value  # Null column
    return S_ext


def sinkhorn_algorithm(C: np.ndarray, epsilon: float = 0.1, max_iter: int = 100) -> np.ndarray:
    """Solve optimal transport using Sinkhorn algorithm (entropy-regularized OT).

    Args:
        C: Cost matrix F×N (lower is better).
        epsilon: Regularization parameter (default 0.1).
        max_iter: Maximum iterations (default 100).

    Returns:
        Assignment matrix A ∈ [0,1]^{F×N} (approximately bistochastic).
    """
    F, N = C.shape

    # Initialize: K = exp(-C / epsilon)
    K = np.exp(-C / epsilon)
    K = np.clip(K, 1e-20, None)  # Avoid overflow

    # Initialize u, v (marginals)
    u = np.ones(F) / F
    v = np.ones(N) / N

    # Iterate until convergence
    for _ in range(max_iter):
        u_prev = u.copy()
        # Update u: normalize rows
        u = 1.0 / (K @ v + 1e-20)
        # Update v: normalize columns
        v = 1.0 / (K.T @ u + 1e-20)

        # Check convergence
        if np.max(np.abs(u - u_prev)) < 1e-6:
            break

    # Compute final assignment: A = diag(u) @ K @ diag(v)
    A = np.diag(u) @ K @ np.diag(v)
    return A


def hungarian_assignment(C: np.ndarray) -> List[int]:
    """Solve assignment using Hungarian algorithm (exact matching).

    Args:
        C: Cost matrix F×N (lower is better).

    Returns:
        List of column indices (one per row), or -1 for no match.
    """
    try:
        from scipy.optimize import linear_sum_assignment

        # Hungarian algorithm expects square matrix
        F, N = C.shape
        if F > N:
            # Pad columns with high cost
            C_padded = np.pad(C, ((0, 0), (0, F - N)), mode="constant", constant_values=C.max() + 1)
            row_indices, col_indices = linear_sum_assignment(C_padded)
            # Map back to original columns
            assignments = [-1] * F
            for r, c in zip(row_indices, col_indices):
                if c < N:
                    assignments[r] = c
                else:
                    assignments[r] = -1  # No match
            return assignments
        else:
            # Pad rows with zero cost
            C_padded = np.pad(C, ((0, N - F), (0, 0)), mode="constant", constant_values=0)
            row_indices, col_indices = linear_sum_assignment(C_padded)
            # Map to original rows
            assignments = [-1] * F
            for r, c in zip(row_indices, col_indices):
                if r < F:
                    assignments[r] = c
            return assignments
    except ImportError:
        # Fallback: greedy assignment
        F, N = C.shape
        assignments = []
        used_cols = set()
        for f in range(F):
            row = C[f, :]
            # Mask used columns
            masked_row = row.copy()
            masked_row[list(used_cols)] = np.inf
            best_col = np.argmin(masked_row)
            if masked_row[best_col] < np.inf:
                assignments.append(best_col)
                used_cols.add(best_col)
            else:
                assignments.append(-1)  # No match
        return assignments


def global_assignment(
    schema_fields: List[SchemaField],
    blocks: List[Block],
    layout: LayoutGraph,
    semantic_seeds: Optional[Dict[str, List[Tuple[int, float]]]] = None,
    matching_cfg: Optional[Dict] = None,
    method: str = "sinkhorn",
    alpha: float = 0.7,
    beta: float = 0.3,
    top_k: int = 6,
    null_threshold: float = 0.35,
) -> Dict[str, List[FieldCandidate]]:
    """Perform global field-to-block assignment using optimal transport.

    Args:
        schema_fields: List of schema fields.
        blocks: List of blocks.
        layout: Layout graph.
        semantic_seeds: Optional dict mapping field_name -> list of (block_id, cosine_score).
        matching_cfg: Optional matching configuration dict.
        method: Assignment method: "sinkhorn" or "hungarian" (default "sinkhorn").
        alpha: Weight for semantic similarity (default 0.7).
        beta: Weight for spatial priors (default 0.3).
        top_k: Keep top-K columns per row (default 6).
        null_threshold: Similarity threshold for null column (default 0.35).

    Returns:
        Dictionary mapping field_name -> list of FieldCandidate (best match + alternatives).
    """
    F = len(schema_fields)
    N = len(blocks)

    if F == 0 or N == 0:
        return {}

    matching_cfg = matching_cfg or {}

    # Build semantic similarity matrix
    S_sem = build_semantic_matrix(schema_fields, blocks, semantic_seeds)

    # Build spatial priors matrix
    P_spatial = build_spatial_priors(schema_fields, blocks, layout, matching_cfg)

    # Build combined similarity matrix
    S = build_similarity_matrix(schema_fields, blocks, S_sem, P_spatial, alpha, beta)

    # Apply type gates
    S = apply_type_gates(S, schema_fields, blocks)

    # Top-K mask
    S = topk_mask_rows(S, k=top_k)

    # Add null column
    S_ext = add_null_column(S, null_value=null_threshold)
    F_ext, N_ext = S_ext.shape

    # Convert to cost matrix (lower is better)
    C = 1.0 - S_ext

    # Solve assignment
    A = None
    if method == "sinkhorn":
        A = sinkhorn_algorithm(C)
        # Get best assignment per row
        assignments = np.argmax(A, axis=1)
    elif method == "hungarian":
        assignments_list = hungarian_assignment(C)
        assignments = np.array(assignments_list)
    else:
        # Greedy fallback
        assignments = np.argmin(C, axis=1)

    # Build results
    results: Dict[str, List[FieldCandidate]] = {}
    block_by_id = {b.id: b for b in blocks}

    # Track which spatial relation contributed most (for relation assignment)
    # This is simplified - in practice, we'd track this during P_spatial construction
    neighborhood = getattr(layout, "neighborhood", {})

    for f_idx, field in enumerate(schema_fields):
        candidates = []
        best_col = assignments[f_idx]

        # Check if assigned to null
        if best_col >= N:  # Null column
            results[field.name] = []
            continue

        if best_col < 0 or best_col >= N:
            results[field.name] = []
            continue

        # Get assigned block
        assigned_block = blocks[best_col]

        # Determine relation (simplified - check spatial priors)
        relation = "same_line_right_of"  # Default
        if P_spatial[f_idx, best_col] > 0.8:
            relation = "same_line_right_of"
        elif P_spatial[f_idx, best_col] > 0.6:
            relation = "first_below_same_column"
        elif P_spatial[f_idx, best_col] > 0.4:
            relation = "same_block"

        # Find label block for source_label_block_id (reuse inline functions)
        # (Functions already defined above in build_spatial_priors)
        import unicodedata
        import re

        def _normalize_text_inline(s: str) -> str:
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            s = s.lower()
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _build_synonyms_inline(field: SchemaField) -> list[str]:
            if field.synonyms:
                return [s.lower().strip() for s in field.synonyms if s.strip()]
            synonyms = [field.name.lower()]
            name_norm = _normalize_text_inline(field.name)
            synonyms.append(name_norm)
            if "inscri" in name_norm or "registro" in name_norm:
                synonyms.extend(["inscricao", "inscrição", "nº oab", "n.oab", "numero oab", "registro"])
            if "seccional" in name_norm:
                synonyms.extend(["seccional", "uf", "conselho"])
            if "nome" in name_norm:
                synonyms.extend(["nome", "name"])
            seen = set()
            unique = []
            for syn in synonyms:
                syn_norm = _normalize_text_inline(syn)
                if syn_norm not in seen:
                    seen.add(syn_norm)
                    unique.append(syn_norm)
            return unique

        def _contains_any_inline(haystack: str, needles: list[str]) -> bool:
            haystack_norm = _normalize_text_inline(haystack)
            for needle in needles:
                if _normalize_text_inline(needle) in haystack_norm:
                    return True
            return False

        def _find_label_blocks_inline(blocks: list[Block], synonyms: list[str]) -> list[int]:
            candidates = []
            for block in blocks:
                if _contains_any_inline(block.text, synonyms):
                    text_len = len(block.text)
                    priority = 1.0 / (1.0 + text_len * 0.01)
                    if block.font_size:
                        priority += block.font_size * 0.01
                    candidates.append((block.id, priority))
            candidates.sort(key=lambda x: x[1], reverse=True)
            return [bid for bid, _ in candidates]

        synonyms = _build_synonyms_inline(field)
        label_block_ids = _find_label_blocks_inline(blocks, synonyms)
        source_label_block_id = label_block_ids[0] if label_block_ids else assigned_block.id

        # Build candidate
        candidate = FieldCandidate(
            field=field,
            node_id=assigned_block.id,
            source_label_block_id=source_label_block_id,
            relation=relation,
            scores={
                "spatial": float(S_ext[f_idx, best_col]),
                "type": 1.0,
                "semantic": float(S_sem[f_idx, best_col]) if S_sem[f_idx, best_col] > 0 else 0.0,
            },
        )
        candidates.append(candidate)

        # Add alternatives (2nd, 3rd best from S_ext)
        if method == "sinkhorn" and A is not None:
            # Get top-3 from assignment matrix
            top3_cols = np.argsort(A[f_idx, :])[-3:][::-1]
            for col in top3_cols[1:]:  # Skip best (already added)
                if col < N and col != best_col:
                    alt_block = blocks[col]
                    alt_candidate = FieldCandidate(
                        field=field,
                        node_id=alt_block.id,
                        source_label_block_id=source_label_block_id,
                        relation=relation,
                        scores={
                            "spatial": float(S_ext[f_idx, col]),
                            "type": 1.0,
                            "semantic": float(S_sem[f_idx, col]) if S_sem[f_idx, col] > 0 else 0.0,
                        },
                    )
                    candidates.append(alt_candidate)
        else:
            # Fallback: get top-3 from S_ext directly
            top3_cols = np.argsort(S_ext[f_idx, :])[-3:][::-1]
            for col in top3_cols[1:]:
                if col < N and col != best_col:
                    alt_block = blocks[col]
                    alt_candidate = FieldCandidate(
                        field=field,
                        node_id=alt_block.id,
                        source_label_block_id=source_label_block_id,
                        relation=relation,
                        scores={
                            "spatial": float(S_ext[f_idx, col]),
                            "type": 1.0,
                            "semantic": float(S_sem[f_idx, col]) if S_sem[f_idx, col] > 0 else 0.0,
                        },
                    )
                    candidates.append(alt_candidate)

        results[field.name] = candidates

    return results
