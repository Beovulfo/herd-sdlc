"""Part A of docs/designs/herd-guardrails.md: the PreToolUse guard hook."""
import io
import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import herd
from tests.test_herd_cli import stub_first_verify_refusal

HOOKS = Path(herd.__file__).resolve().parent.parent / "hooks" / "hooks.json"
STATE = ("evidence.json", "notes.jsonl", "start.json", "red.json", "frozen.json", "green.json", "fails.json",
         "stopped.json", "gate_blocks", "done_blocks", "cancelled")  # G3, as the design lists them
PUSH = ("Herd guard: `git push` is not allowed during a task. Use `herd pr` to publish "
        "(`herd pr --draft` for a draft PR, `--milestone NAME` for its milestone), or ask the human one question and stop.")
DENIED = [  # (command, the rule it breaks): each built-in rule in several shapes
    ("git push", "git push"), ("git push --force origin herd/x", "git push"), ("git push origin x --force", "git push"),
    ("/usr/bin/git push", "git push"), ("git -C sub push", "git push"), ("git -c a.b=c push -u origin x", "git push"),
    ("git reset --hard", "git reset --hard"), ("git reset HEAD~1 --hard", "git reset --hard"),
    ("git clean -f", "git clean -f"), ("git clean -fd", "git clean -f"), ("git clean -xfd", "git clean -f"),
    ("git clean -d -f", "git clean -f"), ("git clean --force", "git clean -f"),
    ("git branch -D old", "git branch -D"), ("git checkout -- .", "git checkout -- ."), ("git restore .", "git restore ."),
    ("git commit --no-verify -m x", "git commit --no-verify"), ("git commit -n -m x", "git commit --no-verify"),
    ("git commit -anm x", "git commit --no-verify"),
    ("gh pr merge 3", "gh pr merge"), ("gh pr merge --squash --admin", "gh pr merge"), ("gh repo delete o/r --yes", "gh repo delete"),
    ("rm -rf /", "rm -rf /"), ("rm -fr /", "rm -rf /"), ("rm -r -f /", "rm -rf /"), ("rm --recursive --force /*", "rm -rf /"),
    ("rm -rf ~", "rm -rf ~"), ("rm -rf ~/", "rm -rf ~"), ("rm -rf $HOME", "rm -rf ~"),
    ("rm -rf .", "rm -rf ."), ("rm -rf ./", "rm -rf ."), ("rm -rf *", "rm -rf ."),
]
PREFIXED = ["env A=1 {}", "A=1 B=2 {}", "sudo {}", "command {}", "time {}", "env {}"]
ALLOWED = ["ls -la", "git status", "git log --oneline -3", "git diff HEAD", "git add -A", "git commit -m 'fix'",
           "echo \"git push\"", "git commit -m 'do not git push --force here'", "grep -r 'gh pr merge' docs",
           "python3 /x/scripts/herd.py pr --yes", "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/herd.py\" pr",
           "git pushx", "git branch -d done", "git clean -n", "rm -rf build", "rm -rf ./dist", "rm file.txt",
           "cat .env", "grep KEY .env", "git checkout main", "git restore src/a.py", "gh pr view 3", "gh pr create --draft"]


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class Base(unittest.TestCase):
    refuses_first = False

    def setUp(self):
        stub_first_verify_refusal(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        herd.init_task(self.root, "t1", "a task", request="a task")

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, command, cwd=None):
        return herd.guard(self.root, {"cwd": str(cwd or self.root), "tool_name": "Bash",
                                      "tool_input": {"command": command}})

    def edit(self, path, tool="Edit"):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return herd.guard(self.root, {"cwd": str(self.root), "tool_name": tool, "tool_input": {key: str(path)}})

    def assertDenied(self, out, msg=None):
        self.assertIsNotNone(out, msg)
        h = out["hookSpecificOutput"]
        self.assertEqual((h["hookEventName"], h["permissionDecision"]), ("PreToolUse", "deny"), msg)
        self.assertTrue(h["permissionDecisionReason"].startswith("Herd guard: "), msg)
        return h["permissionDecisionReason"]

    def cli(self, stdin, python=sys.executable):
        return subprocess.run([python, str(Path(herd.__file__)), "guard"], cwd=self.root, input=stdin,
                              capture_output=True, text=True)


