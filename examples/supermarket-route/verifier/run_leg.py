#!/usr/bin/env python3
"""Launch N headless runs of one benchmark leg, each isolated from the hidden verifier, the published
solutions, the other runs and the network. See the "Run isolation" section of ../README.md.

  python3 run_leg.py --name haiku-herd-v0.12.1 --runs 6 --model claude-haiku-5-5 --prompt PROMPT_FILE \
      [--herd-tag v0.12.1] [--root DIR] [--budget 10] [--dry-run]
  python3 run_leg.py --selftest

Prove a finished run stayed inside its sandbox with leak_audit.py.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLANTED_NAMES = {"verify_general.py", "robustness_probe.py", "probe6.py"}
TOOLS = "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Agent,Skill"
GITCONFIG = "[user]\n\tname = bench\n\temail = bench@example.com\n"


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--name")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--model")
    ap.add_argument("--prompt")
    ap.add_argument("--herd-tag")
    ap.add_argument("--root")
    ap.add_argument("--budget", type=float, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    return ap.parse_args(argv)


def _under(path, root):
    path, root = Path(path), Path(root)
    return path == root or root in path.parents


def denied_paths(root, n_runs, i):
    """Absolute paths run i must not read: other entries of the root's parent, and the other runs with their logs."""
    root = Path(root)
    out = []
    if root.parent.is_dir():
        out += [str(p) for p in sorted(root.parent.iterdir()) if p != root]
    for m in range(1, n_runs + 1):
        if m != i:
            out += [str(root / f"run-{m}"), str(root / f"run-{m}.jsonl"), str(root / f"run-{m}.err")]
    return out


def build_settings(root, n_runs, i, extra=()):
    denied = denied_paths(root, n_runs, i) + [str(x) for x in extra]
    return {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False,
                    "filesystem": {"denyRead": ["~/", *denied]}},
        "permissions": {"deny": ["Read(~/**)", *[f"Read(/{d}/**)" for d in denied], "WebFetch", "WebSearch"]},
    }


def build_command(ns, prompt, run_dir):
    run_dir = Path(run_dir)
    cmd = ["claude", "-p", prompt, "--model", ns.model]
    if ns.herd_tag:
        cmd += ["--plugin-dir", str(run_dir / "plugin")]
    cmd += ["--setting-sources", "project", "--settings", str(run_dir / "settings.json"),
            "--permission-mode", "dontAsk", "--allowedTools", TOOLS,
            "--max-budget-usd", f"{ns.budget:g}", "--output-format", "stream-json", "--verbose"]
    return cmd


def preflight(scan_dirs, denied):
    """Files named like the hidden verifier or probes, readable by a run, under the scan dirs."""
    denied = [os.path.realpath(d) for d in denied]
    found, seen = [], set()
    for top in scan_dirs:
        top = os.path.realpath(top)
        if top in seen or not os.path.isdir(top):
            continue
        seen.add(top)
        for cur, dirs, files in os.walk(top, onerror=lambda e: None):
            dirs[:] = [d for d in dirs if not any(_under(os.path.realpath(os.path.join(cur, d)), x) for x in denied)]
            found += [os.path.join(cur, f) for f in files if f in PLANTED_NAMES]
    return sorted(set(found))


def _git_env(run_dir, base):
    return {**base, "GIT_CONFIG_GLOBAL": str(Path(run_dir) / "gitconfig"), "XDG_CONFIG_HOME": str(Path(run_dir) / "xdg")}


