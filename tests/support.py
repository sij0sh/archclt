from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tests.fixtures.evidence import build

from archctl.atlas.impact import build_impact
from archctl.core.compiler import compile_model
from archctl.core.io import load_document, write_text
from archctl.guard.evaluate import check
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from tests.fixtures.storefront import initialize


def split_model(root: Path) -> None:
    """Exercise the legacy authoring layout in focused compatibility tests."""
    architecture = root / "architecture"
    target = architecture / "model.yaml"
    document = load_document(target)
    system = {key: document.pop(key) for key in ("schema_version", "system_id", "name", "domains", "enforcement")
              if key in document}
    target.unlink()
    for section, value in {"system": system, **document}.items():
        content = value if section == "system" else {section: value}
        write_text(architecture / f"{section}.yaml", yaml.safe_dump(content, sort_keys=False))


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        initialize(self.root, demo=True)
        self.baseline = compile_model(self.root)

    def candidate(self):
        return compile_model(self.root)

    def evidence(self):
        return parse_evidence(build(self.root), self.candidate())

    def assess(self, *, bundle=None, execute=False, paths=None):
        snapshot = self.candidate()
        observations = bundle or self.evidence()
        fresh = lambda: check_freshness(self.root, snapshot, observations)
        impact = build_impact(snapshot, observations, paths or ["app/orders/api.py"], "Test task", fresh())
        return check(self.root, snapshot, self.baseline, observations, impact,
                     execute=execute, environment="test", freshness=fresh)
