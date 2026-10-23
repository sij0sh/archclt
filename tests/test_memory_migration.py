"""Legacy memory records migrate once without changing their reasoning."""

import json
from pathlib import Path
import tempfile
import unittest

from archctl.core.contracts import version
from archctl.core.io import InputError, digest, write_text
from archctl.core.memory import parse_memory
from scripts.migrate_memory_v2 import migrate_file


def legacy_record():
    value = {"schema_version": "archctl.memory.v1", "id": "legacy-reason",
             "statement": "Keep the legacy statement", "rationale": "Keep the legacy rationale",
             "origin": "agent_inferred", "references": ["conversation:old"], "components": [],
             "paths": [], "topics": ["legacy"], "assumptions": [], "supersedes": [], "contradicts": [],
             "source_files": {}}
    value["revision"] = digest(value)
    return value


class MemoryMigrationTests(unittest.TestCase):
    def test_migration_changes_only_serialization_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-reason.json"
            original = legacy_record()
            write_text(path, json.dumps(original))
            self.assertTrue(migrate_file(path))
            migrated = json.loads(path.read_text())
            self.assertEqual(migrated["schema_version"], version("memory"))
            record = parse_memory(migrated)
            self.assertEqual(record.statement, original["statement"])
            self.assertEqual(record.rationale, original["rationale"])
            self.assertEqual(record.references, tuple(original["references"]))
            self.assertEqual(migrated["revision"], record.to_dict()["revision"])
            self.assertFalse(migrate_file(path))

    def test_tampered_legacy_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-reason.json"
            original = legacy_record()
            original["statement"] = "Changed after the revision was recorded"
            write_text(path, json.dumps(original))
            with self.assertRaisesRegex(InputError, "revision does not match"):
                migrate_file(path)
