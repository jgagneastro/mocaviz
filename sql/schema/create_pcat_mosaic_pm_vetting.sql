-- Review and apply on mocadb_private_tables. No existing tables are altered.
-- The foreign key identifies the managed data_proper_motions row. The immutable
-- bundle preserves the fitted values even if a later review updates that row.
CREATE TABLE IF NOT EXISTS mocadb_private_tables.pcat_mosaic_pm_vetting (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    moca_oid BIGINT UNSIGNED NOT NULL,
    decision ENUM('adopt','reject') NOT NULL,
    webtool_version VARCHAR(64) NOT NULL,
    method VARCHAR(20) NOT NULL,
    fit_mode ENUM('pm','pm_plx') NOT NULL,
    measurement_bundle JSON NOT NULL,
    comparison_json JSON NOT NULL,
    delta_pmra DOUBLE DEFAULT NULL,
    delta_pmdec DOUBLE DEFAULT NULL,
    proper_motion_id BIGINT UNSIGNED DEFAULT NULL,
    reviewed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    undone_at TIMESTAMP(6) NULL DEFAULT NULL,
    is_public TINYINT(1) NOT NULL DEFAULT 0,
    rls VARCHAR(20) NOT NULL DEFAULT 'gagne',
    PRIMARY KEY (id),
    UNIQUE KEY mosaic_review_request (request_id),
    KEY mosaic_review_current (moca_oid, undone_at, id),
    KEY mosaic_review_proper_motion (proper_motion_id),
    CONSTRAINT mosaic_review_oid FOREIGN KEY (moca_oid)
        REFERENCES mocadb_private_tables.moca_objects (moca_oid) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT mosaic_review_pm FOREIGN KEY (proper_motion_id)
        REFERENCES mocadb_private_tables.data_proper_motions (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT mosaic_review_private CHECK (is_public=0 AND rls='gagne')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Private visual decisions and reproducible MOSAIC proper-motion fits';
