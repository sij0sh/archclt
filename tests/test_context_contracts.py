"""Advisory contracts are reproducible and actual CLI outputs match their schemas."""

import importlib.util
import json
from pathlib import Path
import unittest

from scripts.generate_context_schemas import make_schemas
import tests.test_context as context_support
from archctl.core.memory import remember
from archctl.integrations.verification import run


class ContextSchemaGenerationTests(unittest.TestCase):
    def test_published_schemas_match_the_generator(self):
        root = Path(__file__).resolve().parents[1] / "contracts/context/v1"
        for name, schema in make_schemas().items():
            self.assertEqual(json.loads((root / f"{name}.schema.json").read_text()), schema)


@unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install .[dev] for advisory JSON Schema conformance checks")
class ContextSchemaConformanceTests(unittest.TestCase):
    cli = context_support.ContextWorkflowTests.cli

    def setUp(self):
        context_support.ContextWorkflowTests.setUp(self)

    def test_actual_context_memory_and_execution_outputs_conform(self):
        from jsonschema import Draft202012Validator
        schemas = make_schemas()
        memory = remember(self.root, context_support.note())
        execution = run(self.root, ["python3", "-c", "pass"], task="batch", paths=["src/api/batching.py"])
        context = self.cli("context", "batching")
        for name, value in (("memory", memory.to_dict()), ("execution", execution), ("context", context)):
            Draft202012Validator.check_schema(schemas[name])
            Draft202012Validator(schemas[name]).validate(value)
