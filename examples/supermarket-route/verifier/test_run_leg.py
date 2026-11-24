import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_leg as rl  # noqa: E402


def run_main(argv, env, scan_dirs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = rl.run(argv, env=env, scan_dirs=scan_dirs)
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.tmpdir = self.tmp / "tmpdir"
        self.tmpdir.mkdir()
        self.env = {"HOME": str(self.home), "TMPDIR": str(self.tmpdir), "PATH": os.environ["PATH"]}
        self.prompt = self.tmp / "prompt.md"
        self.prompt.write_text("Build a thing.\n\"quoted\" $x `y`\n")

    def args(self, *extra, name="leg"):
        return ["--name", name, "--runs", "3", "--model", "claude-haiku-5-5", "--prompt", str(self.prompt), *extra]


class TestSettings(Base):
    def test_shape_and_denied_paths(self):
        root = self.tmpdir / "herd-bench" / "leg"
        (self.tmpdir / "herd-bench" / "older-leg").mkdir(parents=True)
        s = rl.build_settings(root, 3, 2)
        self.assertEqual(s["sandbox"]["enabled"], True)
        self.assertEqual(s["sandbox"]["autoAllowBashIfSandboxed"], True)
        self.assertEqual(s["sandbox"]["allowUnsandboxedCommands"], False)
        deny = s["sandbox"]["filesystem"]["denyRead"]
        older = str(root.parent / "older-leg")
        run1, run3, run2 = (str(root / f"run-{i}") for i in (1, 3, 2))
        self.assertEqual(deny[0], "~/")
        logs = [f"{r}{x}" for r in (run1, run3) for x in (".jsonl", ".err")]
        self.assertEqual(sorted(deny[1:]), sorted([older, run1, run3, *logs]))
        self.assertNotIn(run2, deny)
        self.assertNotIn(str(root), deny)
        perms = s["permissions"]["deny"]
        for d in deny[1:]:
            self.assertIn("Read(/" + d + "/**)", perms)  # "//" then the path without its leading slash
        self.assertIn("Read(~/**)", perms)
        self.assertIn("WebFetch", perms)
        self.assertIn("WebSearch", perms)
        self.assertEqual(set(s), {"sandbox", "permissions"})

    def test_root_parent_is_created_lazily_so_siblings_are_listed_when_present(self):
        root = self.tmpdir / "herd-bench" / "leg"
        s = rl.build_settings(root, 1, 1)
        self.assertEqual(s["sandbox"]["filesystem"]["denyRead"], ["~/"])


class TestRefusals(Base):
    def test_root_inside_home_is_refused(self):
        code, out = run_main(self.args("--root", str(self.home / "bench")), self.env, [])
        self.assertEqual(code, 2)
        self.assertIn("HOME", out)
        self.assertFalse((self.home / "bench").exists())

    def test_existing_root_is_refused(self):
        root = self.tmpdir / "there"
        root.mkdir()
        code, _ = run_main(self.args("--root", str(root)), self.env, [])
        self.assertEqual(code, 2)

    def test_preflight_refuses_and_lists_planted_file(self):
        planted = self.tmpdir / "old" / "verify_general.py"
        planted.parent.mkdir()
        planted.write_text("x")
        code, out = run_main(self.args("--dry-run"), self.env, [str(self.tmpdir)])
        self.assertEqual(code, 2)
        self.assertIn(str(planted), out)
        self.assertFalse((self.tmpdir / "herd-bench").exists())

    def test_preflight_accepts_a_file_inside_a_denied_sibling(self):
        planted = self.tmpdir / "herd-bench" / "older-leg" / "probe6.py"
        planted.parent.mkdir(parents=True)
        planted.write_text("x")
        code, out = run_main(self.args("--dry-run"), self.env, [str(self.tmpdir)])
        self.assertEqual(code, 0, out)


class TestDryRun(Base):
    def test_old_layout_tag_is_archived_from_the_root(self):
        old = "685d69a"  # 0.12.1: the plugin sat at the repository root
        if not rl.tag_exists(old):
            self.skipTest("the 0.12.1 commit is not in this clone")
        code, out = run_main(self.args("--dry-run", "--herd-tag", old), self.env, [str(self.tmpdir)])
        self.assertEqual(code, 0, out)
        plugin = self.tmpdir / "herd-bench" / "leg" / "run-1" / "plugin"
        self.assertTrue((plugin / "scripts" / "herd.py").is_file())
        self.assertTrue((plugin / ".claude-plugin" / "plugin.json").is_file())
        self.assertFalse((plugin / "examples").exists())

    def test_dry_run_writes_everything_and_starts_nothing(self):
        with mock.patch.object(rl, "start", side_effect=AssertionError("started")):
            code, out = run_main(self.args("--dry-run", "--herd-tag", "HEAD", "--budget", "7"),
                                 self.env, [str(self.tmpdir)])
        self.assertEqual(code, 0, out)
        root = self.tmpdir / "herd-bench" / "leg"
        for i in (1, 2, 3):
            r = root / f"run-{i}"
            self.assertTrue((r / "xdg").is_dir())
            self.assertIn("bench@example.com", (r / "gitconfig").read_text())
            self.assertTrue((r / "plugin" / "scripts" / "herd.py").is_file())
            self.assertFalse((r / "plugin" / "examples").exists())
            self.assertFalse((r / "plugin" / "tests").exists())
            self.assertFalse((r / "plugin" / "docs").exists())
            log = subprocess.run(["git", "-C", str(r / "work"), "log", "--oneline"],
                                 capture_output=True, text=True, env={**os.environ, "GIT_CONFIG_GLOBAL": str(r / "gitconfig")})
            self.assertEqual(len(log.stdout.splitlines()), 1, log.stderr)
            s = json.loads((r / "settings.json").read_text())
            self.assertEqual(len([d for d in s["sandbox"]["filesystem"]["denyRead"] if "/run-" in d]), 6)
        self.assertIn("--setting-sources project", out)
        self.assertIn("--max-budget-usd 7", out)
        self.assertIn("--permission-mode dontAsk", out)
        self.assertIn(str(root / "run-2" / "plugin"), out)
        self.assertIn("\"type\":\"result\"", out)

    def test_command_carries_the_prompt_verbatim_and_no_plugin_without_a_tag(self):
        ns = rl.parse(self.args())
        cmd = rl.build_command(ns, self.prompt.read_text(), self.tmpdir / "r" / "run-1")
        self.assertEqual(cmd[:3], ["claude", "-p", self.prompt.read_text()])
        self.assertNotIn("--plugin-dir", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Agent,Skill")


class TestAttacks(Base):
    def test_bad_input_missing_prompt_and_bad_counts(self):
        for extra in (["--prompt", str(self.tmp / "absent.md")],):
            a = self.args()
            a[a.index("--prompt") + 1] = extra[1]
            code, out = run_main(a, self.env, [])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", out)
        for runs in ("0", "-1"):
            a = self.args()
            a[a.index("--runs") + 1] = runs
            self.assertEqual(run_main(a, self.env, [])[0], 2)
        self.assertEqual(run_main(self.args("--herd-tag", "no-such-tag-xyz"), self.env, [])[0], 2)
        self.assertFalse((self.tmpdir / "herd-bench").exists())

    def test_collision_same_name_twice_is_refused(self):
        self.assertEqual(run_main(self.args("--dry-run"), self.env, [])[0], 0)
        self.assertEqual(run_main(self.args("--dry-run"), self.env, [])[0], 2)

    def test_one_bad_part_unreadable_dir_does_not_stop_preflight(self):
        bad = self.tmpdir / "locked"
        bad.mkdir()
        (bad / "x").write_text("x")
        bad.chmod(0)
        self.addCleanup(bad.chmod, 0o755)
        self.assertEqual(run_main(self.args("--dry-run"), self.env, [str(self.tmpdir)])[0], 0)

    def test_recount_preflight_equals_plain_find(self):
        import random
        rng = random.Random(7)
        names = ["verify_general.py", "probe6.py", "robustness_probe.py", "other.py", "verify_general.py.bak"]
        for n in range(12):
            d = self.tmpdir / f"d{n}" / rng.choice(["a", "b"]) / rng.choice(["c", "d"])
            d.mkdir(parents=True, exist_ok=True)
            (d / rng.choice(names)).write_text("x")
        want = subprocess.run(["find", str(self.tmpdir), "(", "-name", "verify_general.py", "-o", "-name",
                               "probe6.py", "-o", "-name", "robustness_probe.py", ")", "-type", "f"],
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(rl.preflight([str(self.tmpdir)], []), sorted(want))
        skip = self.tmpdir / "d3"
        got = rl.preflight([str(self.tmpdir)], [str(skip)])
        self.assertEqual(got, sorted(w for w in want if not w.startswith(str(skip) + "/")))

    def test_refusal_home_check_is_by_component(self):
        sibling = Path(str(self.home) + "-other") / "bench"
        self.assertEqual(run_main(self.args("--dry-run", "--root", str(sibling)), self.env, [])[0], 0)
        self.assertEqual(run_main(self.args("--root", str(self.home)), self.env, [])[0], 2)


class TestRepoDeny(Base):
    def test_checkout_outside_home_is_denied(self):
        root = self.tmpdir / "herd-bench" / "leg"
        with mock.patch.object(rl, "_repo_root", return_value="/opt/src/herd"):
            self.assertEqual(rl.outside_home_repo({"HOME": str(self.home)}), [os.path.realpath("/opt/src/herd")])
            self.assertEqual(rl.outside_home_repo({"HOME": "/opt"}), [])
        s = rl.build_settings(root, 1, 1, ["/opt/src/herd"])
        self.assertIn("/opt/src/herd", s["sandbox"]["filesystem"]["denyRead"])
        self.assertIn("Read(///opt/src/herd/**)".replace("///", "//"), s["permissions"]["deny"])


class TestTask(Base):
    BUS = {"bus_verify.py", "bus_probe.py", "bus_reference.py"}

    def test_task_value_as_name_or_path_resolves_to_the_same_task(self):
        for v in ("bus-transfer", "examples/bus-transfer", "examples/bus-transfer/", "./examples/bus-transfer",
                  str(rl.EXAMPLES / "bus-transfer"), str(rl.EXAMPLES / "bus-transfer") + "/"):
            self.assertEqual(rl.resolve_task(v), "bus-transfer", v)
        self.assertEqual(rl.resolve_task("supermarket-route"), "supermarket-route")

    def test_unknown_task_is_refused_with_the_known_names(self):
        for v in ("nope", "examples/nope", "", "../bus-transfer-x"):
            with self.assertRaises(ValueError) as cm:
                rl.resolve_task(v)
            self.assertIn("bus-transfer", str(cm.exception))
            self.assertIn("supermarket-route", str(cm.exception))
        code, out = run_main(["--name", "leg", "--runs", "1", "--model", "m", "--task", "nope"], self.env, [])
        self.assertEqual(code, 2)
        self.assertIn("unknown task", out)

    def test_task_supplies_the_prompt_and_an_explicit_prompt_wins(self):
        want = (rl.EXAMPLES / "bus-transfer" / "prompt.md").read_text()
        for task in ("bus-transfer", "examples/bus-transfer/"):
            code, out = run_main(["--name", "leg", "--runs", "1", "--model", "m", "--task", task, "--dry-run"],
                                 self.env, [str(self.tmpdir)])
            self.assertEqual(code, 0, out)
            self.assertIn(shlex.quote(want), out)
            shutil.rmtree(self.tmpdir / "herd-bench")
        code, out = run_main(self.args("--task", "bus-transfer", "--dry-run"), self.env, [str(self.tmpdir)])
        self.assertEqual(code, 0, out)
        self.assertIn(shlex.quote(self.prompt.read_text()), out)
        self.assertNotIn(shlex.quote(want), out)

    def test_hidden_names_of_both_tasks_are_refused_for_either_task(self):
        for task in ("bus-transfer", "supermarket-route"):
            for name in sorted(self.BUS | {"verify_general.py", "robustness_probe.py", "probe6.py"}):
                planted = self.tmpdir / "old" / name
                planted.parent.mkdir(exist_ok=True)
                planted.write_text("x")
                code, out = run_main(self.args("--task", task, "--dry-run"), self.env, [str(self.tmpdir)])
                self.assertEqual(code, 2, (task, name))
                self.assertIn(str(planted), out)
                planted.unlink()

    def test_hidden_names_table_covers_every_task_folder(self):
        self.assertTrue(self.BUS <= rl.HIDDEN["bus-transfer"])
        self.assertEqual(set(rl.HIDDEN), {p.name for p in rl.EXAMPLES.iterdir() if (p / "verifier").is_dir()})
        self.assertEqual(rl.PLANTED_NAMES, set().union(*rl.HIDDEN.values()))

    def test_supermarket_still_requires_a_prompt_or_a_task(self):
        code, out = run_main(["--name", "leg", "--runs", "1", "--model", "m"], self.env, [])
        self.assertEqual(code, 2)
        self.assertIn("--prompt or --task", out)


class TestHiddenBus(Base):
    def test_Hidden_bus_test_file_is_in_the_bus_table(self):
        self.assertIn("test_bus_verify.py", rl.HIDDEN["bus-transfer"])
        self.assertIn("test_bus_verify.py", rl.PLANTED_NAMES)

    def test_Hidden_stray_copy_of_the_bus_test_file_in_the_temp_folder_is_refused(self):
        planted = self.tmpdir / "stray" / "test_bus_verify.py"
        planted.parent.mkdir()
        planted.write_text("x")
        for task in ("bus-transfer", "supermarket-route"):
            code, out = run_main(self.args("--task", task, "--dry-run"), self.env, [str(self.tmpdir)])
            self.assertEqual(code, 2, (task, out))
            self.assertIn("refused: the hidden verifier or a probe is readable by a run", out)
            self.assertIn(str(planted), out)
        self.assertFalse((self.tmpdir / "herd-bench").exists())

    def test_Hidden_refusal_of_every_bus_name_matches_a_plain_find(self):
        names = sorted({"bus_verify.py", "bus_probe.py", "bus_reference.py", "test_bus_verify.py"})
        for name in names:
            (self.tmpdir / "copies" / name.replace(".py", "")).mkdir(parents=True)
            (self.tmpdir / "copies" / name.replace(".py", "") / name).write_text("x")
        (self.tmpdir / "copies" / "other.py").write_text("x")
        want = subprocess.run(["find", str(self.tmpdir), "-type", "f", "(", *sum(([ "-name", n, "-o"] for n in names), [])[:-1], ")"],
                              capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(rl.preflight([str(self.tmpdir)], []), sorted(want))
        self.assertEqual(len(want), len(names))


if __name__ == "__main__":
    unittest.main()
