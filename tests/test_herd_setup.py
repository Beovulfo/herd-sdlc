"""`herd setup`: Herd for Codex and other agents that read AGENTS.md, run without Claude Code."""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERD = REPO / "scripts" / "herd.py"
SKILLS = ("herd-run", "herd-criteria", "herd-evidence")
RUN_REFS = ("quick.md", "worktree.md", "adversarial.md", "pr.md")
HERD_CMD = re.compile(r'python3 "([^"]*herd\.py)"')
# Codex's Stop hook input (codex-rs/hooks/schema/generated/stop.command.input.schema.json): all required fields
STOP_FIELDS = {"session_id": "s1", "turn_id": "t1", "transcript_path": None, "hook_event_name": "Stop",
               "model": "local-model", "permission_mode": "default", "stop_hook_active": False,
               "last_assistant_message": "done"}
# the properties Codex's Stop output schema allows (stop.command.output.schema.json, additionalProperties false)
STOP_OUTPUT = {"continue", "decision", "reason", "stopReason", "suppressOutput", "systemMessage"}


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def new_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "README.md").write_text("x\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.codex = t / "home", t / "codex-home"
        self.home.mkdir()
        self.project = new_repo(t / "project")
        # no Claude Code anywhere: no plugin root, a fresh HOME and CODEX_HOME
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        self.env.update(HOME=str(self.home), CODEX_HOME=str(self.codex))

    def tearDown(self):
        self.tmp.cleanup()

    def setup_cmd(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(HERD), "setup", *args], cwd=cwd or self.project,
                              env=self.env, capture_output=True, text=True)

    def places(self, mode):
        """(skills dir, AGENTS.md, hooks.json) that `herd setup` writes in each mode."""
        if mode == "user":
            return self.home / ".agents/skills", self.codex / "AGENTS.md", self.codex / "hooks.json"
        return self.project / ".agents/skills", self.project / "AGENTS.md", self.project / ".codex/hooks.json"

    def run_setup(self, mode):
        p = self.setup_cmd(*(["--user"] if mode == "user" else []))
        self.assertEqual(p.returncode, 0, p.stderr)
        return self.places(mode)

    def gate_command(self, hooks_json):
        data = json.loads(hooks_json.read_text())
        cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g.get("hooks", [])
                if isinstance(h, dict) and "herd.py" in h["command"]]
        self.assertEqual(len(cmds), 1, cmds)
        return cmds[0]

    def sh(self, cmd, cwd, stdin=None):
        return subprocess.run(cmd, shell=True, cwd=cwd, env=self.env, input=stdin, capture_output=True, text=True)

    def stop(self, hooks_json, cwd):
        """Run the Stop hook command exactly as Codex would: through the shell, Codex's JSON on stdin."""
        payload = json.dumps(dict(STOP_FIELDS, cwd=str(cwd)))
        return self.sh(self.gate_command(hooks_json), cwd=self.home, stdin=payload)


class TestRender(Base):
    def test_skills_render_for_any_agent(self):
        for mode in ("user", "project"):
            with self.subTest(mode=mode):
                skills, _, _ = self.run_setup(mode)
                names = []
                for name in SKILLS:
                    text = (skills / name / "SKILL.md").read_text()
                    front = re.search(r"^---\n(.*?)\n---\n", text, re.S).group(1)
                    names.append(re.search(r"^name: (\S+)$", front, re.M).group(1))
                    self.assertRegex(front, r"(?m)^description: \S")
                    files = [skills / name / "SKILL.md"] + ([skills / name / r for r in RUN_REFS]
                                                             if name == "herd-run" else [])
                    for f in files:
                        body = f.read_text()
                        self.assertNotIn("CLAUDE_PLUGIN_ROOT", body, f)
                        self.assertNotRegex(body, r"/?herd:(run|criteria|evidence)\b", f)
                        for path in HERD_CMD.findall(body):
                            self.assertEqual(Path(path), HERD, f)
                    self.assertTrue(HERD_CMD.search(text), name)
                    for link in re.findall(r"\]\(([\w.-]+\.md)\)", text):  # relative links still resolve
                        self.assertTrue((skills / name / link).exists(), link)
                self.assertEqual(names, list(SKILLS))
                self.assertIn("herd-criteria", (skills / "herd-run/SKILL.md").read_text())

    def test_project_mode_keeps_rendered_skills_out_of_commits(self):
        self.run_setup("project")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.project,
                                capture_output=True, text=True).stdout
        self.assertNotIn(".agents/skills/herd-", status)

    def test_setup_prints_what_it_wrote_and_the_trust_step(self):
        p = self.setup_cmd("--user")
        self.assertIn(str(self.codex / "hooks.json"), p.stdout)
        self.assertIn("/hooks", p.stdout)

    def test_bad_arguments(self):
        p = self.setup_cmd("--bogus")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("usage: herd setup", p.stderr)
        self.assertNotIn("Traceback", p.stderr)


