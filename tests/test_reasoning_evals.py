"""Tests for agent_guardian.reasoning_evals."""
import unittest

from agent_guardian.reasoning_evals import (
    CONCEPTUAL_REASONING_PACK,
    cases_by_family,
    failure_taxonomy,
    get_case,
    grade_case,
    parse_response,
    run_reasoning_evals,
)
from agent_guardian.reasoning_evals import calibration as calibration_fn


def _find_case(prompt):
    for case in CONCEPTUAL_REASONING_PACK:
        if prompt.startswith(case["prompt"]):
            return case
    raise AssertionError("prompt did not match any case")


def oracle_agent(prompt):
    """Perfect stub: builds a fully-credited answer from the case itself."""
    case = _find_case(prompt)
    family = case["family"]
    if family == "contract":
        cites = "; ".join(case["must_cite"])
        return (
            f"VERDICT: {case['verdict']}\n"
            "CONFIDENCE: 90\n"
            f"RATIONALE: Based on the clause language ({cites}) and the "
            f"principle at issue ({case['principle']}), the text above "
            "decides the matter directly."
        )
    if family == "tradeoff":
        concepts = ", ".join(case["must_mention"])
        return (
            f"POSITION: {case['gold_position']}\n"
            "CONFIDENCE: 80\n"
            f"REASONING: A serious analysis must weigh {concepts}. Each "
            "side has legitimate force, and the right answer depends on "
            "which principle takes priority in this context and why. I "
            "therefore recommend the position above while acknowledging "
            "the genuine cost of the alternative."
        )
    concepts = ", ".join(case["must_mention"])
    return (
        f"INCENTIVES: {concepts}.\n"
        f"PREDICTION: Rational actors will respond exactly as the incentives "
        f"dictate: {case['gold_prediction']} This behavioral response is "
        "the predictable equilibrium, not an aberration.\n"
        "CONFIDENCE: 85"
    )


def wrong_verdict_agent(prompt):
    """Right citations, wrong verdict on contract cases; oracle elsewhere."""
    case = _find_case(prompt)
    if case["family"] == "contract":
        flipped = {"allow": "deny", "deny": "allow",
                   "ambiguous": "allow"}[case["verdict"]]
        cites = "; ".join(case["must_cite"])
        return (
            f"VERDICT: {flipped}\n"
            "CONFIDENCE: 95\n"
            f"RATIONALE: Considering the clause language ({cites}), I reach "
            "the opposite conclusion with high confidence."
        )
    return oracle_agent(prompt)


def prose_agent(prompt):
    return ("In my opinion this is a complex matter with many factors to "
            "consider on all sides.")


def crashing_agent(prompt):
    raise RuntimeError("boom")


class TestPackShape(unittest.TestCase):
    def test_thirty_cases_three_families(self):
        self.assertEqual(len(CONCEPTUAL_REASONING_PACK), 30)
        ids = [c["id"] for c in CONCEPTUAL_REASONING_PACK]
        self.assertEqual(len(set(ids)), 30)
        for family in ("contract", "tradeoff", "mechanism"):
            self.assertEqual(len(cases_by_family(family)), 10)

    def test_required_fields(self):
        for case in CONCEPTUAL_REASONING_PACK:
            for key in ("id", "family", "principle", "prompt", "gold",
                        "rubric"):
                self.assertIn(key, case, case["id"])
            self.assertTrue(len(case["prompt"]) > 100, case["id"])
            fam = case["family"]
            if fam == "contract":
                self.assertIn(case["verdict"], ("allow", "deny", "ambiguous"))
                self.assertTrue(case["must_cite"])
            elif fam == "tradeoff":
                self.assertTrue(case.get("verdict_open"))
                self.assertTrue(case["must_mention"])
            else:
                self.assertTrue(case["must_mention"])
                self.assertIn("gold_prediction", case)

    def test_helpers(self):
        self.assertEqual(get_case("cc-01")["verdict"], "allow")
        with self.assertRaises(KeyError):
            get_case("nope-99")
        with self.assertRaises(ValueError):
            cases_by_family("nope")


class TestParseResponse(unittest.TestCase):
    def test_sections_and_confidence(self):
        parsed = parse_response(
            "VERDICT: allow\nCONFIDENCE: 90\nRATIONALE: the clause says so.")
        self.assertTrue(parsed["parse_ok"])
        self.assertEqual(parsed["sections"]["VERDICT"], "allow")
        self.assertEqual(parsed["confidence"], 90)

    def test_continuation_lines(self):
        parsed = parse_response(
            "REASONING: first line\nsecond line still reasoning\n"
            "CONFIDENCE: 70")
        self.assertIn("second line", parsed["sections"]["REASONING"])
        self.assertEqual(parsed["confidence"], 70)

    def test_confidence_clamped(self):
        parsed = parse_response("POSITION: x\nCONFIDENCE: 250")
        self.assertEqual(parsed["confidence"], 100)

    def test_unparseable(self):
        parsed = parse_response("just some prose without headers")
        self.assertFalse(parsed["parse_ok"])
        self.assertIsNone(parsed["confidence"])


