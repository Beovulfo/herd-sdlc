"""docs/designs/herd-focused-review.md: the focus list, the hook's answers and the delta (Herd 0.13.0)."""
import glob
import json
import os
import time
import tomllib
import unittest
import unittest.mock
from pathlib import Path

from scripts import herd
from tests.test_herd_review import ReviewBase

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "focus-replay"


def task(**kw):
    t = {"goal": "g", "test_budget": "unit tests", "known_limits": "- may fail on list order\n* slow on big maps\n\n3. odd",
         "inputs": [{"human": "all products", "program": "{id, x, y}"}, {"human": "a list", "program": "ids"}],
         "criteria": [{"id": "C1", "source": "human", "text": "t1", "coverage": "proves a", "check": "true"},
                      {"id": "C2", "source": "agent-proposed", "text": "t2", "coverage": "ignored", "check": "true"},
                      {"id": "C3", "source": "human", "text": "t3", "coverage": "", "check": "true"},
                      {"id": "C4", "source": "human", "text": "t4", "coverage": "proves d", "check": ""}]}
    return task_with(t, kw)


def task_with(t, kw):
    t.update(kw)
    return t


def note(kind, text="x", **kw):
    return {"at": "2026-01-01T00:00:00Z", "kind": kind, "text": text} | kw


def tried(attack, text=None, check="python3 -m unittest"):
    return note("tried", text or f"{attack} done", attack=attack, **({"check": check} if check else {}))


NOTES = [note("found", "a bug"), note("open", "limit one"), tried("bad-input"), tried("collision"),
         note("decision", "chose x"), tried("refusal", "n/a: no refusals", check=None), note("open", "limit two"),
         note("tried", "no attack field", check="ls"), tried("bad-input", "second bad-input")]


def by_id(items):
    return {i["id"]: i for i in items}


class FocusItemsTests(unittest.TestCase):
    def test_focus_items_one_per_entry(self):
        items = herd.focus_items(task(), NOTES)
        ids = [i["id"] for i in items]
        self.assertEqual(ids, ["A:C1", "A:C4", "B:budget", "B:limit-1", "B:limit-2", "B:limit-3",
                               "B:note-1", "B:note-4", "B:note-6", "C:bad-input", "C:collision", "C:refusal",
                               "D:1", "D:2"])
        for i in items:
            self.assertEqual(set(i), {"id", "cat", "quote", "qhash", "attack_with"})
            self.assertEqual(i["cat"], i["id"][0])
        got = by_id(items)
        self.assertEqual(got["A:C1"]["quote"], "proves a")
        self.assertIn("true", got["A:C1"]["attack_with"])
        self.assertIn("no check", got["A:C4"]["attack_with"])
        self.assertEqual(got["B:limit-1"]["quote"], "may fail on list order")  # the list marker is not text
        self.assertEqual(got["B:limit-3"]["quote"], "odd")
        self.assertEqual(got["C:bad-input"]["quote"], "second bad-input")  # the latest note of an attack
        self.assertIn("n/a: no refusals", got["C:refusal"]["attack_with"])
        self.assertEqual(got["D:1"]["quote"], "all products -> {id, x, y}")
        self.assertIn("not from the `program` form", got["D:1"]["attack_with"])
        self.assertEqual(herd.focus_items(task(known_limits="", test_budget="", inputs=[]), []), [
            {"id": "A:C1", **{k: v for k, v in by_id(items)["A:C1"].items() if k != "id"}},
            {"id": "A:C4", **{k: v for k, v in by_id(items)["A:C4"].items() if k != "id"}}])
        self.assertEqual(herd.focus_items({"criteria": [], "inputs": ["x", 3]}, []), [])

    def test_focus_items_ids_are_stable(self):
        before = herd.focus_items(task(), NOTES)
        more = NOTES + [note("open", "late"), note("decision", "later"), tried("recount")]
        after = herd.focus_items(task(), more)
        self.assertEqual([i for i in after if i["id"] in by_id(before)], before)  # nothing renumbered
        self.assertEqual([i["id"] for i in after if i["id"] not in by_id(before)],
                         ["B:note-9", "B:note-10", "C:recount"])
        t = task(known_limits="- may fail on list order\n- slow on big maps\n\n- odd\n- fourth")
        self.assertIn("B:limit-4", by_id(herd.focus_items(t, NOTES)))
        self.assertEqual(herd.focus_items(task(), NOTES), before)  # a second call gives the same

    def test_focus_items_ignore_wording(self):
        a = herd.focus_items(task(), NOTES)
        t = task()
        t["criteria"][0]["coverage"] = "nothing like it, but any every whatever"
        t["known_limits"] = "- zzz\n* qqq\n\n3. rrr"
        t["test_budget"] = "all reworded"
        t["inputs"][0]["human"] = "other words"
        n = [dict(x, text="reworded: any every only first") if x["kind"] != "tried" else dict(x, text="n/a: reworded" if "n/a" in x["text"] else "other")
             for x in NOTES]
        b = herd.focus_items(t, n)
        self.assertEqual([i["id"] for i in a], [i["id"] for i in b])
        self.assertNotEqual([i["qhash"] for i in a], [i["qhash"] for i in b])
        c = herd.focus_items(task(), [dict(x, text="x") if x["kind"] in ("open", "decision") else x for x in NOTES])
        self.assertEqual([i["qhash"] for i in a if i["cat"] != "B" or "note" not in i["id"]],
                         [i["qhash"] for i in c if i["cat"] != "B" or "note" not in i["id"]])

    def test_focus_cap_keeps_decisions(self):
        notes = [note("open", f"open {k}") for k in range(40)] + [note("decision", f"decision {k}") for k in range(5)]
        t = task(known_limits="", test_budget="", inputs=[])
        items = herd.focus_items(t, notes)
        ids = [i["id"] for i in items]
        self.assertEqual(len([i for i in ids if i.startswith("B:note") and int(i[7:]) >= 40]), 5)  # every decision kept
        opens = [i for i in ids if i.startswith("B:note") and int(i[7:]) < 40]
        self.assertEqual(len(opens) + 2, 30)  # A:C1, A:C4 and the newest open notes make 30
        self.assertEqual(opens, [f"B:note-{k}" for k in range(12, 40)])  # the oldest are cut
        self.assertEqual(herd.focus_cut(t, notes), 12)
        many = task(known_limits="\n".join(f"limit {k}" for k in range(35)), test_budget="")
        items = herd.focus_items(many, notes)  # the rest alone exceed 30: only open notes were cut, all of them
        self.assertEqual([i for i in items if i["id"].startswith("B:note") and int(i["id"][7:]) < 40], [])
        self.assertEqual(len([i for i in items if i["id"].startswith("B:limit")]), 35)
        self.assertEqual(herd.focus_cut(many, notes), 40)
        self.assertEqual(herd.focus_cut(task(), NOTES), 0)


