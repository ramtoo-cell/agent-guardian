"""Tests for AuditLog concurrency: threads and multi-process writers."""
import json
import os
import tempfile
import threading
import unittest

from agent_guardian.audit import AuditLog, verify_log


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_appends_stay_consistent(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "audit.jsonl")
            log = AuditLog(path, agent_id="t")
            threads, per_thread = 8, 25
            errors = []

            def worker(n):
                try:
                    for i in range(per_thread):
                        log.append("event", {"thread": n, "i": i})
                except Exception as exc:  # record, don't swallow
                    errors.append(exc)

            runners = [threading.Thread(target=worker, args=(n,))
                       for n in range(threads)]
            for r in runners:
                r.start()
            for r in runners:
                r.join()

            self.assertEqual(errors, [])
            total = threads * per_thread
            self.assertEqual(len(log), total)
            result = verify_log(path)
            self.assertTrue(result.ok, result.message)
            self.assertEqual(result.records_checked, total)
            # sequence numbers unique and contiguous
            with open(path, encoding="utf-8") as fh:
                seqs = [json.loads(line)["seq"] for line in fh]
            self.assertEqual(sorted(seqs), list(range(1, total + 1)))
        finally:
            tmp.cleanup()

    def test_two_instances_same_file(self):
        # Simulates two processes: separate AuditLog objects, one file.
        # The file lock + tail re-read must keep seq unique.
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "audit.jsonl")
            log_a = AuditLog(path, agent_id="a")
            log_b = AuditLog(path, agent_id="b")
            for i in range(10):
                (log_a if i % 2 == 0 else log_b).append("event", {"i": i})
            result = verify_log(path)
            self.assertTrue(result.ok, result.message)
            self.assertEqual(result.records_checked, 10)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
