"""Issue #122: the guard denies a Herd subagent that would run in the background."""
import json
import random
import shutil
import string
import unittest

from scripts import herd
from tests.test_herd_guard import HOOKS, Base

HERD = ("herd:herd-builder", "herd:herd-designer")
ABSENT = object()
VALUES = (ABSENT, True, False, None, 0, 1, "false", "False", "", [], {})
OTHERS = ("general-purpose", "Explore", "fork", "herd-builder", "other:herd-designer", "herd:herd-builder-2",
          "HERD:HERD-BUILDER", "herd:herd-builder ", "", None, 3, ["herd:herd-builder"], {"a": 1}, ABSENT)


def call(root, kind, background=ABSENT, tool="Agent"):
    inp = {"description": "b", "prompt": "x"}
    if kind is not ABSENT:
        inp["subagent_type"] = kind
    if background is not ABSENT:
        inp["run_in_background"] = background
    return {"cwd": str(root), "tool_name": tool, "tool_input": inp}


class AgentBase(Base):
    def spawn(self, kind, background=ABSENT):
        return herd.guard(self.root, call(self.root, kind, background))

    def guard_notes(self):
        path = self.root / ".herd/tasks/t1/notes.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        return [n for n in map(json.loads, lines) if n["kind"] == "guard"]


class TestAgentSpawn(AgentBase):
    def test_background_herd_agents_are_denied_with_one_line_naming_the_fix(self):
        for kind in HERD:
            for value in VALUES:
                out = self.spawn(kind, value)
                if value is False:
                    self.assertIsNone(out, kind)
                    continue
                reason = self.assertDenied(out, (kind, value))
                self.assertEqual(len(reason.splitlines()), 1)
                self.assertIn(f"`{kind}`", reason)
                self.assertIn("`run_in_background: false`", reason)

    def test_other_subagent_types_pass(self):
        for kind in OTHERS:
            for value in VALUES:
                self.assertIsNone(self.spawn(kind, value), (kind, value))
        self.assertEqual(self.guard_notes(), [])


class TestNoTask(AgentBase):
    def test_denied_with_no_task_and_nothing_is_written(self):
        shutil.rmtree(self.root / ".herd")
        for kind in HERD:
            hook = call(self.root, kind)
            p = self.cli(json.dumps(hook))
            self.assertEqual((p.returncode, p.stderr), (0, ""))
            self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
            p = self.cli(json.dumps(call(self.root, kind, False)))
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        p = self.cli(json.dumps(call(self.root, "Explore")))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        for command in ("git push", 'echo "Agent"'):  # naming Agent leaves the fast path; still nothing to deny
            p = self.cli(json.dumps({"cwd": str(self.root), "tool_name": "Bash",
                                     "tool_input": {"command": command, "description": "Agent"}}))
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.assertFalse((self.root / ".herd").exists())

    def test_cancelled_task_still_denies_without_a_note(self):
        herd.cancel_task(self.root, "t1", "dropped")
        self.assertDenied(self.spawn(HERD[0]))
        self.assertEqual(self.guard_notes(), [])


class TestBadInput(AgentBase):
    def test_malformed_hook_input_never_crashes(self):
        for bad in ("", "{not json", "[1]", '"Agent"', '{"tool_name":"Agent"}', '{"tool_name":"Agent","tool_input":5}',
                    '{"tool_name":"Agent","tool_input":{"subagent_type":["herd:herd-builder"]}}',
                    '{"tool_name":"Agent","cwd":7,"tool_input":{}}', "[" * 100000 + '"Agent"'):
            p = self.cli(bad)
            self.assertEqual((p.returncode, p.stdout), (0, ""), bad[:80])
            self.assertNotIn("Traceback", p.stderr)

    def test_broken_config_and_unwritable_notes_still_deny(self):
        (self.root / "herd.toml").write_text("[guard\n")
        notes = self.root / ".herd/tasks/t1/notes.jsonl"
        notes.unlink(missing_ok=True)
        notes.mkdir()
        p = self.cli(json.dumps(call(self.root, HERD[0])))
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


class TestRecount(AgentBase):
    def test_every_denial_is_counted_once(self):
        rng = random.Random(122)
        denied = []
        for _ in range(60):
            kind, value = rng.choice(HERD + ("Explore",)), rng.choice(VALUES)
            if self.spawn(kind, value):
                denied.append(kind)
        notes = self.guard_notes()
        self.assertEqual(len(notes), len(denied))
        line = herd.guard_line(notes)
        self.assertIn(f"Guard: {len(denied)} denied", line)
        for kind in HERD:
            self.assertIn(f"background {kind} x{denied.count(kind)}", line)


class TestRefusal(AgentBase):
    def test_generated_calls_match_a_plain_oracle(self):
        rng = random.Random(7)
        for _ in range(400):
            kind = rng.choice(HERD + OTHERS + ("".join(rng.choices(string.printable, k=rng.randint(1, 30))),))
            value = rng.choice(VALUES)
            tool = rng.choice(("Agent", "Agent", "Read", "Task"))
            want = tool == "Agent" and (kind == HERD[0] or kind == HERD[1]) and value is not False
            got = herd.guard(self.root, call(self.root, kind, value, tool))
            self.assertEqual(got is not None, want, (kind, value, tool))


class TestRegistered(unittest.TestCase):
    def test_the_guard_matcher_names_agent(self):
        entries = json.loads(HOOKS.read_text())["hooks"]["PreToolUse"]
        matcher = next(e["matcher"] for e in entries if e["hooks"][0]["command"].endswith('herd.py" guard'))
        self.assertIn("Agent", matcher.split("|"))


del Base  # imported for AgentBase only
if __name__ == "__main__":
    unittest.main()
