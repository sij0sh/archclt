from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from archctl import __version__
from archctl.core.io import write_json
from tests.fixtures.storefront import initialize
from tests.support import ProjectTest, build


class CliTests(ProjectTest):
    def setUp(self):
        super().setUp()
        write_json(self.root / "baseline.json", self.baseline.to_dict())
        write_json(self.root / "evidence.json", build(self.root))

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "archctl", "--root", str(self.root), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_version_matches_the_package_identity(self):
        result = subprocess.run([sys.executable, "-m", "archctl", "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)

    def test_cli_compile_impact_decisions_and_gate(self):
        self.cli("model", "validate")
        self.cli("model", "compile", "--out", "candidate.json")
        self.assertTrue((self.root / "candidate.json").is_file())
        result = self.cli("impact", "Change checkout", "--evidence", "evidence.json", "--paths", "app/orders/api.py")
        impact = json.loads(result.stdout)
        self.assertEqual(impact["assessment"], "complete")
        result = self.cli("decisions", "list", "--components", "orders")
        self.assertEqual(json.loads(result.stdout)["decisions"][0]["id"], "ADR-001")
        self.cli("decisions", "show", "ADR-001")
        self.cli("guard", "check", "--evidence", "evidence.json", "--baseline", "baseline.json", expected=2)
        self.cli("guard", "check", "--evidence", "evidence.json", "--baseline", "baseline.json", "--run", "--out", "gate.json")
        gate = json.loads((self.root / "gate.json").read_text())
        self.assertEqual(gate["status"], "passed")

    def test_cli_import_report_export_and_observe(self):
        self.cli("evidence", "validate", "--input", "evidence.json")
        self.cli("evidence", "import", "--input", "evidence.json")
        self.cli("report", "--evidence", "evidence.json", "--out", "report.md")
        self.assertIn("## Reconciliation", (self.root / "report.md").read_text())
        self.cli("reconcile", "--evidence", "evidence.json")
        exported = json.loads(self.cli("briefcase", "export-intent").stdout)
        self.assertFalse(exported["native_briefcase_format"])
        observed = json.loads(self.cli("observe", "run", "checkout", "--baseline", "baseline.json", "--evidence", "evidence.json").stdout)
        self.assertEqual(observed["status"], "passed")
        self.cli("observe", "import", "--input", "evidence.json", expected=3)

    def test_cli_fail_unknown_and_input_error_exit_codes(self):
        self.cli("impact", "No concrete scope", "--evidence", "evidence.json", expected=2)
        path = self.root / "app/orders/api.py"
        path.write_text("from app.ledger import store\n" + path.read_text())
        write_json(self.root / "evidence.json", build(self.root))
        self.cli("guard", "check", "--baseline", "baseline.json", "--evidence", "evidence.json", "--run", expected=1)
        self.cli("evidence", "validate", "--input", "does-not-exist.json", expected=3)
        self.cli("decisions", "show", "ADR-NOT-REAL", expected=3)

    def test_git_change_scope_includes_deleted_and_untracked_files(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        git("init", "-q")
        git("add", "app", "checks", "architecture")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "baseline")
        (self.root / ".gitignore").write_text("__pycache__/\n*.json\n.gitignore\n")
        (self.root / "app/orders/api.py").unlink()
        (self.root / "app/orders/new.py").write_text("# new source\n")
        write_json(self.root / "evidence.json", build(self.root))
        report = json.loads(self.cli("impact", "Rename", "--evidence", "evidence.json", "--changed").stdout)
        self.assertEqual(report["changed_paths"], ["app/orders/api.py", "app/orders/new.py"])

    def test_git_change_scope_excludes_tool_artifacts(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        git("init", "-q")
        git("add", "app", "checks", "architecture")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "baseline")
        artifact = self.root / ".archctl/tracked.json"
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_text("{}\n")
        git("add", "-f", ".archctl/tracked.json")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tool artifact")
        artifact.write_text("{\"changed\": true}\n")
        path = self.root / "app/orders/api.py"
        path.write_text(path.read_text() + "\n# edited\n")
        write_json(self.root / "evidence.json", build(self.root))
        report = json.loads(self.cli("impact", "Artifact", "--evidence", "evidence.json", "--changed",
                                     expected=2).stdout)
        self.assertIn("app/orders/api.py", report["changed_paths"])
        self.assertNotIn(".archctl/tracked.json", report["changed_paths"])

    def test_invalid_git_base_is_an_input_error(self):
        self.cli("impact", "Bad git", "--evidence", "evidence.json", "--changed", "--base-ref=-bad", expected=3)

    def test_git_scope_is_relative_to_nested_application_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repository = Path(temp.name)
        self.root = repository / "nested-app"
        initialize(self.root, demo=True)
        def git(*args):
            subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)
        git("init", "-q")
        (repository / "unrelated.txt").write_text("original\n")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "baseline")
        (self.root / ".gitignore").write_text("*.json\n.gitignore\n")
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text() + "\n# edited\n")
        (repository / "unrelated.txt").write_text("changed outside app\n")
        write_json(self.root / "evidence.json", build(self.root))
        report = json.loads(self.cli("impact", "Nested app", "--evidence", "evidence.json", "--changed").stdout)
        self.assertEqual(report["changed_paths"], ["app/orders/api.py"])

    def test_generated_output_cannot_overwrite_authority_or_source(self):
        source = self.root / "app/orders/api.py"
        original = source.read_text()
        self.cli("report", "--evidence", "evidence.json", "--out", "app/orders/api.py", expected=3)
        self.assertEqual(source.read_text(), original)
        self.cli("model", "compile", "--out", "architecture/model.yaml", expected=3)
        self.cli("guard", "check", "--evidence", "evidence.json", "--baseline", "baseline.json", "--out", "baseline.json", expected=3)

    def test_empty_task_or_environment_is_an_input_error(self):
        self.cli("impact", "", "--evidence", "evidence.json", "--paths", "app/orders/api.py", expected=3)
        self.cli("guard", "check", "--evidence", "evidence.json", "--baseline", "baseline.json", "--environment", "", expected=3)
