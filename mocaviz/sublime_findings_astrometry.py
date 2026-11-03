"""Spectrum-specific astrometry and pixel overlays for the Atlas inspector."""
import base64
import io
import json
import math
import re
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import NoConvergence, WCS
from PIL import Image

from . import spherex_review as sr

LANES = ('spiffstacker', 'spiff', 'sublimeaperture')


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def julian_epoch(mjd=None, date=None):
    mjd = number(mjd)
    if mjd is not None and 35000 < mjd < 90000:
        return 2000 + (mjd - 51544.5) / 365.25
    if date:
        try:
            return float(Time(date).jyear)
        except (ValueError, TypeError):
            pass
    return None


def position(ra, dec, epoch=None, pmra=None, pmdec=None):
    ra, dec = number(ra), number(dec)
    if ra is None or dec is None or not 0 <= ra < 360 or not -90 <= dec <= 90:
        return None
    epoch = number(epoch)
    return {'ra':ra, 'dec':dec, 'epoch':epoch if epoch is not None and 1800 <= epoch <= 2200 else None,
            'pmra':number(pmra), 'pmdec':number(pmdec)}


def stacker_manifest(meta):
    """Read only the exact spectrum's manifest when its recorded directory is local."""
    filename = meta.get('original_filename') or ''
    folder = Path(meta.get('original_directory') or '.')
    if Path(filename).name != filename or not filename.endswith('_spectrum.csv') or not folder.is_absolute():
        return None
    try:
        path = (folder / (filename[:-len('_spectrum.csv')] + '_manifest.json')).resolve()
        if not any(root in path.parents for root in (Path('/Volumes'), Path.home()/'Documents')):
            return None
        if path.stat().st_size > 2_000_000:
            return None
        target = json.loads(path.read_text()).get('target', {})
        if str(target.get('moca_oid')) != str(meta['moca_oid']):
            return None
        return position(target.get('ra_deg'), target.get('dec_deg'), target.get('ref_epoch_yr'),
                        target.get('pmra_masyr'), target.get('pmdec_masyr'))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def spectrum_positions(cur, oid, ids):
    if not ids:
        return {}
    rows = sr.rows(cur, '''SELECT s.moca_specid,s.moca_oid,s.moca_specpackid,s.telescope_ra,s.telescope_dec,
        s.telescope_object_name,s.original_directory,s.original_filename,
        pm.pmra_masyr,pm.pmdec_masyr
        FROM moca_spectra s JOIN moca_objects mo ON mo.moca_oid=s.moca_oid
        LEFT JOIN data_proper_motions pm ON pm.id=(SELECT MAX(p.id) FROM data_proper_motions p
          WHERE p.moca_oid=mo.moca_oid AND p.ignored=0 AND p.adopted=1)
        WHERE mo.moca_oid=%s AND mo.ignored=0 AND s.moca_specid IN ('''
        + ','.join(['%s']*len(ids)) + ')', (oid,*ids.values()))
    by_id = {row['moca_specid']:row for row in rows}
    result = {}
    for lane, specid in ids.items():
        meta = by_id.get(specid)
        if not meta or meta['moca_specpackid'] != sr.LANES[lane]['pack']:
            continue
        stored = position(meta['telescope_ra'], meta['telescope_dec'])
        astrometry = None
        source = 'moca_spectra'
        if lane == 'spiff':
            refs = sr.rows(cur, '''SELECT DISTINCT reference_ra_deg,reference_dec_deg,reference_crd_epoch_yr,
                reference_pmra_masyr,reference_pmdec_masyr FROM data_spherex_spectra_spiff
                WHERE moca_specid=%s AND moca_oid=%s AND reference_ra_deg IS NOT NULL
                  AND reference_dec_deg IS NOT NULL LIMIT 2''', (specid,oid))
            if len(refs) == 1:
                ref = refs[0]
                astrometry = position(ref['reference_ra_deg'], ref['reference_dec_deg'], ref['reference_crd_epoch_yr'],
                                      ref['reference_pmra_masyr'], ref['reference_pmdec_masyr'])
                source = 'SPIFF reduction record'
        elif lane == 'spiffstacker':
            astrometry = stacker_manifest(meta)
            if astrometry:
                source = 'SPIFFStacker manifest'
        elif stored:
            candidate = re.fullmatch(r'SUBLIME2 (\d+)', meta.get('telescope_object_name') or '')
            if candidate:
                apertures = sr.rows(cur, '''SELECT epoch_yr FROM pcat_sublime_candidates_v2
                    WHERE id=%s AND moca_oid=%s''', (int(candidate[1]),oid))
                if apertures:
                    stored = position(stored['ra'], stored['dec'], apertures[0]['epoch_yr'])
        if stored:
            # Attach a reduction epoch only when it describes the stored coordinate.
            if astrometry and abs((stored['ra'] - astrometry['ra'] + 180) % 360 - 180) < 1e-7 and abs(stored['dec'] - astrometry['dec']) < 1e-7:
                stored.update(epoch=astrometry['epoch'], pmra=astrometry['pmra'], pmdec=astrometry['pmdec'])
            astrometry, source = stored, 'moca_spectra'
        if astrometry:
            if astrometry['pmra'] is None or astrometry['pmdec'] is None:
                astrometry.update(pmra=number(meta['pmra_masyr']), pmdec=number(meta['pmdec_masyr']))
            result[lane] = {**astrometry, 'specid':specid, 'source':source}
    return result


