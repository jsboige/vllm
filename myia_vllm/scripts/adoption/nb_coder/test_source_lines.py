"""Offline regression tests for the deterministic writer (no MCP/network needed)."""
import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

# Exercise the actual writer without importing the driver's MCP runtime dependencies.
TREE = ast.parse(Path(__file__).with_name("nb_coder_driver.py").read_text(encoding="utf-8"))
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef)
         and n.name in {"_text", "apply_edits"}]
NS = {"Path": Path, "json": json, "hashlib": hashlib}
exec(compile(ast.Module(body=NODES, type_ignores=[]), "nb_coder_driver.py", "exec"), NS)


class SourceLinesTests(unittest.TestCase):
    def test_edits_and_inserts_preserve_text_and_unrelated_outputs(self):
        for text in ("first\nsecond\n", "first\nsecond", "", "école\n\nfin"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "sample.ipynb"
                untouched = {"cell_type": "code", "source": ["print(1)"],
                             "metadata": {}, "execution_count": 1,
                             "outputs": [{"output_type": "stream", "name": "stdout",
                                          "text": ["1\n"]}]}
                nb = {"cells": [{"cell_type": "markdown", "source": ["old\n"],
                                 "metadata": {}, "id": "original"}, untouched],
                      "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
                p.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                result = NS["apply_edits"](p, {"edits": [{"cell": 0, "source": text}],
                     "inserts": [{"after": 0, "source": text, "cell_type": "markdown"}]})
                self.assertEqual(result["errors"], [])
                cells = json.loads(p.read_text(encoding="utf-8"))["cells"]
                for cell in cells[:2]:
                    self.assertIsInstance(cell["source"], list)
                    self.assertEqual("".join(cell["source"]), text)
                self.assertEqual(cells[2], untouched)


if __name__ == "__main__":
    unittest.main()
