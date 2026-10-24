"""Reasons remain challengeable when the task has no governed workflow."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from archctl.atlas.context import markdown
from archctl.core.io import write_json
from archctl.core.memory import remember
from tests import test_context as support


class ContextPivotTests(unittest.TestCase):
    setUp = support.ContextWorkflowTests.setUp
    cli = support.ContextWorkflowTests.cli

    def independent(self, *arguments):
        # A fresh interpreter detects transitive imports that in-process mocks hide.
        code = """import contextlib, io, json, sys
from archctl.cli import main
with contextlib.redirect_stdout(io.StringIO()):
    result = main(json.loads(sys.argv[1]))
assert result == 0, result
for name in ('archctl.cli_gate', 'archctl.guard.evaluate', 'archctl.observatory.workflows', 'archctl.core.change'):
    assert name not in sys.modules, name
"""
        result = subprocess.run([sys.executable, "-B", "-c", code,
            json.dumps(["--root", str(self.root), *arguments])], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_core_routes_do_not_load_governance_with_an_invalid_optional_model(self):
        (self.root / "architecture").mkdir()
        (self.root / "architecture/model.yaml").write_text("schema_version: [\n")
        write_json(self.root / "reason.json", support.note())
        for arguments in (("context", "batching"), ("memory", "record", "--input", "reason.json"),
                          ("memory", "show", "batching-lifetime"), ("memory", "list"),
                          ("verify", "run", "--task", "batching", "--paths", "src/api/batching.py",
                           "--command", json.dumps([sys.executable, "-c", "pass"]))):
            with self.subTest(arguments=arguments):
                self.independent(*arguments)

    def test_changed_context_shares_git_scope_without_loading_the_gate(self):
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.source.write_text("batching = 'changed'\n")
        self.independent("context", "batching", "--changed")
        self.assertFalse((self.root / ".archctl").exists())

    def test_reverse_conflict_survives_a_one_record_budget_with_an_exact_fetch(self):
        remember(self.root, support.note())
        remember(self.root, support.note("exception", statement="A narrow exception", rationale="Independent condition",
            paths=[], topics=[], contradicts=["batching-lifetime"]))
        packet = self.cli("context", "request batching lifetime", "--limit", "1")
        record = packet["memories"][0]
        self.assertEqual(record["id"], "batching-lifetime")
        self.assertEqual(record["contradicted_by"], ["exception"])
        self.assertEqual(packet["memory_retrieval"]["omitted"], 1)
        omitted = packet["memory_retrieval"]["omitted_records"][0]
        self.assertEqual(omitted["id"], "exception")
        fetched = self.cli(*omitted["fetch_command"][1:])["records"][0]
        self.assertEqual(fetched["rationale"], "Independent condition")
        self.assertTrue(any(c["kind"] == "conflicting_reasoning" for c in packet["concerns"]))
        self.assertIn("archctl memory show exception", markdown(packet))

    def test_related_branches_are_discovered_transitively_and_omissions_are_bounded(self):
        remember(self.root, support.note())
        for ident, relations in (("branch-a", {"supersedes": ["batching-lifetime"]}),
                                 ("branch-b", {"supersedes": ["batching-lifetime"]}),
                                 ("challenge", {"contradicts": ["branch-a"]})):
            remember(self.root, support.note(ident, statement="Different account", rationale="Independent condition",
                topics=[], paths=[], **relations))
        packet = self.cli("context", "batching", "--limit", "1")
        retrieval = packet["memory_retrieval"]
        self.assertEqual((retrieval["matched"], retrieval["related"], retrieval["omitted"]), (1, 3, 3))
        self.assertEqual(len(retrieval["omitted_records"]), 1)
        self.assertTrue(retrieval["omitted_records_truncated"])
        self.assertEqual(packet["totals"]["memories"], 4)
        complete = self.cli(*retrieval["inventory_command"][1:])["records"]
        self.assertEqual({r["id"] for r in complete}, {"batching-lifetime", "branch-a", "branch-b", "challenge"})

    def test_matching_and_changed_source_hashes_leave_reason_applicability_unassessed(self):
        remember(self.root, support.note())
        path = self.root / "architecture/memory/batching-lifetime.json"
        original = path.read_bytes()
        before = self.cli("context", "batching")["memories"][0]
        self.source.write_text("new implementation\n")
        after = self.cli("context", "batching")["memories"][0]
        self.assertEqual(before["freshness"]["status"], "current")
        self.assertEqual(after["freshness"]["status"], "stale")
        self.assertEqual(before["applicability"]["status"], "not_assessed")
        self.assertEqual(after["applicability"], before["applicability"])
        self.assertEqual(path.read_bytes(), original)

    def test_reference_presence_is_separate_from_provider_verification(self):
        references = ["src/api/batching.py", "artifact:missing.md", "case:old-case", "conversation:turn-2",
                      "artifact:../outside.md"]
        remember(self.root, support.note(references=references))
        packet = self.cli("context", "batching")
        record = packet["memories"][0]
        self.assertEqual(record["references"], references)
        self.assertEqual([r["status"] for r in record["reference_checks"]],
                         ["available", "unavailable", "not_checked", "not_checked", "unavailable"])
        self.assertTrue(any(c["kind"] == "unavailable_reference" for c in packet["concerns"]))

    def test_markdown_shows_assumptions_scope_and_full_untruncated_fetch(self):
        remember(self.root, support.note(rationale="Detailed reasoning. " * 160,
            assumptions=["Jobs overlap"], components=["worker-runtime"]))
        packet = self.cli("context", "batching")
        self.assertTrue(packet["memories"][0]["excerpt_truncated"])
        text = markdown(packet)
        for value in ("Assumptions: Jobs overlap", "Paths: src/api/batching.py", "Components: worker-runtime",
                      "Applicability: not_assessed", "archctl memory show batching-lifetime"):
            self.assertIn(value, text)
        self.assertGreater(len(self.cli("memory", "show", "batching-lifetime")["records"][0]["rationale"]), 2000)

    def test_memory_list_finds_a_reason_by_an_assumption(self):
        remember(self.root, support.note(assumptions=["Leases expire after cancellation"]))
        self.assertEqual(self.cli("memory", "list", "leases")["records"][0]["id"], "batching-lifetime")

    def test_unreadable_optional_adr_and_default_evidence_are_local_gaps(self):
        decisions = self.root / "architecture/decisions"
        decisions.mkdir(parents=True)
        (decisions / "invalid.md").write_bytes(b"\xff")
        (self.root / ".archctl").mkdir()
        (self.root / ".archctl/evidence.json").write_bytes(b"\xff")
        remember(self.root, support.note())
        packet = self.cli("context", "batching")
        self.assertTrue(packet["memories"])
        self.assertTrue(any("could not be read" in g["message"] for g in packet["limitations"]))
        self.assertTrue(any("default evidence is invalid" in g["message"] for g in packet["limitations"]))
        self.cli("context", "batching", "--evidence", ".archctl/evidence.json", expected=3)

    def test_corrupt_memory_is_not_downgraded_to_an_optional_gap(self):
        folder = self.root / "architecture/memory"
        folder.mkdir(parents=True)
        (folder / "broken.json").write_text("{}")
        self.cli("context", "batching", expected=3)

    def test_explicit_registered_check_still_requires_its_model(self):
        self.cli("verify", "run", "--task", "batching", "--check", "missing", expected=3)


class StatusPivotTests(unittest.TestCase):
    setUp = support.ContextWorkflowTests.setUp
    cli = support.ContextWorkflowTests.cli

    def test_missing_governed_inputs_do_not_become_core_prerequisites(self):
        report = self.cli("status", expected=2)
        self.assertEqual(report["status"], "needs_model")  # Preserve legacy exit/status consumers.
        self.assertEqual(report["status_scope"], "governed_inputs")
        for name in ("context", "memory", "verify_command"):
            self.assertFalse(report["capabilities"][name]["requires_model"])
            self.assertFalse(report["capabilities"][name]["requires_baseline"])
        self.assertEqual(report["capabilities"]["governed_gate"]["adoption"], "not_assessed")
        self.assertIn("context TASK", report["next_actions"][0])
        self.assertFalse(any(action.startswith("Run gate") for action in report["next_actions"]))
        self.assertFalse((self.root / "architecture").exists())


class EvidencePivotTests(unittest.TestCase):
    setUp = support.ContextWithEvidenceTests.setUp
    cli = support.ContextWorkflowTests.cli

    def test_context_preserves_provider_identity_and_bundle_location(self):
        from archctl.core.compiler import compile_model
        from archctl.integrations.briefcase.adapter import parse_evidence
        bundle = json.loads((self.root / "evidence.json").read_text())
        observed = parse_evidence(bundle, compile_model(self.root))
        packet = self.cli("context", "checkout", "--paths", "app/orders/api.py", "--evidence", "evidence.json")
        self.assertEqual(packet["source"]["evidence_producer"], bundle["producer"])
        self.assertEqual(packet["source"]["evidence_revision"], bundle["source"]["revision"])
        self.assertEqual(packet["source"]["evidence_source_digest"], observed.source_digest)
        self.assertEqual(packet["source"]["evidence_path"], "evidence.json")
        self.assertTrue(packet["evidence"])
        original_locations = {item["location"] for item in bundle["evidence"]}
        self.assertTrue(all(item["location"] in original_locations for item in packet["evidence"]))
        self.assertEqual(packet["decisions"][0]["applicability"]["status"], "not_assessed")

    def test_failed_refresh_retains_historical_reasons_without_reusing_old_evidence(self):
        write_json(self.root / ".archctl/evidence.json", json.loads((self.root / "evidence.json").read_text()))
        remember(self.root, support.note())
        packet = self.cli("context", "batching", "--refresh-evidence", "--briefcase", "/missing/briefcase")
        self.assertTrue(packet["memories"])
        self.assertEqual(packet["observed_edges"], [])
        self.assertEqual(packet["source"]["evidence_freshness"], "unavailable")
        self.assertIsNone(packet["source"]["evidence_path"])
        self.assertIsNone(packet["source"]["evidence_producer"])
        self.assertTrue(any("refresh unavailable" in gap["message"] for gap in packet["limitations"]))
