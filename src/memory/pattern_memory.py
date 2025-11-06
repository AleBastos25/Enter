"""Pattern Memory API for incremental learning from high-confidence extractions."""

from __future__ import annotations

import re
import statistics
from typing import Dict, List, Optional, Tuple

from .schema import (
    FieldMemory,
    FieldMemoryV2,
    FingerprintObs,
    LabelMemory,
    OffsetObs,
    Relation,
    StrategyStats,
    SynonymObs,
    ValueShapeObs,
)
from .store import MemoryStore


# Stop words to filter from synonyms
STOP_WORDS = {
    "de",
    "do",
    "da",
    "dos",
    "das",
    "a",
    "o",
    "e",
    "em",
    "para",
    "com",
    "por",
    "the",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "a",
    "an",
}


def _normalize_text(s: str) -> str:
    """Normalize text: lowercase, remove accents, collapse spaces."""
    import unicodedata

    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_tokens(text: str) -> List[str]:
    """Extract tokens from text (normalized, filtered)."""
    normalized = _normalize_text(text)
    # Remove punctuation except essential separators
    tokens = re.findall(r"[a-z0-9]+", normalized)
    # Filter stop words and very short tokens
    tokens = [t for t in tokens if t not in STOP_WORDS and len(t) >= 2]
    return tokens


def _quantize_to_grid(center: Tuple[float, float], grid_res: Tuple[int, int]) -> Tuple[int, int]:
    """Quantize center coordinates to grid cell.

    Args:
        center: (x, y) in [0, 1]
        grid_res: (nx, ny) grid resolution

    Returns:
        (gx, gy) grid cell indices
    """
    x, y = center
    nx, ny = grid_res
    gx = min(int(x * nx), nx - 1)
    gy = min(int(y * ny), ny - 1)
    return (gx, gy)


