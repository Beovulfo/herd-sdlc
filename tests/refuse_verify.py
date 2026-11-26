"""Attack helper (issue #127): run `herd verify` on a task it must refuse (a duplicate id, or a broken criterion)."""
import subprocess
import sys
import tempfile
from pathlib import Path

HERD = Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "herd.py"
ONE = '[[criteria]]\nid = "C1"\ntext = "t"\nsource = "agent-proposed"\ncheck = "{}"\n'
BAD = {"duplicate": ONE.format("true") + ONE.format("false"), "broken": '[[criteria]]\nid = "C1"\n'}

with tempfile.TemporaryDirectory() as d:
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run([sys.executable, HERD, "init", "t", "g"], cwd=d, check=True, capture_output=True)
    Path(d, ".herd/tasks/t/task.toml").write_text('goal = "g"\n' + BAD[sys.argv[1]])
    sys.exit(subprocess.run([sys.executable, HERD, "verify"], cwd=d).returncode)