class TestCodexHook(Base):
    def test_stop_hook_blocks_then_allows(self):
        _, _, hooks = self.run_setup("user")
        data = json.loads(hooks.read_text())
        self.assertLessEqual(set(data), {"description", "hooks"})  # Codex HooksFile denies unknown fields
        handler = [h for g in data["hooks"]["Stop"] for h in g["hooks"] if "herd.py" in h["command"]][0]
        self.assertEqual(handler["type"], "command")
        self.assertIsInstance(handler["timeout"], int)
        herd = f"{shlex.quote(sys.executable)} {shlex.quote(str(HERD))}"
        check = "python3 -c \"import pathlib,sys; sys.exit(not pathlib.Path('ok.txt').exists())\""
        p = self.sh(f"{herd} init q 'Write ok.txt' --quick {shlex.quote(check)}", cwd=self.project)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.sh(f"{herd} verify", cwd=self.project)
        sub = self.project / "src"
        sub.mkdir()
        p = self.stop(hooks, sub)  # Codex passes the session cwd, which may be a subfolder
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertLessEqual(set(out), STOP_OUTPUT)
        self.assertEqual(out["decision"], "block")
        self.assertIn("`q`", out["reason"])
        (self.project / "ok.txt").write_text("ok")
        self.sh(f"{herd} verify", cwd=self.project)
        self.assertEqual(self.sh(f"{herd} done", cwd=self.project).returncode, 0)
        p = self.stop(hooks, self.project)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, ""))  # empty stdout lets Codex stop

    def test_no_task_no_block(self):
        _, _, hooks = self.run_setup("project")
        p = self.stop(hooks, self.project)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, ""))


