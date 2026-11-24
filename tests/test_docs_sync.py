"""The docs match the code (issue #59). Facts are read from the code, not typed again here.

The details live in the GitHub wiki, outside this repository: set HERD_WIKI to a folder with its pages to
check them too. Without it those tests are skipped, as on CI.
"""
import json
import os
import re
import unittest
from pathlib import Path

from scripts import herd, herd_triage

ROOT = Path(__file__).resolve().parent.parent
WIKI = Path(os.environ["HERD_WIKI"]) if os.environ.get("HERD_WIKI") else None
WIKI_URL = "https://github.com/Beovulfo/herd-sdlc/wiki/"
VERSION = json.loads((ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text())["version"]


def read(name):
    return (ROOT / name).read_text()


def row(text, start):
    """The one markdown table row that starts with `start`."""
    rows = [line for line in text.splitlines() if line.startswith(start)]
    assert len(rows) == 1, (start, rows)
    return rows[0]


def wiki(page):
    return (WIKI / f"{page}.md").read_text()


STALE = ["5 attacks", "five standard attacks", "after every change", "Python 3.11 to 3.13",
         "Adversarial pass: 5 attempts", "egm@egm", "(v0.4)", "463 unit tests", "`recount`) and needs",
         "herd/bench-isolation", "Done: added slugify(text) in textutil.py."]
ROOT_PATH = re.compile(r"(?<![\w/}.-])(scripts|skills|hooks|agents)/[\w-]+\.(py|md|json)")


class TestDocsSync(unittest.TestCase):
    def test_stale_strings_are_gone(self):
        stale = {
            "README.md": STALE,
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
        hits = [f"{name}: {m.group(0)}" for name in ("README.md", "CLAUDE.md", "docs/PRD.md")
                for m in ROOT_PATH.finditer(read(name))]
        self.assertEqual(hits, [])

    def test_version_is_the_manifest_version(self):
        self.assertIn(f"Version {VERSION} ", read("README.md"))
        self.assertIn(f"version {VERSION},", read("docs/PRD.md"))

    def test_readme_is_short(self):
        self.assertLessEqual(len(read("README.md").splitlines()), 150)
        self.assertIn("6 attacks", read("README.md"))

    def test_readme_settings_have_the_real_defaults(self):
        self.check_defaults(read("README.md"))

    def check_defaults(self, text):
        floor = row(text, "| `[floor]`")
        for globs in herd_triage.DEFAULT_RULES.values():
            self.assertEqual([g for g in globs if g not in floor], [])
        review = row(text, "| `[review]`")
        self.assertIn(json.dumps(list(herd.DEFAULT_TIERS)), review)
        self.assertIn(f"`step = {herd.DEFAULT_STEP}`", review)
        self.assertIn(f"`{herd.REVIEW_CAP}`", review)

    def test_reviewer_knows_the_limits(self):
        text = read("plugin/agents/herd-reviewer.md")
        self.assertIn("capped at Sonnet", text)
        self.assertIn(f"at most {herd.MAX_REVIEW_ROUNDS} reviews", text)

    def test_attacks_are_all_named(self):
        for text in (read("plugin/skills/run/adversarial.md"), herd.USAGE["note"]):
            self.assertEqual([a for a in herd.ATTACKS if a not in text], [], text[:80])
        self.assertEqual(len(herd.ATTACKS), 6)

    def test_blocked_leak_finding_counts_as_clean(self):
        text = read("examples/supermarket-route/README.md")
        self.assertIn("A finding marked `blocked` is an attempt that the sandbox refused", text)
        self.assertIn("It counts as clean. Only a read of the hidden verifier, of another run or of the network "
                      "voids a run.", text)


@unittest.skipUnless(WIKI, "set HERD_WIKI to the folder with the wiki pages")
class TestWiki(unittest.TestCase):
    check_defaults = TestDocsSync.check_defaults

    def test_every_wiki_link_has_a_page(self):
        links = re.findall(re.escape(WIKI_URL) + r"([\w-]+)", read("README.md"))
        self.assertTrue(links)
        for f in WIKI.glob("*.md"):
            links += re.findall(r"\]\(([A-Z][\w-]*)(?:#[\w-]*)?\)", f.read_text())
        self.assertEqual(sorted({p for p in links if not (WIKI / f"{p}.md").is_file()}), [])

    def test_stale_strings_and_root_paths_are_gone(self):
        hits = [f"{f.name}: {s}" for f in WIKI.glob("*.md") for s in STALE if s in f.read_text()]
        hits += [f"{f.name}: {m.group(0)}" for f in WIKI.glob("*.md") for m in ROOT_PATH.finditer(f.read_text())]
        self.assertEqual(hits, [])

    def test_commands_page_covers_usage_and_attacks(self):
        text = wiki("Commands")
        self.assertEqual([c for c in herd.USAGE if not re.search(rf"^\| `herd {c}\b", text, re.M)], [])
        note = row(text, "| `herd note ")
        self.assertEqual([a for a in herd.ATTACKS if a not in note], [])

    def test_settings_page_has_the_real_defaults(self):
        text = wiki("Settings")
        self.check_defaults(text)
        ext = row(text, "| `path_extensions`")
        self.assertEqual([e for e in herd_triage.DEFAULT_EXTENSIONS if f'"{e}"' not in ext], [])
        self.assertIn(f"`timeout_s` is {herd.LINT_TIMEOUT}", text)


if __name__ == "__main__":
    unittest.main()
