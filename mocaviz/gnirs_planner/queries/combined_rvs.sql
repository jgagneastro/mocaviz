SELECT moca_oid,id,radial_velocity_kms,radial_velocity_kms_unc,n_measurements,n_epochs,
 radial_velocity_intrinsic_scatter,avg_epoch_yr,epoch_span_yr,origin
 FROM calc_radial_velocities_combined WHERE ignored=0 AND is_public=0 AND moca_oid IN (__OIDS__)
