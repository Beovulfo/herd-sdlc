#!/usr/bin/env python3
"""Mean and standard deviation per arm from the scored runs. Run from the repository root:

  python3 examples/supermarket-route/verifier/aggregate.py

Reads runs/usage.json (cost and effort per run) and runs/results/<run>.txt (probe and verifier output).
"""
import json
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "runs"
ARMS = [("Sonnet 5.5 + Herd 0.3.1", "sonnet-herd-"), ("Sonnet 5.5, no workflow", "sonnet-plain-"),
        ("Haiku 5.5 + Herd 0.3.1", "haiku-herd-"), ("Haiku 5.5, no workflow", "haiku-plain-")]
TIERS = {"S": 16, "M": 16, "L": 8, "XL": 8}


def parse(run):
    text = (ROOT / "results" / f"{run}.txt").read_text()
    probe = int(re.search(r"\| (\d) of 6 \|", text.splitlines()[0])[1])
    tiers = {}
    for m in re.finditer(r"^\| (S|M|L|XL) \| (\d+) \| (\d+) of \d+ \| (\d+) of \d+ \| (?:([\d.]+)%|n/a) \|.*?\| (?:([\d.]+)|n/a) \|", text, re.M):
        tiers[m[1]] = {"valid": int(m[4]), "saved": float(m[5]) if m[5] else None, "wall": float(m[6]) if m[6] else None}
    return probe, tiers


def ms(xs, fmt="{:.1f}"):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "n/a"
    sd = st.stdev(xs) if len(xs) > 1 else 0.0
    return f"{fmt.format(st.mean(xs))} ± {fmt.format(sd)}"


def main():
    usage = json.loads((ROOT / "usage.json").read_text())
    rows = {}
    for label, prefix in ARMS:
        runs = [f"{prefix}{i}" for i in range(1, 7)]
        parsed = {r: parse(r) for r in runs}
        valid = [sum(t["valid"] for t in parsed[r][1].values()) for r in runs]
        rows[label] = {
            "Valid stores, of 48": ms(valid),
            "Runs with all 48 valid": f"{sum(v == 48 for v in valid)} of 6",
            "Robustness probe, of 6": ms([parsed[r][0] for r in runs]),
            **{f"Valid {t} stores, of {n}": ms([parsed[r][1][t]["valid"] for r in runs]) for t, n in TIERS.items()},
            **{f"Time saved, {t} (%)": ms([parsed[r][1][t]["saved"] for r in runs]) for t in TIERS},
            "Median plan time, XL store (s)": ms([parsed[r][1]["XL"]["wall"] for r in runs]),
            "Build time (min)": ms([usage[r]["duration_s"] / 60 for r in runs]),
            "Tool calls": ms([usage[r]["tool_calls"] for r in runs], "{:.0f}"),
            "Model requests": ms([usage[r]["req"] for r in runs], "{:.0f}"),
            "Output tokens (k)": ms([usage[r]["out"] / 1000 for r in runs]),
            "Tokens read, incl. cache (k)": ms([(usage[r]["inp"] + usage[r]["cr"] + usage[r]["cw"]) / 1000 for r in runs], "{:.0f}"),
            "Estimated cost per run (USD)": ms([usage[r]["cost"] for r in runs], "{:.3f}"),
        }
    labels = list(rows)
    print("| Measure (mean ± standard deviation over 6 runs) | " + " | ".join(labels) + " |")
    print("| --- |" + " --- |" * len(labels))
    for k in rows[labels[0]]:
        print(f"| {k} | " + " | ".join(rows[lab][k] for lab in labels) + " |")


if __name__ == "__main__":
    main()
