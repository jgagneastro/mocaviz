"""Local synthetic browser fixture. Never imported by the production app.

Run from the repo root: python -B tests/serve_spectrum_compare_fixture.py
No real credentials/database or public mock-authentication bypass is involved.
"""
from pathlib import Path
import math
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.serving import run_simple, WSGIRequestHandler
from test_spectrum_compare_access import FakeConnection, FakeCursor, forbid_file_writes
from app import application
from mocaviz import spectrum_compare as compare


class BrowserCursor(FakeCursor):
    def fetchall(self):
        sql, parameters = self.calls[-1]
        rows = super().fetchall()
        if "FROM moca_spectra AS s" in sql:
            row = rows[0]
            if "WHERE s.moca_specid=" in sql:
                row["moca_specid"] = parameters[0]
                row["comments"] = "TCSHQA=WARNING; TCSELQA=WARNING"
                rows = [row]
            else:
                rows = [row, {**row, "moca_specid": 3, "object_name": "Second synthetic object"}]
            for row in rows:
                row["median_spectral_resolving_power"] = 1000
        if "FROM data_spectra" in sql:
            for row in rows:
                x = row["wavelength_angstrom"]
                row["flux_flambda"] *= 1 - .3 * math.exp(-((x - 10700) / 50) ** 2)
        return rows


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


def connect(**kwargs):
    connection = FakeConnection(kwargs["user"])
    connection.cur = BrowserCursor(kwargs["user"])
    return connection


if __name__ == "__main__":
    # Local test-only server; all file mutations raise, including swallowed ones.
    with patch.object(compare.pymysql, "connect", side_effect=connect), forbid_file_writes() as violations:
        try:
            run_simple("127.0.0.1", 8876, application, use_reloader=False,
                       use_debugger=False, threaded=False, request_handler=QuietHandler)
        finally:
            if violations:
                raise RuntimeError(f"Detected {len(violations)} filesystem mutations")
