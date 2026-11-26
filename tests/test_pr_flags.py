"""`herd pr --draft --milestone NAME`, and refusal of anything else (issue #125).

A temporary repository with a bare local origin and a fake `gh` that logs each call as one JSON list.
`python3 -m tests.test_pr_flags refuse-collision|refuse-bad-milestone|example|refresh` runs one case by hand.
"""
import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    with open(os.environ["GH_LOG"] + ".body", "w") as f:
        f.write(sys.stdin.read())
if os.environ.get("GH_FAIL") == "edit" and a[:2] == ["pr", "edit"]:
    sys.exit("HTTP 502\\nsecond line of the error")
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


def record(repo, value=URL + "\n", slug="t"):
    path = repo.work / ".herd/tasks" / slug / "pr"
    path.write_bytes(value if isinstance(value, bytes) else value.encode())


def body(repo):
    return Path(str(repo.log) + ".body").read_text()


class Refresh(Base):
    def verify(self, *args, code=0, **env):
        self.repo.log.unlink(missing_ok=True)
        p = self.repo.herd("verify", "t", *args, **env)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        return p

    def task(self, *checks):
        text = "".join(f'[[criteria]]\nid = "C{i}"\ntext = "t{i}"\nsource = "agent-proposed"\ncheck = "{c}"\n'
                       for i, c in enumerate(checks, 1))
        (self.repo.work / ".herd/tasks/t/task.toml").write_text('goal = "g"\n' + text)

    def warned(self, p):
        lines = [line for line in p.stderr.splitlines() if "not refreshed" in line]
        self.assertEqual(len(lines), 1, p.stderr)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1, p.stderr)


class TestRefresh(Refresh):
    def test_edits_only_the_body_of_the_recorded_pr(self):
        record(self.repo)
        self.verify("--fresh")
        self.assertEqual(self.repo.calls(), [["pr", "edit", URL, "--body-file", "-"]])
        self.assertIn("1 of 1 criteria proven", body(self.repo))
        self.assertFalse(self.repo.pushed())

    def test_a_skipped_verify_refreshes_too_and_shows_a_closed_note_gone(self):
        record(self.repo)
        self.repo.herd("note", "--open", "limit-xyz")
        self.verify()
        self.assertIn("Open caveat: limit-xyz", body(self.repo))
        self.repo.herd("note", "--fixed", "--closes", "1", "resolved")
        p = self.verify()
        self.assertIn("unchanged since", p.stdout)
        self.assertNotIn("Open caveat", body(self.repo))

    def test_body_names_the_commit_and_uncommitted_changes(self):
        record(self.repo)
        head = self.repo.git("rev-parse", "HEAD")[:12]
        self.verify("--fresh")
        self.assertIn(f"on commit `{head}`.", body(self.repo))
        (self.repo.work / "dirty.txt").write_text("x")
        self.verify()
        self.assertIn(f"on commit `{head}` plus uncommitted changes.", body(self.repo))

    def test_only_writes_no_evidence_and_edits_nothing(self):
        record(self.repo)
        self.verify("--only", "C1")
        self.assertEqual(self.repo.calls(), [])


class TestRefreshNoGh(Refresh):
    def test_no_gh_on_path_is_silent(self):
        record(self.repo)
        tools = self.repo.work.parent / "tools"
        tools.mkdir()
        for name in ("git", "sh"):
            (tools / name).symlink_to(shutil.which(name))
        for check, code in (("true", 0), ("false", 1)):
            self.task(check)
            p = self.verify("--fresh", code=code, PATH=str(tools))
            self.assertEqual((p.stderr, self.repo.calls()), ("", []))
            self.assertNotIn("pr:", p.stdout)


class TestRefreshBadInput(Refresh):
    BAD = ("", "\n", "7", "--title", "not a url", "https://", f"{URL} extra", f"{URL}\n{URL}2\n", b"\xff\xfe")

    def test_bad_record_warns_once_and_calls_no_gh(self):
        for value in self.BAD:
            record(self.repo, value)
            self.warned(self.verify())
            self.assertEqual(self.repo.calls(), [], value)

    def test_record_that_is_a_folder(self):
        (self.repo.work / ".herd/tasks/t/pr").mkdir()
        self.warned(self.verify("--fresh"))
        self.assertEqual(self.repo.calls(), [])

    def test_failing_gh_keeps_both_exit_codes(self):
        record(self.repo)
        self.warned(self.verify("--fresh", GH_FAIL="edit"))
        self.task("false")
        self.warned(self.verify("--fresh", code=1, GH_FAIL="edit"))

    def test_gh_that_cannot_start_or_hangs(self):
        record(self.repo)
        gh = Path(self.repo.env["PATH"].split(os.pathsep)[0]) / "gh"
        for script in ("#!/no/such/interpreter\n", "#!/bin/sh\nexec sleep 20\n"):
            gh.write_text(script)
            err = io.StringIO()
            with mock.patch.dict(os.environ, self.repo.env), mock.patch.object(herd, "PR_REFRESH_S", 0.3), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                herd.refresh_pr(self.repo.work, "t")
            self.assertEqual(len(err.getvalue().strip().splitlines()), 1, err.getvalue())


