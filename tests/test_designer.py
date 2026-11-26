"""Design on a stronger model than the builder, with a "be specific" second look before the attacks (issue #102).
Session logs are written by hand, in the layout of spike S3; no model runs."""
import itertools
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests.test_herd_cli import git, run_herd

BRIEF = ("Challenge your own understanding of the request and its business context: do not assume you already know "
         "everything. Write ANSWERS.md, saying what you first assumed and what you decided after thinking it through. "
         "Be specific: every success criterion you propose and every input form must state exactly what the program "
         "accepts, what it does with it and what it refuses, so that no choice is left unstated. Then update your Herd "
         "task to match your decisions (the human's criteria stay word for word), write your attacks and run herd "
         "verify.")
TASK = '''goal = "Add a greeting"
test_budget = "one check"
known_limits = "none known"
inputs = []

[[criteria]]
id = "C1"
text = "it greets"
source = "agent-proposed"
check = "test -f greet.txt"
'''
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
PAST = "2000-01-01T00:00:00Z"


def line(model, at=PAST, **kw):
    return json.dumps({"type": "assistant", "timestamp": at, "message": {"model": model}, **kw})


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root, self.logs = Path(tmp.name) / "repo", Path(tmp.name) / "logs"
        self.root.mkdir()
        self.logs.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        self.main = self.logs / "s1.jsonl"

    def session(self, *models, command="herd.py status"):
        """The main session log, and the pre-init hook seeing a herd command in that session."""
        self.main.write_text("".join(line(m) + "\n" for m in models))
        herd.preinit({"cwd": str(self.root), "transcript_path": str(self.main),
                      "tool_input": {"command": f"python3 {command}"}})

    def init(self, toml=None, task=TASK, slug="t1"):
        if toml is not None:
            (self.root / "herd.toml").write_text(toml)
        herd.init_task(self.root, slug, "Add a greeting")
        self.dir = self.root / ".herd/tasks" / slug
        (self.dir / "task.toml").write_text(task)

    def answers(self, text="I assumed x; I decided y."):
        (self.dir / "ANSWERS.md").write_text(text)

    def stop(self, *models, raw=None, agent="herd:herd-designer", agent_id="a1", **extra):
        path = self.logs / "s1" / "subagents" / f"agent-{agent_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw if raw is not None else "".join(line(m, isSidechain=True) + "\n" for m in models))
        hook = {"cwd": str(self.root), "agent_type": agent, "agent_id": agent_id,
                "transcript_path": str(self.main), "agent_transcript_path": str(path), **extra}
        return run_herd(self.root, "design-hook", input=json.dumps(hook))

    def record(self):
        path = self.dir / "design.json"
        return json.loads(path.read_text()) if path.exists() else None

    def status(self):
        p = run_herd(self.root, "status")
        return p.stdout

    def problems(self):
        return herd.design_problems(self.root, "t1")


class Models(Repo):
    def test_models_default_and_override(self):
        self.init()
        self.assertIn("Models: design sonnet, build haiku", self.status())
        self.assertEqual(herd.task_models(self.root, "t1"), {"design": "sonnet", "build": "haiku"})

    def test_models_default_and_override_by_herd_toml(self):
        (self.root / "herd.toml").write_text('[models]\ndesign = "opus"\nbuild = "claude-sonnet-5-5"\n')
        before = run_herd(self.root, "status")  # no task yet: the models still print, and that is not an error
        self.assertIn("Models: design opus, build claude-sonnet-5-5", before.stdout)
        self.assertEqual(before.returncode, 0)
        self.init()
        (self.root / "herd.toml").write_text('[models]\ndesign = "haiku"\n')  # an edit during the task: no effect
        self.assertIn("Models: design opus, build claude-sonnet-5-5", self.status())

    def test_models_default_and_override_of_one_key(self):
        self.init('[models]\nbuild = "opus"\n')
        self.assertIn("Models: design sonnet, build opus", self.status())

    def test_bad_input_models_table(self):
        for toml in ('models = 3\n', '[models]\ndesign = ""\n', '[models]\nbuild = ["haiku"]\n',
                     '[models]\ndesing = "opus"\n', "[models\n"):
            with self.subTest(toml=toml):
                (self.root / "herd.toml").write_text(toml)
                for args in (["status"], ["init", "t9", "goal"]):
                    p = run_herd(self.root, *args)
                    self.assertEqual(p.returncode, 1, p.stdout)
                    self.assertIn("herd.toml", p.stderr)
                    self.assertNotIn("Traceback", p.stderr)
                self.assertFalse((self.root / ".herd/tasks/t9").exists())

    def test_one_bad_part_value_is_never_replaced_by_the_default(self):
        (self.root / "herd.toml").write_text('[models]\ndesign = "opus"\nbuild = 3\n')
        with self.assertRaisesRegex(ValueError, "build"):
            herd.read_models(self.root)

    def test_one_bad_part_log_lines_are_skipped(self):
        self.main.write_text("not json\n[1]\n" + line("<synthetic>") + "\n" + line(SONNET) + "\n"
                             + line(HAIKU, isSidechain=True) + "\n{\"type\": \"assistant\"}\n")
        self.assertEqual(herd.log_models(self.main), [SONNET])

    def test_collision_a_setting_given_twice(self):
        (self.root / "herd.toml").write_text('[models]\ndesign = "sonnet"\ndesign = "haiku"\n')
        with self.assertRaises(ValueError):
            herd.read_models(self.root)


