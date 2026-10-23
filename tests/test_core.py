from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
import tempfile

import yaml

from archctl.core.compiler import compile_model, parse_model, read_snapshot
from archctl.core.io import (InputError, contained, load_document, matches, source_files, write_json,
                             write_text)
from tests.fixtures.storefront import initialize
from tests.support import ProjectTest, split_model


class CompilerTests(ProjectTest):
    def test_reproducible_and_movable_snapshot(self):
        self.assertEqual(self.baseline, self.candidate())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialize(root, demo=True)
            self.assertEqual(self.baseline, compile_model(root))
        path = self.root / "snapshot.json"
        write_json(path, self.baseline.to_dict())
        self.assertEqual(read_snapshot(path), self.baseline)

    def test_legacy_authoring_normalizes_once_to_v2(self):
        from archctl.core.migration import migrate_document
        document = load_document(self.root / "architecture/model.yaml")
        document["schema_version"] = "archctl.authoring.v1"
        document.pop("enforcement")
        for policy in document["policies"]:
            policy.pop("obligation")
        migrated = migrate_document(document)
        self.assertEqual(migrated["enforcement"], "strict")
        self.assertTrue(all(p["obligation"] == "required" for p in migrated["policies"]))
        write_text(self.root / "architecture/model.yaml", yaml.safe_dump(document))
        self.assertEqual(self.candidate().model, self.baseline.model)
        self.assertEqual(self.candidate().to_dict()["schema_version"], "archctl.snapshot.v2")
        document["policies"][0]["severity"] = "warning"
        document["policies"][1]["severity"] = "warning"
        migrated = migrate_document(document)
        self.assertEqual([p["obligation"] for p in migrated["policies"]], ["advisory", "required"])

    def test_legacy_split_authoring_has_the_same_normalized_obligations(self):
        path = self.root / "architecture/model.yaml"
        document = load_document(path)
        document["schema_version"] = "archctl.authoring.v1"
        document.pop("enforcement")
        for policy in document["policies"]:
            policy.pop("obligation")
        write_text(path, yaml.safe_dump(document))
        split_model(self.root)
        self.assertEqual(self.candidate().model, self.baseline.model)

    def test_obligations_and_modes_require_explicit_valid_values(self):
        path = self.root / "architecture/model.yaml"
        document = load_document(path)
        document["enforcement"] = "silently-ignore-errors"
        write_text(path, yaml.safe_dump(document))
        with self.assertRaisesRegex(InputError, "system.enforcement"):
            compile_model(self.root)
        document["enforcement"] = "strict"
        document["policies"][0].pop("obligation")
        write_text(path, yaml.safe_dump(document))
        with self.assertRaisesRegex(InputError, "policy.obligation"):
            compile_model(self.root)

    def test_split_layout_compiles_to_the_same_model(self):
        split_model(self.root)
        snapshot = compile_model(self.root)
        self.assertEqual(snapshot.model, self.baseline.model)
        self.assertIn("architecture/system.yaml", dict(snapshot.sources))
        write_text(self.root / "architecture/model.yaml", "schema_version: archctl.authoring.v2\n")
        with self.assertRaisesRegex(InputError, "cannot be combined"):
            compile_model(self.root)

    def test_model_file_rejects_unknown_sections_and_missing_system(self):
        path = self.root / "architecture/model.yaml"
        merged = load_document(path)
        write_text(path, yaml.safe_dump({**merged, "rules": []}))
        with self.assertRaisesRegex(InputError, "unknown keys"):
            compile_model(self.root)
        path.unlink()
        with self.assertRaisesRegex(InputError, "Missing architecture/model.yaml"):
            compile_model(self.root)

    def test_policy_targets_expand_to_one_policy_per_target(self):
        path = self.root / "architecture/model.yaml"
        document = load_document(path)
        isolation = document["policies"][0]
        compact = {**isolation, "id": "orders-isolation", "targets": ["ledger"]}
        del compact["target"]
        document["policies"][0] = compact
        write_text(path, yaml.safe_dump(document, sort_keys=False))
        policy = next(p for p in compile_model(self.root).model.policies if p.kind == "forbidden_dependency")
        expected = next(p for p in self.baseline.model.policies if p.id == "payment-isolation")
        self.assertEqual(policy.id, "orders-isolation-ledger")
        self.assertEqual(dataclasses.replace(policy, id=expected.id), expected)
        for bad, message in (({"targets": []}, "unique nonempty"),
                             ({"targets": ["ledger", "ledger"]}, "unique nonempty"),
                             ({"targets": ["ledger"], "target": "ledger"}, "no target"),
                             ({"targets": ["ledger"], "kind": "required_verification"}, "forbidden_dependency"),
                             ({"targets": ["missing"]}, "unknown components")):
            with self.subTest(bad=bad):
                document["policies"][0] = {**compact, **bad}
                write_text(path, yaml.safe_dump(document, sort_keys=False))
                with self.assertRaisesRegex(InputError, message):
                    compile_model(self.root)

    def test_snapshot_rejects_legacy_wire_version_and_unknown_enforcement(self):
        data = self.baseline.to_dict()
        data["schema_version"] = "archctl.snapshot.v1"
        path = self.root / "snapshot.json"
        write_json(path, data)
        with self.assertRaisesRegex(InputError, "archctl.snapshot.v2"):
            read_snapshot(path)
        data = self.baseline.to_dict()
        data["model"]["enforcement"] = "selective-v2"
        write_json(path, data)
        with self.assertRaisesRegex(InputError, "model.enforcement"):
            read_snapshot(path)

    def test_rationale_changes_snapshot(self):
        path = self.root / "architecture/decisions/ADR-001.md"
        path.write_text(path.read_text() + "\nAdditional rationale.\n")
        self.assertNotEqual(self.baseline.revision, self.candidate().revision)

    def test_invalid_references_and_unknown_keys(self):
        data = self.baseline.model.to_dict()
        data["components"][0]["domain"] = "missing"
        with self.assertRaisesRegex(InputError, "unknown domains"):
            parse_model(data)
        data = self.baseline.model.to_dict()
        data["policies"][0]["accidental_typo"] = True
        with self.assertRaisesRegex(InputError, "unknown keys"):
            parse_model(data)

    def test_unapproved_decision_cannot_govern(self):
        data = self.baseline.model.to_dict()
        data["decisions"][0]["status"] = "proposed"
        with self.assertRaisesRegex(InputError, "accepted or deprecated"):
            parse_model(data)

    def test_supersession_requires_correct_lifecycle(self):
        data = self.baseline.model.to_dict()
        old = copy.deepcopy(data["decisions"][0])
        old.update(id="ADR-000", status="superseded", supersedes=[])
        data["decisions"][0]["supersedes"] = ["ADR-000"]
        data["decisions"].append(old)
        self.assertEqual(len(parse_model(data).decisions), 2)
        data["decisions"][0]["supersedes"] = []
        with self.assertRaisesRegex(InputError, "exactly one"):
            parse_model(data)

    def test_cycle_and_rule_contradiction_rejected(self):
        data = self.baseline.model.to_dict()
        first = data["decisions"][0]
        first.update(status="superseded", supersedes=["ADR-002"])
        second = copy.deepcopy(first)
        second.update(id="ADR-002", supersedes=["ADR-001"])
        data["decisions"].append(second)
        with self.assertRaisesRegex(InputError, "cycle"):
            parse_model(data)
        data = self.baseline.model.to_dict()
        policy = next(p for p in data["policies"] if p["kind"] == "forbidden_dependency")
        policy["target"] = "payments"
        with self.assertRaisesRegex(InputError, "contradicts"):
            parse_model(data)

    def test_duplicate_keys_and_ids_rejected(self):
        path = self.root / "bad.yaml"
        path.write_text("id: one\nid: two\n")
        with self.assertRaisesRegex(InputError, "unique strings"):
            load_document(path)
        path = self.root / "bad.json"
        path.write_text('{"id":"one","id":"two"}')
        with self.assertRaisesRegex(InputError, "Duplicate JSON"):
            load_document(path)
        data = self.baseline.model.to_dict()
        data["components"].append(data["components"][0])
        with self.assertRaisesRegex(InputError, "Duplicate identifier"):
            parse_model(data)

    def test_snapshot_tampering_is_detected(self):
        data = self.baseline.to_dict()
        data["model"]["name"] = "Changed without recomputing revision"
        path = self.root / "snapshot.json"
        write_json(path, data)
        with self.assertRaisesRegex(InputError, "integrity"):
            read_snapshot(path)

    def test_unsafe_paths_and_command_types_rejected(self):
        data = self.baseline.model.to_dict()
        data["components"][0]["paths"] = ["../secrets/**"]
        with self.assertRaisesRegex(InputError, "escapes"):
            parse_model(data)
        data = self.baseline.model.to_dict()
        data["verification"][0]["command"] = "echo shell"
        with self.assertRaisesRegex(InputError, "list"):
            parse_model(data)
        data["verification"][0]["command"] = ["python3"]
        data["verification"][0]["timeout_seconds"] = True
        with self.assertRaisesRegex(InputError, "integer"):
            parse_model(data)

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (self.root / "escape").symlink_to(tmp, target_is_directory=True)
            with self.assertRaisesRegex(InputError, "Symlink escapes"):
                contained(self.root, "escape/file")

    def test_glob_segment_semantics(self):
        self.assertTrue(matches("app/orders/api.py", "app/orders/**"))
        self.assertTrue(matches("app/orders/api.py", "app/**/*.py"))
        self.assertTrue(matches("app/a/b/c.py", "app/**/*.py"))
        self.assertFalse(matches("app/a/b/c.py", "app/*/*.py"))

    def test_init_never_overwrites(self):
        path = self.root / "app/orders/api.py"
        original = path.read_text()
        with self.assertRaisesRegex(InputError, "overwrite"):
            initialize(self.root, demo=True)
        self.assertEqual(path.read_text(), original)

    def test_source_inventory_ignores_only_paths_below_repository_root(self):
        nested = self.root / ".archctl" / "nested-application"
        initialize(nested, demo=True)
        files = source_files(nested, ("app/**",))
        self.assertIn("app/orders/api.py", files)
        self.assertIn("app/ledger/store.py", files)
