"""Attacks on `herd note --covered-by` (issue #85), run through the real command line in temporary repositories.

`python3 -m tests.test_covered_by_attacks both|unknown|example` runs one case for --refuses or --example."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERD = Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "herd.py"
NAMES = ("bad-input", "collision", "one-bad-part", "recount", "refusal", "other-reading")
MAY_BE_COVERED = ("recount", "refusal", "other-reading")
PASS, FAIL = 'python3 -c "import json"', 'python3 -c "import no_such_module"'


def herd(root, *args):
    return subprocess.run([sys.executable, str(HERD), *args], cwd=root, capture_output=True, text=True, timeout=60)


def write_task(root, criteria):
    lines = ['goal = "g"', "inputs = []"]
    for cid, check in criteria:
        lines += ["[[criteria]]", f"id = {json.dumps(cid)}", 'text = "t"', 'source = "agent-proposed"',
                  f"check = {json.dumps(check)}"]
    (Path(root) / ".herd/tasks/t/task.toml").write_text("\n".join(lines) + "\n")


def repo(root, criteria):
    for args in (["init", "-q"], ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q",
                                  "--allow-empty", "-m", "i"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    assert herd(root, "init", "t", "g").returncode == 0
    write_task(root, criteria)
    # these tests assert the exact attack list: start past the first verify, which would need all six notes (issue #94)
    (Path(root) / ".herd/tasks/t/red.json").write_text('{"at": "2026-01-01T00:00:00Z", "notes": 1000}\n')


def logged(root):
    p = Path(root) / ".herd/tasks/t/notes.jsonl"
    return p.read_text().splitlines() if p.exists() else []


def evidence(root):
    herd(root, "verify")
    return json.loads((Path(root) / ".herd/tasks/t/evidence.json").read_text())


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def note(self, attack, *args):
        return herd(self.root, "note", "--tried", "--attack", attack, *args, "covers it")

    def assert_refused(self, p):
        self.assertIn(p.returncode, range(1, 126), p.stdout)
        self.assertTrue(p.stderr.strip())
        self.assertNotIn("Traceback", p.stdout + p.stderr)


class BadInput(Repo):
    def test_every_bad_argument_and_file_ends_with_a_message(self):
        repo(self.root, [("C1", PASS)])
        for args in (["--covered-by"], ["--covered-by", ""], ["--covered-by", "  "], ["--covered-by", "c1"],
                     ["--covered-by", "C1; rm -rf x"], ["--covered-by", "C1", "--covered-by", "C1"],
                     ["--covered-by", "C1", "--timeout", "5"], ["--covered-by", "C1", "--refuses", PASS]):
            self.assert_refused(self.note("recount", *args))
        self.assert_refused(herd(self.root, "note", "--found", "--covered-by", "C1", "x"))
        self.assert_refused(herd(self.root, "note", "--tried", "--covered-by", "C1", "x"))
        task = Path(self.root) / ".herd/tasks/t/task.toml"
        for broken in ("not [ toml", "goal = 'g'\ncriteria = 3\n", "goal = 'g'\ncriteria = [3]\n", ""):
            task.write_text(broken)
            self.assert_refused(self.note("recount", "--covered-by", "C1"))
        task.unlink()
        self.assert_refused(self.note("recount", "--covered-by", "C1"))
        self.assertEqual(logged(self.root), [])
        write_task(self.root, [("C1", PASS)])  # the control: the refusals above are not a missing feature
        self.assertEqual(self.note("recount", "--covered-by", "C1").returncode, 0)


class Collision(Repo):
    def test_attacks_sharing_a_criterion_all_count_and_two_proofs_are_refused(self):
        repo(self.root, [("C1", PASS)])
        self.assert_refused(self.note("recount", "--covered-by", "C1", "--check", FAIL))
        self.assertEqual(logged(self.root), [])
        for name in MAY_BE_COVERED:
            self.assertEqual(self.note(name, "--covered-by", "C1").returncode, 0)
        self.assertEqual([(a["attack"], a["status"]) for a in evidence(self.root)["attacks"]],
                         [(n, "passing") for n in MAY_BE_COVERED])


class OneBadPart(Repo):
    def test_a_removed_criterion_fails_its_attack_and_no_other(self):
        repo(self.root, [("C1", PASS), ("C2", PASS)])
        self.assertEqual(self.note("recount", "--covered-by", "C1").returncode, 0)
        self.assertEqual(self.note("refusal", "--covered-by", "C2").returncode, 0)
        write_task(self.root, [("C2", PASS)])
        got = {a["attack"]: a["status"] for a in evidence(self.root)["attacks"]}
        self.assertEqual(got, {"recount": "failing", "refusal": "passing"})

    def test_a_hand_edited_note_cannot_cover_another_attack(self):
        repo(self.root, [("C1", PASS)])
        self.assertEqual(self.note("recount", "--covered-by", "C1").returncode, 0)
        p = Path(self.root) / ".herd/tasks/t/notes.jsonl"
        p.write_text(p.read_text().replace('"recount"', '"bad-input"'))
        self.assertNotEqual(evidence(self.root)["attacks"][0]["status"], "passing")


class Recount(Repo):
    def test_states_match_a_separate_count_on_random_cases(self):
        repo(self.root, [("C1", PASS)])
        rng = random.Random(85)
        checks = {PASS: "passing", FAIL: "failing", "": "nocheck"}
        for _ in range(6):
            crit = [(f"C{i}", rng.choice(list(checks))) for i in range(rng.randint(1, 5))]
            write_task(self.root, crit)
            (Path(self.root) / ".herd/tasks/t/notes.jsonl").unlink(missing_ok=True)
            want = {}
            for name in rng.sample(MAY_BE_COVERED, rng.randint(1, 3)):
                cid, check = rng.choice(crit)
                self.assertEqual(self.note(name, "--covered-by", cid).returncode, 0)
                want[name] = (cid, checks[check])
            ev = evidence(self.root)
            self.assertEqual({a["attack"]: (a["covered_by"], a["status"]) for a in ev["attacks"]}, want)
            report = herd(self.root, "status").stdout
            words = {"passing": "passing", "failing": "failing"}
            for name, (cid, state) in want.items():
                if state in words:
                    self.assertIn(f"{name} {words[state]} (check: --covered-by {cid})", report)


class Refusal(Repo):
    def test_refused_exactly_when_a_plain_rule_says_so(self):
        known = ["C1", "AC-2", "red first"]
        repo(self.root, [(cid, PASS) for cid in known])
        rng = random.Random(850)
        ids = known + ["C2", "c1", "C1 C1", "".join(rng.choice("AC12-") for _ in range(4))]
        for name in NAMES:
            for cid in ids:
                before = len(logged(self.root))
                p = self.note(name, "--covered-by", cid)
                ok = name in MAY_BE_COVERED and cid in known
                self.assertEqual(p.returncode == 0, ok, (name, cid, p.stderr))
                self.assertEqual(len(logged(self.root)) - before, int(ok))
                if not ok:
                    self.assert_refused(p)


class OtherReading(Repo):
    def test_every_reading_of_an_id_and_of_passing_is_served(self):
        rng = random.Random(8500)
        ids = ["C3", "AC-2", "red first", "3", "é-1", f"X{rng.randint(10, 999)}"]
        checks = [PASS, FAIL, "true", 'python3 -c "print(\'Ran 0 tests\')"']
        repo(self.root, [(cid, PASS) for cid in ids])
        for cid in ids:  # the id as written, and with stray spaces
            for given in (cid, f" {cid} "):
                self.assertEqual(self.note("recount", "--covered-by", given).returncode, 0, given)
                self.assertEqual(evidence(self.root)["attacks"][-1]["status"], "passing", given)
        for check in checks:  # "passing": the latest verify's result; no tests or no project code never counts
            write_task(self.root, [("C3", check)])
            self.assertEqual(self.note("recount", "--covered-by", "C3").returncode, 0)
            a = evidence(self.root)["attacks"][-1]
            counts = a["status"] == "passing" and not a["zero_tests"] and not a.get("vacuous")
            self.assertEqual(counts, check == PASS, check)


def one_case(case):
    """For --refuses (both, unknown) and --example (example): herd's own exit code and message."""
    with tempfile.TemporaryDirectory() as root:
        repo(root, [("C3", PASS)])
        args = {"both": ["--covered-by", "C3", "--check", PASS], "unknown": ["--covered-by", "C9"],
                "example": ["--covered-by", "C3"]}[case]
        p = herd(root, "note", "--tried", "--attack", "recount", *args, "what it covers")
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        return p.returncode


if __name__ == "__main__":
    sys.exit(one_case(sys.argv[1]))
