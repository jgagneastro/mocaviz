from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RepositoryStructureTests(unittest.TestCase):
    def test_production_application_has_a_clear_package_name(self) -> None:
        self.assertTrue((REPOSITORY_ROOT / "mocaviz" / "__init__.py").is_file())
        self.assertTrue((REPOSITORY_ROOT / "mocaviz" / "app.py").is_file())

    def test_former_package_is_only_a_compatibility_launcher(self) -> None:
        legacy_root = REPOSITORY_ROOT / "bd_colors_fast"
        self.assertEqual(
            {path.name for path in legacy_root.iterdir() if path.name != "__pycache__"},
            {"README.md", "__init__.py", "app.py"},
        )
        for retired_subdirectory in ("data", "static", "vendor"):
            self.assertFalse((legacy_root / retired_subdirectory).exists())

    def test_database_sql_is_grouped_outside_the_application_package(self) -> None:
        sql_root = REPOSITORY_ROOT / "sql"
        self.assertTrue((sql_root / "README.md").is_file())
        for category in ("indexes", "schema", "staging", "views"):
            self.assertTrue((sql_root / category).is_dir(), category)
            self.assertTrue(any((sql_root / category).glob("*.sql")), category)

        self.assertFalse(any(REPOSITORY_ROOT.glob("*.sql")))
        self.assertFalse(any((REPOSITORY_ROOT / "mocaviz").glob("*.sql")))


if __name__ == "__main__":
    unittest.main()
