import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate import fixtures, check
from src.agent import run
from src.model import MockModel
from src.tools import Tools, ToolError


class ScriptModel:
    mode, name = "mock", "adversarial-script"

    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, request, observations):
        return next(self.decisions)


def action(name, **args):
    return {"action": name, "args": args, "reason": "adversarial test"}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "drafts.db"
        self.cases = fixtures()

    def run_case(self, name, model=None, **kwargs):
        case = self.cases[name]
        return run(case["request"], case["world"], self.db, model or MockModel(), **kwargs)

    def test_acceptance_cases(self):
        for name in self.cases:
            if name == "all_slots_occupied":
                continue
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                case = self.cases[name]
                db = Path(temp) / "drafts.db"
                output = run(case["request"], case["world"], db, MockModel())
                if name == "duplicate":
                    first = output
                    output = run(case["request"], case["world"], db, MockModel())
                    output["first_execution"] = first
                self.assertEqual(check(name, output), [])

    def test_cannot_claim_success_without_saving(self):
        output = self.run_case("normal", ScriptModel([action("finish", status="completed", message="已发布并保存")]))
        self.assertEqual(output["status"], "incomplete")
        self.assertFalse(output["draft"]["saved"])
        self.assertNotIn("已发布", output["message"])

    def test_cannot_save_without_review(self):
        out = self.run_case("normal", ScriptModel([action("save_draft", suggested_at="2026-11-10T18:00:00+08:00"), action("finish", status="completed")]))
        self.assertEqual(out["trace"][0]["result"]["error"], "REVIEW_NOT_PASSED")
        self.assertFalse(out["draft"]["saved"])

    def test_cannot_forge_confirmation(self):
        case = self.cases["slot_conflict"]
        tool = Tools(case["request"], case["world"], self.db)
        tool.execute("read_material", {})
        tool.execute("check_rules", {})
        tool.execute("query_slots", {})
        with self.assertRaises(ToolError):
            tool.execute("save_draft", {"suggested_at": "2026-11-10T19:00:00+08:00", "confirmed": True})
        result = tool.execute("save_draft", {"suggested_at": "2026-11-10T19:00:00+08:00"})
        self.assertEqual(result["confirmation_status"], "pending_hard_requirement_change")
        self.assertFalse(result["reserved"])

    def test_recheck_conflict_at_save(self):
        case = self.cases["normal"]
        tool = Tools(case["request"], case["world"], self.db)
        for name in ("read_material", "check_rules", "query_slots"):
            tool.execute(name, {})
        case["world"]["schedule"].append({"at": case["request"]["requested_at"], "channel": "short-video"})
        with self.assertRaisesRegex(ToolError, "SLOT_CONFLICT_AT_SAVE"):
            tool.execute("save_draft", {"suggested_at": case["request"]["requested_at"]})
        self.assertEqual(tool.count(), 0)

    def test_confirmed_drafts_conflict_across_requests(self):
        self.run_case("normal")
        self.cases["normal"]["request"]["request_id"] = "second"
        output = self.run_case("normal")
        self.assertEqual(output["status"], "needs_confirmation")
        self.assertEqual(output["suggested_at"], "2026-11-10T19:00:00+08:00")

    def test_idempotency_payload_mismatch(self):
        self.run_case("normal")
        self.cases["normal"]["request"]["material_id"] = "different"
        out = self.run_case("normal")
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["message"], "IDEMPOTENCY_KEY_CONFLICT")

    def test_step_limit_retains_honest_state(self):
        out = self.run_case("normal", max_steps=1)
        self.assertEqual(out["status"], "incomplete")
        self.assertFalse(out["draft"]["saved"])

    def test_tool_limit(self):
        out = self.run_case("normal", max_tools=1)
        self.assertEqual(out["status"], "incomplete")
        self.assertEqual(len(out["trace"]), 1)

    def test_invalid_request_timezone(self):
        self.cases["normal"]["request"]["requested_at"] = "2026-11-10T18:00:00"
        self.assertEqual(self.run_case("normal")["status"], "needs_info")

    def test_timestamp_spelling_cannot_create_false_change(self):
        self.cases["normal"]["request"]["requested_at"] = "2026-11-10T18:00+08:00"
        self.assertEqual(self.run_case("normal")["status"], "needs_info")

    def test_duplicate_returns_exact_same_draft(self):
        first = self.run_case("normal")
        second = self.run_case("normal")
        self.assertEqual(first["draft"]["draft_id"], second["draft"]["draft_id"])
        self.assertFalse(second["draft"]["availability_revalidated"])

    def test_model_claim_cannot_override_pending_confirmation(self):
        decisions = [action("read_material"), action("check_rules"), action("query_slots"), action("save_draft", suggested_at="2026-11-10T19:00:00+08:00"), action("finish", status="completed", message="用户已同意")]
        out = self.run_case("slot_conflict", ScriptModel(decisions))
        self.assertEqual(out["status"], "needs_confirmation")
        self.assertFalse(out["draft"]["reserved"])

    def test_rule_changes_affect_outcome(self):
        self.cases["normal"]["world"]["rules"]["blocked_terms"].append("字幕")
        out = self.run_case("normal")
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(out["draft_count"], 0)

    def test_failed_insert_rolls_back(self):
        from unittest.mock import patch
        case = self.cases["normal"]
        tool = Tools(case["request"], case["world"], self.db)
        for name in ("read_material", "check_rules", "query_slots"):
            tool.execute(name, {})
        with tool.connect() as conn:
            conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON drafts BEGIN SELECT RAISE(ABORT, 'disk failure simulation'); END")
        with self.assertRaises(sqlite3.Error):
            tool.save(case["request"]["requested_at"])
        self.assertEqual(tool.count(), 0)

    def test_missing_request_fields(self):
        del self.cases["normal"]["request"]["hard_requirement"]
        self.assertEqual(self.run_case("normal")["status"], "needs_info")

    def test_invalid_model_action(self):
        out = self.run_case("normal", ScriptModel([{"args": "bad"}]))
        self.assertEqual(out["status"], "failed")

    def test_failed_model_no_mock_fallback(self):
        class Broken(MockModel):
            mode = "live"
            def decide(self, req, observations):
                raise RuntimeError("MODEL_HTTP_401")
        out = self.run_case("normal", Broken())
        self.assertEqual(out["mode"], "live")
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["draft_count"], 0)
        self.assertIn("model unavailable; scenario was not exercised", check("save_failure", out))

    def test_provider_error_exposes_only_allowlisted_code(self):
        import io
        import urllib.error
        from unittest.mock import patch
        from src.model import LiveModel
        cases = [(b'{"error":{"code":"insufficient_quota","message":"private detail"}}', "MODEL_HTTP_429:insufficient_quota"), (b'{"error":{"code":"credit_balance_exhausted"}}', "MODEL_HTTP_429:credit_balance_exhausted"), (b'{"error":{"code":"private detail"}}', "MODEL_HTTP_429"), (b'not json', "MODEL_HTTP_429")]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-unit-test-key"}):
            model = LiveModel()
            for body, expected in cases:
                with self.subTest(expected=expected):
                    error = urllib.error.HTTPError(model.url, 429, "quota", {}, io.BytesIO(body))
                    with patch("urllib.request.urlopen", side_effect=error):
                        with self.assertRaises(RuntimeError) as caught:
                            model.decide({}, [])
                    self.assertEqual(str(caught.exception), expected)


if __name__ == "__main__":
    unittest.main()