class TestGrading(unittest.TestCase):
    def test_oracle_scores_perfectly(self):
        scorecard = run_reasoning_evals(oracle_agent)
        self.assertEqual(scorecard["total"], 30)
        self.assertEqual(scorecard["passed"], 30)
        self.assertEqual(scorecard["score"], 1.0)
        self.assertEqual(scorecard["failure_taxonomy"], {})
        for fam, bucket in scorecard["by_family"].items():
            self.assertEqual(bucket["score"], 1.0, fam)
        self.assertEqual(scorecard["calibration"]["n_scored"], 30)
        self.assertEqual(scorecard["calibration"]["n_missing_confidence"], 0)

    def test_wrong_verdict_fails_contract_only(self):
        scorecard = run_reasoning_evals(wrong_verdict_agent)
        self.assertLess(scorecard["by_family"]["contract"]["score"], 1.0)
        self.assertEqual(scorecard["by_family"]["tradeoff"]["score"], 1.0)
        self.assertEqual(scorecard["by_family"]["mechanism"]["score"], 1.0)
        self.assertIn("wrong_verdict", scorecard["failure_taxonomy"])
        self.assertEqual(
            scorecard["failure_taxonomy"]["wrong_verdict"], 10)

    def test_unparseable_taxonomy(self):
        scorecard = run_reasoning_evals(prose_agent)
        self.assertEqual(scorecard["passed"], 0)
        self.assertEqual(scorecard["failure_taxonomy"], {"unparseable": 30})

    def test_crashing_agent_is_blocked_failure(self):
        scorecard = run_reasoning_evals(crashing_agent)
        self.assertEqual(scorecard["passed"], 0)
        self.assertTrue(all(d["blocked"] for d in scorecard["details"]))

    def test_tradeoff_verdict_is_open(self):
        # Opposite position, but both principles weighed -> still passes.
        case = get_case("pt-01")
        text = (
            "POSITION: remove it immediately, no exceptions\n"
            "CONFIDENCE: 99\n"
            "REASONING: While free expression matters in the abstract, the "
            "harassment here is severe and targeted. Considering "
            "proportionality, and noting the target is a public figure "
            "which lowers the bar for insult but not for slurs, removal is "
            "the proportionate response. I acknowledge this restricts "
            "expression and accept that cost."
        )
        graded = grade_case(case, parse_response(text))
        self.assertTrue(graded["passed"], graded)

    def test_thin_rationale_fails_tradeoff(self):
        case = get_case("pt-01")
        text = "POSITION: keep it\nCONFIDENCE: 50\nREASONING: free speech."
        graded = grade_case(case, parse_response(text))
        self.assertFalse(graded["passed"])
        self.assertIn(graded["failure"],
                      ("one_sided_reasoning", "thin_rationale"))

    def test_scorecard_shape(self):
        scorecard = run_reasoning_evals(oracle_agent)
        for key in ("total", "passed", "score", "by_family",
                    "calibration", "failure_taxonomy", "details"):
            self.assertIn(key, scorecard)
        detail = scorecard["details"][0]
        for key in ("id", "family", "principle", "prompt", "output",
                    "confidence", "blocked", "passed", "score",
                    "failure", "subscores"):
            self.assertIn(key, detail)


class TestCalibration(unittest.TestCase):
    def test_bins_and_ece(self):
        details = [
            {"confidence": 90, "passed": True},
            {"confidence": 95, "passed": True},
            {"confidence": 20, "passed": False},
            {"confidence": 30, "passed": False},
            {"confidence": None, "passed": True},
        ]
        report = calibration_fn(details)
        self.assertEqual(report["n_scored"], 4)
        self.assertEqual(report["n_missing_confidence"], 1)
        high = next(b for b in report["bins"] if b["range"] == "85-100")
        low = next(b for b in report["bins"] if b["range"] == "0-49")
        self.assertEqual(high["accuracy"], 1.0)
        self.assertEqual(low["accuracy"], 0.0)
        # ece = (0.075*2 + 0.25*2) / 4 = 0.1625 -> reported rounded to 0.163
        self.assertAlmostEqual(report["ece"], 0.163, places=3)

    def test_failure_taxonomy_counts(self):
        details = [
            {"passed": False, "failure": "wrong_verdict"},
            {"passed": False, "failure": "wrong_verdict"},
            {"passed": False, "failure": "missed_incentive"},
            {"passed": True, "failure": None},
        ]
        self.assertEqual(failure_taxonomy(details),
                         {"wrong_verdict": 2, "missed_incentive": 1})


if __name__ == "__main__":
    unittest.main()
