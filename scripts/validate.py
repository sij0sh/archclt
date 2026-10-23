#!/usr/bin/env python3
"""Run regressions, build a wheel, and exercise the installed package offline."""

from __future__ import annotations

import io
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from archctl import __version__
from archctl.core.compiler import compile_model
from archctl.core.io import file_digest, write_json, write_text


def command(argv: list[str], *, env: dict | None = None,
            expected: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True)
    if result.returncode not in expected:
        raise RuntimeError(f"Command failed ({result.returncode}): {argv}\n{result.stdout}\n{result.stderr}")
    return result


def selective_smoke(app: Path, cli: list[str], env: dict) -> dict:
    """Review opt-in selective intent, then add an advisory forbidden edge."""
    model = app / "architecture/model.yaml"
    value = yaml.safe_load(model.read_text())
    value.update(schema_version="archctl.authoring.v2", enforcement="selective")
    for policy in value["policies"]:
        policy["obligation"] = "advisory" if policy["id"] == "payment-isolation" else "required"
    model.write_text(yaml.safe_dump(value, sort_keys=False))
    command(["git", "-C", str(app), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "commit", "-qam", "review selective v2 intent"])
    sha = command(["git", "-C", str(app), "rev-parse", "HEAD"]).stdout.strip()
    source = app / "app/orders/api.py"
    source.write_text("from app.ledger import store\n" + source.read_text())
    command([sys.executable, "tests/fixtures/evidence.py", str(app)], env=env)
    gate = json.loads(command([*cli, "gate", "--baseline-ref", sha, "--change", ".archctl/change.json",
                              "--evidence", ".archctl/evidence.json", "--run"], env=env).stdout)
    summary = json.loads((Path(gate["report"]) / "gate-summary.json").read_text())
    finding = next((f for f in summary["findings"] if f["id"] == "payment-isolation"), {})
    if (summary["schema_version"] != "archctl.gate.v2" or summary["status"] != "passed"
            or (finding.get("status"), finding.get("obligation")) != ("failed", "advisory")):
        raise RuntimeError("Installed package did not retain the advisory selective outcome")
    return {"local_gate": summary["status"], "schema_version": summary["schema_version"],
            "advisory_finding": finding["status"]}


def installed_smoke(wheel: Path) -> dict:
    temporary = ROOT / ".archctl"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-smoke-", dir=temporary) as tmp:
        directory = Path(tmp)
        target, app = directory / "site-packages", directory / "application"
        command([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir",
                 "--disable-pip-version-check", "--target", str(target), str(wheel)])
        env = {**os.environ, "PYTHONPATH": str(target)}
        imported = command([sys.executable, "-c", "import archctl; print(archctl.__file__)"], env=env).stdout.strip()
        if not Path(imported).is_relative_to(target):
            raise RuntimeError("Package smoke accidentally imported the checkout instead of the wheel")
        cli = [sys.executable, "-m", "archctl", "--root", str(app)]
        from tests.fixtures.storefront import initialize
        initialize(app, demo=True)
        command([*cli, "model", "compile", "--out", ".archctl/approved.lock.json"], env=env)
        command([sys.executable, "tests/fixtures/evidence.py", str(app)], env=env)
        neutral = directory / "neutral-application"
        neutral_cli = [sys.executable, "-m", "archctl", "--root", str(neutral)]
        command([*neutral_cli, "init"], env=env)
        neutral_status = json.loads(command([*neutral_cli, "status", "--format", "json"], env=env,
                                            expected=(0, 2)).stdout)
        if (neutral_status.get("model", {}).get("state") != "valid"
                or neutral_status.get("status") != "needs_attention"):
            raise RuntimeError("Installed package did not report a neutral scaffold as a valid, unready model")
        status = json.loads(command([*cli, "status", "--drift", "--format", "json"], env=env).stdout)
        impact = json.loads(command([*cli, "impact", "Installed-package change", "--paths", "app/orders/api.py",
                                     "--evidence", ".archctl/evidence.json"], env=env).stdout)
        guard = json.loads(command([*cli, "guard", "check", "--baseline", ".archctl/approved.lock.json",
                                    "--evidence", ".archctl/evidence.json", "--run"], env=env).stdout)
        workflow = json.loads(command([*cli, "observe", "run", "checkout", "--baseline", ".archctl/approved.lock.json",
                                       "--evidence", ".archctl/evidence.json"], env=env).stdout)
        report = command([*cli, "report", "--evidence", ".archctl/evidence.json"], env=env).stdout
        # Exercise the supported gate from the installed wheel against a real
        # application Git baseline, not repository scripts or a candidate tool.
        (app / ".gitignore").write_text(".archctl/\n__pycache__/\n*.pyc\n")
        for arguments in (("init", "-q"), ("add", "."),
                          ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "reviewed application")):
            command(["git", "-C", str(app), *arguments])
        sha = command(["git", "-C", str(app), "rev-parse", "HEAD"]).stdout.strip()
        source = app / "app/orders/api.py"
        source.write_text(source.read_text().replace('"order:" + order_id', 'f"order:{order_id}"'))
        write_json(app / ".archctl/change.json", {
            "schema_version": "archctl.change.v2", "id": "installed-trial", "objective": "Preserve checkout while refactoring its key",
            "scope": {"components": ["orders", "payments", "ledger"]},
            "acceptance": [{"id": "AC-01", "requirement": "Checkout stays idempotent", "checks": ["checkout-integration"]}],
            "constraints": {"decisions": ["ADR-001"], "policies": ["payment-isolation"]}, "open_questions": []})
        command([sys.executable, "tests/fixtures/evidence.py", str(app)], env=env)
        preparation = {"status": "not_executed", "reason": "Reviewed v2 exporter and Briefcase are not configured"}
        if env.get("ARCHCTL_RELEASE_EXPORTER") and env.get("BRIEFCASE_BIN"):
            prepared = json.loads(command([*cli, "briefcase", "prepare-evidence",
                "--archctl", env["ARCHCTL_RELEASE_EXPORTER"], "--briefcase", env["BRIEFCASE_BIN"],
                "--source-root", ".", "--out-dir", ".archctl/prepared/installed"], env=env).stdout)
            manifest = json.loads(Path(prepared["manifest"]).read_text())
            if manifest["status"] != "prepared" or not Path(prepared["output"]).is_file():
                raise RuntimeError("Installed preparation did not publish independently produced evidence")
            preparation = {"status": manifest["status"], "pins": len(manifest["source"]["component_files"]),
                           "source_revision": manifest["source_revision"]}
        gate = json.loads(command([*cli, "gate", "--baseline-ref", sha, "--change", ".archctl/change.json",
                                  "--evidence", ".archctl/evidence.json", "--run"], env=env).stdout)
        if (status.get("schema_version") != "archctl.status.v2" or status.get("status") != "ready"
                or status.get("drift", {}).get("state") != "clean"
                or impact["assessment"] != "complete" or guard["status"] != "passed"
                or workflow["status"] != "passed" or gate["status"] != "passed" or "## Reconciliation" not in report):
            raise RuntimeError("Installed package did not complete the expected workflow")
        selective = selective_smoke(app, cli, env)
        return {"scoped_preparation": preparation, "selective_v2": selective, "status": "passed",
                "neutral_status": neutral_status["status"], "isolated_import": True,
                "status_contract": status["status"],
                "impact": impact["assessment"], "guard": guard["status"], "workflow": workflow["status"],
                "local_gate": gate["status"], "evaluator_source": "installed wheel",
                "markdown_report": True,
                "verification": {r["id"]: r["status"] for r in guard["verification"]}}


