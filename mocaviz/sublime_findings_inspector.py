"""Bounded, read-only cutouts and the SUBLIME reviewer's survey conventions."""
from __future__ import annotations
import base64
import bz2
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CUTOUT_ROOTS=(Path('/Users/jonathan/Documents/Python/Python_Packages/sublime/outputs/submine_cutouts'),
              Path('/Volumes/Phoenix_A/sublime/outputs'))
MAX_IMAGE=20_000_000


def remote_text(url, timeout=12, limit=4_000_000):
    req=urllib.request.Request(url,headers={'User-Agent':'MOCAviz-SUBLIME-Findings/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Survey response exceeds the interactive limit.')
        return data.decode('utf-8',errors='replace')


def cutout_paths(source_key):
    if not re.fullmatch(r'\d+:[+\-\d.]+:[+\-\d.]+',str(source_key)):return []
    tile,ra,dec=source_key.split(':')
    if not all(math.isfinite(float(v)) for v in (ra,dec)):return []
    if not 0<=float(ra)<360 or not -90<=float(dec)<=90:return []
    filename='%d_%s_%s_deep_cutout.png'%(int(tile),ra,dec)
    return [root/('tile_%05d'%int(tile))/sub/filename for root in CUTOUT_ROOTS for sub in ('winning_spectra','winning_source_spectra')]


def image_bytes(path):
    for candidate in (path,path.with_name(path.name+'.bz2')):
        try:
            if candidate.stat().st_size>MAX_IMAGE:continue
            data=candidate.read_bytes()
            if candidate.suffix=='.bz2':data=bz2.BZ2Decompressor().decompress(data,max_length=MAX_IMAGE+1)
            if len(data)>MAX_IMAGE or not data.startswith(b'\x89PNG\r\n\x1a\n'):continue
            return data
        except (OSError,EOFError,ValueError):continue
    return None


def cutouts(cur,oid):
    cur.execute("SELECT designation,ra,`dec` FROM moca_objects WHERE moca_oid=%s AND ignored=0",(oid,))
    obj=cur.fetchone()
    if not obj:raise ValueError('Object is no longer active.')
    cur.execute('''SELECT source_key,epoch_yr,min_epoch,max_epoch,'SUBLIME2' AS sample FROM pcat_sublime_candidates_v2 WHERE moca_oid=%s
        UNION ALL SELECT source_key,epoch_yr,min_epoch,max_epoch,'SUBLIME1' AS sample FROM pcat_sublime_candidates WHERE moca_oid=%s''',(oid,oid))
    keys={}
    for row in cur.fetchall():keys.setdefault(row['source_key'],[]).append(row)
    images=[];missing=0
    for key,epochs in keys.items():
        data=None
        for path in cutout_paths(key):
            data=image_bytes(path)
            if data is not None:break
        if data is None:missing+=1;continue
        images.append({'source_key':key,'epochs':epochs,'data':'data:image/png;base64,'+base64.b64encode(data).decode('ascii')})
        if len(images)>=10:break
    return {'object':obj,'images':images,'missing_cutouts':missing,'source_keys':len(keys)}


def survey(survey,ra,dec,fov):
    """Coordinates alone go to the same public image services as the reviewer."""
    if survey not in ('2mass','ps1','nsc'):raise ValueError('Unknown survey.')
    if not all(math.isfinite(v) for v in (ra,dec,fov)) or not 0<=ra<360 or not -90<=dec<=90 or not 10<=fov<=300:
        raise ValueError('Invalid survey coordinates or field size.')
    if survey=='2mass':
        q=urllib.parse.urlencode({'mode':'getImage','file_type':'colorimage','survey':'2mass',
              'subsetsize':fov/60,'RA':ra,'DEC':dec,'reproject':'true'})
        return {'url':'https://irsa.ipac.caltech.edu/applications/finderchart/servlet/api?'+q,
                'label':'2MASS J/H/K · 1997–2001 coadd','orientation':'N up · E left','crosshair':True}
    if survey=='ps1':
        url='https://ps1images.stsci.edu/cgi-bin/ps1filenames.py?'+urllib.parse.urlencode({'ra':ra,'dec':dec,'filters':'izy'})
        lines=[line.split() for line in remote_text(url).splitlines() if line.strip()]
        header=next((line for line in lines if 'filter' in line and 'filename' in line),None)
        if not header:raise ValueError('PS1 returned no image table.')
        fi,ni=header.index('filter'),header.index('filename');names={}
        for line in lines:
            if len(line)>max(fi,ni) and '.fits' in line[ni]:names.setdefault(line[fi],line[ni])
        if any(b not in names for b in 'yzi'):raise ValueError('No complete PS1 i/z/y coverage at this position.')
        q=urllib.parse.urlencode({'ra':ra,'dec':dec,'size':max(32,round(fov/.25)), 'output_size':400,
                                'format':'png','red':names['y'],'green':names['z'],'blue':names['i']})
        return {'url':'https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?'+q,'label':'PS1 DR2 i/z/y · stack coadd',
                'orientation':'N up · E left','crosshair':True}
    url='https://datalab.noirlab.edu/sia/nsc_dr2?'+urllib.parse.urlencode({'POS':'%s,%s'%(ra,dec),
             'SIZE':'%s,%s'%(fov/3600,fov/3600),'FORMAT':'ALL','INTERSECT':'OVERLAPS','VERB':2})
    xml=ET.fromstring(remote_text(url))
    fields=[e for e in xml.iter() if e.tag.split('}')[-1]=='FIELD']
    index={str(e.get('name') or e.get('ID') or '').lower():i for i,e in enumerate(fields)}
    def cell(cells,key):
        i=index.get(key)
        return ''.join(cells[i].itertext()).strip() if i is not None and i<len(cells) else ''
    rows=[]
    for tr in (e for e in xml.iter() if e.tag.split('}')[-1]=='TR'):
        cells=[e for e in tr if e.tag.split('}')[-1]=='TD']
        preview=cell(cells,'preview').replace('&amp;','&')
        if not preview or cell(cells,'prodtype').lower()!='image':continue
        try:seeing=float(cell(cells,'seeing') or 999)
        except ValueError:seeing=999
        rows.append({'url':preview,'band':cell(cells,'obs_bandpass').lower(),'epoch':cell(cells,'date_obs').split('T')[0],'seeing':seeing})
    if not rows:raise ValueError('No NSC DR2 image coverage returned.')
    rows.sort(key=lambda r:({'z':0,'i':1,'r':2,'y':3,'g':4}.get(r['band'],5),r['seeing']))
    row=rows[0]
    # SIA previews can cover a whole exposure. Do not draw a central target marker.
    return {'url':row['url'],'label':'NSC DR2 %s · %s'%(row['band'],row['epoch']),
            'orientation':'N up · E left (preview flipped as in reviewer)','flip_x':True,'crosshair':False,
            'note':'Per-exposure preview; target is not assumed to be at the image center.'}


def wiseview_html():
    html=remote_text('http://byw.tools/wiseview-v2',limit=1_000_000)
    html=html.replace('<head>','<head><base href="./">',1)
    for name in ('flash3.js','flash3-theme.css'):
        html=html.replace('static/'+name,'wiseview-assets/'+name)
    return html
