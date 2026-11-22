import unittest

from scripts import herd_escalation as he

ROUNDS = {"trigger": "rounds", "step": 7, "findings": ["a1b2c3d4"],
          "options": [{"n": 1, "label": "one more round", "action": "continue_round"},
                      {"n": 2, "label": "proceed with the open findings listed", "action": "proceed_open"},
                      {"n": 3, "label": "stop", "action": "stop"}]}
BUDGET = {"trigger": "budget", "step": 7, "findings": [],
          "options": [{"n": 1, "label": "raise limits", "action": "raise_budget"},
                      {"n": 2, "label": "stop", "action": "stop"}]}
LOWC = {"trigger": "low_confidence", "step": 7, "findings": ["deadbeef"],
        "options": [{"n": 1, "label": "follow the Arbiter", "action": "follow_arbiter"},
                    {"n": 2, "label": "overrule it", "action": "overrule_arbiter"},
                    {"n": 3, "label": "stop", "action": "stop"}]}


def t(n):
    return f"2026-11-22T10:{n:02d}:00Z"


def ev(type_, at, **kw):
    return {"type": type_, "at": t(at), **kw}


def opened(at, issue, causes, repeat_of=None):
    return ev("issue_opened", at, issue=issue, kind="escalation", causes=causes, repeat_of=repeat_of)


def comment(at, issue, body, cid=1, maint=True, bot=False, edited=False):
    return ev("comment", at, issue=issue, id=cid, body=body, author="u", author_is_bot=bot,
              author_is_maintainer=maint, edited=edited)


def st(*events):
    return he.replay(list(events))


class TestStatus(unittest.TestCase):
    def test_status_table(self):
        cases = [
            ([], "running"),
            ([ev("label_added", 1, label="herd:hold")], "held"),
            ([opened(1, 10, [ROUNDS])], "awaiting_answer"),
            ([ev("label_added", 1, label="herd:hold"), opened(2, 10, [ROUNDS])], "held_and_awaiting"),
            ([ev("label_added", 1, label="herd:hold"), opened(2, 10, [ROUNDS]),
              ev("label_added", 3, label="herd:blocked")], "blocked"),
            ([ev("label_added", 1, label="herd:hold"), ev("label_removed", 2, label="herd:hold")], "running"),
        ]
        for events, want in cases:
            self.assertEqual(he.herd_status(st(*events)), want, events)

    def test_one_open_escalation(self):
        s = st(opened(1, 10, [LOWC]))
        self.assertEqual(he.next_escalation(s, "budget", 7), {"action": "append", "issue": 10, "repeat_of": None})
        s = st()
        self.assertEqual(he.next_escalation(s, "budget", 7)["action"], "open")

    def test_cause_added_extends_open_escalation(self):
        s = st(opened(1, 10, [LOWC]), ev("cause_added", 2, issue=10, cause=BUDGET))
        self.assertEqual([c["trigger"] for c in s["escalations"][0]["causes"]], ["low_confidence", "budget"])
        extra = dict(LOWC, findings=["cafe0001"])
        s = st(opened(1, 10, [LOWC]), ev("cause_added", 2, issue=10, cause=extra))
        self.assertEqual(s["escalations"][0]["causes"][0]["findings"], ["deadbeef", "cafe0001"])
        self.assertEqual(len(s["escalations"][0]["causes"]), 1)

    def test_parse_command(self):
        pc = lambda b, **kw: he.parse_command(b, kw.get("bot", False), kw.get("edited", False))
        self.assertEqual(pc("/herd hold")["name"], "hold")
        self.assertEqual(pc("/herd resume\nthanks")["name"], "resume")
        self.assertEqual(pc("/herd risk medium")["level"], "medium")
        self.assertEqual(pc("/herd answer rounds=1 budget=2")["pairs"], {"rounds": 1, "budget": 2})
        for bad in ("/herd risk urgent", "/herd answer", "/herd answer rounds=x", "/herd answer rounds=1 rounds=2",
                    "please /herd hold", "/herd  hold", "/herd hold now", "/herd"):
            self.assertIsNone(pc(bad), bad)

    def test_command_in_code_fence_ignored(self):
        self.assertIsNone(he.parse_command("```\n/herd hold\n```", False, False))
        self.assertIsNone(he.parse_command("> /herd hold", False, False))
        self.assertEqual(he.parse_command("```\ncode\n```\n/herd hold", False, False)["name"], "hold")

    def test_edited_and_bot_comments_ignored(self):
        self.assertIsNone(he.parse_command("/herd hold", False, True))
        self.assertIsNone(he.parse_command("/herd hold", True, False))

    def test_non_maintainer_ignored(self):
        s = st()
        r = he.apply_command(s, {"name": "hold", "pairs": {}, "level": None}, False)
        self.assertEqual(r, {"action": None, "reply": ""})

    def test_command_table(self):
        hold = {"name": "hold", "pairs": {}, "level": None}
        resume = {"name": "resume", "pairs": {}, "level": None}
        risk = {"name": "risk", "pairs": {}, "level": "low"}
        H = ev("label_added", 1, label="herd:hold")
        E = opened(2, 10, [ROUNDS])
        for events, cmd, action, in_reply in [
            ([], hold, "add_label", "next step boundary"),
            ([H], hold, None, "already held"),
            ([E], hold, "add_label", "next step boundary"),
            ([H, E], hold, None, "already held"),
            ([], resume, None, "not paused"),
            ([H], resume, "remove_label", ""),
            ([E], resume, None, "#10"),
            ([H, E], resume, "remove_label", "#10"),
            ([], risk, "set_risk", ""),
            ([H, E], risk, "set_risk", ""),
        ]:
            r = he.apply_command(st(*events), cmd, True)
            self.assertEqual(r["action"], action, (events, cmd))
            self.assertIn(in_reply.lower(), r["reply"].lower())
        blocked = st(ev("label_added", 1, label="herd:blocked"))
        for cmd in (hold, resume, risk):
            self.assertIsNone(he.apply_command(blocked, cmd, True)["action"])

    def test_hold_and_escalation_independent(self):
        H = ev("label_added", 1, label="herd:hold")
        E = opened(2, 10, [ROUNDS])
        s = st(H, E, ev("label_removed", 3, label="herd:hold"))
        self.assertEqual(he.herd_status(s), "awaiting_answer")
        s = st(H, E, comment(3, 10, "/herd answer rounds=1"))
        self.assertEqual(he.herd_status(s), "held")  # answer cleared the escalation, not the hold


