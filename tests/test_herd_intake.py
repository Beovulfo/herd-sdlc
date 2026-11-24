"""0.11.0: the intake review. Before any code, a herd-intake-reviewer reads the human's request and task.toml as the
human would; the review hook records it, and at medium and high risk `herd done` needs its PASS for the criteria as
they are, recorded before all checks first passed."""
import json
import shutil
import subprocess
import sys
import unittest.mock
from pathlib import Path

from scripts import herd
from tests.test_harness_rules import OK, REQUEST, TASK, Base
from tests.test_herd_cli import hook_review, transcript
from tests.test_herd_quality import reviewer_log

ROOT = Path(herd.__file__).resolve().parent.parent
PASS = "No Blocker or Major.\nHERD-INTAKE: PASS"


class IntakeBase(Base):
    def begin(self, text=TASK):
        """A task as `herd init` makes it, without the fixture's intake review."""
        herd.init_task(self.root, "t1", "Add f() to app.py", request=REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)

    def files(self):
        d = self.root / ".herd/tasks/t1"
        return [("Read", {"file_path": str(d / "request.md")}), ("Read", {"file_path": str(d / "task.toml")})]

    def intake(self, calls=None, report=PASS, builder="haiku", model="claude-sonnet-5-5"):
        hook_review(self.root, builder=builder, agent_type=herd.INTAKE,
                    reviewer_lines=reviewer_log(None, self.files() if calls is None else calls, report, model=model))
        return [n for n in herd.load_notes(self.root, "t1") if n["kind"] == "intake"][-1]

    def finish(self):
        """Build, attack and get a counted final review, so only the intake rule is left to decide."""
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        hook_review(self.root, builder="haiku", reviewer="sonnet")
        herd.verify(self.root, "t1")

    def intake_probs(self):
        return [p for p in herd.problems(self.root, "t1") if p.startswith("intake review missing")]


