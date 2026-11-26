"""`herd note --fixed --closes N` (issue #126), run through the real command line in temporary repositories.

`python3 -m tests.test_note_closes example|twice|broken` runs one case for --example or --refuses."""
import json
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERD = Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "herd.py"


def herd(root, *args):
    return subprocess.run([sys.executable, str(HERD), *args], cwd=root, capture_output=True, text=True, timeout=60)


def repo(root):
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                 ["commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    assert herd(root, "init", "t", "g", "--quick", "true").returncode == 0


def notes_file(root):
    return Path(root) / ".herd/tasks/t/notes.jsonl"


def finish(root):
    """The lines of the final report, by their label."""
    assert herd(root, "verify").returncode == 0
    r = herd(root, "done")
    assert r.returncode == 0, r.stderr
    return {line.split(":")[0]: line for line in r.stdout.splitlines() if ":" in line}


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        repo(self.root)

    def ok(self, *args):
        r = herd(self.root, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def refused(self, *args):
        before = notes_file(self.root).read_text() if notes_file(self.root).exists() else ""
        r = herd(self.root, *args)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(notes_file(self.root).read_text() if notes_file(self.root).exists() else "", before)
        return r.stderr.strip()


class Closing(Repo):
    def test_closed_note_leaves_not_proven_and_enters_caveats(self):
        self.ok("note", "--open", "real run not done yet")
        self.ok("note", "--open", "scale not measured")
        self.assertIn("#1", self.ok("note", "--fixed", "--closes", "1", "real run done"))
        report = finish(self.root)
        self.assertNotIn("real run not done yet", report["Not proven"])
        self.assertIn("scale not measured", report["Not proven"])
        self.assertRegex(report["Caveats"], r"open #1 opened at \S.*?, closed at \S.*?: real run not done yet")
        self.assertIn("real run done", report["Caveats"])

    def test_open_notes_are_numbered_in_note_output_and_status(self):
        self.ok("note", "--found", "a bug")
        self.assertIn("#1", self.ok("note", "--open", "x"))
        self.assertIn("#2", self.ok("note", "--open", "y"))
        self.ok("note", "--fixed", "--closes", "1", "z")
        self.assertIn("- open #2: y", self.ok("status"))  # before any evidence too
        self.ok("verify")
        status = self.ok("status")
        self.assertRegex(status, r"open #1 \(closed at [^)]+\): x")
        self.assertIn("open #2: y", status)
        self.assertIn("1 open, 1 closed", status)

    def test_pr_body_drops_closed_open_caveat(self):
        sys.path.insert(0, str(HERD.parent))
        import herd as module
        self.ok("note", "--open", "gone later")
        self.ok("note", "--open", "still here")
        self.ok("note", "--fixed", "--closes", "1", "done")
        self.ok("verify")
        body = module.pr_body(Path(self.root), "t")
        self.assertNotIn("Open caveat: gone later", body)
        self.assertIn("Open caveat: still here", body)

    def test_not_open_or_missing_number_is_refused_with_one_line(self):
        self.assertEqual(len(self.refused("note", "--fixed", "--closes", "1", "z").splitlines()), 1)
        self.ok("note", "--open", "x")
        self.ok("note", "--fixed", "--closes", "1", "z")
        for number in ("1", "2", "0"):
            err = self.refused("note", "--fixed", "--closes", number, "again")
            self.assertEqual(len(err.splitlines()), 1, err)
            self.assertIn(number, err)


class BadInput(Repo):
    def test_bad_values_and_wrong_kinds(self):
        self.ok("note", "--open", "x")
        for value in ("", " ", "-1", "1.5", "abc", "²", "##1", "1,2", "9" * 5000):
            self.refused("note", "--fixed", "--closes", value, "t")
        for kind in ("--found", "--open", "--tried", "--decision", "--late-red", "--human-change"):
            self.refused("note", kind, "--closes", "1", "t")
        self.refused("note", "--fixed", "t", "--closes")
        self.refused("note", "--closes", "1", "t")
        self.refused("note", "--fixed", "--closes", "1", "--closes", "1", "t")
        self.refused("note", "--fixed", "--closes", "1", "  ")


class Collision(Repo):
    def test_same_text_twice_each_counted(self):
        self.ok("note", "--open", "same")
        self.assertIn("#2", self.ok("note", "--open", "same"))
        self.ok("note", "--fixed", "--closes", "1", "one done")
        self.assertEqual(finish(self.root)["Not proven"].count("same"), 1)

    def test_closing_twice_is_refused(self):
        self.ok("note", "--open", "x")
        self.ok("note", "--fixed", "--closes", "1", "z")
        self.refused("note", "--fixed", "--closes", "1", "other")


class OneBadPart(Repo):
    def test_broken_log_line_fails_the_close(self):
        self.ok("note", "--open", "x")
        with open(notes_file(self.root), "a") as f:
            f.write("{broken\n")
        self.refused("note", "--fixed", "--closes", "1", "z")


class Generated(Repo):
    def run_random(self, seed, steps=14):
        """Random notes and closes against a separate model: the model is a dict of number to (text, closed)."""
        rnd, model = random.Random(seed), {}
        for i in range(steps):
            what = rnd.choice(("open", "open", "close", "close", "found"))
            if what == "open":
                self.assertIn(f"#{len(model) + 1})", self.ok("note", "--open", f"limit-{seed}-{i}."))
                model[len(model) + 1] = [f"limit-{seed}-{i}.", False]
            elif what == "found":
                self.ok("note", "--found", f"bug-{i}")
            else:
                n = rnd.randint(0, len(model) + 2)
                if n in model and not model[n][1]:
                    self.ok("note", "--fixed", "--closes", rnd.choice((str(n), f"#{n}")), f"done-{i}")
                    model[n][1] = True
                else:
                    self.refused("note", "--fixed", "--closes", str(n), f"no-{i}")
        return model


class Recount(Generated):
    def test_report_matches_a_separate_count(self):
        model = self.run_random(1) | {}
        self.ok("verify")
        status = self.ok("status")
        left = sum(not closed for _, closed in model.values())
        self.assertIn(f"{left} open", status)
        report = finish(self.root)
        for number, (text, closed) in model.items():
            self.assertEqual(text in report["Not proven"], not closed, text)
            self.assertEqual(bool(re.search(rf"open #{number} opened at [^;]*closed at [^;]*{re.escape(text)}",
                                            report["Caveats"])), closed, text)


class Refusal(Generated):
    def test_refused_exactly_when_the_model_says_so(self):
        self.assertTrue(self.run_random(2, 20))


class OtherReading(Repo):
    def test_number_with_or_without_hash(self):
        for text in ("a", "b"):
            self.ok("note", "--open", text)
        self.ok("note", "--fixed", "--closes", "#2", "z")
        self.ok("note", "--fixed", "--closes", "1", "z")
        self.assertIn("nothing open", finish(self.root)["Not proven"])

    def test_log_written_before_this_version(self):
        notes_file(self.root).write_text(json.dumps({"at": "2026-01-01T00:00:00Z", "kind": "open",
                                                     "text": "old", "elapsed_s": None}) + "\n")
        self.ok("note", "--fixed", "--closes", "1", "z")
        self.assertIn("opened at 2026-01-01T00:00:00Z", finish(self.root)["Caveats"])


def case(name):
    with tempfile.TemporaryDirectory() as root:
        repo(root)
        herd(root, "note", "--open", "real run not done yet")
        if name == "broken":
            with open(notes_file(root), "a") as f:
                f.write("{broken\n")
        r = herd(root, "note", "--fixed", "--closes", "1", "real run done")
        if name == "twice":
            r = herd(root, "note", "--fixed", "--closes", "1", "not done after all")
        elif name == "example":
            print(finish(root)["Not proven"])
        sys.stderr.write(r.stderr)
        return r.returncode


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] in ("example", "twice", "broken"):
        sys.exit(case(sys.argv[1]))
    unittest.main()
