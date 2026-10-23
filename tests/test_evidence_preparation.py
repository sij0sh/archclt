"""Preparation safety tests. Mocked exports are not native interoperability."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from archctl.core.compiler import compile_model
from archctl.core.io import InputError, file_digest, source_files, write_json
from archctl.integrations.briefcase.preparation import _run, prepare_evidence
from archctl.integrations.briefcase.adapter import check_freshness, read_evidence
from tests.fixtures.storefront import initialize


class PreparationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "application"
        initialize(self.root, demo=True)
        (self.root / ".gitignore").write_text(".archctl/\n.briefcase/\n__pycache__/\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "source")
        self.snapshot = compile_model(self.root)
        self.destination = self.root / ".archctl/prepared/test"
        self.archctl = self.directory / "external-archctl"
        self.briefcase = self.directory / "external-briefcase"
        for path in (self.archctl, self.briefcase):
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        self.commands = []
        self.mutate = lambda bundle: None
        self.after_export = lambda: None
        self.publication_change = lambda publication: None

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                              capture_output=True, text=True).stdout.strip()

    def fake_run(self, argv, cwd, output):
        """Supply wire fixtures only; real tools are exercised separately below."""
        self.commands.append(list(map(str, argv)))
        if "--version" in argv:
            result = "0.1.0\n"
        elif "export-evidence" in argv:
            projection = Path(argv[argv.index("--root") + 1])
            snapshot = compile_model(projection)
            patterns = tuple(p for c in snapshot.model.components for p in c.paths)
            files = source_files(projection, patterns)
            bundle = {"schema_version": "archctl.evidence.v2",
                      "producer": {"name": "briefcase-native-exporter", "version": "1+briefcase-0.1.0"},
                      "source": {"revision": "briefcase:view:1:snapshot:fixture", "files": files},
                      "coverage": {"analysis": "static", "status": "complete", "gaps": [],
                                   "components": [c.id for c in snapshot.model.components],
                                   "relationship_kinds": ["imports"]}, "evidence": [], "edges": []}
            self.mutate(bundle)
            write_json(Path(argv[argv.index("--out") + 1]), bundle)
            self.after_export()
            result = json.dumps({"status": "written"})
        else:
            self.assertIn("status", argv)
            publication = {"view_id": "view:1",
                "status": "published", "scope": "source", "diagnostics": {
                    "coverage": {"unresolved_count": 2, "unsupported_count": 1},
                    "capture": {"repository_root": str(Path(argv[argv.index("--db") + 1]).parent.parent),
                                "capture_head": subprocess.run(["git", "-C", str(Path(argv[argv.index("--db") + 1]).parent.parent),
                                    "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()}}}
            self.publication_change(publication)
            result = json.dumps({"current_view": "view:1", "scans": [publication]})
        output.write_text(result)
        return result

    def prepare(self, **kwargs):
        with patch("archctl.integrations.briefcase.preparation._run", side_effect=self.fake_run):
            return prepare_evidence(self.root, self.snapshot, archctl=self.archctl,
                                    briefcase=self.briefcase, destination=self.destination,
                                    source_roots=(".",), **kwargs)

    def assert_failed(self, text):
        with self.assertRaisesRegex(InputError, text):
            self.prepare()
        self.assertFalse((self.destination / "evidence.json").exists())
        if (self.destination / "manifest.json").exists():
            manifest = json.loads((self.destination / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "error")
        self.assertEqual(len(self.git("worktree", "list", "--porcelain").split("worktree ")) - 1, 1)


class PreparationTests(PreparationFixture):
    def test_fresh_projection_pins_dirty_added_and_deleted_files_and_retains_limits(self):
        edited = self.root / "app/orders/api.py"
        edited.write_text(edited.read_text() + "\n# dirty candidate\n")
        added = self.root / "app/orders/new file.py"
        added.write_text("# added candidate\n")
        deleted = self.root / "app/orders/__init__.py"
        deleted.unlink()
        before = self.git("status", "--porcelain")
        config = self.git("config", "--local", "--list")
        result = self.prepare()
        self.assertEqual(result["schema_version"], "archctl.output.v2")
        self.assertEqual(result["status"], "written")
        bundle = read_evidence(self.destination / "evidence.json", self.snapshot)
        self.assertEqual(check_freshness(self.root, self.snapshot, bundle), [])
        manifest = json.loads((self.destination / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["source"]["head_sha"], self.git("rev-parse", "HEAD"))
        self.assertEqual(manifest["source"]["overlay"]["app/orders/new file.py"]["candidate_sha256"], file_digest(added))
        self.assertIsNone(manifest["source"]["overlay"]["app/orders/__init__.py"]["candidate_sha256"])
        self.assertIn("checks/test_checkout.py", manifest["omitted_tracked_paths"])
        self.assertEqual(manifest["support"]["languages"], ["python"])
        self.assertEqual(manifest["gate"], "not_executed")
        self.assertEqual(manifest["approval"], "not_assessed")
        self.assertEqual(manifest["publication"]["diagnostics"]["coverage"]["unresolved_count"], 2)
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertEqual(self.git("config", "--local", "--list"), config)
        self.assertEqual(len(self.git("worktree", "list", "--porcelain").split("worktree ")) - 1, 1)
        for command in self.commands:
            self.assertIn(command[0], (str(self.archctl), str(self.briefcase)))

    def test_reused_destination_never_changes_previous_evidence(self):
        self.prepare()
        original = (self.destination / "evidence.json").read_bytes()
        with self.assertRaisesRegex(InputError, "exist"):
            self.prepare()
        self.assertEqual((self.destination / "evidence.json").read_bytes(), original)

    def test_missing_changed_extra_and_partial_export_never_publish(self):
        for kind in ("missing", "changed", "extra", "partial", "missing-component"):
            with self.subTest(kind=kind):
                self.destination = self.root / f".archctl/prepared/{kind}"
                def mutate(bundle):
                    files = bundle["source"]["files"]
                    if kind == "missing":
                        files.pop(next(iter(files)))
                    elif kind == "changed":
                        files[next(iter(files))] = "0" * 64
                    elif kind == "extra":
                        files["app/undeclared.py"] = "0" * 64
                    elif kind == "missing-component":
                        bundle["coverage"]["components"].pop()
                    else:
                        bundle["coverage"].update(status="partial", gaps=["missing capture"])
                self.mutate = mutate
                self.assert_failed("inventory|coverage")

    def test_changed_candidate_authoring_head_and_tools_invalidate_export(self):
        for kind in ("source", "new-source", "authoring", "head", "tool"):
            with self.subTest(kind=kind):
                # Each mutation needs an independent application and snapshot.
                with tempfile.TemporaryDirectory() as directory:
                    original = self.directory / "application"
                    self.root = Path(directory) / "application"
                    shutil.copytree(original, self.root, ignore=shutil.ignore_patterns(".git", ".archctl"))
                    self.git("init", "-q")
                    self.git("add", ".")
                    self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "source")
                    self.snapshot = compile_model(self.root)
                    self.destination = self.root / ".archctl/prepared/test"
                    def mutate():
                        if kind == "source":
                            (self.root / "app/orders/api.py").write_text("# changed during export\n")
                        elif kind == "new-source":
                            (self.root / "app/orders/new.py").write_text("# unpinned\n")
                        elif kind == "authoring":
                            path = self.root / "architecture/model.yaml"
                            path.write_text(path.read_text() + "\n# authoring changed\n")
                        elif kind == "head":
                            self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "new head")
                        else:
                            self.briefcase.write_text(self.briefcase.read_text() + "# changed\n")
                    self.after_export = mutate
                    self.assert_failed("changed|inventory")
                    self.root = original

    def test_ambiguous_binding_empty_scope_symlinks_and_nonpython_are_rejected(self):
        component_file = self.root / "architecture/model.yaml"
        original = component_file.read_text()
        for kind in ("ambiguous", "empty", "symlink", "nonpython"):
            with self.subTest(kind=kind):
                value = yaml.safe_load(original)
                if kind == "ambiguous":
                    value["components"][1]["paths"].append("app/orders/**")
                elif kind == "empty":
                    value["components"][0]["paths"] = ["missing/**"]
                elif kind == "symlink":
                    (self.root / "app/orders/link.py").symlink_to("api.py")
                else:
                    (self.root / "app/orders/native.rs").write_text("// unsupported\n")
                component_file.write_text(yaml.safe_dump(value, sort_keys=False))
                self.snapshot = compile_model(self.root)
                self.destination = self.root / f".archctl/prepared/{kind}"
                self.assert_failed("binding|files|Symlink|Python")
                (self.root / "app/orders/link.py").unlink(missing_ok=True)
                (self.root / "app/orders/native.rs").unlink(missing_ok=True)
        component_file.write_text(original)

    def test_producer_failure_missing_tool_and_candidate_tool_never_reuse_old_bundle(self):
        old = self.root / ".archctl/evidence.json"
        old.parent.mkdir(exist_ok=True)
        old.write_text('{"old":true}\n')
        def fail_export(argv, cwd, output):
            if "export-evidence" in argv:
                raise InputError("producer failed")
            return self.fake_run(argv, cwd, output)
        with patch("archctl.integrations.briefcase.preparation._run", side_effect=fail_export):
            with self.assertRaisesRegex(InputError, "producer failed"):
                prepare_evidence(self.root, self.snapshot, archctl=self.archctl,
                                 briefcase=self.briefcase, destination=self.destination, source_roots=(".",))
        self.assertFalse((self.destination / "evidence.json").exists())
        self.assertEqual(old.read_text(), '{"old":true}\n')
        self.destination = self.root / ".archctl/prepared/missing-tool"
        self.briefcase.unlink()
        self.assert_failed("executable")
        self.destination = self.root / ".archctl/prepared/candidate-tool"
        self.briefcase = self.root / "candidate-briefcase"
        self.briefcase.write_text("#!/bin/sh\nexit 0\n")
        self.briefcase.chmod(0o755)
        self.assert_failed("outside|checkout")


    def test_missing_or_wrong_publication_cannot_publish(self):
        for kind in ("view", "root", "head"):
            with self.subTest(kind=kind):
                self.destination = self.root / f".archctl/prepared/wrong-{kind}"
                def mutate(publication):
                    if kind == "view":
                        publication["view_id"] = "view:999"
                    elif kind == "root":
                        publication["diagnostics"]["capture"]["repository_root"] = str(self.root)
                    else:
                        publication["diagnostics"]["capture"]["capture_head"] = "0" * 40
                self.publication_change = mutate
                self.assert_failed("publication|producing")

    def test_malformed_publication_output_is_an_input_error(self):
        for document in ("[]", "{}", '{"scans":[null]}', '{"scans":[],"scans":[]}'):
            with self.subTest(document=document):
                self.destination = self.root / f".archctl/prepared/malformed-{len(self.commands)}"
                def malformed(argv, cwd, output):
                    if "status" in argv:
                        output.write_text(document)
                        return document
                    return self.fake_run(argv, cwd, output)
                with patch("archctl.integrations.briefcase.preparation._run", side_effect=malformed):
                    with self.assertRaises(InputError):
                        prepare_evidence(self.root, self.snapshot, archctl=self.archctl,
                                         briefcase=self.briefcase, destination=self.destination,
                                         source_roots=(".",))
                self.assertFalse((self.destination / "evidence.json").exists())

    def test_wrong_import_roots_and_changed_export_are_rejected(self):
        for source_root in ("missing", "app", "checks"):
            with self.subTest(source_root=source_root):
                self.destination = self.root / f".archctl/prepared/root-{source_root}"
                with self.assertRaisesRegex(InputError, "Source root"):
                    with patch("archctl.integrations.briefcase.preparation._run", side_effect=self.fake_run):
                        prepare_evidence(self.root, self.snapshot, archctl=self.archctl,
                                         briefcase=self.briefcase, destination=self.destination,
                                         source_roots=(source_root,))
                self.assertFalse((self.destination / "evidence.json").exists())
        self.destination = self.root / ".archctl/prepared/changed-export"
        def change_export(publication):
            (self.destination / "export.json").write_text("{}\n")
        self.publication_change = change_export
        self.assert_failed("evidence changed")

    def test_projection_never_writes_through_a_head_symlink(self):
        victim = self.directory / "victim.py"
        victim.write_text("# must survive unchanged\n")
        source = self.root / "app/orders/escape.py"
        source.symlink_to(victim)
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "symlink")
        source.unlink()
        source.write_text("# ordinary candidate file\n")
        self.snapshot = compile_model(self.root)
        self.assert_failed("Symlink")
        self.assertEqual(victim.read_text(), "# must survive unchanged\n")

    def test_external_commands_drop_candidate_python_and_database_overrides(self):
        output = self.directory / "environment.json"
        with patch.dict(os.environ, {"PYTHONPATH": str(self.root), "PYTHONHOME": str(self.root),
                                     "BRIEFCASE_DB": "wrong-database", "GIT_DIR": "wrong-repository"}):
            result = _run([sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
                          self.directory, output)
        environment = json.loads(result)
        for name in ("PYTHONPATH", "PYTHONHOME", "BRIEFCASE_DB", "GIT_DIR"):
            self.assertNotIn(name, environment)
        self.assertEqual(environment["PYTHONSAFEPATH"], "1")
        with self.assertRaisesRegex(InputError, "failed"):
            _run([sys.executable, "-c", "raise SystemExit(7)"], self.directory, output)
        with self.assertRaisesRegex(InputError, "unavailable"):
            _run([str(self.directory / "missing")], self.directory, output)
        with patch("archctl.integrations.briefcase.preparation.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("producer", 300)):
            with self.assertRaisesRegex(InputError, "timed out"):
                _run([sys.executable], self.directory, output)


@unittest.skipUnless(os.environ.get("ARCHCTL_RELEASE_EXPORTER") and os.environ.get("BRIEFCASE_BIN"),
                     "Reviewed v2 exporter and Briefcase are not configured")
class PinnedPreparationIntegrationTests(PreparationFixture):

    def test_pinned_tools_support_archctl_and_roast_layouts(self):
        for package in ("archctl", "roast_my_harness"):
            with self.subTest(package=package):
                target = self.root / "src" / package
                target.parent.mkdir(exist_ok=True)
                shutil.move(str(self.root / "app"), target)
                for path in target.rglob("*.py"):
                    path.write_text(path.read_text().replace("app.", package + "."))
                components = self.root / "architecture/model.yaml"
                value = yaml.safe_load(components.read_text())
                for component in value["components"]:
                    component["paths"] = [p.replace("app/", f"src/{package}/") for p in component["paths"]]
                components.write_text(yaml.safe_dump(value, sort_keys=False))
                self.snapshot = compile_model(self.root)
                destination = self.root / f".archctl/native/{package}"
                prepare_evidence(self.root, self.snapshot, archctl=Path(os.environ["ARCHCTL_RELEASE_EXPORTER"]),
                                 briefcase=Path(os.environ["BRIEFCASE_BIN"]), destination=destination,
                                 source_roots=("src",))
                observed = read_evidence(destination / "evidence.json", self.snapshot)
                self.assertEqual(check_freshness(self.root, self.snapshot, observed), [])
                self.assertEqual({(edge.source, edge.target) for edge in observed.edges},
                                 {("orders", "payments"), ("payments", "ledger")})
                self.assertEqual(observed.coverage.status, "complete")
                # Rebuild the original fixture before testing the second layout.
                shutil.rmtree(self.root / "src")
                shutil.rmtree(self.root / "architecture")
                shutil.rmtree(self.root / "checks")
                initialize(self.root, demo=True)