class TestProtectedEdits(Base):
    def test_guard_denies_protected_edit(self):
        (self.root / "herd.toml").write_text('[guard]\nprotected_paths = ["secrets/**"]\n')
        rng = random.Random(7)
        nested = ["/".join(rng.choice("abcxyz") * rng.randint(1, 4) for _ in range(rng.randint(1, 4))) for _ in range(5)]
        paths = [".env", ".env.local", "certs/a.pem", "deep/x/y/server.key", "home/id_rsa", "id_rsa.pub", ".git/config",
                 "secrets/token.txt"] + [f"{n}/k.pem" for n in nested] + [f"{n}/z.key" for n in nested]
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            for p in paths:
                for form in (self.root / p, p):  # absolute, as Claude Code sends it, and relative to cwd
                    reason = self.assertDenied(self.edit(form, tool), (tool, form))
                    self.assertIn(p, reason)
            for p in ("src/app.py", "env.txt", ".envrc", "pem.md", "docs/keys.md", "herd.toml", "README.md"):
                self.assertIsNone(self.edit(self.root / p, tool), (tool, p))
        self.assertIsNone(self.edit("/elsewhere/.env"))  # outside the project: not this guard's business


class TestDeniedCommands(Base):
    def test_guard_denies_push_in_a_chain(self):
        self.assertEqual(self.assertDenied(self.bash("git add -A && git push --force origin herd/export-json")), PUSH)  # CUJ 1
        for cmd, rule in DENIED:
            for shape in ["{}", "git status && {}", "ls || {}", "true; {}", "echo a | {}", "cd sub && {} && ls",
                          "ls\n{}", "(cd sub; {})", "x=$({})", "ls & {}"] + PREFIXED:
                full = shape.format(cmd)
                self.assertIn(f"`{rule}`", self.assertDenied(self.bash(full), full), full)
        self.assertIn("Herd never merges: a human merges after reading the evidence",
                      self.assertDenied(self.bash("gh pr merge 3")))
        self.assertIn("irreversible: ask the human one question and stop", self.assertDenied(self.bash("git reset --hard")))
        rng = random.Random(11)  # seeded random chains of allowed and denied segments
        for _ in range(300):
            parts = [rng.choice(ALLOWED + [c for c, _ in DENIED]) for _ in range(rng.randint(1, 5))]
            seps = [rng.choice([" && ", " || ", "; ", " | ", "\n"]) for _ in parts]
            full = "".join(p + s for p, s in zip(parts, seps)).strip()
            bad = any(p in {c for c, _ in DENIED} for p in parts)
            out = self.bash(full)
            self.assertEqual(out is not None, bad, full)

    def test_guard_allows_herd_pr(self):
        for cmd in ALLOWED:
            self.assertIsNone(self.bash(cmd), cmd)
        self.assertIsNone(self.bash("python3 /Users/x/.claude/plugins/cache/herd/scripts/herd.py pr t1 --yes && git status"))

    def test_extra_deny_commands_extend_the_built_in_ones(self):
        (self.root / "herd.toml").write_text('[guard]\ndeny_commands = ["npm publish", "terraform apply -auto-approve"]\n')
        self.assertIn("`npm publish`", self.assertDenied(self.bash("npm publish --tag next")))
        self.assertIn("`terraform apply -auto-approve`",
                      self.assertDenied(self.bash("terraform apply -auto-approve -var x=1")))
        self.assertIsNone(self.bash("terraform apply"))
        self.assertDenied(self.bash("git push"))  # the built-in rules stay


