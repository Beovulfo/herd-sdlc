"""Herd Triage (M0): deterministic risk floor. See docs/designs/herd-triage.md.

Standard library only. Pure functions except write_record. Python 3.11+.
"""
import json
import os
import re
import tempfile
import tomllib
from pathlib import PurePosixPath


def _glob_re(pattern):
    segs, out = pattern.split("/"), []
    for i, seg in enumerate(segs):
        if seg == "**":  # zero or more segments; a trailing ** needs at least one, as in full_match
            out.append("(?:[^/]+/)+" if i == len(segs) - 1 else "(?:[^/]+/)*")
        else:
            out.append("".join("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in seg) + "/")
    return "".join(out)


def glob_match(path, pattern):
    """PurePosixPath(path).full_match(pattern), with a fallback for Python 3.11 and 3.12.

    ponytail: the fallback handles *, ? and **, not [seq] classes; add them if a rule needs one.
    """
    if hasattr(PurePosixPath, "full_match"):
        return PurePosixPath(path).full_match(pattern)
    return re.fullmatch(_glob_re(pattern), path + "/") is not None

LEVELS = ("low", "medium", "high")
DEFAULT_RULES = {
    "high": ["migrations/**", "auth/**", "billing/**", "herd.toml"],
    "medium": ["api/**"],
}
DEFAULT_EXTENSIONS = ["py", "ts", "js", "sql", "toml", "json", "md"]
SCHEMA_VERSION = 1

_SLASH_TOKEN = re.compile(r"[A-Za-z0-9._\-/]*[A-Za-z0-9_\-]/[A-Za-z0-9._\-/]*")


def _rank(level):
    return LEVELS.index(level) if level in LEVELS else LEVELS.index("high")


def extract_paths(body, extensions):
    """Path-like tokens from issue text, normalised. Prose paths are missed."""
    exts = "|".join(re.escape(e) for e in extensions)
    pattern = re.compile(rf"[A-Za-z0-9._\-/]+(?:\.(?:{exts})(?![A-Za-z0-9_]))|{_SLASH_TOKEN.pattern}")
    out = []
    for tok in pattern.findall(body):
        tok = tok.rstrip(".")
        if tok.startswith("/") or ".." in tok.split("/"):
            continue
        tok = tok[2:] if tok.startswith("./") else tok
        tok = re.sub(r"/{2,}", "/", tok)
        if tok and tok not in out:
            out.append(tok)
    return out


def floor(paths, labels, rules):
    """Return (level, matched_rules, source). labels maps label name to applier role."""
    matched, level = [], None
    for lvl in ("high", "medium"):
        for glob in rules.get(lvl, []):
            if any(glob_match(p, glob) for p in paths):
                matched.append(glob)
                level = level or lvl
    source = "issue_text" if matched else "default"
    label_level = None
    for name in ("risk:high", "risk:medium"):
        if name in labels and (label_level is None or _rank(name[5:]) > _rank(label_level)):
            label_level = name[5:]
    if label_level and (level is None or _rank(label_level) > _rank(level)):
        return label_level, matched, "label"
    if level:
        return level, matched, source
    if labels.get("risk:low") == "maintainer":
        return "low", [], "label"
    return "medium", [], "default"


def effective_of(record):
    """Effective level of a stored record; any out-of-range value is high."""
    risk = record.get("risk", {})
    override = risk.get("override")
    level = override.get("to") if override else risk.get("floor")
    return level if level in LEVELS else "high"


def _fallback(feature, issue, cause, prior=None):
    rec = dict(prior) if isinstance(prior, dict) else {}
    rec.update({
        "schema_version": SCHEMA_VERSION, "feature": feature, "issue": issue,
        "status": "fallback", "cause": cause,
        "risk": {"floor": "high", "floor_rules": [], "floor_inputs": {"paths": [], "source": "default"},
                 "effective": "high", "override": None},
    })
    return rec


def _rules_from(herd_toml):
    cfg = tomllib.loads(herd_toml)
    ext = cfg.get("path_extensions", DEFAULT_EXTENSIONS)
    if "floor" not in cfg:
        return DEFAULT_RULES, ext
    fl = cfg["floor"]
    if not isinstance(fl, dict) or set(fl) - {"high", "medium"}:
        raise ValueError("bad [floor] table")
    for lvl in fl:
        if not isinstance(fl[lvl], list) or not all(isinstance(g, str) for g in fl[lvl]):
            raise ValueError("floor lists must be lists of strings")
    return fl, ext


def build_record(feature, issue, body, labels, herd_toml, prior=None):
    """Build the triage record. Never raises; failure gives a high fallback record."""
    try:
        if prior is not None and prior.get("schema_version") != SCHEMA_VERSION:
            return _fallback(feature, issue, "schema")
        if herd_toml is None:
            return _fallback(feature, issue, "herd_toml", prior)
        try:
            rules, ext = _rules_from(herd_toml)
        except (tomllib.TOMLDecodeError, ValueError):
            return _fallback(feature, issue, "herd_toml", prior)
        paths = extract_paths(body, ext)
        level, matched, source = floor(paths, labels, rules)
        rec = dict(prior) if prior else {}
        override = (prior or {}).get("risk", {}).get("override")
        rec.update({
            "schema_version": SCHEMA_VERSION, "feature": feature, "issue": issue,
            "status": "ok", "cause": None,
            "risk": {"floor": level, "floor_rules": matched,
                     "floor_inputs": {"paths": paths, "source": source},
                     "effective": level, "override": override},
        })
        rec["risk"]["effective"] = effective_of(rec)
        return rec
    except Exception:  # ponytail: any failure fails closed to high
        return _fallback(feature, issue, "error", prior if isinstance(prior, dict) else None)


def apply_override(record, level, actor, comment_id, now):
    """Human override (a maintainer's /herd risk). Raises ValueError on a bad level."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    rec = json.loads(json.dumps(record))
    risk = rec["risk"]
    risk["override"] = {"actor": actor, "comment_id": comment_id,
                        "from": risk["effective"], "to": level, "time": now}
    risk["effective"] = level
    return rec


def write_record(path, record):
    """Write JSON to a temp file in the same directory, then rename."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
