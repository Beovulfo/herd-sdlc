"""0.10.0: three deterministic quality checks. Human criteria quoted verbatim (refused), required fields at medium
and high risk (refused), and what the reviewer saw, read from its own log (counted, and its bad references shown)."""
import json
import subprocess
import sys
from pathlib import Path

from scripts import herd
from tests.test_harness_rules import APP_CHECK, NO_INPUTS, REQUEST, TASK, Base
from tests.test_herd_cli import transcript
from tests.test_herd_review import ReviewBase

NARROWED = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')


class TestQuote(Base):
    """_quotes: what copying changes is ignored, what changes the meaning is not."""

    REQ = ("## Task\nPlease build it.\n\n> **Success:** the optimized route saves *more than* 20 percent of the time"
           " — vs a random walk.\n- It must return `1` for any call (even 0).\n"
           "1. Values x >= 5 are rejected; see [the spec](http://x/y).\nIt’s “fast”, isn't it?  "
           "Price is 20.5 eur.\nThe route is\nwrapped here.\n")

    def test_faithful_quotes_pass(self):
        for text in ("the optimized route saves more than 20 percent of the time vs a random walk",
                     "The optimized route saves more than 20 percent of the time - vs a random walk.",
                     "the optimized route saves more than 20 percent of the time -- vs a random walk",
                     "It must return 1 for any call (even 0)", "It must return `1` for any call",
                     "Values x >= 5 are rejected; see the spec", "It's \"fast\", isn’t it?",
                     "Price is 20.5 eur", "**Success:** the optimized route", "values x \\>= 5 are rejected",
                     "the route is wrapped here", "“It must return 1 for any call.”"):
            self.assertTrue(herd._quotes(text, self.REQ), text)

    def test_changed_meaning_is_not_a_quote(self):
        for text in ("It must return 1 for one call", "Values x > 5 are rejected", "Values x <= 5 are rejected",
                     "it must return 10 for any call", "Price is 20 eur", "Price is 20.50 eur",
                     "the route saves more than 20 percent", "must not return 1", "It must return 1 for all calls",
                     "...", "", "   "):
            self.assertFalse(herd._quotes(text, self.REQ), text)
        for text, source in (("return 1", "return 1.5"), ("version 2", "version 2.0"), ("returns 1", "returns 1-2"),
                             ("costs 1", "costs 1,000"), ("returns 23", "returns 2*3"), ("uses maxlen", "uses max_len"),
                             ("> 5 items are refused", "5 items are refused")):
            self.assertFalse(herd._quotes(text, source), (text, source))
        for text, source in (("uses max_len", "it uses max_len."), ("2*3", "returns 2*3"), ("return 1", "(return 1)")):
            self.assertTrue(herd._quotes(text, source), (text, source))


