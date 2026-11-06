"""Headless review helpers ported from the maintained SPHEREx pipeline.

Only browser-runtime dependencies are included; no desktop GUI or workers.
"""
from __future__ import annotations
import bz2


from pathlib import Path


def current_cutout_path(path: Path) -> Path:
    """Find the current name if compression renamed the cached cutout."""
    path = Path(path)
    alternate = path.with_suffix("") if path.suffix == ".bz2" else path.with_name(path.name + ".bz2")
    return path if path.is_file() or not alternate.is_file() else alternate


def read_cutout_bytes(path: Path) -> bytes:
    """Read PNG or PNG.bz2, tolerating a concurrent verified compression rename."""
    path = Path(path)
    alternate = path.with_suffix("") if path.suffix == ".bz2" else path.with_name(path.name + ".bz2")
    for candidate in (path, alternate):
        try:
            data = candidate.read_bytes()
        except FileNotFoundError:
            continue
        return bz2.decompress(data) if candidate.suffix == ".bz2" else data
    raise FileNotFoundError(f"Cutout not found: {path} or {alternate}")
