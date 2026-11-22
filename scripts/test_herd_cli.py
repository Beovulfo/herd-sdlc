import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import herd

TASK = '''goal = "Add a greeting"

[[criteria]]
id = "C1"
text = "Given a name, when greet runs, then it prints hello"
source = "human"
check = "test -f greet.txt"

[[criteria]]
id = "C2"
text = "The greeting reads well"
source = "agent-proposed"
check = ""
'''


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, text=TASK):
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)


class TestTask(Base):
    def test_init_creates_task_and_active(self):
        herd.init_task(self.root, "t1", "Add a greeting")
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "t1")
        t = herd.load_task(self.root, "t1")
        self.assertEqual(t["goal"], "Add a greeting")
        self.assertEqual(t.get("criteria", []), [])

    def test_init_rejects_bad_slug_and_existing(self):
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "../x", "g")
        herd.init_task(self.root, "t1", "g")
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "t1", "g")

    def test_validate(self):
        self.task()
        self.assertEqual(herd.validate_task(herd.load_task(self.root, "t1")), [])
        bad = {"goal": "", "criteria": [{"id": "C1", "text": "a", "source": "x", "check": "true"},
                                        {"id": "C1", "text": "b", "source": "human"}]}
        errs = " | ".join(herd.validate_task(bad))
        for needle in ("goal", "source", "duplicate", "check"):
            self.assertIn(needle, errs)
        self.assertIn("no criteria", " ".join(herd.validate_task({"goal": "g", "criteria": []})))


