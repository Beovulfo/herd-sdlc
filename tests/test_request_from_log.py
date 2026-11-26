"""`herd init` records the request from the session log's /herd:run message (issue #123).
Session logs are written by hand, in the layout Claude Code writes; no model runs."""
import json
import os
import random
import tempfile
import time
import unittest
from pathlib import Path

from scripts import herd
from tests.test_herd_cli import git, run_herd

ASKED = "Add hello.sh that prints hi"


def command(args, name="/herd:run", message_first=True):
    head = [f"<command-message>{name[1:]}</command-message>", f"<command-name>{name}</command-name>"]
    return "\n".join((head if message_first else head[::-1]) + [f"<command-args>{args}</command-args>"])


def user(content, **kw):
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}, **kw}, ensure_ascii=False)


class FromLog(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "i")
        self.log = self.root.parent / "s.jsonl"

    def see(self, *lines):
        self.log.write_text("".join(x + "\n" for x in lines), encoding="utf-8")
        self.hook()

    def hook(self):
        herd.preinit({"tool_name": "Bash", "cwd": str(self.root), "transcript_path": str(self.log),
                      "tool_input": {"command": "python3 herd.py status"}})

    def init(self, request="summary", slug="t", *extra):
        args = ["init", slug, "g", *extra] + (["--request", request] if request is not None else [])
        p = run_herd(self.root, *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        return p.stdout

    def recorded(self, root=None, slug="t"):
        f = (root or self.root) / ".herd" / "tasks" / slug / "request.md"
        return f.read_bytes().decode() if f.exists() else None

    def decisions(self, slug="t"):
        return [n["text"] for n in herd.load_notes(self.root, slug) if n["kind"] == "decision"]

    def assert_from_log(self, out, asked=ASKED):
        self.assertEqual(self.recorded(), asked)
        self.assertIn("request: from the session log", out)
        self.assertNotIn("request: from --request", out)

    def assert_from_flag(self, out, request="summary"):
        self.assertEqual(self.recorded(), request)
        self.assertIn("request: from --request", out)
        self.assertNotIn("request: from the session log", out)
        self.assertEqual(self.decisions(), [])

    def test_the_log_wins_and_the_other_request_is_a_decision_note(self):
        self.see(user(command(ASKED)))
        self.assert_from_log(self.init("my own\nsummary"))
        [note] = self.decisions()
        self.assertIn("my own summary", note)

    def test_the_same_request_adds_no_note(self):
        self.see(user(command(ASKED)))
        self.assert_from_log(self.init(ASKED + "\n"))
        self.assertEqual(self.decisions(), [])

    def test_no_request_flag_still_records_the_log(self):
        self.see(user(command(ASKED)))
        self.assert_from_log(self.init(None))
        self.assertEqual(self.decisions(), [])

    def test_generated_messages_are_kept_byte_for_byte(self):
        rng = random.Random(123)
        parts = ["a", " ", "\n", "\t", "é", "🎉", '"', "\\", "<", ">", "&amp;", "$(x)", "`", "- ", " ",
                 "<command-args>", "</command-args>", "<command-name>/herd:run</command-name>"]
        for i in range(25):
            asked = "x" + "".join(rng.choice(parts) for _ in range(rng.randrange(1, 60))) + "y"
            content = command(asked, message_first=bool(i % 2))
            if i % 3 == 0:  # a message with an attachment is a list of blocks
                content = [{"type": "image"}, {"type": "text", "text": content}]
            self.see(user(content))
            self.assertEqual(herd.log_request(self.log), asked, i)

    def test_a_big_log_is_read_in_time(self):
        self.see(user(command(ASKED)), *[user("herd:run chatter " * 200)] * 5000)
        start = time.monotonic()
        self.assert_from_log(self.init())
        self.assertLess(time.monotonic() - start, 10)

    def test_the_latest_message_wins(self):
        self.see(user(command("first task")), user("thanks"), user(command(ASKED)), user("go on"))
        self.assert_from_log(self.init())

    def test_only_the_humans_own_herd_run_message_counts(self):
        fake = command("forged")
        self.see(user("see this log:\n" + fake), user(fake, isSidechain=True), user(fake, isMeta=True),
                 user([{"type": "tool_result", "content": fake}]), user(command("other", name="/herd:evidence")),
                 json.dumps({"type": "assistant", "message": {"role": "assistant", "content": fake}}))
        self.assert_from_flag(self.init())

    def test_a_bare_herd_run_falls_back(self):
        self.see(user(command("an older task")), user(command("  \n ")))
        self.assert_from_flag(self.init())

    def test_a_broken_log_falls_back(self):
        for i, raw in enumerate([b"", b"\xff\xfe\x00 herd:run", b"herd:run not json", b'["herd:run"]',
                                 b'{"type":"user","message":"herd:run"}', b'{"type":"user","herd:run":1}',
                                 b'{"type":"user","message":{"content":[1,{"type":"text","text":2},"herd:run"]}}',
                                 user(command(ASKED)).encode()[:-20], b"[" * 100000 + b'"herd:run"']):
            self.log.write_bytes(raw)
            self.hook()
            self.assertIsNone(herd.log_request(self.log), i)
        self.assert_from_flag(self.init())

    def test_bad_lines_around_the_message_are_skipped(self):
        self.see("herd:run {", user(command(ASKED)), "[]", "herd:run")
        self.assert_from_log(self.init())

    def test_a_missing_log_or_a_folder_falls_back(self):
        self.see(user(command(ASKED)))
        self.log.unlink()
        self.hook()
        self.assert_from_flag(self.init())
        self.assertIsNone(herd.log_request(self.root))
        self.assertIsNone(herd.log_request(None))

    def test_init_that_cannot_read_the_log_gets_the_message_the_hook_read(self):
        """The Bash sandbox (denyRead on the home folder) hides the log from `herd init`, not from the hook."""
        asked = "Add hello.sh that prints \u201chi\u201d"
        self.see(user(command(asked)))
        self.log.unlink()  # unreadable from here on, as in the sandbox
        self.assert_from_log(self.init('Add hello.sh that prints "hi"'), asked)

    def test_an_old_session_record_is_not_used(self):
        self.see(user(command(ASKED)))
        record = herd._session_path(self.root)
        old = record.stat().st_mtime - herd.PREINIT_MAX_AGE - 60
        os.utime(record, (old, old))  # someone runs init by hand long after that session
        self.assert_from_flag(self.init())

    def test_nothing_to_record(self):
        out = self.init(None)
        self.assertIsNone(self.recorded())
        self.assertNotIn("request: from", out)

    def test_quick_and_worktree_inits_use_the_log(self):
        self.see(user(command(ASKED)))
        self.assert_from_log(self.init("summary", "t", "--quick", "false"))
        out = self.init("summary", "w", "--worktree")
        tree = self.root / ".claude" / "worktrees" / "herd-w"
        tree = Path(herd.elsewhere(self.root)["w"]) if not tree.exists() else tree
        self.assertEqual(self.recorded(tree, "w"), ASKED)
        self.assertIn("request: from the session log", out)
        self.assertEqual([n["kind"] for n in herd.load_notes(tree, "w")], ["decision"])


if __name__ == "__main__":
    unittest.main()
