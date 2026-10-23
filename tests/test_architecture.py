"""Executable module boundaries derived from the repository's compiled model."""

import ast
from pathlib import Path
import unittest

from archctl.core.compiler import compile_model
from archctl.core.io import matches

ROOT = Path(__file__).resolve().parents[1]


class ModuleBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = compile_model(ROOT)
        cls.components = {c.id: c for c in cls.snapshot.model.components}
        cls.forbidden = {(p.source, p.target) for p in cls.snapshot.model.policies
                         if p.kind == "forbidden_dependency" and "imports" in p.kinds}

    def owner(self, relative: str) -> str:
        owners = [ident for ident, component in self.components.items()
                  if any(matches(relative, pattern) for pattern in component.paths)]
        self.assertEqual(len(owners), 1, f"{relative} must have exactly one component binding, found {owners}")
        return owners[0]

    def target(self, module: str) -> str:
        if module == "archctl":
            return self.owner("src/archctl/__init__.py")
        stem = "src/" + module.replace(".", "/")
        for relative in (stem + ".py", stem + "/__init__.py"):
            if (ROOT / relative).is_file():
                return self.owner(relative)
        self.fail(f"Import target is not bound to a source module: {module}")

    def test_every_source_file_is_bound_and_dependency_directions_hold(self):
        root = ROOT / "src/archctl"
        files = sorted(path.relative_to(ROOT).as_posix() for path in root.rglob("*.py"))
        self.assertTrue(files)
        for component in self.components.values():
            for pattern in component.paths:
                self.assertTrue(any(matches(relative, pattern) for relative in files),
                                f"{component.id} path matched no source: {pattern}")
        graph = {name: set() for name in self.components}
        for relative in files:
            source = self.owner(relative)
            for node in ast.walk(ast.parse((ROOT / relative).read_text())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    self.fail(f"{relative} uses a relative import that cannot be mapped to a component")
                modules = [node.module] if isinstance(node, ast.ImportFrom) else (
                    [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                for module in modules:
                    if module != "archctl" and not (module or "").startswith("archctl."):
                        continue
                    target = self.target(module)
                    self.assertNotIn(
                        (source, target), self.forbidden,
                        f"{relative} ({source}) imports prohibited component {target}")
                    if target != source:
                        graph[source].add(target)

        def visit(name, ancestors):
            self.assertNotIn(name, ancestors, f"Module dependency cycle: {ancestors} -> {name}")
            for target in graph[name]:
                visit(target, ancestors | {name})

        for name in graph:
            visit(name, set())