class Routing(Repo):
    def test_build_model_routing_here_when_the_session_matches(self):
        self.session(HAIKU)
        self.init()
        out = self.status()
        self.assertIn("Design: spawn herd:herd-designer with model sonnet", out)
        self.assertIn("Build: here, in this session", out)
        self.assertNotIn("herd-builder", out)

    def test_build_model_routing_spawns_a_builder_otherwise(self):
        self.session(OPUS)
        self.init()
        out = self.status()
        self.assertIn("Build: spawn herd:herd-builder with model haiku", out)
        self.assertIn("Design: spawn herd:herd-designer with model sonnet", out)

    def test_build_model_routing_before_init(self):
        self.session(HAIKU)
        p = run_herd(self.root, "status")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Build: here, in this session", p.stdout)
        self.assertIn("no active task", p.stdout)

    def test_build_model_routing_unknown_session(self):
        self.init()
        out = self.status()
        self.assertIn("spawn herd:herd-designer with model sonnet", out)
        self.assertIn("unless your model is haiku", out)

    def test_build_model_routing_follows_the_latest_model(self):
        self.session(HAIKU, SONNET)
        self.init()
        self.assertIn("Build: spawn herd:herd-builder", self.status())

    def test_other_reading_tier_full_id_or_capitals(self):
        for setting in ("sonnet", "Sonnet", SONNET, " sonnet "):
            with self.subTest(setting=setting):
                self.assertTrue(herd.model_matches(setting, SONNET))
                self.assertFalse(herd.model_matches(setting, HAIKU))
        self.assertTrue(herd.model_matches(SONNET, SONNET + "-20260101"))
        self.assertFalse(herd.model_matches("sonnet", None))


class Brief(Repo):
    def test_brief_is_the_measured_text(self):
        self.init()
        p = run_herd(self.root, "design-brief")
        self.assertEqual((p.returncode, p.stdout), (0, BRIEF + "\n"), p.stderr)

    def test_brief_needs_no_task(self):
        self.assertEqual(run_herd(self.root, "design-brief").stdout, BRIEF + "\n")

    def test_bad_input_brief_with_an_argument(self):
        p = run_herd(self.root, "design-brief", "--nope")
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)


