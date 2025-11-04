"""Persistence layer for pattern memory (filesystem JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .schema import LabelMemory


class MemoryStore:
    """File-based store for pattern memory (one file per label)."""

    def __init__(self, store_dir: str) -> None:
        """Initialize store with directory path.

        Args:
            store_dir: Directory to store memory files.
        """
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, label: str) -> Path:
        """Get file path for a label."""
        # Sanitize label for filename
        safe_label = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
        return self.store_dir / f"{safe_label}.json"

    def load(self, label: str) -> Optional[LabelMemory]:
        """Load memory for a label.

        Args:
            label: Document label.

        Returns:
            LabelMemory if exists, None otherwise.
        """
        file_path = self._file_path(label)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return self._from_dict(data)
        except Exception:
            return None

    def save(self, memory: LabelMemory) -> None:
        """Save memory for a label.

        Args:
            memory: LabelMemory to save.
        """
        file_path = self._file_path(memory.label)
        data = self._to_dict(memory)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _to_dict(self, memory: LabelMemory) -> Dict:
        """Convert LabelMemory to dict for JSON serialization."""
        fields_dict = {}
        for field_name, field_mem in memory.fields.items():
            fields_dict[field_name] = {
                "field_name": field_mem.field_name,
                "synonyms": [{"text": s.text, "weight": s.weight} for s in field_mem.synonyms],
                "offsets": [
                    {
                        "relation": o.relation,
                        "dx": o.dx,
                        "dy": o.dy,
                        "tol": o.tol,
                        "weight": o.weight,
                    }
                    for o in field_mem.offsets
                ],
                "fingerprints": [
                    {
                        "grid_label": fp.grid_label,
                        "grid_value": fp.grid_value,
                        "section_hint": fp.section_hint,
                        "column_hint": fp.column_hint,
                        "weight": fp.weight,
                    }
                    for fp in field_mem.fingerprints
                ],
                "value_shapes": [
                    {
                        "regex_id": vs.regex_id,
                        "enum_key": vs.enum_key,
                        "has_digits": vs.has_digits,
                        "length_range": vs.length_range,
                        "weight": vs.weight,
                    }
                    for vs in field_mem.value_shapes
                ],
            }
        return {"label": memory.label, "fields": fields_dict}

    def _from_dict(self, data: Dict) -> LabelMemory:
        """Convert dict to LabelMemory from JSON."""
        from .schema import FieldMemory, FingerprintObs, OffsetObs, SynonymObs, ValueShapeObs

        label = data.get("label", "")
        fields_dict = {}
        for field_name, field_data in data.get("fields", {}).items():
            synonyms = [
                SynonymObs(text=s["text"], weight=s["weight"]) for s in field_data.get("synonyms", [])
            ]
            offsets = [
                OffsetObs(
                    relation=o["relation"],
                    dx=o["dx"],
                    dy=o["dy"],
                    tol=o.get("tol", 0.06),
                    weight=o["weight"],
                )
                for o in field_data.get("offsets", [])
            ]
            fingerprints = [
                FingerprintObs(
                    grid_label=tuple(fp["grid_label"]),
                    grid_value=tuple(fp["grid_value"]),
                    section_hint=fp.get("section_hint"),
                    column_hint=fp.get("column_hint"),
                    weight=fp["weight"],
                )
                for fp in field_data.get("fingerprints", [])
            ]
            value_shapes = [
                ValueShapeObs(
                    regex_id=vs.get("regex_id"),
                    enum_key=vs.get("enum_key"),
                    has_digits=vs.get("has_digits"),
                    length_range=tuple(vs["length_range"]) if vs.get("length_range") else None,
                    weight=vs["weight"],
                )
                for vs in field_data.get("value_shapes", [])
            ]
            fields_dict[field_name] = FieldMemory(
                field_name=field_name,
                synonyms=synonyms,
                offsets=offsets,
                fingerprints=fingerprints,
                value_shapes=value_shapes,
            )
        return LabelMemory(label=label, fields=fields_dict)

