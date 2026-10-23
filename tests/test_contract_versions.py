"""All public schema families use one version label."""

import json
from pathlib import Path
import re
import unittest

from archctl.core.contracts import VERSION, version
from scripts.generate_context_schemas import make_schemas as make_context_schemas
from scripts.generate_schemas import make_schemas as make_exchange_schemas


class ContractVersionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_one_version_is_used_for_every_published_schema(self):
        paths = sorted((self.root / "contracts").glob("**/*.schema.json"))
        self.assertGreater(len(paths), 0)
        for path in paths:
            schema = json.loads(path.read_text())
            self.assertIn(f":{VERSION}:", schema["$id"], path)
            self.assertNotRegex(path.read_text(), r"archctl\.[a-z-]+\.v1", path)

    def test_advisory_contract_directory_follows_the_shared_version(self):
        self.assertTrue((self.root / f"contracts/context/{VERSION}").is_dir())
        self.assertFalse((self.root / "contracts/context/v1").exists())
        self.assertEqual(set(make_context_schemas()), {"context", "context-config", "execution", "memory"})
        self.assertEqual(version("memory"), f"archctl.memory.{VERSION}")

    def test_generators_use_the_shared_version_constant(self):
        for name, schema in {**make_exchange_schemas(), **make_context_schemas()}.items():
            self.assertIn(f":{VERSION}:", schema["$id"])
            self.assertNotRegex(json.dumps(schema), r"archctl\.[a-z-]+\.v1")
            if "schema_version" in schema.get("properties", {}):
                self.assertEqual(schema["properties"]["schema_version"], {"const": f"archctl.{name}.{VERSION}"})