def replay(folder, task_file="task.toml"):
    t = tomllib.loads((folder / task_file).read_text())
    n = [json.loads(line) for line in (folder / "notes.jsonl").read_text().splitlines() if line.strip()]
    return t, n


def report(label, runs):
    print(f"\nreplay {label}: items per run " + ", ".join(f"{k}={len(v)}" for k, v in runs.items()))
    for k, items in runs.items():
        print(f"  run {k}: " + " ".join(i["id"] for i in items))


class ReplayTests(unittest.TestCase):
    def test_replay_points_at_findings_0121(self):
        runs = {}
        for k in range(1, 7):
            t, n = replay(FIXTURES / f"run{k}")
            self.assertFalse([x for x in n if x["kind"] == "review"], k)  # cut at the first review note
            items = herd.focus_items(t, n)
            self.assertLessEqual(len([i for i in items if not (i["id"].startswith("B:note") and
                                                               n[int(i["id"][7:])]["kind"] == "decision")]), 30, k)
            runs[k] = items
        report("0.12.1", runs)
        got = by_id(runs[6])
        self.assertIn("stores beyond 300x300", got["A:C2"]["quote"])  # the unbounded cache, a Major in the round
        self.assertIn("even very big ones", got["A:C2"]["attack_with"])  # against the human claim
        self.assertIn("x,y", got["D:1"]["quote"])  # the bare cell: the lost-store form
        self.assertIn("plain flood fill", got["C:refusal"]["quote"])  # the check that shared the code's assumption

    def test_replay_points_at_findings_0120(self):
        base = os.environ.get("HERD_BENCH_DIR")
        if not base:
            self.skipTest("HERD_BENCH_DIR is not set: the six 0.12.0 run folders are not here")
        runs = {}
        for k in range(1, 7):
            hit = glob.glob(f"{base}/*0.12.0*-{k}/.herd/tasks/*")
            self.assertTrue(hit, f"no 0.12.0 run {k} under {base}")
            t = tomllib.loads(Path(hit[0], "task.toml").read_text())
            n = [json.loads(line) for line in Path(hit[0], "notes.jsonl").read_text().splitlines() if line.strip()]
            cut = next((i for i, x in enumerate(n) if x["kind"] == "review"), len(n))
            runs[k] = herd.focus_items(t, n[:cut])
        report("0.12.0", runs)

        def has(k, pred):
            return any(pred(i) for i in runs[k])
        rows = {"run1 pick side": has(1, lambda i: i["cat"] == "A" and "whatever" in i["attack_with"]),
                "run1 TypeError": has(1, lambda i: i["id"] == "C:bad-input"),
                "run4 OverflowError": has(4, lambda i: i["id"] == "C:bad-input"),
                "run4 entrance picks": has(4, lambda i: i["id"] in ("C:collision", "C:recount")),
                "run5 list order": has(5, lambda i: i["id"].startswith("B:limit") and "list order" in i["quote"]),
                "run5 mean only": has(5, lambda i: i["id"] == "A:C4"),
                "run6 first access cell": has(6, lambda i: i["id"] == "B:budget"),
                "run6 stale budget": has(6, lambda i: i["id"] == "B:budget"),
                "run2 lost store": has(2, lambda i: i["id"].startswith("B:note") and "neighbour" in i["quote"]),
                "run5 lost store": has(5, lambda i: i["id"] == "D:1")}
        print("rows not pointed at: " + (", ".join(k for k, v in rows.items() if not v) or "none"))
        self.assertGreaterEqual(sum(rows.values()), 8, rows)


