"""Programs for the attacks of tests.test_designer: `python3 -m tests.refuse_designer collision|one-bad-part|example`
runs `herd status` in a private temporary repository and exits as it did."""
import subprocess
import sys
import tempfile
from pathlib import Path

HERD = Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "herd.py"
TOML = {"collision": '[models]\ndesign = "sonnet"\ndesign = "haiku"\n',  # one setting given twice
        "one-bad-part": "[models]\ndesign = 3\n",
        "example": '[models]\nbuild = "opus"\n'}


def main(case):
    with tempfile.TemporaryDirectory() as tmp:
        def run(*cmd):
            return subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        run("git", "init", "-q")
        (Path(tmp) / "herd.toml").write_text(TOML[case])
        if case == "example":  # a task, so that status exits 0; it keeps the models herd.toml had at init
            run(sys.executable, str(HERD), "init", "t1", "Add a greeting")
        p = run(sys.executable, str(HERD), "status")
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
