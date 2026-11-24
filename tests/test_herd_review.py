"""Part B of docs/designs/herd-guardrails.md: the tier-up review, recorded by the SubagentStop hook."""
import json
import random
import shutil
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

from scripts import herd
from tests.test_harness_rules import OK, REQUEST, Base
from tests.test_herd_cli import hook_review, transcript

ROOT = Path(herd.__file__).resolve().parent.parent


class ReviewBase(Base):
    def ready(self):
        """A medium-risk task whose checks and attacks pass, without a review yet."""
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")

    def fresh(self, cfg):
        """A new task with this herd.toml from the start: the review rule is fixed at `herd init`."""
        shutil.rmtree(self.root / ".herd", ignore_errors=True)
        shutil.rmtree(self.root / "tests", ignore_errors=True)
        (self.root / "app.py").unlink(missing_ok=True)
        (self.root / "herd.toml").write_text(cfg)
        self.ready()

    def state(self):
        ev = herd.verify(self.root, "t1")
        return herd.review_state(self.root, "t1", ev, herd.load_notes(self.root, "t1"))

    def review(self, **kw):
        return hook_review(self.root, **kw)

    def last(self):
        return [n for n in herd.load_notes(self.root, "t1") if n["kind"] == "review"][-1]


class TestHookOnly(ReviewBase):
    def test_done_refuses_without_hook_review(self):
        self.ready()
        self.assertIn("review missing", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(self.cli("done").returncode, 1)
        p = self.cli("review", "--skipped", "no subagent can run here")
        self.assertEqual(p.returncode, 1)
        self.assertIn("a review is required at medium and high risk", p.stderr)
        self.assertFalse(any(n["kind"] == "review" for n in herd.load_notes(self.root, "t1")))
        self.assertEqual(self.cli("review", "--by", "me", "looks fine").returncode, 0)  # a note, never counted here
        herd.verify(self.root, "t1")
        self.assertIn("recorded by hand, not by the review hook: spawn herd-reviewer",
                      " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:  # an old skipped note from 0.4 to 0.6
            f.write(json.dumps({"at": herd.now(), "kind": "review", "text": "no reviewer", "skipped": True,
                                "risk": "high"}) + "\n")
        ev = herd.verify(self.root, "t1")
        self.assertIn("unreviewed", " ".join(herd.final_report(self.root, "t1", ev, herd.load_notes(self.root, "t1"))))
        self.assertTrue(herd.problems(self.root, "t1"))
        self.review(builder="haiku", reviewer="sonnet")  # CUJ 3
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        n = self.last()
        self.assertEqual((n["source"], n["tier"], n["builder_tier"], n["verdict"], n["by"]),
                         ("hook", "sonnet", "haiku", "PASS", "claude-sonnet-5-5"))
        p = self.cli("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Review: claude-sonnet-5-5 (sonnet, builder on haiku; PASS; ran git diff or git show, read 1 of 1 changed code file)", p.stdout)

    def test_quick_route_needs_no_review(self):
        herd.init_task(self.root, "q1", "Fix a typo", quick_check="python3 -c 1")
        herd.verify(self.root, "q1")
        self.assertEqual(herd.problems(self.root, "q1"), [])


class TestTierRule(ReviewBase):
    def test_review_tier_rule(self):
        tiers = ["haiku", "sonnet", "opus"]
        for step in (1, 2):
            self.fresh(f"[review]\nstep = {step}\n")
            for b, builder in enumerate(tiers):
                for t, reviewer in enumerate(tiers):
                    self.review(builder=builder, reviewer=reviewer)
                    ok, why = self.state()
                    need = min(b + step, 2)
                    self.assertEqual(ok, t >= need, (step, builder, reviewer, why))
                    if not ok:
                        self.assertEqual(why, f"review by {reviewer} does not count: the builder ran on {builder}, "
                                              f"the reviewer must be {tiers[need]} or higher. Spawn herd-reviewer "
                                              f"with model {tiers[need]}")
        self.fresh("")  # the default, one tier above since 0.10.0
        self.review(builder="opus", reviewer="opus")  # the top tier reviews itself
        self.assertTrue(self.state()[0])
        self.assertIn("same tier", herd._review(herd.load_notes(self.root, "t1")))
        self.review(builder=["haiku", "sonnet", "haiku"], reviewer="sonnet")  # the builder's highest tier counts
        self.assertIn("the builder ran on sonnet", self.state()[1])

    def test_tier_rule_with_random_tiers(self):
        rng = random.Random(9)
        for _ in range(12):
            names = rng.sample(["ant", "bee", "cat", "dog", "elk", "fox"], rng.randint(2, 5))
            step = rng.randint(0, 3)
            self.fresh(f"[review]\ntiers = {json.dumps(names)}\nstep = {step}\n")
            b, t = rng.randrange(len(names)), rng.randrange(len(names))
            self.review(builder=names[b], reviewer=names[t], model=rng.choice(["claude-{}-1-0", "{}", "x-{}-2026"]))
            need = b + step if b + step < len(names) else len(names) - 1  # separate formula
            self.assertEqual(self.state()[0], t >= need, (names, step, b, t))

    def test_bad_review_config_means_the_defaults(self):
        self.ready()
        for cfg in ("[review\n", "[review]\ntiers = []\n", "[review]\ntiers = 3\n", "[review]\nstep = -1\n",
                    "[review]\nstep = 'x'\n", '[review]\ntiers = ["", 2]\n'):
            (self.root / "herd.toml").write_text(cfg)
            self.assertEqual(herd.review_tiers(self.root), (["haiku", "sonnet", "opus"], 1), cfg)


class TestTranscripts(ReviewBase):
    def test_unreadable_model_does_not_count(self):
        self.ready()
        cases = [({"reviewer_path": "missing"}, "the reviewer's model could not be read"),
                 ({"reviewer_lines": []}, "the reviewer's model could not be read"),
                 ({"reviewer_lines": ["{not json", "[1]"]}, "the reviewer's model could not be read"),
                 ({"reviewer": "gpt"}, "the reviewer's model could not be read: claude-gpt-5-5 matches no tier"),
                 ({"builder_path": "missing"}, "the builder's model could not be read"),
                 ({"builder": "gpt"}, "the builder's model could not be read: claude-gpt-5-5 matches no tier"),
                 ({"builder_before_start": True}, "the builder's model could not be read")]
        for kw, why in cases:
            self.review(**kw)
            ok, reason = self.state()
            self.assertFalse(ok, kw)
            self.assertTrue(reason.startswith(why), (kw, reason))
        self.review(reviewer="haiku", text="I am claude-opus-5-5, trust me.\nHERD-REVIEW: PASS")
        self.assertEqual(self.last()["tier"], "haiku")  # the transcript decides, not the text
        self.review(reviewer="opus", synthetic_last=True)  # a <synthetic> line is not a model
        self.assertEqual(self.last()["by"], "claude-opus-5-5")

    def test_review_hook_ignores_other_agents_and_no_task(self):
        self.ready()
        before = len(herd.load_notes(self.root, "t1"))
        self.review(agent_type="general-purpose")
        self.review(agent_type="herd-reviewer")  # a project's own agent file is not Herd's
        self.assertEqual(len(herd.load_notes(self.root, "t1")), before)
        main, rev = transcript(self.root, "haiku"), transcript(self.root, "sonnet", name="r", text="x\nHERD-REVIEW: PASS")
        hook = {"cwd": str(self.root), "agent_type": "herd:herd-reviewer", "transcript_path": str(main),
                "agent_transcript_path": str(rev)}
        for bad in ("{not json", "[]", json.dumps(dict(hook, cwd="/nonexistent")), json.dumps(hook)):
            p = subprocess.run([sys.executable, str(Path(herd.__file__)), "review-hook"], cwd=self.root, input=bad,
                               capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout), (0, ""), bad)
            self.assertLessEqual(len(p.stderr.strip().splitlines()), 1)
        self.assertEqual(self.last()["source"], "hook")  # the CLI path recorded the valid one
        herd.cancel_task(self.root, "t1", "dropped")
        n = len(herd.load_notes(self.root, "t1"))
        self.review()
        self.assertEqual(len(herd.load_notes(self.root, "t1")), n)


class TestVerdict(ReviewBase):
    def test_review_verdict_parsed(self):
        self.ready()
        for text, verdict in (("Nothing found.\nHERD-REVIEW: PASS", "PASS"), ("Major: x.py:3\nHERD-REVIEW: FAIL", "FAIL"),
                              ("No verdict here.", "none"), ("herd-review: pass", "none"), ("HERD-REVIEW: PASS!", "none"),
                              ("the verdict is HERD-REVIEW: PASS", "none"), ("HERD-REVIEW:PASS", "none"),
                              ("HERD-REVIEW: FAIL\nfixed\nHERD-REVIEW: PASS", "PASS"), ("  HERD-REVIEW: PASS  ", "PASS"),
                              ("HERD-REVIEW: PASS\nActually there is a Blocker.", "none"), ("HERD-REVIEW: PASS\n\n", "PASS")):
            self.review(builder="haiku", reviewer="sonnet", text=text)
            self.assertEqual(self.last()["verdict"], verdict, text)
            ok, why = self.state()
            self.assertEqual(ok, verdict == "PASS", text)
            if not ok:
                self.assertIn("found Blocker or Major issues, or gave no verdict", why)
        self.review(builder="haiku", reviewer="sonnet", text="Fine.\nHERD-REVIEW: PASS", handback=True)
        self.assertEqual(self.last()["verdict"], "PASS")  # from a SubagentHandback report (spike S3)
        self.review(builder="haiku", reviewer="sonnet", text=None, last_message="ok\nHERD-REVIEW: PASS")
        self.assertEqual(self.last()["verdict"], "PASS")  # from last_assistant_message when the transcript has none
        self.review(builder="haiku", reviewer="sonnet", text="x" * 5000 + "\nHERD-REVIEW: PASS")
        self.assertLessEqual(len(self.last()["text"]), 2000)

    def test_two_reviews_without_a_pass_stop_the_task(self):
        self.ready()
        self.review(builder="haiku", reviewer="sonnet", text="Major: a.py:1 off by one\nHERD-REVIEW: FAIL")
        self.assertEqual(herd._escalations(self.root, "t1"), [])
        self.review(builder="haiku", reviewer="haiku", text="HERD-REVIEW: FAIL")  # too low a tier: not a round, still a run
        herd.verify(self.root, "t1")
        self.assertIn("review limit", " ".join(herd._escalations(self.root, "t1")))
        self.review(builder="haiku", reviewer="sonnet", text="Blocker: b.py:2 crash\nHERD-REVIEW: PASS")  # over the cap
        last = self.last()
        self.assertEqual((last["over_cap"], last["round"]), (True, False))
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("review limit", why)
        ev = herd.verify(self.root, "t1")
        self.assertIsNone(herd.gate(self.root, {}))  # releases: the session ends, it does not loop
        rec = json.loads((self.root / ".herd/tasks/t1/stopped.json").read_text())
        self.assertEqual((rec["reason"], rec["resumable"]), ("escalated", False))
        self.assertIn("review limit", rec["next"])
        msg = herd.review_limit(herd.load_notes(self.root, "t1"))
        self.assertIn("stop and ask the human", msg)
        self.assertIn("Blocker: b.py:2 crash", msg)
        self.assertNotIn("Nit", msg)
        for cmd in ("review-brief", "verify"):
            p = self.cli(cmd)
            self.assertIn("review limit reached", p.stdout, cmd)
            self.assertIn("stop and ask the human", p.stdout, cmd)
            self.assertIn("Blocker: b.py:2 crash", p.stdout, cmd)
        self.assertNotIn("Goal:", self.cli("review-brief").stdout)
        self.assertEqual(ev["summary"]["failing"], 0)

    def test_a_pass_that_counts_resets_the_count_and_a_failed_one_does_not(self):
        self.ready()
        self.review(builder="haiku", reviewer="sonnet", text="Major: a.py:1\nHERD-REVIEW: FAIL")
        self.review(builder="haiku", reviewer="sonnet")  # PASS that counts
        self.review(builder="haiku", reviewer="sonnet", text="Major: a.py:2\nHERD-REVIEW: FAIL")
        self.assertIsNone(herd.review_limit(herd.load_notes(self.root, "t1")))
        self.review(builder="haiku", reviewer="haiku")  # a PASS by too low a tier does not reset
        self.assertIn("review limit", herd.review_limit(herd.load_notes(self.root, "t1")))

    def test_a_decision_note_for_the_review_limit_resets_it(self):
        self.ready()
        for _ in range(2):
            self.review(builder="haiku", reviewer="sonnet", text="Major: a.py:1\nHERD-REVIEW: FAIL")
        herd.add_note(self.root, "t1", "decision", "chose a plain fix; no reason about reviews")  # not a reset
        self.assertIsNotNone(herd.review_limit(herd.load_notes(self.root, "t1")))
        herd.add_note(self.root, "t1", "decision", "Review limit: the human said one more round")
        self.assertIsNone(herd.review_limit(herd.load_notes(self.root, "t1")))
        self.assertEqual(herd._escalations(self.root, "t1"), [])
        self.review(builder="haiku", reviewer="sonnet")
        self.assertTrue(self.state()[0])


class TestWiringAndStatus(ReviewBase):
    def test_review_hook_is_registered(self):
        text = (ROOT / "agents/herd-reviewer.md").read_text()
        front = dict(line.split(": ", 1) for line in text.split("---")[1].strip().splitlines())
        self.assertEqual(front["name"], "herd-reviewer")
        self.assertEqual(front["model"], "inherit")
        self.assertEqual({t.strip() for t in front["tools"].split(",")}, {"Read", "Grep", "Glob", "Bash"})
        body = text.split("---", 2)[2]
        for word in ("HERD-REVIEW: PASS", "HERD-REVIEW: FAIL", "Blocker", "Major", "Nit", "Do not edit"):
            self.assertIn(word, body)
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["SubagentStop"]
        self.assertEqual([(e["matcher"], h["command"].rsplit(" ", 1)[-1]) for e in hooks for h in e["hooks"]],
                         [("^herd:herd-reviewer$", "review-hook")])
        self.assertIn('["review-hook"]', Path(herd.__file__).read_text().split("import hashlib", 1)[0])

    def test_status_and_stop_record_name_the_tier(self):
        main = transcript(self.root, "haiku", name="main")
        herd.preinit({"cwd": str(self.root), "transcript_path": str(main),
                      "tool_input": {"command": f"python3 {herd.SELF} init t1 'x'"}})
        self.ready()
        self.assertEqual(json.loads((self.root / ".herd/tasks/t1/start.json").read_text())["transcript"], str(main))
        out = self.cli("status").stdout
        self.assertIn("Review: needs sonnet or higher (builder on haiku)", out)
        self.assertIn("Spawn the herd-reviewer subagent with model sonnet", " ".join(herd.problems(self.root, "t1")))
        for _ in range(herd.MAX_BLOCKS + 1):
            herd.gate(self.root, {})
        rec = json.loads((self.root / ".herd/tasks/t1/stopped.json").read_text())  # CUJ 5
        self.assertEqual(rec["next"], "spawn herd-reviewer with model sonnet, then run `herd verify`")
        self.assertEqual(rec["review"]["needed"], "sonnet")
        (self.root / ".herd/tasks/t1/start.json").write_text(json.dumps(
            dict(json.loads((self.root / ".herd/tasks/t1/start.json").read_text()), transcript="/nonexistent")))
        self.assertIn("Review: needs a reviewer one tier above the builder", self.cli("status").stdout)


class TestReviewAttacks(ReviewBase):
    """The adversarial pass on the review hook (skills/run/adversarial.md)."""

    def test_review_bad_input(self):
        self.ready()
        main = transcript(self.root, "haiku")
        bad_logs = ['{"type": "assistant", "message": "x"}', '{"type": "assistant", "message": {"model": 5}}',
                    '{"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": "text"}}',
                    '{"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": [1, null]}}', "null", "7"]
        for line in bad_logs:
            self.review(builder_path=str(main), reviewer_lines=[line])
            self.assertFalse(self.state()[0], line)
        for hook in (None, [], "x", {"agent_type": "herd:herd-reviewer"},
                     {"agent_type": "herd:herd-reviewer", "transcript_path": 5, "agent_transcript_path": ["x"]},
                     {"agent_type": "herd:herd-reviewer", "last_assistant_message": 3}):
            herd.review_hook(self.root, hook)  # never raises
        self.assertFalse(self.state()[0])
        for cfg in ("[review\n", '[review]\ntiers = "opus"\n', "[review]\nstep = true\n"):
            (self.root / "herd.toml").write_text(cfg)
            self.assertEqual(herd.review_tiers(self.root), (["haiku", "sonnet", "opus"], 1))

    def test_review_collision(self):
        self.ready()
        self.review(builder="haiku", reviewer="sonnet", text="HERD-REVIEW: FAIL")
        self.review(builder="haiku", reviewer="sonnet")  # two reviews in a row: the latest decides
        self.assertTrue(self.state()[0])
        self.review(builder="haiku", reviewer="sonnet", text="HERD-REVIEW: FAIL")
        self.assertFalse(self.state()[0])
        main = transcript(self.root, "haiku", text="All good.\nHERD-REVIEW: PASS")
        hook = {"cwd": str(self.root), "agent_type": "herd:herd-reviewer", "transcript_path": str(main),
                "agent_transcript_path": str(main)}  # the same log for both: the builder reviewing itself
        herd.review_hook(self.root, hook)
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("not where Claude Code keeps it", why)

    def test_review_one_bad_part(self):
        self.ready()
        main = transcript(self.root, ["haiku", "haiku"])
        rev = transcript(self.root, "sonnet", text="Fine.\nHERD-REVIEW: PASS", reads=[self.root / "app.py"],
                         path=main.parent / main.stem / "subagents" / "agent-x.jsonl")
        rev.write_text("{broken\n" + rev.read_text() + "[1, 2]\n")  # bad lines around good ones
        main.write_text(main.read_text() + '{"type": "assistant", "message": {"model": "<synthetic>"}}\n{oops\n')
        herd._see_session(self.root, "t1", str(main))
        herd.review_hook(self.root, {"cwd": str(self.root), "agent_type": "herd:herd-reviewer", "agent_id": "x",
                                     "transcript_path": str(main), "agent_transcript_path": str(rev)})
        self.assertEqual((self.last()["tier"], self.last()["builder_tier"]), ("sonnet", "haiku"))
        self.assertTrue(self.state()[0])
        self.review(builder=["haiku", "gpt"], reviewer="opus")  # one unknown builder model fails closed, by name
        self.assertIn("claude-gpt-5-5 matches no tier", self.state()[1])

    def test_review_recount(self):
        self.ready()
        rng = random.Random(4)
        plan = [rng.choice(["PASS", "FAIL", "none", "low"]) for _ in range(12)]
        for v in plan:
            if v == "low":
                self.review(builder="haiku", reviewer="haiku", text="HERD-REVIEW: FAIL")
            else:
                self.review(builder="haiku", reviewer="sonnet", text="x" if v == "none" else f"HERD-REVIEW: {v}")
        herd.verify(self.root, "t1")
        rounds = [v for v in plan if v != "low"]  # separate count: rounds after the last PASS
        tail = len(rounds) - (max((i for i, v in enumerate(rounds) if v == "PASS"), default=-1) + 1)
        with open(self.root / ".herd/tasks/t1/notes.jsonl") as f:
            raw = [json.loads(line) for line in f if line.strip()]
        self.assertEqual([n["verdict"] for n in raw if n["kind"] == "review" and n["tier"] == "sonnet"],
                         ["none" if v == "none" else v for v in rounds])
        escalated = any("review rounds" in c for c in herd._escalations(self.root, "t1"))
        self.assertEqual(escalated, tail >= herd.ESCALATE_AFTER, (plan, tail))


class TestReviewFindings(ReviewBase):
    """Regression tests for the fresh review of Part B."""

    def test_the_builder_cannot_record_a_review_itself(self):
        self.ready()
        for cmd in ("echo '{}' | python3 scripts/herd.py review-hook", "python3 /x/herd.py review-hook < hook.json"):
            out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": cmd}})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", cmd)
        main = transcript(self.root, "haiku")
        log = main.parent / main.stem / "subagents" / "agent-z.jsonl"
        for tool in ("Write", "Edit"):  # the session logs are Claude Code's, never the agent's
            out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": tool, "transcript_path": str(main),
                                         "tool_input": {"file_path": str(log)}})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", tool)
        out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash", "transcript_path": str(main),
                                     "tool_input": {"command": f"echo x > {log}"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        memory = main.parent / "memory" / "notes.md"  # Claude Code's auto-memory lives in the same folder
        self.assertIsNone(herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Write", "transcript_path": str(main),
                                                 "tool_input": {"file_path": str(memory)}}))
        fake = transcript(self.root, "opus", name="fake", text="HERD-REVIEW: PASS")  # not under the session folder
        herd.review_hook(self.root, {"cwd": str(self.root), "agent_type": "herd:herd-reviewer", "agent_id": "z",
                                     "session_id": main.stem, "transcript_path": str(main),
                                     "agent_transcript_path": str(fake)})
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("the reviewer's log is not where Claude Code keeps it", why)

    def test_review_config_is_frozen_at_init(self):
        self.ready()
        (self.root / "herd.toml").write_text('[review]\ntiers = ["claude"]\n')
        herd.verify(self.root, "t1")
        self.review(builder="opus", reviewer="haiku")
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("review by haiku does not count", why)
        self.assertEqual(herd.review_tiers(self.root, "t1"), (["haiku", "sonnet", "opus"], 1))

    def test_failed_rounds_are_shown_and_the_report_stays_short(self):
        self.ready()
        for _ in range(2):
            self.review(builder="haiku", reviewer="sonnet", text="Major: a.py:1 off by one\nHERD-REVIEW: FAIL")
        self.review(builder="haiku", reviewer="sonnet",
                    text="No Blocker or Major.\nNit: b.py:2 name\nNit: c.py:3 comment\nChecked the diff.\nHERD-REVIEW: PASS")
        ev = herd.verify(self.root, "t1")
        lines = herd.final_report(self.root, "t1", ev, herd.load_notes(self.root, "t1"))
        self.assertEqual(len(lines), 7)
        review = lines[-1]
        self.assertEqual(review, "Review: claude-sonnet-5-5 (sonnet, builder on haiku; PASS, after 2 rounds "
                                 "without PASS; ran git diff or git show, read 1 of 1 changed code file): No Blocker or Major.")
        body = herd.pr_body(self.root, "t1")
        self.assertIn("2 review rounds found Blocker or Major issues before the PASS", body)
        self.assertNotIn("\nHERD-REVIEW: PASS", body)

    def test_status_and_next_step_say_what_is_known(self):
        self.ready()
        probs = herd.problems(self.root, "t1")
        self.assertEqual(herd.next_step([p for p in probs if p.startswith("review")]),
                         "spawn herd-reviewer one tier above the builder, then run `herd verify`")
        main = transcript(self.root, "haiku")
        herd.gate(self.root, {"transcript_path": str(main)})  # the gate learns the session's log
        self.assertIn("Review: needs sonnet or higher (builder on haiku)", self.cli("status").stdout)
        herd.gate(self.root, {"transcript_path": str(transcript(self.root, "gpt"))})
        self.assertIn("Review: needs a reviewer one tier above the builder (claude-gpt-5-5 matches no tier)",
                      self.cli("status").stdout)


