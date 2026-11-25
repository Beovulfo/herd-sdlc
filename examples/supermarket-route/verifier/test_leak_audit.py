import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import leak_audit as la  # noqa: E402
import run_leg  # noqa: E402

VIOLATION = "<sandbox_violations>\ndeny(1) file-read-data /Users/x/secret\ndeny(1) network-outbound x:443\n</sandbox_violations>"


def use(name, tool_input, tid="t1", parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": tool_input}]}}


def result(tid, text, is_error=False, parent=None):
    return {"type": "user", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text,
                                     "is_error": is_error}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.work = self.dir / "run-1" / "work"
        self.work.mkdir(parents=True)
        self.settings = self.dir / "run-1" / "settings.json"
        self.settings.write_text(json.dumps(run_leg.build_settings(self.dir, 1, 1)))

    def write(self, *events, text=None):
        log = self.dir / "run.jsonl"
        log.write_text(text if text is not None else "\n".join(json.dumps(e) for e in events) + "\nnot json\n")
        return log

    def audit(self, *events):
        return la.audit(self.write(*events), self.work)

    def cli(self, *events, text=None, log=None):
        path = log or self.write(*events, text=text)
        return subprocess.run([sys.executable, str(HERE / "leak_audit.py"), str(path), "--work", str(self.work)],
                              capture_output=True, text=True)

    def set_settings(self, mutate):
        s = json.loads(self.settings.read_text())
        mutate(s)
        self.settings.write_text(json.dumps(s))


class TestAudit(Base):
    def test_clean_log(self):
        f = self.audit(use("Bash", {"command": "cat /etc/hosts ~/x; ls .."}), result("t1", "ok"),
                       use("Write", {"file_path": "a.py", "content": "x = a / b  # /api"}, "t2"),
                       {"type": "result", "subtype": "success"})
        self.assertEqual(f, [])

    def test_sandbox_violations_block_lists_each_line(self):
        f = self.audit(use("Bash", {"command": "cat x"}), result("t1", VIOLATION))
        self.assertEqual(len(f), 2)
        self.assertTrue(all(x.blocked and x.tool == "Bash" for x in f))
        self.assertIn("file-read-data /Users/x/secret", f[0].detail)

    def test_operation_not_permitted(self):
        f = self.audit(use("Bash", {"command": "cat x"}), result("t1", "cat: x: Operation not permitted"))
        self.assertEqual([(x.blocked, x.detail) for x in f], [(True, "Operation not permitted")])

    def test_permission_denial(self):
        f = self.audit(use("Read", {"file_path": "~/x"}),
                       result("t1", "Permission to use Read has been denied by your permission settings", True))
        self.assertEqual(len(f), 1)
        self.assertTrue(f[0].blocked)

    def test_result_text_in_block_list(self):
        c = [{"type": "text", "text": "Operation not permitted"}]
        self.assertEqual(len(self.audit(use("Bash", {"command": "x"}), result("t1", c))), 1)

    def test_webfetch_and_websearch_calls(self):
        f = self.audit(use("WebFetch", {"url": "u"}), use("WebSearch", {"query": "q"}, "t2"))
        self.assertEqual([(x.tool, x.blocked) for x in f], [("WebFetch", False), ("WebSearch", False)])

    def test_subagent_message_with_violation(self):
        f = self.audit(use("Bash", {"command": "x"}, parent="p1"), result("t1", VIOLATION, parent="p1"))
        self.assertEqual(len(f), 2)

    def test_command_text_is_never_read(self):
        f = self.audit(use("Bash", {"command": "curl https://example.com/x; cat ~/.ssh/id_rsa"}), result("t1", "ok"))
        self.assertEqual(f, [])

    def test_missing_settings(self):
        self.settings.unlink()
        f = self.audit()
        self.assertEqual(len(f), 1)
        self.assertIn("not isolated", f[0].detail)

    def test_settings_without_sandbox(self):
        self.set_settings(lambda s: s.pop("sandbox"))
        f = self.audit()
        self.assertTrue(f and all("not isolated" in x.detail for x in f))
        self.assertTrue(any("sandbox.enabled" in x.detail for x in f))

    def test_each_weakened_setting_is_found(self):
        def disable(s): s["sandbox"]["enabled"] = False
        def unsandboxed(s): s["sandbox"]["allowUnsandboxedCommands"] = True
        def no_home(s): s["sandbox"]["filesystem"]["denyRead"].remove("~/")
        def no_read(s): s["permissions"]["deny"].remove("Read(~/**)")
        def no_fetch(s): s["permissions"]["deny"].remove("WebFetch")
        def no_search(s): s["permissions"]["deny"].remove("WebSearch")
        for mutate in (disable, unsandboxed, no_home, no_read, no_fetch, no_search):
            self.set_settings(lambda s: None)
            self.settings.write_text(json.dumps(run_leg.build_settings(self.dir, 1, 1)))
            self.set_settings(mutate)
            f = self.audit()
            self.assertEqual(len(f), 1, mutate.__name__)
            self.assertIn("not isolated", f[0].detail)

    def test_settings_option_overrides_default(self):
        other = self.dir / "other.json"
        other.write_text("{}")
        self.assertGreaterEqual(len(la.audit(self.write(), self.work, settings=other)), 5)

    def test_cli_exit_codes_and_summary(self):
        a = self.cli(use("Read", {"file_path": "a"}))
        self.assertEqual(a.returncode, 0)
        self.assertIn("leak audit: clean", a.stdout)
        b = self.cli(use("WebFetch", {"url": "u"}))
        self.assertEqual(b.returncode, 1)
        self.assertIn("leak audit: 1 findings (0 blocked)", b.stdout)


class TestAttacks(Base):
    def test_bad_input_missing_or_binary_log_gives_one_message_no_traceback(self):
        r = self.cli(log=self.dir / "absent.jsonl")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        r = self.cli(text="\x00\x01 not json at all\n{}\n[]\n\"s\"\n")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "leak audit: clean"))

    def test_collision_same_path_in_two_calls_counts_twice(self):
        e = [use("Bash", {"command": "a"}, "t1"), result("t1", "Operation not permitted"),
             use("Bash", {"command": "a"}, "t2"), result("t2", "Operation not permitted")]
        self.assertIn("leak audit: 2 findings (2 blocked)", self.cli(*e).stdout)

    def test_one_bad_part_malformed_events_do_not_hide_a_real_finding(self):
        r = self.cli({"type": "assistant", "message": {"content": "text"}}, {"type": "assistant", "message": None},
                     {"type": "assistant", "message": {"content": [None, 3, {"type": "tool_use"}]}},
                     use("WebFetch", {"url": "u"}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("leak audit: 1 findings", r.stdout)

    def test_recount_summary_matches_lines_printed(self):
        e = [use("Bash", {"command": "x"}, "t1"), result("t1", VIOLATION), use("WebSearch", {"query": "q"}, "t2")]
        r = self.cli(*e)
        lines = [x for x in r.stdout.splitlines() if not x.startswith("leak audit:")]
        blocked = sum(x.endswith("\tblocked") for x in lines)
        self.assertEqual(r.stdout.splitlines()[-1], f"leak audit: {len(lines)} findings ({blocked} blocked)")
        self.assertEqual((len(lines), blocked), (3, 2))

    def test_refusal_is_not_raised_for_allowed_roots_and_is_for_neighbours(self):
        for text in ("[]", "not json", ""):
            self.settings.write_text(text)
            f = self.audit()
            self.assertEqual(len(f), 1, text)
            self.assertIn("not isolated", f[0].detail)


class TestMissingWork(Base):
    def test_missing_work_folder_exits_2_with_one_message_and_no_clean_verdict(self):
        gone = self.dir / "no-such-dir"
        log = self.write(use("Read", {"file_path": "a"}))
        r = subprocess.run([sys.executable, str(HERE / "leak_audit.py"), str(log), "--work", str(gone)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("work folder not found", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("clean", r.stdout + r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_missing_work_folder_raises_in_the_api(self):
        with self.assertRaises(ValueError) as cm:
            la.audit(self.write(use("Read", {"file_path": "a"})), self.dir / "no-such-dir")
        self.assertIn("work folder not found", str(cm.exception))

    def test_work_path_that_is_a_file_is_refused(self):
        f = self.dir / "a-file"
        f.write_text("x")
        with self.assertRaises(ValueError):
            la.audit(self.write(), f)

    def test_refusal_matches_plain_directory_check(self):
        # Separate code decides what should be refused: pathlib, not the code under test.
        file_path = self.dir / "a-file"
        file_path.write_text("x")
        paths = [self.work, self.dir / "no-such-dir", file_path, self.dir / "no-such" / "deeper", self.dir / ""]
        for p in paths:
            should_refuse = not Path(p).is_dir()
            try:
                la.audit(self.write(), p, settings=self.settings)
                refused = False
            except ValueError:
                refused = True
            self.assertEqual(refused, should_refuse, str(p))

    def test_other_readings_of_an_existing_folder_are_served(self):
        # Readings of "the work folder": absolute or relative, with or without a trailing slash.
        relative = os.path.relpath(self.work, os.getcwd())
        for variant in (str(self.work), str(self.work) + os.sep, relative, relative + os.sep):
            self.assertEqual(la.audit(self.write(), variant, settings=self.settings), [], variant)


class TestTask(Base):
    def test_hidden_file_in_the_work_folder_is_a_finding_for_either_task(self):
        (self.work / "sub").mkdir()
        (self.work / "sub" / "bus_verify.py").write_text("x")
        for task in (None, "bus-transfer"):
            f = la.audit(self.write(use("Read", {"file_path": "a"})), self.work, task=task)
            self.assertEqual(len(f), 1, task)
            self.assertIn("bus_verify.py", f[0].detail)
            self.assertFalse(f[0].blocked)
        (self.work / "sub" / "bus_verify.py").unlink()
        (self.work / "verify_general.py").write_text("x")
        self.assertEqual(len(la.audit(self.write(), self.work)), 1)
        self.assertEqual(len(la.audit(self.write(), self.work, task="bus-transfer")), 1)

    def test_cli_task_as_name_or_path_and_clean_bus_run(self):
        log = self.write(use("Bash", {"command": "python3 plan.py"}, "t1"), result("t1", "ok"))
        for task in ("bus-transfer", "examples/bus-transfer/"):
            r = subprocess.run([sys.executable, str(HERE / "leak_audit.py"), str(log), "--work", str(self.work),
                                "--task", task], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "leak audit: clean"), (task, r.stderr))
        r = subprocess.run([sys.executable, str(HERE / "leak_audit.py"), str(log), "--work", str(self.work),
                            "--task", "nope"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown task", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
