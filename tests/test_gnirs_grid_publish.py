"""Publishing updates only metadata in the existing shared SQLite cache."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mocaviz.gnirs_planner import cache
from scripts.publish_gnirs_rv_grid import main, validate
from test_gnirs_planner import seed
from test_gnirs_rv_settings import synthetic_grid

class GridPublishTests(unittest.TestCase):
    def test_complete_validation_and_single_file_publication(self):
        grid=synthetic_grid();rows=[]
        for r in grid['rows']:
            if r['sptn']!=15:continue
            for n in (10,12,14,16,18,20,22,23,24,26,28,30):rows.append({**r,'sptn':n})
        grid.update(rows=rows,coverage_fractions=[.25,.5,.75,.9,.95],slits=[.1,.15,.2,.3,.45,.675,1.],version='test')
        self.assertEqual(validate(grid),1512)
        with self.assertRaises(ValueError):validate({**grid,'rows':rows[:-1]})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'shared.sqlite';seed(path)
            before=path.read_bytes();revision=cache.revision(path)
            def publish(*flags):
                with patch('sys.argv',['publish','--cache',str(path),*flags]),patch('sys.stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(grid).encode()))),patch('sys.stdout',io.StringIO()):main()
            publish('--check');self.assertEqual(before,path.read_bytes())
            publish();self.assertNotEqual(revision,cache.revision(path))
            with cache.reader(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM targets').fetchone()[0],2)
                meta=cache.get(db,'catalog');self.assertEqual(meta['revision'],cache.get(db,'revision'))
                self.assertEqual(len(meta['grid']['rows']),1512)
            self.assertEqual([p.name for p in path.parent.iterdir()],['shared.sqlite'])

if __name__=='__main__':unittest.main()
