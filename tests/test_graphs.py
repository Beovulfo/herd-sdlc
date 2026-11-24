"""The herd-sdlc-engineer graphs in .claude/graphs/ stay valid, and the validator catches broken ones."""
import importlib.util
import unittest
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / ".claude" / "graphs"
spec = importlib.util.spec_from_file_location("graph_validate", FOLDER / "validate.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)

GOOD = """start: a
nodes:
  a: {type: act, does: "x", next: g}
  g: {type: gate, ask: "ok?", approve: w, skip: e}
  w: {type: act, side_effect: true, does: "write", next: e}
  e: {type: end, does: "report"}
"""


class TestGraphs(unittest.TestCase):
    def test_repo_graphs_are_valid(self):
        files = sorted(FOLDER.glob("*.yaml"))
        self.assertTrue(files)
        for f in files:
            self.assertEqual(validate.problems(f.read_text(encoding="utf-8")), [], f.name)

    def test_good_graph(self):
        self.assertEqual(validate.problems(GOOD), [])

    def test_dangling_edge(self):
        self.assertIn("a: edge to missing node zz", validate.problems(GOOD.replace("next: g", "next: zz")))

    def test_side_effect_without_gate(self):
        bad = GOOD.replace('next: g}', 'next: w}')
        self.assertIn("a -> w: side effect not behind a gate", validate.problems(bad))

    def test_check_retry_into_side_effect_is_allowed(self):
        bad = GOOD.replace('next: e}\n  e:', 'next: c}\n  c: {type: check, does: "read back", pass: e, fail: w}\n  e:')
        self.assertEqual(validate.problems(bad), [])

    def test_unreachable_and_no_end(self):
        found = validate.problems(GOOD.replace("skip: e", "skip: w").replace('next: e}', 'next: g}'))
        self.assertIn("e: unreachable", found)
        self.assertIn("no reachable end node", found)


if __name__ == "__main__":
    unittest.main()
