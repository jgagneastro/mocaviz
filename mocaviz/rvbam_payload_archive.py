"""Read RVBAM sampling payloads from a mounted private archive."""

from __future__ import annotations

import json
import os
from pathlib import Path

ARCHIVE_FORMAT = "rvbam-sampling-payloads-v1"
ARCHIVE_VOLUME = Path("/Volumes/PEGIII")
ARCHIVE_ROOT = ARCHIVE_VOLUME / "RVBAM" / "sampling_payloads"
PAYLOAD_COLUMNS = (
    "moca_payload_id", "moca_sample_run_id", "moca_sampling_parameter_id",
    "payload_kind", "payload_subkind", "dtype", "compression", "order_comment",
    "n_dim", "dim1", "dim2", "dim3", "dim4", "burnin_iterations",
    "thinning_interval", "n_stored_samples", "series_count", "origin", "rls",
    "is_public", "ignored", "created_timestamp", "modified_timestamp", "comments",
)


class PayloadArchive:
    def __init__(self, root: Path, manifest: dict, revision: str):
        self.root = root
        self.revision = revision
        self.bucket_width = manifest["run_bucket_width"]
        self.partitions = manifest["partitions"]

    @classmethod
    def open(cls, volume: Path = ARCHIVE_VOLUME, root: Path = ARCHIVE_ROOT) -> PayloadArchive | None:
        """Stay unavailable until the volume and a completed manifest are present."""
        try:
            if not volume.is_mount():
                return None
            root.resolve().relative_to(volume.resolve())
            with (root / "manifest.json").open(encoding="utf-8") as stream:
                manifest = json.load(stream)
                stat = os.fstat(stream.fileno())
            if (not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT or manifest.get("status") != "complete"
                    or not isinstance(manifest.get("run_bucket_width"), int)
                    or manifest["run_bucket_width"] < 1
                    or not isinstance(manifest.get("partitions"), dict)):
                return None
            # The hosted app can run without the optional Parquet dependency.
            import pyarrow.dataset  # noqa: F401

            revision = f"{stat.st_dev}:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}"
            return cls(root, manifest, revision)
        except (OSError, ValueError, ImportError):
            return None

    def _read(self, run_ids, columns, payload_id=None):
        from pyarrow import dataset as ds

        ids = sorted({int(run_id) for run_id in run_ids if run_id is not None})
        if not ids:
            return []
        buckets = sorted({run_id // self.bucket_width * self.bucket_width for run_id in ids})
        paths = []
        for bucket in buckets:
            for name in self.partitions.get(str(bucket), []):
                if Path(name).name != name or not name.endswith(".parquet"):
                    raise ValueError("Invalid payload filename in the RVBAM archive manifest")
                paths.append(str(self.root / "payloads" / f"run_low={bucket}" / name))
        if not paths:
            return []
        predicate = ds.field("moca_sample_run_id").isin(ids)
        if payload_id is not None:
            predicate &= ds.field("moca_payload_id") == int(payload_id)
        return ds.dataset(paths, format="parquet").to_table(columns=list(columns), filter=predicate).to_pylist()

    def metadata(self, run_ids, columns=PAYLOAD_COLUMNS):
        return self._read(run_ids, columns)

    def chain(self, run_id):
        rows = [
            row for row in self.metadata([run_id], (
                "moca_payload_id", "payload_kind", "payload_subkind", "ignored"
            ))
            if row["payload_kind"] == "chains" and not row["ignored"]
        ]
        selected = min(rows, key=lambda row: (row["payload_subkind"] != "posterior", row["moca_payload_id"]),
                       default=None)
        return self._load_selected(run_id, selected)

    def vector(self, run_id, terms):
        terms = set(terms)
        candidates = []
        for row in self.metadata([run_id], ("moca_payload_id", "payload_kind", "payload_subkind",
                                            "order_comment", "ignored")):
            if row["ignored"]:
                continue
            for rank, key in enumerate(("payload_subkind", "payload_kind", "order_comment")):
                if str(row[key] or "").lower() in terms:
                    candidates.append((rank, row["moca_payload_id"], row))
                    break
        selected = min(candidates, key=lambda candidate: candidate[:2])[2] if candidates else None
        return self._load_selected(run_id, selected)

    def _load_selected(self, run_id, selected):
        if selected is None:
            return None
        rows = self._read([run_id], (*PAYLOAD_COLUMNS, "payload"), selected["moca_payload_id"])
        return rows[0] if rows else None
