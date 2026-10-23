"""End-to-end local gates in disposable Git repositories, with controlled defects."""
from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

from archctl.core.io import write_json
from tests.support import ProjectTest, build

ROOT = Path(__file__).resolve().parents[1]


def contract():
    return {"schema_version": "archctl.change.v2", "id": "checkout-change", "objective": "Preserve checkout behavior",
            "scope": {"components": ["orders", "payments", "ledger"], "excluded_components": [], "paths": ["checks/**"]},
            "acceptance": [{"id": "AC-01", "requirement": "Checkout remains idempotent", "checks": ["checkout-integration"]}],
            "constraints": {"decisions": ["ADR-001"], "policies": ["payment-isolation"]}, "open_questions": []}


class CheckArchitectureTests(ProjectTest):
    def setUp(self):
        super().setUp()
        self.evidence_file = self.root / ".archctl/evidence.json"
        self.change_file = self.root / ".archctl/change.yaml"
        self.change_file.parent.mkdir()
        self.change_file.write_text(yaml.safe_dump(contract()))
        (self.root / ".gitignore").write_text(".archctl/\n__pycache__/\n*.pyc\n")
        self.git("init", "-q")
        self.commit("reviewed baseline")
        self.refresh()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit_paths(self, message, *paths):
        self.git("add", *paths)
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", message)
        self.sha = self.git("rev-parse", "HEAD")

    def commit(self, message):
        self.commit_paths(message, ".")

    def enable_v2(self, *, obligations=None, policies=(), checks=()):
        """Review selective intent without committing unrelated working-tree edits."""
        path = self.root / "architecture/model.yaml"
        value = yaml.safe_load(path.read_text())
        value.update(schema_version="archctl.authoring.v2", enforcement="selective")
        value["policies"] += [dict(policy) for policy in policies]
        for policy in value["policies"]:
            policy["obligation"] = (obligations or {}).get(policy["id"], "required")
        value["verification"] += [dict(check) for check in checks]
        path.write_text(yaml.safe_dump(value, sort_keys=False))
        self.commit_paths("review selective v2 intent", "architecture/model.yaml")
        self.refresh()

    def verification(self, ident):
        return next(item for item in self.summary["verification"] if item["id"] == ident)

    def edit_policies(self, edit):
        path = self.root / "architecture/model.yaml"
        value = yaml.safe_load(path.read_text())
        edit(value)
        path.write_text(yaml.safe_dump(value, sort_keys=False))

    def refresh(self):
        write_json(self.evidence_file, build(self.root))

    def edit_contract(self, edit):
        value = yaml.safe_load(self.change_file.read_text())
        edit(value)
        self.change_file.write_text(yaml.safe_dump(value))

    def gate(self, *args, baseline=None, change=True, cwd=None):
        command = [sys.executable, "-m", "archctl", "--root", str(self.root), "gate", "--baseline-ref", baseline or self.sha,
                   "--evidence", str(self.evidence_file), "--no-briefcase"]
        if change:
            command += ["--change", str(self.change_file)]
        result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=120, cwd=cwd)
        output = json.loads(result.stdout or result.stderr)
        self.report = Path(output["report"]) if "report" in output else None
        self.summary = json.loads((self.report / "gate-summary.json").read_text()) if self.report else output
        return result

    def test_fresh_valid_change_passes_and_repeats_reproducibly(self):
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text().replace('"order:" + order_id', 'f"order:{order_id}"'))
        self.refresh()
        result = self.gate("--run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary, first = self.summary, self.report
        self.assertEqual(summary["acceptance"][0]["status"], "passed")
        self.assertEqual(summary["approval"], "not_assessed")
        self.assertTrue(all(v["status"] == "passed" for v in summary["verification"]))
        self.assertEqual(self.gate("--run").returncode, 0)
        self.assertNotEqual(first, self.report)
        for key in ("status", "model_revision", "source_digest", "change_revision"):
            self.assertEqual(summary[key], self.summary[key])
        for filename in ("baseline.lock.json", "candidate.lock.json", "evidence.json", "impact.json", "guard.json", "reconcile.json", "change.json", "gate-summary.md"):
            self.assertTrue((self.report / filename).is_file(), filename)
        self.assertEqual(len(self.git("worktree", "list", "--porcelain").split("worktree ")) - 1, 1)

    def test_not_executing_is_unknown(self):
        self.assertEqual(self.gate().returncode, 2)
        self.assertTrue(all(v["status"] == "not_executed" for v in self.summary["verification"]))
        self.assertEqual(self.summary["acceptance"][0]["status"], "unknown")

    def test_forbidden_import_fails_even_if_functional_tests_pass(self):
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        tests = subprocess.run([sys.executable, "-m", "unittest", "checks.test_checkout", "checks.test_contract"], cwd=self.root, capture_output=True)
        self.assertEqual(tests.returncode, 0)
        self.assertEqual(self.gate("--run").returncode, 1)
        self.assertTrue(any(f["id"] == "payment-isolation" and f["status"] == "failed" for f in self.summary["findings"]))

    def test_failed_behavior_is_failed(self):
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text().replace('"status": receipt["status"]', '"status": "wrong"'))
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 1)
        self.assertEqual(self.summary["acceptance"][0]["status"], "failed")

    def test_stale_evidence_is_unknown(self):
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text() + "\n# stale\n")
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertEqual(self.summary["stages"]["evidence"], "unknown")

    def test_missing_evidence_does_not_reuse_previous_run(self):
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 0)
        old = self.report
        self.evidence_file.unlink()
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertNotEqual(old, self.report)
        self.assertFalse((self.report / "guard.json").exists())

    def test_partial_evidence_is_unknown(self):
        bundle = build(self.root)
        bundle["coverage"].update(status="partial", gaps=["Unresolved imports"])
        write_json(self.evidence_file, bundle)
        self.assertEqual(self.gate("--run").returncode, 2)

    def test_unapproved_policy_and_command_changes_are_unknown(self):
        source = self.root / "architecture/model.yaml"
        value = yaml.safe_load(source.read_text())
        value["policies"][0]["severity"] = "warning"
        source.write_text(yaml.safe_dump(value))
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertTrue(self.summary["authority_changed"])
        self.assertTrue(all(v["status"] == "not_executed" for v in self.summary["verification"]))

    def test_out_of_scope_file_and_affected_consumer_are_unknown(self):
        self.edit_contract(lambda c: c["scope"].update(components=["orders"], excluded_components=["ledger"]))
        source = self.root / "app/payments/service.py"
        source.write_text(source.read_text() + "\n# change shared provider\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertTrue(any("outside reviewed" in f["message"] for f in self.summary["findings"]))

    def test_unowned_new_file_is_unknown(self):
        (self.root / "unrelated.py").write_text("value = 1\n")
        self.assertEqual(self.gate("--run").returncode, 2)

    def test_reviewed_test_file_scope_is_supported(self):
        (self.root / "checks/test_checkout.py").write_text((self.root / "checks/test_checkout.py").read_text() + "\n# regression\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 0)

    def test_unmapped_criterion_and_open_question_are_unknown(self):
        self.edit_contract(lambda c: c["acceptance"][0].update(checks=[]))
        self.assertEqual(self.gate("--run").returncode, 2)
        self.edit_contract(lambda c: c.update(open_questions=["Which caller owns cancellation?"]))
        self.assertEqual(self.gate("--run").returncode, 2)

    def test_missing_check_reference_is_input_error(self):
        self.edit_contract(lambda c: c["acceptance"][0].update(checks=["missing"]))
        self.assertEqual(self.gate("--run").returncode, 3)
        self.assertEqual(self.summary["status"], "error")

    def test_undeclared_in_scope_relationship_blocks_clean_guard(self):
        # Payments -> Orders is undeclared but is not the forbidden Orders -> Ledger edge.
        source = self.root / "app/payments/service.py"
        source.write_text("import app.orders.api\n" + source.read_text())
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertEqual(self.summary["stages"]["drift"], "unknown")

    def test_explicit_policy_constraint_is_checked_for_test_only_change(self):
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.commit("baseline with a known architectural defect")
        test = self.root / "checks/test_checkout.py"
        test.write_text(test.read_text() + "\n# test-only task\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 1)
        self.assertTrue(any(f.get("id") == "payment-isolation" for f in self.summary["findings"]))

    def test_missing_optional_relationship_is_informational(self):
        path = self.root / "architecture/model.yaml"
        value = yaml.safe_load(path.read_text())
        value["relationships"].append({"id": "optional", "source": "ledger", "target": "orders", "kind": "imports", "decision": "ADR-001", "required": False})
        path.write_text(yaml.safe_dump(value))
        self.commit("review optional relationship")
        self.refresh()
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 0)
        self.assertTrue(any(f["id"] == "missing:optional" for f in self.summary["drift"]["informational"]))

    def test_baseline_evaluator_ignores_candidate_guard_mapper_compiler_and_orchestrator(self):
        shutil.copytree(ROOT / "src/archctl", self.root / "src/archctl", ignore=shutil.ignore_patterns("__pycache__"))
        self.commit("review evaluator")
        for filename in ("guard/evaluate.py", "core/compiler.py", "integrations/briefcase/adapter.py", "cli_gate.py", "cli_report.py"):
            (self.root / "src/archctl" / filename).write_text('raise RuntimeError("Candidate tool must not be imported")\n')
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 1)
        self.assertEqual(self.summary["evaluator"]["source"], "baseline")

    def test_sha_required_and_snapshot_mode_removed(self):
        result = self.gate(baseline="HEAD")
        self.assertEqual(result.returncode, 3)
        self.assertIn("full reviewed", self.summary["message"])
        result = subprocess.run([sys.executable, "-m", "archctl", "gate", "--baseline-file", "snapshot.json"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_output_cannot_overwrite_source(self):
        self.assertEqual(self.gate("--out-dir", "app/orders").returncode, 3)

    def test_running_inside_application_with_application_tempdir_does_not_pollute_scope(self):
        from unittest.mock import patch
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text() + "\n# scoped edit\n")
        self.refresh()
        source_path = str(ROOT / "src")
        with patch.dict(os.environ, {"TMPDIR": str(self.root), "PYTHONPATH": source_path}):
            result = self.gate("--run", cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.summary["changed_paths"], ["app/orders/api.py"])
        self.assertEqual(list((self.root / ".archctl/worktrees").iterdir()), [])

    def test_all_scope_audit_runs_without_change_contract(self):
        self.assertEqual(self.gate("--scope", "all", "--run", change=False).returncode, 0)
        self.assertEqual(self.summary["scope"], "all")
        self.assertNotIn("acceptance", self.summary["stages"])
        self.assertEqual(self.summary["acceptance"], [])
        report = (self.report / "gate-summary.md").read_text()
        self.assertIn("Task acceptance: not assessed (no Change Contract supplied).", report)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install .[dev] for JSON Schema conformance checks")
    def test_published_gate_schema_validates_actual_run(self):
        from jsonschema import Draft202012Validator
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 0)
        schema = json.loads((ROOT / "contracts/v2/gate.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.summary)

    def reviewed_mutating_check(self, code):
        path = self.root / "architecture/model.yaml"
        value = yaml.safe_load(path.read_text())
        value["verification"].append({"id": "mutating-check", "kind": "integration", "command": [sys.executable, "-c", code],
                                      "cwd": ".", "timeout_seconds": 10, "components": ["orders"]})
        path.write_text(yaml.safe_dump(value))
        self.commit("review mutating check for controlled trial")
        self.edit_contract(lambda c: c["acceptance"][0]["checks"].append("mutating-check"))

    def test_contract_changed_during_execution_is_unknown(self):
        self.reviewed_mutating_check("from pathlib import Path; p=Path('.archctl/change.yaml'); p.write_text(p.read_text()+'\\n')")
        self.refresh()
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 2)
        self.assertEqual(self.summary["stages"]["stability"], "unknown")
        self.assertTrue(any("Change contract changed" in f["message"] for f in self.summary["findings"]))

    def test_reviewed_noncomponent_file_changed_during_execution_is_unknown(self):
        (self.root / "note.md").write_text("before")
        self.reviewed_mutating_check("from pathlib import Path; Path('note.md').write_text('during')")
        self.edit_contract(lambda c: c["scope"]["paths"].append("note.md"))
        (self.root / "note.md").write_text("candidate")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertEqual(self.summary["stages"]["stability"], "unknown")

    def test_unreviewed_command_does_not_execute(self):
        path = self.root / "architecture/model.yaml"
        value = yaml.safe_load(path.read_text())
        value["verification"][0]["command"] = [sys.executable, "-c", "from pathlib import Path; Path('UNREVIEWED').write_text('bad')"]
        path.write_text(yaml.safe_dump(value))
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 2)
        self.assertFalse((self.root / "UNREVIEWED").exists())

    def test_gate_summary_is_the_composite_handoff(self):
        self.assertEqual(self.gate("--scope", "all", "--run").returncode, 0)
        text = (self.report / "gate-summary.md").read_text()
        self.assertIn(f"# Architecture change review: {self.summary['status']}", text)
        self.assertIn(self.summary["baseline_sha"], text)
        self.assertIn("AC-01", text)
        self.assertIn("Operator acceptance: not assessed", text)

    def test_gate_preserves_the_application_command_path(self):
        directory = self.root / ".archctl/bin"
        directory.mkdir()
        marker = self.root / ".archctl/application-runner"
        runner = directory / "python3"
        runner.write_text(f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\n"
                          f"Path({str(marker)!r}).write_text('application')\n"
                          f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n")
        runner.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(directory) + os.pathsep + os.environ.get("PATH", "")}):
            result = self.gate("--scope", "all", "--run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(marker.read_text(), "application")

    def test_selective_advisory_forbidden_edge_is_visible_but_not_blocking(self):
        self.enable_v2(obligations={"payment-isolation": "advisory"})
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        result = self.gate("--run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finding = next(f for f in self.summary["findings"] if f["id"] == "payment-isolation")
        self.assertEqual((finding["status"], finding["obligation"]), ("failed", "advisory"))
        # Display severity never promotes an advisory obligation.
        self.assertEqual(finding["severity"], "error")
        self.assertEqual(self.summary["schema_version"], "archctl.gate.v2")
        self.assertEqual(self.summary["enforcement"], "selective")
        self.assertIn("Required obligations passed", self.summary["guarantee"])

    def test_selective_required_warning_policy_still_blocks(self):
        self.enable_v2()
        self.edit_policies(lambda data: data["policies"][0].update(severity="warning"))
        self.commit("review warning display severity")
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 1)
        finding = next(f for f in self.summary["findings"] if f["id"] == "payment-isolation")
        self.assertEqual((finding["status"], finding["obligation"]), ("failed", "required"))

    def test_selective_undeclared_observation_is_advisory_not_blocking(self):
        source = self.root / "app/payments/service.py"
        source.write_text(source.read_text() + "\n\ndef _peek():\n    from app.orders import api\n    return api\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertEqual(self.summary["stages"]["drift"], "unknown")
        self.enable_v2()
        self.assertEqual(self.gate("--run").returncode, 0)
        self.assertEqual(self.summary["schema_version"], "archctl.gate.v2")

    def test_selective_required_reason_dominates_for_a_shared_check(self):
        self.enable_v2(
            obligations={"ledger-audit-policy": "advisory"},
            policies=[{"id": "ledger-audit-policy", "kind": "required_verification", "components": ["ledger"],
                       "checks": ["ledger-audit"], "decision": "ADR-001", "severity": "error"}],
            checks=[{"id": "ledger-audit", "kind": "architecture", "cwd": ".", "timeout_seconds": 20,
                     "command": ["python3", "-m", "unittest", "checks.test_audit"], "components": ["ledger"]}])
        (self.root / "checks/test_audit.py").write_text(
            "import unittest\n\nclass Audit(unittest.TestCase):\n    def test_audit(self):\n        self.fail('unfinished audit')\n")
        source = self.root / "app/ledger/store.py"
        source.write_text(source.read_text() + "\n# ledger change\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 0)
        audit = self.verification("ledger-audit")
        self.assertEqual((audit["status"], audit["obligation"]), ("failed", "advisory"))
        self.edit_contract(lambda change: change["acceptance"][0].update(checks=["checkout-integration", "ledger-audit"]))
        self.assertEqual(self.gate("--run").returncode, 1)
        audit = self.verification("ledger-audit")
        self.assertEqual((audit["status"], audit["obligation"]), ("failed", "required"))
        self.assertIn("AC-01", {reason["id"] for reason in audit["required_by"]})

    def test_selective_stale_evidence_and_authority_changes_stay_required(self):
        self.enable_v2()
        test = self.root / "checks/test_checkout.py"
        test.write_text(test.read_text() + "\n# regression\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 0)
        source = self.root / "app/orders/api.py"
        source.write_text(source.read_text() + "\n# stale\n")
        self.assertEqual(self.gate("--run").returncode, 2)
        self.refresh()
        self.edit_policies(lambda data: data["policies"][0].update(severity="warning"))
        self.assertEqual(self.gate("--run").returncode, 2)
        self.assertTrue(self.summary["authority_changed"])
        self.assertTrue(all(item["status"] == "not_executed" for item in self.summary["verification"]))

    def test_selective_reports_are_versioned(self):
        self.enable_v2()
        test = self.root / "checks/test_checkout.py"
        test.write_text(test.read_text() + "\n# regression\n")
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 0)
        for name, version in (("candidate.lock.json", "archctl.snapshot.v2"), ("impact.json", "archctl.impact.v2"),
                              ("guard.json", "archctl.guard.v2"), ("reconcile.json", "archctl.reconciliation.v2")):
            self.assertEqual(json.loads((self.report / name).read_text())["schema_version"], version, name)
        self.assertTrue(self.summary["verification"][0]["required_by"])
        self.assertIn("selective", (self.report / "gate-summary.md").read_text())

    def test_selective_unexecuted_required_verification_cannot_pass(self):
        self.enable_v2()
        test = self.root / "checks/test_checkout.py"
        test.write_text(test.read_text() + "\n# regression\n")
        self.refresh()
        self.assertEqual(self.gate().returncode, 2)
        self.assertEqual(self.summary["status"], "unknown")
        self.assertTrue(self.summary["verification"])
        for item in self.summary["verification"]:
            self.assertEqual((item["status"], item["obligation"]), ("not_executed", "required"))

    def test_selective_summary_preserves_recorded_advisory_result(self):
        self.enable_v2(obligations={"payment-isolation": "advisory"})
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 0)
        self.assertEqual((self.summary["status"], self.summary["approval"]), ("passed", "not_assessed"))
        advisory = next(f for f in self.summary["findings"] if f["id"] == "payment-isolation")
        text = (self.report / "gate-summary.md").read_text()
        self.assertIn(advisory["message"], text)
        self.assertIn(self.summary["guarantee"], text)

    def test_producer_suggested_verification_is_never_executed(self):
        bundle = json.loads(self.evidence_file.read_text())
        bundle["suggested_verification"] = [{"id": "suggested", "command": [
            sys.executable, "-c", "from pathlib import Path; Path('SUGGESTED').write_text('ran')"]}]
        write_json(self.evidence_file, bundle)
        result = self.gate("--scope", "all", "--run")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.summary["status"], "passed")
        self.assertFalse((self.root / "SUGGESTED").exists())
        self.assertNotIn("suggested", {item["id"] for item in self.summary.get("verification", [])})

    def test_strict_default_uses_the_same_v2_contracts(self):
        source = self.root / "app/orders/api.py"
        source.write_text("from app.ledger import store\n" + source.read_text())
        self.refresh()
        self.assertEqual(self.gate("--run").returncode, 1)
        self.assertEqual(self.summary["schema_version"], "archctl.gate.v2")
        self.assertEqual(self.summary["enforcement"], "strict")
        for item in [*self.summary["findings"], *self.summary["verification"]]:
            self.assertIn("obligation", item)
        for name in ("candidate.lock.json", "impact.json", "guard.json", "reconcile.json"):
            self.assertTrue(json.loads((self.report / name).read_text())["schema_version"].endswith(".v2"), name)
