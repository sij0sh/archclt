import unittest
from archctl.cli_report import overall_status, markdown
from archctl.core.text import markdown_cell


class CompositeResultTests(unittest.TestCase):
    def test_outcomes_cannot_be_upgraded(self):
        self.assertEqual(overall_status("passed", "unknown", "passed"), "unknown")
        self.assertEqual(overall_status("unknown", "failed"), "failed")
        self.assertEqual(overall_status("passed", "error"), "error")
        self.assertEqual(overall_status("passed", "not_executed"), "unknown")
        self.assertEqual(overall_status(), "unknown")
        self.assertEqual(overall_status("passed", "passed"), "passed")

    def test_markdown_cell_escapes_pipes_and_line_endings(self):
        self.assertEqual(markdown_cell("a|b\nc\rd"), "a\\|b c d")
