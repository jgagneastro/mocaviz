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
