import importlib.util
import json
from pathlib import Path
import sys
import unittest

from archctl.atlas.impact import build_impact
from archctl.atlas.reconcile import reconcile
from archctl.integrations.briefcase.adapter import check_freshness
from archctl.observatory.workflows import run_workflow
import yaml

from archctl.core.compiler import compile_model
from tests.support import ProjectTest, build
from tests.test_check_architecture import contract
from scripts.generate_schemas import make_schemas


@unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install .[dev] for JSON Schema conformance checks")
class ExchangeContractTests(ProjectTest):
    def validate(self, name, value, version="v2"):
        from jsonschema import Draft202012Validator
        schema_path = Path(__file__).resolve().parents[1] / "contracts" / version / f"{name}.schema.json"
        schema = json.loads(schema_path.read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)

    def test_all_exchange_outputs_conform_to_published_schemas(self):
        snapshot, observed = self.candidate(), self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observed)
        self.validate("snapshot", snapshot.to_dict())
        self.validate("change", contract())
        self.validate("evidence", build(self.root))
        self.validate("impact", build_impact(snapshot, observed, ["app/orders/api.py"], "Plan", []))
        self.validate("reconciliation", reconcile(snapshot, observed, []))
        report = self.assess(execute=True)
        self.validate("guard", report)
        for result in report["verification"]:
            self.validate("verification-result", result)
        self.validate("workflow-result", run_workflow(self.root, snapshot, self.baseline, observed,
                      "checkout", environment="test", freshness=fresh))
        self.validate("intent", {"schema_version": "archctl.intent.v2", "model_revision": snapshot.revision,
                                 "native_briefcase_format": False, "model": snapshot.model.to_dict()})

@unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install .[dev] for JSON Schema conformance checks")
class SelectiveContractTests(ProjectTest):
    def setUp(self):
        super().setUp()
        system = self.root / "architecture/model.yaml"
        value = yaml.safe_load(system.read_text())
        value.update(schema_version="archctl.authoring.v2", enforcement="selective")
        system.write_text(yaml.safe_dump(value, sort_keys=False))
        policies = self.root / "architecture/model.yaml"
        value = yaml.safe_load(policies.read_text())
        for policy in value["policies"]:
            policy["obligation"] = "required"
        policies.write_text(yaml.safe_dump(value, sort_keys=False))
        self.baseline = compile_model(self.root)

    def validate(self, name, value):
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/v2" / f"{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)

    def test_versioned_outputs_conform_to_v2_schemas(self):
        snapshot, observed = self.candidate(), self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observed)
        self.validate("snapshot", snapshot.to_dict())
        impact = build_impact(snapshot, observed, ["app/orders/api.py"], "Plan", [], all_components=True)
        self.validate("impact", impact)
        self.validate("reconciliation", reconcile(snapshot, observed, []))
        report = self.assess(execute=True)
        self.validate("guard", report)
        for result in report["verification"]:
            self.validate("verification-result", result)
        self.validate("intent", {"schema_version": "archctl.intent.v2", "model_revision": snapshot.revision,
                                 "native_briefcase_format": False, "model": snapshot.model.to_dict()})
        self.assertTrue(report["verification"])
        self.assertTrue(all(item["obligation"] == "required" for item in impact["verification"]))
        self.assertEqual(report["impact"]["unknown_details"], [])


class SchemaGenerationTests(unittest.TestCase):
    def test_generated_schemas_are_current(self):
        directory = Path(__file__).resolve().parents[1] / "contracts/v2"
        for name, expected in make_schemas().items():
            actual = json.loads((directory / f"{name}.schema.json").read_text())
            self.assertEqual(actual, expected, name)
