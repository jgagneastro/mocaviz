"""Portable comment contract for stored spectral-autotype CNN probabilities.

Values are probabilities in [0, 1], never percentages. These fields describe
the spectral CNN, independently of the SUBLIME2 catalog/image classifier.
"""
from __future__ import annotations

import math
import re
from pathlib import PurePath

PREFIX = "spectral_cnn_"
VERSION_FIELD = PREFIX + "metadata_version"
FIELD_RE = re.compile(r"(?:^|;)\s*(spectral_cnn_[a-z0-9_]+)=([^;]*)")


def probability(value):
    if isinstance(value, (bool, str)) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def normalize_cnn(cnn):
    if not isinstance(cnn, dict) or cnn.get("status") not in (None, "classified"):
        return None
    raw = cnn.get("probabilities")
    if not isinstance(raw, dict) or probability(raw.get("good")) is None:
        return None
    values = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            return None
        value = probability(value)
        if value is None:
            return None
        values[key] = value
    model = PurePath(str(cnn.get("model_path") or cnn.get("model") or "")).name
    return {"status": "classified", "probabilities": values,
            "model": model, "predicted_class": str(cnn.get("predicted_class") or "")}


def comment_fields(cnn, *, source="spherex_autotype.py", generated_at=None, sha256=None):
    normalized = normalize_cnn(cnn)
    if normalized is None:
        return ""
    fields = [(VERSION_FIELD, "1")]
    fields.extend((PREFIX + key + "_probability", format(value, ".17g"))
                  for key, value in sorted(normalized["probabilities"].items()))
    for key, value in (("model", normalized["model"]),
                       ("predicted_class", normalized["predicted_class"]),
                       ("source", source), ("generated_at_utc", generated_at),
                       ("json_sha256", sha256)):
        if value:
            # Keep every value within one semicolon-delimited comment field.
            safe = re.sub(r"[;\r\n\x00]", "_", str(value))
            fields.append((PREFIX + key, safe))
    return "; ".join(key + "=" + value for key, value in fields)


def parse_comments(text):
    fields = {}
    for key, value in FIELD_RE.findall(text or ""):
        if key in fields:  # Duplicated metadata is ambiguous, even if equal.
            return None
        fields[key] = value.strip()
    if fields.get(VERSION_FIELD) != "1":
        return None
    values = {}
    for key, value in fields.items():
        if not key.endswith("_probability"):
            continue
        try:
            number = probability(float(value))
        except (ValueError, OverflowError):
            return None
        if number is None:
            return None
        values[key[len(PREFIX):-len("_probability")]] = number
    if "good" not in values:
        return None
    return {"status": "classified", "probabilities": values,
            "model": fields.get(PREFIX + "model", ""),
            "predicted_class": fields.get(PREFIX + "predicted_class", ""),
            "source": fields.get(PREFIX + "source", ""),
            "generated_at_utc": fields.get(PREFIX + "generated_at_utc"),
            "json_sha256": fields.get(PREFIX + "json_sha256")}


def append_comments(comments, cnn, **provenance):
    fields = comment_fields(cnn, **provenance)
    if not fields:
        return comments
    text = comments or ""
    if FIELD_RE.search(text):
        raise ValueError("Existing spectral CNN fields must not be overwritten or duplicated.")
    return text + (" " if text.rstrip().endswith(";") else "; " if text else "") + fields
