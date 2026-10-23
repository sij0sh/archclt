from __future__ import annotations

import copy
from pathlib import Path
import sys

import yaml

from archctl.atlas.impact import build_impact
from archctl.atlas.reconcile import reconcile
from archctl.core.io import InputError, file_digest
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from archctl.integrations.process import run_checks
from archctl.observatory.workflows import run_workflow
from tests.support import ProjectTest, build


class ArchitectureWorkflowTests(ProjectTest):
    def test_valid_change_requires_actual_execution(self):
        report = self.assess()
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(all(r["status"] == "not_executed" for r in report["verification"]))
        executed = self.assess(execute=True)
        self.assertEqual(executed["status"], "passed")
        self.assertEqual({r["id"] for r in executed["verification"]}, {"payments-contract", "checkout-integration"})
        self.assertTrue(all(r["returncode"] == 0 for r in executed["verification"]))

    def test_forbidden_dependency_detected_even_when_functional_tests_pass(self):
        path = self.root / "app/orders/api.py"
        path.write_text("from app.ledger import store\n" + path.read_text())
        report = self.assess(execute=True)
        self.assertEqual(report["status"], "failed")
        violation = next(f for f in report["findings"] if f["id"] == "payment-isolation")
        self.assertEqual(violation["decision"], "ADR-001")
        self.assertTrue(violation["evidence_refs"])
        self.assertTrue(all(r["status"] == "not_executed" for r in report["verification"]))
        snapshot, observed = self.candidate(), self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observed)
        results = run_checks(self.root, snapshot, self.baseline, observed,
                             [v.id for v in snapshot.model.verification], execute=True, environment="test", freshness=fresh)
        self.assertTrue(all(r["status"] == "passed" for r in results))

    def test_stale_deleted_and_new_files_block_a_pass(self):
        before = self.evidence()
        path = self.root / "app/orders/api.py"
        original = path.read_text()
        for change in ("edit", "delete", "add"):
            with self.subTest(change=change):
                path.write_text(original)
                added = self.root / "app/orders/new.py"
                added.unlink(missing_ok=True)
                if change == "edit":
                    path.write_text(original + "\n# candidate change\n")
                elif change == "delete":
                    path.unlink()
                else:
                    added.write_text("# newly introduced source\n")
                report = self.assess(bundle=before, execute=True)
                self.assertEqual(report["status"], "unknown")
                self.assertTrue(all(r["status"] != "passed" for r in report["verification"]))

    def test_partial_and_runtime_coverage_cannot_certify_absence(self):
        bundle = build(self.root)
        bundle["coverage"]["status"] = "partial"
        bundle["coverage"]["gaps"] = ["Dynamic calls unresolved"]
        observed = parse_evidence(bundle, self.candidate())
        report = self.assess(bundle=observed, execute=True)
        self.assertEqual(report["status"], "unknown")
        bundle = build(self.root)
        bundle["coverage"].update(analysis="runtime", status="partial")
        for item in bundle["evidence"]:
            item["kind"] = "runtime"
        for edge in bundle["edges"]:
            edge["origin"] = "runtime"
        observed = parse_evidence(bundle, self.candidate())
        report = self.assess(bundle=observed)
        self.assertEqual(report["status"], "unknown")

    def test_evidence_references_and_scopes_are_strict(self):
        for mutation in ("dangling", "declaration", "unknown", "runtime-complete", "duplicate", "unsupported-version"):
            with self.subTest(mutation=mutation):
                bundle = build(self.root)
                if mutation == "dangling":
                    bundle["edges"][0]["evidence_refs"] = ["not-present"]
                elif mutation == "declaration":
                    bundle["evidence"][0]["kind"] = "derived"
                elif mutation == "unknown":
                    bundle["edges"][0]["target"] = "unknown"
                elif mutation == "runtime-complete":
                    bundle["coverage"]["analysis"] = "runtime"
                elif mutation == "duplicate":
                    bundle["edges"].append(copy.deepcopy(bundle["edges"][0]))
                else:
                    bundle["schema_version"] = "briefcase.native.unknown"
                with self.assertRaises(InputError):
                    parse_evidence(bundle, self.candidate())

    def test_changed_authority_blocks_execution(self):
        path = self.root / "architecture/model.yaml"
        path.write_text(path.read_text().replace("severity: error", "severity: warning"))
        report = self.assess(execute=True)
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(report["authority_changed"])
        self.assertTrue(all(r["status"] == "not_executed" for r in report["verification"]))

    def test_unreviewed_command_is_never_executed(self):
        marker = self.root / "should-not-exist"
        path = self.root / "architecture/model.yaml"
        data = yaml.safe_load(path.read_text())
        data["verification"][0]["command"] = [sys.executable, "-c", "from pathlib import Path; Path('should-not-exist').touch()"]
        path.write_text(yaml.safe_dump(data))
        report = self.assess(execute=True)
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(marker.exists())

    def test_impact_preserves_decisions_and_consumer_evidence(self):
        snapshot, observed = self.candidate(), self.evidence()
        impact = build_impact(snapshot, observed, ["app/payments/service.py"], "Change payment result", [])
        affected = {v["id"]: v for v in impact["affected_components"]}
        self.assertEqual(set(affected), {"orders", "payments", "ledger"})
        self.assertIn("observed_consumer", affected["orders"]["basis"])
        self.assertTrue(affected["orders"]["evidence_refs"])
        self.assertEqual(impact["assessment"], "complete")
        self.assertEqual(impact["governing_decisions"][0]["id"], "ADR-001")
        self.assertEqual({v["id"] for v in impact["verification"]}, {"payments-contract", "checkout-integration"})
        self.assertTrue(all(v["basis"] == "declared_requirement" for v in impact["verification"]))

    def test_unmapped_empty_and_ambiguous_scope_is_incomplete(self):
        snapshot, observed = self.candidate(), self.evidence()
        for paths in ([], ["unknown/file.py"]):
            self.assertEqual(build_impact(snapshot, observed, paths, "Plan", [])["assessment"], "partial")
        path = self.root / "architecture/model.yaml"
        data = yaml.safe_load(path.read_text())
        data["components"][0]["paths"].append("app/payments/**")
        path.write_text(yaml.safe_dump(data))
        impact = build_impact(self.candidate(), observed, ["app/payments/service.py"], "Plan", [])
        self.assertTrue(any("multiple components" in gap for gap in impact["unknowns"]))
        findings = check_freshness(self.root, self.candidate(), observed)
        self.assertTrue(any(f.id.startswith("ambiguous:") for f in findings))

    def test_reconciliation_never_modifies_intent(self):
        before = self.candidate()
        path = self.root / "app/orders/api.py"
        path.write_text("from app.ledger import store\n" + path.read_text())
        result = reconcile(before, self.evidence(), [])
        self.assertFalse(result["authority_updated"])
        self.assertTrue(any(f["status"] == "failed" for f in result["findings"]))
        self.assertEqual(before, self.candidate())

    def test_intra_component_import_is_ignored_not_undeclared(self):
        bundle = build(self.root)
        bundle["evidence"].append({"id": "intra-evidence", "kind": "static",
                                   "location": "app/orders/api.py:1",
                                   "description": "Import inside one component"})
        bundle["edges"].append({"id": "intra-1", "source": "orders", "target": "orders",
                                "kind": "imports", "origin": "static", "evidence_refs": ["intra-evidence"]})
        observed = parse_evidence(bundle, self.candidate())
        result = reconcile(self.candidate(), observed, [])
        self.assertEqual([f for f in result["findings"] if f["status"] != "passed"], [])
        ignored = result["ignored"]
        self.assertEqual([(item["source"], item["target"]) for item in ignored], [("orders", "orders")])
        self.assertIn("Intra-component", ignored[0]["reason"])

    def test_declared_relationship_must_connect_two_components(self):
        path = self.root / "architecture/model.yaml"
        data = yaml.safe_load(path.read_text())
        data["relationships"].append({"id": "orders-orders", "source": "orders", "target": "orders",
                                      "kind": "imports", "decision": "ADR-001", "required": True})
        path.write_text(yaml.safe_dump(data))
        with self.assertRaisesRegex(InputError, "two different components"):
            self.candidate()

    def test_workflow_runs_without_fabricating_traces(self):
        snapshot, observed = self.candidate(), self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observed)
        result = run_workflow(self.root, snapshot, self.baseline, observed, "checkout", environment="test", freshness=fresh)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["runtime_observations"], [])
        with self.assertRaisesRegex(InputError, "Unknown workflow"):
            run_workflow(self.root, snapshot, self.baseline, observed, "missing", environment="test", freshness=fresh)

    def test_missing_required_observed_relationship_fails(self):
        bundle = build(self.root)
        bundle["edges"] = []
        observed = parse_evidence(bundle, self.candidate())
        report = self.assess(bundle=observed)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(f["id"].startswith("required:") and f["status"] == "failed" for f in report["findings"]))


