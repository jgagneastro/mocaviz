-- Optional indexes for the bd_colors_fast prototype.
-- Compared against live information_schema.STATISTICS on 2026-05-08.
-- Review with SHOW INDEX / EXPLAIN before applying to MOCAdb.
-- Target database: mocadb_private_tables, not the public view database.

ALTER TABLE `data_spectral_indices`
  ADD INDEX `idx_bdcol_sidx_oid_siid_ignored`
  (`moca_oid`, `moca_siid`, `ignored`);

ALTER TABLE `data_equivalent_widths`
  ADD INDEX `idx_bdcol_ew_oid_spid_ignored`
  (`moca_oid`, `moca_spid`, `ignored`);

ALTER TABLE `data_association_ages`
  ADD INDEX `idx_bdcol_assoc_age_aid_adopted`
  (`moca_aid`, `adopted`, `age_myr`);

-- Helps MOCAdb spectral typing load only the requested wavelength windows for
-- all standard spectra, especially before the in-memory cache is warm.
ALTER TABLE `data_spectra`
  ADD INDEX `idx_fastmocaviz_spectra_specid_ignored_wv`
  (`moca_specid`, `ignored`, `wavelength_angstrom`);

-- Optional for the fast XYZUVW explorer. The member query filters by
-- association and membership type through summary_all_members, whose private
-- base table currently has single-column moca_aid/is_public indexes but no
-- composite covering this filter plus the ORDER BY.
ALTER TABLE `summary_all_members_both`
  ADD INDEX `idx_fastxyzuvw_aid_mtid_public_oid`
  (`moca_aid`, `moca_mtid`, `is_public`, `moca_oid`);

-- Optional for the legacy radial-velocity diagnostics page. The page filters
-- pcat_mcmc_rv_pipeline by target_name, template_name, and pipeline_version,
-- while the current unique index has order/window/segment columns between
-- template_name and pipeline_version.
ALTER TABLE `pcat_mcmc_rv_pipeline`
  ADD INDEX `idx_fastrv_dataset`
  (`target_name`, `template_name`, `pipeline_version`, `order_number`, `window_number`, `segment_number`, `id`);

-- Optional for file URL lookups by file set and diagnostic description.
ALTER TABLE `mechanics_file_sets`
  ADD INDEX `idx_fastrv_fsid_description_fid`
  (`moca_fsid`, `description`, `moca_fid`);
