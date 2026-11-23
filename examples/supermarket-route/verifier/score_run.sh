#!/bin/sh
# Score one benchmark run: robustness probe, then the hidden verifier on all four sizes.
# From the repository root:  sh examples/supermarket-route/verifier/score_run.sh sonnet-herd-1
set -e
H=examples/supermarket-route
n=$1
python3 $H/verifier/probe_runs.py "$n=$H/runs/$n:$H/runs/adapters/$n.py" | tail -1
python3 $H/verifier/verify_general.py "file:$H/runs/adapters/$n.py" "$H/runs/$n" --tiers S,M,L,XL \
  | grep -E "^\| (S|M|L|XL) |^! |RESULT"
