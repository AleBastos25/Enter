"""LLM Scorer for candidate-field compatibility (v3).

Scores all field×candidate pairs in batch using a single LLM call per page/region.
This enables global assignment and reduces LLM calls.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..core.doc_profile import DocProfile
from ..core.models import SchemaField
from ..matching.candidates import Candidate as CandidateV3
from .client import LLMClient
from .prompts import build_scorer_prompt, parse_scorer_response


def score_matrix(
    fields: List[SchemaField],
    candidate_sets: Dict[str, List[CandidateV3]],
    profile: DocProfile,
    llm_client: Optional[LLMClient] = None,
    timeout_seconds: float = 2.0,
) -> Dict[str, Dict[str, float]]:
    """Score all field×candidate pairs in batch.
    
    Args:
        fields: List of schema fields.
        candidate_sets: Dictionary mapping field_name -> list of Candidate objects.
        profile: Document profile.
        llm_client: Optional LLM client (if None, returns dummy scores).
        timeout_seconds: Timeout for LLM call.
    
    Returns:
        Dictionary mapping field_name -> {candidate_id: score (0.0-1.0), ...}.
    """
    if not llm_client:
        # Return dummy scores (all 0.5) if LLM disabled
        return {
            field.name: {cand.candidate_id: 0.5 for cand in candidate_sets.get(field.name, [])}
            for field in fields
        }
    
    # Build prompt for scorer
    prompt = build_scorer_prompt(fields, candidate_sets, profile)
    
    # Call LLM
    try:
        response = llm_client.generate(prompt, max_tokens=256, timeout=timeout_seconds)
        scores = parse_scorer_response(response, fields, candidate_sets)
        return scores
    except Exception as e:
        # Fallback: return dummy scores on error
        return {
            field.name: {cand.candidate_id: 0.5 for cand in candidate_sets.get(field.name, [])}
            for field in fields
        }