class TestRefreshCollision(Refresh):
    def test_each_task_edits_its_own_pr(self):
        tasks = self.repo.work / ".herd/tasks"
        shutil.copytree(tasks / "t", tasks / "u")  # a second task with the same goal, criterion and check
        record(self.repo)
        record(self.repo, URL + "2\n", slug="u")
        for slug, url in (("t", URL), ("u", URL + "2"), ("t", URL)):
            self.repo.log.unlink(missing_ok=True)
            self.assertEqual(self.repo.herd("verify", slug).returncode, 0)
            self.assertEqual(self.repo.call("edit")[2], url)

    def test_two_different_prs_in_one_record_are_refused(self):
        record(self.repo, f"{URL}\n{URL}2\n")
        self.warned(self.verify())
        self.assertEqual(self.repo.calls(), [])


class TestRefreshRecount(Refresh):
    def test_counts_match_the_rows_of_the_body(self):
        rng = random.Random(137)
        record(self.repo)
        for _ in range(8):
            checks = rng.choices(["true", "false", ""], k=rng.randint(1, 6))
            self.task(*checks)
            self.verify("--fresh", code=int("false" in checks))
            text = body(self.repo)
            rows = len([line for line in text.splitlines() if line.startswith("| C")])
            self.assertEqual(rows, checks.count("true"), text)
            self.assertIn(f"**Result:** {rows} of {len(checks)} criteria proven by a passing check "
                          f"({checks.count('false')} failing, {checks.count('')} unchecked)", text)


def recordable(value):
    """One web address and nothing else. Written apart from herd's pattern."""
    words = value.split()
    return len(words) == 1 and any(words[0].startswith(s) and words[0] != s for s in ("http://", "https://"))


class TestRefreshRefusal(Refresh):
    def test_random_records(self):
        rng = random.Random(1370)
        parts = ["https://", "http://", "h.invalid/pull/1", " ", "\n", "-x", "ftp://"]
        seen = set()
        for _ in range(60):
            value = "".join(rng.choices(parts, [4, 2, 4, 1, 2, 1, 1], k=rng.randint(0, 4)))
            record(self.repo, value)
            p = self.verify()
            ok = recordable(value)
            seen.add(ok)
            self.assertEqual(self.repo.call("edit"), ["pr", "edit", value.strip(), "--body-file", "-"] if ok else None,
                             repr(value))
            self.assertEqual("not refreshed" in p.stderr, not ok, repr(value))
        self.assertEqual(seen, {True, False})


class TestRefreshOtherReading(Refresh):
    def test_any_way_of_recording_from_any_branch(self):
        for i, value in enumerate((URL + "\n", URL, URL + "\r\n", f"  {URL}  \n", "http://h.invalid/o/r/pull/12\n")):
            self.repo.git("switch", "-q", "-c", f"other-{i}")
            record(self.repo, value)
            self.verify()
            self.assertEqual(self.repo.call("edit")[2], value.strip(), repr(value))


class TestDocs(unittest.TestCase):
    def test_guard_hint_names_the_draft_flag(self):
        self.assertIn("herd pr --draft", herd.GUARD_WHY["git push"])

    def test_readme_and_run_skill_list_both_flags(self):
        for name in ("README.md", "plugin/skills/run/pr.md"):
            text = (ROOT / name).read_text()
            self.assertIn("--draft", text, name)
            self.assertIn("--milestone", text, name)

    def test_docs_say_verify_refreshes_the_description(self):
        for name in ("README.md", "plugin/skills/run/pr.md", "docs/how-it-works.md"):
            self.assertRegex((ROOT / name).read_text(), r"`herd verify`[^.]*(rewrites|refreshes)[^.]*description", name)


def by_hand(word):
    repo = Repo()
    try:
        if word == "refresh":
            # the issue's reproduction: a failing verify, a recorded PR, then a passing verify
            toml = repo.work / ".herd/tasks/t/task.toml"
            toml.write_text(toml.read_text().replace('"true"', '"test -f ok"'))
            assert repo.herd("verify", "t").returncode == 1
            record(repo)
            (repo.work / "ok").touch()
            assert repo.herd("verify", "t").returncode == 0
            print(next(line for line in body(repo).splitlines() if line.startswith("**Result:**")))
        elif word == "example":
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
    if sys.argv[1:] and sys.argv[1] in ("example", "refresh", "refuse-collision", "refuse-bad-milestone"):
        sys.exit(by_hand(sys.argv[1]))
    unittest.main()
