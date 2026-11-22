import json
import os
import tempfile
import unittest

from scripts import herd_triage as ht

RULES = {"high": ["migrations/**", "auth/**", "billing/**", "herd.toml"], "medium": ["api/**"]}
TOML = '[floor]\nhigh = ["migrations/**", "auth/**"]\nmedium = ["api/**"]\n'
NOW = "2026-11-22T10:00:00Z"


class TestFloor(unittest.TestCase):
    def test_extract_paths(self):
        body = "Edit `migrations/0001_init.sql.` and ./api/v1/users.py, see util.py"
        self.assertEqual(ht.extract_paths(body, ["py", "sql"]),
                         ["migrations/0001_init.sql", "api/v1/users.py", "util.py"])

    def test_path_normalisation(self):
        body = "a//b/c.py ./x/y.py ../up/z.py /abs/p.py"
        self.assertEqual(ht.extract_paths(body, ["py"]), ["a/b/c.py", "x/y.py"])

    def test_floor_hit(self):
        self.assertEqual(ht.floor(["migrations/0001_init.sql"], {}, RULES),
                         ("high", ["migrations/**"], "issue_text"))

    def test_highest_wins(self):
        lvl, rules, _ = ht.floor(["api/x.py", "auth/y.py"], {}, RULES)
        self.assertEqual((lvl, rules), ("high", ["auth/**", "api/**"]))

    def test_star_does_not_cross_slash(self):
        rules = {"high": ["auth/*"], "medium": []}
        self.assertEqual(ht.floor(["auth/deep/x.py"], {}, rules)[0], "medium")

    def test_case_sensitive(self):
        self.assertEqual(ht.floor(["Migrations/x.sql"], {}, RULES)[0], "medium")

    def test_no_path(self):
        self.assertEqual(ht.floor([], {}, RULES), ("medium", [], "default"))

    def test_low_label(self):
        self.assertEqual(ht.floor(["docs/readme.md"], {"risk:low": "maintainer"}, RULES),
                         ("low", [], "label"))

    def test_low_label_from_non_maintainer_ignored(self):
        self.assertEqual(ht.floor(["docs/readme.md"], {"risk:low": "other"}, RULES)[0], "medium")

    def test_rule_match_beats_low_label(self):
        self.assertEqual(ht.floor(["auth/x.py"], {"risk:low": "maintainer"}, RULES)[0], "high")

    def test_label_raises(self):
        self.assertEqual(ht.floor([], {"risk:high": "other"}, RULES), ("high", [], "label"))
        self.assertEqual(ht.floor(["docs/a.md"], {"risk:medium": "other"}, RULES)[0], "medium")


class TestRecord(unittest.TestCase):
    def build(self, body="touch migrations/0001_init.sql", labels=None, toml=TOML, prior=None):
        return ht.build_record("f1", 7, body, labels or {}, toml, prior)

    def test_record_shape(self):
        r = self.build()
        self.assertEqual(r["schema_version"], 1)
        self.assertEqual((r["status"], r["cause"]), ("ok", None))
        self.assertEqual(r["risk"]["floor"], "high")
        self.assertEqual(r["risk"]["effective"], "high")
        self.assertIsNone(r["risk"]["override"])
        self.assertNotIn("touch", json.dumps(r))  # no issue text in the record

    def test_no_path(self):
        r = self.build(body="users cannot log in")
        self.assertEqual((r["risk"]["floor"], r["risk"]["floor_inputs"]["source"]), ("medium", "default"))

    def test_fallback_cases(self):
        for toml, cause in [(None, "herd_toml"), ("not = [valid", "herd_toml"),
                            ('[floor]\nhigh = ["a/**"]\nbogus = 1\n', "herd_toml"),
                            ('[floor]\nhigh = "a/**"\n', "herd_toml")]:
            r = self.build(toml=toml)
            self.assertEqual((r["status"], r["cause"], r["risk"]["effective"]), ("fallback", cause, "high"), toml)

    def test_other_top_level_keys_ignored(self):
        r = self.build(toml=TOML + '\n[arbiter]\nmodel = "inherit"\n[budget]\ntokens = 1\n')
        self.assertEqual(r["status"], "ok")

    def test_default_rules_when_no_floor_block(self):
        r = self.build(toml='[arbiter]\nmodel = "inherit"\n', body="see billing/x.py")
        self.assertEqual((r["status"], r["risk"]["floor"]), ("ok", "high"))

    def test_override_recorded(self):
        r = ht.apply_override(self.build(), "medium", "maintainer1", 42, NOW)
        self.assertEqual(r["risk"]["effective"], "medium")
        self.assertEqual(r["risk"]["override"],
                         {"actor": "maintainer1", "comment_id": 42, "from": "high", "to": "medium", "time": NOW})

    def test_override_bad_level(self):
        with self.assertRaises(ValueError):
            ht.apply_override(self.build(), "urgent", "m", 1, NOW)

    def test_triage_keeps_override_and_unknown_keys(self):
        prior = ht.apply_override(self.build(), "low", "m", 1, NOW)
        prior["round"] = 2  # a key owned by another design
        r = self.build(prior=prior)
        self.assertEqual(r["risk"]["effective"], "low")
        self.assertEqual(r["risk"]["override"]["to"], "low")
        self.assertEqual(r["round"], 2)

    def test_prior_with_bad_schema_version(self):
        for prior in ({"feature": "f1"}, {"schema_version": 0}):
            r = self.build(prior=prior)
            self.assertEqual((r["status"], r["cause"], r["risk"]["effective"]), ("fallback", "schema", "high"))

    def test_unknown_enum_in_prior_is_high(self):
        prior = self.build()
        prior["risk"]["override"] = {"actor": "m", "comment_id": 1, "from": "high", "to": "urgent", "time": NOW}
        self.assertEqual(ht.effective_of(prior), "high")

    def test_never_raises(self):
        r = ht.build_record("f", 1, None, {}, TOML, None)  # body is not a str
        self.assertEqual((r["status"], r["cause"]), ("fallback", "error"))

    def test_write_record_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f1.json")
            ht.write_record(p, self.build())
            with open(p) as f:
                self.assertEqual(json.load(f)["feature"], "f1")
            self.assertEqual(os.listdir(d), ["f1.json"])


if __name__ == "__main__":
    unittest.main()
