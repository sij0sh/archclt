from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from archctl.core.io import write_json
from archctl.templates import initialize
from tests.support import ProjectTest, build, split_model


class StatusContractTests(ProjectTest):
    def status(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "archctl", "--root", str(self.root), "status", *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def report(self, *args, expected=0):
        result = self.status("--format", "json", *args, expected=expected)
        return json.loads(result.stdout)

    def test_status_without_model_is_a_valid_unknown(self):
        shutil.rmtree(self.root / "architecture")
        result = self.status("--format", "json", expected=2)
        report = json.loads(result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(report["schema_version"], "archctl.status.v2")
        self.assertEqual(report["status"], "needs_model")
        self.assertEqual(report["model"]["state"], "missing")
        self.assertEqual(report["model"]["revision"], None)
        self.assertEqual(report["evidence"]["state"], "not_checked")
        self.assertEqual(report["gate"]["status"], "not_executed")
        self.assertEqual(report["approval"]["status"], "not_assessed")
        self.assertTrue(report["unknowns"])
        self.assertFalse((self.root / ".archctl").exists())

    def test_status_with_valid_model_and_missing_evidence_is_not_ready(self):
        report = self.report("--evidence", ".archctl/missing.json", expected=2)
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["model"]["state"], "valid")
        self.assertEqual(report["model"]["components"], 3)
        self.assertEqual(report["model"]["decisions"]["total"], 1)
        self.assertEqual(report["evidence"]["state"], "missing")
        self.assertEqual(report["evidence"]["freshness"]["status"], "not_executed")
        self.assertEqual(report["gate"]["status"], "not_executed")

    def test_status_with_current_evidence_is_ready_but_not_approval(self):
        write_json(self.root / ".archctl/evidence.json", build(self.root))
        result = self.status("--format", "json")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["evidence"]["state"], "current")
        self.assertEqual(report["evidence"]["coverage"]["status"], "complete")
        self.assertEqual(report["evidence"]["freshness"]["status"], "passed")
        self.assertEqual(report["gate"]["status"], "not_executed")
        self.assertEqual(report["approval"]["status"], "not_assessed")
        self.assertEqual(report["unknowns"], [])
        self.assertNotIn("drift", report)

    def test_drift_inspection_reports_current_undeclared_edges(self):
        bundle = build(self.root)
        bundle["evidence"].append({"id": "drift", "kind": "static", "location": "fixture:drift",
                                   "description": "Observed undeclared dependency"})
        bundle["edges"].append({"id": "drift", "source": "orders", "target": "ledger", "kind": "imports",
                                "origin": "static", "evidence_refs": ["drift"]})
        write_json(self.root / ".archctl/evidence.json", bundle)
        self.assertEqual(self.report()["status"], "ready")
        report = self.report("--drift", expected=2)
        self.assertEqual(report["evidence"]["state"], "current")
        self.assertEqual(report["drift"]["state"], "unresolved")
        self.assertTrue(any("undeclared relationship" in u for u in report["unknowns"]))
        self.assertEqual(report["gate"]["status"], "not_executed")
        self.assertEqual(report["approval"]["status"], "not_assessed")

    def test_drift_is_bounded_and_never_runs_without_valid_inputs(self):
        report = self.report("--drift", expected=2)
        self.assertEqual(report["drift"]["state"], "not_checked")
        bundle = build(self.root)
        bundle["edges"] += [{**bundle["edges"][0], "id": f"extra-{i}", "target": "ledger"} for i in range(25)]
        write_json(self.root / ".archctl/evidence.json", bundle)
        report = self.report("--drift", expected=2)
        self.assertEqual(len(report["drift"]["findings"]), 20)
        self.assertGreater(report["drift"]["findings_total"], 20)
        self.assertGreaterEqual(report["drift"]["unresolved"], 25)
        self.assertTrue(report["drift"]["findings_truncated"])
        write_json(self.root / ".archctl/evidence.json", {"invalid": True})
        self.assertEqual(self.report("--drift", expected=2)["drift"]["state"], "not_checked")

    def test_clean_drift_inspection_keeps_readiness_and_text_output(self):
        write_json(self.root / ".archctl/evidence.json", build(self.root))
        self.assertEqual(self.report("--drift")["drift"]["state"], "clean")
        self.assertIn("Drift: clean (0 unresolved)", self.status("--drift", "--format", "text").stdout)

    def test_status_with_stale_evidence_stays_unknown(self):
        write_json(self.root / "evidence.json", build(self.root))
        path = self.root / "app/orders/api.py"
        path.write_text(path.read_text() + "\n# candidate change\n")
        report = self.report("--evidence", "evidence.json", expected=2)
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["evidence"]["state"], "stale")
        self.assertEqual(report["evidence"]["freshness"]["status"], "unknown")
        self.assertIn("stale:app/orders/api.py",
                      {finding["id"] for finding in report["evidence"]["freshness"]["findings"]})
        self.assertTrue(any("Evidence pin is stale" in item for item in report["unknowns"]))

    def test_status_with_partial_coverage_does_not_become_ready(self):
        bundle = build(self.root)
        bundle["coverage"]["status"] = "partial"
        bundle["coverage"]["gaps"] = [f"unresolved gap {index}" for index in range(25)]
        write_json(self.root / "evidence.json", bundle)
        report = self.report("--evidence", "evidence.json", expected=2)
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["evidence"]["state"], "partial")
        self.assertEqual(len(report["evidence"]["coverage"]["gaps"]), 20)
        self.assertEqual(report["evidence"]["coverage"]["gaps_total"], 25)
        self.assertTrue(report["evidence"]["coverage"]["gaps_truncated"])
        self.assertEqual(report["unknowns_total"], 26)
        self.assertTrue(report["unknowns_truncated"])
        self.assertEqual(len(report["unknowns"]), 20)
        self.assertIn("unresolved gap 0", report["unknowns"])


    def test_status_with_neutral_init_reports_a_valid_model(self):
        shutil.rmtree(self.root / "architecture")
        initialize(self.root)
        report = self.report(expected=2)
        self.assertEqual(report["model"]["state"], "valid")
        self.assertEqual(report["model"]["components"], 0)
        self.assertEqual(report["evidence"]["state"], "missing")
        self.assertEqual(report["status"], "needs_attention")
        self.assertNotEqual(report["status"], "needs_model")

    def test_status_with_split_model_and_current_evidence_is_ready(self):
        split_model(self.root)
        write_json(self.root / ".archctl/evidence.json", build(self.root))
        report = self.report()
        self.assertEqual(report["model"]["state"], "valid")
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["model"]["sources"], 8)

    def test_status_with_malformed_single_model_reports_invalid(self):
        path = self.root / "architecture/model.yaml"
        path.write_text("schema_version: [\n")
        report = self.report(expected=2)
        self.assertEqual(report["model"]["state"], "invalid")
        self.assertEqual(report["status"], "needs_attention")
        self.assertNotEqual(report["status"], "needs_model")

    def test_status_with_invalid_model_reports_an_error_state(self):
        path = self.root / "architecture/model.yaml"
        path.write_text("schema_version: [\n")
        report = self.report(expected=2)
        self.assertEqual(report["model"]["state"], "invalid")
        self.assertTrue(report["model"]["message"])
        self.assertEqual(report["evidence"]["state"], "not_checked")
        self.assertEqual(report["status"], "needs_attention")

    def test_status_with_invalid_evidence_reports_an_error_state(self):
        write_json(self.root / "evidence.json", {"schema_version": "archctl.evidence.v2"})
        report = self.report("--evidence", "evidence.json", expected=2)
        self.assertEqual(report["model"]["state"], "valid")
        self.assertEqual(report["evidence"]["state"], "invalid")
        self.assertTrue(report["evidence"]["message"])
        self.assertEqual(report["status"], "needs_attention")

    def test_status_text_output_and_generated_output_protection(self):
        write_json(self.root / "evidence.json", build(self.root))
        result = self.status("--evidence", "evidence.json", "--format", "text")
        self.assertIn("Status: ready", result.stdout)
        self.assertIn("Gate: not_executed", result.stdout)
        self.assertIn("Approval: not_assessed", result.stdout)

        result = self.status("--evidence", "evidence.json", "--format", "json", "--out", ".archctl/status.json")
        acknowledgement = json.loads(result.stdout)
        self.assertEqual(acknowledgement["schema_version"], "archctl.output.v2")
        self.assertEqual(json.loads((self.root / ".archctl/status.json").read_text())["schema_version"],
                         "archctl.status.v2")

        model = self.root / "architecture/model.yaml"
        original_model = model.read_text()
        self.status("--evidence", "evidence.json", "--out", "architecture/model.yaml", expected=3)
        self.assertEqual(model.read_text(), original_model)
        evidence = self.root / "evidence.json"
        original_evidence = evidence.read_text()
        self.status("--evidence", "evidence.json", "--out", ".archctl/evidence.json", expected=3)
        self.assertEqual(evidence.read_text(), original_evidence)

    def test_support_profile_is_reported_only_for_the_native_mapper(self):
        bundle = build(self.root)
        write_json(self.root / ".archctl/evidence.json", bundle)
        self.assertNotIn("support", self.report()["evidence"])
        bundle["producer"]["name"] = "briefcase-native-exporter"
        write_json(self.root / ".archctl/evidence.json", bundle)
        support = self.report()["evidence"]["support"]
        self.assertEqual((support["languages"], support["predicates"]), (["python"], ["imports"]))
        self.assertIn("Only Python import edges", self.status().stdout)
