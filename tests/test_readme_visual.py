"""The README is short, visual and loses no fact (issue #115). Facts are read from the files, not typed again."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEFORE_WORDS = 1382  # `wc -w README.md` on main before the rewrite
LIMIT = BEFORE_WORDS // 2  # 691
MOVED = "docs/how-it-works.md"
# facts the old README carried that now live in docs/how-it-works.md
MOVED_FACTS = ["--covered-by", "--expect", "--fresh", "herd done` refuses a design", "No second model reviews",
               "matches any model id that contains it", "The values are read at `herd init`",
               "[worktree] required = true", "[pr] open = true", "Untrusted input is refused",
               "`herd pr` (opt-in)", "never merges", "The 0.3.1 round", "[models]", "design = \"sonnet\"",
               "build = \"haiku\""]
# links the old README offered: each must still be there, or be in how-it-works
KEPT_LINKS = ["wiki/Quickstart", "wiki/Settings", "wiki/How-Herd-works", "wiki/Example", "wiki/Attacks",
              "wiki/Hooks-and-guard", "wiki/Commands", "wiki/Benchmark", "wiki/Design-and-roadmap",
              "examples/design-eval/README.md", "docs/PRD.md", "CHANGELOG.md", "examples/supermarket-route/BENCHMARK.md"]


def read(name):
    return (ROOT / name).read_text()


def slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def prose_blocks(text):
    """Blocks of consecutive plain lines: outside code fences, tables and list-less html wrappers are kept as text."""
    blocks, cur, fence = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            cur = cur and (blocks.append(cur) or [])
            continue
        if fence or not line.strip() or line.lstrip().startswith(("|", "#")):
            if cur:
                blocks.append(cur)
            cur = []
            continue
        cur.append(re.sub(r"<[^>]+>", " ", line))
    if cur:
        blocks.append(cur)
    return [b for b in blocks if " ".join(b).strip()]


def links(text):
    return re.findall(r"(?<!!)\]\(([^)\s]+)\)", text)


class TestSize(unittest.TestCase):  # C1
    def test_word_count_at_most_half(self):
        out = subprocess.run(["wc", "-w", str(ROOT / "README.md")], capture_output=True, text=True).stdout
        self.assertLessEqual(int(out.split()[0]), LIMIT)

    def test_rendered_word_count_at_most_half(self):
        text = re.sub(r"```.*?```", " ", read("README.md"), flags=re.S)
        text = re.sub(r"<[^>]+>|\(https?://[^)]*\)|\([\w./#-]+\)", " ", text)
        self.assertLessEqual(len(re.findall(r"[\w`-]+", text)), LIMIT)

    def test_removed_sections_are_linked(self):
        readme = read("README.md")
        self.assertIn(f"]({MOVED})", readme)
        self.assertTrue((ROOT / MOVED).is_file())
        self.assertEqual([x for x in KEPT_LINKS if x not in readme and x not in read(MOVED)], [])


class TestDiagram(unittest.TestCase):  # C2
    def setUp(self):
        found = re.findall(r"```mermaid\n(.*?)```", read("README.md"), re.S)
        self.assertEqual(len(found), 1)
        self.diagram = found[0]

    def test_flow_has_every_step(self):
        self.assertRegex(self.diagram, r"^\s*(flowchart|graph) ")
        low = self.diagram.lower()
        for word in ("goal", "criteria", "red", "build", "attack", "verify", "evidence", "stop"):
            self.assertIn(word, low)

    def test_theme_neutral_and_well_formed(self):
        self.assertNotRegex(self.diagram, r"fill:|stroke:|color:|%%\{init")  # hard colors break dark mode
        for a, b in ("[]", "()", "{}"):
            self.assertEqual(self.diagram.count(a), self.diagram.count(b))
        self.assertGreaterEqual(self.diagram.count("-->"), 6)

    def test_diagram_is_visual_first(self):
        """Within the first 45 lines (visitor decides in 30 seconds), and the Stop gate has its own edge."""
        lines = read("README.md").splitlines()
        self.assertLess(lines.index("```mermaid"), 45)
        self.assertRegex(self.diagram, r"(?i)stop[^\n]*(-->|-\.->|---)|(-->|-\.->)[^\n]*stop")

    def test_diagram_sits_above_the_benchmark(self):
        readme = read("README.md")
        self.assertLess(readme.index("```mermaid"), readme.index("## Benchmark"))


class TestSafe(unittest.TestCase):  # C3
    def test_no_em_dash_no_private_link(self):
        for name in ("README.md", MOVED):
            self.assertNotIn("—", read(name), name)
        readme = read("README.md")
        self.assertNotRegex(readme, r"poi_entry_point\]\(")
        for line in readme.splitlines():
            if "poi_entry_point" in line:
                self.assertNotRegex(line, r"\]\(|http|\d")
        low = (readme + read(MOVED)).lower()
        for word in ("employer",):
            self.assertNotRegex(low, rf"\b{word}\b")

    def test_ci_modules_pass(self):
        r = subprocess.run(["python3", "-m", "unittest", "tests.test_docs_sync", "tests.test_readme_benchmark"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


class TestMoved(unittest.TestCase):  # C4
    def test_each_moved_fact_is_in_how_it_works(self):
        self.assertTrue((ROOT / MOVED).is_file())
        text = read(MOVED)
        self.assertEqual([f for f in MOVED_FACTS if f not in text], [])


class TestReadable(unittest.TestCase):  # C5
    def test_no_paragraph_over_three_lines_or_sixty_words(self):
        bad = [b for b in prose_blocks(read("README.md"))
               if len(b) > 3 or len(re.findall(r"\S+", " ".join(b))) > 60]
        self.assertEqual(bad, [])

    def test_top_order(self):
        t = read("README.md")
        order = [t.index(x) for x in ("assets/logo.svg", "shields.io", "assets/demo.gif", "/plugin install")]
        self.assertEqual(order, sorted(order))

    def test_use_cases_is_a_three_row_table(self):
        sec = re.search(r"^## Use cases\n(.*?)(?=^## |\Z)", read("README.md"), re.M | re.S).group(1)
        rows = [x for x in sec.splitlines() if x.startswith("|")]
        self.assertEqual(len(rows), 2 + 3)  # header, rule, three cases

    def test_each_benchmark_cell_is_one_small_table(self):
        sec = re.search(r"^## Benchmark\n(.*?)(?=^## |\Z)", read("README.md"), re.M | re.S).group(1)
        self.assertEqual(len([x for x in sec.splitlines() if x.startswith("| Measure")]), 1)


class TestLinks(unittest.TestCase):  # bad-input and collision
    FILES = ("README.md", MOVED)

    def test_every_relative_link_and_image_resolves(self):
        bad = []
        for name in self.FILES:
            text = read(name)
            base = (ROOT / name).parent
            for target in links(text) + re.findall(r'(?:src|srcset)="([^"]+)"', text) + re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
                if target.startswith(("http", "mailto:")):
                    continue
                path, _, anchor = target.partition("#")
                dest = (base / path) if path else ROOT / name
                if not dest.exists():
                    bad.append((name, target))
                elif anchor and dest.suffix == ".md":
                    heads = [slug(h) for h in re.findall(r"^#+ (.*)$", dest.read_text(), re.M)]
                    if anchor not in heads:
                        bad.append((name, target))
        self.assertEqual(bad, [])

    def test_no_two_headings_share_an_anchor(self):
        for name in self.FILES:
            heads = [slug(h) for h in re.findall(r"^#+ (.*)$", read(name), re.M)]
            self.assertEqual(len(heads), len(set(heads)), name)

    def test_one_floor_row_and_one_requirements_line(self):
        readme = read("README.md")
        self.assertEqual(len([x for x in readme.splitlines() if x.startswith("| `[floor]`")]), 1)
        self.assertEqual(len([x for x in readme.splitlines() if "Python 3.11" in x and "git repository" in x]), 1)


class TestNumbers(unittest.TestCase):  # recount
    def test_every_number_comes_from_a_source(self):
        corpus = " ".join(read(n) for n in ("examples/supermarket-route/BENCHMARK.md", "CHANGELOG.md",
                                            "plugin/.claude-plugin/plugin.json", "docs/PRD.md",
                                            "plugin/skills/run/adversarial.md"))
        text = re.sub(r"https?://\S+|\([\w./#-]+\)", " ", read("README.md"))
        text = re.sub(r"```mermaid.*?```", " ", text, flags=re.S)
        missing = [n for n in re.findall(r"\d+(?:\.\d+)*", text) if n not in corpus]
        self.assertEqual(missing, [])

    def test_attack_and_run_counts_still_stated(self):
        t = read("README.md")
        for s in ("6 attacks", "6 runs", "39.3 of 40", "38.0"):
            self.assertIn(s, t)


class TestRefusalClaims(unittest.TestCase):  # refusal: claims the docs make about what Herd refuses
    def test_documented_refusals_exist_in_the_code(self):
        code = read("plugin/scripts/herd.py")
        text = read(MOVED)
        self.assertIn("herd done` refuses a design", text)
        self.assertIn("not {model}", code)  # the designer-model refusal reason
        self.assertIn("first verify refuses", code)  # the first verify refuses while an attack has no note


if __name__ == "__main__":
    unittest.main()
