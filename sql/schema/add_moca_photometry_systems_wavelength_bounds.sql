-- Review before applying to mocadb_private_tables.
--
-- Adds 5%/95% bandpass wavelength bounds to moca_photometry_systems and
-- backfills only NULL wavelength metadata from existing data_photometric_bandpasses
-- rows. Existing non-NULL average_wavelength, min_wavelength, and max_wavelength
-- values are not overwritten.

ALTER TABLE `moca_photometry_systems`
  ADD COLUMN IF NOT EXISTS `min_wavelength` float DEFAULT NULL
    COMMENT '5th-percentile wavelength of the photometric response CDF, in angstrom.'
    AFTER `average_wavelength`,
  ADD COLUMN IF NOT EXISTS `max_wavelength` float DEFAULT NULL
    COMMENT '95th-percentile wavelength of the photometric response CDF, in angstrom.'
    AFTER `min_wavelength`;

DROP TEMPORARY TABLE IF EXISTS `tmp_moca_photometry_bandpass_stats`;

CREATE TEMPORARY TABLE `tmp_moca_photometry_bandpass_stats` AS
WITH ordered AS (
  SELECT
    `moca_psid`,
    `wavelength_angstrom`,
    GREATEST(COALESCE(`relative_spectral_response`, 0.0), 0.0) AS `response`,
    LAG(`wavelength_angstrom`) OVER (
      PARTITION BY `moca_psid`
      ORDER BY `wavelength_angstrom`
    ) AS `prev_wavelength_angstrom`,
    LAG(GREATEST(COALESCE(`relative_spectral_response`, 0.0), 0.0)) OVER (
      PARTITION BY `moca_psid`
      ORDER BY `wavelength_angstrom`
    ) AS `prev_response`
  FROM `data_photometric_bandpasses`
  WHERE `moca_psid` IS NOT NULL
    AND `wavelength_angstrom` IS NOT NULL
    AND `relative_spectral_response` IS NOT NULL
),
segments AS (
  SELECT
    `moca_psid`,
    `wavelength_angstrom`,
    `prev_wavelength_angstrom`,
    GREATEST(
      0.0,
      0.5 * (`response` + `prev_response`)
      * (`wavelength_angstrom` - `prev_wavelength_angstrom`)
    ) AS `segment_area`,
    GREATEST(
      0.0,
      0.5 * (`wavelength_angstrom` * `response`
             + `prev_wavelength_angstrom` * `prev_response`)
      * (`wavelength_angstrom` - `prev_wavelength_angstrom`)
    ) AS `segment_lam_area`
  FROM ordered
  WHERE `prev_wavelength_angstrom` IS NOT NULL
    AND `wavelength_angstrom` > `prev_wavelength_angstrom`
),
cumulative AS (
  SELECT
    `moca_psid`,
    `wavelength_angstrom`,
    `prev_wavelength_angstrom`,
    `segment_area`,
    SUM(`segment_area`) OVER (
      PARTITION BY `moca_psid`
      ORDER BY `wavelength_angstrom`
    ) AS `cum_area`,
    SUM(`segment_area`) OVER (
      PARTITION BY `moca_psid`
    ) AS `total_area`,
    SUM(`segment_lam_area`) OVER (
      PARTITION BY `moca_psid`
    ) AS `total_lam_area`
  FROM segments
),
percentile_rows AS (
  SELECT
    c.`moca_psid`,
    p.`pct`,
    CASE
      WHEN c.`segment_area` > 0 THEN
        c.`prev_wavelength_angstrom`
        + ((p.`pct` * c.`total_area`) - (c.`cum_area` - c.`segment_area`))
          / c.`segment_area`
          * (c.`wavelength_angstrom` - c.`prev_wavelength_angstrom`)
      ELSE c.`wavelength_angstrom`
    END AS `pct_wavelength`,
    ROW_NUMBER() OVER (
      PARTITION BY c.`moca_psid`, p.`pct`
      ORDER BY c.`wavelength_angstrom`
    ) AS `rn`
  FROM cumulative c
  JOIN (
    SELECT 0.05 AS `pct` FROM DUAL
    UNION ALL
    SELECT 0.95 AS `pct` FROM DUAL
  ) p
  WHERE c.`total_area` > 0
    AND c.`cum_area` >= p.`pct` * c.`total_area`
),
bounds AS (
  SELECT
    `moca_psid`,
    MAX(CASE WHEN `pct` = 0.05 AND `rn` = 1 THEN `pct_wavelength` END) AS `min_wavelength`,
    MAX(CASE WHEN `pct` = 0.95 AND `rn` = 1 THEN `pct_wavelength` END) AS `max_wavelength`
  FROM percentile_rows
  GROUP BY `moca_psid`
),
weighted AS (
  SELECT
    `moca_psid`,
    MAX(CASE WHEN `total_area` > 0 THEN `total_lam_area` / `total_area` END) AS `average_wavelength`
  FROM cumulative
  GROUP BY `moca_psid`
)
SELECT
  w.`moca_psid`,
  w.`average_wavelength`,
  b.`min_wavelength`,
  b.`max_wavelength`
FROM weighted w
JOIN bounds b USING (`moca_psid`);

-- Audit rows where existing non-NULL metadata differs from the bandpass-derived
-- value. These are intentionally not changed by the UPDATE below.
SELECT
  ps.`moca_psid`,
  ps.`average_wavelength` AS `current_average_wavelength`,
  stats.`average_wavelength` AS `bandpass_average_wavelength`,
  ps.`min_wavelength` AS `current_min_wavelength`,
  stats.`min_wavelength` AS `bandpass_min_wavelength`,
  ps.`max_wavelength` AS `current_max_wavelength`,
  stats.`max_wavelength` AS `bandpass_max_wavelength`
FROM `moca_photometry_systems` ps
JOIN `tmp_moca_photometry_bandpass_stats` stats USING (`moca_psid`)
WHERE (ps.`average_wavelength` IS NOT NULL
       AND ABS(ps.`average_wavelength` - stats.`average_wavelength`) > 1.0)
   OR (ps.`min_wavelength` IS NOT NULL
       AND ABS(ps.`min_wavelength` - stats.`min_wavelength`) > 1.0)
   OR (ps.`max_wavelength` IS NOT NULL
       AND ABS(ps.`max_wavelength` - stats.`max_wavelength`) > 1.0)
ORDER BY ps.`moca_psid`;

UPDATE `moca_photometry_systems` ps
JOIN `tmp_moca_photometry_bandpass_stats` stats USING (`moca_psid`)
SET
  ps.`average_wavelength` = COALESCE(ps.`average_wavelength`, stats.`average_wavelength`),
  ps.`min_wavelength` = COALESCE(ps.`min_wavelength`, stats.`min_wavelength`),
  ps.`max_wavelength` = COALESCE(ps.`max_wavelength`, stats.`max_wavelength`)
WHERE ps.`average_wavelength` IS NULL
   OR ps.`min_wavelength` IS NULL
   OR ps.`max_wavelength` IS NULL;

SELECT
  COUNT(*) AS `n_photometry_systems_with_minmax`
FROM `moca_photometry_systems`
WHERE `min_wavelength` IS NOT NULL
  AND `max_wavelength` IS NOT NULL;

DROP TEMPORARY TABLE IF EXISTS `tmp_moca_photometry_bandpass_stats`;
