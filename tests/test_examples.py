"""Tests that the runnable examples actually run end-to-end."""
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "examples")


def load_example(name):
    """Import examples/<name>.py as a module (without executing main)."""
    path = os.path.join(EXAMPLES_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location(f"example_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExamples(unittest.TestCase):
    def _run(self, name):
        module = load_example(name)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = module.main()
        return rc, buf.getvalue()

    def test_customer_support(self):
        rc, out = self._run("customer_support")
        self.assertEqual(rc, 0)
        self.assertIn("chain intact", out)
        self.assertIn("blocked", out)  # the injection attempt is denied

    def test_coding_agent(self):
        rc, out = self._run("coding_agent")
        self.assertEqual(rc, 0)
        self.assertIn("budget cut the agent off", out)

    def test_red_team(self):
        rc, out = self._run("red_team")
        self.assertEqual(rc, 0)
        self.assertIn("red-team score", out)
        self.assertIn("report written to", out)

    def test_sample_policies_load(self):
        from agent_guardian import PolicyEngine
        base = os.path.join(EXAMPLES_DIR, "policies")
        yaml_policy = PolicyEngine.from_file(
            os.path.join(base, "support_policy.yaml"))
        self.assertTrue(yaml_policy.check("hello").allowed)
        json_policy = PolicyEngine.from_file(
            os.path.join(base, "strict_policy.json"))
        self.assertFalse(json_policy.check("drop table users").allowed)


if __name__ == "__main__":
    unittest.main()
