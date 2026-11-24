"""Herd Escalation, hold and resume (M0). See docs/designs/herd-escalation.md.
Not wired into the CLI yet: a tested building block for the planned GitHub automation.

Standard library only. Pure functions: they take a list of GitHub events and return
values; the orchestrator does the `gh` calls.
"""
import re
from datetime import datetime

HOLD, BLOCKED = "herd:hold", "herd:blocked"
CEILING = 3
BASE_ROUNDS = 3
TOUCHPOINT_RULE = 1
_PAIR = re.compile(r"([a-z_]+)=(\d+)")


# ---- commands -------------------------------------------------------------

def parse_command(body, author_is_bot, edited):
    """First line outside code fences and quotes. None if bot, edited or not a command."""
    if author_is_bot or edited or not isinstance(body, str):
        return None
    fenced = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced or not s or s.startswith(">"):
            continue
        return _match_command(line)
    return None


def _match_command(line):
    line = line.rstrip()
    if line in ("/herd hold", "/herd resume"):
        return {"name": line[6:], "pairs": {}, "level": None}
    m = re.fullmatch(r"/herd risk (low|medium|high)", line)
    if m:
        return {"name": "risk", "pairs": {}, "level": m.group(1)}
    m = re.fullmatch(r"/herd answer ((?:[a-z_]+=\d+)(?: [a-z_]+=\d+)*)", line)
    if m:
        pairs = {}
        for k, v in _PAIR.findall(m.group(1)):
            if k in pairs:
                return None
            pairs[k] = int(v)
        return {"name": "answer", "pairs": pairs, "level": None}
    return None


def _options_text(causes):
    out = []
    for c in causes:
        out.append(f"{c['trigger']}: " + ", ".join(f"{o['n']} {o['label']}" for o in c["options"]))
    return "; ".join(out)


def parse_answer(pairs, causes):
    """Valid when the keys equal the triggers and each value is an option number."""
    triggers = {c["trigger"]: c for c in causes}
    if set(pairs) == set(triggers) and all(
            pairs[t] in {o["n"] for o in triggers[t]["options"]} for t in triggers):
        return True, ""
    syntax = " ".join(f"{c['trigger']}=<n>" for c in causes)
    return False, f"Answer with one option per cause: /herd answer {syntax}. Options: {_options_text(causes)}."


# ---- replay and status ----------------------------------------------------

def replay(events):  # noqa: C901
    """Replay events in order into {labels, escalations, blocked_removed_at}."""
    labels, escs, blocked_removed = set(), {}, None
    for e in events:
        k = e["type"]
        if k == "label_added":
            labels.add(e["label"])
        elif k == "label_removed":
            labels.discard(e["label"])
            if e["label"] == BLOCKED:
                blocked_removed = e["at"]
        elif k == "issue_opened" and e.get("kind") == "escalation":
            escs[e["issue"]] = {"number": e["issue"], "causes": [dict(c) for c in e.get("causes", [])],
                                "repeat_of": e.get("repeat_of"), "opened_at": e["at"],
                                "closed_at": None, "answer": None}
        elif k == "cause_added" and e["issue"] in escs:
            _add_cause(escs[e["issue"]], e["cause"])
        elif k == "issue_closed" and e["issue"] in escs:
            escs[e["issue"]]["closed_at"] = e["at"]
        elif k == "issue_reopened" and e["issue"] in escs:
            escs[e["issue"]]["closed_at"] = None
        elif k == "comment" and e["issue"] in escs:
            esc = escs[e["issue"]]
            if esc["answer"] is None and e.get("author_is_maintainer"):
                cmd = parse_command(e["body"], e.get("author_is_bot", False), e.get("edited", False))
                if cmd and cmd["name"] == "answer" and parse_answer(cmd["pairs"], esc["causes"])[0]:
                    esc["answer"] = {"actor": e["author"], "comment_id": e["id"],
                                     "pairs": cmd["pairs"], "at": e["at"]}
    return {"labels": labels, "escalations": list(escs.values()), "blocked_removed_at": blocked_removed}


def _add_cause(esc, cause):
    for c in esc["causes"]:
        if c["trigger"] == cause["trigger"]:
            c["findings"] = c.get("findings", []) + [f for f in cause.get("findings", []) if f not in c.get("findings", [])]
            return
    esc["causes"].append(dict(cause))


def _open(state):
    return [e for e in state["escalations"] if e["answer"] is None]


def herd_status(state):
    """blocked > held_and_awaiting > awaiting_answer > held > running."""
    held, awaiting = HOLD in state["labels"], bool(_open(state))
    if BLOCKED in state["labels"]:
        return "blocked"
    if held and awaiting:
        return "held_and_awaiting"
    if awaiting:
        return "awaiting_answer"
    return "held" if held else "running"