class TestVerbatimBlock(Base):
    def ready(self, text=TASK, request=True):
        if request:
            self.start(text)
        else:
            herd.init_task(self.root, "t1", "Add f() to app.py")  # no --request: nothing to quote
            (self.root / ".herd/tasks/t1/task.toml").write_text(text)
        self.red_then_build()
        self.attacks_and_review()
        return herd.verify(self.root, "t1")

    def test_an_unquoted_human_criterion_is_refused(self):
        ev = self.ready(NARROWED)
        self.assertEqual(ev["human_not_verbatim"], ["C1"])
        probs = herd.problems(self.root, "t1")
        self.assertEqual([p for p in probs if "verbatim" in p], [
            "human criterion C1 is not a verbatim quote of the request: copy the human's words into its `text` and "
            "put your own scenario in an agent-proposed criterion; if the human reworded it or wrote it elsewhere "
            "(a file they named), record their words with `herd note --human-change \"C1: <their words>\"`"])
        self.assertIn("human criterion C1", herd.next_step(probs))
        p = self.cli("done")
        self.assertEqual(p.returncode, 1)
        self.assertIn("not a verbatim quote", p.stderr)
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")

    def test_a_quote_with_markdown_and_spacing_is_not_refused(self):
        text = TASK.replace('text = "It must return 1 for any call"', 'text = "it MUST return  1 for any call."')
        self.ready(text)
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_no_recorded_request_warns_only(self):
        ev = self.ready(NARROWED, request=False)
        self.assertIsNone(ev["human_not_verbatim"])
        self.assertTrue(any("no request recorded" in w for w in ev["warnings"]))
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_the_humans_rewording_is_the_escape(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        (self.root / ".herd/tasks/t1/task.toml").write_text(NARROWED)  # changed after the first verify
        herd.verify(self.root, "t1")
        probs = " ".join(herd.problems(self.root, "t1"))
        self.assertIn("human criterion C1 changed after the first verify", probs)
        self.assertIn("C1 is not a verbatim quote", probs)
        herd.add_note(self.root, "t1", "human-change", "C2: the human said: It must return 1 for one call")
        herd.verify(self.root, "t1")  # a note for another id is not this criterion's source
        self.assertIn("C1 is not a verbatim quote", " ".join(herd.problems(self.root, "t1")))
        herd.add_note(self.root, "t1", "human-change", "C1: the human now says “It must return 1 for one call.”")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["human_not_verbatim"], [])
        self.assertEqual(herd.problems(self.root, "t1"), [])  # the freeze accepts the same note
        self.assertIn("Human criterion changed with the human's words", herd.report(ev))

    def test_a_criterion_fixed_back_to_the_request_after_the_freeze_is_not_refused(self):
        self.start(NARROWED)
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)  # the human's words, after the first verify
        ev = herd.verify(self.root, "t1")
        self.assertEqual((ev["human_changed"], ev["human_not_verbatim"]), ([], []))
        self.assertEqual(herd.problems(self.root, "t1"), [])
        cut = TASK.replace('"It must return 1 for any call"', '"It must return 1"')  # still a quote, but narrowed
        (self.root / ".herd/tasks/t1/task.toml").write_text(cut)
        herd.verify(self.root, "t1")
        self.assertIn("human criterion C1 changed after the first verify", " ".join(herd.problems(self.root, "t1")))

    def test_an_agent_proposed_criterion_needs_no_quote(self):
        text = TASK.replace("Given the module, when imported, then it defines f", "Something the human never said")
        self.ready(text)
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestRequiredFields(Base):
    def ready(self, text, risk=None):
        self.start(text)
        if risk:
            start = self.root / ".herd/tasks/t1/start.json"
            start.write_text(json.dumps(dict(json.loads(start.read_text()), risk=risk)))
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        return herd.problems(self.root, "t1")

    def test_missing_fields_are_refused_at_medium_risk_with_what_to_write(self):
        text = (TASK.replace('test_budget = "Two import probes; no unit tests"\n', "")
                .replace('known_limits = "Repeated calls are not timed."', 'known_limits = "  "')
                .replace('coverage = "Varies nothing: calls f() once; proves the return value, not repeated calls"\n', ""))
        probs = self.ready(text)
        need = [p for p in probs if " is empty" in p]
        self.assertEqual(need, [
            'test_budget is empty: add to task.toml `test_budget = "<what is tested and what is not, at which level>"`',
            'known_limits is empty: add to task.toml `known_limits = "<when the claim may fail or has not been shown>"`',
            'coverage of human criterion C1 is empty: add `coverage = "<what its check proves and what it does not>"` '
            "to it"])
        self.assertTrue(all("\n" not in p for p in need))
        self.assertEqual(herd.next_step(need), "add `test_budget` to task.toml, then run `herd verify`")
        self.assertEqual(herd.next_step(need[2:]), "add `coverage` to human criterion C1, then run `herd verify`")
        self.assertEqual(self.cli("done").returncode, 1)

    def test_present_fields_and_low_risk_are_not_refused(self):
        self.assertEqual(self.ready(TASK), [])
        bare = TASK.replace('test_budget = "Two import probes; no unit tests"\n', "")
        self.tearDown()
        self.setUp()
        self.assertEqual(self.ready(bare, risk="low"), [])  # at low risk they stay warnings

    def test_high_risk_is_refused_too(self):
        bare = TASK.replace('test_budget = "Two import probes; no unit tests"\n', "")
        self.assertIn("test_budget is empty", " ".join(self.ready(bare, risk="high")))

    def test_agent_proposed_criteria_need_no_coverage(self):
        self.assertFalse([p for p in self.ready(TASK) if "coverage" in p])  # C2 has none

    def test_quick_route_is_exempt(self):
        herd.init_task(self.root, "q1", "Fix a typo", quick_check=APP_CHECK, request=REQUEST)
        herd.verify(self.root, "q1")  # red first
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        ev = herd.verify(self.root, "q1")
        self.assertEqual(ev["risk"]["effective"], "medium")
        self.assertEqual(herd.problems(self.root, "q1"), [])


