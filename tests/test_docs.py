from pathlib import Path
import re
import unittest


class DocumentationLinks(unittest.TestCase):
    def test_repository_document_links_resolve(self):
        root = Path(__file__).resolve().parents[1]
        documents = [*root.glob("*.md"), *root.glob("docs/*.md"), *root.glob("validation/**/README.md")]
        for document in documents:
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                if "://" in target or target.startswith(("#", "/")):
                    continue
                with self.subTest(document=str(document.relative_to(root)), target=target):
                    self.assertTrue((document.parent / target.split("#")[0]).is_file())
