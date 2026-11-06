"""Headless review helpers ported from the maintained SPHEREx pipeline.

Only browser-runtime dependencies are included; no desktop GUI or workers.
"""
from __future__ import annotations


from decimal import Decimal


from . import review_helpers as common


ClassificationSpec = common.ClassificationSpec


CLASSIFICATION_SPECS = (
    ClassificationSpec("4", "Good centered on PSF and isolated", Decimal("4")),
    ClassificationSpec("3", "Good centered on PSF but crowded", Decimal("3")),
    ClassificationSpec("2", "Not centered on PSF but isolated", Decimal("2")),
    ClassificationSpec("1", "Not centered on PSF and crowded", Decimal("1")),
    ClassificationSpec("h", "bad/halo", Decimal("-1")),
)