PASS_CMD = "python3 -c \"print('{}')\""  # a command that exits 0 and differs per id
BREAK_CMD = "python3 -c \"import sys; print('defect'); sys.exit(3)\""


class FocusBase(ReviewBase):
    """A medium-risk focus task: 8 items (A:C1, B:budget, B:limit-1 and the five attacks C:*)."""

    def focused(self):
        self.ready()
        return self.brief()

    def review(self, **kw):
        return super().review(answers=False, **kw)  # the tests write the answers themselves

    def brief(self):
        task, notes = herd.load_task(self.root, "t1"), herd.load_notes(self.root, "t1")
        files, _ = herd.review_files(self.root, "t1")
        self.items = herd.focus_items(task, notes, files or ())
        return herd.add_focus_round(self.root, "t1", self.items)

    def ids(self):
        return [i["id"] for i in self.items]

    def lines(self, brief, **over):
        """BRIEF and one answer per item: holds with a passing command, unless over[id] (with : as _) replaces it."""
        out = [f"BRIEF {brief}"]
        for i in self.items:
            out.append(over.get(i["id"].replace(":", "_").replace("-", "_")) or
                       f"FOCUS {i['id']}: holds: {PASS_CMD.format(i['id'])}")
        return out

    def answer(self, brief, extra=(), **over):
        self.review(text="\n".join(self.lines(brief, **over) + list(extra)), builder="haiku", reviewer="sonnet")
        return self.last()


