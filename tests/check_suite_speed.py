"""Run the full suite once, one process per test class, one per CPU core at a time, and assert it is fast and complete.

Used by the fast-tests task criterion: `python3 tests/check_suite_speed.py`. Not a test module."""
import os
import re
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

LIMIT_SECONDS = 30
MIN_TESTS = 467  # the count before the speed-up


def classes():
    """Every `tests.module.Class` that holds tests, so heavy modules spread over all cores."""
    found = set()

    def walk(suite):
        for t in suite:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                found.add(f"{type(t).__module__}.{type(t).__name__}")
    walk(unittest.defaultTestLoader.discover("tests", top_level_dir=".", pattern="test_*.py"))
    return sorted(found)


def run(module):
    p = subprocess.run([sys.executable, "-m", "unittest", module], capture_output=True, text=True,
                       timeout=LIMIT_SECONDS * 4)
    m = re.search(r"Ran (\d+) tests? in", p.stderr)
    return module, p.returncode, int(m.group(1)) if m else 0, p.stderr


def main():
    mods = classes()
    start = time.time()
    with ThreadPoolExecutor(os.cpu_count() or 6) as pool:
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
