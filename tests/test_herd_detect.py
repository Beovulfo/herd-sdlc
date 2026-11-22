import json
import tempfile
import unittest
from pathlib import Path

from scripts import herd_detect as hd


class TestDetect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, text=""):
        (self.root / name).write_text(text)

    def types(self):
        return {d["type"]: d for d in hd.detect(self.root)}

    def test_empty_directory(self):
        self.assertEqual(hd.detect(self.root), [])

    def test_python_markers(self):
        for marker in ("pyproject.toml", "setup.cfg", "requirements.txt"):
            with self.subTest(marker=marker):
                (self.root / marker).write_text("")
                d = self.types()["python"]
                self.assertEqual((d["test"], d["lint"]), ("pytest", "ruff check ."))
                self.assertIn(marker, d["markers"])
                (self.root / marker).unlink()

    def test_node_with_real_test_script(self):
        self.put("package.json", json.dumps({"scripts": {"test": "jest"}}))
        d = self.types()["node"]
        self.assertEqual((d["test"], d["lint"]), ("npm test", "npx eslint ."))

    def test_node_npm_init_stub_is_not_a_test(self):
        stub = 'echo "Error: no test specified" && exit 1'
        self.put("package.json", json.dumps({"scripts": {"test": stub}}))
        self.assertIsNone(self.types()["node"]["test"])

    def test_node_without_scripts_and_lint_script(self):
        self.put("package.json", "{}")
        self.assertIsNone(self.types()["node"]["test"])
        self.put("package.json", json.dumps({"scripts": {"lint": "eslint src"}}))
        self.assertEqual(self.types()["node"]["lint"], "npm run lint")

    def test_node_bad_json_does_not_crash(self):
        self.put("package.json", "{not json")
        self.assertIsNone(self.types()["node"]["test"])

    def test_rust_and_go(self):
        self.put("Cargo.toml")
        self.put("go.mod")
        t = self.types()
        self.assertEqual((t["rust"]["test"], t["rust"]["lint"]), ("cargo test", "cargo clippy -- -D warnings"))
        self.assertEqual((t["go"]["test"], t["go"]["lint"]), ("go test ./...", "go vet ./..."))

    def test_makefile_needs_test_target(self):
        self.put("Makefile", "build:\n\tcc x.c\n")
        self.assertNotIn("make", self.types())
        self.put("Makefile", "build:\n\tcc x.c\n\ntest:\n\t./run\n")
        d = self.types()["make"]
        self.assertEqual((d["test"], d["lint"]), ("make test", None))
        self.put("Makefile", "retest:\n\techo no\n")  # a target that merely ends in 'test'
        self.assertNotIn("make", self.types())

    def test_several_types_in_one_repo(self):
        self.put("pyproject.toml")
        self.put("package.json", json.dumps({"scripts": {"test": "jest"}}))
        self.assertEqual(set(self.types()), {"python", "node"})

    def test_unsupported_ecosystems_return_nothing(self):
        for name in ("pom.xml", "Gemfile", "dbt_project.yml", "main.tf"):
            self.put(name)
        self.assertEqual(hd.detect(self.root), [])

    def test_result_is_json_serialisable(self):
        self.put("Cargo.toml")
        json.dumps(hd.detect(self.root))


if __name__ == "__main__":
    unittest.main()
