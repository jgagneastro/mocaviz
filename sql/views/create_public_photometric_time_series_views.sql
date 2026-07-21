-- Public MOCAdb views for photometric time series.
--
-- These views intentionally do not expose `is_public` or `rls`, matching the
-- existing public-view convention in `mocadb`. Visibility is enforced by the
-- DEFINER view reading `mocadb_private_tables`.
--
-- Run with a database account that can create views in `mocadb` and can set
-- the definer to `management`@`%`, for example database root. Existing public
-- views such as `data_rotation_periods`, `moca_spectra`, and `data_spectra`
-- use the same definer and `SQL SECURITY DEFINER`.

CREATE OR REPLACE
ALGORITHM=MERGE
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
ALGORITHM=MERGE
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
JOIN `mocadb_private_tables`.`moca_photometric_time_series` AS `parent`
  ON `parent`.`moca_photseqid` = `main`.`moca_photseqid`
WHERE `parent`.`is_public` = 1;

SELECT
  `table_name`,
  `definer`,
  `security_type`
FROM `information_schema`.`views`
WHERE `table_schema` = 'mocadb'
  AND `table_name` IN ('moca_photometric_time_series', 'data_photometric_time_series')
ORDER BY `table_name`;

SELECT
  COUNT(*) AS `exposed_is_public_or_rls_columns`
FROM `information_schema`.`columns`
WHERE `table_schema` = 'mocadb'
  AND `table_name` IN ('moca_photometric_time_series', 'data_photometric_time_series')
  AND `column_name` IN ('is_public', 'rls');

SELECT
  COUNT(*) AS `mora26_public_light_curve_headers`
FROM `mocadb`.`moca_photometric_time_series`
WHERE `moca_pid` = 'Mora26';

SELECT
  COUNT(*) AS `mora26_public_light_curve_points`
FROM `mocadb`.`data_photometric_time_series` AS `dpts`
JOIN `mocadb`.`moca_photometric_time_series` AS `mpts`
  ON `mpts`.`moca_photseqid` = `dpts`.`moca_photseqid`
WHERE `mpts`.`moca_pid` = 'Mora26';
