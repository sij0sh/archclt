from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import validate


class ReleaseValidationTests(unittest.TestCase):
    def test_missing_schema_dependency_stops_release_before_tests_or_build(self):
        discover = importlib.util.find_spec
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = io.StringIO()
            with patch.object(validate, "ROOT", root), patch("importlib.util.find_spec", side_effect=
                    lambda name: None if name == "jsonschema" else discover(name)), \
                    patch.object(validate.unittest.defaultTestLoader, "discover") as tests, \
                    patch.object(validate, "command") as command, redirect_stdout(output):
                self.assertEqual(validate.main(), 1)
            tests.assert_not_called()
            command.assert_not_called()
            report = json.loads((root / ".archctl/validation/summary.json").read_text())
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["stage"], "dependencies")
            self.assertIn("jsonschema", report["missing"])
            self.assertEqual(report["schema_conformance"], "not_executed")