def propagated(point, epoch):
    coord = SkyCoord(point['ra']*u.deg, point['dec']*u.deg, frame='icrs')
    if epoch is None or any(point.get(k) is None for k in ('epoch','pmra','pmdec')):
        return coord, False
    east, north = point['pmra'], point['pmdec']
    return coord.directional_offset_by(math.atan2(east,north)*u.rad,
        math.hypot(east,north)*(epoch-point['epoch'])*u.mas), True


def fits_chart(data, positions, epoch=None, infrared=False):
    """Project onto the same FITS pixels we render, including celestial distortions."""
    with fits.open(io.BytesIO(data), memmap=False) as hdus:
        for hdu in hdus:
            header = hdu.header
            if header.get('NAXIS') != 2:
                continue
            width,height = (header.get(k,0) for k in ('NAXIS1','NAXIS2'))
            if min(width,height)<1 or width*height>4_000_000:
                continue
            wcs = WCS(header).celestial
            if not wcs.has_celestial:
                continue
            pixels = np.asarray(hdu.data, dtype=float)
            if pixels.shape != (height,width):
                continue
            if epoch is None:
                epoch = julian_epoch(header.get('MJD-AVG'), header.get('DATE-AVG'))
                if epoch is None:
                    epoch = julian_epoch(header.get('MJD-OBS'), header.get('DATE-OBS'))
            break
        else:
            raise ValueError('No bounded celestial FITS image.')
    good = np.isfinite(pixels)
    if not good.any():
        raise ValueError('No finite FITS pixels.')
    low,high = np.percentile(pixels[good], (4, 99.6))
    stretched = np.zeros_like(pixels)
    if high>low:
        stretched[good] = np.arcsinh(8*np.clip((pixels[good]-low)/(high-low),0,1))/np.arcsinh(8)
    grayscale = np.flipud((stretched*255).astype('uint8'))
    image = Image.fromarray(grayscale)
    if infrared:
        from matplotlib import cm
        rgb = cm.get_cmap('magma')(grayscale/255, bytes=True)[...,:3]
        image = Image.fromarray(rgb)
    png = io.BytesIO()
    image.save(png, format='PNG')
    marks = []
    for lane, point in positions.items():
        coord, projected = propagated(point, epoch)
        try:
            x,y = wcs.world_to_pixel(coord)
        except (ValueError, NoConvergence):
            continue
        if -.5 <= x < width-.5 and -.5 <= y < height-.5:
            marks.append({'lane':lane, 'x':float((x+.5)/width), 'y':float(1-(y+.5)/height), 'projected':projected})
    return {'data':'data:image/png;base64,'+base64.b64encode(png.getvalue()).decode('ascii'),
            'markers':marks, 'image_epoch':epoch}
