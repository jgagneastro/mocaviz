-- Public MOCAdb views needed by the Spectral Index Explorer.
-- Existing required public views already exist for:
--   data_spectra, data_spectral_types, mechanics_all_designations,
--   moca_chemical_species, moca_objects, moca_spectra, moca_spectral_indices.
-- This migration adds the three new spectral-observable views.
--
-- The views use SQL SECURITY DEFINER so public MOCAdb users can read the
-- public view rows without direct SELECT grants on mocadb_private_tables.
-- Apply as an account allowed to create DEFINER=`management`@`%` views.

USE `mocadb`;

CREATE OR REPLACE
ALGORITHM=MERGE
DEFINER=`management`@`%`
SQL SECURITY DEFINER
VIEW `mocadb`.`moca_spectral_observable_definitions` AS
SELECT
    `main`.`id` AS `id`,
    `main`.`definition_uid` AS `definition_uid`,
    `main`.`observable_type` AS `observable_type`,
    `main`.`moca_siid` AS `moca_siid`,
    `main`.`moca_spid` AS `moca_spid`,
    `main`.`moca_pid` AS `moca_pid`,
    `main`.`source_key` AS `source_key`,
    `main`.`source_label` AS `source_label`,
    `main`.`legacy_observable_name` AS `legacy_observable_name`,
    `main`.`display_name` AS `display_name`,
    `main`.`calculation_family` AS `calculation_family`,
    `main`.`value_unit` AS `value_unit`,
    `main`.`wavelength_unit` AS `wavelength_unit`,
    `main`.`band_statistic` AS `band_statistic`,
    `main`.`continuum_method` AS `continuum_method`,
    `main`.`continuum_polynomial_degree` AS `continuum_polynomial_degree`,
    `main`.`combination_method` AS `combination_method`,
    `main`.`formula_expression` AS `formula_expression`,
    `main`.`min_spectral_resolution` AS `min_spectral_resolution`,
    `main`.`min_spt` AS `min_spt`,
    `main`.`max_spt` AS `max_spt`,
    `main`.`min_wavelength` AS `min_wavelength`,
    `main`.`max_wavelength` AS `max_wavelength`,
    `main`.`legacy_source_path` AS `legacy_source_path`,
    `main`.`legacy_line_start` AS `legacy_line_start`,
    `main`.`legacy_line_end` AS `legacy_line_end`,
    `main`.`quality_status` AS `quality_status`,
    `main`.`comments` AS `comments`,
    `main`.`created_timestamp` AS `created_timestamp`,
    `main`.`modified_timestamp` AS `modified_timestamp`
FROM `mocadb_private_tables`.`moca_spectral_observable_definitions` `main`
WHERE `main`.`is_public` = 1;

CREATE OR REPLACE
ALGORITHM=MERGE
DEFINER=`management`@`%`
SQL SECURITY DEFINER
VIEW `mocadb`.`moca_spectral_observable_bands` AS
SELECT
    `main`.`id` AS `id`,
    `main`.`definition_uid` AS `definition_uid`,
    `main`.`band_order` AS `band_order`,
    `main`.`band_role` AS `band_role`,
    `main`.`band_label` AS `band_label`,
    `main`.`wavelength_start` AS `wavelength_start`,
    `main`.`wavelength_end` AS `wavelength_end`,
    `main`.`band_statistic` AS `band_statistic`,
    `main`.`comments` AS `comments`,
    `main`.`created_timestamp` AS `created_timestamp`,
    `main`.`modified_timestamp` AS `modified_timestamp`
FROM `mocadb_private_tables`.`moca_spectral_observable_bands` `main`
JOIN `mocadb_private_tables`.`moca_spectral_observable_definitions` `defn`
    ON `defn`.`definition_uid` = `main`.`definition_uid`
WHERE `defn`.`is_public` = 1;

CREATE OR REPLACE
ALGORITHM=MERGE
DEFINER=`management`@`%`
SQL SECURITY DEFINER
VIEW `mocadb`.`moca_spectral_observable_definition_links` AS
SELECT
    `main`.`id` AS `id`,
    `main`.`parent_definition_uid` AS `parent_definition_uid`,
    `main`.`child_definition_uid` AS `child_definition_uid`,
    `main`.`link_order` AS `link_order`,
    `main`.`relationship` AS `relationship`,
    `main`.`coefficient` AS `coefficient`,
    `main`.`comments` AS `comments`,
    `main`.`created_timestamp` AS `created_timestamp`,
    `main`.`modified_timestamp` AS `modified_timestamp`
FROM `mocadb_private_tables`.`moca_spectral_observable_definition_links` `main`
JOIN `mocadb_private_tables`.`moca_spectral_observable_definitions` `parent_defn`
    ON `parent_defn`.`definition_uid` = `main`.`parent_definition_uid`
JOIN `mocadb_private_tables`.`moca_spectral_observable_definitions` `child_defn`
    ON `child_defn`.`definition_uid` = `main`.`child_definition_uid`
WHERE `parent_defn`.`is_public` = 1
    AND `child_defn`.`is_public` = 1;

GRANT SELECT ON `mocadb`.`moca_spectral_observable_definitions` TO 'public'@'%';
GRANT SELECT ON `mocadb`.`moca_spectral_observable_bands` TO 'public'@'%';
GRANT SELECT ON `mocadb`.`moca_spectral_observable_definition_links` TO 'public'@'%';

-- Verification queries.
SELECT 'moca_spectral_observable_definitions' AS view_name, COUNT(*) AS n
FROM `mocadb`.`moca_spectral_observable_definitions`;

SELECT 'moca_spectral_observable_bands' AS view_name, COUNT(*) AS n
FROM `mocadb`.`moca_spectral_observable_bands`;

SELECT 'moca_spectral_observable_definition_links' AS view_name, COUNT(*) AS n
FROM `mocadb`.`moca_spectral_observable_definition_links`;

SELECT TABLE_NAME, DEFINER, SECURITY_TYPE, CHECK_OPTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'mocadb'
    AND TABLE_NAME IN (
        'moca_spectral_observable_definitions',
        'moca_spectral_observable_bands',
        'moca_spectral_observable_definition_links'
    )
ORDER BY TABLE_NAME;
