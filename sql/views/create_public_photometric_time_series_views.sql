-- PROPOSAL ONLY: public MOCAdb views for photometric time series.
--
-- This file is intended for review and manual application by a database
-- administrator. It has not been executed by Codex.
--
-- Live schema conventions inspected on 2026-07-20:
--
--   * `mocadb`.`moca_spectra` exposes an explicit column allowlist from
--     `mocadb_private_tables`.`moca_spectra` and keeps only `is_public = 1`.
--   * `mocadb`.`data_spectra` exposes child rows only through an INNER JOIN
--     to a parent `moca_spectra` row having `is_public = 1`.
--   * `mocadb`.`data_rotation_periods` likewise exposes only rows having
--     `is_public = 1` and does not expose its private `is_public`/`rls` fields.
--   * Those established views use `DEFINER = management@%`,
--     `SQL SECURITY DEFINER`, and `ALGORITHM = UNDEFINED`.
--   * `public`@`%` already has schema-wide SELECT and SHOW VIEW privileges on
--     `mocadb`; no new GRANT is required for these view names.
--
-- Security invariants in this proposal:
--
--   1. Keep SQL SECURITY DEFINER. SQL SECURITY INVOKER would require public
--      users to receive direct privileges on `mocadb_private_tables`, which
--      must not happen.
--   2. Use explicit column lists rather than SELECT * so future private-table
--      columns are not exposed automatically.
--   3. Do not expose `rls` or `is_public` from the private header table.
--   4. Determine child-point visibility only through a qualifying public
--      parent header. The INNER JOIN also excludes orphan/NULL parent IDs.
--   5. Do not add direct grants on either private source table.

CREATE OR REPLACE
ALGORITHM=UNDEFINED
DEFINER=`management`@`%`
SQL SECURITY DEFINER
VIEW `mocadb`.`moca_photometric_time_series` AS
SELECT
  `main`.`moca_photseqid` AS `moca_photseqid`,
  `main`.`moca_oid` AS `moca_oid`,
  `main`.`moca_pid` AS `moca_pid`,
  `main`.`flux_units` AS `flux_units`,
  `main`.`pipeline` AS `pipeline`,
  `main`.`mission_name` AS `mission_name`,
  `main`.`data_release` AS `data_release`,
  `main`.`original_filename` AS `original_filename`,
  `main`.`object_designation` AS `object_designation`,
  `main`.`object_designation_type` AS `object_designation_type`,
  `main`.`comments` AS `comments`,
  `main`.`created_timestamp` AS `created_timestamp`,
  `main`.`modified_timestamp` AS `modified_timestamp`,
  `main`.`bibcode` AS `bibcode`
FROM `mocadb_private_tables`.`moca_photometric_time_series` AS `main`
WHERE `main`.`is_public` = 1;

CREATE OR REPLACE
ALGORITHM=UNDEFINED
DEFINER=`management`@`%`
SQL SECURITY DEFINER
VIEW `mocadb`.`data_photometric_time_series` AS
SELECT
  `main`.`id` AS `id`,
  `main`.`moca_photseqid` AS `moca_photseqid`,
  `main`.`epoch_year` AS `epoch_year`,
  `main`.`flux` AS `flux`,
  `main`.`sector` AS `sector`,
  `main`.`created_timestamp` AS `created_timestamp`,
  `main`.`modified_timestamp` AS `modified_timestamp`
FROM `mocadb_private_tables`.`data_photometric_time_series` AS `main`
INNER JOIN `mocadb_private_tables`.`moca_photometric_time_series` AS `parent`
  ON `parent`.`moca_photseqid` = `main`.`moca_photseqid`
WHERE `parent`.`is_public` = 1;

-- Verification: both views must retain the established definer-security model.
SELECT
  `table_name`,
  `definer`,
  `security_type`,
  `check_option`,
  `is_updatable`
FROM `information_schema`.`views`
WHERE `table_schema` = 'mocadb'
  AND `table_name` IN (
    'moca_photometric_time_series',
    'data_photometric_time_series'
  )
ORDER BY `table_name`;

-- Expected result: zero. Security-control columns remain private.
SELECT
  COUNT(*) AS `exposed_security_control_columns`
FROM `information_schema`.`columns`
WHERE `table_schema` = 'mocadb'
  AND `table_name` IN (
    'moca_photometric_time_series',
    'data_photometric_time_series'
  )
  AND `column_name` IN ('is_public', 'rls');

-- Header parity: the public view must contain exactly the public private-table
-- rows, while the private rows remain withheld.
SELECT
  (
    SELECT COUNT(*)
    FROM `mocadb`.`moca_photometric_time_series`
  ) AS `public_view_headers`,
  (
    SELECT COUNT(*)
    FROM `mocadb_private_tables`.`moca_photometric_time_series`
    WHERE `is_public` = 1
  ) AS `expected_public_headers`,
  (
    SELECT COUNT(*)
    FROM `mocadb_private_tables`.`moca_photometric_time_series`
    WHERE `is_public` = 0
  ) AS `withheld_private_headers`
FROM DUAL;

-- Mora26 application check. The first count must be non-zero. The second can
-- scan many point rows, so allow it to finish before restarting the dataviz app.
SELECT
  COUNT(*) AS `mora26_public_light_curve_headers`
FROM `mocadb`.`moca_photometric_time_series`
WHERE `moca_pid` = 'Mora26';

SELECT
  COUNT(*) AS `mora26_public_light_curve_points`
FROM `mocadb`.`data_photometric_time_series` AS `points`
INNER JOIN `mocadb`.`moca_photometric_time_series` AS `headers`
  ON `headers`.`moca_photseqid` = `points`.`moca_photseqid`
WHERE `headers`.`moca_pid` = 'Mora26';

-- Operational note: restart the dataviz process after applying this file.
-- Its in-process table-existence cache can retain the earlier "missing view"
-- result even after the views have been created.