class TestVerify(Base):
    def test_verify_records_evidence(self):
        self.task()
        ev = herd.verify(self.root, "t1")
        by = {r["id"]: r for r in ev["results"]}
        self.assertEqual(by["C1"]["status"], "failing")
        self.assertEqual(by["C2"]["status"], "unchecked")
        self.assertEqual(ev["summary"], {"passing": 0, "failing": 1, "unchecked": 1})
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"], {"passing": 1, "failing": 0, "unchecked": 1})
        r = ev["results"][0]
        self.assertEqual((r["exit_code"], r["check"]), (0, "test -f greet.txt"))
        saved = json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())
        self.assertEqual(saved["summary"], ev["summary"])
        self.assertTrue(saved["head"] and saved["at"] and saved["fingerprint"])

    def test_timeout_is_failing(self):
        self.task(TASK.replace('check = "test -f greet.txt"', 'check = "sleep 5"\ntimeout_s = 1'))
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertEqual(r["status"], "failing")
        self.assertIn("timeout", r["output_tail"])

    def test_output_tail_is_cut(self):
        self.task(TASK.replace('test -f greet.txt', "python3 -c 'print(5000*chr(120))'"))
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertLessEqual(len(r["output_tail"]), herd.TAIL_CHARS)

    def test_dirty_flag_in_evidence_and_report(self):
        self.task()
        ev = herd.verify(self.root, "t1")
        self.assertFalse(ev["dirty"])  # only .herd/ exists, and it is ignored
        self.assertNotIn("uncommitted", herd.report(ev))
        (self.root / "greet.txt").write_text("hello")  # new untracked file counts as uncommitted work
        ev = herd.verify(self.root, "t1")
        self.assertTrue(ev["dirty"])
        self.assertIn("plus uncommitted changes", herd.report(ev))

    def test_report_text(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("C1", text)
        self.assertIn("passing", text)
        self.assertIn("unchecked", text)
        self.assertIn("never counted as met", text)


class TestHygiene(Base):
    def warn(self, check):
        return herd.check_warnings({"criteria": [{"id": "C1", "check": check}]})

    def test_hygiene_flags_vacuous_checks(self):
        for check in ("true", ":", "exit 0", "echo ok", "test -f greet.txt", "test -e greet.txt"):
            self.assertEqual(len(self.warn(check)), 1, check)
            self.assertIn("C1", self.warn(check)[0])

    def test_hygiene_accepts_real_checks_and_empty(self):
        for check in ("python3 -m unittest", "pytest -q", "grep -q hello out.txt && ./run", ""):
            self.assertEqual(self.warn(check), [], check)

    def test_hygiene_cli_prints_warning_and_exits_zero(self):
        self.task(TASK.replace("test -f greet.txt", "true"))
        p = subprocess.run(["python3", str(Path(herd.__file__)), "check"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("ok", p.stdout)
        self.assertIn("warning: C1", p.stdout)


class TestQuick(Base):
    def test_quick_init_writes_one_criterion(self):
        herd.init_task(self.root, "q1", "Fix a typo in README", quick_check="python3 -m unittest")
        t = herd.load_task(self.root, "q1")
        self.assertEqual(t["route"], "quick")
        self.assertEqual(len(t["criteria"]), 1)
        c = t["criteria"][0]
        self.assertEqual((c["id"], c["source"], c["check"], c["text"]),
                         ("C1", "agent-proposed", "python3 -m unittest", "Fix a typo in README"))
        self.assertEqual(herd.validate_task(t), [])
        self.assertEqual(herd.active_slug(self.root), "q1")

    def test_quick_survives_quotes_in_goal_and_check(self):
        herd.init_task(self.root, "q1", 'Say "hi" \\ there', quick_check="grep -q 'a\"b' f.txt")
        c = herd.load_task(self.root, "q1")["criteria"][0]
        self.assertEqual(c["text"], 'Say "hi" \\ there')

    def test_quick_refuses_empty_check(self):
        with self.assertRaises(ValueError) as cm:
            herd.init_task(self.root, "q1", "goal", quick_check="  ")
        self.assertIn("check", str(cm.exception))
        self.assertFalse((self.root / ".herd/tasks/q1").exists())

    def test_quick_refuses_high_risk_floor(self):
        with self.assertRaises(ValueError) as cm:
            herd.init_task(self.root, "q1", "Rotate tokens in auth/session.py", quick_check="true")
        self.assertIn("high", str(cm.exception))
        self.assertFalse((self.root / ".herd/tasks/q1").exists())
        self.assertFalse((self.root / ".herd/active").exists())

    def test_quick_uses_project_herd_toml(self):
        (self.root / "herd.toml").write_text('[floor]\nhigh = ["docs/**"]\n')
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "q1", "Edit docs/guide.md", quick_check="true")
        herd.init_task(self.root, "q2", "Edit auth/x.py", quick_check="true")  # custom rules replace defaults

    def test_validate_route(self):
        ok = {"goal": "g", "criteria": [{"id": "C1", "text": "t", "source": "human", "check": "true"}]}
        self.assertEqual(herd.validate_task(ok), [])
        self.assertIn("route", " ".join(herd.validate_task({**ok, "route": "fast"})))
        self.assertEqual(herd.validate_task({**ok, "route": "quick"}), [])
        two = {**ok, "route": "quick", "criteria": ok["criteria"] + [dict(ok["criteria"][0], id="C2")]}
        self.assertIn("exactly one", " ".join(herd.validate_task(two)))
        empty = {**ok, "route": "quick", "criteria": [dict(ok["criteria"][0], check="")]}
        self.assertIn("quick", " ".join(herd.validate_task(empty)))

    def test_report_shows_route_and_flow_ends_in_evidence(self):
        herd.init_task(self.root, "q1", "Add greet file", quick_check="test -f greet.txt")
        ev = herd.verify(self.root, "q1")
        self.assertEqual(ev["summary"]["failing"], 1)
        (self.root / "greet.txt").write_text("hi")
        text = herd.report(herd.verify(self.root, "q1"))
        self.assertIn("Route: quick", text)
        self.assertEqual(herd.problems(self.root, "q1"), [])

    def test_cli_quick(self):
        p = subprocess.run(["python3", str(Path(herd.__file__)), "init", "q1", "Fix typo", "--quick", "true"],
                           cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run(["python3", str(Path(herd.__file__)), "init", "q2", "Fix auth/x.py", "--quick", "true"],
                           cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("high", p.stderr)


class TestBudgetAndRed(Base):
    def test_budget_note_in_report_and_validation(self):
        self.task('test_budget = "unit for parsing; not testing the CLI wrapper"\n' + TASK)
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Test budget: unit for parsing; not testing the CLI wrapper", text)
        t = herd.load_task(self.root, "t1")
        self.assertEqual(herd.validate_task(dict(t, test_budget=3))[0].split(":")[0], "test_budget")

    def test_no_budget_line_when_absent(self):
        self.task()
        self.assertNotIn("Test budget", herd.report(herd.verify(self.root, "t1")))

    def test_red_recorded_on_first_verify_only(self):
        self.task()
        ev = herd.verify(self.root, "t1")  # C1 fails, C2 unchecked
        self.assertEqual(ev["red"], {"failed": 1, "total": 1})
        self.assertTrue((self.root / ".herd/tasks/t1/red.json").exists())
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"]["passing"], 1)
        self.assertEqual(ev["red"], {"failed": 1, "total": 1})  # still the first run
        self.assertIn("First verify: 1 of 1 checks failed before the work", herd.report(ev))

    def test_green_from_the_start_is_visible(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["red"], {"failed": 0, "total": 1})
        self.assertIn("First verify: 0 of 1 checks failed before the work", herd.report(ev))

    def test_red_does_not_make_evidence_stale(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestVerbatim(Base):
    REQUEST = "Build a thing.\n\nSuccess: the optimized route saves MORE than 20 percent of the time   vs a random walk."

    def human(self, text, source="human"):
        return {"goal": "g", "criteria": [{"id": "C1", "text": text, "source": source, "check": "python3 -m unittest"}]}

    def test_init_records_request(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        self.assertEqual((self.root / ".herd/tasks/t1/request.md").read_text(), self.REQUEST)
        herd.init_task(self.root, "t2", "g")
        self.assertFalse((self.root / ".herd/tasks/t2/request.md").exists())

    def test_quote_is_accepted_ignoring_case_and_spacing(self):
        task = self.human("the optimized route saves more than 20 percent of the time vs a random walk")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), [])
        self.assertEqual(herd.check_warnings(task, self.REQUEST), [])

    def test_reworded_or_narrowed_human_criterion_is_flagged(self):
        task = self.human("Given the sample store, when compared over 10 runs, then optimized is more than 20% lower")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), ["C1"])
        warn = " ".join(herd.check_warnings(task, self.REQUEST))
        self.assertIn("C1", warn)
        self.assertIn("verbatim", warn)

    def test_agent_proposed_criteria_are_not_checked(self):
        task = self.human("Given anything, then something", source="agent-proposed")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), [])
        self.assertEqual(herd.check_warnings(task, self.REQUEST), [])

    def test_no_request_recorded_warns_for_human_criteria_only(self):
        warn = herd.check_warnings(self.human("anything"), None)
        self.assertTrue(any("no request" in w for w in warn))
        self.assertEqual(herd.check_warnings(self.human("anything", "agent-proposed"), None), [])
        self.assertIsNone(herd.human_unquoted(self.human("anything"), None))

    def test_evidence_and_report_show_unquoted_human_criteria(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "Given a sample, then it is 20% lower"\n'
            'source = "human"\ncheck = "true"\n')
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["human_not_verbatim"], ["C1"])
        self.assertIn("Human criteria not quoted verbatim from the request: C1", herd.report(ev))

    def test_report_is_quiet_when_quoted_or_unknown(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "saves MORE than 20 percent of the time"\n'
            'source = "human"\ncheck = "true"\n')
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["human_not_verbatim"], [])
        self.assertNotIn("verbatim", herd.report(ev))
        herd.init_task(self.root, "t2", "g")  # no request recorded
        (self.root / ".herd/tasks/t2/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "x"\nsource = "human"\ncheck = "true"\n')
        self.assertIsNone(herd.verify(self.root, "t2")["human_not_verbatim"])

    def test_cli_request_flag_and_check(self):
        run = lambda *a: subprocess.run(["python3", str(Path(herd.__file__)), *a], cwd=self.root,
                                        capture_output=True, text=True)
        self.assertEqual(run("init", "t1", "g", "--request", self.REQUEST).returncode, 0)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "reworded"\nsource = "human"\ncheck = "python3 -V"\n')
        out = run("check").stdout
        self.assertIn("warning: C1", out)
        self.assertIn("verbatim", out)


class TestTiming(Base):
    def at(self, hhmmss):
        return mock.patch.object(herd, "now", return_value=f"2026-11-22T{hhmmss}Z")

    def test_duration_format(self):
        for secs, text in ((0, "0s"), (45, "45s"), (71, "1m 11s"), (256, "4m 16s"), (3600, "1h 00m 00s"),
                           (3731, "1h 02m 11s")):
            self.assertEqual(herd.fmt_duration(secs), text)

    def test_init_records_start_time(self):
        with self.at("10:00:00"):
            herd.init_task(self.root, "t1", "g")
        self.assertEqual((self.root / ".herd/tasks/t1/started").read_text().strip(), "2026-11-22T10:00:00Z")
        with self.at("10:00:05"):
            herd.init_task(self.root, "q1", "g", quick_check="true")
        self.assertTrue((self.root / ".herd/tasks/q1/started").exists())

    def test_evidence_carries_elapsed_and_first_verify_time(self):
        with self.at("10:00:00"):
            self.task()
        with self.at("10:01:11"):
            ev = herd.verify(self.root, "t1")  # first verify
        self.assertEqual(ev["timing"], {"started_at": "2026-11-22T10:00:00Z", "elapsed_s": 71, "first_verify_s": 71})
        (self.root / "greet.txt").write_text("hello")
        with self.at("10:04:16"):
            ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["timing"]["elapsed_s"], 256)
        self.assertEqual(ev["timing"]["first_verify_s"], 71)  # fixed by the first run
        text = herd.report(ev)
        self.assertIn("Elapsed: 4m 16s from herd init to this verify; first verify at 1m 11s", text)
        self.assertIn("wall clock", text)

    def test_task_without_start_file_has_no_timing(self):
        self.task()
        (self.root / ".herd/tasks/t1/started").unlink()
        ev = herd.verify(self.root, "t1")
        self.assertIsNone(ev["timing"])
        self.assertNotIn("Elapsed", herd.report(ev))

    def test_all_unchecked_has_elapsed_but_no_first_verify(self):
        with self.at("10:00:00"):
            herd.init_task(self.root, "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "human"\ncheck = ""\n')
        with self.at("10:02:00"):
            ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["timing"], {"started_at": "2026-11-22T10:00:00Z", "elapsed_s": 120})
        self.assertNotIn("first verify at", herd.report(ev))

    def test_timing_does_not_make_evidence_stale(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestDetectCli(Base):
    def test_detect_prints_json(self):
        (self.root / "Cargo.toml").write_text("")
        p = subprocess.run(["python3", str(Path(herd.__file__)), "detect"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)[0]["type"], "rust")

    def test_detect_empty_repo(self):
        p = subprocess.run(["python3", str(Path(herd.__file__)), "detect"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout), [])


class TestGate(Base):
    def gate(self, **hook):
        return herd.gate(self.root, hook)

    def test_no_active_task_allows(self):
        self.assertIsNone(self.gate())

    def test_blocks_without_evidence(self):
        self.task()
        out = self.gate()
        self.assertEqual(out["decision"], "block")
        self.assertIn("herd verify", out["reason"])

    def test_blocks_failing_then_allows_passing(self):
        self.task()
        herd.verify(self.root, "t1")
        self.assertIn("C1", self.gate()["reason"])
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIsNone(self.gate())

    def test_blocks_stale_evidence(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIsNone(self.gate())
        (self.root / "greet.txt").write_text("changed")  # workspace changed after verify
        self.assertIn("stale", self.gate()["reason"])
        herd.verify(self.root, "t1")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK + "\n# edit\n")
        self.assertIn("stale", self.gate()["reason"])

    def test_no_passing_criterion_blocks(self):
        self.task('goal = "g"\n\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "human"\ncheck = ""\n')
        herd.verify(self.root, "t1")
        self.assertIn("no passing", self.gate()["reason"])

    def test_circuit_breaker_after_three_blocks(self):
        self.task()
        for _ in range(herd.MAX_BLOCKS):
            self.assertEqual(self.gate()["decision"], "block")
        self.assertIsNone(self.gate())  # allows, so a stuck agent can stop and escalate

    def test_block_counter_resets_when_passing(self):
        self.task()
        self.gate()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIsNone(self.gate())
        self.assertFalse((self.root / ".herd/tasks/t1/gate_blocks").exists())


class TestCli(Base):
    def run_cli(self, *args):
        p = subprocess.run(["python3", str(Path(herd.__file__)), *args], cwd=self.root,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_flow(self):
        rc, out, _ = self.run_cli("init", "t1", "Add a greeting")
        self.assertEqual(rc, 0)
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.assertEqual(self.run_cli("check")[0], 0)
        self.assertEqual(self.run_cli("verify")[0], 1)  # C1 failing
        (self.root / "greet.txt").write_text("hello")
        rc, out, _ = self.run_cli("verify")
        self.assertEqual(rc, 0)
        self.assertIn("1 passing", out)
        rc, out, _ = self.run_cli("done")
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / ".herd/active").exists())
        self.assertTrue((self.root / ".herd/tasks/t1/evidence.md").exists())
        self.assertIn("done: evidence is fresh and passing", out)

    def test_done_refuses_when_not_passing(self):
        self.run_cli("init", "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.run_cli("verify")
        rc, _, err = self.run_cli("done")
        self.assertEqual(rc, 1)
        self.assertTrue((self.root / ".herd/active").exists())

    def test_gate_reads_hook_json_from_stdin(self):
        self.run_cli("init", "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        p = subprocess.run(["python3", str(Path(herd.__file__)), "gate"], cwd=self.root,
                           input=json.dumps({"cwd": str(self.root)}), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_triage(self):
        rc, out, _ = self.run_cli("triage", "Change auth/session.py to rotate tokens")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["risk"]["floor"], "high")


if __name__ == "__main__":
    unittest.main()
