"""Hostile and generated inputs. Counts are recomputed here from the raw files, never with report.py's code."""
import contextlib
import io
import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import judge
import report
import run_eval

HERE = Path(__file__).resolve().parent
TASKS = ("supermarket-route", "bus-transfer")


def call(main, argv, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(argv, **kw)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.cases = judge.load_cases()

    def cases_folder(self, **change):
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        for path in judge.CASES.glob("*.json"):
            data = json.loads(path.read_text())
            if data["task"] == "bus-transfer":
                data.update(change)
            (folder / path.name).write_text(json.dumps(data))
        return folder

    def put_run(self, results, task, arm, n, before, after, status="ok"):
        run = results / task / arm / f"run-{n}"
        for when, label in (("before", before), ("after", after)):
            (run / when).mkdir(parents=True, exist_ok=True)
            (run / when / "label.json").write_text(json.dumps({"label": label}))
        (run / "run.json").write_text(json.dumps({"status": status}))
        return run

    def tree(self, rng, sizes=None, name="results"):
        results = Path(tempfile.mkdtemp(prefix=name, dir=self.tmp))
        for task in TASKS:
            ids = [x["id"] for x in self.cases[task]["labels"]]
            for arm in report.ARMS:
                for n in range(1, (sizes or rng.randint(1, 16)) + 1):
                    status = rng.choice(["ok"] * 6 + ["no-start", "leak", "no-verify"])
                    before, after = rng.choice(ids + [None] if status == "ok" else ids), rng.choice(ids)
                    self.put_run(results, task, arm, n, before, after, status)
        return results


class TestAttacks(Base):
    def assert_clear(self, code, out, what):
        self.assertNotIn(code, (0, None), what)
        self.assertNotIn("Traceback", out, what)
        self.assertTrue(out.strip(), what)

    def test_bad_input_arguments_and_case_files(self):
        broken = {"empty": "", "not json": "{", "a list": "[]", "no labels": '{"task": "x", "prompt": "p", "question": "q"}',
                  "labels not objects": '{"task": "x", "prompt": "p", "question": "q", "labels": [1, 2]}'}
        for what, text in broken.items():
            folder = Path(tempfile.mkdtemp(dir=self.tmp))
            (folder / "x.json").write_text(text)
            for main, argv in ((run_eval.main, ["--dry-run"]), (report.main, [str(self.tmp)]),
                               (judge.main, ["--calibrate"])):
                self.assert_clear(*call(main, argv + ["--cases", str(folder)]), what)
        for change in ({"prompt": "no/such.md"}, {"right": ["nope"]}, {"right": []}, {"task": "../up"}, {"labels": []}):
            folder = self.cases_folder(**change)
            self.assert_clear(*call(run_eval.main, ["--dry-run", "--cases", str(folder)]), change)
        empty = self.tmp / "empty.md"
        empty.write_text("\n")
        binary = self.tmp / "binary.md"
        binary.write_bytes(b"\xff\xfe\x00")
        for path in (empty, binary, self.tmp):
            folder = self.cases_folder(prompt=str(path))
            self.assert_clear(*call(run_eval.main, ["--dry-run", "--cases", str(folder)]), path)
        for argv in (["--case", "nope", "--dry-run"], ["--runs", "0"], ["--runs", "x"], ["--budget", "-1"],
                     ["--cases", str(self.tmp / "none"), "--dry-run"], ["--root", str(Path.home() / "x")],
                     ["--herd-tag", "no-such-tag", "--root", str(self.tmp / "r")]):
            self.assert_clear(*call(run_eval.main, argv, scan_dirs=[]), argv)
        self.assert_clear(*call(run_eval.main, ["--root", str(self.tmp)], scan_dirs=[]), "root exists")

    def test_bad_input_results_and_labelled_folders(self):
        for argv in ([str(self.tmp / "none")], [str(self.tmp)]):
            self.assert_clear(*call(report.main, argv), argv)
            self.assert_clear(*call(judge.main, argv), argv)
        self.assert_clear(*call(judge.main, []), "neither")
        folder = self.cases_folder()
        snap = folder / "bus-transfer" / "labelled" / "s"
        snap.mkdir(parents=True)
        for text in (None, "{", '{"label": "nope"}', '{"label": "refused"}'):  # the last: no task.toml
            if text is not None:
                (snap / "label.json").write_text(text)
            self.assert_clear(*call(judge.main, ["--calibrate", "--cases", str(folder)]), text)

    def test_collision_cases(self):
        folder = self.cases_folder()
        shutil.copy(folder / "bus-transfer.json", folder / "again.json")
        self.assert_clear(*call(run_eval.main, ["--dry-run", "--cases", str(folder)]), "same task twice")
        label = {"id": "refused", "means": "a different meaning"}
        for change in ({"labels": [*self.cases["bus-transfer"]["labels"], label]},
                       {"right": ["refused"], "wrong": ["refused"]}):
            folder = self.cases_folder(**change)
            self.assert_clear(*call(run_eval.main, ["--dry-run", "--cases", str(folder)]), change)

    def test_collision_identical_runs_are_each_counted(self):
        results = self.tmp / "results"
        for arm in ("control", "after-red"):
            for n in (1, 2, 10):  # same labels, run-1 and run-10 share a prefix
                self.put_run(results, "bus-transfer", arm, n, "unstated", "refused")
        data = report.collect(results, self.cases)
        self.assertEqual([len(data["bus-transfer"][a]["runs"]) for a in ("control", "after-red")], [3, 3])

    def test_bad_part_one_broken_record_refuses_the_report(self):
        for what in ("run.json cut", "no status", "label missing", "unknown label", "unknown arm", "unknown case"):
            results = self.tree(random.Random(1), sizes=3)
            run = self.put_run(results, "bus-transfer", "control", 1, "refused", "refused")
            if what == "run.json cut":
                (run / "run.json").write_text("{")
            elif what == "no status":
                (run / "run.json").write_text("{}")
            elif what == "label missing":
                (run / "after" / "label.json").unlink()
            elif what == "unknown label":
                (run / "after" / "label.json").write_text('{"label": "cell"}')
            elif what == "unknown arm":
                (results / "bus-transfer" / "other").mkdir()
            else:
                (results / "other-case").mkdir()
            code, out = call(report.main, [str(results)])
            self.assert_clear(code, out, what)
            self.assertNotIn("## Bar", out, what)

    def test_recount_report_numbers_on_generated_results(self):
        for seed in range(25):
            results = self.tree(random.Random(seed))
            code, out = call(report.main, [str(results)])
            self.assertEqual(code, 0, out)
            for task in TASKS:
                block = out.split(f"## {task} ")[1].split("\n## ")[0]
                for arm in report.ARMS:
                    section = block.split(f"### {arm}: ")[1].split("###")[0]
                    pairs, excluded, flipped = {}, {}, 0
                    for run in (results / task / arm).iterdir():
                        status = json.loads((run / "run.json").read_text())["status"]
                        before, after = (json.loads((run / w / "label.json").read_text())["label"]
                                         for w in ("before", "after"))
                        if status == "ok" and before is None:
                            status = "judge-error"
                        if status != "ok":
                            excluded[status] = excluded.get(status, 0) + 1
                            continue
                        pairs[f"{before}→{after}"] = pairs.get(f"{before}→{after}", 0) + 1
                        flipped += before in self.cases[task]["right"] and after in self.cases[task]["wrong"]
                    shown = {m[0]: int(m[1]) for m in re.findall(r"^(\w+→\w+): (\d+)$", section, re.M)}
                    self.assertEqual(shown, pairs, (seed, task, arm))
                    right = sum(n for k, n in pairs.items() if k.split("→")[1] in self.cases[task]["right"])
                    self.assertTrue(section.startswith(f"right after {right}/{sum(pairs.values())}\n"), section)
                    self.assertIn(f"right-to-wrong flips: {flipped}", section)
                    found = re.search(r"^excluded: (.*)$", section, re.M)
                    shown = dict(x.rsplit(" ", 1) for x in found[1].split(", ")) if found else {}
                    self.assertEqual({k: int(v) for k, v in shown.items()}, excluded)

    def bar_tree(self, right, n=12, flips=0):
        """right[task] = (right runs in control, right runs in both question arms)."""
        results = Path(tempfile.mkdtemp(dir=self.tmp))
        for task, counts in right.items():
            good, bad = self.cases[task]["right"][0], self.cases[task]["wrong"][0]
            for arm in report.ARMS:
                k = counts[0] if arm == "control" else counts[1]
                for i in range(n):
                    after = good if i < k else bad
                    flip = arm != "control" and task == "bus-transfer" and k <= i < k + flips
                    self.put_run(results, task, arm, i + 1, good if flip else "unstated", after)
        return report.collect(results, self.cases)

    def test_refusal_the_bar_matches_a_plain_check(self):
        rng = random.Random(7)
        seen = set()
        for _ in range(150):
            a, b = [(rng.randint(0, 12), rng.randint(0, 12)) for _ in TASKS]
            flips = rng.randint(0, min(3, 12 - b[1]))
            data = self.bar_tree({TASKS[0]: a, TASKS[1]: b}, flips=flips)
            gains = [a[1] - a[0], b[1] - b[0]]
            want = "met" if max(gains) >= 6 and min(gains) >= 0 and flips <= 1 else "not met"
            self.assertEqual(report.bar(data, self.cases, "after-red")[0], want, (a, b, flips))
            seen.add(want)
        self.assertEqual(seen, {"met", "not met"})

    def test_refusal_the_bar_is_not_evaluated_only_when_short(self):
        both = {t: (0, 6) for t in TASKS}
        for n in (6, 11):
            self.assertEqual(report.bar(self.bar_tree(both, n=n), self.cases, "after-red")[0], "not evaluated")
        for n in (12, 13, 24):
            self.assertNotEqual(report.bar(self.bar_tree(both, n=n), self.cases, "after-red")[0], "not evaluated")
        one = self.bar_tree({"bus-transfer": (0, 12)})
        cases = {"bus-transfer": self.cases["bus-transfer"]}
        self.assertEqual(report.bar(one, cases, "after-red")[0], "not evaluated")

    def test_reading_prompts_reach_the_session_word_for_word(self):
        rng = random.Random(3)
        alphabet = "ab $`'\"\\\n\t;|&>“é→-"
        prompts = ["build it " + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 80))) + "z"
                   for _ in range(40)]
        prompts += [(HERE.parent / task / "prompt.md").read_text(encoding="utf-8") for task in TASKS]
        for i, text in enumerate(prompts):
            path = self.tmp / f"p{i}.md"
            path.write_text(text + "\n", encoding="utf-8")
            got = run_eval.case_prompt({"prompt": str(path)})
            self.assertEqual(got, text.rstrip("\n"))
            command = run_eval.session_command(run_eval.parse([]), got, self.tmp)
            self.assertEqual(command[2], "/herd:run " + got)

    def test_reading_a_third_case_is_data_only(self):
        folder = self.cases_folder()
        prompt = self.tmp / "held out.md"
        prompt.write_text("build a \"held out\" thing\nwith two lines\n")
        third = {"task": "held-out", "prompt": str(prompt), "question": "q?", "right": ["yes"], "wrong": ["no"],
                 "labels": [{"id": "yes", "means": "y"}, {"id": "no", "means": "n"}]}
        (folder / "held-out.json").write_text(json.dumps(third))
        code, out = call(run_eval.main, ["--dry-run", "--runs", "1", "--cases", str(folder), "--case", "held-out"])
        self.assertEqual(code, 0, out)
        self.assertIn("# held-out run 1", out)
        self.assertNotIn("# bus-transfer", out)
        results = self.tmp / "results"
        self.put_run(results, "held-out", "control", 1, "no", "yes")
        code, out = call(report.main, [str(results), "--cases", str(folder)])
        self.assertEqual(code, 0, out)
        self.assertIn("no→yes: 1", out)


if __name__ == "__main__":
    unittest.main()