class FocusHookTests(FocusBase):
    def test_unanswered_focus_item_does_not_count(self):
        b = self.focused()
        lines = self.lines(b)[:-2]  # the last two items are not answered
        self.review(text="\n".join(lines), builder="haiku", reviewer="sonnet")
        n = self.last()
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["unanswered"], self.ids()[-2:])
        self.assertIn(self.ids()[-1], n["focus"]["why"])
        self.assertFalse(self.state()[0])
        self.review(text="Looks fine.\nHERD-REVIEW: PASS", builder="haiku", reviewer="sonnet")  # prose, as before
        n = self.last()
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["unanswered"], self.ids())
        self.assertFalse(self.state()[0])
        n = self.answer(b, **{"C_refusal": "FOCUS C:nope: holds: python3 -c 1"})  # an unknown id and a missing one
        self.assertEqual(n["verdict"], "none")
        self.assertIn("C:nope", n["focus"]["why"])
        self.assertEqual(n["focus"]["unanswered"], ["C:refusal"])

    def test_breaks_without_command_does_not_count(self):
        b = self.focused()
        for bad in ("FOCUS C:recount: breaks:", "FOCUS C:recount: breaks:   ", "FOCUS C:recount: breaks"):
            n = self.answer(b, C_recount=bad)
            self.assertEqual((n["verdict"], n["round"]), ("none", False), bad)
            self.assertIn("C:recount", n["focus"]["why"])
            self.assertIn("C:recount", n["focus"]["unanswered"])

    def test_stale_or_missing_brief_does_not_count(self):
        b = self.focused()
        old = b
        herd.add_note(self.root, "t1", "open", "a limit added while the reviewer ran")  # one more item
        n = self.answer(old)  # the brief is the latest round, but the items now have one more
        self.assertEqual(n["verdict"], "none")
        self.assertIn("B:note-", n["focus"]["why"])
        b2 = self.brief()
        n = self.answer(old)  # an older round
        self.assertEqual(n["verdict"], "none")
        self.assertIn("not the latest brief", n["focus"]["why"])
        text = "\n".join(self.lines(b2)[1:])
        self.review(text=text, builder="haiku", reviewer="sonnet")
        self.assertIn("no BRIEF line", self.last()["focus"]["why"])
        lines = self.lines(b2)
        self.review(text="\n".join(["Report", "", lines[0], "(prose)"] + lines[1:]), builder="haiku",
                    reviewer="sonnet")  # BRIEF on line 3, not first
        self.assertEqual(self.last()["verdict"], "PASS")

    def test_holds_needs_a_passing_command(self):
        b = self.focused()
        n = self.answer(b)  # CUJ 3: every item holds
        self.assertEqual((n["verdict"], n["round"]), ("PASS", True))
        self.assertEqual(n["focus"]["holds"], self.ids())
        self.assertEqual(n["focus"]["unconfirmed"], [])
        self.assertTrue(self.state()[0])
        cases = {"exit 1": "python3 -c \"import sys; sys.exit(1)\"", "no file reader": "cat app.py",
                 "a pipe of readers": "grep -n f app.py | head -3", "git diff": "git diff HEAD",
                 "sed -n": "sed -n 1,2p app.py", "git log -p": "git log -p"}
        for why, cmd in cases.items():
            n = self.answer(b, C_refusal=f"FOCUS C:refusal: holds: {cmd}")
            self.assertEqual((n["verdict"], n["round"]), ("none", False), why)
            self.assertEqual(n["focus"]["unconfirmed"], ["C:refusal"], why)
            self.assertIn("C:refusal", n["focus"]["why"])
        ok = "python3 -c \"import app; assert app.f() == 1\" && cat app.py | wc -l"  # a reader inside a longer command
        self.assertEqual(self.answer(b, C_refusal=f"FOCUS C:refusal: holds: {ok}")["verdict"], "PASS")
        same = PASS_CMD.format("one")
        n = self.answer(b, C_refusal=f"FOCUS C:refusal: holds: {same}", C_recount=f"FOCUS C:recount: holds:  {same} ")
        self.assertEqual(n["verdict"], "none")  # the command of another item
        self.assertIn("same command", n["focus"]["why"])

    def break_with(self, **over):
        return self.answer(self.focused(), **over)

    def test_break_confirmed_by_failing_command(self):
        n = self.break_with(C_recount=f"FOCUS C:recount: breaks: {BREAK_CMD}")
        self.assertEqual((n["verdict"], n["round"]), ("FAIL", True))
        [br] = n["focus"]["breaks"]
        self.assertEqual((br["id"], br["exit"], br["confirmed"]), ("C:recount", 3, True))
        self.assertIn("defect", br["tail"])
        self.assertEqual(br["command"], BREAK_CMD)
        self.assertNotIn("C:recount", n["focus"]["holds"])
        full = herd.focus_rounds(self.root, "t1")[-1]["reviews"][-1]  # the full answers are kept in focus.json
        self.assertEqual(full["answers"]["C:recount"]["command"], BREAK_CMD)
        self.assertEqual(full["answers"]["C:recount"]["exit"], 3)

    def test_exit_one_is_unconfirmed(self):
        bad = "python3 -c \"import nosuchmodule\""  # a NameError or typo exits 1
        n = self.break_with(C_recount=f"FOCUS C:recount: breaks: {bad}")
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["unconfirmed"], ["C:recount"])
        self.assertIn("C:recount", n["focus"]["why"])
        n = self.answer(herd.focus_rounds(self.root, "t1")[-1]["brief"], C_recount=f"FOCUS C:recount: breaks: {bad}",
                        C_refusal=f"FOCUS C:refusal: breaks: {BREAK_CMD}")
        self.assertEqual(n["verdict"], "FAIL")  # a confirmed break elsewhere still fails, and names the other
        self.assertEqual(n["focus"]["unconfirmed"], ["C:recount"])

    def test_denied_command_is_unconfirmed(self):
        denied = f"git push origin nowhere; {BREAK_CMD}"
        before = [x for x in herd.load_notes(self.root, "t1") if x["kind"] == "guard"]
        n = self.break_with(C_recount=f"FOCUS C:recount: breaks: {denied}")
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["unconfirmed"], ["C:recount"])
        self.assertIsNone(n["focus"]["breaks"][0]["exit"])  # never run
        self.assertEqual([x for x in herd.load_notes(self.root, "t1") if x["kind"] == "guard"], before)  # no note

    def test_break_that_passes_is_unconfirmed(self):
        n = self.break_with(C_recount=f"FOCUS C:recount: breaks: {PASS_CMD.format('fine')}")
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["breaks"][0]["exit"], 0)
        self.assertFalse(n["focus"]["breaks"][0]["confirmed"])

    def test_reader_break_is_unconfirmed(self):
        n = self.break_with(C_recount="FOCUS C:recount: breaks: grep -n return app.py | head -2")
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertIsNone(n["focus"]["breaks"][0]["exit"])
        self.assertIn("file reader", n["focus"]["breaks"][0]["why"])
        self.assertTrue(herd.focus_reader("cat a.py && head b.py"))
        self.assertTrue(herd.focus_reader("git diff HEAD | grep x"))
        self.assertFalse(herd.focus_reader("python3 -c \"print(open('a').read())\""))
        self.assertFalse(herd.focus_reader("cat a.py | python3 check.py"))
        self.assertFalse(herd.focus_reader("sed -i s/a/b/ a.py"))

    def test_verdict_from_answers_not_severity(self):
        b = self.focused()
        words = "Blocker: this is Major, a Nit, Minor and severe.\nHERD-REVIEW: FAIL"
        self.review(text="\n".join(self.lines(b)) + "\n" + words, builder="haiku", reviewer="sonnet")
        self.assertEqual(self.last()["verdict"], "PASS")  # holds all: severity words decide nothing
        n = self.answer(b, extra=("No Blocker or Major.", "HERD-REVIEW: PASS"), C_recount=f"FOCUS C:recount: breaks: {BREAK_CMD}")
        self.assertEqual(n["verdict"], "FAIL")  # a confirmed break fails, whatever the last line says

    def test_extra_without_command_does_not_fail(self):
        b = self.focused()
        n = self.answer(b, extra=("EXTRA: app.py:1 the README says 12, the code 8",))
        self.assertEqual((n["verdict"], n["round"]), ("PASS", True))
        self.assertEqual(len(n["focus"]["extra"]), 1)
        self.assertEqual(n["focus"]["extra"][0]["id"], "x0.1")
        n = self.answer(b, extra=(f"EXTRA: app.py:1 wrong :: {BREAK_CMD}",))
        self.assertEqual(n["verdict"], "FAIL")  # with a command that exits 3 on the rerun
        self.assertTrue(n["focus"]["extra"][0]["confirmed"])
        n = self.answer(b, extra=("EXTRA: app.py:1 wrong :: python3 -c \"import sys; sys.exit(1)\"",))
        self.assertEqual(n["verdict"], "PASS")  # an unconfirmed EXTRA is shown, never none
        self.assertFalse(n["focus"]["extra"][0]["confirmed"])

    def test_rerun_deadline(self):
        b = self.focused()
        slow = "python3 -c \"import time; time.sleep(30)\""
        with unittest.mock.patch.object(herd, "FOCUS_CMD_S", 1), unittest.mock.patch.object(herd, "FOCUS_TOTAL_S", 2):
            t = time.monotonic()
            n = self.answer(b, C_collision=f"FOCUS C:collision: holds: {slow} # a",
                            C_recount=f"FOCUS C:recount: holds: {slow} # b",
                            C_refusal=f"FOCUS C:refusal: breaks: {slow} # c")
            took = time.monotonic() - t
        self.assertLess(took, 8)
        self.assertEqual(n["verdict"], "none")
        self.assertEqual(sorted(n["focus"]["unconfirmed"]), ["C:collision", "C:one-bad-part", "C:recount", "C:refusal"])
        self.assertIn("timeout", n["focus"]["breaks"][0]["tail"])  # breaks run first, 1 s each, then the cap is spent
        full = herd.focus_rounds(self.root, "t1")[-1]["reviews"][-1]["answers"]
        self.assertIsNone(full["C:collision"]["exit"])
        self.assertIn("total", full["C:recount"]["tail"] + full["C:collision"]["tail"])

    def test_rerun_that_changes_content_is_none(self):
        b = self.focused()
        mutate = "python3 -c \"open('app.py', 'a').write('# changed')\"; python3 -c \"import sys; sys.exit(3)\""
        n = self.answer(b, C_recount=f"FOCUS C:recount: breaks: {mutate}")
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertIn("changed the content", n["focus"]["why"])

    def test_review_needs_focus_round(self):
        self.focused()
        (herd._dir(self.root, "t1") / "focus.json").unlink()  # the builder never ran review-brief
        self.review(builder="haiku", reviewer="sonnet", text="No Blocker or Major.\nHERD-REVIEW: PASS")
        n = self.last()
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertIn("herd review-brief", n["focus"]["why"])
        self.assertFalse(self.state()[0])
        b = self.brief()  # a round exists, but the report is a verdict line and no answers
        self.review(builder="haiku", reviewer="sonnet", text=f"BRIEF {b}\nNo Blocker or Major.\nHERD-REVIEW: PASS")
        n = self.last()
        self.assertEqual((n["verdict"], n["round"]), ("none", False))
        self.assertEqual(n["focus"]["unanswered"], self.ids())