class TestStateFiles(Base):
    def test_guard_state_files_always_protected(self):
        d = ".herd/tasks/t1"
        rng = random.Random(3)
        configs = ["", "[guard]\nprotected_paths = []\ndeny_commands = []\n", '[guard]\nprotected_paths = "x"\n',
                   "[guard\nbroken", "[guard]\nprotected_paths = [1, 2]\n"]
        configs += ["[guard]\nprotected_paths = [" + ", ".join(
            json.dumps(rng.choice(["*.md", "src/**", "", "!.herd/**", "docs/**", "[", "a//b"]))
            for _ in range(rng.randint(0, 4))) + "]\n" for _ in range(8)]
        for cfg in configs:
            (self.root / "herd.toml").write_text(cfg)
            for name in STATE:
                reason = self.assertDenied(self.edit(self.root / d / name), (cfg, name))
                self.assertIn("written only by the herd CLI: run `herd verify` or `herd note`", reason)
                self.assertDenied(self.edit(self.root / d / name, "Write"), name)
                for cmd in (f"echo x > {d}/{name}", f"echo x >> {d}/{name}", f"rm {d}/{name}",
                            f"mv {d}/{name} /tmp/x", f"sed -i '' s/a/b/ {d}/{name}", f"cat x | tee {d}/{name}",
                            f"truncate -s 0 {d}/{name}", f"cp /tmp/x {d}/{name}"):
                    self.assertDenied(self.bash(cmd), cmd)
            self.assertIsNone(self.edit(self.root / d / "task.toml"), cfg)  # the agent writes the criteria
            self.assertIsNone(self.bash(f"cat {d}/evidence.json && python3 x/herd.py verify"))
            for cmd in ("rm -rf .herd", "rm -r .herd/tasks", f"rm -rf {d}", f"rm {d}/*", "rm .herd/active"):
                self.assertDenied(self.bash(cmd), cmd)
        other = self.root / ".claude/worktrees/herd-x/.herd/tasks/x/evidence.json"  # another worktree's task
        self.assertDenied(self.edit(other))


class TestReported(Base):
    def test_guard_denial_is_reported(self):
        self.assertIsNone(self.bash("git status"))
        self.assertEqual(herd.load_notes(self.root, "t1"), [])  # an allowed call adds nothing
        self.bash("git push")
        self.bash("git add -A && git push --force")
        self.edit(self.root / ".env")
        notes = [n for n in herd.load_notes(self.root, "t1") if n["kind"] == "guard"]
        self.assertEqual([n["text"] for n in notes], ["Bash: git push", "Bash: git push", "Edit: .env"])
        task = self.root / ".herd/tasks/t1/task.toml"
        task.write_text('goal = "a task"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "agent-proposed"\n'
                        'check = "python3 -c 1"\n')
        ev = herd.verify(self.root, "t1")
        line = "Guard: 3 denied (git push x2, .env x1)"
        self.assertIn(line, "\n".join(herd.final_report(self.root, "t1", ev, herd.load_notes(self.root, "t1"))))
        self.assertIn(line, herd.pr_body(self.root, "t1"))
        self.assertEqual(herd.guard_line([]), None)