def _repo_root():
    r = subprocess.run(["git", "-C", str(SCRIPT_DIR), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tag_exists(tag):
    repo = _repo_root()
    return bool(repo) and subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", f"{tag}^{{commit}}"],
                                         capture_output=True).returncode == 0


def outside_home_repo(env):
    """This repository's checkout, when it is outside HOME (so `~/` does not already deny it)."""
    repo, home = _repo_root(), os.path.realpath(env.get("HOME", os.path.expanduser("~")))
    return [os.path.realpath(repo)] if repo and not _under(os.path.realpath(repo), home) else []


def create_run(root, n_runs, i, ns, env):
    run_dir = Path(root) / f"run-{i}"
    for sub in ("work", "xdg"):
        (run_dir / sub).mkdir(parents=True)
    (run_dir / "gitconfig").write_text(GITCONFIG)
    genv = _git_env(run_dir, env)
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=run_dir / "work", env=genv, check=True, capture_output=True)
    if ns.herd_tag:
        (run_dir / "plugin").mkdir()
        tar = subprocess.run(["git", "-C", _repo_root(), "archive", "--format=tar", ns.herd_tag, "--", ".",
                              ":!examples", ":!tests", ":!docs"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-xf", "-", "-C", str(run_dir / "plugin")], input=tar, check=True)
    (run_dir / "settings.json").write_text(json.dumps(build_settings(root, n_runs, i, outside_home_repo(env)), indent=2) + "\n")
    return run_dir


def start(cmd, run_dir, log, err, env):
    with open(log, "wb") as out, open(err, "wb") as errf:
        return subprocess.Popen(cmd, cwd=Path(run_dir) / "work", env=_git_env(run_dir, env), stdin=subprocess.DEVNULL,
                                stdout=out, stderr=errf, start_new_session=True)


def run(argv, env=None, scan_dirs=None):
    env = dict(os.environ if env is None else env)
    ns = parse(argv)
    if ns.selftest:
        return selftest(env)
    if not (ns.name and ns.runs and ns.runs > 0 and ns.model and ns.prompt):
        print("--name, --runs (at least 1), --model and --prompt are required", file=sys.stderr)
        return 2
    try:
        prompt = Path(ns.prompt).read_text()
    except OSError as e:
        print(f"refused: cannot read the prompt file {ns.prompt}: {e.strerror}", file=sys.stderr)
        return 2
    tmpdir = env.get("TMPDIR") or "/tmp"
    root = Path(os.path.realpath(ns.root or os.path.join(tmpdir, "herd-bench", ns.name)))
    home = Path(os.path.realpath(env.get("HOME", os.path.expanduser("~"))))
    if _under(root, home):
        print(f"refused: root {root} is inside HOME ({home}); a run could read it through ~", file=sys.stderr)
        return 2
    if root.exists():
        print(f"refused: root {root} already exists", file=sys.stderr)
        return 2
    if ns.herd_tag and not tag_exists(ns.herd_tag):
        print(f"refused: {ns.herd_tag} is not a tag or commit of this repository", file=sys.stderr)
        return 2
    denied = denied_paths(root, 0, 0)
    scan = scan_dirs if scan_dirs is not None else ["/tmp", "/private/tmp", tmpdir]
    bad = preflight(scan, denied)
    if bad:
        print("refused: the hidden verifier or a probe is readable by a run:", file=sys.stderr)
        for b in bad:
            print("  " + b, file=sys.stderr)
        return 2
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    runs = [create_run(root, ns.runs, i, ns, env) for i in range(1, ns.runs + 1)]
    pids = []
    for i, run_dir in enumerate(runs, 1):
        cmd = build_command(ns, prompt, run_dir)
        if ns.dry_run:
            print(f"run-{i}: cd {run_dir / 'work'} && {shlex.join(cmd)} > {root}/run-{i}.jsonl 2> {root}/run-{i}.err")
        else:
            p = start(cmd, run_dir, root / f"run-{i}.jsonl", root / f"run-{i}.err", env)
            pids.append(p.pid)
            print(f"run-{i}: pid {p.pid}")
    print(f"root: {root}")
    print("A run is finished when its run-N.jsonl has a line with \"type\":\"result\".")
    print("Then: python3 leak_audit.py <root>/run-N.jsonl --work <root>/run-N/work [--plugin <root>/run-N/plugin]")
    if ns.dry_run:
        print("dry run: nothing started")
    return 0


def _result_text(log):
    texts = []
    for line in Path(log).read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content") if isinstance(ev, dict) else None
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                texts.append(c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict)))
    return "\n".join(texts)


def _read_results(log):
    """File name -> text of the Read tool result, for each Read call in the log."""
    calls, out = {}, {}
    for line in Path(log).read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content") if isinstance(ev, dict) else None
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == "Read":
                calls[b.get("id")] = os.path.basename(str(b.get("input", {}).get("file_path", "")))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                c = b.get("content")
                out[calls[b["tool_use_id"]]] = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return out


