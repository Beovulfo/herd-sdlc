"""`herd pr --draft --milestone NAME`, and refusal of anything else (issue #125).

A temporary repository with a bare local origin and a fake `gh` that logs each call as one JSON list.
`python3 -m tests.test_pr_flags refuse-collision|refuse-bad-milestone|example` runs one case by hand.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd

HERD = Path(herd.__file__).resolve()
ROOT = Path(__file__).resolve().parent.parent
URL = "https://example.invalid/pull/1"
GH = f"""#!{sys.executable}
import json, os, sys
a = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(a) + "\\n")
if "--body-file" in a:
    sys.stdin.read()
if a[:2] == ["pr", "view"]:
    if os.environ.get("GH_OPEN"):
        print("{URL}")
    sys.exit(0 if os.environ.get("GH_OPEN") else 1)
bad = os.environ.get("GH_FAIL")
if bad == "milestone" and "--milestone" in a:
    sys.exit("could not add to milestone: not found")
if bad == "ready" and a[:2] == ["pr", "ready"]:
    sys.exit("drafts are not supported here")
print("{URL}")
"""


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.work, self.origin, self.log = d / "w", d / "o.git", d / "gh.log"
        self.work.mkdir()
        (d / "bin").mkdir()
        (d / "bin" / "gh").write_text(GH)
        (d / "bin" / "gh").chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if k not in ("GH_OPEN", "GH_FAIL")}
        self.env.update(PATH=f"{d / 'bin'}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(self.log))
        self.git("init", "-q", "--bare", str(self.origin))
        self.git("init", "-q")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "i")
        for args in (("init", "t", "g", "--quick", "true"), ("verify",)):
            p = self.herd(*args)
            assert p.returncode == 0, p.stderr

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True, text=True).stdout

    def herd(self, *args, **env):
        return subprocess.run([sys.executable, str(HERD), *args], cwd=self.work, env={**self.env, **env},
                              capture_output=True, text=True)

    def reset(self):
        """Forget the push and the gh calls, so one repository serves many cases."""
        self.log.unlink(missing_ok=True)
        if self.pushed():
            self.git("push", "-q", "origin", "--delete", "herd/t")

    def pushed(self):
        return bool(self.git("ls-remote", "--heads", str(self.origin), "herd/t"))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def call(self, verb):
        found = [c for c in self.calls() if c[:2] == ["pr", verb]]
        assert len(found) <= 1, found
        return found[0] if found else None


def milestone_of(call):
    return call[call.index("--milestone") + 1] if "--milestone" in call else None


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.tmp.cleanup)

    def ok(self, *args, **env):
        self.repo.reset()
        p = self.repo.herd("pr", *args, **env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.repo.pushed())
        return p

    def refused(self, *args):
        self.repo.reset()
        p = self.repo.herd("pr", *args)
        self.assertNotEqual(p.returncode, 0, args)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual((self.repo.pushed(), self.repo.calls()), (False, []), args)
        return p.stderr


class TestFlags(Base):
    def test_flags_in_any_order_with_or_without_the_slug(self):
        name = "Field robustness: é"
        for args in (("t", "--yes", "--draft", "--milestone", name), ("--milestone", name, "--draft", "--yes", "t"),
                     ("--draft", "--yes", "--milestone", name)):
            self.ok(*args)
            create = self.repo.call("create")
            self.assertIn("--draft", create, args)
            self.assertEqual(milestone_of(create), name, args)
            self.assertIsNone(self.repo.call("ready"))

    def test_no_flags_gives_neither(self):
        self.ok("t", "--yes")
        create = self.repo.call("create")
        self.assertNotIn("--draft", create)
        self.assertNotIn("--milestone", create)


class TestExisting(Base):
    def test_open_pr_gets_milestone_and_draft(self):
        self.ok("--yes", "--draft", "--milestone", "M 1", GH_OPEN="1")
        self.assertIsNone(self.repo.call("create"))
        edit = self.repo.call("edit")
        self.assertEqual(milestone_of(edit), "M 1")
        self.assertNotIn("--draft", edit)
        self.assertEqual(self.repo.call("ready"), ["pr", "ready", "herd/t", "--undo"])

    def test_open_pr_without_flags_keeps_draft_state_and_milestone(self):
        self.ok("--yes", GH_OPEN="1")
        self.assertNotIn("--milestone", self.repo.call("edit"))
        self.assertIsNone(self.repo.call("ready"))


class TestBadInput(Base):
    def test_refused_before_any_push_or_gh_call(self):
        for bad in (["--no-such-flag"], ["-d"], ["--milestone=M"], ["--Draft"], ["--milestone"],
                    ["--milestone", "--draft"], ["--milestone", ""], ["--milestone", "  "], ["t", "extra"]):
            err = self.refused("--yes", *bad)
            self.assertEqual(len(err.strip().splitlines()), 1, err)

    def test_unknown_slug(self):
        self.refused("nope", "--yes", "--draft")


class TestCollision(Base):
    def test_two_names_are_refused(self):
        self.assertIn("--milestone", self.refused("t", "--yes", "--milestone", "A", "--milestone", "B"))

    def test_repeats_are_harmless(self):
        self.ok("t", "--yes", "--yes", "--draft", "--draft", "--milestone", "A", "--milestone", "A")
        create = self.repo.call("create")
        self.assertEqual((create.count("--draft"), create.count("--milestone")), (1, 1))

    def test_slug_equal_to_the_milestone(self):
        self.ok("t", "--yes", "--milestone", "t")
        self.assertEqual(milestone_of(self.repo.call("create")), "t")


class TestOneBadPart(Base):
    def fails(self, message, *args, **env):
        p = self.repo.herd("pr", "--yes", *args, **env)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn(message, p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    def test_rejected_milestone_is_not_retried_without_it(self):
        self.fails("not found", "--milestone", "M", GH_FAIL="milestone")
        self.assertEqual(len([c for c in self.repo.calls() if c[:2] == ["pr", "create"]]), 1)

    def test_rejected_draft_on_an_open_pr_still_records_the_pr(self):
        self.fails("drafts are not supported", "--draft", GH_OPEN="1", GH_FAIL="ready")
        self.assertEqual((self.repo.work / ".herd/tasks/t/pr").read_text().strip(), URL)


def oracle(args):
    """(draft, milestone) when the argument list is acceptable, else None. Written apart from herd's parser."""
    names, rest, draft, it = set(), [], False, iter(args)
    for a in it:
        if a == "--milestone":
            value = next(it, "")
            if not value.strip() or value[0] == "-":
                return None
            names.add(value)
        elif a == "--draft":
            draft = True
        elif a != "--yes":
            rest.append(a)
    if len(names) > 1 or rest not in ([], ["t"]):
        return None
    return draft, next(iter(names), None)