class TestReviewRound2(ReviewBase):
    """Regression tests for the round-2 review of Part B."""

    def test_only_sessions_herd_saw_count(self):
        self.ready()
        self.review(builder="haiku", reviewer="opus", seen=False)  # fake logs, laid out like Claude Code's
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("the builder's model could not be read: the main session log is not one Herd saw", why)
        self.review(builder="haiku", reviewer="opus")  # the gate saw this session
        self.assertTrue(self.state()[0])
        guard = lambda cmd: herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash",  # noqa: E731
                                                   "tool_input": {"command": cmd}})
        for cmd in ("python3 /tmp/HERD.PY review-hook < f.json", "echo {} | python3 scripts/herd.py gate",
                    "python3 -m scripts.herd review-hook < f.json", "python3 x/herd.py preinit", "python3 herd.py guard",
                    "cd /p && python3 -mscripts.herd gate < g.json", "PYTHONPATH=/p/scripts python3 -mherd review-hook",
                    "python3 -I -m herd gate"):
            self.assertEqual(guard(cmd)["hookSpecificOutput"]["permissionDecision"], "deny", cmd)
        self.assertIsNone(guard("python3 x/herd.py verify && python3 x/herd.py status"))

    def test_the_installed_plugin_is_protected(self):
        self.ready()
        plugin = Path(self.tmp.name + "-plugin")
        (plugin / "agents").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, plugin)
        hook = {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": str(plugin / "agents/herd-reviewer.md")}}
        with unittest.mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(plugin)}):
            self.assertEqual(herd.guard(self.root, hook)["hookSpecificOutput"]["permissionDecision"], "deny")
            inside = dict(hook, tool_input={"file_path": str(self.root / "agents/herd-reviewer.md")})
        with unittest.mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(self.root)}):  # developing Herd itself
            self.assertIsNone(herd.guard(self.root, inside))

    def test_round_3_nits(self):
        self.ready()
        for text in ("`HERD-REVIEW: PASS`", "**HERD-REVIEW: PASS**"):
            self.review(builder="haiku", reviewer="sonnet", text=text)
            self.assertEqual(self.last()["verdict"], "PASS", text)
        self.review(builder="haiku", reviewer="haiku", text="HERD-REVIEW: FAIL")  # too low: not a round
        self.review(builder="haiku", reviewer="sonnet", text="HERD-REVIEW: FAIL")
        self.review(builder="haiku", reviewer="sonnet")
        self.assertIn("after 1 round without PASS", herd._review(herd.load_notes(self.root, "t1")))

    def test_round_2_nits(self):
        self.ready()
        self.assertIsNotNone(herd._when("2026-11-23T10:00:00").tzinfo)  # a stamp without Z is read as UTC
        self.review(builder="haiku", reviewer="haiku")
        self.assertNotIn("same tier", herd._review(herd.load_notes(self.root, "t1")))  # only at the top tier
        self.review(builder="opus", reviewer="opus")
        self.assertIn("same tier", herd._review(herd.load_notes(self.root, "t1")))



