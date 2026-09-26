"""Tests for agent_guardian.audit."""
import json
import os
import tempfile
import unittest

from agent_guardian.audit import AuditLog, verify_log


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "audit.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_verify(self):
        log = AuditLog(self.path, agent_id="test-agent")
        log.append("agent_call", {"prompt": "hi"})
        log.append("agent_call", {"prompt": "hello"})
        self.assertEqual(len(log), 2)
        result = verify_log(self.path)
        self.assertTrue(result.ok)
        self.assertEqual(result.records_checked, 2)

    def test_chain_links(self):
        log = AuditLog(self.path)
        r1 = log.append("a", {})
        r2 = log.append("b", {})
        self.assertEqual(r2["prev"], r1["hash"])
        self.assertNotEqual(r1["hash"], r2["hash"])

    def test_tamper_detection(self):
        log = AuditLog(self.path)
        log.append("agent_call", {"output": "original"})
        log.append("agent_call", {"output": "second"})
        # tamper with the first record's payload
        with open(self.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        record = json.loads(lines[0])
        record["payload"]["output"] = "forged"
        lines[0] = json.dumps(record) + "\n"
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        result = verify_log(self.path)
        self.assertFalse(result.ok)
        self.assertEqual(result.first_bad_seq, 1)

    def test_deletion_detected(self):
        log = AuditLog(self.path)
        log.append("a", {})
        log.append("b", {})
        log.append("c", {})
        with open(self.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.writelines([lines[0], lines[2]])  # drop the middle record
        result = verify_log(self.path)
        self.assertFalse(result.ok)

    def test_append_resumes_existing_log(self):
        log = AuditLog(self.path)
        log.append("a", {})
        log2 = AuditLog(self.path)  # new handle, same file
        log2.append("b", {})
        result = verify_log(self.path)
        self.assertTrue(result.ok)
        self.assertEqual(result.records_checked, 2)

    def test_verify_missing_file(self):
        result = verify_log(os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertFalse(result.ok)

    def test_iter_records(self):
        log = AuditLog(self.path)
        log.append("x", {"n": 1})
        log.append("y", {"n": 2})
        kinds = [r["kind"] for r in log.iter_records()]
        self.assertEqual(kinds, ["x", "y"])


if __name__ == "__main__":
    unittest.main()
