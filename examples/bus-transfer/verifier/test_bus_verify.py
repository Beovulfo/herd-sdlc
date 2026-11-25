"""Tests for the bus-transfer verifier: the reference solver, two wrong solvers, the generators, the probe."""
import contextlib
import functools
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "supermarket-route" / "verifier"))
import bus_probe as bp  # noqa: E402
import bus_reference as br  # noqa: E402
import bus_verify as bv  # noqa: E402
import run_leg  # noqa: E402

M = bv.MIN_CHANGE
FULL = os.environ.get("BUS_FULL") == "1"  # CI sets it: XL networks are too slow for every local check
LARGE = ("L", "XL") if FULL else ("L",)

# Each generated network is built once per test process (key: family, size, seed). Tests must not change it.
build_case = bv.make_case
bv.make_case = functools.cache(build_case)


def verify(adapter, *extra, project=None):
    """bus_verify's main in this process, so it reuses the cached networks; adapters still run in their own."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = bv.main([adapter, str(project or HERE), *extra])
    return rc, out.getvalue(), err.getvalue()


def rows_of(adapter, *extra):
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "rows.json"
        rc, stdout, err = verify(adapter, "--json", str(out), *extra)
        return rc, stdout, json.loads(out.read_text()) if out.exists() else None


def plain_earliest(canon, q, m=None):
    """Earliest arrival by plain repeated passes over every trip until nothing improves. Separate from both solvers."""
    m = canon["min_change"] if m is None else m
    a, b = q["from"], q["to"]
    if a == b:
        return q["depart"]
    ready, best = {a: q["depart"]}, {}
    changed = True
    while changed:
        changed = False
        for t in canon["trips"]:
            riding = False
            for stop, arr, dep in t["times"]:
                if riding and arr < best.get(stop, 10 ** 9):
                    best[stop], changed = arr, True
                if riding and arr + m < ready.get(stop, 10 ** 9):
                    ready[stop], changed = arr + m, True
                if ready.get(stop, 10 ** 9) <= dep:
                    riding = True
    return best.get(b)


def rides_as_hops(canon, answer):
    """The same journey with one leg per stop-to-stop hop."""
    trips = {t["id"]: t for t in canon["trips"]}
    out = []
    for leg in answer["legs"]:
        times = trips[leg["trip"]]["times"]
        stops = [x[0] for x in times]
        i, j = stops.index(leg["from"]), stops.index(leg["to"])
        out += [{"trip": leg["trip"], "from": times[k][0], "dep": times[k][2], "to": times[k + 1][0],
                 "arr": times[k + 1][1]} for k in range(i, j)]
    return {**answer, "legs": out}


def small_cases():
    return bv.make_cases(["S", "M"], bv.FAMILIES, 3)


class TestLayout(unittest.TestCase):
    def test_task_folder_holds_the_promised_files(self):
        for rel in ("prompt.md", "README.md", "verifier/bus_verify.py", "verifier/bus_probe.py", "verifier/bus_reference.py",
                    "verifier/ADAPTER_SPEC.md", "verifier/test_bus_verify.py"):
            self.assertTrue((TASK / rel).is_file(), rel)

    def test_readme_has_method_isolation_and_scoring(self):
        text = (TASK / "README.md").read_text()
        for heading in ("## Method", "## Run isolation", "## How to score"):
            self.assertIn(heading, text)
        for word in ("run_leg.py", "leak_audit.py", "--task bus-transfer", "bus_verify.py", "bus_probe.py"):
            self.assertIn(word, text)
        self.assertNotIn("\u2014", text)

    def test_prompt_is_the_median_persons_wording_and_leaks_nothing(self):
        text = (TASK / "prompt.md").read_text()
        self.assertTrue(text.startswith("build a journey planner for our city buses"))
        for word in ("any network", "very big", "whatever the timetables", "earliest", "where to change", "a few minutes",
                     "fast", "not possible"):
            self.assertIn(word, text)
        for word in ("verifier", "oracle", "benchmark", "minutes since", "GTFS", "HH:MM"):
            self.assertNotIn(word, text)

    def test_hidden_files_are_named_in_run_leg_and_the_reference_is_not_imported_by_runs(self):
        self.assertEqual(run_leg.HIDDEN["bus-transfer"],
                         {"bus_verify.py", "bus_probe.py", "bus_reference.py", "test_bus_verify.py"})
        for f in (TASK / "verifier").glob("*.py"):
            self.assertIn(f.name, run_leg.HIDDEN["bus-transfer"])

    def test_hidden_list_names_this_test_file_so_a_copy_is_refused(self):
        self.assertIn("test_bus_verify.py", run_leg.HIDDEN["bus-transfer"])


class TestSolvers(unittest.TestCase):
    def test_reference_scores_every_case_valid(self):
        rc, out, _ = verify("reference", "--tiers", "S,M", "--seeds", "2")
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        for fam in bv.FAMILIES:
            self.assertIn(f"- {fam}:", out)

    def test_static_dijkstra_fails_the_time_dependent_cases(self):
        rc, out, rows = rows_of("static", "--tiers", "S,M", "--seeds", "2")
        self.assertEqual(rc, 1, out)
        bad = {r["case"] for r in rows if not r["valid"]}
        self.assertIn("S hand static-trap", bad)
        self.assertIn("S hand stay-on-bus", bad)
        self.assertTrue(any(c.split()[1] in ("random", "grid", "radial", "clusters", "overnight") for c in bad), bad)
        self.assertNotIn("S hand wait", bad)  # a static graph still serves a single direct bus

    def test_a_solver_that_ignores_the_change_time_fails_those_cases(self):
        rc, out, rows = rows_of("nochange", "--tiers", "S,M", "--seeds", "2")
        self.assertEqual(rc, 1, out)
        bad = {r["case"]: r["invalid"] for r in rows if not r["valid"]}
        self.assertIn("minimum is 4", bad["S hand tight-change"])
        self.assertIn("S hand static-trap", bad)
        self.assertTrue(any(c.split()[1] != "hand" for c in bad), bad)
        self.assertNotIn("S hand two-changes", bad)  # exactly the minimum is allowed

    def test_each_hand_case_has_the_answer_its_note_says(self):
        want = {"static-trap": [620], "tight-change": [580], "stay-on-bus": [560], "overnight": [1510], "wait": [560],
                "disconnected": [None, 600, None], "overtaking": [580], "two-changes": [580]}
        for c in bv.hand_cases():
            bv.validate_canon(c)
            self.assertEqual([bv.oracle_arrival(c, q) for q in c["queries"]], want[c["seed"]], c["seed"])
            self.assertEqual([br.solve(c, q).get("arrival") for q in c["queries"]], want[c["seed"]], c["seed"])


class TestGenerators(unittest.TestCase):
    def test_every_family_makes_a_valid_deterministic_network_at_each_small_size(self):
        for label, c in small_cases():
            bv.validate_canon(c)
            self.assertTrue(c["queries"], label)
            self.assertTrue(c["trips"], label)
        for fam in bv.FAMILIES[1:]:
            self.assertEqual(build_case(fam, "S", 7000), bv.make_case(fam, "S", 7000))
            self.assertNotEqual(bv.make_case(fam, "M", 7000)["trips"], bv.make_case(fam, "M", 7001)["trips"], fam)

    def test_oracle_reference_and_plain_search_agree_on_every_query(self):
        for label, c in small_cases():
            for q in c["queries"]:
                want = plain_earliest(c, q)
                self.assertEqual(bv.oracle_arrival(c, q), want, (label, q))
                self.assertEqual(br.solve(c, q).get("arrival"), want, (label, q))
                self.assertEqual(br.solve(c, q)["found"], want is not None, (label, q))

    def test_agreement_on_purely_random_networks_the_generators_never_made(self):
        rnd = random.Random("tests only")
        for n in range(120):
            stops = [f"s{i}" for i in range(rnd.randint(2, 9))]
            trips = []
            for k in range(rnd.randint(1, 12)):
                seq = rnd.sample(stops, rnd.randint(2, len(stops)))
                t, times = rnd.randint(0, 200), []
                for s in seq:
                    arr = t
                    dep = arr + rnd.choice((0, 0, 3))
                    times.append([s, arr, dep])
                    t = dep + rnd.randint(1, 15)
                trips.append({"id": f"t{k}", "route": "r", "times": times})
            c = {"stops": [[s, s] for s in stops], "trips": trips, "min_change": rnd.choice((0, 1, 3, 7)), "queries": []}
            bv.validate_canon(c)
            for _ in range(6):
                q = {"from": rnd.choice(stops), "to": rnd.choice(stops), "depart": rnd.randint(0, 250)}
                want = plain_earliest(c, q)
                self.assertEqual(bv.oracle_arrival(c, q), want, (n, q))
                ans = br.solve(c, q)
                self.assertEqual(ans.get("arrival"), want, (n, q))
                bv.validate_answer(c, q, ans, want)

    @unittest.skipUnless(FULL, "XL runs in CI (BUS_FULL=1)")
    def test_the_largest_size_is_big_and_the_oracle_answers_it(self):
        c = bv.make_case("random", "XL", 7000)
        bv.validate_canon(c)
        hops = sum(len(t["times"]) - 1 for t in c["trips"])
        self.assertGreater(len(c["stops"]), 5000)
        self.assertGreater(len(c["trips"]), 20000)
        self.assertGreater(hops, 200000)
        self.assertTrue(any(bv.oracle_arrival(c, q) is not None for q in c["queries"]))

    def test_every_family_stays_big_and_useful_at_the_large_sizes(self):
        for tier in LARGE:
            stops = bv.TIERS[tier][0]
            for fam in bv.FAMILIES[1:]:
                c = bv.make_case(fam, tier, 7000)
                bv.validate_canon(c)
                served = {x[0] for t in c["trips"] for x in t["times"]}
                self.assertGreater(len(served), stops // 2, (tier, fam))
                self.assertGreater(len(c["trips"]), stops, (tier, fam))
                found = sum(bv.oracle_arrival(c, q) is not None for q in c["queries"])
                self.assertGreaterEqual(found, 2, (tier, fam))

    def test_every_size_gets_the_requested_number_of_seeds(self):
        with mock.patch.object(bv, "make_case", lambda family, tier, seed: {}):
            labels = [label for label, _ in bv.make_cases(list(bv.TIERS), ["random"], 2)]
        self.assertEqual(labels, [f"{tier} random seed {n}" for tier in bv.TIERS for n in (0, 1)])

    def test_a_stop_has_one_time_so_a_one_time_timetable_loses_nothing(self):
        for label, c in small_cases():
            for t in c["trips"]:
                self.assertTrue(all(arr == dep for _, arr, dep in t["times"]), (label, t["id"]))


class Probe(unittest.TestCase):
    CLI = textwrap.dedent('''
        import json, re, sys
        def fail(msg):
            print("error: " + msg, file=sys.stderr); sys.exit(1)
        def main(path, a, b, when):
            try:
                net = json.load(open(path))
            except FileNotFoundError:
                fail("no such file " + path)
            except ValueError:
                fail("timetable is not valid JSON")
            if not net["stops"]:
                fail("the network has no stops")
            ids = [s[0] for s in net["stops"]]
            if len(set(ids)) != len(ids):
                fail("duplicate stop id")
            if not re.fullmatch(r"\\d\\d:\\d\\d", when):
                fail("departure must look like 08:30")
            if a not in ids or b not in ids:
                MODE_UNKNOWN
            print("A to C: arrive 09:35")
        main(*sys.argv[1:5])
    ''')
    ADAPTER = textwrap.dedent('''
        def probe(sc, d, bp):
            net = bp.canon(sc)
            f = d / "net.json"
            f.write_text(bp.MALFORMED if sc == "malformed_timetable" else bp.j(net))
            a, b, when = bp.query(sc)
            return ["cli.py", str(d / "absent.json" if sc == "missing_file" else f), a, b, when]
    ''')

    def project(self, unknown='fail("unknown stop")'):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        (root / "cli.py").write_text(self.CLI.replace("MODE_UNKNOWN", unknown))
        (root / "adapter.py").write_text(self.ADAPTER)
        return root, bp.load_adapter("fake", root / "adapter.py")


class TestProbe(Probe):
    def test_a_clean_cli_handles_all_six_bad_inputs(self):
        root, mod = self.project()
        res = bp.run_probe(root, mod)
        self.assertEqual(res, ["ok"] + ["clean error"] * 6)
        self.assertEqual(bp.handled(res), 6)

    def test_traceback_silent_success_and_hang_are_not_handled(self):
        root, mod = self.project(unknown="raise KeyError(b)")
        res = bp.run_probe(root, mod)
        self.assertEqual(res[bp.SCENARIOS.index("unknown_stop")], "CRASH")
        self.assertEqual(bp.handled(res), 5)
        root, mod = self.project(unknown="print('no such stop')")
        self.assertEqual(bp.run_probe(root, mod)[bp.SCENARIOS.index("unknown_stop")], "silent")
        root, mod = self.project()
        (root / "cli.py").write_text("import sys\nprint('journey')\n")
        res = bp.run_probe(root, mod)
        self.assertEqual(bp.handled(res), 0)
        self.assertEqual(set(res[1:]), {"silent"})
        (root / "cli.py").write_text("import time\ntime.sleep(30)\n")
        self.assertEqual(set(bp.run_probe(root, mod, timeout=1)), {"HANG"})

    def test_a_cli_that_fails_every_input_handles_nothing(self):
        root, mod = self.project()
        (root / "cli.py").write_text("import sys\nsys.exit('error: always')\n")
        res = bp.run_probe(root, mod)
        self.assertEqual(res, ["FAILS"] + ["clean error"] * 6)
        self.assertEqual(bp.handled(res), 0)

    def test_non_utf8_output_is_a_failed_scenario_not_an_abort(self):
        root, mod = self.project()
        (root / "cli.py").write_text("import sys\nsys.stdout.buffer.write(b'caf\\xe9')\n")
        res = bp.run_probe(root, mod)
        self.assertEqual(res, ["FAILS"] + ["garbled"] * 6)
        self.assertEqual(bp.handled(res), 0)
        root, mod = self.project(unknown="sys.stderr.buffer.write(b'caf\\xe9'); sys.exit(1)")
        res = bp.run_probe(root, mod)
        self.assertEqual(res[bp.SCENARIOS.index("unknown_stop")], "garbled")
        self.assertEqual(bp.handled(res), 5)

    def test_the_probe_scenarios_are_the_six_bad_inputs_of_the_issue(self):
        self.assertEqual(bp.BAD, ["missing_file", "malformed_timetable", "unknown_stop", "empty_network",
                                  "bad_departure", "duplicate_stop_ids"])
        self.assertEqual(bp.canon("empty_network")["stops"], [])
        ids = [s[0] for s in bp.canon("duplicate_stop_ids")["stops"]]
        self.assertEqual(len(ids) - len(set(ids)), 1)
        self.assertEqual(bp.query("bad_departure")[2], "half past eight")
        self.assertEqual(bp.query("unknown_stop")[1], "Z9")


class TestBadInput(unittest.TestCase):
    def test_the_command_line_itself_refuses_in_one_line(self):
        p = subprocess.run([sys.executable, str(HERE / "bus_verify.py"), "nope", str(HERE)], capture_output=True, text=True)
        self.assertEqual((p.returncode, len(p.stderr.strip().splitlines())), (2, 1), p.stderr)

    def test_a_selection_with_no_cases_is_never_a_pass(self):
        rc, out, err = verify("reference", "--tiers", "M", "--families", "hand")
        self.assertEqual(rc, 2, out)
        self.assertIn("no cases ran", err)
        self.assertNotIn("PASS", out)

    def test_verifier_arguments_end_in_one_clear_line_and_exit_2(self):
        for extra, adapter, project in ((["--tiers", "Q"], "reference", HERE), (["--families", "zig"], "reference", HERE),
                                        (["--seeds", "0"], "reference", HERE), (["--limit-scale", "-1"], "reference", HERE),
                                        ([], "reference", HERE / "absent"), ([], "file:" + str(HERE / "absent.py"), HERE),
                                        ([], "nope", HERE)):
            rc, out, err = verify(adapter, *extra, project=project)
            self.assertEqual(rc, 2, (extra, adapter, project))
            self.assertEqual(len(err.strip().splitlines()), 1, err)
            self.assertNotIn("Traceback", err)

    def test_garbage_results_are_a_reason_never_an_exception(self):
        c = bv.hand_cases()[2]
        for result in (None, [], {}, {"answers": None}, {"answers": []}, {"answers": [None]}, {"answers": [{}]},
                       {"answers": [{"found": True}]}, {"answers": [{"found": True, "legs": [{}], "arrival": 1}]},
                       {"answers": [{"found": True, "arrival": "x", "legs": [{"trip": 3, "from": 1}]}]},
                       {"answers": [{"found": "yes"}]}, [1], "answers", 7,
                       {"answers": [{"found": True, "arrival": 1, "legs": "xy"}]},
                       {"answers": [{"found": True, "arrival": 1, "legs": [[["trip", "X.0"]]]}]},
                       {"answers": [{"found": True, "arrival": 1, "legs": 5}]}):
            self.assertIsInstance(bv.check_case(c, result), str, result)

    def test_a_bad_canon_is_refused_by_name(self):
        c = bv.hand_cases()[2]
        for edit in (lambda x: x["stops"].append(["A", "again"]), lambda x: x["trips"].append(dict(x["trips"][0])),
                     lambda x: x["trips"][0]["times"].append(["A", 570, 570]),
                     lambda x: x["trips"][0]["times"].append(["Q", 570, 570]),
                     lambda x: x["trips"][0]["times"].__setitem__(1, ["B", 530, 530])):
            bad = json.loads(json.dumps(c))
            edit(bad)
            with self.assertRaises(ValueError):
                bv.validate_canon(bad)

    def test_probe_runner_arguments(self):
        for arg in ("nonsense", "x=y", "x=" + str(HERE) + ":absent.py", "=" + str(HERE) + ":bus_probe.py"):
            p = subprocess.run([sys.executable, str(HERE / "bus_probe.py"), arg], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, arg)
            self.assertNotIn("Traceback", p.stderr)


def adapter_file(directory, body):
    f = Path(directory) / "adapter.py"
    f.write_text("import sys\nsys.path.insert(0, %r)\nimport bus_reference as br\n" % str(HERE) + textwrap.dedent(body))
    return "file:" + str(f)


REFERENCE_BODY = '''
    def worker(project, canon):
        %s
        return {"answers": [br.solve(canon, q) for q in canon["queries"]]}
'''


class TestCollision(unittest.TestCase):
    def test_two_trips_leaving_together_and_two_identical_queries_are_both_served(self):
        c = bv._hand("tie", {"X.0": [("A", 540, 540), ("B", 550, 550)], "Y.0": [("A", 540, 540), ("B", 550, 550)]},
                     [{"from": "A", "to": "B", "depart": 540}] * 2)
        bv.validate_canon(c)
        self.assertEqual([plain_earliest(c, q) for q in c["queries"]], [550, 550])
        self.assertIsNone(bv.check_case(c, {"answers": [br.solve(c, q) for q in c["queries"]]}))
        self.assertEqual(bv.check_case(c, {"answers": [br.solve(c, c["queries"][0])]}), "wrong number of answers")

    def test_a_leg_naming_the_other_of_two_look_alike_trips_is_checked_against_that_trip(self):
        c = bv._hand("alike", {"X.0": [("A", 540, 540), ("B", 550, 550)], "Y.0": [("A", 541, 541), ("B", 550, 550)]},
                     [{"from": "A", "to": "B", "depart": 540}])
        q = c["queries"][0]
        good = {"found": True, "arrival": 550, "legs": [{"trip": "X.0", "from": "A", "dep": 540, "to": "B", "arr": 550}]}
        bv.validate_answer(c, q, good, 550)
        wrong = {**good, "legs": [{"trip": "Y.0", "from": "A", "dep": 540, "to": "B", "arr": 550}]}
        with self.assertRaises(AssertionError):
            bv.validate_answer(c, q, wrong, 550)

    def test_duplicate_ids_in_a_network_are_refused_not_merged(self):
        c = bv.hand_cases()[2]
        c["stops"].append(["B", "second B"])
        with self.assertRaises(ValueError):
            bv.validate_canon(c)


class TestOneBadPart(unittest.TestCase):
    def test_non_utf8_output_costs_only_its_case(self):
        body = '''
            def worker(project, canon):
                if canon["family"] == "grid":
                    sys.stdout.buffer.write(b"caf\\xe9")
                if canon["family"] == "radial":
                    sys.stderr.buffer.write(b"caf\\xe9")
                return {"answers": [br.solve(canon, q) for q in canon["queries"]]}
        '''
        with tempfile.TemporaryDirectory() as t:
            rc, out, rows = rows_of(adapter_file(t, body), "--tiers", "S", "--seeds", "1",
                                    "--families", "grid,radial,random")
        self.assertEqual(rc, 1, out)
        self.assertEqual({r["family"]: r["valid"] for r in rows}, {"grid": False, "radial": False, "random": True})
        self.assertEqual({r["status"] for r in rows if not r["valid"]}, {"bad output: not UTF-8"})
        self.assertIn("CASES valid 1 of 3", out)

    def test_one_crashing_family_costs_only_its_cases(self):
        with tempfile.TemporaryDirectory() as t:
            ad = adapter_file(t, REFERENCE_BODY % 'assert canon["family"] != "grid", "boom"')
            rc, out, rows = rows_of(ad, "--tiers", "S", "--seeds", "2")
        self.assertEqual(rc, 1, out)
        bad = [r for r in rows if not r["valid"]]
        self.assertEqual({r["family"] for r in bad}, {"grid"})
        self.assertTrue(all(r["status"].startswith("crash") for r in bad))
        self.assertEqual(sum(r["valid"] for r in rows), len(rows) - len(bad))
        self.assertGreater(len(rows) - len(bad), 8)

    def test_one_wrong_query_makes_that_case_invalid_and_no_other(self):
        body = '''
            def worker(project, canon):
                out = [br.solve(canon, q) for q in canon["queries"]]
                if canon["family"] == "radial" and canon["seed"] == 7000:
                    out[1] = {"found": False}
                return {"answers": out}
        '''
        with tempfile.TemporaryDirectory() as t:
            rc, out, rows = rows_of(adapter_file(t, body), "--tiers", "S", "--seeds", "2", "--families", "radial,random")
        self.assertEqual([r["case"] for r in rows if not r["valid"]], ["S radial seed 0"])
        self.assertIn("query 1", [r for r in rows if not r["valid"]][0]["invalid"])

    def test_a_case_over_the_time_limit_is_a_timeout_and_the_rest_still_run(self):
        body = '''
            import time
            def worker(project, canon):
                if canon["family"] == "random":
                    time.sleep(10)
                return {"answers": [br.solve(canon, q) for q in canon["queries"]]}
        '''
        with tempfile.TemporaryDirectory() as t:
            rc, out, rows = rows_of(adapter_file(t, body), "--tiers", "S", "--seeds", "1", "--families", "random,radial",
                                    "--limit-scale", "0.1")
        self.assertEqual({r["family"]: r["status"] for r in rows}, {"random": "timeout", "radial": "ok"})
        self.assertTrue([r for r in rows if r["family"] == "radial"][0]["valid"])


class TestRecount(unittest.TestCase):
    def test_summary_numbers_equal_a_recount_from_the_rows(self):
        body = '''
            def worker(project, canon):
                out = [br.solve(canon, q) for q in canon["queries"]]
                if canon["family"] in ("grid", "overnight"):
                    out[0] = {"found": False}
                return {"answers": out}
        '''
        with tempfile.TemporaryDirectory() as t:
            rc, out, rows = rows_of(adapter_file(t, body), "--tiers", "S,M", "--seeds", "2")
        valid = [r for r in rows if r["status"] == "ok" and r["invalid"] is None]
        self.assertIn(f"CASES valid {len(valid)} of {len(rows)}", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("! ")), len(rows) - len(valid))
        for tier in ("S", "M"):
            rs = [r for r in rows if r["tier"] == tier]
            self.assertIn(f"| {tier} | {len(rs)} | {len(rs)} of {len(rs)} | {sum(r['valid'] for r in rs)} of {len(rs)} |", out)
        self.assertIn("RESULT: FAIL", out)

    def test_every_reference_journey_recounts_from_the_timetable(self):
        for label, c in small_cases():
            trips = {t["id"]: {s: (a, d) for s, a, d in t["times"]} for t in c["trips"]}
            for q in c["queries"]:
                ans = br.solve(c, q)
                if not ans["found"]:
                    continue
                legs = ans["legs"]
                if not legs:
                    self.assertEqual((ans["arrival"], q["from"]), (q["depart"], q["to"]))
                    continue
                self.assertEqual(ans["arrival"], trips[legs[-1]["trip"]][legs[-1]["to"]][0], label)
                self.assertGreaterEqual(trips[legs[0]["trip"]][legs[0]["from"]][1], q["depart"], label)
                for a, b in zip(legs, legs[1:]):
                    arrive = trips[a["trip"]][a["to"]][0]
                    leave = trips[b["trip"]][b["from"]][1]
                    self.assertGreaterEqual(leave - arrive, c["min_change"], (label, q))


class TestRefusal(unittest.TestCase):
    def test_every_not_possible_is_confirmed_by_plain_search_and_nothing_servable_is_refused(self):
        refused = served = 0
        for label, c in small_cases():
            for q in c["queries"]:
                ans = br.solve(c, q)
                want = plain_earliest(c, q)
                self.assertEqual(ans["found"], want is not None, (label, q))
                refused += not ans["found"]
                served += ans["found"]
                if not ans["found"]:
                    self.assertFalse(bv.static_reachable(c, q["from"], q["to"]), (label, q))
        self.assertGreater(refused, 5)
        self.assertGreater(served, 50)

    def test_the_verifier_rejects_a_wrong_refusal_and_a_made_up_journey(self):
        c = bv.hand_cases()[2]
        q = c["queries"][0]
        with self.assertRaisesRegex(AssertionError, "said not possible"):
            bv.validate_answer(c, q, {"found": False}, 560)
        d = bv.hand_cases()[5]
        with self.assertRaisesRegex(AssertionError, "none is possible"):
            bv.validate_answer(d, d["queries"][0], br.solve(c, q), None)
        bv.validate_answer(d, d["queries"][0], {"found": False}, None)


class TestOtherReading(unittest.TestCase):
    def test_a_journey_reported_per_ride_or_per_hop_is_judged_the_same(self):
        checked = 0
        for label, c in small_cases():
            for q in c["queries"]:
                ans = br.solve(c, q)
                if ans["found"] and ans["legs"]:
                    want = bv.oracle_arrival(c, q)
                    bv.validate_answer(c, q, ans, want)
                    bv.validate_answer(c, q, rides_as_hops(c, ans), want)
                    checked += 1
        self.assertGreater(checked, 50)
        c = bv.hand_cases()[2]
        hops = rides_as_hops(c, br.solve(c, c["queries"][0]))
        self.assertEqual(len(hops["legs"]), 2)
        hops["legs"][1]["trip"] = "Q.9"
        with self.assertRaises(AssertionError):
            bv.validate_answer(c, c["queries"][0], hops, 560)

    def test_a_made_up_intermediate_hop_is_rejected_before_hops_are_merged(self):
        c = bv.hand_cases()[2]
        q = c["queries"][0]
        good = rides_as_hops(c, br.solve(c, q))
        for index, key, value in ((0, "to", "NOPE"), (0, "arr", 1), (1, "dep", 2), (1, "from", "NOPE"), (0, "arr", 549)):
            bad = json.loads(json.dumps(good))
            bad["legs"][index][key] = value
            if key == "to":
                bad["legs"][1]["from"] = value
            self.assertIsInstance(bv.check_case(c, {"answers": [bad]}), str, (index, key, value))
        self.assertIsNone(bv.check_case(c, {"answers": [good]}))

    def test_change_time_readings_staying_on_the_bus_and_exactly_the_minimum(self):
        stay, tight, two = bv.hand_cases()[2], bv.hand_cases()[1], bv.hand_cases()[7]
        for c in (stay, two):
            self.assertIsNone(bv.check_case(c, {"answers": [br.solve(c, q) for q in c["queries"]]}))
        late = {"found": True, "arrival": 560, "legs": [
            {"trip": "X.0", "from": "A", "dep": 540, "to": "B", "arr": 550}, {"trip": "Y.0", "from": "B", "dep": 552, "to": "C", "arr": 560}]}
        with self.assertRaisesRegex(AssertionError, "takes 2 minutes"):
            bv.validate_answer(tight, tight["queries"][0], late, 560)

    def test_leaving_exactly_at_the_departure_time_and_times_past_midnight(self):
        c = bv.hand_cases()[0]
        q = {"from": "A", "to": "B", "depart": 540}
        self.assertEqual(bv.oracle_arrival(c, q), 620)
        self.assertEqual(bv.oracle_arrival(c, {**q, "depart": 541}), 620)
        self.assertIsNone(bv.oracle_arrival(c, {**q, "depart": 561}))
        night = bv.hand_cases()[3]
        self.assertEqual(br.solve(night, night["queries"][0])["arrival"], 1510)

    def test_the_two_readings_of_a_late_departure_never_differ_in_generated_cases(self):
        # a timetable that repeats daily would answer a "last bus has gone" query next day; no query depends on that
        for label, c in small_cases():
            for q in c["queries"]:
                if bv.oracle_arrival(c, q) is None:
                    self.assertFalse(bv.static_reachable(c, q["from"], q["to"]), (label, q))


if __name__ == "__main__":
    unittest.main()
