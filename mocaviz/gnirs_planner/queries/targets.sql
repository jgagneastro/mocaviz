SELECT o.moca_oid,o.designation,o.ra AS object_ra,o.`dec` AS object_dec,
 o.radec_origin,o.ignored AS object_ignored,
 s.id AS spt_id,s.spectral_type AS spt,s.spectral_type_number AS sptn,
 s.photometric_estimate,s.lowg_like,s.subdwarf_like,s.quality_flag AS spt_quality,
 s.moca_pid AS spt_ref,s.origin AS spt_origin,s.bibcode AS spt_bibcode,
 s.calculation_method AS spt_calculation_method,
 bs.id AS banyan_id,bs.moca_bsmdid,bs.moca_aid,bs.best_hyp,bs.best_ya,
 bs.observables,bs.ya_prob AS summed_young_prob,bs.uvw_sep,bs.rv_opt,bs.erv_opt,
 bs.u_opt,bs.v_opt,bs.w_opt,bs.modified_timestamp AS banyan_modified,
 bd.prob AS individual_prob_fraction,
 CASE WHEN d.photometric_estimate=1 AND bs.observables IN ('pm,plx','pm,rv,plx')
 THEN CASE WHEN bl.uvw_sep IS NULL OR (bs.uvw_sep IS NOT NULL AND bl.uvw_sep>bs.uvw_sep)
 THEN bs.uvw_sep ELSE bl.uvw_sep END ELSE bs.uvw_sep END AS uvw_sep_loose,
 a.`name` AS association_name,a.is_real,a.highly_contaminated,a.physical_nature,
 age.age_myr,age.age_string_myr AS age_label,age.moca_pid AS age_ref,age.bibcode AS age_bibcode,
 d.distance_pc,d.distance_pc_unc,d.photometric_estimate AS distance_photometric_estimate,
 d.moca_pid AS distance_ref,d.id AS distance_id,
 cr.id AS coordinate_id,cr.ra,cr.`dec`,cr.measurement_epoch_yr,cr.coord_frame,cr.frame_equinox,
 cr.moca_pid AS coordinate_ref,pm.pmra_masyr,pm.pmdec_masyr,pm.moca_pid AS pm_ref,
 dt.teff_k AS teff,dt.teff_k_unc AS teff_unc,dt.moca_pid AS teff_ref,
 dt.origin AS teff_origin,dt.bibcode AS teff_bibcode,dt.method_short AS teff_method,
 EXISTS(SELECT 1 FROM pcat_duplicated_vetting dv WHERE dv.potential_duplicated_moca_oid=o.moca_oid AND dv.classification='y')
 OR EXISTS(SELECT 1 FROM pcat_suspected_bd_duplicates du WHERE du.duplicated_moca_oid=o.moca_oid) AS likely_duplicate
 FROM moca_objects o
 JOIN data_spectral_types s ON s.moca_oid=o.moca_oid AND s.adopted=1 AND s.ignored=0
 LEFT JOIN calc_banyan_sigma bs ON bs.moca_oid=o.moca_oid AND bs.max_observables=1 AND bs.is_public=0
 AND bs.moca_bsmdid=(SELECT moca_bsmdid FROM moca_banyan_sigma_models WHERE adopted=1)
 LEFT JOIN calc_banyan_sigma_details bd ON bd.cbs_id=bs.id AND bd.moca_aid=bs.moca_aid
 LEFT JOIN data_distances d ON d.moca_oid=o.moca_oid AND d.adopted=1 AND d.ignored=0
 LEFT JOIN calc_banyan_sigma bl ON bl.moca_oid=o.moca_oid AND bl.is_public=0
 AND bl.moca_bsmdid=bs.moca_bsmdid AND bl.max_observables=0
 AND ((bs.observables='pm,plx' AND bl.observables='pm') OR (bs.observables='pm,rv,plx' AND bl.observables='pm,rv'))
 LEFT JOIN moca_associations a ON a.moca_aid=bs.moca_aid
 LEFT JOIN data_association_ages age ON age.moca_aid=bs.moca_aid AND age.adopted=1 AND age.ignored=0
 LEFT JOIN data_equatorial_coordinates cr ON cr.moca_oid=o.moca_oid AND cr.adopt_as_reference=1 AND cr.ignored=0
 LEFT JOIN data_proper_motions pm ON pm.moca_oid=o.moca_oid AND pm.adopted=1 AND pm.ignored=0
 LEFT JOIN data_teff dt ON dt.moca_oid=o.moca_oid AND dt.ignored=0 AND
 (dt.adopted=1 OR (dt.public_adopted=1 AND NOT EXISTS(SELECT 1 FROM data_teff dp WHERE dp.moca_oid=o.moca_oid AND dp.adopted=1 AND dp.ignored=0)))
 WHERE o.ignored=0 AND o.moca_oid IN (__OIDS__) ORDER BY o.moca_oid