DEFECT = "python3 -c \"import os, sys; sys.exit(3 if os.path.exists('defect.txt') else 0)\""  # exits 3 while the defect is there


class FocusBreakTests(FocusBase):
    def broken(self):
        """A confirmed break of C:recount whose command exits 3 until defect.txt is removed."""
        (self.root / "defect.txt").write_text("x")
        b = self.focused()
        n = self.answer(b, C_recount=f"FOCUS C:recount: breaks: {DEFECT}")
        self.assertEqual((n["verdict"], n["round"]), ("FAIL", True))
        return b

    def test_open_break_blocks_done(self):
        self.broken()
        ev = herd.verify(self.root, "t1")
        [fb] = ev["focus_breaks"]
        self.assertEqual((fb["id"], fb["exit"], fb["open"], fb["command"]), ("C:recount", 3, True, DEFECT))
        probs = herd.problems(self.root, "t1")
        self.assertEqual(probs[0], f"focus item C:recount still breaks: `{DEFECT}`")
        self.assertIn("herd review-brief", herd.next_step(probs))
        self.assertEqual(self.cli("done").returncode, 1)
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        (self.root / "defect.txt").unlink()  # the fix: the command passes now
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["focus_breaks"][0]["exit"], 0)
        self.assertFalse([p for p in herd.problems(self.root, "t1") if "still breaks" in p])  # shown, not blocking
        self.assertTrue([p for p in herd.problems(self.root, "t1") if "review missing" in p])  # but a review must count
        self.answer(self.brief())  # a full review, every item holds
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertFalse(herd.verify(self.root, "t1")["focus_breaks"][0]["open"])
        self.assertEqual(self.cli("done").returncode, 0)

    def test_next_review_is_full_list(self):
        self.broken()
        (self.root / "defect.txt").unlink()
        herd.verify(self.root, "t1")
        text = herd.review_brief(self.root, "t1")
        last = herd.focus_rounds(self.root, "t1")[-1]
        task, notes = herd.load_task(self.root, "t1"), herd.load_notes(self.root, "t1")
        every = [i["id"] for i in herd.focus_items(task, notes, herd.review_files(self.root, "t1")[0] or ())]
        self.assertEqual([i["id"] for i in last["items"]], every)  # not only the broken item
        self.assertEqual(len(every), len(self.items))
        self.assertTrue(all(f"- {i}: " in text for i in every))
        self.assertNotIn("delta", text.lower())

    def test_holds_closes_open_break(self):
        self.broken()
        herd.verify(self.root, "t1")
        self.assertTrue(herd.focus_breaks(herd.load_notes(self.root, "t1"), {"C:recount"})["C:recount"]["open"])
        n = self.answer(self.brief())  # the defect file is still there: the old command still exits 3
        self.assertEqual((n["verdict"], n["round"]), ("PASS", True))
        ev = herd.verify(self.root, "t1")
        self.assertEqual((ev["focus_breaks"][0]["exit"], ev["focus_breaks"][0]["open"]), (3, False))
        self.assertEqual(herd.problems(self.root, "t1"), [])  # the reviewer closed it, the builder could not
        notes = herd.load_notes(self.root, "t1")
        self.assertIn("C:recount was closed by a later review with its command still exiting 3", " ".join(herd._rule_lines(ev, notes)))
        self.review(text="\n".join(self.lines(self.brief())), builder="haiku", reviewer="haiku")  # too low a tier: no round
        herd.verify(self.root, "t1")
        self.assertFalse([p for p in herd.problems(self.root, "t1") if "still breaks" in p])  # closed by the counting one
        n = self.answer(self.brief(), C_recount=f"FOCUS C:recount: breaks: {DEFECT}")  # it breaks again: open again
        herd.verify(self.root, "t1")
        self.assertTrue([p for p in herd.problems(self.root, "t1") if "still breaks" in p])

    def test_none_review_does_not_close_a_break(self):
        self.broken()
        self.review(text="BRIEF nothing", builder="haiku", reviewer="sonnet")
        herd.verify(self.root, "t1")
        self.assertTrue([p for p in herd.problems(self.root, "t1") if "still breaks" in p])


