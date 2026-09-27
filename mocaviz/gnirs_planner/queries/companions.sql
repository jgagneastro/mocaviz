SELECT mc.moca_oid_child AS moca_oid,mc.moca_oid_parent,mc.moca_cid,
 p.ra AS parent_ra,p.`dec` AS parent_dec,p.designation AS parent_designation,
 cs.id AS separation_id,cs.separation_as,cs.separation_as_unc,cs.epoch,cs.moca_pid
 FROM moca_companions mc JOIN moca_objects p ON p.moca_oid=mc.moca_oid_parent
 LEFT JOIN data_companion_separations cs ON cs.moca_cid=mc.moca_cid AND cs.ignored=0
 WHERE mc.ignored=0 AND mc.moca_oid_child IN (__OIDS__)
