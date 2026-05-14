-- Optional index for the age PDFs page.
-- Target database: mocadb_private_tables, not the public view database.
-- Review with SHOW INDEX / EXPLAIN before applying to MOCAdb.

ALTER TABLE `calc_object_age_pdfs`
  ADD INDEX `idx_calc_object_age_pdfs_age_id_age_myr`
  (`age_id`, `age_myr`);
