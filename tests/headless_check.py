"""Criterion check for issue #40, run by hand or by `herd verify` (it costs about $0.10, so it is not a unittest).
Runs a real headless `claude -p "/herd:run ..."` session in a temp git repo with this checkout as the plugin and
exits 0 only when a review note shows a builder tier and round true."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parent.parent
PROMPT = "/herd:run add add(a, b) in calc.py with a unittest. Use herd init calc."


def main():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty",
                        "-m", "init"], cwd=tmp, check=True)
        subprocess.run(["claude", "-p", PROMPT, "--model", "claude-haiku-5-5", "--plugin-dir", str(CHECKOUT),
                        "--setting-sources", "project", "--permission-mode", "dontAsk", "--allowedTools",
                        "Bash,Read,Write,Edit,Glob,Grep,Agent,Skill", "--max-budget-usd", "1", "--output-format",
                        "stream-json", "--verbose"], cwd=tmp, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       timeout=900)
        reviews = []
        for notes in Path(tmp).glob(".herd/tasks/*/notes.jsonl"):
            reviews += [n for n in map(json.loads, notes.read_text().splitlines()) if n.get("kind") == "review"]
        for n in reviews:
            print({k: n.get(k) for k in ("by", "tier", "builder_tier", "round", "verdict", "unread")})
        if any(n.get("builder_tier") and n.get("round") is True for n in reviews):
            return 0
        print("no review note with a builder tier and round true", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