class Hook(Repo):
    def test_hook_records_model_answers_and_fingerprint(self):
        self.session(HAIKU)
        self.init()
        self.answers()
        p = self.stop(SONNET)
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
        rec = self.record()
        self.assertEqual((rec["model"], rec["design"], rec["matches"], rec["answers"]), (SONNET, "sonnet", True, True))
        self.assertEqual(rec["fingerprint"], herd.design_fingerprint(self.root, "t1"))

    def test_hook_records_a_wrong_model_and_no_answers(self):
        self.init()
        self.stop(SONNET, HAIKU)
        rec = self.record()
        self.assertEqual((rec["model"], rec["matches"], rec["answers"]), (HAIKU, False, False))

    def test_hook_records_fingerprint_changes_with_criteria_and_attacks(self):
        self.init()
        first = herd.design_fingerprint(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "n/a: none", attack="recount")
        second = herd.design_fingerprint(self.root, "t1")
        (self.dir / "task.toml").write_text(TASK.replace("it greets", "it waves"))
        self.assertEqual(len({first, second, herd.design_fingerprint(self.root, "t1")}), 3)

    def test_hook_records_nothing_for_other_agents(self):
        self.init()
        for agent in ("herd-designer", "herd:herd-builder", None):
            self.stop(SONNET, agent=agent)
        self.assertIsNone(self.record())

    def test_hook_records_in_the_worktree_task_of_this_session(self):
        self.session(HAIKU, command="herd.py init t2 goal --worktree")
        path, _, _ = herd.init_worktree(self.root, "t2", "goal")
        self.stop(SONNET)
        self.assertTrue((path / ".herd/tasks/t2/design.json").exists())

    def test_collision_two_designer_stops_the_latest_counts(self):
        self.init()
        self.answers()
        self.stop(HAIKU, agent_id="a1")
        self.stop(SONNET, agent_id="a2")
        self.assertEqual(self.record()["model"], SONNET)
        self.assertEqual(self.problems(), [])
        self.stop(HAIKU, agent_id="a3")
        self.assertTrue(self.problems())

    def test_bad_input_hook(self):
        self.init()
        for raw in ("", "nonsense", "[1]", "{}", json.dumps({"agent_type": "herd:herd-designer"})):
            with self.subTest(raw=raw):
                p = run_herd(self.root, "design-hook", input=raw)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertNotIn("Traceback", p.stderr)

    def test_bad_input_hook_logs(self):
        self.init()
        self.answers()
        for extra in ({"agent_transcript_path": str(self.logs / "none.jsonl")}, {"agent_transcript_path": 3},
                      {"transcript_path": None}):
            with self.subTest(extra=extra):
                p = self.stop(SONNET, **extra)
                self.assertEqual((p.returncode, "Traceback" in p.stderr), (0, False), p.stderr)
                self.assertEqual((self.record()["model"], self.record()["matches"]), (None, False))
        self.stop(raw="garbage\n")
        self.assertFalse(self.record()["matches"])
        (self.dir / "design.json").write_text("{half")
        self.assertTrue(self.problems())

    def test_recount_model_from_the_log(self):
        rng = random.Random(102)
        self.init()
        self.answers()
        for _ in range(40):
            models = [rng.choice([HAIKU, SONNET, OPUS]) for _ in range(rng.randrange(1, 5))]
            self.stop(*models)
            rec = self.record()
            self.assertEqual(rec["model"], models[-1])
            self.assertEqual(rec["matches"], all("sonnet" in m for m in models), models)
            self.assertEqual(herd.design_line(self.root, "t1").split()[1].rstrip(","), models[-1])


