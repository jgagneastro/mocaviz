SELECT moca_oid,classification,'spiffstacker' AS source FROM pcat_spherex_spiffstacker_visual_vetting WHERE moca_oid IN (__OIDS__)
 UNION ALL SELECT moca_oid,classification,'spiff' AS source FROM pcat_spherex_visual_vetting WHERE moca_oid IN (__OIDS__)
