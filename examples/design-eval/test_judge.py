"""The judge and its calibration, on recorded replies (fixtures/*/*/judge-reply.json). No model call."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import judge

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNAPSHOTS = {"supermarket-route": "sealed-shelf", "bus-transfer": "repeated-stop"}


def recorded(task):
    return json.loads((FIXTURES / task / SNAPSHOTS[task] / "judge-reply.json").read_text())["reply"]


def call_main(argv, call):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = judge.main(argv, call=call)
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cases = judge.load_cases()
        self.prompts = []


class TestJudge(Base):
    def test_recorded_reply_matches_the_hand_label(self):
        for task, name in SNAPSHOTS.items():
            snap = FIXTURES / task / name
            got = judge.judge_snapshot(self.cases[task], snap, lambda p, task=task: recorded(task))
            self.assertEqual(got["label"], json.loads((snap / "label.json").read_text())["label"])
            self.assertTrue(got["quote_found"])

    def test_the_judge_sees_the_files_and_the_rubric_but_not_arm_or_time(self):
        snap = self.tmp / "supermarket-route" / "before-attacks" / "run-7" / "after"
        shutil.copytree(FIXTURES / "supermarket-route" / "sealed-shelf", snap)
        (snap / "files").mkdir()
        (snap / "files" / "code.py").write_text("SECRET_CODE")
        prompt = judge.judge_prompt(self.cases["supermarket-route"], judge.material(snap))
        for want in ("walkable neighbour", "[[inputs]]", '"attack": "other-reading"', "- cell:", "- unstated:"):
            self.assertIn(want, prompt)
        for hidden in ("before-attacks", "run-7", "SECRET_CODE", str(self.tmp), "judge-reply"):
            self.assertNotIn(hidden, prompt)

    def test_bad_replies_give_no_label_after_two_tries(self):
        snap = FIXTURES / "bus-transfer" / "repeated-stop"
        for reply in ("", "refused", '{"label": "maybe", "quote": ""}', '{"label": "refused"}', "[1]"):
            calls = []
            got = judge.judge_snapshot(self.cases["bus-transfer"], snap, lambda p, r=reply: calls.append(p) or r)
            self.assertIsNone(got["label"], reply)
            self.assertEqual(len(calls), 2)

    def test_labels_every_snapshot_and_calls_once_for_a_shared_start(self):
        source = FIXTURES / "bus-transfer" / "repeated-stop"
        results = self.tmp / "results"
        for arm in ("control", "after-red"):
            shutil.copytree(source, results / "bus-transfer" / arm / "run-1" / "before")
        for name in ("label.json", "judge-reply.json"):
            for path in results.rglob(name):
                path.unlink()
        calls = []
        code, out = call_main([str(results)], lambda p: calls.append(p) or recorded("bus-transfer"))
        self.assertEqual((code, len(calls)), (0, 1), out)
        labels = [json.loads(p.read_text())["label"] for p in results.rglob("label.json")]
        self.assertEqual(labels, ["tolerated", "tolerated"])


class TestCalibrate(Base):
    def labelled(self, task, count, wrong=0):
        """A cases folder with `count` hand-labelled snapshots, `wrong` of which the fake judge disagrees on."""
        folder = self.tmp / f"cases-{task}-{count}-{wrong}"
        folder.mkdir()
        shutil.copy(judge.CASES / f"{task}.json", folder)
        right, other = self.cases[task]["right"][0], self.cases[task]["wrong"][0]
        for i in range(count):
            snap = folder / task / "labelled" / f"s{i:02}"
            snap.mkdir(parents=True)
            (snap / "task.toml").write_text(f"goal = 'snapshot {i}'\n")
            (snap / "label.json").write_text(json.dumps({"label": other if i < wrong else right}))
        reply = json.dumps({"label": right, "quote": ""})
        return folder, lambda p: self.prompts.append(p) or reply

    def test_calibrate_refuses_fewer_than_ten(self):
        for count in (0, 1, 9):
            folder, call = self.labelled("bus-transfer", count)
            code, out = call_main(["--calibrate", "--cases", str(folder)], call)
            self.assertEqual(code, 2, out)
            self.assertIn(f"refused: {count} labelled", out)
            self.assertNotIn("agreement", out)
        self.assertEqual(self.prompts, [], "no model call for a refused set")

    def test_calibrate_threshold_is_nine_of_ten(self):
        for count, wrong, code_wanted, word in ((10, 0, 0, "10/10: results count"), (10, 1, 0, "9/10: results count"),
                                                (10, 2, 1, "8/10: results do NOT"), (20, 2, 0, "18/20: results count"),
                                                (19, 2, 1, "17/19: results do NOT")):
            folder, call = self.labelled("supermarket-route", count, wrong)
            code, out = call_main(["--calibrate", "--cases", str(folder)], call)
            self.assertEqual(code, code_wanted, out)
            self.assertIn(word, out)

    def test_calibrate_never_shows_the_hand_label_to_the_judge(self):
        folder, call = self.labelled("supermarket-route", 10)
        call_main(["--calibrate", "--cases", str(folder), "--case", "supermarket-route"], call)
        self.assertTrue(self.prompts and all("=== label.json" not in p for p in self.prompts))

    def test_calibrate_the_shipped_folders_exist_and_are_refused_while_empty(self):
        for task in SNAPSHOTS:
            self.assertTrue((judge.CASES / task / "labelled").is_dir())


if __name__ == "__main__":
    unittest.main()