class TestIntakeRemoved(ReviewBase):
    """0.12.0 removed the 0.11.0 intake reviewer: a task started on 0.11.x still finishes, and its stop is ignored."""

    def test_a_0_11_task_with_intake_records_finishes_and_new_intake_stops_record_nothing(self):
        self.ready()
        start = self.root / ".herd/tasks/t1/start.json"
        start.write_text(json.dumps(dict(json.loads(start.read_text()), intake=True)))
        with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:
            f.write(json.dumps({"at": herd.now(), "kind": "intake", "text": "HERD-INTAKE: FAIL", "verdict": "FAIL",
                                "source": "hook"}) + "\n")
        self.review(builder="haiku", reviewer="sonnet")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertNotIn("ntake review", herd.report(herd.verify(self.root, "t1"), herd.load_notes(self.root, "t1")))
        before = len(herd.load_notes(self.root, "t1"))
        self.review(agent_type="herd:herd-intake-reviewer", text="Fine.\nHERD-INTAKE: PASS")
        self.assertEqual(len(herd.load_notes(self.root, "t1")), before)
        self.assertFalse((ROOT / "agents/herd-intake-reviewer.md").exists())
        self.assertNotIn("intake", herd.NOTE_KINDS)



class TestReviewBrief(ReviewBase):
    """0.12.1: the reviewer's brief comes from Herd's records, so it names the files the review hook checks."""

    def test_the_brief_holds_everything_the_reviewer_needs(self):
        self.ready()
        (self.root / "util.py").write_text("X = 1\n")  # a second changed code file, uncommitted
        task = herd.load_task(self.root, "t1")
        head = json.loads((self.root / ".herd/tasks/t1/start.json").read_text())["head"]
        brief = herd.review_brief(self.root, "t1")
        self.assertIn(f"Goal: {task['goal']}", brief)
        for c in task["criteria"]:
            self.assertIn(f"- {c['id']} ({c['source']}): {c['text']} Check: `{c['check']}`", brief)
        self.assertIn(f"Test budget: {task['test_budget']}", brief)
        self.assertIn(f"Known limits: {task['known_limits']}", brief)
        self.assertIn("The human's request, word for word:\n" + REQUEST, brief)
        files, _ = herd.review_files(self.root, "t1")
        self.assertEqual(files, ["app.py", "util.py"])
        self.assertIn("Read every one of these 2 changed code files with Read before you judge, or print the whole "
                      "diff:\n- app.py\n- util.py\n", brief)
        self.assertIn(f"Diff, committed and not: `git diff {head}`", brief)
        p = self.cli("review-brief")
        self.assertEqual((p.returncode, p.stdout), (0, brief))
        herd.verify(self.root, "t1")
        self.assertIn("giving it only what `herd review-brief` prints", " ".join(herd.problems(self.root, "t1")))

    def test_reading_the_listed_files_is_what_the_hook_counts(self):
        self.ready()
        (self.root / "util.py").write_text("X = 1\n")
        files, _ = herd.review_files(self.root, "t1")
        calls = [{"type": "tool_use", "name": "Read", "input": {"file_path": str(self.root / f)}} for f in files]
        lines = [json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": calls}}),
                 json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": [
                     {"type": "text", "text": "Fine.\nHERD-REVIEW: PASS"}]}})]
        self.review(builder="haiku", reviewer_lines=lines)
        self.assertEqual((self.last()["saw"], self.last()["code_unread"]), (True, []))
        self.review(builder="haiku", reviewer_lines=[lines[0].replace("util.py", "other.py"), lines[1]])
        self.assertIn("the reviewer did not read: util.py", self.state()[1])  # the gate names the missed file

    def test_the_brief_for_no_code_change_and_unknown_changes(self):
        self.ready()
        (self.root / "app.py").unlink()
        self.assertIn("Read every one of these 1 changed files (no code file changed)",
                      herd.review_brief(self.root, "t1"))
        start = self.root / ".herd/tasks/t1/start.json"
        start.write_text(json.dumps(dict(json.loads(start.read_text()), head=None)))
        self.assertIn("Changed files: unknown (no commit at `herd init`)", herd.review_brief(self.root, "t1"))


