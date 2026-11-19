# RVBAM sampling payload archive

The hosted RVBAM Explorer loads run and segment metadata, stored parameter summaries, radial velocities, spectra and saved diagnostic images. Posterior samples, histograms, correlations and rebuilt corner plots use the local archive. The viewer switches to metadata-only mode when the archive is unavailable.

Local MOCAviz requires PyArrow to read the archive. Use the Python environment that launches MOCAviz. The current Python 3.8 environment uses PyArrow 17.0.0. Hosted MOCAviz does not require PyArrow for this feature.

## Initial copy from MOCAdb

Use PEGIII once mounted. The first copy can start at 7 p.m. Toronto time. It reads MOCAdb over SQL and writes to `/Volumes/PEGIII/RVBAM/sampling_payloads/`. The database table occupies roughly 369 GiB in InnoDB, and the payloads are already compressed. Measure throughput from the first completed batches to estimate the duration. The initial copy can continue overnight.

1. Record the source DDL, connection time zone, capture time, run ID bounds and source row count. Verify that PEGIII has space for the archive and scratch files. Capture all rows, including ignored and private rows.
2. Stream bounded batches of rows explicitly selecting the invisible `payload` BLOB. Keep its bytes unchanged with its type, dimensions, compression, provenance, visibility, and timestamps. Convert directly to Parquet while recording restart checkpoints and source IDs. Track any mixed snapshot caused by a reconnect or concurrent uploads and reconcile affected ranges on the next read.
3. Sort by `moca_sample_run_id`, then by `moca_payload_id`. Write batches in `payloads/run_low=<lower-bound>/`, with modest Parquet row groups so an individual posterior can be read without loading an entire partition. Include the `moca_sample_run_id` column inside each file.
4. Verify input coverage, Parquet counts and hashes, and decode paired chain and log-probability blobs for representative runs. Compare the arrays and a rebuilt corner plot with RVBAM Explorer's existing behavior. Publish `manifest.json` atomically only after these checks pass.
5. Start local MOCAviz with PEGIII mounted. Verify a known posterior and then test the viewer with the archive unavailable. Any MOCAdb deletion is a separate decision.

The viewer expects an archive manifest like this:

```json
{
  "format": "rvbam-sampling-payloads-v1",
  "status": "complete",
  "run_bucket_width": 1000,
  "partitions": {
    "1000": ["part-0000.parquet"],
    "2000": ["part-0000.parquet", "part-0001.parquet"]
  }
}
```

Partition keys are the lower bounds of integer intervals aligned to
`run_bucket_width`. Each list contains only the filenames published for that
partition. The manifest may also include row counts, hashes and import
provenance. An update writes immutable new filenames and swaps the manifest
after verification. Unpublished files are invisible to the viewer.

## Future uploads

RVBAM jobs upload payloads to MOCAdb through the existing persistence path. No extra HPC project storage is needed. At each transfer, take an overlapping modification-time window and verify ID and checksum coverage. Preserve the original source payload IDs, but scope them by export generation because a future truncate can reset the auto-increment counter. Update affected partitions and preserve conflicting versions when a run has multiple payloads of the same kind. Record the new checkpoint only after archive validation.

The viewer reads an archive only for direct loopback requests on the Mac with
PEGIII mounted. Run metadata and linked diagnostics still come from MOCAdb.
