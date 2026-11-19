import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from mocaviz.rvbam_payload_archive import ARCHIVE_FORMAT, PAYLOAD_COLUMNS, PayloadArchive

viz = importlib.import_module("mocaviz.app")


class RvbamPayloadArchiveTests(unittest.TestCase):
    def setUp(self):
        viz._RVBAM_CACHE.clear()
        viz._RVBAM_ARRAY_CACHE.clear()
        self.client = viz.app.test_client()
        self.endpoint = "/api/rvbam-explorer/segment/11/posterior-summary"

    def fake_query(self, _conn, sql, _params):
        if "FROM pcat_rv_sampling_segments" in sql:
            return pd.DataFrame([{"moca_rv_sampling_segment_id": 11, "moca_sample_run_id": 1001}])
        if "FROM pcat_sampling_parameters" in sql:
            return pd.DataFrame([{"param_name": "rv", "param_index": 0, "units": "km/s"}])
        self.fail(f"Unexpected SQL call: {sql}")

    def get_posterior(self, host, **kwargs):
        engine = SimpleNamespace(connect=lambda: tempfile.TemporaryFile())
        with patch.object(viz, "_engine", return_value=engine), \
             patch.object(viz, "_rvbam_required_tables_available", return_value=(True, [])), \
             patch.object(viz, "_read_sql", side_effect=self.fake_query):
            response = self.client.get(self.endpoint, base_url=host, **kwargs)
        data = response.get_json()
        self.assertEqual(response.status_code, 200, data)
        return response, data

    def test_hosted_and_forwarded_requests_never_open_archive(self):
        with patch.object(viz.sys, "platform", "darwin"), patch.object(PayloadArchive, "open") as open_archive:
            cases = (
                {"host": "https://dataviz.mocadb.ca"},
                {"host": "http://localhost", "headers": {"X-Forwarded-Host": "dataviz.mocadb.ca"}},
                {"host": "http://localhost", "environ_overrides": {"REMOTE_ADDR": "192.0.2.14"}},
            )
            for case in cases:
                with self.subTest(case=case):
                    _, data = self.get_posterior(**case)
                    self.assertEqual(data["samples"], [])
                    self.assertEqual(data["parameterOptions"][0]["name"], "rv")
                    self.assertIn("local MOCAviz", data["meta"]["message"])
            open_archive.assert_not_called()

    def test_mounted_archive_and_disconnect_use_different_response_caches(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("the optional local pyarrow package is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            volume = Path(temporary)
            root = volume / "RVBAM" / "sampling_payloads"
            bucket = root / "payloads" / "run_low=1000"
            bucket.mkdir(parents=True)
            data = np.asarray([[4.0], [6.0], [8.0]], dtype="<f4")
            common = dict.fromkeys(PAYLOAD_COLUMNS)
            common.update(moca_sample_run_id=1001, dtype="f4", compression="none", ignored=0)
            chain = dict(common, moca_payload_id=70, payload_kind="chains", payload_subkind="posterior",
                         n_dim=2, dim1=3, dim2=1, n_stored_samples=3, payload=data.tobytes())
            vector = dict(common, moca_payload_id=71, payload_kind="lnp", payload_subkind="posterior_logl",
                          n_dim=1, dim1=3, n_stored_samples=3, payload=np.zeros(3, dtype="<f4").tobytes())
            unrelated = dict(chain, moca_payload_id=72, moca_sample_run_id=1002)
            pq.write_table(pa.Table.from_pylist([chain, vector, unrelated]), bucket / "part-001.parquet")
            manifest = {"format": ARCHIVE_FORMAT, "status": "complete", "run_bucket_width": 1000,
                        "partitions": {"1000": ["part-001.parquet"]}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            self.assertIsNone(PayloadArchive.open(volume, root))
            with patch.object(Path, "is_mount", return_value=True):
                archive = PayloadArchive.open(volume, root)
            self.assertIsNotNone(archive)
            self.assertEqual({row["moca_payload_id"] for row in archive.metadata([1001])}, {70, 71})
            self.assertEqual(archive.vector(1001, ("lnp",))["moca_payload_id"], 71)
            with patch.object(viz.sys, "platform", "darwin"), \
                 patch.object(PayloadArchive, "open", side_effect=[archive, None]):
                response, payload = self.get_posterior("http://127.0.0.1")
                self.assertEqual(payload["meta"]["sample_count"], 3)
                self.assertEqual([row["rv"] for row in payload["samples"]], [4.0, 6.0, 8.0])
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                _, disconnected = self.get_posterior("http://127.0.0.1")
                self.assertEqual(disconnected["samples"], [])
                self.assertEqual(disconnected["meta"]["sample_count"], 0)
                self.assertIn("PEGIII", disconnected["meta"]["message"])


if __name__ == "__main__":
    unittest.main()