def main() -> int:
    destination = ROOT / ".archctl/validation"
    destination.mkdir(parents=True, exist_ok=True)
    missing = [name for name in ("jsonschema", "setuptools", "wheel") if importlib.util.find_spec(name) is None]
    if missing:
        summary = {"status": "error", "stage": "dependencies", "missing": missing,
                   "schema_conformance": "not_executed",
                   "error": "Release validation requires all .[dev] dependencies in the verification environment"}
        write_json(destination / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 1
    os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
    log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    write_text(destination / "tests.log", log.getvalue())
    native_skips = [item for item in result.skipped if "test_briefcase_native" in str(item[0])]
    summary = {"python": platform.python_version(), "tests": {
        "run": result.testsRun, "passed": result.testsRun - len(result.skipped) - len(result.failures) - len(result.errors),
        "failed": len(result.failures), "errors": len(result.errors),
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped]},
        "schema_conformance": "not_executed" if any("JSON Schema" in reason for _, reason in result.skipped) else "passed",
        "native_briefcase_interoperability": "not_executed: pinned interoperability tools unavailable" if native_skips
        else "passed"}
    stage = "tests"
    if not result.wasSuccessful():
        summary.update(status="failed", stage=stage)
        write_json(destination / "summary.json", summary)
        print(log.getvalue())
        return 1
    try:
        stage = "demo"
        command([sys.executable, "scripts/demo.py", str(destination / "demo-results.json")])
        stage = "model-lock"
        write_json(destination / "model.lock.json", compile_model(ROOT).to_dict())
        stage = "wheel"
        for path in (ROOT / "dist").glob(f"archclt-{__version__}-*.whl"):
            path.unlink()
        build = command([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-build-isolation", "--no-deps",
                         "--no-cache-dir", "--disable-pip-version-check", "--wheel-dir", "dist", "."])
        write_text(destination / "build.log", build.stdout + build.stderr)
        wheels = sorted((ROOT / "dist").glob(f"archclt-{__version__}-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one built wheel, found {len(wheels)}")
        wheel = wheels[0]
        summary["wheel"] = {"filename": wheel.name, "sha256": file_digest(wheel), "bytes": wheel.stat().st_size}
        stage = "installed-smoke"
        summary["installed_package_smoke"] = installed_smoke(wheel)
        summary["demo"] = {name: case["actual"] for name, case in
                           json.loads((destination / "demo-results.json").read_text())["summary"].items()}
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        summary.update(status="failed", stage=stage, error=str(exc))
        write_json(destination / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 1
    summary["stage"] = "complete"
    summary["status"] = "passed_with_optional_checks_unavailable" if result.skipped else "passed"
    write_json(destination / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