class PatternMemory:
    """Pattern Memory for incremental learning from high-confidence extractions."""

    def __init__(self, label: str, cfg: dict, store: MemoryStore) -> None:
        """Initialize pattern memory.

        Args:
            label: Document label.
            cfg: Memory configuration dict.
            store: MemoryStore instance.
        """
        self.label = label
        self.cfg = cfg
        self.store = store

        # Load existing memory or create new
        self.memory: LabelMemory = store.load(label) or LabelMemory(label=label)

        # Apply decay and pruning
        self._apply_decay_and_pruning()

    def _apply_decay_and_pruning(self) -> None:
        """Apply decay factor and prune low-weight entries."""
        decay = self.cfg.get("learn", {}).get("decay_factor", 0.98)
        min_weight = self.cfg.get("learn", {}).get("min_weight_to_keep", 0.15)

        for field_mem in self.memory.fields.values():
            # Decay weights
            for obs in field_mem.synonyms:
                obs.weight *= decay
            for obs in field_mem.offsets:
                obs.weight *= decay
            for obs in field_mem.fingerprints:
                obs.weight *= decay
            for obs in field_mem.value_shapes:
                obs.weight *= decay

            # Prune low weights
            field_mem.synonyms = [s for s in field_mem.synonyms if s.weight >= min_weight]
            field_mem.offsets = [o for o in field_mem.offsets if o.weight >= min_weight]
            field_mem.fingerprints = [f for f in field_mem.fingerprints if f.weight >= min_weight]
            field_mem.value_shapes = [v for v in field_mem.value_shapes if v.weight >= min_weight]

            # Limit to max counts (keep highest weights)
            max_syn = self.cfg.get("learn", {}).get("max_synonyms_per_field", 12)
            max_off = self.cfg.get("learn", {}).get("max_offsets_per_field", 24)
            max_fp = self.cfg.get("learn", {}).get("max_layout_fingerprints", 24)

            field_mem.synonyms.sort(key=lambda s: s.weight, reverse=True)
            field_mem.synonyms = field_mem.synonyms[:max_syn]

            field_mem.offsets.sort(key=lambda o: o.weight, reverse=True)
            field_mem.offsets = field_mem.offsets[:max_off]

            field_mem.fingerprints.sort(key=lambda f: f.weight, reverse=True)
            field_mem.fingerprints = field_mem.fingerprints[:max_fp]

    def get_synonyms(self, field_name: str, max_k: int) -> List[str]:
        """Get learned synonyms for a field (sorted by weight).

        Args:
            field_name: Field name.
            max_k: Maximum number of synonyms to return.

        Returns:
            List of synonym strings (normalized).
        """
        field_mem = self.memory.fields.get(field_name)
        if not field_mem:
            return []

        synonyms = sorted(field_mem.synonyms, key=lambda s: s.weight, reverse=True)
        return [s.text for s in synonyms[:max_k]]

    def get_offset_hints(self, field_name: str) -> List[OffsetObs]:
        """Get learned offset hints for a field.

        Args:
            field_name: Field name.

        Returns:
            List of OffsetObs sorted by weight.
        """
        field_mem = self.memory.fields.get(field_name)
        if not field_mem:
            return []

        return sorted(field_mem.offsets, key=lambda o: o.weight, reverse=True)

    def get_fingerprint_hints(self, field_name: str) -> List[FingerprintObs]:
        """Get learned fingerprint hints for a field.

        Args:
            field_name: Field name.

        Returns:
            List of FingerprintObs sorted by weight.
        """
        field_mem = self.memory.fields.get(field_name)
        if not field_mem:
            return []

        return sorted(field_mem.fingerprints, key=lambda f: f.weight, reverse=True)

    def get_value_shape_hints(self, field_name: str) -> List[ValueShapeObs]:
        """Get learned value shape hints for a field.

        Args:
            field_name: Field name.

        Returns:
            List of ValueShapeObs sorted by weight.
        """
        field_mem = self.memory.fields.get(field_name)
        if not field_mem:
            return []

        return sorted(field_mem.value_shapes, key=lambda v: v.weight, reverse=True)
    
    def get_value_examples(self, field_name: str, max_k: int = 3) -> List[str]:
        """Get example value formats/shapes for a field (for embedding queries).
        
        This returns example descriptions based on learned value shapes, not actual values
        (for privacy). Examples include format hints like "CPF format", "enum value REGULAR",
        or length/digit patterns.
        
        Args:
            field_name: Field name.
            max_k: Maximum number of examples to return.
            
        Returns:
            List of example descriptions (e.g., ["CPF format", "enum: REGULAR", "6 digits"]).
        """
        value_shapes = self.get_value_shape_hints(field_name)
        if not value_shapes:
            return []
        
        examples = []
        for shape in value_shapes[:max_k]:
            # Build example description from shape
            parts = []
            if shape.regex_id:
                # Add format hint
                if shape.regex_id == "cpf":
                    parts.append("CPF format")
                elif shape.regex_id == "cnpj":
                    parts.append("CNPJ format")
                elif shape.regex_id == "cep":
                    parts.append("CEP format")
                elif shape.regex_id == "placa":
                    parts.append("vehicle plate format")
                elif shape.regex_id == "email":
                    parts.append("email format")
            
            if shape.enum_key:
                parts.append(f"enum: {shape.enum_key}")
            
            if shape.length_range:
                min_len, max_len = shape.length_range
                if min_len == max_len:
                    parts.append(f"{min_len} characters")
                else:
                    parts.append(f"{min_len}-{max_len} characters")
            
            if shape.has_digits:
                parts.append("contains digits")
            
            if parts:
                examples.append(", ".join(parts))
        
        return examples[:max_k]

    def learn(
        self,
        field_name: str,
        label_text: str,
        value_text: str,
        relation: Relation,
        label_bbox: Tuple[float, float, float, float],
        value_bbox: Tuple[float, float, float, float],
        confidence: float,
        context: Optional[Dict] = None,
    ) -> None:
        """Learn from a high-confidence extraction.

        Args:
            field_name: Field name.
            label_text: Text of the label block.
            value_text: Extracted value text.
            relation: Spatial relation used.
            label_bbox: Normalized bbox of label (x0, y0, x1, y1).
            value_bbox: Normalized bbox of value (x0, y0, x1, y1).
            confidence: Confidence score of extraction.
            context: Optional context dict (section_id, column_id, page_index, etc.).
        """
        # Get or create field memory
        if field_name not in self.memory.fields:
            self.memory.fields[field_name] = FieldMemory(field_name=field_name)

        field_mem = self.memory.fields[field_name]

        # Learn synonyms
        tokens = _extract_tokens(label_text)
        for token in tokens:
            # Find existing synonym or create new
            existing = next((s for s in field_mem.synonyms if s.text == token), None)
            if existing:
                existing.weight += confidence
            else:
                field_mem.synonyms.append(SynonymObs(text=token, weight=confidence))

        # Learn offset
        label_center_x = (label_bbox[0] + label_bbox[2]) / 2.0
        label_center_y = (label_bbox[1] + label_bbox[3]) / 2.0
        value_center_x = (value_bbox[0] + value_bbox[2]) / 2.0
        value_center_y = (value_bbox[1] + value_bbox[3]) / 2.0

        dx = value_center_x - label_center_x
        dy = value_center_y - label_center_y

        # Check if similar offset exists
        tol = 0.06  # Default tolerance
        existing_offset = None
        for obs in field_mem.offsets:
            if obs.relation == relation and abs(obs.dx - dx) < tol and abs(obs.dy - dy) < tol:
                existing_offset = obs
                break

        if existing_offset:
            existing_offset.weight += confidence
        else:
            field_mem.offsets.append(OffsetObs(relation=relation, dx=dx, dy=dy, tol=tol, weight=confidence))

        # Learn fingerprint
        grid_res = tuple(self.cfg.get("fingerprint", {}).get("grid_resolution", [4, 4]))
        label_grid = _quantize_to_grid((label_center_x, label_center_y), grid_res)
        value_grid = _quantize_to_grid((value_center_x, value_center_y), grid_res)

        section_id = context.get("section_id") if context else None
        column_id = context.get("column_id") if context else None

        # Check if similar fingerprint exists
        existing_fp = None
        for fp in field_mem.fingerprints:
            if (
                fp.grid_label == label_grid
                and fp.grid_value == value_grid
                and fp.section_hint == section_id
                and fp.column_hint == column_id
            ):
                existing_fp = fp
                break

        if existing_fp:
            existing_fp.weight += confidence
        else:
            field_mem.fingerprints.append(
                FingerprintObs(
                    grid_label=label_grid,
                    grid_value=value_grid,
                    section_hint=section_id,
                    column_hint=column_id,
                    weight=confidence,
                )
            )

        # Learn value shape
        value_shape = ValueShapeObs(weight=confidence)

        # Check regex patterns
        value_clean = value_text.strip()
        if re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{11}$", value_clean):
            value_shape.regex_id = "cpf"
        elif re.match(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$|^\d{14}$", value_clean):
            value_shape.regex_id = "cnpj"
        elif re.match(r"^\d{5}-?\d{3}$", value_clean):
            value_shape.regex_id = "cep"
        elif re.match(r"^[A-Z]{3}\d[A-Z]\d{2}$|^[A-Z]{3}-\d{4}$", value_clean.upper()):
            value_shape.regex_id = "placa"
        elif re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", value_clean.lower()):
            value_shape.regex_id = "email"

        # Check enum (if provided in context)
        enum_options = context.get("enum_options") if context else None
        if enum_options and value_clean.upper() in [opt.upper() for opt in enum_options]:
            value_shape.enum_key = value_clean.upper()

        # Check has digits and length
        value_shape.has_digits = bool(re.search(r"\d", value_clean))
        value_shape.length_range = (len(value_clean), len(value_clean))

        # Add value shape
        field_mem.value_shapes.append(value_shape)

    def learn_strategy_stats(
        self,
        field_name: str,
        label_text: str,
        strategy: str,
        success: bool,
        dx: Optional[float] = None,
        dy: Optional[float] = None,
        shape: Optional[str] = None,
        font_z: Optional[float] = None,
        component_id: Optional[int] = None,
    ) -> None:
        """Learn strategy statistics (v2).

        Args:
            field_name: Field name.
            label_text: Label text.
            strategy: Strategy name ('table_row', 'same_line', 'same_block', 'south_of', 'semantic').
            success: True if confidence >= 0.85.
            dx: Optional offset dx.
            dy: Optional offset dy.
            shape: Optional shape string.
            font_z: Optional font_z score.
            component_id: Optional component_id.
        """
        # Get or create field memory v2
        if field_name not in self.memory.fields_v2:
            self.memory.fields_v2[field_name] = FieldMemoryV2(
                field_name=field_name, label_text=label_text
            )

        field_mem_v2 = self.memory.fields_v2[field_name]

        # Get or create strategy stats
        if strategy not in field_mem_v2.strategies:
            field_mem_v2.strategies[strategy] = StrategyStats(strategy=strategy)

        stats = field_mem_v2.strategies[strategy]

        # Update counters
        stats.n_total += 1
        if success:
            stats.n_success += 1
        stats.success_rate = stats.n_success / stats.n_total if stats.n_total > 0 else 0.0

        # Update offsets
        if dx is not None and dy is not None:
            stats.dx_samples.append(dx)
            stats.dy_samples.append(dy)
            if len(stats.dx_samples) > 0:
                stats.dx_mean = statistics.mean(stats.dx_samples)
                stats.dy_mean = statistics.mean(stats.dy_samples)
                if len(stats.dx_samples) > 1:
                    stats.dx_sigma = statistics.stdev(stats.dx_samples)
                    stats.dy_sigma = statistics.stdev(stats.dy_samples)
                else:
                    stats.dx_sigma = 0.0
                    stats.dy_sigma = 0.0

        # Update shapes
        if shape:
            stats.shapes[shape] = stats.shapes.get(shape, 0) + 1

        # Update font_z
        if font_z is not None:
            stats.font_z_samples.append(font_z)
            if len(stats.font_z_samples) > 0:
                stats.font_z_mean = statistics.mean(stats.font_z_samples)
                if len(stats.font_z_samples) > 1:
                    stats.font_z_sigma = statistics.stdev(stats.font_z_samples)
                else:
                    stats.font_z_sigma = 0.0

    def get_strategy_hints(
        self, field_name: str, current_dx: Optional[float] = None, current_shape: Optional[str] = None
    ) -> dict:
        """Get strategy hints for a field (v2): auto_apply, deprioritize, hints.

        Args:
            field_name: Field name.
            current_dx: Current document dx (for compatibility check).
            current_shape: Current document shape (for compatibility check).

        Returns:
            Dict with 'auto_apply', 'deprioritize', 'hints' keys.
        """
        field_mem_v2 = self.memory.fields_v2.get(field_name)
        if not field_mem_v2:
            return {"auto_apply": {}, "deprioritize": [], "hints": {}}

        n_min = 20  # Minimum samples for auto_apply/deprioritize
        auto_apply: dict = {}
        deprioritize: list = []
        hints: dict = {}

        for strategy, stats in field_mem_v2.strategies.items():
            # auto_apply: n_total >= N_min, success_rate >= 0.9, e compatível
            if stats.n_total >= n_min and stats.success_rate >= 0.9:
                # Check compatibility
                compatible = True
                if current_dx is not None and stats.dx_samples:
                    # Check |Δx_doc - Δx_mean| ≤ 2σ
                    if abs(current_dx - stats.dx_mean) > 2 * max(stats.dx_sigma, 0.01):
                        compatible = False
                if current_shape and stats.shapes:
                    # Check shape ∈ top_k_forms
                    top_shapes = sorted(stats.shapes.items(), key=lambda x: x[1], reverse=True)[:3]
                    top_shape_keys = [s[0] for s in top_shapes]
                    if current_shape not in top_shape_keys:
                        compatible = False  # Shape not in top forms

                if compatible:
                    auto_apply[strategy] = stats

            # deprioritize: n_total >= N_min e success_rate <= 0.1
            elif stats.n_total >= n_min and stats.success_rate <= 0.1:
                deprioritize.append(strategy)

            # hints: provide stats even if not auto_apply
            if stats.n_total > 0:
                hints[strategy] = {
                    "success_rate": stats.success_rate,
                    "n_total": stats.n_total,
                    "dx_mean": stats.dx_mean,
                    "dy_mean": stats.dy_mean,
                }

        return {"auto_apply": auto_apply, "deprioritize": deprioritize, "hints": hints}

    def commit(self) -> None:
        """Commit memory to disk (with pruning applied)."""
        self._apply_decay_and_pruning()
        self.store.save(self.memory)

