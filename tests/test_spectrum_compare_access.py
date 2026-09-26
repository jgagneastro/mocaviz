"""Credential isolation, no-file requests and WSGI integration (synthetic DB)."""
from __future__ import annotations

import gzip
import io
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import patch

from werkzeug.test import Client
from werkzeug.wrappers import Response
from app import application
from mocaviz import spectrum_compare as compare
from mocaviz.app import app, _ENCODED_RESPONSE_CACHE, _ENCODED_RESPONSE_INFLIGHT


class FakeCursor:
    def __init__(self, role="collaborators"):
        self.role = role
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def execute(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        assert sql.lstrip().split()[0] in {"SELECT", "SET", "START"}, sql

    def fetchone(self):
        return {"authenticated_user": self.role + "@localhost"}

    def fetchall(self):
        sql, parameters = self.calls[-1]
        if "FROM moca_spectra_packages" in sql:
            return [{"moca_specpackid": 109, "moca_instid": "fire_magellan", "instrument_name": "FIRE", "active_spectra": 1}]
        if "FROM data_spectra" in sql:
            return [{"moca_specid": specid, "wavelength_angstrom": 10000 + i * 10,
                     "flux_flambda": (1 + i / 100) * (1 if specid == 1 else 2),
                     "flux_flambda_unc": 0.1, "ignored": int(i == 20)}
                    for specid in parameters for i in range(150)]
        if "SELECT legacy.moca_specid" in sql:
            return [{"moca_specid": 2, "moca_oid": 42, "moca_instid": "fire_magellan",
                     "moca_specpackid": 1, "instrument_mode_name": "prism", "observing_night": "2020-01-01"}]
        return [{"moca_specid": 1, "moca_oid": 42, "moca_specpackid": 109,
                 "moca_instid": "fire_magellan", "object_name": "Synthetic test object",
                 "instrument_mode_name": "prism", "observing_night": "2020-01-01",
                 "object_ra": 123, "object_dec": -45, "legacy_count": 1,
                 "data_reduction_pipeline_version": "test", "modification_date": "2026-09-26"}]


class FakeConnection:
    def __init__(self, role="collaborators"):
        self.cur = FakeCursor(role)
        self.rolled_back = self.closed = False

    def cursor(self):
        return self.cur

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


_audit_writes = None


def audit_files(event, args):
    if _audit_writes is None:
        return
    if event == "open":
        _path, mode, flags = args
        if (mode and any(char in mode for char in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            _audit_writes.append((event, args))
            raise AssertionError("Request attempted a file write")
    if event in {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.symlink", "os.link", "os.truncate", "subprocess.Popen"}:
        _audit_writes.append((event, args))
        raise AssertionError("Request attempted filesystem mutation or a subprocess")


sys.addaudithook(audit_files)


@contextmanager
def forbid_file_writes():
    global _audit_writes
    violations = []
    _audit_writes = violations
    try:
        yield violations
    finally:
        _audit_writes = None


class ComparisonAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(application, Response)
        self.password = secrets.token_urlsafe(24)
        self.headers = {"X-MOCA-User": "collaborators", "X-MOCA-Password": self.password,
                        "X-MOCA-Database": compare.PRIVATE_DB}
        self.socket_env = patch.dict(os.environ, {"MOCAVIZ_COMPARE_UNIX_SOCKET": ""})
        self.socket_env.start()
        self.addCleanup(self.socket_env.stop)

    def test_missing_public_empty_wrong_database_and_query_credentials_fail_closed(self):
        bad_headers = [{}, {**self.headers, "X-MOCA-User": "public"},
                       {**self.headers, "X-MOCA-Password": ""},
                       {**self.headers, "X-MOCA-Database": "mocadb"}]
        with patch.dict(os.environ, {"MOCA_USERNAME": "management", "MOCA_PASSWORD": self.password}), patch.object(compare.pymysql, "connect") as connect:
            for prefix in ("", "/js"):
                for endpoint in ("packages", "spectra", "spectrum?moca_specid=1", "packages?mock=1"):
                    for headers in bad_headers:
                        with self.subTest(prefix=prefix, endpoint=endpoint, user=headers.get("X-MOCA-User")):
                            response = self.client.get(prefix + "/api/spectrum-compare/" + endpoint, headers=headers)
                            self.assertEqual(response.status_code, 403)
                            self.assertIn("no-store", response.headers["Cache-Control"])
                            self.assertNotIn(self.password, response.text)
                self.assertEqual(self.client.get(prefix + "/api/spectrum-compare/packages?user=collaborators", headers=self.headers).status_code, 403)
            connect.assert_not_called()

    def test_all_data_routes_authenticate_every_request_close_and_never_cache(self):
        before = dict(_ENCODED_RESPONSE_CACHE)
        for prefix in ("", "/js"):
            for role in ("collaborators", "management"):
                for endpoint in ("packages", "spectra?package_id=all", "spectrum?moca_specid=1"):
                    connection = FakeConnection(role)
                    with patch.object(compare.pymysql, "connect", return_value=connection) as connect:
                        response = self.client.get(prefix + "/api/spectrum-compare/" + endpoint,
                                                   headers={**self.headers, "X-MOCA-User": role})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(connection.closed and connection.rolled_back)
                    options = connect.call_args.kwargs
                    self.assertEqual(options["password"], self.password)
                    self.assertEqual(options["ssl"].verify_mode, ssl.CERT_REQUIRED)
                    self.assertTrue(options["ssl"].check_hostname)
                    self.assertFalse(options["autocommit"])
                    self.assertEqual(connection.cur.calls[0][0], "SET TRANSACTION READ ONLY")
                    self.assertEqual(connection.cur.calls[1][0], "START TRANSACTION READ ONLY")
                    self.assertEqual(connection.cur.calls[2][0], "SELECT CURRENT_USER() AS authenticated_user FROM DUAL")
                    self.assertNotIn(self.password, response.text)
                    self.assertNotIn("Set-Cookie", response.headers)
                    self.assertNotIn("X-MOCA-Response-Cache", response.headers)
        self.assertEqual(before, dict(_ENCODED_RESPONSE_CACHE))
        self.assertFalse(_ENCODED_RESPONSE_INFLIGHT)

    def test_wrong_database_account_and_driver_errors_are_safe(self):
        connection = FakeConnection("public")
        with patch.object(compare.pymysql, "connect", return_value=connection):
            response = self.client.get("/api/spectrum-compare/packages", headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(connection.cur.calls), 3)
        self.assertTrue(connection.closed and connection.rolled_back)
        for code, expected in ((1045, 403), (2003, 503)):
            output = io.StringIO()
            with patch.object(compare.pymysql, "connect", side_effect=compare.pymysql.OperationalError(code, self.password)), redirect_stdout(output), redirect_stderr(output):
                response = self.client.get("/api/spectrum-compare/packages", headers=self.headers)
            self.assertEqual(response.status_code, expected)
            self.assertNotIn(self.password, response.text + output.getvalue())

    def test_request_errors_rollback_and_do_not_leak_tracebacks(self):
        connection = FakeConnection()
        with patch.object(compare.pymysql, "connect", return_value=connection), patch.object(compare, "package_rows", side_effect=RuntimeError(self.password)):
            response = self.client.get("/api/spectrum-compare/packages", headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertTrue(connection.closed and connection.rolled_back)
        self.assertNotIn(self.password, response.text)
        self.assertNotIn("Traceback", response.text)

    def test_page_assets_and_every_api_have_zero_file_mutations(self):
        paths = ["/spectrum-compare", "/js/spectrum-compare"]
        for asset in (Path(compare.__file__).parent / "static/spectrum_compare").glob("*.js"):
            paths += ["/static/spectrum_compare/" + asset.name, "/js/static/spectrum_compare/" + asset.name]
        paths += ["/api/spectrum-compare/packages", "/api/spectrum-compare/spectra?package_id=all",
                  "/api/spectrum-compare/spectrum?moca_specid=1", "/api/spectrum-compare/spectrum?moca_specid=bad"]
        with patch.object(compare.pymysql, "connect", side_effect=lambda **_: FakeConnection()), forbid_file_writes() as violations:
            for path in paths:
                with self.client.get(path, headers={**self.headers, "Accept-Encoding": "gzip"}) as response:
                    self.assertIn(response.status_code, (200, 400), path)
                    body = response.data
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    if response.mimetype == "application/json":
                        json.loads(body)
            self.assertEqual(violations, [])

    def test_local_socket_requires_explicit_server_config_and_retains_account_auth(self):
        connection = FakeConnection()
        with patch.dict(os.environ, {"MOCAVIZ_COMPARE_UNIX_SOCKET": "/run/mysqld/mysqld.sock"}), patch.object(compare.pymysql, "connect", return_value=connection) as connect:
            response = self.client.get("/api/spectrum-compare/packages", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(connect.call_args.kwargs["unix_socket"], "/run/mysqld/mysqld.sock")
        self.assertIsNone(connect.call_args.kwargs["ssl"])
        self.assertIn("CURRENT_USER()", connection.cur.calls[2][0])

    def test_not_in_public_menu_and_no_write_routes(self):
        for path in ("/", "/js/", "/api/js-home/context?mock=1"):
            with self.client.get(path) as response:
                self.assertNotIn("spectrum-compare", response.text)
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith(("spectrum_compare.", "spectrum_compare_compat.")):
                self.assertFalse(set(rule.methods) & {"POST", "PUT", "PATCH", "DELETE"})
        self.assertEqual(self.client.post("/api/spectrum-compare/packages", headers=self.headers).status_code, 405)


if __name__ == "__main__":
    unittest.main()