class TestPassHint(ReviewBase):
    """0.12.1: once a review that counts is recorded, `herd verify` and `herd status` say to stop and finish."""

    def test_the_hint_appears_only_for_a_counting_pass_and_states_the_rule(self):
        self.ready()
        self.assertIsNone(herd.pass_hint(self.root, "t1", herd.verify(self.root, "t1"), herd.load_notes(self.root, "t1")))
        self.assertNotIn("Review passed", self.cli("verify").stdout)
        self.review(builder="haiku", reviewer="sonnet", text="Major: x.\nHERD-REVIEW: FAIL")
        self.assertNotIn("Review passed", self.cli("verify").stdout)
        self.review(builder="haiku", reviewer="sonnet")
        hint = ("Review passed and counts: fix only Blocker and Major findings, start no new work, commit and run "
                "`herd done`; at medium risk it keeps counting after edits unless the risk rises to high, but no "
                "reviewer sees them")
        self.assertIn("  " + hint, self.cli("verify").stdout)
        self.assertIn(hint, self.cli("status").stdout)
        self.assertNotIn("Review: needs", self.cli("status").stdout)
        (self.root / "app.py").write_text("def f():\n    return 1  # edited after the PASS\n")
        self.assertNotIn("Review passed", self.cli("status").stdout)  # stale evidence: no hint until `herd verify`
        self.assertIn(hint, self.cli("verify").stdout)  # still counts at medium risk
        (self.root / "app.py").write_text("def f():\n    return 2\n")
        self.assertNotIn("Review passed", self.cli("verify").stdout)  # a failing check: not done, no hint
        (self.root / "app.py").write_text("def f():\n    return 1  # edited after the PASS\n")
        start = self.root / ".herd/tasks/t1/start.json"
        start.write_text(json.dumps(dict(json.loads(start.read_text()), risk="high")))
        ev = herd.verify(self.root, "t1")
        self.assertIsNone(herd.pass_hint(self.root, "t1", ev, herd.load_notes(self.root, "t1")))  # risk rose: void
        self.review(builder="haiku", reviewer="sonnet")
        ev = herd.verify(self.root, "t1")
        self.assertIn("at high risk any file you change after it needs another review (a commit alone does not)",
                      herd.pass_hint(self.root, "t1", ev, herd.load_notes(self.root, "t1")))
        (self.root / "app.py").write_text("def f():\n    return 1  # edited again\n")
        ev = herd.verify(self.root, "t1")
        self.assertIsNone(herd.pass_hint(self.root, "t1", ev, herd.load_notes(self.root, "t1")))
        self.assertIn("the code changed after the review, and the risk is high", " ".join(herd.problems(self.root, "t1")))


