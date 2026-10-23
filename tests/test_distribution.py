"""Exercise the actual wheel and source archive contents outside Git."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='archclt-distribution-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        source = cls.directory / 'source'; source.mkdir()
        for name in ('src', 'tests', 'scripts', 'contracts', 'docs', 'architecture', 'skills', 'npm', '.github'):
            shutil.copytree(ROOT/name, source/name, ignore=shutil.ignore_patterns('__pycache__', 'runtime', '*.pyc'))
        for name in ('pyproject.toml', 'MANIFEST.in', 'LICENSE', 'README.md', 'CONTRIBUTING.md',
                     'ARCHITECTURE.md', 'AGENTS.md', 'CHANGELOG.md', 'package.json', 'package-lock.json', '.gitignore', '.gitattributes'):
            shutil.copy2(ROOT/name, source/name)
        cls.output = cls.directory/'artifacts'; cls.output.mkdir()
        code = 'import setuptools.build_meta as b; b.build_wheel('+repr(str(cls.output))+'); b.build_sdist('+repr(str(cls.output))+')'
        result = subprocess.run([sys.executable, '-c', code], cwd=source, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)

    def test_wheel_contains_runtime_and_license_without_development_fixture(self):
        wheel = next(self.output.glob('*.whl'))
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            self.assertIn('archctl/cli.py', names)
            self.assertTrue(any(name.endswith('/licenses/LICENSE') for name in names))
            self.assertFalse(any(name.startswith(('tests/', 'scripts/', 'validation/')) for name in names))
            self.assertNotIn('Storefront', archive.read('archctl/templates.py').decode())

    def test_extracted_source_archive_can_run_contract_tests(self):
        with tarfile.open(next(self.output.glob('*.tar.gz'))) as archive:
            names = archive.getnames()
            for suffix in ('tests/support.py', 'tests/__init__.py', 'scripts/generate_schemas.py',
                           'scripts/migrate_memory_v2.py', 'contracts/v2/evidence.schema.json',
                           'contracts/context/v2/memory.schema.json', 'skills/architecture-control/SKILL.md'):
                self.assertTrue(any(name.endswith('/'+suffix) for name in names), suffix)
            self.assertFalse(any('/validation/' in name or '/contracts/v1/' in name or '/contracts/context/v1/' in name for name in names))
            destination = self.directory/'extracted'
            # All members were produced above from this task's copied source tree.
            archive.extractall(destination, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        source = next(destination.iterdir())
        env = {**os.environ, 'PYTHONPATH':str(source/'src')+os.pathsep+str(source)}
        result = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_contracts', '-v'],
                                cwd=source, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