class FocusReasonTests(FocusBase):
    def test_unanswered_reviews_escalate(self):
        b = self.focused()
        for k in range(2):
            self.review(text="Fine.\nHERD-REVIEW: PASS", builder="haiku", reviewer="sonnet")
            herd.verify(self.root, "t1")
            self.assertEqual(herd._escalations(self.root, "t1"), [], k)
        self.review(text=f"BRIEF {b}", builder="haiku", reviewer="sonnet")  # another cause, still none
        herd.verify(self.root, "t1")
        self.assertEqual(herd._escalations(self.root, "t1"), ["3 reviews in a row did not count"])
        out = herd.gate(self.root, {})
        self.assertIn("3 reviews in a row did not count: ask the human one question", out["reason"])
        self.answer(b)  # a review that counts ends the run
        herd.verify(self.root, "t1")
        self.assertEqual(herd._escalations(self.root, "t1"), [])
        self.review(text="x", builder="haiku", reviewer="sonnet")
        self.review(text="x", builder="haiku", reviewer="sonnet")
        self.answer(b, C_recount=f"FOCUS C:recount: breaks: {BREAK_CMD}")  # a FAIL between two none runs interrupts them
        self.review(text="x", builder="haiku", reviewer="sonnet")
        self.assertEqual(herd._escalations(self.root, "t1"), [])

    def test_reasons_name_the_ids_not_severity(self):
        b = self.focused()
        self.review(text="\n".join(self.lines(b)[:-1]), builder="haiku", reviewer="sonnet")
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn(f"not answered: {self.ids()[-1]}", why)
        self.assertNotIn("Blocker", why)
        self.answer(b, C_recount=f"FOCUS C:recount: breaks: {BREAK_CMD}")
        ok, why = self.state()
        self.assertFalse(ok)
        self.assertIn("C:recount", why)
        self.assertIn("herd review-brief", why)
        self.assertNotIn("Blocker", why)


