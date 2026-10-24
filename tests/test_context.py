"""Context and memory support decisions across tasks without architecture adoption."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from archctl.atlas.context import markdown as context_markdown
from archctl.core.compiler import compile_model
from archctl.core.io import InputError, digest, write_json
from archctl.core.memory import freshness, read_memories, remember
from archctl.integrations.verification import parse_execution
from tests.fixtures.evidence import build
from tests.fixtures.storefront import initialize


def note(ident="batching-lifetime", **extra):
    return {"schema_version": "archctl.memory.v2", "id": ident,
        "statement": "API batching assumes a request lifetime",
        "rationale": "Worker concurrency outlives the request; extract pure batching before reuse.",
        "origin": "agent_inferred", "references": ["conversation:task-1/message-2"],
        "paths": ["src/api/batching.py"], "topics": ["batching", "concurrency"], **extra}


class ContextWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "src/api/batching.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("REQUEST_BATCH = []\ndef batch_request(item):\n    REQUEST_BATCH.append(item)\n")
        (self.root / "src/worker").mkdir()
        (self.root / "src/worker/jobs.py").write_text("def run_worker(): return 'worker'\n")

    def cli(self, *arguments, expected=0):
        result = subprocess.run([sys.executable, "-m", "archctl", "--root", str(self.root), *arguments],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout else json.loads(result.stderr)

    def test_memory_operations_accept_a_symlinked_root(self):
        alias = self.root.parent / f"{self.root.name}-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink, missing_ok=True)
        remember(alias, note())
        self.assertEqual([record.id for record in read_memories(alias)], ["batching-lifetime"])

    def test_greenfield_context_needs_no_model_git_baseline_or_existing_paths(self):
        packet = self.cli("context", "Create a new event worker", "--paths", "src/new/events.py")
        self.assertEqual(packet["status"], "assembled")
        self.assertIsNone(packet["source"]["model_revision"])
        self.assertTrue(any(c["origin"] == "provisional" for c in packet["components"]))
        self.assertTrue(packet["limitations"])
        self.assertFalse((self.root / "architecture").exists())
        self.assertNotIn("approval", packet)

    def test_task_terms_change_source_retrieval_for_the_same_paths(self):
        batch = self.cli("context", "request batching", "--limit", "1")
        worker = self.cli("context", "run worker jobs", "--limit", "1")
        self.assertEqual(batch["source_candidates"][0]["path"], "src/api/batching.py")
        self.assertEqual(worker["source_candidates"][0]["path"], "src/worker/jobs.py")

    def test_standalone_adr_is_retrieved_without_a_governed_model(self):
        folder = self.root / "architecture/decisions"
        folder.mkdir(parents=True)
        (folder / "ADR-1.md").write_text("# Batching lifetime\n\nKeep request state local to API calls.\n")
        packet = self.cli("context", "Batching lifetime")
        self.assertEqual(packet["decisions"][0]["id"], "ADR-1")
        self.assertIn("request state", packet["decisions"][0]["rationale_excerpt"])

    def test_adr_lifecycle_links_survive_limit_and_markdown(self):
        folder = self.root / "architecture/decisions"
        folder.mkdir(parents=True)
        for number in range(1, 11):
            ident = f"ADR-{number:02d}"
            status = "superseded" if number == 1 else "accepted"
            supersedes = "\nsupersedes: [ADR-01]" if number == 10 else "\nsupersedes: []"
            (folder / f"{ident}.md").write_text(
                f"---\nid: {ident}\nstatus: {status}\ntitle: Decision {number}\ncomponents: []{supersedes}\n---\n"
                "batching decision\n")
        complete = self.cli("context", "batching", "--limit", "10")
        by_id = {item["id"]: item for item in complete["decisions"]}
        self.assertEqual(complete["totals"]["decisions"], 10)
        self.assertEqual(by_id["ADR-01"]["superseded_by"], ["ADR-10"])
        self.assertEqual(by_id["ADR-10"]["supersedes"], ["ADR-01"])
        self.assertIn("Superseded by: ADR-10", context_markdown(complete))
        limited = self.cli("context", "batching", "--limit", "8")
        self.assertEqual(limited["totals"]["decisions"], 10)
        self.assertIn("ADR-10", [item["id"] for item in limited["decisions"]])
        self.assertNotIn("ADR-01", [item["id"] for item in limited["decisions"]])
        self.assertTrue(any("returned 8 of 10" in gap["message"] for gap in limited["limitations"]))

    def test_oversized_standalone_adr_is_reported_not_silently_skipped(self):
        folder = self.root / "architecture/decisions"
        folder.mkdir(parents=True)
        (folder / "ADR-BIG.md").write_text("# Batching decision\n\n" + "x" * 65536)
        packet = self.cli("context", "batching")
        self.assertTrue(any("exceeds 65536 bytes" in gap["message"] for gap in packet["limitations"]))

    def test_model_dir_moves_governed_adrs_not_advisory_bindings_or_memory(self):
        model = self.root / "arch"
        (model / "decisions").mkdir(parents=True)
        (model / "decisions/ADR-ALT.md").write_text(
            "---\nid: ADR-ALT\nstatus: accepted\ntitle: Advisory decision\ncomponents: []\nsupersedes: []\n---\n"
            "Use advisory batching decision.\n")
        (self.root / "architecture").mkdir()
        (self.root / "architecture/context.yaml").write_text(yaml.safe_dump({
            "schema_version": "archctl.context-config.v2",
            "components": [{"id": "worker-runtime", "paths": ["src/api/**"], "purpose": "Advisory worker"}]}))
        remember(self.root, note())
        packet = self.cli("--model-dir", "arch", "context", "advisory batching")
        self.assertIsNone(packet["source"]["model_revision"])
        self.assertEqual(packet["decisions"][0]["id"], "ADR-ALT")
        self.assertIn("worker-runtime", [item["id"] for item in packet["components"]])
        self.assertIn("batching-lifetime", [item["id"] for item in packet["memories"]])

    def test_invalid_default_evidence_is_a_limitation_but_explicit_input_is_an_error(self):
        folder = self.root / ".archctl"
        folder.mkdir()
        (folder / "evidence.json").write_text("{}")
        packet = self.cli("context", "batching")
        self.assertTrue(any("default evidence is invalid" in g["message"] for g in packet["limitations"]))
        self.cli("context", "batching", "--evidence", ".archctl/evidence.json", expected=3)

    def test_same_component_import_does_not_falsely_report_an_architecture_cycle(self):
        helper = self.source.parent / "helper.py"
        helper.write_text("def pure_batch(items): return tuple(items)\n")
        packet = self.cli("context", "Reuse batching", "--paths", "src/api/batching.py", "src/api/helper.py",
                          "--dependency", "src/api/batching.py", "src/api/helper.py")
        self.assertEqual(packet["proposed_dependencies"][0]["cycle"], "within_component")

    def test_cold_start_retrieves_rationale_with_origin_reference_and_assumptions(self):
        input_path = self.root / "record.json"
        write_json(input_path, note(assumptions=["request lifetime differs from job lifetime"]))
        self.cli("memory", "record", "--input", "record.json")
        # A new subprocess has no conversational state and must recover persisted reasoning.
        packet = self.cli("context", "Reuse batching for worker concurrency", "--paths", "src/worker/jobs.py")
        memory = packet["memories"][0]
        self.assertEqual(memory["origin"], "agent_inferred")
        self.assertEqual(memory["references"], ["conversation:task-1/message-2"])
        self.assertIn("request lifetime differs", memory["assumptions"][0])
        self.assertEqual(memory["freshness"]["status"], "current")

    def test_stale_memory_remains_visible_and_is_not_promoted_to_fact(self):
        remember(self.root, note())
        self.source.write_text("def batch_request(items): return tuple(items)\n")
        packet = self.cli("context", "Reuse batching")
        self.assertEqual(packet["memories"][0]["freshness"]["status"], "stale")
        self.assertTrue(any(c["kind"] == "stale_reasoning" for c in packet["concerns"]))
        self.assertEqual(read_memories(self.root)[0].origin, "agent_inferred")

    def test_records_are_immutable_and_idempotent_retry_does_not_repin(self):
        old = remember(self.root, note())
        self.source.write_text("changed\n")
        retry = remember(self.root, note())
        self.assertEqual(old, retry)
        self.assertEqual(freshness(self.root, retry)["status"], "stale")
        with self.assertRaisesRegex(InputError, "immutable"):
            remember(self.root, note(origin="user_stated"))

    def test_conflicts_and_supersession_keep_history_and_related_context(self):
        remember(self.root, note())
        remember(self.root, note("extract-batching", statement="Share the pure part", origin="agent_chosen",
                                supersedes=["batching-lifetime"], paths=[]))
        remember(self.root, note("dispute", statement="New constraint", rationale="Check lifecycle again",
                                topics=[], paths=[], contradicts=["extract-batching"]))
        packet = self.cli("context", "Share the pure part")
        by_id = {m["id"]: m for m in packet["memories"]}
        self.assertIn("batching-lifetime", by_id)
        self.assertIn("dispute", by_id)
        self.assertEqual(by_id["batching-lifetime"]["superseded_by"], "extract-batching")
        self.assertEqual(by_id["batching-lifetime"]["superseded_by_ids"], ["extract-batching"])
        self.assertEqual(len(read_memories(self.root)), 3)

    def test_multiple_memory_successors_are_all_reported(self):
        remember(self.root, note())
        remember(self.root, note("successor-a", statement="API batching successor A", paths=[],
                                 supersedes=["batching-lifetime"]))
        remember(self.root, note("successor-b", statement="API batching successor B", paths=[],
                                 supersedes=["batching-lifetime"]))
        packet = self.cli("context", "API batching")
        by_id = {item["id"]: item for item in packet["memories"]}
        self.assertEqual(by_id["batching-lifetime"]["superseded_by_ids"],
                         ["successor-a", "successor-b"])
        self.assertEqual(by_id["batching-lifetime"]["superseded_by"], "successor-a")
        self.assertIn("Superseded by: successor-a, successor-b", context_markdown(packet))

    def test_component_alias_preserves_memory_retrieval_after_rename(self):
        config = {"schema_version": "archctl.context-config.v2", "components": [
            {"id": "worker-runtime", "aliases": ["legacy-worker"], "paths": ["src/worker/**"]}]}
        (self.root / "architecture").mkdir()
        (self.root / "architecture/context.yaml").write_text(yaml.safe_dump(config))
        remember(self.root, note(statement="Independent reason", rationale="Old architectural choice",
                                paths=[], topics=[], components=["legacy-worker"]))
        packet = self.cli("context", "Update jobs", "--paths", "src/worker/jobs.py")
        self.assertTrue(packet["memories"])
        self.assertEqual(packet["components"][0]["id"], "worker-runtime")

    def test_invalid_optional_model_limits_context_without_preventing_work(self):
        (self.root / "architecture").mkdir()
        (self.root / "architecture/model.yaml").write_text("schema_version: [\n")
        packet = self.cli("context", "batching")
        self.assertTrue(any("invalid" in g["message"] for g in packet["limitations"]))
        self.cli("verify", "run", "--task", "batching smoke", "--paths", "src/api/batching.py",
                 "--command", json.dumps([sys.executable, "-c", "print('ok')"]))

    def test_generated_output_does_not_overwrite_source_or_previous_packet(self):
        self.cli("context", "batch", "--out", "src/api/batching.py", expected=3)
        self.cli("context", "batch", "--out", ".archctl/context.json")
        self.cli("context", "batch", "--out", ".archctl/context.json", expected=3)

    def test_legacy_advisory_contracts_are_rejected(self):
        with self.assertRaisesRegex(InputError, "archctl.memory.v2"):
            remember(self.root, note(schema_version="archctl.memory.v1"))
        (self.root / "architecture").mkdir()
        (self.root / "architecture/context.yaml").write_text(yaml.safe_dump({
            "schema_version": "archctl.context-config.v1", "components": []}))
        self.cli("context", "batching", expected=3)
        (self.root / "architecture/context.yaml").unlink()
        result = self.cli("verify", "run", "--task", "batching", "--paths", "src/api/batching.py",
                          "--command", json.dumps([sys.executable, "-c", "pass"]))
        result.pop("applicability"); result.pop("record_path"); result.pop("revision")
        result["schema_version"] = "archctl.execution.v1"
        with self.assertRaisesRegex(InputError, "archctl.execution.v2"):
            parse_execution(result)

    def test_invalid_memory_origin_reference_and_escaping_paths_are_rejected(self):
        for invalid in (note(origin="approved"), note(references=[]), note(paths=["../outside.py"]),
                        note(supersedes=["missing"]), note(contradicts=["batching-lifetime"])):
            with self.subTest(invalid=invalid), self.assertRaises(InputError):
                remember(self.root, invalid)

    def test_symlinks_outside_root_are_not_read_as_context(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "secret.py"
            target.write_text("SECRET = 'batching'\n")
            (self.root / "escape.py").symlink_to(target)
            packet = self.cli("context", "batching")
            self.assertNotIn("escape.py", [s["path"] for s in packet["source_candidates"]])
            self.cli("context", "batching", "--paths", "escape.py", expected=3)

    def test_command_results_survive_missing_architectural_evidence(self):
        result = self.cli("verify", "run", "--task", "batching regression", "--paths", "src/api/batching.py",
                          "--command", json.dumps([sys.executable, "-c", "print('ok')"]))
        self.assertEqual(result["result"]["status"], "passed")
        self.assertEqual(result["applicability"]["status"], "current")
        packet = self.cli("context", "batching regression")
        self.assertEqual(packet["executions"][0]["result"]["status"], "passed")
        self.assertTrue(packet["limitations"])
        self.source.write_text("changed\n")
        packet = self.cli("context", "batching regression")
        self.assertEqual(packet["executions"][0]["applicability"]["status"], "stale")
        self.assertEqual(packet["executions"][0]["result"]["status"], "passed")

    def test_verification_reports_failure_timeout_and_source_changes(self):
        result = self.cli("verify", "run", "--task", "failed", "--paths", "src/api/batching.py",
                          "--command", json.dumps([sys.executable, "-c", "raise SystemExit(4)"]), expected=1)
        self.assertEqual(result["result"]["status"], "failed")
        result = self.cli("verify", "run", "--task", "timeout", "--timeout", "1", "--paths", "src/api/batching.py",
                          "--command", json.dumps([sys.executable, "-c", "import time; time.sleep(5)"]), expected=2)
        self.assertEqual(result["result"]["status"], "unknown")
        result = self.cli("verify", "run", "--task", "mutation", "--paths", "src/api/batching.py", "--command",
                          json.dumps([sys.executable, "-c", "from pathlib import Path; Path('src/api/batching.py').write_text('changed')"]), expected=2)
        self.assertEqual(result["result"]["status"], "passed")
        self.assertFalse(result["source"]["stable_during_execution"])

    def test_external_execution_import_keeps_harness_origin_and_actual_status(self):
        result = self.cli("verify", "run", "--task", "batching", "--paths", "src/api/batching.py", "--command",
                          json.dumps([sys.executable, "-c", "pass"]))
        result.pop("applicability"); result.pop("record_path"); result.pop("revision")
        result["origin"] = "harness"
        result["references"] = ["session:test-run-1"]
        write_json(self.root / "external.json", result)
        imported = self.cli("verify", "import", "--input", "external.json")
        self.assertEqual(imported["origin"], "harness")
        self.assertEqual(imported["references"], ["session:test-run-1"])
        imported["result"]["returncode"] = 2
        imported.pop("applicability"); imported.pop("record_path"); imported.pop("revision")
        with self.assertRaises(InputError):
            parse_execution(imported)


class ContextWithEvidenceTests(unittest.TestCase):
    cli = ContextWorkflowTests.cli

    def setUp(self):
        ContextWorkflowTests.setUp(self)
        initialize(self.root, demo=True)
        write_json(self.root / "evidence.json", build(self.root))

    def test_hypothetical_import_reports_cycle_path_without_creating_observation(self):
        packet = self.cli("context", "Reuse orders in ledger", "--dependency", "ledger", "orders",
                          "--evidence", "evidence.json")
        hypothetical = packet["proposed_dependencies"][0]
        self.assertEqual(hypothetical["cycle"], "supported_path")
        self.assertEqual([(e["source"], e["target"]) for e in hypothetical["return_path"]],
                         [("orders", "payments"), ("payments", "ledger")])
        self.assertFalse(any((e["source"], e["target"]) == ("ledger", "orders") for e in packet["observed_edges"]))

    def test_undeclared_edge_is_context_and_constraint_does_not_stop_verification(self):
        path = self.root / "app/orders/api.py"
        path.write_text("from app.ledger import store\n" + path.read_text())
        write_json(self.root / "evidence.json", build(self.root))
        packet = self.cli("context", "Change checkout", "--paths", "app/orders/api.py", "--evidence", "evidence.json")
        self.assertTrue(any(c["kind"] == "declared_constraint" for c in packet["concerns"]))
        self.cli("verify", "run", "--task", "Checkout checks", "--check", "payments-contract")

    def test_stale_evidence_cannot_prove_current_cycle_and_adr_rationale_is_included(self):
        path = self.root / "app/orders/api.py"
        path.write_text(path.read_text() + "\n# edited\n")
        packet = self.cli("context", "Reuse ledger", "--dependency", "ledger", "orders", "--evidence", "evidence.json")
        self.assertEqual(packet["proposed_dependencies"][0]["cycle"], "possible_from_stale_evidence")
        self.assertTrue(packet["decisions"][0]["rationale_excerpt"])

    def test_advisory_context_config_does_not_enter_governed_model_authority(self):
        baseline = compile_model(self.root)
        path = self.root / "architecture/context.yaml"
        path.write_text(yaml.safe_dump({"schema_version": "archctl.context-config.v2", "components": [
            {"id": "worker", "paths": ["src/worker/**"], "aliases": []}]}))
        self.assertEqual(baseline.revision, compile_model(self.root).revision)
        self.cli("context", "worker", "--paths", "src/worker/jobs.py")


if __name__ == "__main__":
    unittest.main()