class RunnerTests(ProjectTest):
    def configured(self, command, timeout=20):
        path = self.root / "architecture/model.yaml"
        data = yaml.safe_load(path.read_text())
        data["verification"] = [data["verification"][0]]
        data["verification"][0]["command"] = command
        data["verification"][0]["timeout_seconds"] = timeout
        # Keep the other check as-is so model references remain valid.
        original = yaml.safe_load(path.read_text())
        data["verification"].append(original["verification"][1])
        path.write_text(yaml.safe_dump(data))
        snapshot = self.candidate()
        observed = self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observed)
        return run_checks(self.root, snapshot, snapshot, observed, [data["verification"][0]["id"]],
                          execute=True, environment="runner-test", freshness=fresh)[0]

    def test_command_failure_is_not_a_pass(self):
        result = self.configured([sys.executable, "-c", "raise SystemExit(4)"])
        self.assertEqual((result["status"], result["returncode"]), ("failed", 4))

    def test_missing_executable_and_timeout_are_unknown(self):
        result = self.configured(["archctl-no-such-executable-123"])
        self.assertEqual(result["status"], "unknown")
        result = self.configured([sys.executable, "-c", "import time; time.sleep(3)"], timeout=1)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("timed out", result["message"])

    def test_shell_metacharacters_remain_literal_arguments(self):
        literal = "$(touch should-not-exist); echo bad"
        result = self.configured([sys.executable, "-c", "import sys; print(sys.argv[1])", literal])
        self.assertEqual(result["status"], "passed")
        self.assertIn(literal, result["stdout"])
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_source_changes_during_execution_invalidate_result(self):
        result = self.configured([sys.executable, "-c",
            "from pathlib import Path; p=Path('app/orders/api.py'); p.write_text(p.read_text()+'\\n# mutation\\n')"])
        self.assertEqual(result["status"], "unknown")
        self.assertIn("changed during", result["message"])

    def test_new_adr_during_execution_invalidates_result(self):
        script = "from pathlib import Path; p=Path('architecture/decisions/ADR-001.md'); Path('architecture/decisions/ADR-002.md').write_text(p.read_text().replace('ADR-001','ADR-002'))"
        result = self.configured([sys.executable, "-c", script])
        self.assertEqual(result["status"], "unknown")

    def test_output_is_bounded(self):
        result = self.configured([sys.executable, "-c", "print('x'*100000)"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["stdout"]), 65536)
        self.assertTrue(result["output_truncated"])
