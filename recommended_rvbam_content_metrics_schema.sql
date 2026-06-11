-- Recommended MOCAdb schema additions for persisted RVBAM RV-content metrics.
--
-- Target private database: mocadb_private_tables.
-- Public database: mocadb views may also need to expose these columns, but
-- public views should still not expose `is_public` or `rls`.
--
-- Review before applying. This script is written for the new MariaDB 11.8
-- server, where ADD COLUMN IF NOT EXISTS and CREATE INDEX IF NOT EXISTS are
-- available.

USE `mocadb_private_tables`;

-- Inspect current private-table state first.
SELECT
  `column_name`,
  `column_type`,
  `is_nullable`,
  `column_default`,
  `column_comment`
FROM `information_schema`.`columns`
WHERE `table_schema` = DATABASE()
  AND `table_name` = 'pcat_rv_sampling_segments'
  AND `column_name` IN (
    'data_contrast',
    'model_contrast',
    'nmodel_10p_contrast',
    'noutliers_masked',
    'segment_snr_median',
    'segment_snr_p10',
    'segment_snr_p90',
    'segment_snr_npoints',
    'rv_content_method',
    'rv_content_version',
    'rv_content_computed_timestamp',
    'rv_content_status',
    'rv_content_error'
  )
ORDER BY `column_name`;

-- Segment-level metrics read directly by the JS RVBAM explorer.
ALTER TABLE `pcat_rv_sampling_segments`
  ADD COLUMN IF NOT EXISTS `data_contrast` DOUBLE DEFAULT NULL
    COMMENT 'RVBAM observed fractional data RV content contrast; v1 is intrinsic flux scatter after noise subtraction, revised after masking positive model residual outliers when model content is available',
  ADD COLUMN IF NOT EXISTS `model_contrast` DOUBLE DEFAULT NULL
    COMMENT 'RVBAM model fractional RV content contrast: (p99_flux - p1_flux) / abs(p99_flux) on the reconstructed model flux in this segment',
  ADD COLUMN IF NOT EXISTS `nmodel_10p_contrast` INT UNSIGNED DEFAULT NULL
    COMMENT 'Number of reconstructed model pixels with flux <= 0.9 * p99_flux in this segment',
  ADD COLUMN IF NOT EXISTS `noutliers_masked` INT UNSIGNED DEFAULT NULL
    COMMENT 'Number of positive data-minus-model residual pixels masked by the RV content diagnostic',
  ADD COLUMN IF NOT EXISTS `segment_snr_median` DOUBLE DEFAULT NULL
    COMMENT 'Median per-pixel flux/error SNR in this RVBAM segment',
  ADD COLUMN IF NOT EXISTS `segment_snr_p10` DOUBLE DEFAULT NULL
    COMMENT '10th percentile per-pixel flux/error SNR in this RVBAM segment',
  ADD COLUMN IF NOT EXISTS `segment_snr_p90` DOUBLE DEFAULT NULL
    COMMENT '90th percentile per-pixel flux/error SNR in this RVBAM segment',
  ADD COLUMN IF NOT EXISTS `segment_snr_npoints` INT UNSIGNED DEFAULT NULL
    COMMENT 'Number of finite positive-uncertainty spectral points used for segment SNR and data contrast',
  ADD COLUMN IF NOT EXISTS `rv_content_method` VARCHAR(96) DEFAULT NULL
    COMMENT 'Method identifier for persisted RVBAM RV-content metrics',
  ADD COLUMN IF NOT EXISTS `rv_content_version` VARCHAR(32) DEFAULT NULL
    COMMENT 'Version string for persisted RVBAM RV-content metrics',
  ADD COLUMN IF NOT EXISTS `rv_content_computed_timestamp` TIMESTAMP NULL DEFAULT NULL
    COMMENT 'UTC timestamp when RVBAM RV-content metrics were computed',
  ADD COLUMN IF NOT EXISTS `rv_content_status` VARCHAR(32) DEFAULT NULL
    COMMENT 'ok, observed_only, model_unavailable, data_unavailable, or failed',
  ADD COLUMN IF NOT EXISTS `rv_content_error` TEXT DEFAULT NULL
    COMMENT 'Short diagnostic error message from RVBAM RV-content metric computation';

-- Optional indexes for content filters. Keep only the indexes that EXPLAIN uses
-- on the production workload if write/update cost becomes noticeable.
CREATE INDEX IF NOT EXISTS `idx_rvseg_content_data_contrast`
  ON `pcat_rv_sampling_segments` (`data_contrast`);

CREATE INDEX IF NOT EXISTS `idx_rvseg_content_model_contrast`
  ON `pcat_rv_sampling_segments` (`model_contrast`);

CREATE INDEX IF NOT EXISTS `idx_rvseg_content_model_10p`
  ON `pcat_rv_sampling_segments` (`nmodel_10p_contrast`);

CREATE INDEX IF NOT EXISTS `idx_rvseg_content_snr`
  ON `pcat_rv_sampling_segments` (`segment_snr_median`);

CREATE INDEX IF NOT EXISTS `idx_rvseg_content_outliers`
  ON `pcat_rv_sampling_segments` (`noutliers_masked`);

-- Public view check. If `mocadb`.`pcat_rv_sampling_segments` exists as a view,
-- recreate that view with these columns included and with no `is_public` or
-- `rls` columns exposed.
SELECT
  `table_schema`,
  `table_name`,
  `table_type`
FROM `information_schema`.`tables`
WHERE `table_schema` IN ('mocadb_private_tables', 'mocadb')
  AND `table_name` = 'pcat_rv_sampling_segments'
ORDER BY `table_schema`;

SELECT
  `table_schema`,
  `table_name`,
  `column_name`
FROM `information_schema`.`columns`
WHERE `table_schema` = 'mocadb'
  AND `table_name` = 'pcat_rv_sampling_segments'
  AND `column_name` IN (
    'data_contrast',
    'model_contrast',
    'nmodel_10p_contrast',
    'noutliers_masked',
    'segment_snr_median',
    'segment_snr_p10',
    'segment_snr_p90',
    'segment_snr_npoints',
    'rv_content_method',
    'rv_content_version',
    'rv_content_computed_timestamp',
    'rv_content_status',
    'rv_content_error',
    'is_public',
    'rls'
  )
ORDER BY `column_name`;

-- Sanity check after RVBAM has backfilled values.
SELECT
  COUNT(*) AS `segments_total`,
  SUM(`data_contrast` IS NOT NULL) AS `segments_with_data_contrast`,
  SUM(`model_contrast` IS NOT NULL) AS `segments_with_model_contrast`,
  SUM(`segment_snr_median` IS NOT NULL) AS `segments_with_snr`,
  SUM(`rv_content_status` = 'ok') AS `segments_status_ok`,
  SUM(`rv_content_status` IS NOT NULL AND `rv_content_status` <> 'ok') AS `segments_status_non_ok`
FROM `pcat_rv_sampling_segments`;
