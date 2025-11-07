"""Global assignment solver for field×candidate pairs (v3).

Resolves conflicts globally by maximizing score sum with constraints:
- Exclusivity: one candidate cannot serve incompatible fields
- Type gate: hard rejection for type mismatches
- Footer guard: penalize repeated footer blocks
- Scope: prefer candidates in matching sections/components
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..core.doc_profile import DocProfile
from ..core.models import SchemaField
from ..matching.candidates import Candidate as CandidateV3
from ..validation.patterns import type_gate_generic


@dataclass
class AssignmentResult:
    """Result of global assignment.
    
    Attributes:
        picks: Dictionary mapping field_name -> candidate_id.
        scores: Dictionary mapping field_name -> final_score.
        dropped_conflicts: List of (field_name, candidate_id) pairs that were dropped due to conflicts.
    """
    
    picks: Dict[str, str]  # field -> candidate_id
    scores: Dict[str, float]  # field -> score_final
    dropped_conflicts: List[Tuple[str, str]]  # (field, cand) that fell due to conflicts


def solve_assignment(
    score_matrix: Dict[str, Dict[str, float]],
    candidate_sets: Dict[str, List[CandidateV3]],
    fields: List[SchemaField],
    profile: DocProfile,
    constraints: Optional[Dict] = None,
) -> AssignmentResult:
    """Solve global assignment maximizing score sum with constraints.
    
    Uses a greedy algorithm with conflict resolution (simpler than full Hungarian).
    
    Args:
        score_matrix: Dictionary mapping field_name -> {candidate_id: score}.
        candidate_sets: Dictionary mapping field_name -> list of Candidate objects.
        fields: List of schema fields.
        profile: Document profile.
        constraints: Optional constraint config dict.
    
    Returns:
        AssignmentResult with picks, scores, and dropped conflicts.
    """
    if constraints is None:
        constraints = {}
    
    # Build candidate lookup
    candidate_by_id: Dict[str, CandidateV3] = {}
    for field_name, candidates in candidate_sets.items():
        for cand in candidates:
            candidate_by_id[cand.candidate_id] = cand
    
    # Build field lookup
    field_by_name = {f.name: f for f in fields}
    
    # Apply constraints and adjust scores
    adjusted_scores: Dict[str, Dict[str, float]] = {}
    for field_name in score_matrix:
        field = field_by_name.get(field_name)
        if not field:
            continue
        
        adjusted_scores[field_name] = {}
        for cand_id, score in score_matrix[field_name].items():
            cand = candidate_by_id.get(cand_id)
            if not cand:
                continue
            
            # 1. Hard type gate: reject if type_gate fails
            if not type_gate_generic(cand.snippet, field.type or "text"):
                adjusted_scores[field_name][cand_id] = -1.0  # Reject
                continue
            
            # 2. Footer penalty
            adjusted_score = score
            if cand.features.in_repeated_footer:
                if isinstance(constraints, dict):
                    footer_penalty = constraints.get("footer_penalty")
                else:
                    footer_penalty = None
                if footer_penalty is None:
                    if isinstance(profile.thresholds, dict):
                        footer_penalty = profile.thresholds.get("tau_footer_penalty", 0.35)
                    else:
                        footer_penalty = 0.35
                adjusted_score *= (1.0 - footer_penalty)
            
            # 3. Section/component scope bonus
            if field.meta.get("section_hint") or field.meta.get("position_hint"):
                # Prefer candidates in same section/component
                if cand.features.section_id is not None:
                    adjusted_score += constraints.get("section_scope_bonus", 0.15)
            
            # 4. Same line/table bonus
            if cand.features.relation == "same_line_right_of":
                adjusted_score += constraints.get("prefer_same_line_weight", 0.20)
            elif cand.features.relation == "same_table_row":
                adjusted_score += constraints.get("prefer_same_table_col_weight", 0.25)
            
            # Clamp to [0, 1]
            adjusted_score = max(0.0, min(1.0, adjusted_score))
            adjusted_scores[field_name][cand_id] = adjusted_score
    
    # Greedy assignment with conflict resolution
    picks: Dict[str, str] = {}
    scores: Dict[str, float] = {}
    used_candidates: Set[str] = set()
    dropped_conflicts: List[Tuple[str, str]] = []
    
    # Sort fields by priority (enum > date/money > others)
    field_priority = []
    for field in fields:
        if field.type == "enum":
            priority = 0
        elif field.type in ("date", "money"):
            priority = 1
        else:
            priority = 2
        field_priority.append((priority, field.name))
    
    field_priority.sort()
    
    # IMPROVEMENT: Track candidate values to detect duplicates
    candidate_values: Dict[str, str] = {}  # cand_id -> extracted value
    for field_name, candidates in candidate_sets.items():
        for cand in candidates:
            if cand.candidate_id not in candidate_values:
                # Extract snippet/value for duplicate detection
                candidate_values[cand.candidate_id] = (cand.snippet or "").strip()
    
    # Assign greedily
    for _, field_name in field_priority:
        if field_name not in adjusted_scores:
            continue
        
        # Get candidates sorted by adjusted score
        candidates_with_scores = [
            (cand_id, score)
            for cand_id, score in adjusted_scores[field_name].items()
            if score > 0.0  # Skip rejected
        ]
        candidates_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Try to assign best candidate
        assigned = False
        for cand_id, score in candidates_with_scores:
            # IMPROVEMENT: Check if this candidate value was already used by a different field
            # This prevents same value (e.g., same date) being assigned to multiple fields
            cand_value = candidate_values.get(cand_id, "").strip()
            if cand_value:
                # Normalize value for comparison (remove common variations)
                import re
                cand_value_normalized = re.sub(r'\s+', ' ', cand_value.lower().strip())
                
                # Check if any other field already uses a candidate with this exact value
                for other_field, other_cand_id in picks.items():
                    if other_field != field_name:
                        other_value = candidate_values.get(other_cand_id, "").strip()
                        if other_value:
                            other_value_normalized = re.sub(r'\s+', ' ', other_value.lower().strip())
                            # If values match (normalized), prefer the field with higher score
                            if other_value_normalized == cand_value_normalized:
                                existing_score = scores.get(other_field, 0.0)
                                # IMPROVEMENT: More restrictive - need 20% better AND field types must match
                                current_field = field_by_name[field_name]
                                other_field_obj = field_by_name.get(other_field)
                                if other_field_obj:
                                    # Only allow replacement if same type OR new score is significantly better
                                    if current_field.type != other_field_obj.type:
                                        # Different types - reject duplicate
                                        dropped_conflicts.append((field_name, cand_id))
                                        continue
                                if score <= existing_score * 1.20:  # Need 20% better to replace
                                    dropped_conflicts.append((field_name, cand_id))
                                    continue  # Skip this candidate, keep existing assignment
            
            # Check exclusivity: if candidate already used, check if fields are compatible
            if cand_id in used_candidates:
                # Check if we can share (same field type)
                existing_field = None
                for fname, picked_cand_id in picks.items():
                    if picked_cand_id == cand_id:
                        existing_field = field_by_name.get(fname)
                        break
                
                if existing_field:
                    # IMPROVEMENT: More restrictive exclusivity - different fields should not share candidates
                    # even if same type (e.g., data_base and data_verncimento should not share same date)
                    # Only allow sharing if fields are semantically compatible (same name/synonyms)
                    current_field = field_by_name[field_name]
                    
                    # Check if fields are semantically the same (same name or overlapping synonyms)
                    fields_similar = False
                    if existing_field.name == current_field.name:
                        fields_similar = True
                    else:
                        # Check if they share synonyms (very unlikely but possible)
                        existing_syns = set((existing_field.meta or {}).get("synonyms", []))
                        current_syns = set((current_field.meta or {}).get("synonyms", []))
                        if existing_syns & current_syns:
                            fields_similar = True
                    
                    if fields_similar and existing_field.type == current_field.type:
                        # Same field or semantically equivalent - allow sharing
                        picks[field_name] = cand_id
                        scores[field_name] = score
                        assigned = True
                        break
                    else:
                        # Conflict: different fields using same candidate (even if same type)
                        # Prefer the field with higher score
                        existing_score = scores.get(existing_field.name, 0.0)
                        if score > existing_score * 1.1:  # 10% better to replace
                            # Replace existing assignment
                            picks.pop(existing_field.name, None)
                            picks[field_name] = cand_id
                            scores[field_name] = score
                            dropped_conflicts.append((existing_field.name, cand_id))
                            assigned = True
                            break
                        else:
                            # Keep existing, drop new
                            dropped_conflicts.append((field_name, cand_id))
                            continue
                else:
                    # Should not happen, but skip to be safe
                    continue
            
            # Assign candidate
            picks[field_name] = cand_id
            scores[field_name] = score
            used_candidates.add(cand_id)
            assigned = True
            break
        
        # If no candidate assigned, field gets None
        if not assigned:
            picks[field_name] = None  # Will be converted to null later
            scores[field_name] = 0.0
    
    # Check minimum score threshold
    if isinstance(constraints, dict):
        min_field_score = constraints.get("min_field_score")
    else:
        min_field_score = None
    if min_field_score is None:
        if isinstance(profile.thresholds, dict):
            min_field_score = profile.thresholds.get("tau_min_score", 0.60)
        else:
            min_field_score = 0.60
    for field_name in list(picks.keys()):
        if scores[field_name] < min_field_score:
            # Drop assignment if below threshold
            if picks[field_name] is not None:
                dropped_conflicts.append((field_name, picks[field_name]))
            picks[field_name] = None
            scores[field_name] = 0.0
    
    return AssignmentResult(
        picks=picks,
        scores=scores,
        dropped_conflicts=dropped_conflicts,
    )

