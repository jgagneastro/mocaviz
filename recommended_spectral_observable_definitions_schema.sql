-- Recommended MOCAdb schema for visual spectral-index/EW definitions.
--
-- This is additive: it does not alter data_spectral_indices or
-- data_equivalent_widths. Apply from mocadb_private_tables after review.

CREATE TABLE IF NOT EXISTS `moca_spectral_observable_definitions` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Unique row identifier.',
  `definition_uid` varchar(120) NOT NULL COMMENT 'Stable definition key, usually source:paper:observable.',
  `observable_type` varchar(24) NOT NULL COMMENT 'spectral_index or equivalent_width.',
  `moca_siid` varchar(20) DEFAULT NULL COMMENT 'Optional spectral-index identifier in moca_spectral_indices.',
  `moca_spid` varchar(12) DEFAULT NULL COMMENT 'Optional chemical-species identifier in moca_chemical_species.',
  `moca_pid` varchar(20) DEFAULT NULL COMMENT 'Publication key where this definition was introduced.',
  `source_key` varchar(60) DEFAULT NULL COMMENT 'Short source key, e.g. kirkpatrick1999.',
  `source_label` varchar(120) DEFAULT NULL COMMENT 'Human-readable source label.',
  `legacy_observable_name` varchar(80) NOT NULL COMMENT 'Observable name in the source code or publication.',
  `display_name` varchar(120) DEFAULT NULL COMMENT 'Display name for apps.',
  `calculation_family` varchar(40) NOT NULL DEFAULT 'flux_ratio' COMMENT 'flux_ratio, equivalent_width, compound, profile_width, or external.',
  `value_unit` varchar(40) DEFAULT NULL COMMENT 'Physical unit of the calculated value, if not dimensionless.',
  `wavelength_unit` varchar(20) NOT NULL DEFAULT 'angstrom' COMMENT 'Unit used by min_wavelength, max_wavelength, and band rows.',
  `band_statistic` varchar(30) DEFAULT NULL COMMENT 'median, average, weighted_mean, total, or integral as applicable.',
  `continuum_method` varchar(40) DEFAULT NULL COMMENT 'Continuum handling, e.g. two_band_linear or polynomial_windows.',
  `continuum_polynomial_degree` tinyint(3) unsigned DEFAULT NULL COMMENT 'Polynomial degree for continuum fits when applicable.',
  `combination_method` varchar(40) DEFAULT NULL COMMENT 'direct, arithmetic_mean, weighted_sum, harmonic, ratio, sum, scaled, log10, copied_from, continuum_divided_by_feature, or formula.',
  `formula_expression` text DEFAULT NULL COMMENT 'Source expression for compound definitions or special calculation notes.',
  `min_spectral_resolution` float DEFAULT NULL COMMENT 'Minimum resolving power required by the definition.',
  `min_spt` float DEFAULT NULL COMMENT 'Earliest numerical spectral type where this definition is intended.',
  `max_spt` float DEFAULT NULL COMMENT 'Latest numerical spectral type where this definition is intended.',
  `min_wavelength` double DEFAULT NULL COMMENT 'Smallest wavelength needed to compute or display this definition, in angstrom.',
  `max_wavelength` double DEFAULT NULL COMMENT 'Largest wavelength needed to compute or display this definition, in angstrom.',
  `legacy_source_path` varchar(255) DEFAULT NULL COMMENT 'Source file used to seed this definition.',
  `legacy_line_start` int(11) unsigned DEFAULT NULL COMMENT 'First source line for the parsed definition.',
  `legacy_line_end` int(11) unsigned DEFAULT NULL COMMENT 'Last source line for the parsed definition.',
  `quality_status` varchar(24) NOT NULL DEFAULT 'review' COMMENT 'review, ready, or deprecated.',
  `comments` text DEFAULT NULL COMMENT 'Definition-specific notes.',
  `created_timestamp` timestamp NOT NULL DEFAULT current_timestamp(),
  `modified_timestamp` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `is_public` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_msod_definition_uid` (`definition_uid`),
  KEY `ix_msod_observable_type` (`observable_type`),
  KEY `ix_msod_moca_siid` (`moca_siid`),
  KEY `ix_msod_moca_spid` (`moca_spid`),
  KEY `ix_msod_moca_pid` (`moca_pid`),
  KEY `ix_msod_source_key` (`source_key`),
  KEY `ix_msod_quality_status` (`quality_status`),
  KEY `ix_msod_is_public` (`is_public`),
  CONSTRAINT `moca_spectral_observable_definitions_ibfk_1` FOREIGN KEY (`moca_siid`) REFERENCES `moca_spectral_indices` (`moca_siid`) ON UPDATE CASCADE,
  CONSTRAINT `moca_spectral_observable_definitions_ibfk_2` FOREIGN KEY (`moca_spid`) REFERENCES `moca_chemical_species` (`moca_spid`) ON UPDATE CASCADE,
  CONSTRAINT `moca_spectral_observable_definitions_ibfk_3` FOREIGN KEY (`moca_pid`) REFERENCES `moca_publications` (`moca_pid`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci COMMENT='Calculation metadata for spectral indices and equivalent widths.';

CREATE TABLE IF NOT EXISTS `moca_spectral_observable_bands` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Unique row identifier.',
  `definition_uid` varchar(120) NOT NULL COMMENT 'Definition key in moca_spectral_observable_definitions.',
  `band_order` smallint(5) unsigned NOT NULL COMMENT 'Display and calculation order within the definition.',
  `band_role` varchar(32) NOT NULL COMMENT 'numerator, denominator, feature, blue_continuum, red_continuum, continuum, or line_center.',
  `band_label` varchar(80) DEFAULT NULL COMMENT 'Human-readable label for the band.',
  `wavelength_start` double DEFAULT NULL COMMENT 'Band lower wavelength, in angstrom.',
  `wavelength_end` double DEFAULT NULL COMMENT 'Band upper wavelength, in angstrom.',
  `band_statistic` varchar(30) DEFAULT NULL COMMENT 'Optional statistic override for this band.',
  `comments` text DEFAULT NULL COMMENT 'Band-specific notes.',
  `created_timestamp` timestamp NOT NULL DEFAULT current_timestamp(),
  `modified_timestamp` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_msob_definition_role_order` (`definition_uid`,`band_role`,`band_order`),
  KEY `ix_msob_definition_uid` (`definition_uid`),
  KEY `ix_msob_band_role` (`band_role`),
  KEY `ix_msob_wavelength_start` (`wavelength_start`),
  KEY `ix_msob_wavelength_end` (`wavelength_end`),
  CONSTRAINT `moca_spectral_observable_bands_ibfk_1` FOREIGN KEY (`definition_uid`) REFERENCES `moca_spectral_observable_definitions` (`definition_uid`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci COMMENT='Wavelength windows used by spectral-index and EW definitions.';

CREATE TABLE IF NOT EXISTS `moca_spectral_observable_definition_links` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Unique row identifier.',
  `parent_definition_uid` varchar(120) NOT NULL COMMENT 'Compound definition key.',
  `child_definition_uid` varchar(120) NOT NULL COMMENT 'Component definition key.',
  `link_order` smallint(5) unsigned NOT NULL COMMENT 'Component order in the parent formula.',
  `relationship` varchar(40) NOT NULL DEFAULT 'component' COMMENT 'component, copied_from, numerator_component, or denominator_component.',
  `coefficient` double DEFAULT NULL COMMENT 'Optional scalar coefficient used in simple combinations.',
  `comments` text DEFAULT NULL COMMENT 'Component-specific notes.',
  `created_timestamp` timestamp NOT NULL DEFAULT current_timestamp(),
  `modified_timestamp` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_msodl_parent_child` (`parent_definition_uid`,`child_definition_uid`),
  KEY `ix_msodl_child_definition_uid` (`child_definition_uid`),
  CONSTRAINT `moca_spectral_observable_definition_links_ibfk_1` FOREIGN KEY (`parent_definition_uid`) REFERENCES `moca_spectral_observable_definitions` (`definition_uid`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `moca_spectral_observable_definition_links_ibfk_2` FOREIGN KEY (`child_definition_uid`) REFERENCES `moca_spectral_observable_definitions` (`definition_uid`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci COMMENT='Links from compound observable definitions to their component definitions.';

CREATE OR REPLACE VIEW `moca_spectral_index_definition_bands` AS
SELECT
  d.`definition_uid`,
  d.`moca_siid`,
  d.`moca_pid`,
  d.`source_key`,
  d.`source_label`,
  d.`legacy_observable_name`,
  d.`display_name`,
  d.`calculation_family`,
  d.`band_statistic` AS `definition_band_statistic`,
  d.`continuum_method`,
  d.`continuum_polynomial_degree`,
  d.`combination_method`,
  d.`formula_expression`,
  d.`quality_status`,
  b.`band_order`,
  b.`band_role`,
  b.`band_label`,
  b.`wavelength_start`,
  b.`wavelength_end`,
  COALESCE(b.`band_statistic`, d.`band_statistic`) AS `band_statistic`
FROM `moca_spectral_observable_definitions` d
JOIN `moca_spectral_observable_bands` b
  ON b.`definition_uid` = d.`definition_uid`
WHERE d.`observable_type` = 'spectral_index';

CREATE OR REPLACE VIEW `moca_equivalent_width_definition_bands` AS
SELECT
  d.`definition_uid`,
  d.`moca_spid`,
  d.`moca_pid`,
  d.`source_key`,
  d.`source_label`,
  d.`legacy_observable_name`,
  d.`display_name`,
  d.`calculation_family`,
  d.`continuum_method`,
  d.`continuum_polynomial_degree`,
  b.`band_order`,
  b.`band_role`,
  b.`band_label`,
  b.`wavelength_start`,
  b.`wavelength_end`
FROM `moca_spectral_observable_definitions` d
JOIN `moca_spectral_observable_bands` b
  ON b.`definition_uid` = d.`definition_uid`
WHERE d.`observable_type` = 'equivalent_width';