class TestHeadlessSession(ReviewBase):
    """Issue #40: in a headless `claude -p` run the agent ran `H="python3 .../herd.py"; $H init calc ...`, which the
    pre-init hook cannot read, so start.json had no session and no review counted until the first Stop block."""
    INIT = 'H="python3 /p/scripts/herd.py"; $H init calc "Add add(a, b)" --request "r" 2>&1; echo ---'

    def sessions(self):
        return json.loads((self.root / ".herd/tasks/t1/start.json").read_text()).get("sessions")

    def pre_tool(self, main, **extra):
        """What Claude Code gives a PreToolUse hook on Bash (and the guard returns None for a harmless command)."""
        hook = {"session_id": main.stem, "transcript_path": str(main), "cwd": str(self.root), "hook_event_name": "PreToolUse",
                "tool_name": "Bash", "tool_input": {"command": "git status"}} | extra
        return herd.guard(self.root, hook)

    def test_the_observed_init_command_is_not_read_by_preinit(self):
        self.assertIsNone(herd._init_target(self.INIT, self.root))

    def test_the_guard_records_the_main_session(self):
        self.ready()
        self.assertIsNone(self.sessions())
        main = transcript(self.root, "haiku", path=self.root / ".herd" / "logs" / "head.jsonl")
        self.assertIsNone(self.pre_tool(main))
        self.assertEqual(self.sessions(), [str(main)])
        self.assertIsNone(self.pre_tool(main))  # again: recorded once
        self.assertEqual(self.sessions(), [str(main)])
        self.review(builder="haiku", reviewer="sonnet", builder_path=main, seen=False)
        self.assertEqual((self.last()["builder_tier"], self.last()["round"]), ("haiku", True))

    def test_a_subagent_or_odd_input_records_nothing(self):
        self.ready()
        main = transcript(self.root, "haiku", path=self.root / ".herd" / "logs" / "head.jsonl")
        self.pre_tool(main, agent_id="a1")  # a subagent's own tool call
        for bad in (None, "", 5, ["x"]):
            herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "ls"},
                                   "transcript_path": bad})
        herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertIsNone(self.sessions())

    def test_a_hand_made_log_still_does_not_count(self):
        self.ready()
        fake = transcript(self.root, "haiku", path=self.root / ".herd" / "logs" / "fake.jsonl")
        self.review(builder="haiku", reviewer="sonnet", builder_path=fake, seen=False)  # nobody recorded it
        self.assertIsNone(self.last()["builder_tier"])
        self.assertFalse(self.last()["round"])
        cmd = f"echo '{{\"transcript_path\": \"{fake}\"}}' | python3 /p/scripts/herd.py guard"
        main = transcript(self.root, "haiku", path=self.root / ".herd" / "logs" / "head.jsonl")  # the real hook input
        self.assertEqual(self.pre_tool(main, tool_input={"command": cmd})["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.sessions(), [str(main)])  # the path in the command is never taken


class TestReviewLimitAttacks(Base):
    """The break-it pass for the review limit, on notes written straight to the log (no hook run)."""

    def rv(self, text="Major: a.py:1\nHERD-REVIEW: FAIL", **kw):
        herd.add_note(self.root, "t1", "review", text, extra={"source": "hook", "verdict": "FAIL", "round": True} | kw)

    def limit(self):
        return herd.review_limit(herd.load_notes(self.root, "t1"))

    def test_bad_input_a_hand_edited_log_never_crashes(self):
        self.start()
        self.rv()
        self.rv()
        with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:
            f.write(json.dumps({"kind": "decision"}) + "\n" + json.dumps({"kind": "review", "text": None}) + "\n"
                    + json.dumps({"text": 5}) + "\n")
        self.assertIn("review limit reached", self.limit())
        self.assertIn("review limit reached", herd.review_limit([{}, {"kind": "decision", "text": 3}] + herd.load_notes(self.root, "t1")))
        self.assertIsNone(herd.review_limit([]))

    def test_collision_identical_reviews_each_count(self):
        self.start()
        herd.add_note(self.root, "t1", "review", "same", extra={"source": "hook", "verdict": "FAIL", "round": True,
                                                                "content": "x", "risk": "medium"})
        self.assertIsNone(self.limit())
        herd.add_note(self.root, "t1", "review", "same", extra={"source": "hook", "verdict": "FAIL", "round": True,
                                                                "content": "x", "risk": "medium"})
        self.assertIn("2 reviews since the last PASS", self.limit())

    def test_one_bad_part_a_hand_written_review_does_not_count(self):
        self.start()
        self.rv()
        herd.add_review(self.root, "t1", by="me", text="looks fine")  # recorded by hand, no source: not a hook review
        self.assertIsNone(self.limit())
        self.rv()
        self.assertIsNotNone(self.limit())

    def test_recount_the_number_in_the_message_is_the_number_of_hook_reviews(self):
        self.start()
        for n in range(1, 6):
            self.rv()
            notes = herd.load_notes(self.root, "t1")
            hook = sum(1 for x in notes if x["kind"] == "review" and x.get("source") == "hook")
            msg = herd.review_limit(notes)
            self.assertEqual(msg is not None, hook >= 2)
            if msg:
                self.assertIn(f"{hook} reviews since the last PASS", msg)

    def test_refusal_no_review_after_the_limit_can_pass_or_reset(self):
        self.start()
        self.rv()
        self.rv()
        herd.add_note(self.root, "t1", "review", "No Blocker or Major.\nHERD-REVIEW: PASS",
                      extra={"source": "hook", "verdict": "PASS", "round": False, "over_cap": True})
        self.assertIn("review limit reached", self.limit())
        ev = {"risk": {"effective": "medium"}}
        notes = herd.load_notes(self.root, "t1")
        self.assertFalse(herd.review_state(self.root, "t1", ev, notes)[0])
        self.assertIn("review limit", herd.review_state(self.root, "t1", ev, notes)[1])


if __name__ == "__main__":
    unittest.main()
