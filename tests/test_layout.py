"""The plugin lives in plugin/, so an install does not ship examples/ (issue #34)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"


class TestLayout(unittest.TestCase):
    def test_marketplace_source(self):
        m = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual([p["source"] for p in m["plugins"]], ["./plugin"])
        self.assertTrue((PLUGIN / ".claude-plugin" / "plugin.json").is_file())

    @unittest.skipUnless(shutil.which("claude"), "the claude CLI is not installed (CI runners lack it)")
    def test_install_has_no_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CLAUDE_CONFIG_DIR": tmp}
            for cmd in (["marketplace", "add", str(ROOT)], ["install", "herd@herd-sdlc"]):
                p = subprocess.run(["claude", "plugin", *cmd], env=env, cwd=tmp, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            cache = Path(tmp) / "plugins" / "cache" / "herd-sdlc" / "herd"
            installed = [d for d in cache.iterdir() if d.is_dir()]
            self.assertEqual(len(installed), 1)
            names = {c.name for c in installed[0].iterdir()}
            self.assertNotIn("examples", names)
            self.assertNotIn("tests", names)
            self.assertTrue({"hooks", "agents", "skills", "scripts"} <= names, names)
            self.assertFalse(list(installed[0].rglob("examples")))

    def test_plugin_names_no_repo_paths(self):
        bad = re.compile(r"(?<![\w-])(examples|tests)/")
        hits = []
        for f in PLUGIN.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".md", ".json"}:
                for n, line in enumerate(f.read_text().splitlines(), 1):
                    if bad.search(line):
                        hits.append(f"{f.relative_to(ROOT)}:{n}")
        self.assertEqual(hits, [])

    def test_version_and_changelog(self):
        v = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
        self.assertEqual(v, "0.12.11")
        self.assertIn("## 0.12.2", (ROOT / "CHANGELOG.md").read_text())
        self.assertEqual(sorted(p.name for p in PLUGIN.iterdir() if p.name != ".DS_Store"),
                         [".claude-plugin", "LICENSE", "NOTICE", "agents", "assets", "hooks", "scripts", "skills"])


if __name__ == "__main__":
    unittest.main()
