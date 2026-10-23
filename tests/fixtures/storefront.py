"""Development-only executable Storefront fixture."""

from __future__ import annotations

from pathlib import Path
import textwrap

import yaml

from archctl.core.io import InputError, contained, write_text


def starter_files(*, demo: bool) -> dict[str, str]:
    if not demo:
        model = {"schema_version": "archctl.authoring.v2", "enforcement": "strict", "system_id": "application",
                 "name": "Unreviewed application scaffold", "domains": [],
                 **{name: [] for name in ("components", "relationships", "interfaces", "policies", "verification", "workflows")}}
        return {"architecture/model.yaml": yaml.safe_dump(model, sort_keys=False)}
    decisions = "ADR-001"
    documents = {
        "system": {"schema_version": "archctl.authoring.v2", "enforcement": "strict", "system_id": "storefront", "name": "Storefront",
                   "domains": [{"id": "commerce", "name": "Commerce", "owners": ["commerce-team"]},
                               {"id": "finance", "name": "Finance", "owners": ["finance-team"]}]},
        "components": {"components": [
            {"id": "orders", "name": "Orders", "domain": "commerce", "kind": "service", "paths": ["app/orders/**"]},
            {"id": "payments", "name": "Payments", "domain": "finance", "kind": "service", "paths": ["app/payments/**"]},
            {"id": "ledger", "name": "Payment ledger", "domain": "finance", "kind": "database", "paths": ["app/ledger/**"]}]},
        "relationships": {"relationships": [
            {"id": "orders-payments", "source": "orders", "target": "payments", "kind": "imports", "decision": decisions, "required": True},
            {"id": "payments-ledger", "source": "payments", "target": "ledger", "kind": "imports", "decision": decisions, "required": True}]},
        "interfaces": {"interfaces": [{"id": "payments-api", "provider": "payments", "consumers": ["orders"],
                                       "verification": ["payments-contract"], "decision": decisions}]},
        "policies": {"policies": [
            {"id": "payment-isolation", "kind": "forbidden_dependency", "source": "orders", "target": "ledger",
             "kinds": ["imports"], "decision": decisions, "severity": "error", "obligation": "required"},
            {"id": "finance-verification", "kind": "required_verification", "components": ["payments", "ledger"],
             "checks": ["payments-contract", "checkout-integration"], "decision": decisions, "severity": "error", "obligation": "required"}]},
        "verification": {"verification": [
            {"id": "payments-contract", "kind": "contract", "command": ["python3", "-m", "unittest", "checks.test_contract"],
             "cwd": ".", "timeout_seconds": 20, "components": ["orders", "payments", "ledger"]},
            {"id": "checkout-integration", "kind": "integration", "command": ["python3", "-m", "unittest", "checks.test_checkout"],
             "cwd": ".", "timeout_seconds": 20, "components": ["orders", "payments", "ledger"]}]},
        "workflows": {"workflows": [{"id": "checkout", "participants": ["orders", "payments", "ledger"],
                                     "verification": ["checkout-integration"], "decision": decisions}]},
    }
    model = dict(documents.pop("system"))
    for section in documents.values():
        model.update(section)
    result = {"architecture/model.yaml": yaml.safe_dump(model, sort_keys=False)}
    result["architecture/decisions/ADR-001.md"] = textwrap.dedent('''\
        ---
        id: ADR-001
        title: Centralize payment state changes
        status: accepted
        components: [orders, payments, ledger]
        supersedes: []
        ---
        # Centralize payment state changes

        ## Decision
        Orders requests payments through Payments. Only Payments imports the ledger.

        ## Rationale
        One owner of payment writes preserves idempotency, auditability, and reconciliation.

        ## Alternatives
        Direct ledger access from Orders would reduce a local call but distribute payment invariants.

        ## Revisit when
        An approved replacement defines equivalent ownership and migration guarantees.
        ''')
    for package in ("app", "app/orders", "app/payments", "app/ledger", "checks"):
        result[f"{package}/__init__.py"] = ""
    result["app/ledger/store.py"] = textwrap.dedent('''\
        _entries = {}

        def reset():
            _entries.clear()

        def record(key, amount):
            existing = _entries.get(key)
            if existing is not None and existing != amount:
                raise ValueError("Idempotency key reused with a different amount")
            _entries[key] = amount
            return {"id": key, "amount": amount, "status": "paid"}

        def count():
            return len(_entries)
        ''')
    result["app/payments/service.py"] = textwrap.dedent('''\
        from app.ledger import store

        def pay(key, amount):
            if not isinstance(key, str) or not key:
                raise ValueError("A payment key is required")
            if type(amount) is not int or amount <= 0:
                raise ValueError("Amount must be a positive integer in cents")
            return store.record(key, amount)
        ''')
    result["app/orders/api.py"] = textwrap.dedent('''\
        from app.payments import service

        def checkout(order_id, amount):
            receipt = service.pay("order:" + order_id, amount)
            return {"order_id": order_id, "payment_id": receipt["id"], "status": receipt["status"]}
        ''')
    result["checks/test_contract.py"] = textwrap.dedent('''\
        import unittest
        from app.payments.service import pay
        from app.ledger import store

        class PaymentContract(unittest.TestCase):
            def setUp(self):
                store.reset()

            def test_result_contract_and_idempotency(self):
                expected = {"id": "key", "amount": 1250, "status": "paid"}
                self.assertEqual(pay("key", 1250), expected)
                self.assertEqual(pay("key", 1250), expected)
                self.assertEqual(store.count(), 1)
                with self.assertRaises(ValueError):
                    pay("key", 500)

            def test_invalid_input_does_not_write(self):
                for amount in (0, -1, True, 1.5):
                    with self.assertRaises(ValueError):
                        pay("key", amount)
                self.assertEqual(store.count(), 0)
        ''')
    result["checks/test_checkout.py"] = textwrap.dedent('''\
        import unittest
        from app.orders.api import checkout
        from app.ledger import store

        class CheckoutWorkflow(unittest.TestCase):
            def setUp(self):
                store.reset()

            def test_checkout_succeeds_once(self):
                expected = {"order_id": "123", "payment_id": "order:123", "status": "paid"}
                self.assertEqual(checkout("123", 1250), expected)
                self.assertEqual(checkout("123", 1250), expected)
                self.assertEqual(store.count(), 1)

            def test_failure_does_not_write(self):
                with self.assertRaises(ValueError):
                    checkout("123", -1)
                self.assertEqual(store.count(), 0)
        ''')
    return result


def initialize(root: Path, *, demo: bool = False) -> list[str]:
    planned = starter_files(demo=demo)
    root.mkdir(parents=True, exist_ok=True)
    destinations = {rel: contained(root, rel) for rel in planned}
    collisions = [rel for rel, path in destinations.items() if path.exists()]
    if collisions:
        raise InputError(f"Refusing to overwrite existing files: {', '.join(collisions)}")
    for rel, text in planned.items():
        write_text(destinations[rel], text)
    return sorted(planned)