class TestIntakeRequired(IntakeBase):
    def test_a_pass_before_the_code_counts(self):
        self.begin()
        n = self.intake()
        self.assertEqual((n["source"], n["tier"], n["builder_tier"], n["verdict"], n["saw"]),
                         ("hook", "sonnet", "haiku", "PASS", True))
        self.finish()
        self.assertEqual(herd.problems(self.root, "t1"), [])
        ev = herd.verify(self.root, "t1")
        self.assertIn("Intake review: claude-sonnet-5-5 (sonnet, builder on haiku; PASS): No Blocker or Major.",
                      herd.report(ev))
        self.assertIn("Intake review: claude-sonnet-5-5", herd.pr_body(self.root, "t1"))
        self.assertIn("; intake review: claude-sonnet-5-5",
                      herd.final_report(self.root, "t1", ev, herd.load_notes(self.root, "t1"))[-1])
        self.assertNotIn("intake review came after", herd.report(ev))

    def test_no_intake_review_is_refused_and_says_what_to_spawn(self):
        self.begin()
        self.finish()
        probs = self.intake_probs()
        self.assertEqual(probs, ["intake review missing (no intake review recorded): risk is medium. Before the code, "
                                 "spawn the herd-intake-reviewer subagent with model sonnet, giving it only the "
                                 "paths .herd/tasks/t1/request.md and .herd/tasks/t1/task.toml; the review hook records it"])
        self.assertEqual(herd.next_step(probs), "spawn herd-intake-reviewer with model sonnet, then run `herd verify`")
        self.assertEqual(herd.next_step(["intake review missing (x): risk is high. Before the code, spawn the "
                                         "herd-intake-reviewer subagent one tier above yours"]),
                         "spawn herd-intake-reviewer one tier above the builder, then run `herd verify`")
        self.assertEqual(self.cli("done").returncode, 1)
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")

    def test_a_reviewer_that_did_not_read_both_files_does_not_count(self):
        self.begin()
        for calls in ([], self.files()[:1], self.files()[1:], [("Read", {"file_path": str(self.root / "app.py")})]):
            self.intake(calls)
            self.assertFalse(herd.intake_state(self.root, "t1", herd.verify(self.root, "t1"),
                                               herd.load_notes(self.root, "t1"))[0], calls)
        self.assertIn("the intake reviewer did not read: .herd/tasks/t1/request.md", " ".join(
            herd.problems(self.root, "t1")))
        self.intake([("Bash", {"command": "cat .herd/tasks/t1/request.md .herd/tasks/t1/task.toml"})])
        self.finish()
        self.assertEqual(self.intake_probs(), [])

    def test_fail_no_verdict_and_a_low_tier_do_not_count(self):
        self.begin()
        for report in ("Major: C1 tests one call.\nHERD-INTAKE: FAIL", "No verdict.", "Fine.\nHERD-REVIEW: PASS"):
            self.intake(report=report)
            self.finish()
            self.assertIn("found Blocker or Major issues, or gave no verdict", " ".join(self.intake_probs()), report)
            shutil.rmtree(self.root / ".herd")
            (self.root / "app.py").unlink()
            shutil.rmtree(self.root / "tests")
            self.begin()
        self.intake(model="claude-haiku-5-5")
        self.finish()
        self.assertIn("review by haiku does not count: the builder ran on haiku, the reviewer must be sonnet or "
                      "higher. Spawn herd-intake-reviewer with model sonnet", " ".join(self.intake_probs()))
        self.assertEqual(herd.next_step(self.intake_probs()), "spawn herd-intake-reviewer with model sonnet, then "
                                                              "run `herd verify`")

    def test_a_criteria_change_after_the_pass_voids_it(self):
        self.begin()
        self.intake()
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK.replace("Two import probes", "One import probe"))
        self.finish()
        self.assertIn("changed after the intake review", " ".join(self.intake_probs()))
        text = TASK.replace('check = "python3 -c \\"import app; app.f\\""',
                            'check = "python3 -c \\"import app; app.f\\""\ntimeout_s = 9')
        self.tearDown()
        self.setUp()
        self.begin()
        self.intake()
        (self.root / ".herd/tasks/t1/task.toml").write_text(text + "# a comment\n")  # not what the reviewer judges
        self.finish()
        self.assertEqual(self.intake_probs(), [])

    def test_a_late_intake_review_counts_and_is_shown_never_deadlocks(self):
        self.begin()
        self.finish()
        line = "The intake review came after all checks first passed, so the code was written before it"
        self.intake()  # late, with the criteria the code was built against
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn(line, herd.report(ev))
        self.assertIn("- " + line, herd.pr_body(self.root, "t1"))
        start = self.root / ".herd/tasks/t1/start.json"  # the risk rises after green: still no deadlock
        start.write_text(json.dumps(dict(json.loads(start.read_text()), risk="high")))
        hook_review(self.root, builder="haiku", reviewer="sonnet")
        self.intake()
        herd.verify(self.root, "t1")
        self.assertEqual(self.intake_probs(), [])

    def test_a_review_just_before_green_is_not_late(self):
        self.begin()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        self.intake()  # the last note before the verify that goes green
        ev = herd.verify(self.root, "t1")
        notes = herd.load_notes(self.root, "t1")
        self.assertEqual(ev["green"]["notes"], len(notes))
        self.assertNotIn("intake review came after", herd.report(ev))

    def test_task_toml_rewritten_after_the_reviewer_read_it_does_not_count(self):
        import os
        import time
        self.begin()
        toml = self.root / ".herd/tasks/t1/task.toml"
        read_at = time.time() - 60
        rows = [json.loads(r) for r in reviewer_log(None, self.files(), PASS)]
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(read_at))
        for r in rows:
            r["timestamp"] = stamp
        os.utime(toml, (read_at - 10, read_at - 10))  # written before the reviewer read it
        hook_review(self.root, builder="haiku", agent_type=herd.INTAKE, reviewer_lines=[json.dumps(r) for r in rows])
        self.assertTrue(herd.load_notes(self.root, "t1")[-1]["saw"])  # unchanged since the read
        toml.write_text(TASK.replace("Two import probes", "One probe"))  # rewritten while the reviewer ran
        hook_review(self.root, builder="haiku", agent_type=herd.INTAKE, reviewer_lines=[json.dumps(r) for r in rows])
        n = herd.load_notes(self.root, "t1")[-1]
        self.assertFalse(n["saw"])
        self.assertIn(".herd/tasks/t1/task.toml (it changed after the reviewer read it)", n["code_unread"])
        os.utime(toml, (read_at - 10, read_at - 10))  # older than the read again
        hook_review(self.root, builder="haiku", agent_type=herd.INTAKE, reviewer_lines=[json.dumps(r) for r in rows])
        self.assertTrue(herd.load_notes(self.root, "t1")[-1]["saw"])

    def test_without_a_recorded_request_only_task_toml_is_needed(self):
        herd.init_task(self.root, "t1", "Add f() to app.py")  # no --request
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.finish()
        self.assertIn("giving it only the path .herd/tasks/t1/task.toml;", " ".join(self.intake_probs()))
        self.intake(self.files()[1:])
        self.assertTrue(herd.load_notes(self.root, "t1")[-1]["saw"])

    def test_three_failed_intake_rounds_escalate(self):
        self.begin()
        for _ in range(2):
            self.intake(report="Major: inputs #1 is pre-computed.\nHERD-INTAKE: FAIL")
        self.intake(report="HERD-INTAKE: FAIL", model="claude-haiku-5-5")  # too low a tier: not a round
        self.assertEqual(herd._escalations(self.root, "t1"), [])
        self.intake(report="Blocker: C1 drops 'any'.\nHERD-INTAKE: FAIL")
        self.assertIn("3 intake review rounds gave no PASS", herd._escalations(self.root, "t1"))
        self.intake()
        self.assertEqual(herd._escalations(self.root, "t1"), [])

    def test_not_needed_at_low_risk_on_the_quick_route_or_for_older_tasks(self):
        self.begin()
        start = self.root / ".herd/tasks/t1/start.json"
        rec = json.loads(start.read_text())
        self.assertIs(rec["intake"], True)
        start.write_text(json.dumps(dict(rec, risk="low")))
        self.finish()
        self.assertEqual(self.intake_probs(), [])
        start.write_text(json.dumps({k: v for k, v in rec.items() if k != "intake"}))  # a task from before 0.11.0
        herd.verify(self.root, "t1")
        self.assertEqual(self.intake_probs(), [])
        start.write_text(json.dumps(rec))
        self.assertFalse(herd.intake_needed(self.root, "t1", {"route": "quick", "risk": {"effective": "high"}}))