class TestEscalation(unittest.TestCase):
    def test_parse_answer(self):
        self.assertTrue(he.parse_answer({"rounds": 1, "budget": 2}, [ROUNDS, BUDGET])[0])
        for pairs, causes in [({"rounds": 4}, [ROUNDS]),                      # not an option
                              ({"rounds": 1}, [ROUNDS, BUDGET]),              # a cause is missing
                              ({"rounds": 1, "budget": 1, "low_confidence": 1}, [ROUNDS, BUDGET]),  # extra
                              ({"rounds": 1, "other": 1}, [ROUNDS, BUDGET])]:  # unknown trigger
            ok, reply = he.parse_answer(pairs, causes)
            self.assertFalse(ok, pairs)
            self.assertIn("/herd answer", reply)
        ok, reply = he.parse_answer({"rounds": 4}, [ROUNDS])
        self.assertIn("1 one more round", reply)

    def test_answer_via_replay_and_touchpoints(self):
        s = st(opened(1, 10, [ROUNDS, BUDGET]),
               comment(2, 10, "/herd answer rounds=4 budget=1", cid=1),            # invalid
               comment(3, 10, "/herd answer rounds=1 budget=1", cid=2, maint=False),  # not a maintainer
               comment(4, 10, "/herd answer rounds=1 budget=1", cid=3, edited=True),  # edited
               comment(5, 10, "/herd answer rounds=1 budget=2", cid=4),            # valid
               comment(6, 10, "/herd answer rounds=2 budget=2", cid=5),            # second answer ignored
               ev("issue_closed", 7, issue=10))
        e = s["escalations"][0]
        self.assertEqual(e["answer"]["comment_id"], 4)
        self.assertEqual(e["answer"]["pairs"], {"rounds": 1, "budget": 2})
        self.assertEqual(he.herd_status(s), "running")
        self.assertEqual(he.touchpoints(s), {"opened": 1, "answered": 1, "open": 0, "repeats": 0, "rule": 1})

    def test_touchpoints_count_only_valid_answers(self):
        s = st(opened(1, 10, [ROUNDS]), comment(2, 10, "/herd answer rounds=9"), ev("issue_closed", 3, issue=10))
        self.assertEqual(he.touchpoints(s)["answered"], 0)
        self.assertEqual(he.touchpoints(s)["open"], 1)

    def test_closed_without_answer_stays_open(self):
        s = st(opened(1, 10, [ROUNDS]), ev("issue_closed", 2, issue=10))
        self.assertEqual(he.herd_status(s), "awaiting_answer")
        s = st(opened(1, 10, [ROUNDS]), ev("issue_closed", 2, issue=10), ev("issue_reopened", 3, issue=10))
        self.assertEqual(he.herd_status(s), "awaiting_answer")
        self.assertEqual(he.touchpoints(s)["answered"], 0)

    def test_answer_validated_against_causes_at_that_time(self):
        s = st(opened(1, 10, [LOWC]), comment(2, 10, "/herd answer low_confidence=1", cid=1),
               )
        self.assertIsNotNone(s["escalations"][0]["answer"])
        s = st(opened(1, 10, [LOWC]), ev("cause_added", 2, issue=10, cause=BUDGET),
               comment(3, 10, "/herd answer low_confidence=1", cid=1))
        self.assertIsNone(s["escalations"][0]["answer"])  # budget cause was added, so one pair is not enough

    def test_apply_answer_command(self):
        s = st(opened(1, 10, [ROUNDS]))
        cmd = {"name": "answer", "pairs": {"rounds": 1}, "level": None}
        self.assertEqual(he.apply_command(s, cmd, True, issue=10)["action"], "close_issue")
        bad = {"name": "answer", "pairs": {"rounds": 7}, "level": None}
        r = he.apply_command(s, bad, True, issue=10)
        self.assertIsNone(r["action"])
        self.assertIn("1 one more round", r["reply"])
        self.assertIsNone(he.apply_command(s, cmd, True, issue=99)["action"])
        self.assertIsNone(he.apply_command(st(), cmd, True, issue=10)["action"])

    def test_ceiling(self):
        events = [opened(1, 10, [ROUNDS]), comment(2, 10, "/herd answer rounds=1"),
                  opened(3, 11, [BUDGET]), comment(4, 11, "/herd answer budget=2"),
                  opened(5, 12, [LOWC]), comment(6, 12, "/herd answer low_confidence=1")]
        self.assertEqual(he.next_escalation(st(*events), "rounds", 9)["action"], "blocked")
        events += [ev("label_added", 7, label="herd:blocked"), ev("label_removed", 8, label="herd:blocked")]
        self.assertEqual(he.next_escalation(st(*events), "rounds", 9)["action"], "open")
        events += [opened(9, 13, [ROUNDS])]
        self.assertEqual(he.next_escalation(st(*events[:-1] + [events[-1], comment(10, 13, "/herd answer rounds=2")]),
                                             "budget", 9)["action"], "open")

    def test_ceiling_counts_unanswered_open_as_append(self):
        events = [opened(1, 10, [ROUNDS]), comment(2, 10, "/herd answer rounds=1"),
                  opened(3, 11, [BUDGET]), comment(4, 11, "/herd answer budget=2"),
                  opened(5, 12, [LOWC])]
        self.assertEqual(he.next_escalation(st(*events), "rounds", 9)["action"], "append")

    def test_repeat_of(self):
        events = [opened(1, 10, [ROUNDS]), comment(2, 10, "/herd answer rounds=1")]
        r = he.next_escalation(st(*events), "rounds", 7)
        self.assertEqual((r["action"], r["repeat_of"]), ("open", 10))
        r = he.next_escalation(st(*events), "rounds", 8)
        self.assertEqual(r["repeat_of"], None)
        s = st(*events, opened(3, 11, [ROUNDS], repeat_of=10))
        self.assertEqual(he.touchpoints(s)["repeats"], 1)

    def test_build_issue_body(self):
        body = he.build_issue_body(5, [ROUNDS, BUDGET])
        self.assertTrue(body.startswith("<!-- herd:escalation v1 feature=5 -->"))
        self.assertIn("- 1: one more round", body)
        self.assertIn("/herd answer rounds=<n> budget=<n>", body)
        self.assertIn("a1b2c3d4", body)
        self.assertNotIn("/herd answer rounds=1 budget=1 ", body.replace("<n>", ""))
        for line in body.splitlines()[1:]:
            self.assertFalse(line.startswith("/herd hold"))

    def test_effective_limits(self):
        base = {"rounds": 3, "tokens": 1000, "minutes": 60, "raise_by_pct": 50}
        self.assertEqual(he.effective_limits(st(), base), {"rounds": 3, "tokens": 1000, "minutes": 60})
        s = st(opened(1, 10, [ROUNDS, BUDGET]), comment(2, 10, "/herd answer rounds=1 budget=1"),
               opened(3, 11, [ROUNDS]), comment(4, 11, "/herd answer rounds=2"),
               opened(5, 12, [BUDGET]), comment(6, 12, "/herd answer budget=2"))
        self.assertEqual(he.effective_limits(s, base), {"rounds": 4, "tokens": 1500, "minutes": 90})

    def test_paused_seconds(self):
        events = [ev("label_added", 0, label="herd:hold"),       # 0..10 held
                  opened(5, 10, [ROUNDS]),                       # 5..20 awaiting (overlaps 5..10)
                  ev("label_removed", 10, label="herd:hold"),
                  comment(20, 10, "/herd answer rounds=1")]
        self.assertEqual(he.paused_seconds(events, t(30)), 20 * 60)
        self.assertEqual(he.paused_seconds([ev("label_added", 0, label="herd:hold")], t(3)), 180)
        self.assertEqual(he.paused_seconds([], t(3)), 0)


if __name__ == "__main__":
    unittest.main()