class Done(Repo):
    def verify(self):
        return run_herd(self.root, "verify")

    def attacks(self):
        for name in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", "n/a: nothing to attack", attack=name)

    def done(self):
        (self.root / "greet.txt").write_text("hi")
        run_herd(self.root, "note", "--late-red", "test")
        self.verify()
        return run_herd(self.root, "done")

    def test_answers_before_red(self):
        self.init()
        self.attacks()
        p = self.verify()
        self.assertEqual(p.returncode, 1)
        self.assertIn("ANSWERS.md", p.stderr)
        self.assertIn("design-brief", p.stderr)
        self.assertEqual([f for f in ("red.json", "evidence.json", "frozen.json") if (self.dir / f).exists()], [])
        self.answers("  \n")
        self.assertIn("ANSWERS.md", self.verify().stderr)
        self.answers()
        self.verify()
        self.assertTrue((self.dir / "red.json").exists())

    def test_answers_before_red_not_on_the_quick_route(self):
        herd.init_task(self.root, "t1", "Add a greeting", quick_check="test -f greet.txt")
        self.verify()
        self.assertTrue((self.root / ".herd/tasks/t1/red.json").exists())

    def test_done_requires_design(self):
        self.session(HAIKU)
        self.init()
        self.attacks()
        self.answers()
        self.verify()
        p = self.done()
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("herd:herd-designer with model sonnet", p.stderr)
        self.stop(HAIKU)
        self.assertIn(HAIKU, run_herd(self.root, "done").stderr)
        self.stop(SONNET)
        (self.dir / "ANSWERS.md").unlink()
        self.assertIn("ANSWERS.md", run_herd(self.root, "done").stderr)
        self.answers()
        p = run_herd(self.root, "done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"Design: {SONNET}", (self.dir / "evidence.md").read_text())

    def test_done_requires_design_with_answers_when_the_designer_stopped(self):
        self.init()
        self.stop(SONNET)
        self.answers()
        self.assertIn("ANSWERS.md", " ".join(self.problems()))

    def test_done_requires_design_not_on_the_quick_route(self):
        herd.init_task(self.root, "t1", "Add a greeting", quick_check="test -f greet.txt")
        self.verify()
        p = self.done()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Design:", p.stdout)

    def test_done_requires_design_not_for_a_task_from_before(self):
        self.init()
        start = json.loads((self.dir / "start.json").read_text())
        del start["models"]
        (self.dir / "start.json").write_text(json.dumps(start))
        self.assertEqual(self.problems(), [])

    def test_same_model_ok(self):
        self.session(SONNET)
        self.init()
        self.attacks()
        self.answers()
        self.verify()
        self.assertIn("Design: here, in this session", self.status())
        p = self.done()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIsNone(self.record())

    def test_same_model_ok_needs_answers(self):
        self.session(SONNET)
        self.init()
        self.assertIn("ANSWERS.md", " ".join(self.problems()))

    def test_same_model_ok_only_for_the_design_itself(self):
        """The model that counts is the one that worked before red, not one switched to afterwards."""
        self.session(HAIKU)
        self.init()
        self.attacks()
        self.answers()
        self.verify()
        red = json.loads((self.dir / "red.json").read_text())
        self.main.write_text(line(HAIKU, at=red["at"]) + "\n" + line(SONNET, at="2999-12-31T00:00:00Z") + "\n")
        self.assertTrue(self.problems())

    def test_refusal_matches_a_plain_rule(self):
        """Every combination of setting, designer model, session model and ANSWERS.md, judged by a substring rule: a
        designer that ran decides, otherwise the session's own model."""
        settings, models = ("haiku", "sonnet", "opus"), (None, HAIKU, SONNET, OPUS)
        template = None
        for setting, designer, main, answers in itertools.product(settings, models, models, (True, False)):
            with self.subTest(setting=setting, designer=designer, main=main, answers=answers):
                shutil.rmtree(self.root / ".herd", ignore_errors=True)
                shutil.rmtree(self.logs / "s1", ignore_errors=True)
                self.main.unlink(missing_ok=True)
                (self.root / ".git" / herd.SESSION_FILE).unlink(missing_ok=True)
                if main:
                    self.session(main)
                if template is None:
                    self.init(f'[models]\ndesign = "{setting}"\n')
                    template = True
                else:
                    (self.root / "herd.toml").write_text(f'[models]\ndesign = "{setting}"\n')
                    herd.init_task(self.root, "t1", "Add a greeting")
                if answers:
                    self.answers()
                if designer:
                    self.stop(designer)
                served = answers and (setting in designer if designer else bool(main) and setting in main)
                self.assertEqual(not self.problems(), served, self.problems())


class Guard(Repo):
    def test_bad_input_guard_protects_the_design_record(self):
        self.init()
        for tool, inp in (("Write", {"file_path": str(self.dir / "design.json")}),
                          ("Bash", {"command": "python3 scripts/herd.py design-hook < x.json"})):
            out = herd.guard(self.root, {"tool_name": tool, "tool_input": inp, "cwd": str(self.root)})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


class Plugin(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent / "plugin"

    def test_hook_records_is_wired(self):
        hooks = json.loads((self.ROOT / "hooks/hooks.json").read_text())["hooks"]
        entry = hooks["SubagentStop"][0]
        self.assertEqual(entry["matcher"], "^herd:herd-designer$")
        self.assertIn("design-hook", entry["hooks"][0]["command"])

    def test_build_model_routing_agents_exist(self):
        for name in ("herd-designer", "herd-builder"):
            self.assertIn(f"name: {name}\n", (self.ROOT / "agents" / f"{name}.md").read_text())


if __name__ == "__main__":
    unittest.main()
