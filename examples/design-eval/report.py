#!/usr/bin/env python3
"""One ROI row per arm of a labelled design eval. Raw numbers and no verdict: the owner decides.

  python3 report.py [RESULTS] [--case TASK]

RESULTS holds TASK/ARM/run-N/run.json and, after judge.py, TASK/ARM/run-N/{before,after}/label.json.
Without RESULTS, the newest results under $TMPDIR/design-eval (run_eval.py's default root) are read.
Only runs with status "ok" and both labels are counted; the rest are listed by reason, never silently dropped.
"""
import argparse
import math
import os
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

import armfile
import judge

PARTS = ("first", "challenger", "resume")


def read_run(run_dir, case):
    """("ok", before label, after label) for a counted run, else (reason, None, None)."""
    status = judge.read_json(run_dir / "run.json").get("status")
    if not isinstance(status, str):
        raise judge.Refused(f"{run_dir}/run.json has no status")
    if status != "ok":
        return status, None, None
    ids = [x["id"] for x in case["labels"]]
    labels = []
    for when in ("before", "after"):
        path = run_dir / when / "label.json"
        if not path.is_file():
            raise judge.Refused(f"{path} is missing: run judge.py on the results first")
        label = judge.read_json(path).get("label")
        if label is None:
            return "judge-error", None, None
        if label not in ids:
            raise judge.Refused(f"{path}: unknown label {label!r}")
        labels.append(label)
    return "ok", labels[0], labels[1]


def _total(record, key, path):
    """The sum of a run's parts, None when one is not known. A run never counts as free for lack of a number."""
    parts = record.get(key)
    if parts is None:
        return None, None
    if not isinstance(parts, dict):
        raise judge.Refused(f"{path}: {key} is not an object")
    values = [parts.get(k) for k in PARTS]
    if any(v is not None and (type(v) not in (int, float) or not 0 <= v < math.inf) for v in values):
        raise judge.Refused(f"{path}: {key} holds something that is not a number of 0 or more")
    return (None if None in values else sum(values)), parts.get("challenger")


def collect(results, cases, arms, only=None):
    """{task: {arm: {"runs": [(name, before, after)], "used": [per counted run], "excluded": Counter}}}"""
    results = Path(results)
    if not results.is_dir():
        raise judge.Refused(f"no results folder {results}")
    data = {}
    for task_dir in sorted(p for p in results.iterdir() if p.is_dir()):
        if only and task_dir.name not in only:
            continue
        if task_dir.name not in cases:
            raise judge.Refused(f"{task_dir}: no case file for {task_dir.name!r}")
        for arm_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            if arm_dir.name not in arms:
                raise judge.Refused(f"{arm_dir}: unknown arm")
            cell = data.setdefault(task_dir.name, {}).setdefault(
                arm_dir.name, {"runs": [], "used": [], "excluded": Counter()})
            for run_dir in sorted(arm_dir.glob("run-*")):
                status, before, after = read_run(run_dir, cases[task_dir.name])
                if status != "ok":
                    cell["excluded"][status] += 1
                    continue
                cell["runs"].append((run_dir.name, before, after))
                path = run_dir / "run.json"
                record = judge.read_json(path)
                cost, challenger = _total(record, "cost", path)
                seconds = _total(record, "seconds", path)[0]
                cell["used"].append({"cost": cost, "challenger": challenger, "seconds": seconds})
    if not data:
        raise judge.Refused(f"no runs under {results}")
    return data


def fisher(a, b, c, d):
    """Two-sided p of the table [[a, b], [c, d]]: every table with these margins that is no more likely."""
    row, col, n = a + b, a + c, a + b + c + d

    def ways(k):
        return math.comb(col, k) * math.comb(n - col, row - k)

    possible = range(max(0, row - (n - col)), min(row, col) + 1)
    return float(Fraction(sum(ways(k) for k in possible if ways(k) <= ways(a)), math.comb(n, row)))


def mean(cell, key):
    values = [u[key] for u in cell["used"]]
    return sum(values) / len(values) if values and None not in values else None