def selftest(env):
    repo = _repo_root()
    if not repo or not (Path(repo) / "CLAUDE.md").is_file():
        print("selftest needs the repository's CLAUDE.md as the home-read target", file=sys.stderr)
        return 2
    root = Path(os.path.realpath(os.path.join(env.get("TMPDIR") or "/tmp", "herd-bench", f"selftest-{os.getpid()}")))
    ns = parse(["--name", "selftest", "--runs", "2", "--model", "claude-haiku-5-5", "--prompt", "-",
                "--herd-tag", "HEAD", "--budget", "1"])
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    try:
        runs = [create_run(root, 2, i, ns, env) for i in (1, 2)]
        r1, r2 = runs
        (r2 / "work" / "secret.txt").write_text("sibling secret\n")
        (root / "run-2.jsonl").write_text("sibling log\n")
        plugin = r1 / "plugin"
        (r1 / "work" / "probe.sh").write_text(
            f'echo "HOME $(cat {shlex.quote(repo + "/CLAUDE.md")} >/dev/null 2>&1 && echo READ || echo BLOCKED)"\n'
            f'echo "SIBLING $(cat {shlex.quote(str(r2 / "work" / "secret.txt"))} >/dev/null 2>&1 && echo READ || echo BLOCKED)"\n'
            f'echo "SIBLOG $(cat {shlex.quote(str(root / "run-2.jsonl"))} >/dev/null 2>&1 && echo READ || echo BLOCKED)"\n'
            f'echo "SKILL $(cat {shlex.quote(str(plugin / "skills/run/SKILL.md"))} >/dev/null 2>&1 && echo READ || echo BLOCKED)"\n'
            f'python3 {shlex.quote(str(plugin / "scripts/herd.py"))} status 2>&1 | grep -q "no active task" && echo "HERD ran" || echo "HERD failed"\n'
            'echo "NET $(curl -sS -m 10 -o /dev/null https://raw.githubusercontent.com/ >/dev/null 2>&1 && echo READ || echo BLOCKED)"\n'
            'git commit -q --allow-empty -m probe >/dev/null 2>&1 && echo "COMMIT OK" || echo "COMMIT failed"\n')
        cmd = build_command(ns, "Run exactly one Bash call: sh probe.sh. Then make two separate Read tool calls, first on "
                            f"{r2 / 'work' / 'secret.txt'} and second on {repo}/CLAUDE.md, even if the first is refused. Then stop.", r1)
        log = root / "run-1.jsonl"
        try:
            with open(log, "wb") as out:
                subprocess.run(cmd, cwd=r1 / "work", env=_git_env(r1, env), stdin=subprocess.DEVNULL, stdout=out,
                               stderr=subprocess.PIPE, timeout=300)
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"selftest: claude did not finish: {e}\nkept for inspection: {root}", file=sys.stderr)
            return 1
        text = _result_text(log)
        want = [("home read", "HOME BLOCKED"), ("sibling run read", "SIBLING BLOCKED"),
                ("sibling run log read", "SIBLOG BLOCKED"), ("network", "NET BLOCKED"),
                ("plugin SKILL.md read", "SKILL READ"), ("herd.py status", "HERD ran"), ("git commit in work", "COMMIT OK")]
        reads = _read_results(log)
        extra = [("Read tool, sibling run", "sibling secret" not in reads.get("secret.txt", "sibling secret") and "secret.txt" in reads),
                 ("Read tool, home", "herd-sdlc" not in reads.get("CLAUDE.md", "herd-sdlc") and "CLAUDE.md" in reads)]
        ok = True
        print("| probe | expected | result |\n| --- | --- | --- |")
        for label, marker in want:
            hit = re.search(rf"^{re.escape(marker)}$", text, re.M) is not None
            ok &= hit
            print(f"| {label} | {marker.split()[1]} | {'PASS' if hit else 'FAIL'} |")
        for label, hit in extra:
            ok &= hit
            print(f"| {label} | BLOCKED | {'PASS' if hit else 'FAIL'} |")
        print("selftest: " + ("ok" if ok else "FAILED"))
        if ok:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"kept for inspection: {root}", file=sys.stderr)
        return 0 if ok else 1
    except Exception:
        print(f"kept for inspection: {root}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
