"""Smoke test for benchmarks/bench.py (tiny N; not a perf assertion)."""
import importlib.util
import os
import unittest

BENCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "benchmarks", "bench.py")


def load_bench():
    spec = importlib.util.spec_from_file_location("bench", BENCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBenchmarks(unittest.TestCase):
    def test_bench_run_returns_sane_numbers(self):
        bench = load_bench()
        results = bench.run(calls=20, appends=20, repeats=1)
        self.assertEqual(set(results),
                         {"wrap_overhead_us", "audit_appends_per_sec",
                          "eval_suite_seconds"})
        self.assertGreaterEqual(results["wrap_overhead_us"], 0.0)
        self.assertGreater(results["audit_appends_per_sec"], 0.0)
        self.assertGreaterEqual(results["eval_suite_seconds"], 0.0)

    def test_bench_main_exits_zero(self):
        bench = load_bench()
        self.assertEqual(
            bench.main(["--calls", "20", "--appends", "20",
                        "--repeats", "1"]), 0)


if __name__ == "__main__":
    unittest.main()
