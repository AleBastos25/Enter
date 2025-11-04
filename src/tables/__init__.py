"""Table detection and extraction module."""

from .detector import detect_tables
from .extractor import find_cell_by_label

__all__ = ["detect_tables", "find_cell_by_label"]