def apply_command(state, command, is_maintainer, issue=None):  # noqa: C901
    """Return {action, reply}. Non-maintainers and blocked features get no action."""
    none = {"action": None, "reply": ""}
    if not is_maintainer or command is None:
        return none
    status, name = herd_status(state), command["name"]
    if status == "blocked":
        return none
    open_ = _open(state)
    if name == "hold":
        if status in ("held", "held_and_awaiting"):
            return {"action": None, "reply": "Already held."}
        return {"action": "add_label", "reply": "Held. A step already running finishes; the hold takes effect at the next step boundary."}
    if name == "resume":
        if status == "running":
            return {"action": None, "reply": "Not paused."}
        names = ", ".join(f"#{e['number']}" for e in open_)
        if status == "held":
            return {"action": "remove_label", "reply": ""}
        if status == "awaiting_answer":
            return {"action": None, "reply": f"Answer the open escalation {names} first."}
        return {"action": "remove_label", "reply": f"Hold removed. Still waiting on {names}."}
    if name == "risk":
        return {"action": "set_risk", "reply": ""}
    if name == "answer":
        esc = next((e for e in open_ if e["number"] == issue), None)
        if esc is None:
            return none
        ok, reply = parse_answer(command["pairs"], esc["causes"])
        return {"action": "close_issue", "reply": ""} if ok else {"action": None, "reply": reply}
    return none


# ---- escalations ----------------------------------------------------------

def next_escalation(state, trigger, step):
    """append to the open escalation, open a new one, or blocked at the ceiling."""
    open_ = _open(state)
    if open_:
        return {"action": "append", "issue": open_[0]["number"], "repeat_of": None}
    since = state["blocked_removed_at"]
    opened = [e for e in state["escalations"] if since is None or e["opened_at"] > since]
    if len(opened) >= CEILING:
        return {"action": "blocked", "repeat_of": None}
    repeat = None
    for e in state["escalations"]:
        if e["answer"] and any(c["trigger"] == trigger and c.get("step") == step for c in e["causes"]):
            repeat = e["number"]
    return {"action": "open", "repeat_of": repeat}


def build_issue_body(feature, causes):
    """Fixed template, no model call. Only finding ids, never finding text."""
    lines = [f"<!-- herd:escalation v1 feature={feature} -->",
             f"Feature issue: #{feature}. This feature is paused until a maintainer answers.", ""]
    for c in causes:
        ids = ", ".join(c.get("findings", [])) or "none"
        lines.append(f"Cause `{c['trigger']}` (step {c.get('step', '?')}, finding ids: {ids})")
        lines += [f"- {o['n']}: {o['label']}" for o in c["options"]]
        lines.append("")
    syntax = " ".join(f"{c['trigger']}=<n>" for c in causes)
    lines.append(f"Answer in a comment with one option per cause: `/herd answer {syntax}`")
    return "\n".join(lines) + "\n"


def _answered_actions(state, trigger):
    for e in state["escalations"]:
        if e["answer"] and trigger in e["answer"]["pairs"]:
            n = e["answer"]["pairs"][trigger]
            cause = next(c for c in e["causes"] if c["trigger"] == trigger)
            yield next(o["action"] for o in cause["options"] if o["n"] == n)


def effective_limits(state, base):
    """Round cap and budget limits, derived from answered escalations."""
    rounds = base.get("rounds", BASE_ROUNDS) + sum(a == "continue_round" for a in _answered_actions(state, "rounds"))
    k = sum(a == "raise_budget" for a in _answered_actions(state, "budget"))
    factor = (1 + base.get("raise_by_pct", 0) / 100) ** k
    out = {"rounds": rounds}
    for key in ("tokens", "minutes"):
        if key in base:
            out[key] = base[key] * factor
            if out[key] == int(out[key]):
                out[key] = int(out[key])
    return out


def touchpoints(state):
    escs = state["escalations"]
    return {"opened": len(escs), "answered": sum(e["answer"] is not None for e in escs),
            "open": len(_open(state)), "repeats": sum(e["repeat_of"] is not None for e in escs),
            "rule": TOUCHPOINT_RULE}


# ---- budget ---------------------------------------------------------------

def _ts(s):
    return datetime.fromisoformat(s).timestamp()


def paused_seconds(events, now):
    """Length of the union of hold intervals and open-escalation intervals."""
    intervals, hold_start = [], None
    for e in events:
        if e["type"] == "label_added" and e["label"] == HOLD and hold_start is None:
            hold_start = e["at"]
        elif e["type"] == "label_removed" and e["label"] == HOLD and hold_start is not None:
            intervals.append((_ts(hold_start), _ts(e["at"])))
            hold_start = None
    if hold_start is not None:
        intervals.append((_ts(hold_start), _ts(now)))
    for esc in replay(events)["escalations"]:
        end = esc["answer"]["at"] if esc["answer"] else now
        intervals.append((_ts(esc["opened_at"]), _ts(end)))
    total, cur_end = 0.0, None
    for a, b in sorted(intervals):
        if cur_end is None or a > cur_end:
            total += b - a
            cur_end = b
        elif b > cur_end:
            total += b - cur_end
            cur_end = b
    return int(total)
