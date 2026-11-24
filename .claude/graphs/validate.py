"""Check every graph: edges point at existing nodes, side-effect nodes are reached only through a gate,
and every node is reachable from start. Exits 1 on any problem.

ponytail: a regex parse of the one-line-per-node YAML style used here (the standard library has no YAML
parser); switch to a real parser if graphs ever nest.
Same rules as the blackboard-reviewer validator this format comes from.
"""
import re
import sys
from pathlib import Path

EDGES = ("next", "pass", "fail", "approve", "edit", "skip", "on_exhausted")
TYPES = ("act", "think", "check", "gate", "sub", "end")


def problems(text):
    """List of problems in one graph's text (empty when it is valid)."""
    nodes = dict(re.findall(r"^  (\w+):\s*(\{.*\})\s*$", text, re.M))
    start = re.search(r"^start:\s*(\w+)", text, re.M)
    if not start:
        return ["no start"]
    start = start.group(1)
    edges = {n: re.findall(r"\b(?:%s):\s*(\w+)" % "|".join(EDGES), body) for n, body in nodes.items()}
    out = [f"{start}: start is not a node"] if start not in nodes else []
    out += [f"{n}: edge to missing node {e}" for n, es in edges.items() for e in es if e not in nodes]
    out += [f"{n}: unknown type" for n, b in nodes.items() if not re.search(r"type: (%s)\b" % "|".join(TYPES), b)]
    out += [f"{n}: {b.count('{') - b.count('}')} unclosed brace" for n, b in nodes.items() if b.count("{") != b.count("}")]
    side = {n for n, b in nodes.items() if "side_effect: true" in b}
    gate = {n for n, b in nodes.items() if "type: gate" in b}
    # a side-effect node is entered from a gate, from another side-effect node, or as a check's retry (fail edge)
    out += [f"{p} -> {s}: side effect not behind a gate" for p, es in edges.items() for s in es
            if s in side and p not in gate | side and not re.search(r"fail:\s*%s\b" % s, nodes[p])]
    seen, todo = set(), [start]
    while todo:
        n = todo.pop()
        if n in seen or n not in nodes:
            continue
        seen.add(n)
        todo += edges[n]
    out += [f"{n}: unreachable" for n in sorted(set(nodes) - seen)]
    if not any("type: end" in nodes[n] for n in seen):
        out.append("no reachable end node")
    return out


def main(folder):
    ok = True
    for f in sorted(Path(folder).glob("*.yaml")):
        found = problems(f.read_text(encoding="utf-8"))
        print(f"{f.name}: " + ("ok" if not found else "; ".join(found)))
        ok = ok and not found
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent))
