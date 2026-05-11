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

-- Helps fast spectral typing load only the requested wavelength windows for
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