class TestMerge(Base):
    BLOCK = "<!-- herd:start"

    def test_user_content_survives_and_rerun_adds_nothing(self):
        _, agents, hooks = self.places("project")
        agents.write_text("# Mine\n\nkeep me\n")
        hooks.parent.mkdir()
        mine = {"description": "my hooks", "hooks": {
            "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo post"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        hooks.write_text(json.dumps(mine))
        self.run_setup("project")
        first = (agents.read_text(), hooks.read_text())
        self.run_setup("project")
        self.assertEqual((agents.read_text(), hooks.read_text()), first)
        text = agents.read_text()
        self.assertTrue(text.startswith("# Mine\n\nkeep me\n"))
        self.assertEqual(text.count(self.BLOCK), 1)
        data = json.loads(hooks.read_text())
        self.assertEqual(data["description"], "my hooks")
        self.assertEqual(data["hooks"]["PostToolUse"], mine["hooks"]["PostToolUse"])
        stop_cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
        self.assertIn("echo mine", stop_cmds)
        self.assertEqual(sum("herd.py" in c for c in stop_cmds), 1)

    def test_moved_herd_copy_replaces_the_old_entry(self):
        _, agents, hooks = self.places("user")
        self.codex.mkdir()
        agents.write_text('top\n<!-- herd:start old -->\npython3 "/old/scripts/herd.py"\n<!-- herd:end -->\nbottom\n')
        hooks.write_text(json.dumps({"hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "python3 '/old/scripts/herd.py' gate", "timeout": 30}]}]}}))
        self.run_setup("user")
        text = agents.read_text()
        self.assertNotIn("/old/", text)
        self.assertTrue(text.startswith("top\n") and text.endswith("bottom\n"), text)
        self.assertNotIn("/old/", hooks.read_text())
        self.assertIn(str(HERD), self.gate_command(hooks))

    def test_malformed_hooks_json_is_refused_unchanged(self):
        skills, agents, hooks = self.places("project")
        hooks.parent.mkdir()
        for bad in ("{not json", '{"hooks": []}', '{"hooks": {"Stop": {}}}', "[]"):
            with self.subTest(bad=bad):
                hooks.write_text(bad)
                p = self.setup_cmd()
                self.assertEqual(p.returncode, 1)
                self.assertIn("hooks.json", p.stderr)
                self.assertNotIn("Traceback", p.stderr)
                self.assertEqual(hooks.read_text(), bad)
                self.assertFalse(agents.exists())  # nothing is half-written
                self.assertFalse((skills / "herd-run").exists())


class TestAttacks(Base):
    def refused(self, *args):
        p = self.setup_cmd(*args)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertTrue(p.stderr.startswith("herd: "), p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        return p.stderr

    def test_bad_input_at_every_entry_point(self):
        skills, agents, hooks = self.places("project")
        for args in (["--user", "--user"], ["extra"], ["--user", "x"]):  # arguments
            p = self.setup_cmd(*args)
            self.assertEqual(p.returncode, 1)
            self.assertIn("usage: herd setup", p.stderr)
        hooks.mkdir(parents=True)  # hooks.json is a folder
        self.assertIn("hooks.json", self.refused())
        hooks.rmdir()
        agents.mkdir()  # AGENTS.md is a folder: refused before anything is written
        self.assertIn("AGENTS.md", self.refused())
        self.assertFalse((skills / "herd-run").exists())
        self.assertFalse(hooks.exists())
        agents.rmdir()
        agents.write_bytes(b"\xff\xfe bad bytes")  # not text
        self.assertIn("AGENTS.md", self.refused())
        agents.unlink()
        hooks.write_bytes(b"\xff\xfe")
        self.assertIn("hooks.json", self.refused())
        hooks.unlink()
        hooks.parent.chmod(0o500)  # cannot write
        try:
            if not os.access(hooks.parent, os.W_OK):  # root can write anyway
                self.assertIn(".codex", self.refused())
        finally:
            hooks.parent.chmod(0o700)

    def test_collision_herd_entries_and_names(self):
        skills, agents, hooks = self.places("user")
        self.codex.mkdir()
        (skills / "run").mkdir(parents=True)  # the user's own skill called run
        (skills / "run" / "SKILL.md").write_text("---\nname: run\ndescription: mine\n---\n")
        block = "<!-- herd:start x -->\nold\n<!-- herd:end -->"
        agents.write_text(f"a\n{block}\nb\n{block}\nc\n")  # two Herd blocks
        gate = {"type": "command", "command": "python3 /x/scripts/herd.py gate"}
        hooks.write_text(json.dumps({"hooks": {"Stop": [
            {"hooks": [gate, {"type": "command", "command": "echo mine"}]},  # shares a group with a user hook
            {"hooks": [dict(gate, command='python3 "/y/scripts/herd.py" gate')]}]}}))
        self.run_setup("user")
        text = agents.read_text()
        self.assertEqual(text.count("<!-- herd:start"), 1)
        self.assertNotIn("\nold\n", text)
        for kept in ("a\n", "\nb\n", "\nc\n"):
            self.assertIn(kept, text)
        stop = json.loads(hooks.read_text())["hooks"]["Stop"]
        cmds = [h["command"] for g in stop for h in g["hooks"]]
        self.assertEqual(sum("herd.py" in c for c in cmds), 1)
        self.assertIn("echo mine", cmds)
        self.assertEqual((skills / "run" / "SKILL.md").read_text(), "---\nname: run\ndescription: mine\n---\n")

    def test_one_bad_part_elsewhere_in_hooks_json_is_kept(self):
        _, _, hooks = self.places("project")
        hooks.parent.mkdir()
        odd = {"PostToolUse": "not a list", "Stop": [{"hooks": ["not a handler"]}, {"matcher": "x"}]}
        hooks.write_text(json.dumps({"hooks": odd}))
        self.run_setup("project")
        stop = json.loads(hooks.read_text())["hooks"]
        self.assertEqual(stop["PostToolUse"], "not a list")
        self.assertEqual(stop["Stop"][:2], odd["Stop"])
        self.assertEqual(len(stop["Stop"]), 3)
        p = self.stop(hooks, self.project)  # Herd's own entry still works
        self.assertEqual(p.returncode, 0, p.stderr)


class TestEndToEnd(Base):
    """A whole Herd task through the rendered instructions only, the way Codex or an open model would run it."""

    def flow(self, mode):
        skills, agents, hooks = self.run_setup(mode)
        guide = agents.read_text()
        self.assertIn("herd done", guide)
        self.assertIn(str(skills / "herd-run" / "SKILL.md"), guide)  # agents without skill support read it by path
        herd = HERD_CMD.search((skills / "herd-run" / "SKILL.md").read_text()).group(0)
        self.assertIn(herd, guide)
        (self.project / "greet.py").write_text("def greet(name):\n    return ''\n")
        (self.project / "test_greet.py").write_text(
            "import unittest\nfrom greet import greet\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_hello(self):\n        self.assertEqual(greet('Ann'), 'hello Ann')\n"
            "    def test_bad(self):\n        self.assertRaises(TypeError, greet, None)\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "greet stub")
        p = self.sh(f"{herd} init greet 'Greet by name' --request 'greet people by name'", cwd=self.project)
        self.assertEqual(p.returncode, 0, p.stderr)
        task = self.project / ".herd/tasks/greet/task.toml"
        task.write_text('goal = "Greet by name"\n\n[[criteria]]\nid = "C1"\ntext = "greet people by name"\n'
                        'source = "human"\ncoverage = "one name; not unicode names"\n'
                        'check = "python3 -m unittest test_greet"\n')
        self.assertEqual(self.sh(f"{herd} check", cwd=self.project).returncode, 0)
        self.assertEqual(self.sh(f"{herd} verify", cwd=self.project).returncode, 1)  # red first
        self.assertEqual(json.loads(self.stop(hooks, self.project).stdout)["decision"], "block")
        (self.project / "greet.py").write_text(
            "def greet(name):\n    if not isinstance(name, str):\n        raise TypeError('name')\n"
            "    return 'hello ' + name\n")
        test = "python3 -m unittest test_greet"
        for attack in ("bad-input", "recount"):
            p = self.sh(f"{herd} note --tried --attack {attack} --check {shlex.quote(test)} 'covered'", self.project)
            self.assertEqual(p.returncode, 0, p.stderr)
        for attack in ("collision", "one-bad-part"):
            self.sh(f"{herd} note --tried --attack {attack} 'n/a: one value'", cwd=self.project)
        self.assertEqual(self.sh(f"{herd} done", cwd=self.project).returncode, 1)  # no fresh evidence yet
        p = self.sh(f"{herd} verify", cwd=self.project)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.sh(f"{herd} done", cwd=self.project)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("1 of 1 criteria proven", p.stdout)
        self.assertTrue((self.project / ".herd/tasks/greet/evidence.md").exists())
        self.assertEqual(self.stop(hooks, self.project).stdout.strip(), "")

    def test_codex_user_install(self):
        self.flow("user")

    def test_project_install_for_isolated_codex_homes_and_other_agents(self):
        # `unsloth start codex` runs Codex with its own home, so only project files are read there
        self.flow("project")


class TestDocs(unittest.TestCase):
    def test_readme_says_what_works_where(self):
        readme = (REPO / "README.md").read_text()
        section = readme.split("## Other agents", 1)[1].split("\n## ", 1)[0]
        for word in ("Claude Code", "Codex", "Unsloth", "AGENTS.md", "herd setup", "--user", "/hooks", "Stop gate"):
            self.assertIn(word, section, word)

    def test_version_agrees(self):
        version = json.loads((REPO / ".claude-plugin/plugin.json").read_text())["version"]
        top = re.search(r"^## (\S+)", (REPO / "CHANGELOG.md").read_text(), re.M).group(1)
        self.assertEqual(top, version)
        self.assertIn(f"Version {version} ", (REPO / "README.md").read_text())
        self.assertNotEqual(version, "0.3.2")


if __name__ == "__main__":
    unittest.main()
