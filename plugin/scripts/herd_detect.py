"""Project-type detection for Herd: proposals only, nothing runs.

The per-ecosystem commands are conventions from general knowledge, not from docs.
The human confirms them (see skills/evidence).
"""
import json
import re
from pathlib import Path

NPM_STUB = "no test specified"


def _node(root):
    test, lint = None, "npx eslint ."
    try:
        scripts = json.loads((root / "package.json").read_text()).get("scripts", {})
    except (ValueError, AttributeError, OSError):
        scripts = {}
    if isinstance(scripts, dict):
        t = scripts.get("test")
        if isinstance(t, str) and t.strip() and NPM_STUB not in t:
            test = "npm test"
        if isinstance(scripts.get("lint"), str):
            lint = "npm run lint"
    return {"test": test, "lint": lint}


def _make(root):
    try:
        text = (root / "Makefile").read_text()
    except OSError:
        return None
    return {"test": "make test", "lint": None} if re.search(r"^test\s*:", text, re.M) else None


FIXED = [
    ("python", ("pyproject.toml", "setup.cfg", "requirements.txt"), {"test": "pytest", "lint": "ruff check ."}),
    ("rust", ("Cargo.toml",), {"test": "cargo test", "lint": "cargo clippy -- -D warnings"}),
    ("go", ("go.mod",), {"test": "go test ./...", "lint": "go vet ./..."}),
]


def detect(root):
    """List of {type, markers, test, lint} for the supported ecosystems found in root."""
    root = Path(root)
    out = []
    for kind, markers, cmds in FIXED:
        found = [m for m in markers if (root / m).exists()]
        if found:
            out.append({"type": kind, "markers": found, **cmds})
    if (root / "package.json").exists():
        out.append({"type": "node", "markers": ["package.json"], **_node(root)})
    if (root / "Makefile").exists():
        cmds = _make(root)
        if cmds:
            out.append({"type": "make", "markers": ["Makefile"], **cmds})
    return out