class TestInputsRefused(Base):
    """0.10.0: `inputs` is refused when missing, misplaced or incomplete at medium and high risk (a Haiku run put
    `inputs = "..."` inside each [[criteria]] table and ignored the 0.9.0 warning)."""
    MISPLACED = NO_INPUTS.replace('check = {}'.format(json.dumps(APP_CHECK)),
                                  'inputs = "Maps from 5 generated layout families"\ncheck = {}'.format(json.dumps(APP_CHECK)))

    def ready(self, text, risk=None):
        self.start(text)
        if risk:
            start = self.root / ".herd/tasks/t1/start.json"
            start.write_text(json.dumps(dict(json.loads(start.read_text()), risk=risk)))
        self.red_then_build()
        self.attacks_and_review()
        ev = herd.verify(self.root, "t1")
        return ev, [p for p in herd.problems(self.root, "t1") if "inputs" in p]

    def test_missing_inputs_are_refused_with_the_table_to_write(self):
        ev, probs = self.ready(NO_INPUTS)
        self.assertEqual(len(probs), 1)
        self.assertTrue(probs[0].startswith("no `inputs`: add to task.toml, at the top level, `[[inputs]]`, "
                                            '`human = "<the input as the human described it>"`, `program = "<the '
                                            'input as the program receives it>"`, one line each'), probs[0])
        self.assertNotIn("\n", probs[0])
        self.assertEqual(herd.next_step(probs), "add top-level `[[inputs]]` tables with `human` and `program` to "
                                                "task.toml, then run `herd verify`")
        self.assertEqual(self.cli("done").returncode, 1)

    def test_inputs_inside_a_criterion_are_reported_with_where_they_belong(self):
        _, probs = self.ready(self.MISPLACED)
        self.assertEqual(len(probs), 2, probs)
        self.assertTrue(probs[0].startswith("C1 has an `inputs` key inside its [[criteria]] table: inputs belong at "
                                            "the top level of task.toml as `[[inputs]]`"), probs[0])
        self.assertIn("not inside [[criteria]]", probs[0])
        self.assertTrue(probs[1].startswith("no `inputs`"))
        self.tearDown()
        self.setUp()
        _, probs = self.ready(self.MISPLACED.replace("[[criteria]]", "inputs = []\n\n[[criteria]]", 1))
        self.assertEqual([p.split(":", 1)[0] for p in probs], ["C1 has an `inputs` key inside its [[criteria]] table"])

    def test_an_incomplete_or_wrong_shape_input_is_refused(self):
        _, probs = self.ready(NO_INPUTS + '\n[[inputs]]\nhuman = "a call"\nprogram = " "\n')
        self.assertEqual([p.split(":", 1)[0] for p in probs], ["inputs #1"])
        self.tearDown()
        self.setUp()
        _, probs = self.ready(NO_INPUTS.replace("[[criteria]]", 'inputs = "a call"\n\n[[criteria]]', 1))
        self.assertTrue(probs[0].startswith("`inputs` must be a list of tables: write `[[inputs]]`"), probs)

    def test_complete_inputs_pass_and_are_shown_unchanged(self):
        ev, probs = self.ready(NO_INPUTS + '\n[[inputs]]\nhuman = "a call"\nprogram = "a call, as typed"\n')
        self.assertEqual(probs, [])
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("Inputs (as you described them -> as the program receives them): a call -> a call, as typed",
                      herd.report(ev))
        self.tearDown()
        self.setUp()
        self.assertEqual(self.ready(TASK)[1], [])  # `inputs = []`: it takes none

    def test_low_risk_warns_only_and_the_quick_route_is_exempt(self):
        ev, probs = self.ready(self.MISPLACED, risk="low")
        self.assertEqual(probs, [])
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertTrue([w for w in ev["warnings"] if w.startswith("C1 has an `inputs` key")])
        self.assertTrue([w for w in ev["warnings"] if w.startswith("no `inputs`")])
        self.assertEqual(herd.input_warnings({"route": "quick", "criteria": [{"id": "C1", "inputs": "x"}]}), [])

    def test_the_template_shows_a_top_level_inputs_table(self):
        herd.init_task(self.root, "t9", "g")
        text = (self.root / ".herd/tasks/t9/task.toml").read_text()
        self.assertIn('# [[inputs]]\n# human = "the input as the human described it"\n'
                      '# program = "the input as the program receives it"', text)
        self.assertLess(text.index("# [[inputs]]"), text.index("# [[criteria]]"))
        skill = (Path(herd.__file__).resolve().parent.parent / "skills/criteria/SKILL.md").read_text()
        fmt = skill.split("## Format", 1)[1]
        self.assertLess(fmt.index("[[inputs]]"), fmt.index("[[criteria]]"))
        self.assertIn("never inside [[criteria]]", fmt)


