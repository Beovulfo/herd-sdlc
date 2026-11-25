"""Arm files drive the eval; hostile arm files; skills and the challenger's own call. No model call."""
import contextlib
import io
import json
import os
import random
import shlex
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import armfile
import judge
import money
import run_eval
from test_eval import PROMPT, FakeClaude

TASK_TOML = '''goal = "g"
known_limits = "only small inputs"
[[inputs]]
human = "HUMAN WORDS"
program = "a file of rows"
[[criteria]]
id = "C1"
text = "it prints the total"
'''


class TaskClaude(FakeClaude):
    def start(self, cmd, run_dir, log, err, env):
        proc = super().start(cmd, run_dir, log, err, env)
        if "--resume" not in cmd:
            (Path(run_dir) / "work" / ".herd" / "tasks" / "t" / "task.toml").write_text(TASK_TOML)
        return proc


def quiet(call, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            return call(*args, **kw), out.getvalue()
        except SystemExit as e:
            return e.code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.env = {"HOME": str(self.tmp / "home"), "PATH": os.environ["PATH"]}
        self.asked = []

    def folder(self, *arms):
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        for arm in arms:
            (folder / f"{arm['name']}.json").write_text(json.dumps(arm))
        return folder

    def arm(self, name="new-arm", **change):
        return {"name": name, "when": "after-red", "sees": ["request"], "instruction": "ASK THIS", **change}

    def skill(self, text="---\nname: adhd\n---\n", rel="home/.claude/skills/adhd/SKILL.md"):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_arms(self, folder, fake=None, runs=1, argv=()):
        ns = run_eval.parse(["--runs", str(runs), "--herd-tag", "HEAD", "--poll", "0", "--timeout", "5", *argv])

        def ask(arm, prompt):
            self.asked.append((arm["name"], prompt))
            return "1. why?", 0.5

        fake = fake or TaskClaude()
        ev = run_eval.Eval(ns, self.env, self.tmp / "root", armfile.load_arms(folder), start=fake.start,
                           stop=fake.stop, call=ask)
        quiet(ev.run, {"supermarket-route": PROMPT})
        return ev.results / "supermarket-route", fake


class TestArmFromData(Base):
    def test_arm_from_data_when_sees_and_instruction_come_from_the_file(self):
        for when, held in (("after-red", False), ("before-attacks", True)):
            self.asked, self.tmp = [], self.tmp / when
            self.tmp.mkdir()
            arm = self.arm(when=when, sees=["inputs_program", "known_limits", "criteria"])
            out, fake = self.run_arms(self.folder(arm))
            (name, asked), = self.asked
            self.assertEqual(name, "new-arm")
            self.assertTrue(asked.startswith("ASK THIS"))
            for want in ("a file of rows", "only small inputs", "it prints the total"):
                self.assertIn(want, asked)
            for hidden in ("HUMAN WORDS", PROMPT):
                self.assertNotIn(hidden, asked)
            self.assertEqual(fake.hooked[0], held)
            resume = fake.commands[-1][2]
            self.assertEqual("write your attacks" in resume, held)
            self.assertIn("1. why?", resume)
            record = json.loads((out / "new-arm" / "run-1" / "run.json").read_text())
            self.assertEqual((record["status"], record["cost"]["challenger"]), ("ok", 0.5))

    def test_arm_from_data_none_asks_nobody_and_request_is_the_case_prompt(self):
        out, fake = self.run_arms(self.folder(self.arm("control", when="none", sees=[], instruction=""),
                                              self.arm()))
        self.assertEqual([n for n, _ in self.asked], ["new-arm"])
        self.assertIn(PROMPT, self.asked[0][1])
        self.assertNotIn("only small inputs", self.asked[0][1])
        self.assertEqual(sum("--resume" not in c for c in fake.commands), 1, "both fork one start")

    def test_arm_from_data_command_line_runs_a_new_file(self):
        folder = self.folder(self.arm("made-today"))
        code, out = quiet(run_eval.main, ["--case", "supermarket-route", "--runs", "1", "--dry-run",
                                          "--arms", str(folder), "--arm", "made-today"], env=self.env)
        self.assertEqual(code, 0, out)
        self.assertIn("session for made-today", out)

    def test_arm_from_data_a_missing_field_says_none_stated(self):
        task = self.tmp / "task.toml"
        task.write_text("goal = 'g'\n")
        arm = self.arm(sees=["known_limits"])
        self.assertIn("(none stated)", run_eval.challenger_input(arm, PROMPT, task))
        task.write_text("not [ toml")
        with self.assertRaises(judge.Refused):
            run_eval.challenger_input(arm, PROMPT, task)


class TestShipped(Base):
    def test_shipped_arms_have_the_asked_settings(self):
        arms = armfile.load_arms()
        design = ["request", "inputs_program", "known_limits"]
        want = {"control": ("none", []), "generic-after-red": ("after-red", ["request"]),
                "generic-before-attacks": ("before-attacks", ["request"]),
                "design-aware-before-attacks": ("before-attacks", design),
                "limit-cost-before-attacks": ("before-attacks", design),
                "adhd-before-attacks": ("before-attacks", ["request"])}
        self.assertEqual({n: (a["when"], a["sees"]) for n, a in arms.items()}, want)
        self.assertEqual(arms["generic-after-red"]["instruction"], arms["generic-before-attacks"]["instruction"])
        self.assertEqual(arms["adhd-before-attacks"]["tools"], "Agent,Skill")
        self.assertEqual(arms["adhd-before-attacks"]["skills"], ["~/.claude/skills/adhd/SKILL.md"])
        for name, arm in arms.items():
            if name != "adhd-before-attacks":
                self.assertEqual((arm.get("tools"), arm.get("skills")), (None, None), name)
        self.assertIn("what does this limit cost them, and should it be a limit at all?",
                      arms["limit-cost-before-attacks"]["instruction"])


class TestSkill(Base):
    def test_skill_is_copied_into_the_challengers_project_with_the_tools(self):
        self.skill("SKILL BODY")
        arm = self.arm(tools="Agent,Skill", skills=["~/.claude/skills/adhd/SKILL.md"])
        seen = {}

        def fake(cmd, **kw):
            seen["cmd"] = cmd
            seen["skill"] = (Path(kw["cwd"]) / ".claude" / "skills" / "adhd" / "SKILL.md").read_text()
            events = [{"type": "assistant", "message": {"content": [
                          {"type": "tool_use", "name": "Skill", "input": {"skill": "adhd"}}]}},
                      {"type": "result", "result": "1. q", "total_cost_usd": 0.4}]
            return mock.Mock(stdout="\n".join(map(json.dumps, events)))

        with mock.patch.object(run_eval.subprocess, "run", fake):
            self.assertEqual(run_eval.ask_challenger("m", arm, "p", self.env, 1, 5), ("1. q", 0.4))
        self.assertEqual(seen["skill"], "SKILL BODY")
        for flag in ("--tools", "--allowedTools"):
            self.assertEqual(seen["cmd"][seen["cmd"].index(flag) + 1], "Agent,Skill")

    def test_skill_not_used_fails_the_run(self):
        stream = json.dumps({"type": "result", "result": "1. q", "total_cost_usd": 0.1})
        with self.assertRaisesRegex(judge.Refused, "never used the skill adhd"):
            run_eval.challenger_reply(stream, ["adhd"])

    def test_skill_missing_skips_the_arm_with_a_message(self):
        argv = ["--case", "supermarket-route", "--runs", "1", "--dry-run"]
        code, out = quiet(run_eval.main, argv, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertIn("arm adhd-before-attacks skipped: no skill file at ~/.claude/skills/adhd/SKILL.md", out)
        self.assertNotIn("session for generic-before-attacks, adhd", out)
        self.assertNotIn("# adhd-before-attacks", out)
        code, out = quiet(run_eval.main, argv + ["--arm", "adhd-before-attacks"], env=self.env)
        self.assertEqual(code, 2, out)
        self.assertIn("skipped", out)
        self.skill()
        code, out = quiet(run_eval.main, argv, env=self.env)
        self.assertIn("# adhd-before-attacks challenger", out)

    def test_skill_removed_after_the_start_is_never_run_without(self):
        arm = self.arm(tools="Skill", skills=["~/gone/SKILL.md"])
        with mock.patch.object(run_eval.subprocess, "run") as run, self.assertRaises(judge.Refused):
            run_eval.ask_challenger("m", arm, "p", self.env, 1, 5)
        run.assert_not_called()

    def test_skill_challenger_without_tools_gets_none(self):
        cmd = run_eval.challenger_command("m", self.arm(), 3)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", cmd)

    def test_skill_questions_after_the_marker(self):
        reply = "Designs:\n1. a\n6. f\nQUESTIONS:\nContext.\n" + "".join(f"{i}. q{i}\n" for i in range(1, 8))
        got = run_eval.first_questions(reply)
        self.assertTrue(got.startswith("Context."))
        self.assertIn("5. q5", got)
        self.assertNotIn("q6", got)


class TestChallengerCost(Base):
    def test_challenger_cost_is_the_last_results_total(self):
        events = [{"type": "result", "result": "wait", "total_cost_usd": 0.1},
                  {"type": "result", "result": "1. q", "total_cost_usd": 0.9}]
        self.assertEqual(run_eval.challenger_reply("\n".join(map(json.dumps, events)), []), ("1. q", 0.9))

    def test_challenger_cost_of_a_stopped_session_matches_a_billed_total(self):
        # one real claude-haiku-5-5 call, 2026-11-25: its result said total_cost_usd 0.00068319
        usage = {"input_tokens": 2, "cache_creation_input_tokens": 3180, "cache_read_input_tokens": 649,
                 "cache_creation": {"ephemeral_1h_input_tokens": 3180}, "output_tokens": 1}
        start = {"type": "message_start", "message": {"id": "m", "model": "claude-haiku-5-5", "usage": usage}}
        events = [{"type": "stream_event", "event": start},
                  {"type": "assistant", "message": {"id": "m", "model": "claude-haiku-5-5", "usage": usage}},
                  {"type": "stream_event", "event": {"type": "message_delta", "usage": {"output_tokens": 81}}}]
        log = self.tmp / "log"
        log.write_text("\n".join(map(json.dumps, events)) + "\ncut {")
        self.assertAlmostEqual(money.log_cost(log), 0.00068319, places=10)
        sub = {"input_tokens": 2, "output_tokens": 4, "cache_read_input_tokens": 3371,
               "cache_creation_input_tokens": 512, "cache_creation": {"ephemeral_5m_input_tokens": 512}}
        with log.open("a") as f:
            f.write("\n" + json.dumps({"type": "user", "tool_use_result": {"usage": sub,
                                                                        "resolvedModel": "claude-haiku-5-5"}}))
        self.assertAlmostEqual(money.log_cost(log), 0.00068319 + 0.00009991, places=8)
        log.write_text(log.read_text().replace("claude-haiku-5-5", "some-other-model"))
        self.assertIsNone(money.log_cost(log))
        log.write_text("")
        self.assertIsNone(money.log_cost(log))


class TestParallel(Base):
    def test_parallel_never_more_than_three_live_and_every_run_recorded(self):
        for asked in (1, 9):
            lock, live, peak = threading.Lock(), [0], [0]

            class Slow(TaskClaude):
                def start(self, *a):
                    with lock:
                        live[0] += 1
                        peak[0] = max(peak[0], live[0])
                    return super().start(*a)

                def stop(self, proc):
                    time.sleep(0.05)  # not in start, which runs under the eval's lock
                    with lock:
                        live[0] -= 1

            self.tmp = self.tmp / str(asked)
            self.tmp.mkdir()
            fake = Slow()
            # FakeClaude names a run by its log: only session and resume, no early stop, so order is free
            (out, _), _text = quiet(self.run_arms, self.folder(self.arm()), fake, 8, ["--parallel", str(asked)])
            self.assertEqual(peak[0], min(asked, 3))
            self.assertEqual(live[0], 0)
            self.assertEqual(len(list(out.glob("new-arm/run-*/run.json"))), 8)

    def test_parallel_an_error_stops_the_rest(self):
        class Broken(TaskClaude):
            def start(self, *a):
                raise OSError("no claude")

        with self.assertRaises(OSError):
            self.run_arms(self.folder(self.arm()), Broken(), 5, ["--parallel", "3"])


GOOD = {"name": "a", "when": "after-red", "sees": ["request"], "instruction": "x"}
BAD = [{"name": "b"}, {"name": 3}, {"name": "../a"}, {"when": "later"}, {"when": None}, {"sees": "request"},
       {"sees": ["code"]}, {"sees": []}, {"sees": [1]}, {"instruction": ""}, {"instruction": 5},
       {"tools": "Bash"}, {"tools": ["Agent"]}, {"tools": "Agent,Read"}, {"skills": "x/SKILL.md"},
       {"skills": ["x/other.md"], "tools": "Skill"}, {"skills": ["x/SKILL.md"]},
       {"skills": ["x/s/SKILL.md", "y/s/SKILL.md"], "tools": "Skill"}, {"extra": 1}]


class TestHostile(Base):
    def refused(self, folder):
        code, out = quiet(run_eval.main, ["--dry-run", "--arms", str(folder)], env=self.env)
        self.assertEqual(code, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertTrue(out.startswith("refused: "), out)

    def write(self, text):
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        (folder / "a.json").write_text(text)
        return folder

    def test_bad_arm_input(self):
        for text in ("", "{", "[]", "3", "{}", *[json.dumps({**GOOD, **c}) for c in BAD]):
            self.refused(self.write(text))
        self.refused(self.tmp / "none")
        self.refused(self.folder())
        for argv in ([str(self.tmp / "none")], [str(self.tmp), "--case", "nope"],
                     [str(self.tmp), "--arms", str(self.tmp / "none")]):
            code, out = quiet(__import__("report").main, argv)
            self.assertEqual(code, 2, out)
            self.assertNotIn("Traceback", out)
        code, out = quiet(__import__("report").main, [], env={"TMPDIR": str(self.tmp)})
        self.assertEqual(code, 2, out)

    def test_arm_collision_one_name_twice_is_refused(self):
        folder = self.write(json.dumps(GOOD))
        (folder / "again.json").write_text(json.dumps({**GOOD, "instruction": "other"}))
        self.refused(folder)

    def test_bad_arm_part_one_broken_file_refuses_all(self):
        folder = self.folder(self.arm())
        (folder / "broken.json").write_text("{")
        self.refused(folder)
        code, out = quiet(run_eval.main, ["--dry-run", "--arms", str(folder), "--arm", "new-arm"], env=self.env)
        self.assertEqual(code, 2, out)

    def test_arm_refusal_exactly_the_invalid_files(self):
        def valid(a):
            skills, tools = a.get("skills", []), a.get("tools", "")
            return (a["when"] in ("none", "before-attacks", "after-red") and isinstance(a["sees"], list)
                    and set(a["sees"]) <= {"request", "inputs_program", "known_limits", "criteria"}
                    and (a["when"] == "none" or bool(a["sees"] and a["instruction"].strip()))
                    and tools in ("", "Agent", "Skill", "Agent,Skill", "Skill,Agent")
                    and (not skills or "Skill" in tools))

        rng, seen = random.Random(5), set()
        for _ in range(300):
            arm = {"name": "a", "when": rng.choice(["none", "before-attacks", "after-red", "x"]),
                   "sees": rng.sample(["request", "inputs_program", "known_limits", "criteria", "code"],
                                      rng.choice([0, 1, 1, 2])),
                   "instruction": rng.choice(["", " ", "ask"])}
            if rng.random() < 0.5:
                arm["tools"] = rng.choice(["", "Agent", "Skill", "Agent,Skill", "Skill,Agent", "Bash"])
            if rng.random() < 0.3:
                arm["skills"] = ["~/s/SKILL.md"]
            try:
                armfile.load_arms(self.write(json.dumps(arm)))
                got = True
            except judge.Refused:
                got = False
            self.assertEqual(got, valid(arm), arm)
            seen.add(got)
        self.assertEqual(seen, {True, False})

    def test_arm_reading_names_in_any_order_and_skill_paths_either_way(self):
        names = ["control", "generic-after-red", "design-aware-before-attacks"]
        for order in (names, names[::-1], names + names):
            self.assertEqual(list(armfile.load_arms(only=order)), [names[0], names[1], names[2]])
        absolute = self.skill()
        for text in ("~/.claude/skills/adhd/SKILL.md", str(absolute)):
            self.assertEqual(armfile.skill_files({"skills": [text]}, self.env), ([("adhd", absolute)], []))
        command = run_eval.challenger_command("m", self.arm(tools="Agent,Skill"), 3)
        self.assertEqual(shlex.split(shlex.join(command)), command)


if __name__ == "__main__":
    unittest.main()
