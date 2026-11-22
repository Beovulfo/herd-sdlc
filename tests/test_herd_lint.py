import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import herd


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class LintBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        (self.root / "a.py").write_text("x = 1\n")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "n.md").write_text("hi")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, body):
        (self.root / "herd.toml").write_text(body)

    def activate(self):
        herd.init_task(self.root, "t1", "goal")

    def hook(self, rel="a.py", **kw):
        return {"cwd": str(self.root), "tool_name": "Edit",
                "tool_input": {"file_path": str(self.root / rel)}, **kw}

    def run_lint(self, **kw):
        return herd.lint(self.hook(**kw))


class TestLint(LintBase):
    def test_no_active_task_is_a_noop(self):
        self.config('[lint]\ncommand = "false"\n')
        self.assertIsNone(self.run_lint())

    def test_no_config_or_no_lint_table_is_a_noop(self):
        self.activate()
        self.assertIsNone(self.run_lint())
        self.config('[floor]\nhigh = ["x/**"]\n')
        self.assertIsNone(self.run_lint())

    def test_bad_toml_is_a_noop(self):
        self.activate()
        self.config("[lint\ncommand=")
        self.assertIsNone(self.run_lint())

    def test_glob_miss_is_a_noop(self):
        self.activate()
        self.config('[lint]\ncommand = "false"\nglobs = ["**/*.py"]\n')
        self.assertIsNone(self.run_lint(rel="docs/n.md"))

    def test_default_glob_matches_everything(self):
        self.activate()
        self.config('[lint]\ncommand = "false"\n')
        self.assertIsNotNone(self.run_lint(rel="docs/n.md"))
        self.assertIsNotNone(self.run_lint(rel="a.py"))

    def test_passing_lint_is_silent(self):
        self.activate()
        self.config('[lint]\ncommand = "true"\n')
        self.assertIsNone(self.run_lint())

    def test_failing_lint_returns_additional_context_with_exact_shape(self):
        self.activate()
        self.config('[lint]\ncommand = "echo bad style in {file}; exit 3"\n')
        out = self.run_lint()
        self.assertEqual(set(out), {"hookSpecificOutput"})
        h = out["hookSpecificOutput"]
        self.assertEqual(set(h), {"hookEventName", "additionalContext"})
        self.assertEqual(h["hookEventName"], "PostToolUse")
        self.assertIn("bad style", h["additionalContext"])
        self.assertIn("exit 3", h["additionalContext"])
        self.assertNotIn("decision", out)  # non-blocking by design

    def test_output_tail_is_cut(self):
        self.activate()
        self.config('[lint]\ncommand = "python3 -c \'print(5000*chr(120)); raise SystemExit(1)\'"\n')
        ctx = self.run_lint()["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(ctx), herd.TAIL_CHARS + 200)

    def test_timeout_is_reported(self):
        self.activate()
        self.config('[lint]\ncommand = "sleep 5"\ntimeout_s = 1\n')
        self.assertIn("timeout", self.run_lint()["hookSpecificOutput"]["additionalContext"])

    def test_path_with_spaces_and_shell_characters_is_quoted(self):
        self.activate()
        name = "we ird; echo pwned $(x).py"
        (self.root / name).write_text("x")
        self.config('[lint]\ncommand = "test -f {file}"\n')  # exits 0 only if the quoted path is one argument
        self.assertIsNone(self.run_lint(rel=name))
        self.config('[lint]\ncommand = "echo {file}; exit 1"\n')
        ctx = self.run_lint(rel=name)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("we ird; echo pwned $(x).py", ctx)

    def test_file_outside_project_or_missing_path_is_a_noop(self):
        self.activate()
        self.config('[lint]\ncommand = "false"\n')
        self.assertIsNone(herd.lint({"cwd": str(self.root), "tool_input": {"file_path": "/etc/hosts"}}))
        self.assertIsNone(herd.lint({"cwd": str(self.root), "tool_input": {}}))
        self.assertIsNone(herd.lint({"cwd": str(self.root)}))

    def test_cli_reads_payload_from_stdin(self):
        self.activate()
        self.config('[lint]\ncommand = "echo oops; exit 1"\n')
        p = subprocess.run(["python3", str(Path(herd.__file__)), "lint"], cwd=self.root,
                           input=json.dumps(self.hook()), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("oops", json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_cli_silent_when_nothing_to_do(self):
        p = subprocess.run(["python3", str(Path(herd.__file__)), "lint"], cwd=self.root,
                           input=json.dumps(self.hook()), capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_hook_registered_for_edit_and_write(self):
        hooks = json.loads((Path(herd.__file__).parent.parent / "hooks" / "hooks.json").read_text())["hooks"]
        entry = hooks["PostToolUse"][0]
        self.assertEqual(entry["matcher"], "Edit|Write")
        cmd = entry["hooks"][0]
        self.assertIn("herd.py", cmd["command"])
        self.assertTrue(cmd["command"].rstrip().endswith("lint"))
        self.assertGreater(cmd["timeout"], 20)  # above the default timeout_s


class TestSuggest(LintBase):
    def test_suggest_python_and_node(self):
        (self.root / "pyproject.toml").write_text("")
        (self.root / "package.json").write_text("{}")
        text = herd.suggest_lint(self.root)
        self.assertIn("[lint]", text)
        self.assertIn("ruff check {file}", text)
        self.assertIn("npx eslint {file}", text)

    def test_suggest_without_per_file_linter(self):
        (self.root / "Cargo.toml").write_text("")
        text = herd.suggest_lint(self.root)
        self.assertNotIn("[lint]", text)
        self.assertIn("no per-file lint", text)

    def test_suggest_cli(self):
        (self.root / "pyproject.toml").write_text("")
        p = subprocess.run(["python3", str(Path(herd.__file__)), "lint", "--suggest"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("ruff check {file}", p.stdout)


if __name__ == "__main__":
    unittest.main()
