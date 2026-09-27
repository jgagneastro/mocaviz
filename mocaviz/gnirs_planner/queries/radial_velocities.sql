SELECT v.moca_oid,v.id AS rv_id,v.radial_velocity_kms,v.radial_velocity_kms_unc,
 v.adopt_asis,v.flags,v.epoch,v.n_measurements,v.moca_pid,v.moca_instid,v.moca_specid,
 v.origin,v.comments,v.publication_comments,p.bibcode,p.doi,p.`name` AS reference
 FROM data_radial_velocities v LEFT JOIN moca_publications p ON p.moca_pid=v.moca_pid
 WHERE v.ignored=0 AND v.radial_velocity_kms IS NOT NULL AND v.moca_oid IN (__OIDS__) ORDER BY v.moca_oid,v.id