def row(cell, control, case):
    """Every number of one arm; None where it cannot be computed."""
    runs = cell["runs"]
    right = case["right"]
    out = {"runs": len(runs), "before": sum(b in right for _, b, _ in runs),
           "after": sum(a in right for _, _, a in runs),
           "transitions": Counter((b, a) for _, b, a in runs),
           "flips": [name for name, b, a in runs if b in right and a in case["wrong"]],
           "challenger": mean(cell, "challenger"), "gain": None, "extra_cost": None, "extra_minutes": None,
           "per_design": None, "p": None}
    if not (runs and control and control["runs"]):
        return out
    base = sum(a in right for _, _, a in control["runs"])
    out["gain"] = out["after"] - base
    out["p"] = fisher(out["after"], out["runs"] - out["after"], base, len(control["runs"]) - base)
    for key, name, unit in (("cost", "extra_cost", 1), ("seconds", "extra_minutes", 60)):
        mine, theirs = mean(cell, key), mean(control, key)
        if mine is not None and theirs is not None:
            out[name] = (mine - theirs) / unit
    if out["gain"] > 0 and out["extra_cost"] is not None:
        out["per_design"] = out["extra_cost"] * out["runs"] / out["gain"]  # the arm's whole extra cost, per design
    return out


def _show(value, form):
    return "n/a" if value is None else form.format(value)


COLUMNS = ("arm", "runs", "right before", "right after", "gain", "transitions", "right-to-wrong flips",
           "challenger $/run", "extra $/run", "extra min/run", "$ per extra right design", "Fisher p", "excluded")


def render(data, cases, arms):
    lines = []
    for task, case in cases.items():
        if task not in data:
            continue
        lines += [f"## {task} (right: {', '.join(case['right'])})", "",
                  "| " + " | ".join(COLUMNS) + " |", "|" + " --- |" * len(COLUMNS)]
        control = data[task].get(armfile.CONTROL)
        for arm in arms:
            cell = data[task].get(arm)
            if cell is None:
                continue
            r = row(cell, control, case)
            values = (
                arm, r["runs"], r["before"], r["after"], _show(r["gain"], "{:+d}"),
                "; ".join(f"{b}→{a} {n}" for (b, a), n in sorted(r["transitions"].items())) or "none",
                f"{len(r['flips'])}" + (f" ({', '.join(r['flips'])})" if r["flips"] else ""),
                _show(r["challenger"], "{:.4f}"), _show(r["extra_cost"], "{:+.4f}"),
                _show(r["extra_minutes"], "{:+.1f}"), _show(r["per_design"], "{:.4f}"), _show(r["p"], "{:.3f}"),
                ", ".join(f"{k} {v}" for k, v in sorted(cell["excluded"].items())) or "none")
            lines.append("| " + " | ".join(str(v) for v in values) + " |")
        lines.append("")
    lines.append("Extra and gain are against control. Costs of stopped sessions are estimates at list prices.")
    lines.append(f"Results count only if `judge.py --calibrate` agrees on at least 9 of {judge.MIN_LABELLED} per case.")
    return "\n".join(lines)


def latest_results(env):
    found = [p for p in Path(env.get("TMPDIR") or "/tmp").glob("design-eval/*/results") if p.is_dir()]
    if not found:
        raise judge.Refused("no results folder given and none under $TMPDIR/design-eval")
    return max(found, key=lambda p: p.stat().st_mtime)


def main(argv=None, env=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", nargs="?")
    ap.add_argument("--case", action="append", help="task name; repeat for more (default: every case run)")
    ap.add_argument("--cases", default=str(judge.CASES), help="folder of case files")
    ap.add_argument("--arms", default=str(armfile.ARMS_DIR), help="folder of arm files")
    a = ap.parse_args(argv)
    try:
        cases = judge.load_cases(a.cases)
        judge.load_cases(a.cases, a.case)  # refuses an unknown --case
        arms = armfile.load_arms(a.arms)
        results = a.results
        if results is None:
            results = latest_results(os.environ if env is None else env)
            print(f"results: {results}")
        print(render(collect(results, cases, arms, a.case), cases, arms))
    except (judge.Refused, OSError) as e:
        print(f"report: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
