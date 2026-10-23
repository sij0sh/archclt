from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys

import yaml

from archctl.cli import main
from archctl.core.io import write_json
from tests.support import ProjectTest, build
from tests.test_check_architecture import contract


class CliContractTests(ProjectTest):
    def setUp(self):
        super().setUp()
        write_json(self.root / "baseline.json", self.baseline.to_dict())
        write_json(self.root / "evidence.json", build(self.root))

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "archctl", "--root", str(self.root), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_legacy_authoring_and_migration_command_are_rejected(self):
        source = self.root / "architecture/model.yaml"
        document = yaml.safe_load(source.read_text())
        document["schema_version"] = "archctl.authoring.v1"
        source.write_text(yaml.safe_dump(document))
        error = json.loads(self.cli("model", "validate", expected=3).stderr)
        self.assertEqual(error["schema_version"], "archctl.error.v2")
        self.assertIn("archctl.authoring.v2", error["message"])
        self.assertIn("no longer supported", error["message"])
        error = json.loads(self.cli("model", "migrate", "--input", "architecture/model.yaml",
                                    "--out", "migrated.yaml", expected=3).stderr)
        self.assertEqual(error["schema_version"], "archctl.error.v2")
        self.assertIn("invalid choice", error["message"])
        self.assertFalse((self.root / "migrated.yaml").exists())

    def test_model_validate_json_and_error_contracts(self):
        result = self.cli("model", "validate")
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], "archctl.model-validation.v2")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["revision"], self.baseline.revision)
        self.assertIsInstance(report["components"], int)
        self.assertEqual(result.stderr, "")

        (self.root / "architecture/model.yaml").write_text("schema_version: [\n")
        result = self.cli("model", "validate", expected=3)
        self.assertEqual(result.stdout, "")
        error = json.loads(result.stderr)
        self.assertEqual(error["schema_version"], "archctl.error.v2")
        self.assertEqual(error["status"], "error")
        self.assertTrue(error["message"])

    def test_invalid_invocations_use_the_json_input_error_contract(self):
        for arguments in ((), ("unknown-command",), ("gate", "--baseline-file", "snapshot.json")):
            result = self.cli(*arguments, expected=3)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(result.stderr)["schema_version"], "archctl.error.v2")

    def test_decisions_list_and_show_contracts(self):
        listed = json.loads(self.cli("decisions", "list", "--components", "orders").stdout)
        self.assertEqual(listed["schema_version"], "archctl.decisions.v2")
        self.assertEqual(listed["model_revision"], self.baseline.revision)
        self.assertEqual([decision["id"] for decision in listed["decisions"]], ["ADR-001"])

        shown = json.loads(self.cli("decisions", "show", "ADR-001").stdout)
        self.assertEqual(shown["schema_version"], "archctl.decision.v2")
        self.assertEqual(shown["id"], "ADR-001")
        self.assertTrue(shown["body"])

        error = json.loads(self.cli("decisions", "show", "ADR-MISSING", expected=3).stderr)
        self.assertEqual(error["schema_version"], "archctl.error.v2")
        self.assertIn("Unknown decision", error["message"])

    def test_impact_contract_and_exit_codes(self):
        result = self.cli("impact", "Change checkout", "--evidence", "evidence.json",
                          "--paths", "app/orders/api.py")
        impact = json.loads(result.stdout)
        self.assertEqual(impact["schema_version"], "archctl.impact.v2")
        self.assertEqual(impact["assessment"], "complete")
        self.assertEqual(result.stderr, "")

        partial = self.cli("impact", "No concrete scope", "--evidence", "evidence.json", expected=2)
        self.assertEqual(json.loads(partial.stdout)["assessment"], "partial")
        missing = self.cli("impact", "Missing evidence", "--evidence", "missing.json",
                           "--paths", "app/orders/api.py", expected=3)
        self.assertEqual(json.loads(missing.stderr)["schema_version"], "archctl.error.v2")

    def test_change_validate_reports_passed_and_unknown(self):
        path = self.root / ".archctl/change.yaml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(yaml.safe_dump(contract()))
        result = self.cli("change", "validate", "--input", ".archctl/change.yaml")
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], "archctl.change-validation.v2")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["unknowns"], [])
        self.assertTrue(report["change_revision"])

        value = contract()
        value["acceptance"][0]["checks"] = []
        value["open_questions"] = ["Confirm the rollout owner"]
        path.write_text(yaml.safe_dump(value))
        result = self.cli("change", "validate", "--input", ".archctl/change.yaml", expected=2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "unknown")
        self.assertIn("Acceptance criterion has no verification: AC-01", report["unknowns"])
        self.assertIn("Open question: Confirm the rollout owner", report["unknowns"])

    def test_observe_import_normalizes_runtime_evidence(self):
        bundle = build(self.root)
        bundle["coverage"].update(analysis="runtime", status="partial", gaps=["Sampled at runtime"])
        for item in bundle["evidence"]:
            item["kind"] = "runtime"
        for edge in bundle["edges"]:
            edge["origin"] = "runtime"
        write_json(self.root / "runtime.json", bundle)
        result = self.cli("observe", "import", "--input", "runtime.json", "--out", "normalized.json")
        written = json.loads(result.stdout)
        self.assertEqual(written["schema_version"], "archctl.output.v2")
        imported = json.loads((self.root / "normalized.json").read_text())
        self.assertEqual(imported["schema_version"], "archctl.evidence.v2")
        self.assertEqual(imported["coverage"]["analysis"], "runtime")
        self.assertTrue(imported["edges"])

    def test_guard_unknown_and_passed_contracts(self):
        unknown = self.cli("guard", "check", "--baseline", "baseline.json", "--evidence", "evidence.json",
                           "--paths", "app/orders/api.py", expected=2)
        report = json.loads(unknown.stdout)
        self.assertEqual(report["schema_version"], "archctl.guard.v2")
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["authority_changed"])
        self.assertTrue(all(check["status"] == "not_executed" for check in report["verification"]))

        passed = self.cli("guard", "check", "--baseline", "baseline.json", "--evidence", "evidence.json",
                          "--paths", "app/orders/api.py", "--run")
        report = json.loads(passed.stdout)
        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(check["status"] == "passed" for check in report["verification"]))

    def test_guard_failed_and_input_error_contracts(self):
        path = self.root / "app/orders/api.py"
        path.write_text("from app.ledger import store\n" + path.read_text())
        write_json(self.root / "evidence.json", build(self.root))
        result = self.cli("guard", "check", "--baseline", "baseline.json", "--evidence", "evidence.json",
                          "--paths", "app/orders/api.py", "--run", expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "failed")
        violation = next(finding for finding in report["findings"] if finding["id"] == "payment-isolation")
        self.assertEqual(violation["status"], "failed")
        self.assertTrue(all(check["status"] == "not_executed" for check in report["verification"]))

        error = self.cli("guard", "check", "--baseline", "missing.json", "--evidence", "evidence.json",
                         "--paths", "app/orders/api.py", expected=3)
        self.assertEqual(json.loads(error.stderr)["schema_version"], "archctl.error.v2")

    def test_output_acknowledgement_contract(self):
        result = self.cli("impact", "Change checkout", "--evidence", "evidence.json",
                          "--paths", "app/orders/api.py", "--out", ".archctl/impact.json")
        acknowledgement = json.loads(result.stdout)
        self.assertEqual(acknowledgement["schema_version"], "archctl.output.v2")
        self.assertEqual(acknowledgement["status"], "written")
        written = json.loads((self.root / ".archctl/impact.json").read_text())
        self.assertEqual(written["schema_version"], "archctl.impact.v2")

    def test_preparation_cli_routes_explicit_tools_and_returns_output_acknowledgement(self):
        output = self.root / ".archctl/prepared/new"
        acknowledgement = {"schema_version": "archctl.output.v2", "status": "written",
                           "output": str(output / "evidence.json"), "manifest": str(output / "manifest.json")}
        with patch("archctl.cli.prepare_evidence", return_value=acknowledgement) as prepare:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["--root", str(self.root), "briefcase", "prepare-evidence",
                             "--archctl", "/external/archctl", "--briefcase", "/external/briefcase",
                             "--source-root", "app", "--out-dir", ".archctl/prepared/new"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), acknowledgement)
        self.assertEqual(prepare.call_args.kwargs["archctl"], Path("/external/archctl"))
        self.assertEqual(prepare.call_args.kwargs["source_roots"], ("app",))
        self.assertEqual(prepare.call_args.kwargs["destination"], output)

    def test_preparation_requires_explicit_tools_and_source_roots(self):
        result = self.cli("briefcase", "prepare-evidence", expected=3)
        self.assertEqual(json.loads(result.stderr)["schema_version"], "archctl.error.v2")
        result = self.cli("briefcase", "prepare-evidence", "--archctl", "/missing/archctl",
                          "--briefcase", "/missing/briefcase", "--source-root", "app",
                          "--out-dir", "app/orders/generated", expected=3)
        self.assertFalse((self.root / "app/orders/generated").exists())
        self.assertIn(".archctl/", json.loads(result.stderr)["message"])

    def test_configured_tools_work_without_path_and_flags_override_them(self):
        environment = {"ARCHCTL_BIN": "/configured/archctl", "BRIEFCASE_BIN": "/configured/briefcase", "PATH": "/no-tools"}
        base = ["--root", str(self.root)]
        with patch.dict(os.environ, environment), redirect_stdout(io.StringIO()):
            with patch("archctl.cli.prepare_evidence", return_value={}) as prepare:
                args = [*base, "briefcase", "prepare-evidence", "--source-root", ".", "--out-dir", ".archctl/new"]
                self.assertEqual(main(args), 0)
                self.assertEqual(prepare.call_args.kwargs["archctl"], Path("/configured/archctl"))
                self.assertEqual(prepare.call_args.kwargs["briefcase"], Path("/configured/briefcase"))
                self.assertEqual(main([*args, "--archctl", "/flag/archctl", "--briefcase", "/flag/briefcase"]), 0)
                self.assertEqual(prepare.call_args.kwargs["archctl"], Path("/flag/archctl"))
                self.assertEqual(prepare.call_args.kwargs["briefcase"], Path("/flag/briefcase"))
            with patch("archctl.cli.export_evidence", return_value=build(self.root)) as export:
                args = [*base, "briefcase", "export-evidence"]
                self.assertEqual(main(args), 0)
                self.assertEqual(export.call_args.kwargs["binary"], "/configured/briefcase")
                self.assertEqual(main([*args, "--briefcase", "/flag/briefcase"]), 0)
                self.assertEqual(export.call_args.kwargs["binary"], "/flag/briefcase")
            with patch("archctl.cli.run_gate", return_value=(0, {})) as gate:
                args = [*base, "gate", "--baseline-ref", "a" * 40]
                self.assertEqual(main(args), 0)
                self.assertEqual(gate.call_args.args[1].briefcase, "/configured/briefcase")
                self.assertEqual(main([*args, "--briefcase", "/flag/briefcase"]), 0)
                self.assertEqual(gate.call_args.args[1].briefcase, "/flag/briefcase")
