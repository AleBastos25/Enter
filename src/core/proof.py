"""Audit trail (proof) construction for reproducible decisions.

Tracks all decisions made during extraction with deterministic evidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.models import Block, LayoutGraph


def build_proof(
    field_name: str,
    selected_candidate: Optional[Dict[str, Any]],
    all_candidates: List[Dict[str, Any]],
    pareto_criteria: Optional[List[Any]] = None,
    tie_breaker_applied: bool = False,
    tie_breaker_reason: Optional[str] = None,
    llm_used: bool = False,
    llm_result: Optional[Dict[str, Any]] = None,
    memory_invariants: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build audit trail (proof) for a field extraction.
    
    Args:
        field_name: Field name.
        selected_candidate: Selected candidate dict (or None).
        all_candidates: All candidates considered.
        pareto_criteria: Optional list of ParetoCriteria objects.
        tie_breaker_applied: Whether tie-breakers were applied.
        tie_breaker_reason: Optional reason from tie-breaker.
        llm_used: Whether LLM chooser was used.
        llm_result: Optional LLM result dict with 'pick' and 'why'.
        memory_invariants: Optional dict of invariants used.
        
    Returns:
        Proof dict with all decision evidence.
    """
    proof: Dict[str, Any] = {
        "field": field_name,
        "num_candidates": len(all_candidates),
    }
    
    # Label component info
    if selected_candidate:
        label_block_id = selected_candidate.get("label_block_id")
        block_id = selected_candidate.get("block_id")
        relation = selected_candidate.get("relation", "")
        
        proof["label_component"] = {
            "label_block_id": label_block_id,
            "rules_applied": ["label_matching", "neighborhood_search"],
        }
        
        proof["value_component"] = {
            "block_id": block_id,
            "relation": relation,
            "rules_applied": ["type_gate", "neighborhood"],
        }
        
        proof["search"] = {
            "direction": relation,
            "hops": 0 if relation in ("same_block", "same_line") else 1,
            "no_crossing": True,  # Simplified
        }
    else:
        proof["label_component"] = None
        proof["value_component"] = None
        proof["search"] = None
    
    # Pareto info
    if pareto_criteria and len(all_candidates) > 1:
        non_dominated_indices = []
        for i, criteria in enumerate(pareto_criteria):
            is_dominated = False
            for j, other_criteria in enumerate(pareto_criteria):
                if i != j and other_criteria.dominates(criteria):
                    is_dominated = True
                    break
            if not is_dominated:
                non_dominated_indices.append(i)
        
        proof["pareto"] = {
            "num_candidates_before": len(all_candidates),
            "num_non_dominated": len(non_dominated_indices),
            "non_dominated_indices": non_dominated_indices,
        }
    else:
        proof["pareto"] = None
    
    # Tie-breakers info
    if tie_breaker_applied:
        proof["tie_breakers"] = {
            "applied": True,
            "reason": tie_breaker_reason or "direction_preference",
        }
    else:
        proof["tie_breakers"] = {"applied": False}
    
    # LLM info
    if llm_used:
        proof["llm_used"] = {
            "used": True,
            "pick": llm_result.get("pick") if llm_result else None,
            "why": llm_result.get("why") if llm_result else None,
        }
    else:
        proof["llm_used"] = {"used": False}
    
    # Memory invariants
    if memory_invariants:
        proof["memory"] = memory_invariants
    else:
        proof["memory"] = None
    
    return proof