def reviewer_log(path, calls, report="No Blocker or Major.\nHERD-REVIEW: PASS", model="claude-sonnet-5-5"):
    """A reviewer log with these tool calls, as (name, input) pairs, then the report."""
    rows = [{"type": "user", "message": {"role": "user", "content": "review"}}]
    rows += [{"type": "assistant", "message": {"model": model, "content": [
        {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}} for i, (name, inp) in enumerate(calls)]
    rows += [{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}"}]}}
             for i in range(len(calls))]
    rows.append({"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": report}]}})
    return [json.dumps(r) for r in rows]


class TestReviewerSaw(ReviewBase):
    def check(self, calls, report="No Blocker or Major.\nHERD-REVIEW: PASS"):
        self.review(builder="haiku", reviewer="sonnet", reviewer_lines=reviewer_log(None, calls, report))
        return self.state()

    def test_a_review_that_saw_nothing_does_not_count(self):
        self.ready()
        for calls in ([], [("Grep", {"pattern": "f"})], [("Bash", {"command": "git diff --stat"})],
                      [("Bash", {"command": "git show --name-only HEAD"})], [("Bash", {"command": "git log -3"})],
                      [("Read", {"file_path": str(self.root / "tests/test_app.py")})],
                      [("Bash", {"command": "echo git diff"})], [("Read", {"file_path": "/elsewhere/app.py"})]):
            ok, why = self.check(calls)
            self.assertFalse(ok, calls)
            self.assertEqual(why, "the reviewer did not read: app.py, and ran no `git diff` or `git show`: spawn "
                                  "herd-reviewer again and have it read the diff", calls)
        self.assertFalse(self.last()["round"])  # a blind review is not a review round
        self.assertIn("review missing (the reviewer did not read: app.py", " ".join(herd.problems(self.root, "t1")))

    def test_a_review_that_saw_the_change_counts(self):
        self.ready()
        for calls in ([("Bash", {"command": "git diff"})], [("Bash", {"command": f"git -C {self.root} --no-pager diff HEAD~1"})],
                      [("Bash", {"command": f"cd {self.root} && git show HEAD"})], [("Bash", {"command": "git log -p -2"})],
                      [("Bash", {"command": "git diff --stat && git diff -- app.py"})],
                      [("Bash", {"command": "git diff --stat -p"})],
                      [("Read", {"file_path": str(self.root / "app.py")})], [("Read", {"file_path": "app.py"})],
                      [("Bash", {"command": "cat app.py | head"})], [("Bash", {"command": "sed -n '1,9p' ./app.py"})]):
            ok, why = self.check(calls)
            self.assertTrue(ok, (calls, why))
        n = self.last()
        self.assertEqual((n["diff_seen"], n["code_read"], n["code_total"], n["code_unread"]), (False, 1, 1, []))
        self.assertIn("(sonnet, builder on haiku; PASS; no git diff or git show, read 1 of 1 changed code file)",
                      herd._review(herd.load_notes(self.root, "t1")))
        self.check([("Bash", {"command": "git diff"})])
        self.assertIn("ran git diff or git show, read 0 of 1 changed code file)", herd._review(herd.load_notes(self.root, "t1")))

    def test_every_changed_code_file_must_be_read_without_a_diff(self):
        self.ready()
        (self.root / "util.py").write_text("X = 1\n")
        (self.root / "notes.md").write_text("doc\n")  # not code
        ok, why = self.check([("Read", {"file_path": str(self.root / "app.py")})])
        self.assertFalse(ok)
        self.assertTrue(why.startswith("the reviewer did not read: util.py, and"), why)
        ok, _ = self.check([("Read", {"file_path": str(self.root / "app.py")}), ("Bash", {"command": "cat util.py"})])
        self.assertTrue(ok)
        self.assertIn("read 2 of 2 changed code files", herd.report(herd.verify(self.root, "t1")))

    def test_git_commands_that_print_no_change_do_not_count(self):
        self.ready()
        for cmd in ("git diff --check", "git diff --output=/tmp/x", "git diff > /dev/null", "git show -s HEAD",
                    "git diff --stat=80"):
            self.assertFalse(self.check([("Bash", {"command": cmd})])[0], cmd)

    def test_a_change_without_code_files_needs_its_files_read(self):
        self.ready()
        (self.root / "app.py").unlink()  # now only tests/test_app.py changed: no code file
        (self.root / "__pycache__").mkdir(exist_ok=True)  # build output, as CI leaves it with no global gitignore
        (self.root / "__pycache__/app.cpython-311.pyc").write_bytes(b"x")
        (self.root / "run.log").write_text("x")
        self.assertFalse(self.check([])[0])
        self.assertIn("the reviewer did not read: tests/test_app.py", self.state()[1])
        self.assertTrue(self.check([("Read", {"file_path": str(self.root / "tests/test_app.py")})])[0])
        self.assertIn("read 1 of 1 changed file)", herd._review(herd.load_notes(self.root, "t1")))

    def test_unknown_changes_do_not_block(self):
        self.ready()
        start = self.root / ".herd/tasks/t1/start.json"
        start.write_text(json.dumps(dict(json.loads(start.read_text()), head=None)))
        self.assertTrue(self.check([])[0])
        self.assertIn("changed files unknown", herd._review(herd.load_notes(self.root, "t1")))

    def test_a_review_from_before_0_10_does_not_count(self):
        self.ready()
        self.review(builder="haiku", reviewer="sonnet")
        notes = herd.load_notes(self.root, "t1")
        for key in ("saw", "diff_seen", "code_total", "code_read", "code_unread", "bad_refs"):
            notes[-1].pop(key)
        (self.root / ".herd/tasks/t1/notes.jsonl").write_text("".join(json.dumps(n) + "\n" for n in notes))
        self.assertIn("recorded before Herd 0.10.0 checked what the reviewer read", self.state()[1])

    def test_handback_and_last_message_reports_still_need_the_tool_calls(self):
        self.ready()
        self.review(builder="haiku", reviewer="sonnet", handback=True, saw=False)
        self.assertIn("the reviewer did not read: app.py", self.state()[1])
        self.review(builder="haiku", reviewer="sonnet", handback=True)
        self.assertTrue(self.state()[0])
        self.review(builder="haiku", reviewer="sonnet", text=None, last_message="ok\nHERD-REVIEW: PASS")
        self.assertTrue(self.state()[0])  # the last line is a `git diff` call

    def test_the_hook_stays_silent_and_non_blocking(self):
        self.ready()
        main = transcript(self.root, "sonnet", path=self.root / ".herd/logs/sx.jsonl")
        rev = main.parent / "sx" / "subagents" / "agent-q.jsonl"
        rev.parent.mkdir(parents=True)
        rev.write_text("\n".join(reviewer_log(None, [("Read", {"file_path": 7}), ("Bash", {"command": "git diff '"}),
                                                     ("Read", {"file_path": "a\x00b"}), ("Bash", {"command": "cat a\x00b"}),
                                                     ("Bash", {"command": ["git", "diff"]}), ("Read", {})],
                                              "Blocker: app.py:999\nHERD-REVIEW: PASS")) + "\n")
        herd._see_session(self.root, "t1", str(main))
        hook = {"cwd": str(self.root), "agent_type": "herd:herd-reviewer", "agent_id": "q",
                "transcript_path": str(main), "agent_transcript_path": str(rev)}
        p = subprocess.run([sys.executable, str(Path(herd.__file__)), "review-hook"], cwd=self.root,
                           input=json.dumps(hook), capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        n = self.last()
        self.assertEqual((n["diff_seen"], n["bad_refs"]), (True, ["app.py:999 (app.py has 2 lines)"]))

    def test_the_builder_cannot_write_the_reviewer_log(self):
        self.ready()
        main = transcript(self.root, "sonnet")
        log = main.parent / main.stem / "subagents" / "agent-z.jsonl"
        for cmd in (f"cp fake.jsonl {log}", f"mv fake.jsonl {log}", f"tee -a {log} < fake.jsonl"):
            out = herd.guard(self.root, {"cwd": str(self.root), "tool_name": "Bash", "transcript_path": str(main),
                                         "tool_input": {"command": cmd}})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", cmd)


class TestBadRefs(ReviewBase):
    def test_refs_in_the_repository_are_fine_and_bad_ones_are_shown_not_refused(self):
        self.ready()
        (self.root / "src").mkdir()
        (self.root / "src/a.go").write_text("1\n2\n3\n")
        report = ("Nit: app.py:2 name. Nit: `src/a.go:1-3` ok. Nit: a.go:3 by its name alone. Nit: tests/test_app.py:1:4 col. See "
                  "http://example.com/x.py:3 and C1:2 at 10:30.\nMajor: app.py:3 off the end; src/a.go:2-4 past it; "
                  "missing.py:1 gone; src/a.go:0 zero; app.py:3 again; ../outside.py:1; /etc/hosts:1\n"
                  "HERD-REVIEW: PASS")
        self.review(builder="haiku", reviewer="sonnet", text=report)
        bad = ["app.py:3 (app.py has 2 lines)", "src/a.go:2-4 (src/a.go has 3 lines)",
               "missing.py:1 (no such file in the repository)", "src/a.go:0 (lines start at 1)",
               "../outside.py:1 (no such file in the repository)", "/etc/hosts:1 (no such file in the repository)"]
        self.assertEqual(self.last()["bad_refs"], bad)
        self.assertTrue(self.state()[0])  # recorded, never refused
        ev = herd.verify(self.root, "t1")
        line = "The review cites lines not in the repository now: " + "; ".join(bad)
        self.assertIn(line, herd.report(ev))
        self.assertIn("- " + line, herd.pr_body(self.root, "t1"))
        self.assertIn(line, " ".join(herd.final_report(self.root, "t1", ev, herd.load_notes(self.root, "t1"))))
        self.review(builder="haiku", reviewer="sonnet", text="Nit: app.py:1 fine.\nHERD-REVIEW: PASS")
        self.assertNotIn("cites lines", herd.report(herd.verify(self.root, "t1")))  # only the latest review

    def test_a_path_from_the_repository_top_counts_in_a_subfolder_project(self):
        pkg = self.root / "pkg"
        pkg.mkdir()
        (self.root / "top.py").write_text("x = 1\n")
        self.assertEqual(herd.bad_refs(pkg, "top.py:1 pkg/nope.py:1"), ["pkg/nope.py:1 (no such file in the repository)"])
        self.assertEqual(herd.bad_refs(self.root, "a symlink-free text with no refs"), [])
        self.assertEqual(len(herd.bad_refs(self.root, " ".join(f"m{i}.py:1" for i in range(50)))), herd.MAX_REFS)

