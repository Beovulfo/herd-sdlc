"""docs/designs/herd-focused-review.md: the focus list, the hook's answers and the delta (Herd 0.13.0)."""
import glob
import json
import os
import tomllib
import unittest
from pathlib import Path

from scripts import herd

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


if __name__ == "__main__":
    unittest.main()
