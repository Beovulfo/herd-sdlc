"""Herd Arbiter (M0): orchestrator-side validation and logging.
See docs/designs/herd-arbiter.md. Standard library only; reads no config file.
"""
import hashlib
import json
import re

SEVERITIES = ("Nit", "Major", "Blocker")
VERDICTS = ("accept", "contest", "decline", "escalate")
REASON_MAX = 140


def _norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def _sha(text, n):
    return hashlib.sha1(text.encode()).hexdigest()[:n]


def finding_id(text):
    return _sha(_norm(text), 8)


def quote_sha(quote):
    return _sha(_norm(quote), 12)


def merge_findings(findings):
    """Merge findings with the same normalised text. Highest severity wins."""
    out = {}
    for f in findings:
        fid = finding_id(f["text"])
        if fid not in out:
            out[fid] = {"id": fid, "personas": [], "severity": f["severity"],
                        "scope": f.get("scope", ""), "text": f["text"]}
        m = out[fid]
        if f["persona"] not in m["personas"]:
            m["personas"].append(f["persona"])
        if SEVERITIES.index(f["severity"]) > SEVERITIES.index(m["severity"]):
            m["severity"] = f["severity"]
    return list(out.values())


def build_input(rubric, spec, prior, findings):
    """Rubric first (outside data), then spec, prior rulings, findings in data blocks."""
    prior_lines = [json.dumps({"id": k, **v}) for k, v in sorted(prior.items())]
    blocks = [f'<data kind="spec">\n{spec}\n</data>',
              f'<data kind="prior_rulings">\n' + "\n".join(prior_lines) + "\n</data>",
              '<data kind="findings">\n' + "\n".join(
                  json.dumps({"id": f["id"], "severity": f["severity"], "scope": f["scope"], "text": f["text"]})
                  for f in findings) + "\n</data>"]
    return rubric.rstrip() + "\n\n" + "\n\n".join(blocks) + "\n"


def _clean_reason(reason):
    return re.sub(r"[\r\n|]+", " ", str(reason))[:REASON_MAX]


def _schema_ok(o):
    if not isinstance(o, dict) or not isinstance(o.get("id"), str):
        return False
    if o.get("verdict") not in VERDICTS or o.get("confidence") not in ("H", "L"):
        return False
    if not isinstance(o.get("reason"), str):
        return False
    c = o.get("citation")
    if c is not None and not (isinstance(c, dict) and isinstance(c.get("path"), str)
                              and isinstance(c.get("start"), int) and isinstance(c.get("end"), int)
                              and isinstance(c.get("quote", ""), str)):
        return False
    return True


def _citation_ok(c, spec_path, spec_lines):
    if not c or c["path"] != spec_path or not c.get("quote"):
        return False
    if not (1 <= c["start"] <= c["end"] <= len(spec_lines)):
        return False
    cited = _norm(" ".join(spec_lines[c["start"] - 1:c["end"]]))
    return _norm(c["quote"]) in cited


def _row(f, verdict, arbiter_verdict, cause, conf, citation, reason):
    quote = (citation or {}).get("quote")
    return {"id": f["id"], "personas": f["personas"], "severity": f["severity"],
            "verdict": verdict, "arbiter_verdict": arbiter_verdict, "cause": cause, "conf": conf,
            "citation": {k: citation[k] for k in ("path", "start", "end")} if citation else None,
            "quote_sha": quote_sha(quote) if quote else None,
            "reason": _clean_reason(reason),
            "effective": verdict == "accept" or (verdict in ("decline", "contest") and f["severity"] == "Nit")}


def validate(findings, raw_output, spec_path, spec_lines, prior):
    """One ruling per finding after the policy checks. Never raises.

    If the whole output is unparseable every ruling has cause `malformed`; the caller
    re-asks the Arbiter once (when all rulings are malformed) and validates again.
    """
    def esc(f, cause, reason=""):
        return _row(f, "escalate", "escalate", cause, "L", None, reason)
    try:
        data = json.loads(raw_output)
        if not isinstance(data, list):
            raise ValueError("not a list")
    except (ValueError, TypeError):
        return [esc(f, "malformed") for f in findings]
    ids = {f["id"] for f in findings}
    seen, dup, objs = set(), set(), {}
    for o in data:
        oid = o.get("id") if isinstance(o, dict) else None
        if oid not in ids:
            continue  # unknown id: ignored, the finding it should have ruled becomes `missing`
        if oid in seen:
            dup.add(oid)
        seen.add(oid)
        objs.setdefault(oid, o)
    out = []
    for f in findings:
        o = objs.get(f["id"])
        if o is None:
            out.append(esc(f, "missing"))
        elif f["id"] in dup:
            out.append(esc(f, "duplicate"))
        elif not _schema_ok(o):
            out.append(esc(f, "malformed"))
        else:
            out.append(_judge(f, o, spec_path, spec_lines, prior))
    return out


