#!/usr/bin/env python3
"""Compare the arms of a labelled design eval and say whether the questions arms clear the bar.

  python3 report.py RESULTS

RESULTS holds TASK/ARM/run-N/run.json and, after judge.py, TASK/ARM/run-N/{before,after}/label.json.
Only runs with status "ok" and both labels are counted; the rest are listed by reason, never silently dropped.
The bar, for each questions arm against control: a higher share of right final labels by at least 6 of 12 on one
case, no lower share on any other case, and at most one right-to-wrong flip across the cases.
"""
import argparse
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

import judge

ARMS = ("control", "after-red", "before-attacks")
NEEDED_RUNS = 12
MARGIN = Fraction(6, 12)
MAX_FLIPS = 1


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


def collect(results, cases):
    """{task: {arm: {"runs": [(name, before, after)], "excluded": Counter}}}"""
    results = Path(results)
    if not results.is_dir():
        raise judge.Refused(f"no results folder {results}")
    data = {}
    for task_dir in sorted(p for p in results.iterdir() if p.is_dir()):
        if task_dir.name not in cases:
            raise judge.Refused(f"{task_dir}: no case file for {task_dir.name!r}")
        for arm_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            if arm_dir.name not in ARMS:
                raise judge.Refused(f"{arm_dir}: unknown arm")
            cell = data.setdefault(task_dir.name, {}).setdefault(arm_dir.name, {"runs": [], "excluded": Counter()})
            for run_dir in sorted(arm_dir.glob("run-*")):
                status, before, after = read_run(run_dir, cases[task_dir.name])
                if status == "ok":
                    cell["runs"].append((run_dir.name, before, after))
                else:
                    cell["excluded"][status] += 1
    if not data:
        raise judge.Refused(f"no runs under {results}")
    return data


def right_share(cell, case):
    return Fraction(sum(after in case["right"] for _, _, after in cell["runs"]), len(cell["runs"]))


def flips(cell, case):
    return [name for name, before, after in cell["runs"] if before in case["right"] and after in case["wrong"]]


def bar(data, cases, arm):
    """("met" | "not met" | "not evaluated", why) for one questions arm. Every case in `cases` must be there."""
    for task in cases:
        for name in ("control", arm):
            n = len(data.get(task, {}).get(name, {}).get("runs", []))
            if n < NEEDED_RUNS:
                return "not evaluated", f"{task} {name} has {n} counted runs, needs {NEEDED_RUNS}"
    if len(cases) < 2:
        return "not evaluated", "the bar needs at least two cases"
    margins = {t: right_share(data[t][arm], c) - right_share(data[t]["control"], c) for t, c in cases.items()}
    flipped = sum(len(flips(data[t][arm], c)) for t, c in cases.items())
    why = ", ".join(f"{t} {float(m) * 12:+.1f}/12" for t, m in margins.items()) + f", right-to-wrong flips {flipped}"
    met = max(margins.values()) >= MARGIN and min(margins.values()) >= 0 and flipped <= MAX_FLIPS
    return ("met" if met else "not met"), why


def render(data, cases):
    lines = []
    cases = {t: c for t, c in cases.items() if t in data}  # a case that was not run is not compared
    for task, case in cases.items():
        lines.append(f"## {task} (right: {', '.join(case['right'])})")
        for arm in ARMS:
            cell = data.get(task, {}).get(arm)
            if cell is None:
                lines.append(f"\n### {arm}: no runs")
                continue
            runs = cell["runs"]
            right = sum(after in case["right"] for _, _, after in runs)
            lines.append(f"\n### {arm}: right after {right}/{len(runs)}")
            for (before, after), n in sorted(Counter((b, a) for _, b, a in runs).items()):
                lines.append(f"{before}→{after}: {n}")
            final = Counter(after for _, _, after in runs)
            lines.append("final: " + ", ".join(f"{x['id']} {final[x['id']]}" for x in case["labels"]))
            flipped = flips(cell, case)
            lines.append(f"right-to-wrong flips: {len(flipped)}" + (f" ({', '.join(flipped)})" if flipped else ""))
            if cell["excluded"]:
                lines.append("excluded: " + ", ".join(f"{k} {v}" for k, v in sorted(cell["excluded"].items())))
        lines.append("")
    lines.append(f"## Bar: beat control by at least 6 of {NEEDED_RUNS} on one case, no worse on the others, "
                 f"at most {MAX_FLIPS} right-to-wrong flip")
    for arm in ARMS[1:]:
        verdict, why = bar(data, cases, arm)
        lines.append(f"{arm}: {verdict} ({why})")
    lines.append(f"Results count only if `judge.py --calibrate` agrees on at least 9 of {judge.MIN_LABELLED} per case.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results")
    ap.add_argument("--cases", default=str(judge.CASES), help="folder of case files")
    a = ap.parse_args(argv)
    try:
        cases = judge.load_cases(a.cases)
        print(render(collect(a.results, cases), cases))
    except (judge.Refused, OSError) as e:
        print(f"report: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
