#!/usr/bin/env python3
"""Prove pass, violation, stale evidence, and unreviewed authority outcomes."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archctl.atlas.impact import build_impact
from archctl.core.compiler import compile_model
from archctl.core.io import write_json
from archctl.guard.evaluate import check
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from tests.fixtures.storefront import initialize
from tests.fixtures.evidence import build


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="archctl-demo-") as tmp:
        root = Path(tmp)
        initialize(root, demo=True)
        baseline = compile_model(root)
        def assess(bundle: dict, run: bool = True) -> dict:
            candidate = compile_model(root)
            observed = parse_evidence(bundle, candidate)
            fresh = lambda: check_freshness(root, candidate, observed)
            impact = build_impact(candidate, observed, ["app/orders/api.py"], "Change checkout", fresh())
            return check(root, candidate, baseline, observed, impact, execute=run, environment="demo", freshness=fresh)
        valid_bundle = build(root)
        valid = assess(valid_bundle)
        path = root / "app/orders/api.py"
        original = path.read_text()
        path.write_text("from app.ledger import store\n" + original)
        stale = assess(valid_bundle)
        violation_bundle = build(root)
        violation = assess(violation_bundle)
        policy = root / "architecture/model.yaml"
        original_policy = policy.read_text()
        policy.write_text(original_policy.replace("obligation: required", "obligation: advisory"))
        weakened = assess(violation_bundle)
        cases = {"valid_change": valid, "stale_evidence": stale,
                 "forbidden_dependency": violation, "weakened_policy": weakened}
        expected = {"valid_change": "passed", "stale_evidence": "unknown",
                    "forbidden_dependency": "failed", "weakened_policy": "unknown"}
        output = {name: {"expected": expected[name], "actual": report["status"],
                         "verification": {r["id"]: r["status"] for r in report["verification"]},
                         "authority_changed": report["authority_changed"]} for name, report in cases.items()}
        print(json.dumps(output, indent=2))
        if len(sys.argv) > 1:
            write_json(Path(sys.argv[1]).resolve(), {"summary": output, "reports": cases})
        return 0 if all(report["status"] == expected[name] for name, report in cases.items()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
