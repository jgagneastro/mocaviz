"""Decode only the requested timing curves from compact shared grid rows."""
import base64
import struct


def row_curves(grid, row, coverage=None):
    if 'timing_log_i32' not in row:
        return row['curves']
    if grid.get('timing_encoding') != 'base64-i32-le-ceil':
        raise ValueError('Unsupported timing encoding')
    data=base64.b64decode(row['timing_log_i32'],validate=True)
    fractions=grid['coverage_fractions'];frames=grid['frames'];count=grid['magnitude_count']
    if len(data)!=4*len(frames)*len(fractions)*count:
        raise ValueError('Incomplete packed timing row')
    selected=fractions if coverage is None else [coverage]
    output=[]
    for j,frame in enumerate(frames):
        logs={}
        for fraction in selected:
            offset=4*count*(j*len(fractions)+fractions.index(fraction))
            values=struct.unpack_from(f'<{count}i',data,offset)
            logs[str(float(fraction))]=[None if x==grid['timing_null'] else x/grid['timing_log_scale'] for x in values]
        output.append(dict(frame_seconds=frame,log_seconds=logs))
    return output