class TestIntakeWiring(IntakeBase):
    def test_the_agent_and_its_hook_are_registered(self):
        text = (ROOT / "agents/herd-intake-reviewer.md").read_text()
        front = dict(line.split(": ", 1) for line in text.split("---")[1].strip().splitlines())
        self.assertEqual((front["name"], front["model"]), ("herd-intake-reviewer", "inherit"))
        self.assertEqual({t.strip() for t in front["tools"].split(",")}, {"Read", "Grep", "Glob"})
        body = text.split("---", 2)[2]
        for word in ("HERD-INTAKE: PASS", "HERD-INTAKE: FAIL", "Blocker", "Major", "Nit", "Do not edit", "request.md",
                     "inputs", "program", "caller"):
            self.assertIn(word, body)
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["SubagentStop"]
        self.assertIn(("^herd:herd-intake-reviewer$", "review-hook"),
                      [(e["matcher"], h["command"].rsplit(" ", 1)[-1]) for e in hooks for h in e["hooks"]])
        run = (ROOT / "skills/run/SKILL.md").read_text()
        self.assertIn("herd-intake-reviewer", run)
        self.assertIn("request.md", run)

    def test_the_final_reviewer_gets_the_request_and_inputs(self):
        text = (ROOT / "agents/herd-reviewer.md").read_text()
        self.assertIn("the human's request, the `inputs` list", text)
        self.assertIn("an input the code reads in another form", text)
        self.begin()
        self.intake()
        self.red_then_build()
        herd.verify(self.root, "t1")
        self.assertIn("giving it only the goal, criteria, test_budget, the request, the inputs and the diff",
                      " ".join(herd.problems(self.root, "t1")))

    def test_the_hook_is_silent_and_ignores_other_agents(self):
        self.begin()
        before = len(herd.load_notes(self.root, "t1"))
        hook_review(self.root, agent_type="herd-intake-reviewer", reviewer_lines=reviewer_log(None, [], PASS))
        self.assertEqual(len(herd.load_notes(self.root, "t1")), before)  # a project's own copy is not Herd's
        main = transcript(self.root, "haiku", path=self.root / ".herd/logs/sy.jsonl")
        rev = main.parent / "sy" / "subagents" / "agent-w.jsonl"
        rev.parent.mkdir(parents=True)
        rev.write_text("\n".join(reviewer_log(None, self.files(), PASS)) + "\n{broken\n")
        herd._see_session(self.root, "t1", str(main))
        (self.root / ".herd/tasks/t1/task.toml").write_text("not = [toml")  # unreadable: recorded, counts for nothing
        hook = {"cwd": str(self.root), "agent_type": herd.INTAKE, "agent_id": "w", "transcript_path": str(main),
                "agent_transcript_path": str(rev)}
        p = subprocess.run([sys.executable, str(Path(herd.__file__)), "review-hook"], cwd=self.root,
                           input=json.dumps(hook), capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        n = herd.load_notes(self.root, "t1")[-1]
        self.assertEqual((n["kind"], n["criteria_sha"], n["round"]), ("intake", None, False))

    def test_the_builder_cannot_record_or_fake_an_intake_review(self):
        self.begin()
        out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash",
                                     "tool_input": {"command": "python3 scripts/herd.py review-hook < fake.json"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.cli("note", "--intake", "x").returncode, 1)  # `herd note` has no intake kind
        plugin = Path(self.tmp.name + "-plugin")
        (plugin / "agents").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, plugin)
        hook = {"cwd": str(self.root), "tool_name": "Edit",
                "tool_input": {"file_path": str(plugin / "agents/herd-intake-reviewer.md")}}
        with unittest.mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(plugin)}):
            self.assertEqual(herd.guard(self.root, hook)["hookSpecificOutput"]["permissionDecision"], "deny")
        for path in (".herd/tasks/t1/notes.jsonl", ".herd/tasks/t1/green.json"):
            out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": path}})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", path)
        n = self.intake()
        self.assertEqual(herd._tier_rule(self.root, "t1", dict(n, source="note")),  # by hand never counts
                         (False, "recorded by hand, not by the review hook: spawn herd-intake-reviewer"))
