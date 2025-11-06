"""Pattern Registry for dynamic pattern learning (v3).

Learns patterns (shapes/regex) from confirmed extractions.
Patterns start in "shadow" mode (generate candidates + small bonus) and
promote to "active" mode (higher bonus) when precision is high enough.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PatternDetector = Dict[str, any]  # shape_id, regex_candidate, stats


@dataclass
class PatternStats:
    """Statistics for a learned pattern.
    
    Attributes:
        n_total: Total attempts using this pattern.
        n_match: Number of successful matches.
        precision_estimate: Wilson confidence interval estimate.
        timestamps: List of timestamps when pattern was used (for decay).
    """
    
    n_total: int = 0
    n_match: int = 0
    precision_estimate: float = 0.0
    timestamps: List[float] = field(default_factory=list)


@dataclass
class PatternDetector:
    """A learned pattern detector.
    
    Attributes:
        shape_id: Compact shape sequence (e.g., "D{5}" with prefix=9).
        len_range: Expected length range (min, max).
        has_digits: Whether pattern requires digits.
        charset: Expected character set.
        separators: List of separator characters used.
        regex_candidate: Optional regex synthesized by LLM.
        stats: Pattern statistics.
        status: "shadow" or "active".
    """
    
    shape_id: str
    len_range: Tuple[int, int]
    has_digits: bool
    charset: str
    separators: List[str]
    regex_candidate: Optional[str] = None
    stats: PatternStats = field(default_factory=PatternStats)
    status: str = "shadow"  # "shadow" or "active"


class PatternRegistry:
    """Registry for learned patterns (one per label/field combination)."""
    
    def __init__(self, store_dir: Path):
        """Initialize pattern registry.
        
        Args:
            store_dir: Directory to store pattern files.
        """
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.patterns: Dict[str, Dict[str, List[PatternDetector]]] = {}  # label -> field -> list of patterns
        self.load_patterns()
    
    def load_patterns(self) -> None:
        """Load patterns from disk."""
        for pattern_file in self.store_dir.glob("pattern_*.json"):
            try:
                with open(pattern_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    label = data.get("label", "")
                    if label not in self.patterns:
                        self.patterns[label] = {}
                    
                    for field_name, patterns_data in data.get("fields", {}).items():
                        patterns = []
                        for p_data in patterns_data:
                            pattern = PatternDetector(
                                shape_id=p_data["shape_id"],
                                len_range=tuple(p_data["len_range"]),
                                has_digits=p_data["has_digits"],
                                charset=p_data["charset"],
                                separators=p_data.get("separators", []),
                                regex_candidate=p_data.get("regex_candidate"),
                                stats=PatternStats(**p_data.get("stats", {})),
                                status=p_data.get("status", "shadow"),
                            )
                            patterns.append(pattern)
                        
                        self.patterns[label][field_name] = patterns
            except Exception:
                pass  # Skip corrupted files
    
    def save_patterns(self, label: str) -> None:
        """Save patterns for a label to disk.
        
        Args:
            label: Label name.
        """
        if label not in self.patterns:
            return
        
        pattern_file = self.store_dir / f"pattern_{label}.json"
        data = {
            "label": label,
            "fields": {},
        }
        
        for field_name, patterns in self.patterns[label].items():
            data["fields"][field_name] = []
            for pattern in patterns:
                data["fields"][field_name].append({
                    "shape_id": pattern.shape_id,
                    "len_range": list(pattern.len_range),
                    "has_digits": pattern.has_digits,
                    "charset": pattern.charset,
                    "separators": pattern.separators,
                    "regex_candidate": pattern.regex_candidate,
                    "stats": {
                        "n_total": pattern.stats.n_total,
                        "n_match": pattern.stats.n_match,
                        "precision_estimate": pattern.stats.precision_estimate,
                        "timestamps": pattern.stats.timestamps,
                    },
                    "status": pattern.status,
                })
        
        with open(pattern_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def learn_patterns(
        self,
        label: str,
        field_name: str,
        confirmed_value: str,
        min_precision: float = 0.95,
        min_matches: int = 5,
    ) -> None:
        """Learn patterns from confirmed extraction.
        
        Args:
            label: Document label.
            field_name: Field name.
            confirmed_value: Confirmed extracted value.
            min_precision: Minimum precision to promote from shadow to active.
            min_matches: Minimum matches to promote.
        """
        if label not in self.patterns:
            self.patterns[label] = {}
        if field_name not in self.patterns[label]:
            self.patterns[label][field_name] = []
        
        # Extract pattern features
        shape_id = _extract_shape(confirmed_value)
        len_range = (len(confirmed_value), len(confirmed_value))
        has_digits = bool(re.search(r"\d", confirmed_value))
        charset = _extract_charset(confirmed_value)
        separators = _extract_separators(confirmed_value)
        
        # Find or create pattern
        pattern = None
        for p in self.patterns[label][field_name]:
            if (p.shape_id == shape_id and
                p.has_digits == has_digits and
                p.charset == charset):
                pattern = p
                break
        
        if not pattern:
            pattern = PatternDetector(
                shape_id=shape_id,
                len_range=len_range,
                has_digits=has_digits,
                charset=charset,
                separators=separators,
                status="shadow",
            )
            self.patterns[label][field_name].append(pattern)
        
        # Update stats
        pattern.stats.n_total += 1
        pattern.stats.n_match += 1  # Confirmed = match
        pattern.stats.timestamps.append(time.time())  # Current time
        
        # Recalculate precision
        if pattern.stats.n_total > 0:
            pattern.stats.precision_estimate = pattern.stats.n_match / pattern.stats.n_total
        
        # Promote to active if threshold met
        if (pattern.status == "shadow" and
            pattern.stats.n_match >= min_matches and
            pattern.stats.precision_estimate >= min_precision):
            pattern.status = "active"
        
        # Update len_range to include this value
        min_len, max_len = pattern.len_range
        pattern.len_range = (min(min_len, len(confirmed_value)), max(max_len, len(confirmed_value)))
        
        # Save
        self.save_patterns(label)
    
    def suggest_pattern_detectors(
        self,
        label: str,
        field_name: str,
    ) -> List[PatternDetector]:
        """Get pattern detectors for a field (shadow + active).
        
        Args:
            label: Document label.
            field_name: Field name.
        
        Returns:
            List of pattern detectors (active first, then shadow).
        """
        if label not in self.patterns:
            return []
        if field_name not in self.patterns[label]:
            return []
        
        patterns = self.patterns[label][field_name]
        # Sort: active first, then by precision
        patterns.sort(key=lambda p: (0 if p.status == "active" else 1, -p.stats.precision_estimate))
        
        return patterns
    
    def apply_patterns(
        self,
        label: str,
        field_name: str,
        text: str,
    ) -> List[Dict[str, any]]:  # Returns list of SpanMatch dicts
        """Apply learned patterns to generate candidate spans.
        
        Args:
            label: Document label.
            field_name: Field name.
            text: Text to search.
        
        Returns:
            List of span matches (start, end, pattern_id, bonus).
        """
        patterns = self.suggest_pattern_detectors(label, field_name)
        matches = []
        
        for pattern in patterns:
            # Try regex if available
            if pattern.regex_candidate:
                try:
                    regex_matches = re.finditer(pattern.regex_candidate, text)
                    for match in regex_matches:
                        matches.append({
                            "start": match.start(),
                            "end": match.end(),
                            "text": match.group(0),
                            "pattern_id": pattern.shape_id,
                            "bonus": 0.12 if pattern.status == "active" else 0.05,
                        })
                except Exception:
                    pass
            
            # Fallback: shape-based matching
            # Simple heuristic: look for text matching shape characteristics
            min_len, max_len = pattern.len_range
            words = re.findall(r"\b\w+\b", text)
            for word in words:
                if min_len <= len(word) <= max_len:
                    if pattern.has_digits and not re.search(r"\d", word):
                        continue
                    if pattern.separators and not any(sep in word for sep in pattern.separators):
                        continue
                    
                    # Found potential match
                    start = text.find(word)
                    if start >= 0:
                        matches.append({
                            "start": start,
                            "end": start + len(word),
                            "text": word,
                            "pattern_id": pattern.shape_id,
                            "bonus": 0.12 if pattern.status == "active" else 0.05,
                        })
        
        return matches


def _extract_shape(value: str) -> str:
    """Extract shape sequence from value.
    
    Args:
        value: Value string.
    
    Returns:
        Shape sequence (e.g., "D{5}" for 5 digits).
    """
    shape = []
    i = 0
    while i < len(value):
        if value[i].isdigit():
            digit_count = 0
            while i < len(value) and value[i].isdigit():
                digit_count += 1
                i += 1
            shape.append(f"D{{{digit_count}}}")
        elif value[i].isalpha():
            letter_count = 0
            while i < len(value) and value[i].isalpha():
                letter_count += 1
                i += 1
            shape.append(f"L{{{letter_count}}}")
        else:
            shape.append("P")  # Punctuation
            i += 1
    
    return "".join(shape)


def _extract_charset(value: str) -> str:
    """Extract character set from value.
    
    Args:
        value: Value string.
    
    Returns:
        Character set description.
    """
    has_digits = bool(re.search(r"\d", value))
    has_upper = bool(re.search(r"[A-Z]", value))
    has_lower = bool(re.search(r"[a-z]", value))
    
    if has_digits and has_upper and has_lower:
        return "alphanum_mixed"
    elif has_digits and has_upper:
        return "alphanum_upper"
    elif has_digits:
        return "digits"
    elif has_upper:
        return "upper"
    elif has_lower:
        return "lower"
    else:
        return "other"


def _extract_separators(value: str) -> List[str]:
    """Extract separator characters from value.
    
    Args:
        value: Value string.
    
    Returns:
        List of separator characters found.
    """
    separators = []
    for char in value:
        if char in ".,-/:;":
            if char not in separators:
                separators.append(char)
    return separators