class FocusBriefTests(FocusBase):
    def test_review_brief_prints_focus(self):
        self.ready()
        text = herd.review_brief(self.root, "t1")
        rounds = herd.focus_rounds(self.root, "t1")
        self.assertEqual(len(rounds), 1)
        self.assertIn(f"\nBrief: {rounds[0]['brief']}\n", text)
        self.assertIn("Focus list: answer every id", text)
        task, notes = herd.load_task(self.root, "t1"), herd.load_notes(self.root, "t1")
        items = herd.focus_items(task, notes, herd.review_files(self.root, "t1")[0] or ())
        self.assertEqual(rounds[0]["items"], [{"id": i["id"], "qhash": i["qhash"]} for i in items])
        for i in items:
            self.assertIn(f"- {i['id']}: {i['quote']}\n  Attack with: {i['attack_with']}\n", text)
        self.assertLess(text.index("Focus list"), text.index("Read every one of these"))  # before the file list
        self.assertIn("FOCUS <id>: holds: <command>", text)
        self.assertIn("exits 3", text)
        herd.review_brief(self.root, "t1")  # a second brief adds a round and overwrites nothing
        again = herd.focus_rounds(self.root, "t1")
        self.assertEqual((len(again), again[0]), (2, rounds[0]))
        self.assertNotEqual(again[1]["brief"], rounds[0]["brief"])
        for k in range(32):  # past the cap: the oldest open notes are cut and the brief says how many
            herd.add_note(self.root, "t1", "open", f"limit {k}")
        self.assertIn("(10 older open notes were cut)", herd.review_brief(self.root, "t1"))
        p = self.cli("review-brief")  # the CLI prints the same brief and records the round
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(herd.focus_rounds(self.root, "t1")), 4)
        self.assertIn(f"Brief: {herd.focus_rounds(self.root, 't1')[-1]['brief']}", p.stdout)

    def test_the_agent_cannot_write_focus_json(self):
        self.ready()
        d = herd._dir(self.root, "t1")
        self.assertIn("focus.json", herd.GUARD_STATE)
        self.assertTrue(herd._protected(self.root, self.root, str(d / "focus.json"), []))
        out = herd.guard(self.root, {"tool_name": "Write", "tool_input": {"file_path": str(d / "focus.json")}, "cwd": str(self.root)})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


