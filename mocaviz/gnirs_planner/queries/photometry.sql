SELECT id,moca_oid,moca_psid,magnitude,magnitude_unc,system_band_simple,
 adopted_simpleband,adopted,is_synthetic,flags,moca_pid FROM data_photometry
 WHERE ignored=0 AND (adopted=1 OR adopted_simpleband=1) AND system_band_simple IN ('j','k','ks')
 AND moca_oid IN (__OIDS__)
