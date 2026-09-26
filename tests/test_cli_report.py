"""Tests for agent_guardian.report and agent_guardian.cli."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from agent_guardian import (
    AgentGuardianError,
    TargetLoadError,
    render_report,
    run_evals,
    verify_log,
)
from agent_guardian.audit import AuditLog
from agent_guardian.cli import build_parser, load_target, main


def echo_agent(prompt):
    return f"Echo: {prompt}"


class TestRenderReport(unittest.TestCase):
    def test_report_sections(self):
        scorecard = run_evals(echo_agent)
        report = render_report(scorecard)
        for section in ("## Summary", "## Score by category",
                        "## Failed cases", "Overall score"):
            self.assertIn(section, report)
        for category in ("jailbreak", "benign"):
            self.assertIn(category, report)

    def test_report_with_audit_log(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "a.jsonl")
            AuditLog(path).append("agent_call", {"x": 1})
            report = render_report(run_evals(echo_agent), audit_path=path)
            self.assertIn("## Audit log", report)
            self.assertIn("Chain intact:** yes", report)
        finally:
            tmp.cleanup()

    def test_report_tampered_log_flagged(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "a.jsonl")
            log = AuditLog(path)
            log.append("agent_call", {"x": 1})
            # Tamper robustly: parse the record, alter the payload, rewrite.
            with open(path, encoding="utf-8") as fh:
                record = json.loads(fh.read().strip())
            record["payload"]["x"] = 2
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            self.assertFalse(verify_log(path).ok)
            report = render_report(run_evals(echo_agent), audit_path=path)
            self.assertIn("Chain intact:** NO", report)
        finally:
            tmp.cleanup()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # a tiny importable agent module for --target
        self.mod_path = os.path.join(self.tmp.name, "demo_agent.py")
        with open(self.mod_path, "w", encoding="utf-8") as fh:
            fh.write("def agent(prompt: str) -> str:\n"
                     "    return 'demo says: ' + prompt\n")
        sys.path.insert(0, self.tmp.name)

    def tearDown(self):
        sys.path.remove(self.tmp.name)
        for mod in ("demo_agent",):
            sys.modules.pop(mod, None)
        self.tmp.cleanup()

    def test_load_target(self):
        fn = load_target("demo_agent:agent")
        self.assertEqual(fn("hi"), "demo says: hi")

    def test_load_target_bad_format(self):
        with self.assertRaises(TargetLoadError):
            load_target("no-colon-here")
        # the taxonomy still funnels into the package base exception
        try:
            load_target("no-colon-here")
        except AgentGuardianError as exc:
            self.assertIsInstance(exc, TargetLoadError)
        else:
            self.fail("TargetLoadError not raised")

    def test_audit_writes_report(self):
        out = os.path.join(self.tmp.name, "report.md")
        log = os.path.join(self.tmp.name, "audit.jsonl")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["audit", "--target", "demo_agent:agent",
                       "--out", out, "--audit-log", log])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(out))
        self.assertTrue(os.path.exists(log))
        with open(out, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("# Agent Governance Report", content)
        self.assertIn("## Audit log", content)
        self.assertIn("score:", buf.getvalue())

    def test_audit_with_policy_file(self):
        policy_path = os.path.join(self.tmp.name, "policy.json")
        with open(policy_path, "w", encoding="utf-8") as fh:
            json.dump({"blocked_phrases": ["banned-word"]}, fh)
        out = os.path.join(self.tmp.name, "report.md")
        rc = main(["audit", "--target", "demo_agent:agent",
                   "--policy", policy_path, "--out", out,
                   "--audit-log", os.path.join(self.tmp.name, "a2.jsonl")])
        self.assertEqual(rc, 0)

    def test_verify_log_ok(self):
        path = os.path.join(self.tmp.name, "v.jsonl")
        AuditLog(path).append("agent_call", {"x": 1})
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["verify-log", "--path", path])
        self.assertEqual(rc, 0)
        self.assertIn("ok:", buf.getvalue())

    def test_verify_log_tampered(self):
        path = os.path.join(self.tmp.name, "v2.jsonl")
        AuditLog(path).append("agent_call", {"x": 1})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("not json at all\n")
        with redirect_stdout(io.StringIO()):
            rc = main(["verify-log", "--path", path])
        self.assertEqual(rc, 1)

    def test_parser_help_lists_subcommands(self):
        parser = build_parser()
        for sub in ("audit", "verify-log"):
            self.assertIn(sub, parser._subparsers._group_actions[0].choices)


if __name__ == "__main__":
    unittest.main()