class TestInactiveAndCrash(Base):
    def test_guard_inactive_allows(self):
        self.assertDenied(self.bash("git push"))
        herd.cancel_task(self.root, "t1", "dropped")
        self.assertIsNone(self.bash("git push"))
        herd.init_task(self.root, "t3", "next", request="next")
        self.assertDenied(self.bash("git push"))
        (self.root / ".herd/active").unlink()  # as `herd done` leaves it
        self.assertIsNone(self.bash("git push"))
        self.assertIsNone(self.edit(self.root / ".env"))
        shutil.rmtree(self.root / ".herd")
        for stdin in (json.dumps({"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "git push"}}), ""):
            p = self.cli(stdin)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        old = shutil.which("python3", path="/usr/bin")
        if not old or subprocess.run([old, "-c", "import sys; sys.exit(sys.version_info >= (3, 11))"]).returncode:
            self.skipTest("no Python older than 3.11 at /usr/bin/python3")
        herd.init_task(self.root, "t2", "again", request="again")
        p = self.cli(json.dumps({"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "git push"}}), old)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_guard_crash_allows(self):
        hook = json.dumps({"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "git push"}})
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(herd, "guard", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(hook)), redirect_stdout(out), redirect_stderr(err):
            code = herd.main(["guard"])
        self.assertEqual((code, out.getvalue()), (0, ""))
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertIn("boom", err.getvalue())
        for bad in ("{not json", "[1, 2]", '{"tool_name": "Bash", "tool_input": 5}', '{"tool_input": {"command": 7}}',
                    '{"tool_name": "Edit", "tool_input": {"file_path": ""}}', '{"tool_name": "Unknown"}'):
            p = self.cli(bad)
            self.assertEqual((p.returncode, p.stdout), (0, ""), bad)
            self.assertLessEqual(len(p.stderr.strip().splitlines()), 1, bad)


class TestGuardAttacks(Base):
    """The adversarial pass on the guard (skills/run/adversarial.md)."""

    def test_guard_bad_input(self):
        for hook in (None, 5, "x", [], {}, {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": 5},
                     {"tool_name": "Bash", "tool_input": {"command": 7}}, {"tool_name": "Bash", "tool_input": {"command": ""}},
                     {"tool_name": "Edit", "tool_input": {"file_path": ""}}, {"tool_name": "Edit", "tool_input": {"file_path": 3}},
                     {"tool_name": "Unknown", "tool_input": {"command": "git push"}}):
            with self.subTest(hook=hook):
                self.assertIsNone(herd.guard(self.root, hook))
        self.assertDenied(herd.guard(self.root, {"tool_name": "Bash", "tool_input": {"command": "git push"}, "cwd": 5}))
        self.assertDenied(self.bash('git push"'))  # an unbalanced quote still finds the push
        self.assertDenied(self.bash("git commit -m 'oops && git push --force"))
        for cfg in ("[guard\n", "[guard]\nprotected_paths = 3\n", "[guard]\ndeny_commands = [\"\", 1]\n",
                    "guard = 1\n", "[guard]\nprotected_paths = [\"[\", \"a//b\", \"\"]\n"):
            (self.root / "herd.toml").write_text(cfg)
            self.assertDenied(self.bash("git push"), cfg)
            self.assertDenied(self.edit(self.root / ".env"), cfg)
            self.assertIsNone(self.bash("ls"), cfg)

    def test_guard_collision(self):
        (self.root / "herd.toml").write_text('[guard]\nprotected_paths = [".env", "**/*.pem"]\ndeny_commands = ["git push"]\n')
        self.bash("git push && gh pr merge 1")  # two rules in one command: the first is reported, once
        self.edit(self.root / ".env")
        self.edit(self.root / ".env", "Write")  # the same file through two tools: each counts
        self.bash("echo x > .env")
        notes = [n["text"] for n in herd.load_notes(self.root, "t1") if n["kind"] == "guard"]
        self.assertEqual(notes, ["Bash: git push", "Edit: .env", "Write: .env", "Bash: .env"])
        self.assertEqual(herd.guard_line(herd.load_notes(self.root, "t1")), "Guard: 4 denied (git push x1, .env x3)")
        other = self.root / ".herd/tasks/another/evidence.json"  # another task's state in the same checkout
        self.assertDenied(self.edit(other))

    def test_guard_one_bad_part(self):
        (self.root / "herd.toml").write_text('[guard]\nprotected_paths = ["[", "vault/**", 7]\ndeny_commands = [3, "npm publish"]\n')
        self.assertDenied(self.edit(self.root / "vault/x.txt"))  # a bad entry does not drop the good ones
        self.assertDenied(self.bash("npm publish"))
        self.assertDenied(self.bash("echo 'unclosed && ls; git push"))
        self.assertIsNone(self.bash("ls; echo 'a | b' | grep a"))  # an odd but harmless chain is allowed

    def test_guard_recount(self):
        rng = random.Random(5)
        actions = [lambda: self.bash("git push"), lambda: self.bash("git reset --hard"),
                   lambda: self.edit(self.root / ".env"), lambda: self.edit(self.root / "a.pem", "Write"),
                   lambda: self.bash("ls"), lambda: self.edit(self.root / "ok.py")]
        expect = {0: "git push", 1: "git reset --hard", 2: ".env", 3: "*.pem"}
        picks = [rng.randrange(len(actions)) for _ in range(40)]
        for i in picks:
            actions[i]()
        mine = {}
        for i in picks:
            if i in expect:
                mine[expect[i]] = mine.get(expect[i], 0) + 1
        with open(self.root / ".herd/tasks/t1/notes.jsonl") as f:  # recount from the raw log
            raw = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(sum(1 for n in raw if n["kind"] == "guard"), sum(mine.values()))
        line = herd.guard_line(raw)
        self.assertTrue(line.startswith(f"Guard: {sum(mine.values())} denied ("))
        for rule, n in mine.items():
            self.assertIn(f"{rule} x{n}", line)

    def test_guard_is_fast(self):
        import time
        hook = json.dumps({"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "ls && git status"}})
        for active in (True, False):
            if not active:
                (self.root / ".herd/active").unlink()
            start = time.perf_counter()
            for _ in range(5):
                self.assertEqual(self.cli(hook).returncode, 0)
            per_call = (time.perf_counter() - start) / 5
            self.assertLess(per_call, 0.5, (active, per_call))  # a hook on every tool call must stay cheap


class TestGuardFindings(Base):
    """Regression tests for the fresh break-it pass on the guard."""

    def test_commands_inside_shell_blocks_and_behind_prefix_flags(self):
        for cmd in ("if true; then git push; fi", "while true; do git push; done", "for i in 1; do git push; done",
                    "{ git push; }", "! git push", "if git push; then :; fi", "sudo -u root git push", "sudo -E git push",
                    "env -i git push", "env -u X git push", "time -p git push", "nohup git push", "exec git push",
                    "gh -R o/r pr merge 1", "gh --repo o/r pr merge 1", "gh --repo=o/r pr merge 1",
                    "git reset --har", "git commit --no-verif -m x", "git clean --forc", "git branch -d -f x",
                    "git branch --delete --force x", "git branch --del --forc x", "git checkout .", "git checkout -f",
                    "rm -rf /.", "rm -rf ..", "rm -rf ../..", "rm -rf .*", f"rm -rf {self.root}", "rm -rf ~/.",
                    "sed -ni 's/a/b/' .env", "touch .herd/tasks/t1/cancelled"):
            self.assertDenied(self.bash(cmd), cmd)
        for cmd in ("git branch -d done", "git reset --soft HEAD~1", "git checkout -b new", "git checkout main",
                    "rm -rf ./build ../other/tmp", "sed -n 1p .env", "if true; then ls; fi", "gh -R o/r pr view 1"):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_heredoc_bodies_are_text_not_commands(self):
        for cmd in ("git commit -F- <<'EOF'\ngit push is now denied\nEOF", "cat > setup.sh <<'EOF'\necho KEY=1 > .env\nEOF",
                    "cat > README.md <<EOF\nrm -rf . deletes all\nEOF\nls", "cat <<-END > notes.md\n\tgit push\n\tEND",
                    "tee -a .gitignore <<< .env"):
            self.assertIsNone(self.bash(cmd), cmd)
        self.assertDenied(self.bash("cat > x.md <<'EOF'\ntext\nEOF\ngit push"))  # after the body, commands again
        self.assertDenied(self.bash("cat > .env <<'EOF'\nKEY=1\nEOF"))  # the heredoc's own target still counts

    def test_symlinked_and_differently_cased_paths(self):
        link = Path(self.tmp.name + "-link")
        link.symlink_to(self.root)
        self.addCleanup(link.unlink)
        for p in (link / ".env", link / ".herd/tasks/t1/evidence.json", self.root / ".ENV", self.root / "x.PEM",
                  self.root / ".herd/tasks/t1/Evidence.json"):
            self.assertDenied(self.edit(p), p)
        self.assertDenied(self.bash(f"echo x > {link}/.env"))

    def test_the_task_is_found_from_outside_its_folder(self):
        elsewhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, elsewhere)
        nested = self.root / "vendor/lib"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        cases = [({"cwd": elsewhere, "tool_name": "Write", "tool_input": {"file_path": str(self.root / ".env")}}, {}),
                 ({"cwd": elsewhere, "tool_name": "Bash", "tool_input": {"command": f"cd {self.root} && git push"}}, {}),
                 ({"cwd": elsewhere, "tool_name": "Bash", "tool_input": {"command": "git push"}},
                  {"CLAUDE_PROJECT_DIR": str(self.root)}),
                 ({"cwd": str(nested), "tool_name": "Bash", "tool_input": {"command": "git push"}}, {})]
        for hook, env in cases:
            with self.subTest(hook=hook), mock.patch.dict("os.environ", env):
                root = herd.guard_root(hook)
                self.assertEqual(root, self.root)
                self.assertDenied(herd.guard(root, hook))
                p = subprocess.run([sys.executable, str(Path(herd.__file__)), "guard"], cwd=elsewhere,
                                   input=json.dumps(hook), capture_output=True, text=True,
                                   env={**__import__("os").environ, **env})
                self.assertIn('"deny"', p.stdout, p.stderr)
        self.assertIsNone(herd.guard_root({"cwd": elsewhere, "tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertIsNone(herd.guard_line([{"kind": "guard"}][:0]))
        self.assertEqual(herd.guard_line([{"kind": "guard"}]), "Guard: 1 denied (? x1)")


class TestGuardReviewFindings(Base):
    """Regression tests for the fresh-context review of the guard."""

    def test_a_denial_stays_a_denial_when_the_note_cannot_be_written(self):
        with mock.patch.object(herd, "add_note", side_effect=PermissionError("read-only")):
            self.assertDenied(self.bash("git push"))
        self.assertDenied(self.bash("chmod 444 .herd/tasks/t1/notes.jsonl"))

    def test_env_files_anywhere_and_templates_editable(self):
        for p in ("apps/web/.env", "config/.env.prod", ".env.local"):
            self.assertDenied(self.edit(self.root / p), p)
        for p in (".env.example", "apps/web/.env.sample", ".env.template", ".env.dist"):
            self.assertIsNone(self.edit(self.root / p), p)

    def test_wrappers_and_quoted_substitutions(self):
        for cmd in ("timeout 120 git push origin HEAD", "timeout -s KILL 5m git push", "nice git push",
                    "nice -n 10 git push", "xargs git push", "xargs -I {} git push", 'x="$(git push 2>&1)"',
                    'git commit -m "x `git push`"', "git stash clear", "git stash drop", "git switch -f main",
                    "git switch --discard-changes main"):
            self.assertDenied(self.bash(cmd), cmd)
        for cmd in ("git restore --staged .", "git restore -S .", "rm -rf ''", "timeout 5 ls", "git stash list",
                    "git switch main", 'echo "$(date)"'):
            self.assertIsNone(self.bash(cmd), cmd)
        self.assertDenied(self.bash("git restore --staged --worktree ."))

    def test_odd_input_never_prints_a_traceback(self):
        deep = '{"a":' * 20000 + "1" + "}" * 20000
        for stdin in (deep, "\x00", "{" * 50000):
            p = self.cli(stdin)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
            self.assertLessEqual(len(p.stderr.strip().splitlines()), 1, p.stderr[-300:])

    def test_base_and_pr_are_state_and_reasons_name_the_herd_folder(self):
        for name in ("base", "pr"):
            reason = self.assertDenied(self.edit(self.root / ".herd/tasks/t1" / name))
            self.assertIn(f"`.herd/tasks/t1/{name}`", reason)

    def test_guard_notes_do_not_crowd_the_pr_notes(self):
        for _ in range(herd.MAX_PR_NOTES + 5):
            self.bash("git push")
        herd.add_note(self.root, "t1", "found", "a real caveat")
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "a task"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "agent-proposed"\ncheck = "python3 -c 1"\n')
        herd.verify(self.root, "t1")
        body = herd.pr_body(self.root, "t1")
        self.assertIn("a real caveat", body)
        self.assertIn(f"Guard: {herd.MAX_PR_NOTES + 5} denied (git push x{herd.MAX_PR_NOTES + 5})", body)


class TestGuardRound2(Base):
    """Regression tests for the round-2 review of the guard."""

    def test_cd_earlier_in_the_chain_moves_relative_paths(self):
        (self.root / "apps").mkdir()
        (self.root / "build").mkdir()
        for cmd in ("cd .herd/tasks/t1 && rm evidence.json", "cd .herd && rm active", "cd apps && echo X=1 > ../.env",
                    "pushd .herd/tasks/t1 && rm notes.jsonl", "cd apps; cd ..; rm -rf ."):
            self.assertDenied(self.bash(cmd), cmd)
        self.assertDenied(self.bash("cd build && rm -rf ./*"))  # the folder you are in: the rule as written
        self.assertIsNone(self.bash("cd build && rm -rf ./tmp"))

    def test_a_worktree_inside_the_checkout_has_its_own_tasks(self):
        tree = self.root / ".claude/worktrees/other"
        git(self.root, "worktree", "add", "-q", "-b", "other", str(tree))
        hook = {"cwd": str(tree), "tool_name": "Bash", "tool_input": {"command": "git push origin other"}}
        self.assertIsNone(herd.guard_root(hook))  # the main checkout's task does not reach into the worktree
        sub = self.root / "vendor/lib"
        sub.mkdir(parents=True)
        git(sub, "init", "-q")  # a nested repository that is part of the project still is
        self.assertEqual(herd.guard_root(dict(hook, cwd=str(sub))), self.root)

    def test_dry_runs_help_and_option_values_are_allowed(self):
        for cmd in ("git clean -fdn", "git clean -f --dry-run", "gh pr merge --help", "git push --help",
                    "git commit -m '-n'", "git commit -m -n", "git commit --message=-n"):
            self.assertIsNone(self.bash(cmd), cmd)
        self.assertDenied(self.bash("git commit -m x -n"))

    def test_more_write_commands(self):
        for cmd in ("ln -sf /dev/null .herd/tasks/t1/evidence.json", "dd if=/dev/zero of=.env", "install x .env",
                    "rsync x .env", "git rm .env", "git rm -f .herd/tasks/t1/notes.jsonl"):
            self.assertDenied(self.bash(cmd), cmd)
        self.assertIsNone(self.bash("ln -s .env link-to-read"))  # the link is new; .env is only read


class TestGuardRound3(Base):
    """Regression tests for the round-3 review of the guard."""

    def test_a_comment_ends_at_its_line(self):
        for cmd in ("# push the branch\ngit push", "pytest -q  # run tests\ngit reset --hard", "# clean up\nrm -rf .",
                    "ls # list\necho hi > .env", "echo a#b && git push", "git log --grep=#3 && git push",
                    "sed -i s#a#b# .env", "git commit -m '#3 fix' && git push", 'echo "# not a comment" ; git push'):
            self.assertDenied(self.bash(cmd), cmd)
        for cmd in ("echo a\\ #b ; git push", "echo \\;# ; git push", "echo \\|#x && git reset --hard",
                    "echo $'don\\'t' # see <<X\ngit push", "cat <<EOF > n.md\ndon't\nEOF\n# use <<END, it's fine\ngit push",
                    "cat <<'A' > x\n# heading\nA\ngit push", "cat <<A <<B\none\nA\ntwo\nB\ngit push",
                    'git commit -m "$(printf "Fix #12")" && git push origin HEAD', "n=2; echo $((1<<n))\ngit push",
                    "(( x <<y ))\ngit push", "cat <<NEVER\ntext\ngit push", "echo \"$(echo 'a # b')\" && git push"):
            self.assertDenied(self.bash(cmd), cmd)
        for cmd in ("npm test # ok && git push", "# git push", "ls\n  # rm -rf .\nls",
                    "cat <<EOF > n.md\ngit push in the docs\nEOF",
                    "git commit -m \"$(cat <<'EOF'\nFix #3: git push is now denied\nEOF\n)\"",
                    "cat <<\\EOF > a.md\ngit push\nEOF"):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_round_3_nits(self):
        (self.root / "herd.toml").write_text('[guard]\ndeny_commands = ["./deploy.sh", "scripts/release.sh --prod"]\n')
        for cmd in ("rm -rf */", "gh pr -R o/r merge 1", "./deploy.sh now", "scripts/release.sh --prod"):
            self.assertDenied(self.bash(cmd), cmd)
        for cmd in ("git rm --cached .env", "git commit -m x -- -n", "scripts/release.sh --dev"):
            self.assertIsNone(self.bash(cmd), cmd)


class TestWiring(unittest.TestCase):
    def test_guard_hook_is_registered(self):
        entries = json.loads(HOOKS.read_text())["hooks"]["PreToolUse"]
        guard = [h for e in entries for h in e["hooks"] if h["command"].endswith('herd.py" guard')]
        self.assertEqual(len(guard), 1)
        self.assertEqual(guard[0]["timeout"], 10)
        matcher = next(e["matcher"] for e in entries if guard[0] in e["hooks"])
        self.assertEqual(set(matcher.split("|")), {"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"})
        src = Path(herd.__file__).read_text()
        self.assertIn('"guard"', src.split("import hashlib", 1)[0])  # leaves early on an old Python


if __name__ == "__main__":
    unittest.main()


class TestInstalledPlugin(Base):
    def test_the_installed_plugin_is_protected(self):
        plugin = Path(self.tmp.name + "-plugin")
        (plugin / "skills").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, plugin)
        hook = {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": str(plugin / "skills/x.md")}}
        with mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(plugin)}):
            self.assertEqual(herd.guard(self.root, hook)["hookSpecificOutput"]["permissionDecision"], "deny")
        inside = dict(hook, tool_input={"file_path": str(self.root / "skills/x.md")})
        with mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(self.root)}):  # developing Herd itself
            self.assertIsNone(herd.guard(self.root, inside))
