SELECT sp.moca_oid,sp.moca_specid,sp.moca_specpackid,sp.instrument_name,sp.instrument_mode_name,
 sp.median_spectral_resolving_power,sp.median_snr_per_res_element,sp.exposure_time
 FROM moca_spectra sp
 JOIN moca_objects o ON o.moca_oid=sp.moca_oid AND o.ignored=0
 JOIN data_spectral_types s ON s.moca_oid=o.moca_oid AND s.adopted=1 AND s.ignored=0
 WHERE sp.ignored=0 AND sp.instrument_name='GNIRS' AND s.spectral_type_number>=5
 ORDER BY sp.moca_oid,sp.moca_specid
