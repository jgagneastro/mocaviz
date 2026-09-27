SELECT moca_oid,moca_specid,moca_specpackid,instrument_name,instrument_mode_name,
 median_spectral_resolving_power,median_snr_per_res_element,exposure_time
 FROM moca_spectra WHERE ignored=0
 AND ((median_spectral_resolving_power>=2000 OR instrument_name='GNIRS') OR instrument_name='GNIRS')
 AND moca_oid IN (__OIDS__)
