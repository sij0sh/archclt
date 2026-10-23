from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from archctl.atlas.change_scope import apply_change
from archctl.atlas.impact import build_impact
from archctl.core.change import parse_change
from archctl.core.compiler import compile_model
from archctl.core.io import InputError, load_document
from archctl.templates import initialize
from tests.support import ProjectTest
from tests.test_check_architecture import contract


class ChangeContractTests(ProjectTest):
    def test_roundtrip_and_immutable_criteria(self):
        change = parse_change(contract(), self.baseline)
        self.assertEqual(parse_change(change.to_dict(), self.baseline), change)
        self.assertEqual(change.revision, parse_change(copy.deepcopy(contract()), self.baseline).revision)
        with self.assertRaises(AttributeError):
            change.acceptance[0].checks += ("new",)

    def test_strict_references_fields_and_scope(self):
        cases = [lambda c: c.update(approved=True),
                 lambda c: c["scope"].update(components=["missing"]),
                 lambda c: c["scope"].update(excluded_components=["orders", "payments", "ledger"]),
                 lambda c: c["scope"].update(paths=["../escape/**"]),
                 lambda c: c["constraints"].update(decisions=["ADR-MISSING"]),
                 lambda c: c["constraints"].update(policies=["missing"]),
                 lambda c: c.update(acceptance=[]),
                 lambda c: c["acceptance"].append(c["acceptance"][0]),
                 lambda c: c["acceptance"][0].update(checks=["missing"])]
        for edit in cases:
            value = contract(); edit(value)
            with self.subTest(value=value), self.assertRaises(InputError):
                parse_change(value, self.baseline)

    def test_excluded_components_subtract_from_allowed_scope(self):
        value = contract()
        value["scope"].update(components=["orders", "payments", "ledger"],
                              excluded_components=["ledger"])
        change = parse_change(value, self.baseline)
        self.assertEqual(change.allowed_components, ("orders", "payments"))
        impact = build_impact(self.baseline, self.evidence(), ["app/ledger/store.py"], "excluded scope", [])
        result = apply_change(change, self.baseline, self.baseline, impact)
        self.assertTrue(any("outside reviewed change scope: ledger" in gap for gap in result["unknowns"]))

    def test_contract_adds_obligations_not_just_existing_policy_checks(self):
        impact = build_impact(self.baseline, self.evidence(), ["app/orders/api.py"], "task", [])
        value = contract()
        self.assertEqual(apply_change(parse_change(value, self.baseline), self.baseline, self.baseline, impact)["assessment"], "complete")
        value["acceptance"][0]["checks"] = []
        result = apply_change(parse_change(value, self.baseline), self.baseline, self.baseline, impact)
        self.assertEqual(result["assessment"], "partial")
        self.assertIn("Acceptance criterion has no verification: AC-01", result["unknowns"])

    def test_default_init_is_neutral_and_unready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root)
            snapshot = compile_model(root)
            self.assertEqual(snapshot.model.components, ())
            self.assertEqual(snapshot.model.decisions, ())
            self.assertEqual(snapshot.model.verification, ())
            self.assertEqual(snapshot.model.domains, ())
            self.assertIn("Unreviewed", snapshot.model.name)
            self.assertFalse((root / "app").exists())
            self.assertEqual([p.name for p in (root / "architecture").glob("*.yaml")], ["model.yaml"])
