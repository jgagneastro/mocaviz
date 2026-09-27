"""Pure in-memory adaptation of the original GNIRS science assembly."""
from collections import defaultdict
import math
import numpy as np
def grouped(rows,key='moca_oid'):
    out=defaultdict(list)
    for r in rows:out[r[key]].append(r)
    return out

def separation_arcsec(ra1,dec1,ra2,dec2):
    ra1,d1,ra2,d2=map(math.radians,[ra1,dec1,ra2,dec2])
    h=math.sin((d2-d1)/2)**2+math.cos(d1)*math.cos(d2)*math.sin((ra2-ra1)/2)**2
    return math.degrees(2*math.asin(math.sqrt(min(1,max(0,h)))))*3600

def assemble(raw, reference, previous):
    rows=raw['targets']
    by_oid={}
    for r in rows:
        prior=by_oid.get(r['moca_oid'])
        if prior and r!=prior:
            differences={k for k in r if k!='membership_detail_note' and r[k]!=prior.get(k)}
            if not differences:
                by_oid[r['moca_oid']]=prior
                continue
            if differences=={'individual_prob_fraction'}:
                # Four late-M rows have duplicate BANYAN detail entries with
                # near-identical probabilities. Preserve the conservative one
                # and expose the conflict; never merge other adopted values.
                values=[v for v in [r['individual_prob_fraction'],prior['individual_prob_fraction']] if v is not None]
                r={**r,'individual_prob_fraction':min(values) if values else None,
                   'membership_detail_note':'Duplicate BANYAN detail probabilities; conservative minimum retained'}
            else:raise ValueError(f"Conflicting adopted rows for {r['moca_oid']}: {sorted(differences)}")
        by_oid[r['moca_oid']]=r
    rows=list(by_oid.values())
    assert len(rows)==len({r['moca_oid'] for r in rows}),'Parent query returned duplicate OIDs'
    old=previous
    sequence=reference['spectral_type_axis']['points']
    rvs=grouped(raw['radial_velocities'])
    combined={r['moca_oid']:r for r in raw['combined_rvs']}
    phot=grouped(raw['photometry'])
    spectra=grouped(raw['spectra'])
    companions=grouped(raw['companions'])
    assoc_dist={r['moca_aid']:r for r in raw['association_distances']}
    vetting=grouped(raw['spiff_vetting'])
    archive={oid:r.get('archive_matches',[]) for oid,r in old.items()}
    planned={oid for oid,r in old.items() if r.get('planned_reduction_highres')}
    benchmarks={oid for oid,r in old.items() if r.get('rv_reference_audit')}
    component_overrides={}
    for oid,r in old.items():
        for band,measurement in r.get('photometry',{}).items():
            if measurement and measurement.get('component_override'):
                component_overrides.setdefault(oid,{})[band]=measurement
    for row in rows:
        oid=row['moca_oid'];e=old.get(oid,{})
        row['ra']=row['ra'] if row['ra'] is not None else row['object_ra']
        row['dec']=row['dec'] if row['dec'] is not None else row['object_dec']
        if row['coord_frame'] not in (None,'ICRS'):
            raise ValueError(f'Unsupported coordinate frame for {oid}: {row["coord_frame"]}')
        row['individual_prob']=None if row['individual_prob_fraction'] is None else row['individual_prob_fraction']*100
        if row['individual_prob'] is not None:assert 0<=row['individual_prob']<=100.0001
        row['observables']='+'.join(k for k in ['pm','plx','rv'] if k in (row['observables'] or '').split(',')) or 'unknown'
        row['association_mean_distance_pc']=assoc_dist.get(row['moca_aid'],{}).get('avg_dist')
        row['association_distance_public_fallback']=assoc_dist.get(row['moca_aid'],{}).get('is_public')==1
        row['association_age_is_conditional']=row['best_hyp']=='FIELD' and row['age_myr'] is not None
        if row['moca_aid'] is None:
            for k in ['age_myr','age_label','age_ref','age_bibcode']:row[k]=None
        if row['teff'] is None:
            n=row['sptn']
            row['teff']=float(np.interp(n,[p['sptn'] for p in sequence],[p['teff'] for p in sequence])) if sequence[0]['sptn']<=n<=sequence[-1]['sptn'] else None
            row['teff_source']='young SpT–Teff fallback' if row['teff'] is not None else 'unavailable'
            row['teff_ref']='sptn_teff_si_yng' if row['teff'] is not None else None
        else:row['teff_source']='adopted data_teff (private preferred, public-adopted fallback)'
        # Propagated companion/host values are useful context, but not a direct
        # measurement of this object's RV. Flagged direct measurements remain
        # visible; quality cuts belong in the reference-sample controls.
        rvrows=rvs.get(oid,[])
        host=[r for r in rvrows if 'propagate_host' in str(r.get('origin')).lower()]
        direct=[r for r in rvrows if r not in host and not any(w in str(r.get('origin')).lower() for w in ['banyan','predicted_rv'])]
        row['has_rv']=bool(direct)
        row['rv_measurements']=direct
        row['host_rv_measurements']=host
        row['rv_combined']=combined.get(oid) if direct else None
        if direct:
            representative=min(direct,key=lambda r:(not r['adopt_asis'],bool(r['flags']),r['radial_velocity_kms_unc'] is None or r['radial_velocity_kms_unc']<=0,r['radial_velocity_kms_unc'] or math.inf,r['rv_id']))
            row['rv_individual']=representative
            if row['rv_combined'] and not host:
                row['rv']={**row['rv_combined'],'adoption':'MOCAdb combined adopted estimate','references':sorted({r['moca_pid'] for r in direct if r['moca_pid']})}
            else:row['rv']={**representative,'adoption':'Individual measurement (adopt_asis first, then unflagged smallest uncertainty)','references':[representative['moca_pid']]}
        else:row['rv']=None;row['rv_individual']=None
        row['rv_reference_audit']='Prior benchmark audit; small formal errors do not certify stability' if oid in benchmarks else None
        row['photometry']={}
        for band in ['j','k']:
            available=[p for p in phot.get(oid,[]) if p['system_band_simple'].lower() in (['j'] if band=='j' else ['k','ks']) and p['magnitude'] is not None and not any(s in str(p['flags']).lower() for s in ['limit','ph_qual=u'])]
            chosen=min(available,key=lambda p:(not p['adopted_simpleband'],bool(p['is_synthetic']),p['magnitude_unc'] is None,p['magnitude_unc'] or 99,p['id']),default=None)
            if band in component_overrides.get(oid,{}):
                chosen=component_overrides[oid][band]
            row['photometry'][band]=chosen
        row['spectra']=spectra.get(oid,[])
        row['archive_matches']=archive.get(oid,[])
        row['archive_max_R']=max([0]+[s['median_spectral_resolving_power'] or 0 for s in row['spectra'] if str(s['instrument_name']).upper()=='GNIRS']+[a.get('estimated_R') or 0 for a in row['archive_matches']])
        row['archive_identity_review']=oid in [863715,873365]
        row['planned_reduction_highres']=oid in planned
        row['planned_reduction_resolution_floor']=2700
        row['host_separation']=None;row['host_separation_source']=None
        pairs=companions.get(oid,[])
        measured=[c for c in pairs if c['separation_as'] and c['separation_as']>0]
        if measured:
            c=min(measured,key=lambda c:(-(c['epoch'] or 0),c['separation_as_unc'] is None,c['separation_as_unc'] or 0))
            row['host_separation']=c['separation_as']*1000
            row['host_separation_source']=f"data_companion_separations #{c['separation_id']}; {c['moca_pid']}; epoch {c['epoch']}"
        elif pairs:
            values=[separation_arcsec(row['object_ra'],row['object_dec'],c['parent_ra'],c['parent_dec']) for c in pairs
                    if all(v is not None for v in (row['object_ra'],row['object_dec'],c['parent_ra'],c['parent_dec']))]
            values=[v for v in values if v>0]
            if values:row['host_separation']=min(values)*1000;row['host_separation_source']='Parent/child catalog angular separation; mixed epochs possible'
        if row['host_separation'] is None and e.get('host_separation') is not None:
            row['host_separation']=e['host_separation'];row['host_separation_source']='Audited host-separation value from existing selector cache'
        for key in ['gaia_neighbor_source_id','gaia_neighbor_separation_arcsec']:
            row[key]=e.get(key)
        row['gaia_neighbor_checked']=oid in old
        vv=sorted(vetting.get(oid,[]),key=lambda v:v['source']!='spiffstacker')
        row['spiff_vetting_classification']=vv[0]['classification'] if vv else None
        row['spiff_vetting_source']=vv[0]['source'] if vv else None
        row['ra_accessible']=row['ra'] is not None and (row['ra']/15>4 or row['ra']/15<1)
        row['restricted_access']=row['ra'] is not None and row['dec'] is not None and (row['ra']/15<6 or row['ra']/15>23 or row['dec']<-30 or row['dec']>73)
        row['report_url']=f'https://mocadb.ca/search/results?search-query=oid%28{oid}%29&search-type=star'
    return rows
