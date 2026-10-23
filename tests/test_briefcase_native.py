"""Native Briefcase mapping tests and optional interoperability regressions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from archctl.atlas.impact import build_impact
from archctl.core.compiler import compile_model
from archctl.guard.evaluate import check
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from archctl.integrations.briefcase.native import (_import_targets, _internal_target,
                                                    _module_index, _unsupported_gaps,
                                                    export_evidence)
from tests.fixtures.storefront import initialize


class NativeMappingUnitTests(unittest.TestCase):
    def test_imports_and_module_index_are_classified_without_guessing(self):
        self.assertEqual(_import_targets("from archctl.core.io import digest"),
                         ["archctl.core.io"])
        self.assertEqual(_import_targets("import yaml"), ["yaml"])
        self.assertIsNone(_import_targets("from . import sibling"))
        modules = _module_index(["src/archctl/cli.py", "src/archctl/core/io.py"], ("src",))
        self.assertTrue(_internal_target("archctl.core.missing", modules))
        self.assertTrue(_internal_target("archctl", modules))
        self.assertFalse(_internal_target("yaml", modules))
        app_modules = _module_index(["app/orders/api.py", "app/__init__.py"], (".",))
        self.assertTrue(_internal_target("app.missing", app_modules))
        self.assertFalse(_internal_target("checks", app_modules))

    def test_unsupported_component_files_are_explicit_coverage_gaps(self):
        self.assertEqual(_unsupported_gaps(["app/orders/api.py", "app/payments/bridge.rs",
                                            "app/payments/schema.json"]),
                         ["Component file outside supported Python import scope: app/payments/bridge.rs",
                          "Component file outside supported Python import scope: app/payments/schema.json"])


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("briefcase"), "Briefcase is not installed")
class NativeBriefcaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        initialize(self.root, demo=True)
        (self.root / ".gitignore").write_text("__pycache__/\n.archctl/\n.briefcase/\n")
        _git(self.root, "init", "-q")
        _git(self.root, "add", ".")
        _git(self.root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "commit", "-qm", "baseline")

    def commit(self, message: str) -> None:
        _git(self.root, "add", ".")
        _git(self.root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "commit", "-qm", message)

    def export(self):
        snapshot = compile_model(self.root)
        bundle = export_evidence(self.root, snapshot, database=self.root / ".briefcase/briefcase.db")
        return snapshot, bundle

    def assess(self, snapshot, observations, paths):
        impact = build_impact(snapshot, observations, paths, "Native evidence", [])
        return check(self.root, snapshot, snapshot, observations, impact, execute=True,
                     environment="test", freshness=lambda: check_freshness(self.root, snapshot, observations))

    @staticmethod
    def finding(report, identifier="payment-isolation"):
        return next(f for f in report["findings"] if f["id"] == identifier)

    def test_native_mapper_produces_fresh_evidence_and_passes_guard(self):
        snapshot, bundle = self.export()
        if importlib.util.find_spec("jsonschema"):
            from jsonschema import Draft202012Validator
            schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/v2/evidence.schema.json").read_text())
            Draft202012Validator(schema).validate(bundle)
        observations = parse_evidence(bundle, snapshot)
        self.assertEqual(observations.coverage.status, "complete")
        self.assertEqual(observations.coverage.gaps, ())
        self.assertEqual(observations.source_revision.startswith("briefcase:view:"), True)
        self.assertEqual({(edge.source, edge.target) for edge in observations.edges},
                         {("orders", "payments"), ("payments", "ledger")})
        self.assertEqual(check_freshness(self.root, snapshot, observations), [])
        report = self.assess(snapshot, observations, ["app/orders/api.py"])
        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(result["status"] == "passed" for result in report["verification"]))

    def test_native_mapper_chunks_external_inspection(self):
        for index in range(33):
            (self.root / f"app/orders/generated_{index}.py").write_text("")
        self.commit("add more than one inspection chunk")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "complete")
        self.assertEqual(bundle["coverage"]["gaps"], [])

    def test_unresolved_internal_import_keeps_coverage_partial(self):
        path = self.root / "app/orders/api.py"
        path.write_text("from app.missing import thing\n" + path.read_text())
        self.commit("add unresolved import")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "partial")
        self.assertTrue(any("Unresolved internal import" in gap for gap in bundle["coverage"]["gaps"]))

    def test_unretained_tracked_file_outside_components_is_not_a_gap(self):
        outside = self.root / "evaluation/blob.bin"
        outside.parent.mkdir()
        outside.write_bytes(b"\x00\x01")
        self.commit("track an unretained non-component file")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "complete")
        self.assertEqual(bundle["coverage"]["gaps"], [])

    def test_unretained_component_file_keeps_coverage_partial(self):
        ignored = self.root / "app/orders/generated.py"
        ignored.write_text("")
        gitignore = self.root / ".gitignore"
        gitignore.write_text(gitignore.read_text() + "app/orders/generated.py\n")
        self.commit("ignore generated source")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "partial")
        self.assertTrue(any("app/orders/generated.py" in gap for gap in bundle["coverage"]["gaps"]))
        self.assertTrue(any("did not retain exact current bytes" in gap and "app/orders/generated.py" in gap
                            for gap in bundle["coverage"]["gaps"]))
        self.assertEqual(bundle["source"]["files"]["app/orders/generated.py"],
                         hashlib.sha256(ignored.read_bytes()).hexdigest())

    def test_unsupported_component_file_keeps_coverage_partial(self):
        bridge = self.root / "app/payments/bridge.rs"
        bridge.write_text("use crate::orders;\npub fn bridge() {}\n")
        self.commit("add unsupported component file")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "partial")
        self.assertTrue(any("app/payments/bridge.rs" in gap and "Python" in gap
                            for gap in bundle["coverage"]["gaps"]))
        self.assertEqual(bundle["source"]["files"]["app/payments/bridge.rs"],
                         hashlib.sha256(bridge.read_bytes()).hexdigest())
        observations = parse_evidence(bundle, snapshot)
        self.assertEqual({(edge.source, edge.target) for edge in observations.edges},
                         {("orders", "payments"), ("payments", "ledger")})
        report = self.assess(snapshot, observations, ["app/payments/bridge.rs"])
        self.assertEqual(self.finding(report)["status"], "unknown")
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(all(result["status"] == "not_executed" for result in report["verification"]))

    def test_unsupported_only_component_cannot_establish_absence(self):
        components = self.root / "architecture/model.yaml"
        model = yaml.safe_load(components.read_text())
        model["components"].append({"id": "bridge", "name": "Bridge", "domain": "finance",
                                    "kind": "library", "paths": ["app/bridge/**"]})
        components.write_text(yaml.safe_dump(model, sort_keys=False))
        policies = self.root / "architecture/model.yaml"
        model = yaml.safe_load(policies.read_text())
        model["policies"].append({"id": "bridge-isolation", "kind": "forbidden_dependency",
                                  "source": "orders", "target": "bridge", "kinds": ["imports"],
                                  "decision": "ADR-001", "severity": "error", "obligation": "required"})
        policies.write_text(yaml.safe_dump(model, sort_keys=False))
        bridge = self.root / "app/bridge/bridge.rs"
        bridge.parent.mkdir()
        bridge.write_text("pub fn bridge() {}\n")
        self.commit("declare and populate an unsupported-only component")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "partial")
        self.assertTrue(any("app/bridge/bridge.rs" in gap for gap in bundle["coverage"]["gaps"]))
        observations = parse_evidence(bundle, snapshot)
        self.assertEqual({(edge.source, edge.target) for edge in observations.edges},
                         {("orders", "payments"), ("payments", "ledger")})
        report = self.assess(snapshot, observations, ["app/bridge/bridge.rs"])
        self.assertEqual(self.finding(report, "bridge-isolation")["status"], "unknown")
        self.assertEqual(report["status"], "unknown")

    def test_known_python_violation_remains_failed_with_unsupported_files(self):
        api = self.root / "app/orders/api.py"
        api.write_text("from app.ledger import store\n" + api.read_text())
        unsupported = self.root / "app/orders/bridge.ts"
        unsupported.write_text("export const bridge = 1;\n")
        self.commit("add a real violation and an unsupported file")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "partial")
        observations = parse_evidence(bundle, snapshot)
        self.assertIn(("orders", "ledger"),
                      {(edge.source, edge.target) for edge in observations.edges})
        report = self.assess(snapshot, observations, ["app/orders/api.py"])
        self.assertEqual(self.finding(report)["status"], "failed")
        self.assertEqual(report["status"], "failed")

    def test_unsupported_file_outside_components_is_not_a_gap(self):
        outside = self.root / "evaluation/bridge.ts"
        outside.parent.mkdir()
        outside.write_text("export const bridge = 1;\n")
        self.commit("add an unsupported file outside components")
        snapshot, bundle = self.export()
        self.assertEqual(bundle["coverage"]["status"], "complete")
        self.assertEqual(bundle["coverage"]["gaps"], [])
