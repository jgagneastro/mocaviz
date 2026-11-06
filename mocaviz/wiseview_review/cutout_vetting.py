"""Per-image cutout reviews within the caller's motion-review transaction."""
from . import cutout_specs as desktop

TABLE='pcat_spherex_cutout_visual_vetting'
CLASSIFICATION_SPECS=desktop.CLASSIFICATION_SPECS
FIELDS=('classification','classification_integer','comments','reviewer','ra_deg','dec_deg',
        'source_key','cutout_path','source_table','origin')


def canonical_path(path):
    value=str(path)
    return value[:-4] if value.endswith('.bz2') else value


def per_path_ready(cur):
    cur.execute('''SELECT INDEX_NAME,COLUMN_NAME,SEQ_IN_INDEX FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND NON_UNIQUE=0
        ORDER BY INDEX_NAME,SEQ_IN_INDEX''',(TABLE,))
    indexes={}
    for row in cur.fetchall():indexes.setdefault(row['INDEX_NAME'],[]).append(row['COLUMN_NAME'])
    return ['moca_oid','cutout_path_sha256'] in indexes.values() and ['moca_oid'] not in indexes.values()


def rows_for_object(cur,oid,*,lock=False):
    cur.execute('SELECT id,'+','.join('`'+name+'`' for name in FIELDS)+
                f' FROM `{TABLE}` WHERE moca_oid=%s ORDER BY id'+(' FOR UPDATE' if lock else ''),(oid,))
    return list(cur.fetchall())


def selected_rows(rows,paths):
    by_path={canonical_path(row['cutout_path']):row for row in rows if row.get('cutout_path')}
    return {path:by_path.get(path) for path in paths}


def apply(cur,oid,spec,images,obj,args,comments):
    if not per_path_ready(cur):
        raise ValueError('Per-cutout storage needs sql/cutout_vetting_per_path.sql; no reviews were saved')
    for image in images:
        sources=image['source_tables']
        source_table=args.source_table if args.source_table in sources else sources[0]
        values=(oid,spec.classification,spec.classification_integer,comments.strip() or None,
            args.reviewer or None,obj.ra_deg,obj.dec_deg,image['source_key'],image['cutout_path'],
            source_table,'wiseview_web/server.py')
        cur.execute(f'INSERT INTO `{TABLE}` (moca_oid,'+','.join('`'+name+'`' for name in FIELDS)+
            ') VALUES ('+','.join(['%s']*11)+') ON DUPLICATE KEY UPDATE '+
            ','.join('`'+name+'`=VALUES(`'+name+'`)' for name in FIELDS),values)


def restore(cur,oid,before,after):
    for path,row in before.items():
        if row is None:
            cur.execute(f'DELETE FROM `{TABLE}` WHERE id=%s AND moca_oid=%s',(after[path]['id'],oid))
        else:
            cur.execute(f'UPDATE `{TABLE}` SET '+','.join('`'+name+'`=%s' for name in FIELDS)+
                ' WHERE id=%s AND moca_oid=%s',tuple(row[name] for name in FIELDS)+(row['id'],oid))