def _judge(f, o, spec_path, spec_lines, prior):
    verdict, conf, cit, reason = o["verdict"], o["confidence"], o.get("citation"), o["reason"]
    def esc(cause):
        return _row(f, "escalate", verdict, cause, conf, cit if verdict != "escalate" else None, reason)
    if conf == "L":
        return esc("low_confidence")
    if verdict == "escalate":
        return _row(f, "escalate", "escalate", "arbiter", conf, None, reason)
    if verdict in ("decline", "contest") and f["severity"] != "Nit":
        return esc("policy")
    if not _citation_ok(cit, spec_path, spec_lines):
        return esc("citation")
    p = prior.get(f["id"])
    if p and p["arbiter_verdict"] != verdict and p["quote_sha"] == quote_sha(cit["quote"]):
        return esc("flip")
    return _row(f, verdict, verdict, None, conf, cit, reason)


def make_header(round_no, arbiter_model, elephant_model, rubric_text, spec_text):
    same = arbiter_model in (None, "inherit") or arbiter_model == elephant_model
    return {"type": "header", "round": round_no,
            "arbiter_model": None if arbiter_model in (None, "inherit") else arbiter_model,
            "elephant_model": elephant_model, "same_model": same,
            "rubric_sha": _sha(rubric_text, 12), "spec_sha": _sha(spec_text, 12)}


def format_lines(rulings, header):
    lines = [json.dumps(header)]
    for r in rulings:
        rec = {"type": "ruling", "round": header["round"]}
        rec.update({k: r[k] for k in ("id", "personas", "severity", "verdict", "arbiter_verdict",
                                      "cause", "conf", "citation", "quote_sha", "reason", "effective")})
        lines.append(json.dumps(rec))
    return lines


def _records(lines):
    for line in lines:
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def prior_from_lines(lines, round_no):
    return {r["id"]: {"arbiter_verdict": r["arbiter_verdict"], "quote_sha": r["quote_sha"]}
            for r in _records(lines) if r.get("type") == "ruling" and r.get("round") == round_no}


def needs_audit(finding_id, feature_index):
    """Every ruling for the first 5 features, then ids whose hex value is divisible by 4."""
    return feature_index <= 5 or int(finding_id, 16) % 4 == 0


def overturn_rate(lines):
    """Stats per same_model flag. Escalated rulings are not in the denominator."""
    same_by_round, rulings, audits = {}, {}, {}
    for r in _records(lines):
        if r.get("type") == "header":
            same_by_round[r["round"]] = r["same_model"]
        elif r.get("type") == "ruling":
            rulings[r["id"]] = r
        elif r.get("type") == "audit":
            audits[r["id"]] = r["result"]
    stats = {k: {"total": 0, "esc": 0, "n": 0, "overturned": 0, "bm_n": 0, "bm_overturned": 0}
             for k in ("same", "different")}
    for fid, r in rulings.items():
        s = stats["same" if same_by_round.get(r["round"], True) else "different"]
        s["total"] += 1
        if r["verdict"] == "escalate":
            s["esc"] += 1
            continue
        if fid not in audits or not r["effective"]:
            continue
        over = audits[fid] == "overturned"
        s["n"] += 1
        s["overturned"] += over
        if r["severity"] != "Nit":
            s["bm_n"] += 1
            s["bm_overturned"] += over
    for s in stats.values():
        s["rate"] = s["overturned"] / s["n"] if s["n"] else None
        s["bm_rate"] = s["bm_overturned"] / s["bm_n"] if s["bm_n"] else None
        s["escalate_rate"] = s["esc"] / s["total"] if s["total"] else None
        del s["total"], s["esc"]
    return stats


def summary(lines):
    """Plain-text block for the spec PR. Never a link."""
    rs = [r for r in _records(lines) if r.get("type") == "ruling"]
    counts = {}
    for r in rs:
        counts[(r["verdict"], r["severity"])] = counts.get((r["verdict"], r["severity"]), 0) + 1
    out = ["Arbiter rulings: " + (", ".join(f"{v} {s}: {n}" for (v, s), n in sorted(counts.items())) or "none")]
    for r in rs:
        if r["verdict"] == "escalate":
            out.append(f"escalate {r['id']} {r['severity']} cause={r['cause']} arbiter_verdict={r['arbiter_verdict']}: {r['reason']}")
    for r in rs:
        if r["verdict"] == "accept" and r["severity"] != "Nit":
            out.append(f"accepted {r['id']} {r['severity']}: {r['reason']}")
    return "\n".join(out)
