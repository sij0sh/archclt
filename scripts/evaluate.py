#!/usr/bin/env python3
"""Retain reproducible local-gate trials against an executable sample application.

These are automated fixture trials, not operator acceptance or native Briefcase
interoperability. Rebuilds use a deterministic Git baseline and exact source pins.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from archctl.core.io import write_json
from tests.fixtures.storefront import initialize
from tests.fixtures.evidence import build


def git(root, *arguments):
    environment = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00"}
    return subprocess.run(["git", "-C", str(root), *arguments], env=environment, check=True, capture_output=True, text=True).stdout.strip()


def change():
    return {"schema_version": "archctl.change.v2", "id": "checkout-trial", "objective": "Implement the trial's reviewed acceptance behavior",
            "scope": {"components": ["orders", "payments", "ledger"], "excluded_components": [], "paths": ["checks/**"]},
            "acceptance": [{"id": "AC-01", "requirement": "New checkout behavior and existing payment behavior pass real assertions",
                            "checks": ["checkout-integration", "payments-contract"]}],
            "constraints": {"decisions": ["ADR-001"], "policies": ["payment-isolation"]}, "open_questions": []}


def replace(root, rel, old, new):
    path = root / rel
    text = path.read_text()
    if old not in text:
        raise RuntimeError(f"Trial source did not match: {rel}")
    path.write_text(text.replace(old, new))


def refactor(root):
    replace(root, "app/orders/api.py", '"order:" + order_id', 'f"order:{order_id}"')


def validation(root, condition, value):
    replace(root, "app/orders/api.py", '    receipt =', f'    if {condition}:\n        raise ValueError("Invalid order ID")\n    receipt =')
    path = root / "checks/test_checkout.py"
    path.write_text(path.read_text() + f'''\nclass NewOrderIdContract(unittest.TestCase):
    def test_invalid_order_id_cannot_write(self):
        store.reset()
        with self.assertRaises(ValueError):
            checkout({value}, 1250)
        self.assertEqual(store.count(), 0)
''')


def run(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    # Preserve each evaluation as an immutable run, just like the local gate.
    run_directory = Path(tempfile.mkdtemp(prefix="run-", dir=destination))
    cases = [
        ("refactor-order-key", "passed", lambda root: refactor(root)),
        ("reject-empty-order", "passed", lambda root: validation(root, "not order_id", "''")),
        ("reject-whitespace-order", "passed", lambda root: validation(root, "not order_id.strip()", "'  '")),
        ("reject-non-string-order", "passed", lambda root: validation(root, "not isinstance(order_id, str)", "123")),
        ("bound-order-id-length", "passed", lambda root: validation(root, "len(order_id) > 128", "'x' * 129")),
        ("forbidden-import", "failed", lambda root: replace(root, "app/orders/api.py", "from app.payments", "from app.ledger import store\nfrom app.payments")),
        ("broken-checkout-behavior", "failed", lambda root: replace(root, "app/orders/api.py", '"status": receipt["status"]', '"status": "incorrect"')),
        ("undeclared-dependency", "unknown", lambda root: replace(root, "app/payments/service.py", "from app.ledger", "import app.orders.api\nfrom app.ledger")),
        ("stale-source", "unknown", lambda root: refactor(root)),
        ("partial-evidence", "unknown", lambda root: refactor(root)),
        ("outside-reviewed-scope", "unknown", lambda root: refactor(root)),
        ("unmapped-acceptance", "unknown", lambda root: refactor(root)),
        ("unexecuted-checks", "unknown", lambda root: refactor(root)),
        ("unapproved-authority", "unknown", lambda root: replace(root, "architecture/model.yaml", "name: Storefront", "name: Changed intent")),
        ("missing-check-reference", "error", lambda root: refactor(root)),
    ]
    results = []
    for name, expected, mutate in cases:
        case_directory = run_directory / name
        case_directory.mkdir()
        with tempfile.TemporaryDirectory(prefix="archctl-evaluation-") as temporary:
            root = Path(temporary)
            initialize(root, demo=True)
            (root / ".gitignore").write_text(".archctl/\n__pycache__/\n*.pyc\n")
            git(root, "init", "-q", "--initial-branch=main")
            git(root, "add", ".")
            git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "reviewed fixture baseline")
            sha = git(root, "rev-parse", "HEAD")
            baseline_evidence = build(root)
            mutate(root)
            task = change()
            task["objective"] = name.replace("-", " ")
            if name == "outside-reviewed-scope":
                task["scope"]["components"] = ["orders"]
            if name == "unmapped-acceptance":
                task["acceptance"][0]["checks"] = []
            if name == "missing-check-reference":
                task["acceptance"][0]["checks"] = ["missing"]
            evidence = baseline_evidence if name == "stale-source" else build(root)
            if name == "partial-evidence":
                evidence["coverage"].update(status="partial", gaps=["Controlled incomplete evidence"])
            write_json(root / ".archctl/evidence.json", evidence)
            (root / ".archctl/change.yaml").write_text(yaml.safe_dump(task))
            command = [sys.executable, "-m", "archctl", "--root", str(root), "gate", "--baseline-ref", sha,
                       "--change", ".archctl/change.yaml", "--evidence", ".archctl/evidence.json", "--no-briefcase"]
            if name != "unexecuted-checks":
                command.append("--run")
            process = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, timeout=120)
            output = json.loads(process.stdout or process.stderr)
            report = Path(output["report"])
            shutil.copytree(report, case_directory / "result")
            for directory in ("app", "checks", "architecture"):
                shutil.copytree(root / directory, case_directory / "candidate" / directory, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(root / ".archctl/change.yaml", case_directory / "change.yaml")
            diff = git(root, "diff", sha, "--", ".")
            (case_directory / "change.diff").write_text(diff + "\n")
            summary = json.loads((report / "gate-summary.json").read_text())
            actual = summary["status"]
            expected_exit = {"passed": 0, "failed": 1, "unknown": 2, "error": 3}[expected]
            results.append({"case": name, "expected": expected, "actual": actual, "exit": process.returncode,
                            "matched": actual == expected and process.returncode == expected_exit,
                            "baseline_sha": sha, "source_digest": summary.get("source_digest"),
                            "report": (case_directory / "result/gate-summary.json").relative_to(ROOT / "validation").as_posix()})
    return {"schema_version": "archctl.evaluation.v2", "status": "passed" if all(r["matched"] for r in results) else "failed",
            "run_directory": run_directory.relative_to(ROOT / "validation").as_posix(),
            "cases": results, "limitations": ["Fixture-only Python import exporter, not native Briefcase interoperability",
            "Five positive code-and-test trials are automated, not independent operator acceptance",
            "Evaluator tampering and additional input mutations are covered by the unit regression suite"]}


def main() -> int:
    try:
        report = run(ROOT / ".archctl/evaluation")
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        report = {"schema_version": "archctl.evaluation.v2", "status": "failed",
                  "run_directory": None, "cases": [], "error": str(exc),
                  "limitations": ["The evaluation stopped before a complete report was produced"]}
    write_json(ROOT / ".archctl/evaluation.json", report)
    cases = report.get("cases", [])
    print(json.dumps({"status": report["status"], "matched": sum(r.get("matched", False) for r in cases),
                      "total": len(cases), "error": report.get("error")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
