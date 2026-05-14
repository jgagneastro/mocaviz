-- Optional indexes for the RVBAM explorer.
-- Target database: mocadb_private_tables, not the public view database.
-- Review with SHOW INDEX / EXPLAIN before applying to MOCAdb.
--
-- These complement the existing single-column indexes on moca_oid,
-- moca_specid, moca_instid, moca_fsid, and pipeline_version.

-- Helps object-centered RVBAM browsing, where the explorer filters by object,
-- optional pipeline version, ignored state, and then loads matching spectra.
ALTER TABLE `pcat_rv_sampling_runs`
  ADD INDEX `idx_rvbam_runs_oid_pipeline_specid`
  (`moca_oid`, `pipeline_version`(64), `moca_specid`, `ignored`, `moca_rv_sample_run_id`);

-- Helps spectrum-centered RVBAM browsing and deep links from a known
-- moca_specid, again with optional pipeline-version and ignored filters.
ALTER TABLE `pcat_rv_sampling_runs`
  ADD INDEX `idx_rvbam_runs_specid_pipeline`
  (`moca_specid`, `pipeline_version`(64), `ignored`, `moca_rv_sample_run_id`);
