"""The README benchmark and contributor pages say what their sources say (issue #106)."""
import re
import statistics
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISCUSSIONS = "https://github.com/Beovulfo/herd-sdlc/discussions"
ARMS = {"Sonnet + Herd 0.3.1": "Sonnet + Herd 0.3.1", "Sonnet, no plugin": "Sonnet, no workflow",
        "Haiku + Herd 0.12.1 (real hooks)": "Haiku + Herd 0.12.1 (real hooks)",
        "Haiku, no plugin": "Haiku, no workflow"}
ROWS = {"Valid stores, of 48": "Valid stores, of 48", "Bad inputs handled, of 6": "Bad-input scenarios handled, of 6",
        "Cost per run (USD)": "Estimated cost per run (USD)"}


def read(name):
    return (ROOT / name).read_text()


def section(text, title):
    found = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return found.group(1) if found else ""


def cells(line):
    return [re.sub(r"\*\*|\(the session's own cost\)", "", c).strip() for c in line.strip().strip("|").split("|")]


def table(text, first):
    """The table whose header starts with `first`, as {row name: {column: cell}}."""
    lines = iter(text.splitlines())
    head = next((cells(x) for x in lines if x.startswith(f"| {first} |")), None)
    if head is None:
        return {}
    next(lines)
    out = {}
    for line in lines:
        if not line.startswith("|"):
            break
        row = cells(line)
        out[row[0]] = dict(zip(head[1:], row[1:]))
    return out


class TestNumbers(unittest.TestCase):
    def setUp(self):
        self.text = section(read("README.md"), "Benchmark")
        self.mine = table(self.text, "Measure")

    def test_table_matches_benchmark_results(self):
        source = table(read("examples/supermarket-route/BENCHMARK.md"), "Measure")
        self.assertEqual(list(self.mine), list(ROWS))
        for name, theirs in ROWS.items():
            self.assertEqual(self.mine[name], {a: source[theirs][b] for a, b in ARMS.items()}, name)

    def test_haiku_herd_column_matches_its_runs(self):
        part = section(read("examples/supermarket-route/BENCHMARK.md"), "Haiku with Herd 0.12.1, real sessions")
        runs = [v for k, v in table(part, "Run").items() if k.isdigit()]
        self.assertEqual(len(runs), 6)
        for name, column, digits in (("Valid stores, of 48", "Valid stores, of 48", 1),
                                     ("Bad inputs handled, of 6", "Bad inputs, of 6", 1),
                                     ("Cost per run (USD)", "Cost (USD)", 2)):
            values = [float(r[column]) for r in runs]
            want = f"{statistics.mean(values):.{digits}f} ± {statistics.stdev(values):.{digits}f}"
            self.assertEqual(self.mine[name]["Haiku + Herd 0.12.1 (real hooks)"], want, name)

    def test_notes_link_and_end_to_end_line(self):
        for s in ("6 runs", "emulated", "real headless", "method", "examples/supermarket-route/BENCHMARK.md",
                  "0.14.0", "39.3 of 40", "38.0", "run count", "bus-transfer", "no recorded"):
            self.assertIn(s, self.text)
        self.assertIn("Sonnet design with a Haiku build scored 39.3 of 40 stores, against 38.0 for Haiku alone",
                      read("CHANGELOG.md"))

    def test_no_other_decimals(self):
        known = read("examples/supermarket-route/BENCHMARK.md") + read("CHANGELOG.md")
        self.assertTrue(self.text)
        self.assertEqual([n for n in re.findall(r"\d+\.\d+(?:\.\d+)?", self.text) if n not in known], [])


class TestPages(unittest.TestCase):
    def test_requirements_line_and_discussions(self):
        readme = read("README.md")
        lines = [x for x in readme.splitlines() if "Python 3.11" in x and "git repository" in x]
        self.assertEqual(len(lines), 1)
        self.assertIn("`gh`", lines[0])
        self.assertIn("`herd pr`", lines[0])
        self.assertIn(DISCUSSIONS, readme)
        self.assertIn("CONTRIBUTING.md", readme)

    def test_use_cases(self):
        text = section(read("README.md"), "Use cases")
        for s in ("(examples/supermarket-route", "(examples/bus-transfer"):
            self.assertIn(s, text)
        poi = [x for x in text.splitlines() if "poi_entry_point" in x]
        self.assertEqual(len(poi), 1)
        for s in ("private", "fuel stations", "Overture Maps", "OpenStreetMap"):
            self.assertIn(s, poi[0])
        self.assertIsNone(re.search(r"\]\(|http|\d|`[^`]*/", poi[0]), poi[0])

    def test_contributing(self):
        text = read("CONTRIBUTING.md")
        for s in ("python3", "3.11", "`gh`", "python3 -m unittest tests.", "ruff check .",
                  "claude plugin validate ./plugin", "plugin/.claude-plugin/plugin.json", "CHANGELOG",
                  "/herd:run", "standard library", "good first issue", DISCUSSIONS):
            self.assertIn(s, text)

    def test_issue_templates(self):
        config = read(".github/ISSUE_TEMPLATE/config.yml")
        self.assertRegex(config, r"(?m)^blank_issues_enabled: false$")
        self.assertIn(f"url: {DISCUSSIONS}", config)
        for name in ("bug_report", "feature_request"):
            form = read(f".github/ISSUE_TEMPLATE/{name}.yml")
            for key in (r"^name: \S", r"^description: \S", r"^body:$", r"^    attributes:$", r"^      label: \S"):
                self.assertRegex(form, re.compile(key, re.M), name)
            self.assertNotIn("\t", form)

    def test_writing_style(self):
        for name in ("CONTRIBUTING.md", "README.md", ".github/ISSUE_TEMPLATE/config.yml",
                     ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml"):
            self.assertNotIn("—", read(name), name)


if __name__ == "__main__":
    unittest.main()
