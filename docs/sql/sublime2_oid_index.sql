-- Recommendation only. Run manually against the online MOCAdb database.
-- Verified 2026-11-05: no current index begins with moca_oid on this table.
-- This is a non-unique index: an object can have multiple SUBLIME2 apertures.

SHOW INDEX FROM `mocadb_private_tables`.`pcat_sublime_candidates_v2`
WHERE Column_name = 'moca_oid';

ALTER TABLE `mocadb_private_tables`.`pcat_sublime_candidates_v2`
    ADD INDEX IF NOT EXISTS `idx_pcat_sublime_candidates_v2_moca_oid` (`moca_oid`),
    ALGORITHM=INPLACE,
    LOCK=NONE;

SHOW INDEX FROM `mocadb_private_tables`.`pcat_sublime_candidates_v2`
WHERE Key_name = 'idx_pcat_sublime_candidates_v2_moca_oid';
