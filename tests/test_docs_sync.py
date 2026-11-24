"""The docs match the code (issue #59). Facts are read from the code, not typed again here."""
import json
import re
import unittest
from pathlib import Path

from scripts import herd, herd_triage

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text())["version"]


def read(name):
    return (ROOT / name).read_text()


def row(text, start):
    """The one markdown table row that starts with `start`."""
    rows = [line for line in text.splitlines() if line.startswith(start)]
    assert len(rows) == 1, (start, rows)
    return rows[0]


class TestDocsSync(unittest.TestCase):
    def test_stale_strings_are_gone(self):
        stale = {
            "README.md": ["5 attacks", "five standard attacks", "after every change", "Python 3.11 to 3.13",
                          "Adversarial pass: 5 attempts", "egm@egm", "(v0.4)", "463 unit tests",
                          "`recount`) and needs", "herd/bench-isolation"],
            "docs/PRD.md": ["modules in `scripts/`", "(version 0.12.10"],
            "plugin/skills/run/SKILL.md": ["one tier above yours (`herd status` prints it)"],
            "plugin/agents/herd-reviewer.md": ["a model one tier above yours (`herd status` names it)"],
            "examples/supermarket-route/README.md": ["so it ships this folder",
                                                     "only for runs whose audit prints"],
            "examples/supermarket-route/BENCHMARK.md": ["are on branch `herd/bench-isolation`"],
        }
        hits = [f"{name}: {s}" for name, strings in stale.items() for s in strings if s in read(name)]
        self.assertEqual(hits, [])

    def test_no_root_level_plugin_paths(self):
        bad = re.compile(r"(?<![\w/}.-])(scripts|skills|hooks|agents)/[\w-]+\.(py|md|json)")
        hits = [f"{name}: {m.group(0)}" for name in ("README.md", "CLAUDE.md", "docs/PRD.md")
                for m in bad.finditer(read(name))]
        self.assertEqual(hits, [])

    def test_version_is_the_manifest_version(self):
        self.assertIn(f"Version {VERSION} ", read("README.md"))
        self.assertIn(f"version {VERSION},", read("docs/PRD.md"))

    def test_commands_table_covers_usage(self):
        readme = read("README.md")
        self.assertEqual([c for c in herd.USAGE if not re.search(rf"^\| `herd {c}\b", readme, re.M)], [])

    def test_attacks_are_all_named(self):
        for text in (read("plugin/skills/run/adversarial.md"), herd.USAGE["note"],
                     row(read("README.md"), "| `herd note ")):
            self.assertEqual([a for a in herd.ATTACKS if a not in text], [], text[:80])
        self.assertEqual(len(herd.ATTACKS), 6)
        self.assertIn("6 attacks", read("README.md"))

    def test_settings_table_has_the_real_defaults(self):
        readme = read("README.md")
        floor = row(readme, "| `[floor]`")
        for globs in herd_triage.DEFAULT_RULES.values():
            self.assertEqual([g for g in globs if g not in floor], [])
        ext = row(readme, "| `path_extensions`")
        self.assertEqual([e for e in herd_triage.DEFAULT_EXTENSIONS if f'"{e}"' not in ext], [])
        review = row(readme, "| `[review]`")
        self.assertIn(json.dumps(list(herd.DEFAULT_TIERS)), review)
        self.assertIn(f"`step = {herd.DEFAULT_STEP}`", review)
        self.assertIn(f"`{herd.REVIEW_CAP}`", review)
        self.assertIn(f"`timeout_s` is {herd.LINT_TIMEOUT}", readme)

    def test_reviewer_knows_the_limits(self):
        text = read("plugin/agents/herd-reviewer.md")
        self.assertIn("capped at Sonnet", text)
        self.assertIn(f"at most {herd.MAX_REVIEW_ROUNDS} reviews", text)

    def test_blocked_leak_finding_counts_as_clean(self):
        text = read("examples/supermarket-route/README.md")
        self.assertIn("marked `blocked`", text)
        self.assertIn("counts as clean", text)
        self.assertIn("void", text)


if __name__ == "__main__":
    unittest.main()