class TestRefusal(Base):
    def test_random_argument_lists(self):
        rng = random.Random(125)
        words = ["t", "--draft", "--milestone", "A", "B c", "--yes", "--nope", ""]
        seen = set()
        for _ in range(60):
            args = ["--yes", *rng.choices(words, [3, 3, 4, 2, 1, 1, 1, 1], k=rng.randint(0, 4))]
            want = oracle(args)
            seen.add(want is None)
            if want is None:
                self.refused(*args)
                continue
            self.ok(*args)
            create = self.repo.call("create")
            self.assertEqual(("--draft" in create, milestone_of(create)), want, args)
        self.assertEqual(seen, {True, False})


class TestDocs(unittest.TestCase):
    def test_guard_hint_names_the_draft_flag(self):
        self.assertIn("herd pr --draft", herd.GUARD_WHY["git push"])

    def test_readme_and_run_skill_list_both_flags(self):
        for name in ("README.md", "plugin/skills/run/pr.md"):
            text = (ROOT / name).read_text()
            self.assertIn("--draft", text, name)
            self.assertIn("--milestone", text, name)


def by_hand(word):
    repo = Repo()
    try:
        if word == "example":
            p = repo.herd("pr", "--yes", "--draft", "--milestone", "Field robustness", "t")
            create = repo.call("create")
            print(f"draft={'yes' if '--draft' in create else 'no'} milestone=[{milestone_of(create)}]")
        elif word == "refuse-collision":
            p = repo.herd("pr", "t", "--yes", "--milestone", "A", "--milestone", "B")
        else:
            p = repo.herd("pr", "t", "--yes", "--milestone", "M", GH_FAIL="milestone")
        sys.stderr.write(p.stderr)
        return p.returncode
    finally:
        shutil.rmtree(repo.tmp.name)


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] in ("example", "refuse-collision", "refuse-bad-milestone"):
        sys.exit(by_hand(sys.argv[1]))
    unittest.main()
