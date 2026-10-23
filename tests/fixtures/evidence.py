#!/usr/bin/env python3
"""Fixture-only static import exporter. Not a replacement for Briefcase.

This exporter recognizes the tiny bundled Python demo's absolute app imports.
It rejects relative/dynamic app loading instead of claiming general coverage.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

from archctl.core.compiler import compile_model
from archctl.core.io import InputError, digest, matches, source_files, write_json
from archctl.integrations.briefcase.adapter import parse_evidence


def build(root: Path) -> dict:
    snapshot = compile_model(root)
    files = source_files(root, tuple(p for c in snapshot.model.components for p in c.paths))
    files.update(source_files(root, ("checks/**/*.py",)))
    modules = {rel[:-3].replace("/", "."): rel for rel in files if rel.endswith(".py")}
    def owner(rel: str) -> str | None:
        owners = [c.id for c in snapshot.model.components if any(matches(rel, p) for p in c.paths)]
        if len(owners) > 1:
            raise InputError(f"Ambiguous fixture ownership: {rel}")
        return owners[0] if owners else None
    edges, evidence = [], []
    for rel in sorted(files):
        source = owner(rel)
        if not source or not rel.endswith(".py"):
            continue
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) and node.func.id in {"__import__", "exec", "eval"}
                 or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"):
                raise InputError("The fixture exporter does not resolve dynamic Python loading")
            targets = []
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    raise InputError("The fixture exporter only supports absolute imports")
                module = node.module or ""
                if module == "app" or module.startswith("app."):
                    for alias in node.names:
                        target = f"{module}.{alias.name}"
                        targets.append(target if target in modules else module)
            elif isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names if alias.name.startswith("app.")]
            for module in targets:
                if module not in modules:
                    raise InputError(f"Unresolved demo import: {module}")
                target = owner(modules[module])
                if not target or source == target:
                    continue
                ident = f"import-{len(edges)}"
                evidence.append({"id": ident, "kind": "static", "location": f"{rel}:{node.lineno}",
                                 "description": "Absolute Python import resolved by the fixture-only exporter"})
                edges.append({"id": ident, "source": source, "target": target, "kind": "imports",
                              "origin": "static", "evidence_refs": [ident]})
    bundle = {"schema_version": "archctl.evidence.v2", "producer": {"name": "storefront-fixture-exporter", "version": "1"},
              "source": {"revision": "fixture:" + digest(files), "files": files},
              "coverage": {"analysis": "static", "status": "complete", "components": [c.id for c in snapshot.model.components],
                           "relationship_kinds": ["imports"], "gaps": []}, "evidence": evidence, "edges": edges}
    return parse_evidence(bundle, snapshot).to_dict()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: evidence.py ROOT [OUTPUT]", file=sys.stderr)
        raise SystemExit(2)
    root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root / ".archctl/evidence.json"
    write_json(output, build(root))
    print(output)
