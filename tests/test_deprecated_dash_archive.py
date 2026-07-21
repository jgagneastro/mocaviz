from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DASH_ARCHIVE = REPOSITORY_ROOT / "deprecated" / "dash"


class DeprecatedDashArchiveTests(unittest.TestCase):
    def test_dash_directories_are_archived_outside_the_production_root(self) -> None:
        for directory in ("pages", "assets", "utils"):
            self.assertFalse((REPOSITORY_ROOT / directory).exists())
            self.assertTrue((DASH_ARCHIVE / directory).is_dir())

    def test_all_explicitly_retired_dash_pages_are_in_the_archive(self) -> None:
        archived_pages = {path.name for path in (DASH_ARCHIVE / "pages").glob("*.py")}
        self.assertTrue(
            {
                "mcmc_rvs.py",
                "oage_pdfs.py",
                "mocaviz_trueflow_age_pdfs.py",
            }.issubset(archived_pages)
        )

    def test_production_python_entry_points_do_not_import_dash(self) -> None:
        for relative_path in ("app.py", "bd_colors_fast/app.py"):
            source_path = REPOSITORY_ROOT / relative_path
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported_roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots.add(node.module.split(".", 1)[0])
            self.assertNotIn("dash", imported_roots, relative_path)

    def test_production_requirements_do_not_install_dash(self) -> None:
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")
        package_names = {
            line.split("==", 1)[0].strip().lower()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertFalse(
            {
                "dash",
                "dash-core-components",
                "dash-html-components",
                "dash-table",
            }
            & package_names
        )


if __name__ == "__main__":
    unittest.main()
