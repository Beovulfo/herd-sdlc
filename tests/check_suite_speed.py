"""Run the full suite once, one process per test module, 6 at a time, and assert it is fast and complete.

Used by the fast-tests task criterion: `python3 tests/check_suite_speed.py`. Not a test module."""
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LIMIT_SECONDS = 30
MIN_TESTS = 467  # the count before the speed-up


def run(module):
    p = subprocess.run([sys.executable, "-m", "unittest", module], capture_output=True, text=True,
                       timeout=LIMIT_SECONDS * 4)
    m = re.search(r"Ran (\d+) tests? in", p.stderr)
    return module, p.returncode, int(m.group(1)) if m else 0, p.stderr


def main():
    mods = sorted(f"tests.{p.stem}" for p in Path("tests").glob("test_*.py"))
    start = time.time()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(run, mods))
    wall = time.time() - start
    total = sum(n for _, _, n, _ in results)
    for mod, code, n, err in results:
        if code:
            print(err[-2000:])
    print(f"{total} tests in {wall:.1f} s wall (limit {LIMIT_SECONDS} s, at least {MIN_TESTS} tests)")
    bad = [m for m, c, _, _ in results if c]
    if bad:
        sys.exit(f"failing modules: {bad}")
    if total < MIN_TESTS:
        sys.exit(f"only {total} tests, expected at least {MIN_TESTS}")
    if wall >= LIMIT_SECONDS:
        sys.exit(f"{wall:.1f} s is not under {LIMIT_SECONDS} s")


if __name__ == "__main__":
    main()