class FocusAttackTests(FocusBase):
    """The five standard attacks on the focus code, one command each (`herd note --tried --attack`)."""

    def test_bad_input(self):
        for bad in (None, 5, "", [], b"x", "FOCUS", "FOCUS :", "BRIEF", "EXTRA:", "FOCUS a: holds:", "\x00FOCUS a: holds: x"):
            got = herd.parse_focus(bad)
            self.assertEqual(set(got), {"brief", "answers", "bad", "extra"})
        for t in ({"criteria": None}, {"criteria": [3, None, "x"], "inputs": "x", "known_limits": 4, "test_budget": None},
                  {"criteria": [{"source": "human", "coverage": 4}]}, {}):
            herd.focus_items(t, [{"kind": "open"}, {"kind": "tried", "attack": "refusal"}, {"kind": "decision", "text": None}])
        b = self.focused()
        d = herd._dir(self.root, "t1")
        for junk in ("{not json", "{}", "[1, null, \"x\"]", ""):  # a focus.json that is not a list of rounds
            (d / "focus.json").write_text(junk)
            self.assertEqual(herd.focus_rounds(self.root, "t1"), [])
            self.review(text="\n".join(self.lines(b)), builder="haiku", reviewer="sonnet")
            self.assertEqual(self.last()["verdict"], "none")  # no usable round: never a traceback, never a PASS
        self.review(text=None, last_message="BRIEF x", builder="haiku", reviewer="sonnet")
        self.assertEqual(self.last()["verdict"], "none")

    def test_collision(self):
        t = task(criteria=[{"id": "C1", "source": "human", "text": "a", "coverage": "one", "check": ""},
                           {"id": "C1", "source": "human", "text": "b", "coverage": "two", "check": ""}])
        self.assertEqual([i["quote"] for i in herd.focus_items(t, []) if i["cat"] == "A"], ["one"])
        b = self.focused()
        same = "python3 -c \"print(1)\""  # two items answered by one command, two extras with one text
        n = self.answer(b, extra=("EXTRA: a.py:1 x", "EXTRA: a.py:1 x"), C_recount=f"FOCUS C:recount: holds: {same}",
                        C_refusal=f"FOCUS C:refusal: holds: {same}")
        self.assertEqual(n["verdict"], "none")
        n = self.answer(b, extra=("EXTRA: a.py:1 x", "EXTRA: a.py:1 x"))
        self.assertEqual([x["id"] for x in n["focus"]["extra"]], ["x0.1", "x0.2"])  # same text, two ids
        self.assertEqual(herd.parse_focus("FOCUS A: holds: a\nFOCUS A: breaks: b")["bad"], ["A"])

    def test_one_bad_part(self):
        b = self.focused()
        n = self.answer(b, C_recount="FOCUS C:recount: holds: ", C_collision="FOCUS C:collision: holds: python3 -c \"import sys; sys.exit(1)\"")
        self.assertEqual(n["focus"]["unanswered"], ["C:recount"])  # one bad line names only itself
        self.assertEqual(n["focus"]["answered"], len(self.items) - 1)
        n = self.answer(b, C_collision="FOCUS C:collision: holds: python3 -c \"import sys; sys.exit(1)\"")
        self.assertEqual(n["focus"]["unconfirmed"], ["C:collision"])  # one failing holds leaves the others confirmed
        self.assertEqual(len(n["focus"]["holds"]), len(self.items))
        d = herd._dir(self.root, "t1")
        rounds = herd.focus_rounds(self.root, "t1")
        (d / "focus.json").write_text(json.dumps([7, "x"] + rounds))  # a junk entry beside a good round
        self.assertEqual(herd.focus_rounds(self.root, "t1"), rounds)

    def test_recount(self):
        b = self.focused()
        n = self.answer(b, C_recount=f"FOCUS C:recount: breaks: {BREAK_CMD}", C_refusal="FOCUS C:refusal: holds: python3 -c \"import sys; sys.exit(2)\"",
                        extra=(f"EXTRA: a.py:1 x :: {BREAK_CMD} ",))
        full = herd.focus_rounds(self.root, "t1")[-1]["reviews"][-1]["answers"]
        confirmed = [i for i, a in full.items() if a["exit"] == (0 if a["verdict"] == "holds" else 3)]  # separate rule
        f = n["focus"]
        self.assertEqual(sorted(confirmed), sorted(set(self.ids() + ["x0.1"]) - {"C:refusal"}))
        self.assertEqual(f["unconfirmed"], ["C:refusal"])
        self.assertEqual(f["answered"], len(self.items))
        self.assertEqual(sorted(f["holds"] + [x["id"] for x in f["breaks"]]), sorted(self.ids()))
        self.assertEqual(n["verdict"], "FAIL")

    def test_refusal(self):
        """Every report the hook refuses (verdict none) is one a simple model also refuses; every other passes."""
        import random
        rng = random.Random(7)
        b = self.focused()
        for _ in range(6):
            kinds, lines = [], [f"BRIEF {b}"]
            for i in self.items:
                kind = rng.choice(["holds", "holds", "missing", "dup", "badhold", "break", "badbreak", "reader"])
                kinds.append(kind)
                cmd = PASS_CMD.format(i["id"])
                line = {"holds": f"holds: {cmd}", "dup": f"holds: {cmd}", "badhold": "holds: python3 -c \"import sys; sys.exit(4)\"",
                        "break": f"breaks: {BREAK_CMD} # {i['id']}", "badbreak": f"breaks: {cmd}", "reader": "holds: cat app.py"}.get(kind)
                if line:
                    lines += [f"FOCUS {i['id']}: {line}"] * (2 if kind == "dup" else 1)
            self.review(text="\n".join(lines), builder="haiku", reviewer="sonnet")
            structure = "missing" in kinds or "dup" in kinds  # F4.5, in order: structure, a confirmed break, unconfirmed
            want = ("none" if structure else "FAIL" if "break" in kinds else
                    "none" if {"badhold", "badbreak", "reader"} & set(kinds) else "PASS")
            self.assertEqual(self.last()["verdict"], want, (kinds, lines))


class ParseFocusTests(unittest.TestCase):
    def test_parse_focus(self):
        text = "\n".join(["Report", "**BRIEF abc123**", "- FOCUS A:C1: holds: `python3 -c 1`", "  FOCUS B:limit-1: breaks: x -y",
                          "FOCUS C:recount: breaks:", "FOCUS A:C1: holds: other", "EXTRA: a.py:3 bad :: ls -l", "EXTRA: b.py:4 bad",
                          "FOCUS D:1 holds: no colon", "prose FOCUS Z:1: holds: not at the start"])
        got = herd.parse_focus(text)
        self.assertEqual(got["brief"], "abc123")
        self.assertEqual(got["answers"]["B:limit-1"], {"verdict": "breaks", "command": "x -y"})
        self.assertEqual(got["answers"]["A:C1"]["command"], "python3 -c 1")  # the first; the repeat is a bad line
        self.assertEqual(sorted(got["bad"]), ["A:C1", "C:recount", "D:1"])
        self.assertEqual(got["extra"], [{"text": "a.py:3 bad", "command": "ls -l"}, {"text": "b.py:4 bad", "command": None}])
        self.assertIsNone(herd.parse_focus("no brief here")["brief"])
        self.assertEqual(herd.parse_focus(None), {"brief": None, "answers": {}, "bad": [], "extra": []})


if __name__ == "__main__":
    unittest.main()
