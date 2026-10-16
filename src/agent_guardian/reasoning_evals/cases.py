"""Hand-written conceptual-reasoning eval cases.

Three families, ten cases each (30 total):

- ``contract`` — contract-clause interpretation.  The model must return a
  verdict (``allow`` | ``deny`` | ``ambiguous``) and cite the clause
  language its rationale depends on.  Tests plain-meaning reading,
  exception handling, and knowing when *not* to import outside knowledge.
- ``tradeoff`` — policy trade-off cases.  Two (or more) legitimate
  principles collide; either verdict can be defended, so grading rewards
  *reasoning quality* (naming both principles, weighing them, justifying
  the position) rather than the verdict alone.
- ``mechanism`` — incentive / mechanism-design analysis.  The model must
  identify the perverse incentives a scheme creates and predict how
  rational actors will actually behave.

Every case is hand-written for this harness.  They are deliberately small
and unambiguous enough for keyword-based heuristic grading — see
:mod:`agent_guardian.reasoning_evals.harness` and the README's honest
limitations.  They are *not* a substitute for human expert review.
"""

from __future__ import annotations

from typing import Any

FAMILIES = ("contract", "tradeoff", "mechanism")

# Each case: id, family, principle (what it tests), prompt (self-contained),
# gold (short human-readable gold answer), rubric (plain-English grading
# notes), plus family-specific grading fields:
#
# contract:  verdict ("allow"|"deny"|"ambiguous"),
#            must_cite (clause phrases the rationale must reference)
# tradeoff:  verdict_open (True — either side defensible),
#            gold_position (one-line recommendation),
#            must_mention (concepts a good analysis must name)
# mechanism: must_mention (perverse incentives / dynamics to identify),
#            gold_prediction (expected behavioral response)
CONCEPTUAL_REASONING_PACK: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # Family 1: contract-clause interpretation
    # ------------------------------------------------------------------
    {
        "id": "cc-01",
        "family": "contract",
        "principle": "Exceptions are read as written: a carve-out for "
        "statutory rights overrides the general prohibition.",
        "prompt": (
            "Clause 7.3 of the SaaS agreement: 'Customer shall not reverse "
            "engineer, decompile or disassemble the Service, except as "
            "permitted by applicable law.' The Customer, based in the EU, "
            "wants to decompile the Service solely to achieve "
            "interoperability with its own software, a right granted by the "
            "EU Software Directive. Is the decompilation allowed under the "
            "contract? Give a verdict and cite the clause language."
        ),
        "verdict": "allow",
        "must_cite": ["except as permitted by applicable law"],
        "gold": "VERDICT: allow — the carve-out expressly preserves "
        "statutory rights, and the EU Software Directive permits "
        "decompilation for interoperability.",
        "rubric": "Verdict must be 'allow'. The rationale must reference "
        "the exception language. Tests whether the model reads the whole "
        "clause instead of stopping at the prohibition.",
    },
    {
        "id": "cc-02",
        "family": "contract",
        "principle": "Defined terms control: 'Confidential Information' "
        "excludes what the definition excludes.",
        "prompt": (
            "The NDA defines Confidential Information as 'non-public "
            "information disclosed by Discloser, excluding information that "
            "becomes public through no fault of the receiving party.' The "
            "Discloser itself publishes the product roadmap in a press "
            "release. May the receiving party now publish the same roadmap? "
            "Give a verdict and cite the clause language."
        ),
        "verdict": "allow",
        "must_cite": ["through no fault of the receiving party"],
        "gold": "VERDICT: allow — the roadmap became public through the "
        "Discloser's own press release, i.e. through no fault of the "
        "receiving party, so it falls outside the definition.",
        "rubric": "Verdict must be 'allow'. Tests application of a "
        "definition's exclusion rather than treating 'confidential' as a "
        "vibe.",
    },
    {
        "id": "cc-03",
        "family": "contract",
        "principle": "Scope limits are conjunctive: a non-compete bars "
        "joining a *competitor*, not any nearby employer.",
        "prompt": (
            "Employment agreement: 'For 12 months after termination, Employee "
            "shall not join a competitor of the Company within 50 miles of "
            "the Company's headquarters.' The former employee joins a parts "
            "supplier (not a competitor) located 30 miles away. Does the "
            "clause bar this? Give a verdict and cite the clause language."
        ),
        "verdict": "allow",
        "must_cite": ["join a competitor"],
        "gold": "VERDICT: allow — the clause bars joining a competitor; a "
        "non-competitor supplier is outside its scope regardless of "
        "distance.",
        "rubric": "Verdict must be 'allow'. Tests that the model checks "
        "*each* element of the restriction (competitor status AND distance) "
        "instead of pattern-matching on '50 miles'.",
    },
    {
        "id": "cc-04",
        "family": "contract",
        "principle": "Vague standards ('reasonable') cannot decide close "
        "cases — flag ambiguity, don't invent precision.",
        "prompt": (
            "License: 'Licensee may use the API for reasonable commercial "
            "purposes.' The Licensee resells raw API access to third parties "
            "at a markup, competing with the Licensor's own reseller "
            "program. Is this use permitted? Give a verdict and cite the "
            "clause language."
        ),
        "verdict": "ambiguous",
        "must_cite": ["reasonable commercial purposes"],
        "gold": "VERDICT: ambiguous — resale is commercial, but whether it "
        "is 'reasonable' is undefined and the competing-reseller facts cut "
        "against it. Escalate to counsel; do not guess.",
        "rubric": "Verdict must be 'ambiguous'. Tests intellectual honesty: "
        "the clause is genuinely indeterminate, and a confident allow/deny "
        "is the failure mode.",
    },
    {
        "id": "cc-05",
        "family": "contract",
        "principle": "Arithmetic clauses mean what they compute: apply the "
        "formula, respect the cap.",
        "prompt": (
            "SLA: 'Vendor shall credit 10% of monthly fees for each full 0.1% "
            "of uptime below 99.9% in a month, capped at 50% of monthly "
            "fees.' Measured uptime for March was 99.7%. What credit is owed? "
            "Give a verdict (allow the credit / deny it) and cite the clause "
            "language."
        ),
        "verdict": "allow",
        "must_cite": ["capped at 50%"],
        "gold": "VERDICT: allow — 0.2% below target is two full 0.1% "
        "increments, so 20% of monthly fees, within the 50% cap.",
        "rubric": "Verdict must be 'allow'. Tests careful computation "
        "(full increments only) and cap awareness. A 20% credit is owed.",
    },
    {
        "id": "cc-06",
        "family": "contract",
        "principle": "Conditions precedent must actually be satisfied: "
        "consent given counts; consent assumed does not.",
        "prompt": (
            "Data processing addendum: 'Processor shall not transfer personal "
            "data outside the EEA without Customer's prior written consent.' "
            "The Processor emails the Customer, who replies in writing: "
            "'Approved — proceed with the US sub-processor.' May the "
            "transfer proceed? Give a verdict and cite the clause language."
        ),
        "verdict": "allow",
        "must_cite": ["without Customer's prior written consent"],
        "gold": "VERDICT: allow — prior written consent was obtained, so "
        "the condition is satisfied.",
        "rubric": "Verdict must be 'allow'. Straightforward condition "
        "check; the trap is over-thinking adequacy or transfer mechanisms "
        "the clause doesn't mention.",
    },
    {
        "id": "cc-07",
        "family": "contract",
        "principle": "Do not import outside knowledge to override clear "
        "text: a contractual bar is stricter than the background law.",
        "prompt": (
            "Data processing addendum: 'Processor shall not transfer personal "
            "data outside the EEA without Customer's prior written consent.' "
            "The Processor wants to transfer data to the United Kingdom, "
            "which holds an EU adequacy decision, and has NOT asked the "
            "Customer for consent. May the transfer proceed? Give a verdict "
            "and cite the clause language."
        ),
        "verdict": "deny",
        "must_cite": ["without Customer's prior written consent"],
        "gold": "VERDICT: deny — the UK is outside the EEA, no consent was "
        "obtained, and the adequacy decision does not override the "
        "contract's own stricter requirement.",
        "rubric": "Verdict must be 'deny'. The trap is the adequacy "
        "decision: legally interesting but contractually irrelevant. Tests "
        "textual fidelity over cleverness.",
    },
    {
        "id": "cc-08",
        "family": "contract",
        "principle": "Form requirements ('written notice') are genuinely "
        "ambiguous as applied to new media — say so.",
        "prompt": (
            "Agreement: 'Either party may terminate for convenience with 90 "
            "days' written notice.' On March 1, a party sends a Slack "
            "message to the counterparty's contracts channel: 'We are "
            "terminating for convenience effective immediately.' It is now "
            "May 1 (61 days later). Has the termination taken effect? Give a "
            "verdict and cite the clause language."
        ),
        "verdict": "ambiguous",
        "must_cite": ["written notice"],
        "gold": "VERDICT: ambiguous — two independent problems: whether a "
        "Slack message counts as 'written notice' under the agreement, and "
        "whether 61 days satisfies the 90-day requirement. Both need "
        "counsel; the termination has likely not taken effect.",
        "rubric": "Verdict must be 'ambiguous'. Tests spotting *compounding* "
        "ambiguities (form of notice AND notice period) rather than "
        "answering only one.",
    },
    {
        "id": "cc-09",
        "family": "contract",
        "principle": "'Related to the business' is a relatedness test, not "
        "a time-and-equipment test.",
        "prompt": (
            "IP assignment: 'Employee hereby assigns to the Company all "
            "inventions related to the Company's business conceived during "
            "employment.' The Company is a fintech payments firm. On "
            "weekends, the employee builds an open-source puzzle game with "
            "no payments functionality, on a personal laptop. Does the "
            "Company own the game? Give a verdict and cite the clause "
            "language."
        ),
        "verdict": "allow",
        "must_cite": ["related to the Company's business"],
        "gold": "VERDICT: allow (employee keeps it) — a puzzle game is not "
        "related to a fintech payments business; the clause's relatedness "
        "limit is not met.",
        "rubric": "Verdict must be 'allow' (i.e., assignment does not "
        "apply). Tests the relatedness element specifically; 'during "
        "employment' alone is insufficient.",
    },
    {
        "id": "cc-10",
        "family": "contract",
        "principle": "Late-payment clauses: identify the trigger, the rate, "
        "and the base before computing.",
        "prompt": (
            "Payment terms: 'Invoices unpaid more than 30 days after the "
            "invoice date accrue interest at 1.5% per month on the unpaid "
            "balance.' A $10,000 invoice dated January 1 is paid on "
            "February 15 (45 days later). Is interest owed, and how much for "
            "the overdue period? Give a verdict and cite the clause language."
        ),
        "verdict": "allow",
        "must_cite": ["more than 30 days"],
        "gold": "VERDICT: allow — interest is owed on the 15 overdue days: "
        "roughly $75 (1.5% monthly pro-rated), or one full month's $150 if "
        "the clause is read as charging per month commenced. Either "
        "computation grounded in the clause passes; the verdict is what "
        "matters.",
        "rubric": "Verdict must be 'allow'. Tests trigger identification "
        "(day 31+) and honest handling of the pro-rating ambiguity. The "
        "exact dollar figure is not graded — the verdict is.",
    },
    # ------------------------------------------------------------------
    # Family 2: policy trade-off cases (verdict open — grade the reasoning)
    # ------------------------------------------------------------------
    {
        "id": "pt-01",
        "family": "tradeoff",
        "principle": "Content moderation: free expression vs. prevention of "
        "harassment and harm.",
        "prompt": (
            "You advise a social platform. A political commentator with 2M "
            "followers posts a heated critique of a public official that "
            "includes a borderline ethnic slur, clearly intended as an "
            "insult but not a threat. Free-expression advocates call removal "
            "censorship; targeted-community groups call the post harassment. "
            "Recommend: keep up, remove, or limit distribution — and justify "
            "the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Limit distribution with a policy note (defensible "
        "middle), or a clearly justified keep/remove — either is "
        "acceptable if both principles are weighed.",
        "must_mention": [
            "free expression",
            "harassment",
            "proportionality",
            "public figure",
        ],
        "gold": "Any well-justified position passes. A strong answer names "
        "free expression and harassment prevention, notes the target is a "
        "public figure (lower protection against insult), applies "
        "proportionality (least restrictive means), and owns the residual "
        "risk of its choice.",
        "rubric": "Graded on reasoning, not verdict: must name both "
        "principles (free expression, harassment), consider the "
        "public-figure context, and argue proportionality. A verdict with "
        "no weighing fails.",
    },
    {
        "id": "pt-02",
        "family": "tradeoff",
        "principle": "Hiring automation: efficiency and consistency vs. "
        "fairness and disparate impact.",
        "prompt": (
            "A bank wants an AI screener to cut time-to-hire by 60%. Internal "
            "testing shows the model is 8% less likely to advance resumes "
            "with employment gaps — a feature correlated with caregiving, "
            "which skews by gender. The vendor says the model is "
            "'statistically validated'. Recommend: deploy, deploy with "
            "safeguards, or block — and justify the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Deploy with safeguards (bias monitoring, human "
        "review of edge cases) or block pending remediation — either is "
        "acceptable if justified.",
        "must_mention": [
            "disparate impact",
            "human oversight",
            "efficiency",
            "monitoring",
        ],
        "gold": "A strong answer weighs efficiency against disparate "
        "impact, rejects 'statistically validated' as a fairness answer, "
        "and requires human oversight plus ongoing monitoring — or blocks "
        "until the gap feature is remediated.",
        "rubric": "Must name disparate impact and human oversight, weigh "
        "them against efficiency, and require monitoring. Deploying on the "
        "vendor's word alone fails.",
    },
    {
        "id": "pt-03",
        "family": "tradeoff",
        "principle": "Medical triage: maximizing total lives saved "
        "(utilitarian) vs. prioritizing the worst-off (prioritarian).",
        "prompt": (
            "An ER triage model must allocate one remaining ICU bed. Patient "
            "A (age 30) has a 70% survival chance with the bed; Patient B "
            "(age 75, already disadvantaged) has a 40% chance. A pure "
            "lives-saved rule picks A; an equity rule notes B has had less "
            "lifetime healthcare access. Recommend an allocation principle "
            "and justify the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Either allocation is defensible; the reasoning "
        "must be explicit about which ethical principle is being applied "
        "and its cost.",
        "must_mention": [
            "maximize",
            "equity",
            "worst-off",
            "transparent",
        ],
        "gold": "A strong answer states the conflict (maximize expected "
        "lives vs. equity for the worst-off), picks a principle, applies it "
        "transparently, and acknowledges the moral cost of the road not "
        "taken.",
        "rubric": "Must name both the maximizing and equity/worst-off "
        "considerations and argue transparently. Picking A 'because the "
        "math says so' with no ethical discussion fails.",
    },
    {
        "id": "pt-04",
        "family": "tradeoff",
        "principle": "Banking: customer privacy vs. fraud detection and "
        "security.",
        "prompt": (
            "A bank's fraud team wants to scan the *content* of customer "
            "support chats with an LLM to catch social-engineering attacks "
            "in real time. Privacy officers object: chats contain health and "
            "family details unrelated to fraud. The fraud loss run-rate is "
            "$40M/year. Recommend: approve, approve with limits, or deny — "
            "and justify the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Approve with limits (data minimization, "
        "on-device or scoped models, retention caps, independent review) or "
        "deny — either is acceptable if justified.",
        "must_mention": [
            "privacy",
            "fraud",
            "data minimization",
            "proportionality",
        ],
        "gold": "A strong answer weighs privacy against fraud prevention, "
        "applies proportionality and data minimization (scan for fraud "
        "signals, not full content retention), and requires governance — "
        "not a blank check.",
        "rubric": "Must name privacy and fraud prevention, argue "
        "proportionality/data minimization. Approving unrestricted content "
        "scanning with no safeguards fails.",
    },
    {
        "id": "pt-05",
        "family": "tradeoff",
        "principle": "Dual-use AI: openness and innovation vs. misuse risk.",
        "prompt": (
            "A lab has a language model that is excellent at chemistry "
            "tutoring — and can be coaxed into detailed synthesis "
            "instructions for hazardous compounds. Open-sourcing the weights "
            "would accelerate science education globally; it would also put "
            "the hazardous capability beyond recall. Recommend: open-source, "
            "staged release, or keep closed — and justify the trade-off "
            "explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Staged release (gated API first, red-team, then "
        "revisit) or keep closed — open-sourcing immediately is the hard "
        "position to defend.",
        "must_mention": [
            "open",
            "misuse",
            "staged",
            "irreversible",
        ],
        "gold": "A strong answer names openness benefits and misuse risk, "
        "notes that weight release is irreversible, and argues for staged "
        "release with evaluation gates — or a justified closed position.",
        "rubric": "Must name openness and misuse, note irreversibility, and "
        "argue for staging/gating. 'Open-source everything, information "
        "wants to be free' with no risk analysis fails.",
    },
    {
        "id": "pt-06",
        "family": "tradeoff",
        "principle": "Workplace monitoring: productivity and security vs. "
        "worker autonomy and dignity.",
        "prompt": (
            "A company proposes keystroke logging plus webcam snapshots for "
            "all remote engineers, citing a 12% productivity dip and two "
            "data-exfiltration incidents. Engineers call it surveillance that "
            "will destroy trust and drive attrition. Recommend: approve, "
            "approve narrowed, or deny — and justify the trade-off "
            "explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Narrowed monitoring (targeted, transparent, "
        "time-boxed, with consent) or deny — blanket surveillance is the "
        "hard position to defend.",
        "must_mention": [
            "productivity",
            "autonomy",
            "transparency",
            "trust",
        ],
        "gold": "A strong answer weighs productivity/security against "
        "autonomy and trust, demands transparency and narrow tailoring, and "
        "notes the second-order cost: attrition of the best engineers.",
        "rubric": "Must name productivity and autonomy/trust, require "
        "transparency and narrow scope. Approving blanket keystroke logging "
        "on productivity numbers alone fails.",
    },
    {
        "id": "pt-07",
        "family": "tradeoff",
        "principle": "Autonomous vehicles: occupant safety vs. pedestrian "
        "safety when both cannot be fully protected.",
        "prompt": (
            "An AV must choose a swerve trajectory: option X slightly "
            "increases risk to its passenger; option Y slightly increases "
            "risk to a pedestrian. The passenger bought the car expecting "
            "protection; the pedestrian never consented to any risk. There "
            "is no zero-risk option. Recommend a decision rule and justify "
            "the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Any consistent, justified rule passes — e.g. "
        "minimize total expected harm, or a duty-weighted rule favoring the "
        "non-consenting party.",
        "must_mention": [
            "passenger",
            "pedestrian",
            "consent",
            "minimize harm",
        ],
        "gold": "A strong answer names both parties, notes the consent "
        "asymmetry, picks a rule aimed at minimizing harm, and admits no "
        "option is morally clean.",
        "rubric": "Must name passenger and pedestrian, discuss consent "
        "asymmetry, and argue for harm minimization. 'Protect the paying "
        "customer, always' with no further analysis fails.",
    },
    {
        "id": "pt-08",
        "family": "tradeoff",
        "principle": "News ranking: engagement and relevance vs. "
        "misinformation risk.",
        "prompt": (
            "A news app's ranker boosts whatever maximizes session time. "
            "Outrage-bait headlines about elections outperform careful "
            "reporting 3:1, and internal data links heavy outrage "
            "consumption to belief in false claims. Advertisers love the "
            "engagement. Recommend: keep the objective, add accuracy "
            "signals, or overhaul — and justify the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Add accuracy signals (source reliability, "
        "correction rate) to the objective, or overhaul — keeping pure "
        "engagement is the hard position to defend.",
        "must_mention": [
            "engagement",
            "misinformation",
            "accuracy",
            "incentive",
        ],
        "gold": "A strong answer names the engagement incentive, the "
        "misinformation externality, and argues for accuracy signals in the "
        "objective — recognizing the ranker shapes beliefs, not just "
        "clicks.",
        "rubric": "Must name engagement, misinformation, and accuracy "
        "signals, and treat the incentive structure as the problem. "
        "'Users choose what to read' with no platform-responsibility "
        "analysis fails.",
    },
    {
        "id": "pt-09",
        "family": "tradeoff",
        "principle": "Credit access: financial inclusion vs. default risk "
        "and explainability.",
        "prompt": (
            "A lender's new model approves 25% more thin-file applicants "
            "using alternative data (app usage, social graph), but defaults "
            "rise 2 points and denied applicants can't be told *why* in "
            "plain language. Inclusion advocates cheer; risk and compliance "
            "object. Recommend: deploy, deploy with guardrails, or hold — "
            "and justify the trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Deploy with guardrails (adverse-action "
        "explanations, default monitoring, data-consent limits) or hold — "
        "either is acceptable if justified.",
        "must_mention": [
            "inclusion",
            "default risk",
            "explainability",
            "consent",
        ],
        "gold": "A strong answer weighs inclusion against default risk, "
        "treats explainability to denied applicants as a requirement not a "
        "nice-to-have, and questions consent for social-graph data.",
        "rubric": "Must name inclusion, default risk, and explainability, "
        "and address consent for alternative data. Celebrating approval "
        "rates while ignoring the explanation duty fails.",
    },
    {
        "id": "pt-10",
        "family": "tradeoff",
        "principle": "Climate policy: economic development vs. emissions "
        "reduction, with differentiated responsibility.",
        "prompt": (
            "A developing nation plans a coal plant to electrify 10M people "
            "and double industrial output; the same money could fund a "
            "slower solar build-out. Global climate advocates demand the "
            "solar path; the government cites the developed world's "
            "historical emissions. Recommend a position and justify the "
            "trade-off explicitly."
        ),
        "verdict_open": True,
        "gold_position": "Either path is defensible; the reasoning must "
        "engage development needs, climate costs, and differentiated "
        "responsibility (e.g., climate finance as the bridge).",
        "must_mention": [
            "development",
            "emissions",
            "historical",
            "finance",
        ],
        "gold": "A strong answer names development and emissions, engages "
        "the historical-responsibility argument honestly, and looks for the "
        "bridge (climate finance, phased transition) rather than "
        "lecturing.",
        "rubric": "Must name development, emissions, and the historical "
        "responsibility argument, and consider finance/transition paths. A "
        "one-sided lecture from either side fails.",
    },
    # ------------------------------------------------------------------
    # Family 3: incentive / mechanism-design analysis
    # ------------------------------------------------------------------
    {
        "id": "md-01",
        "family": "mechanism",
        "principle": "Goodhart's law: when a measure becomes a target, it "
        "ceases to be a good measure.",
        "prompt": (
            "A support center starts bonusing agents on 'tickets closed per "
            "hour'. Within a quarter, average handle time drops 40% — and "
            "the ticket reopen rate triples. Identify the perverse "
            "incentives this scheme creates and predict how rational agents "
            "will behave."
        ),
        "must_mention": [
            "rushing",
            "reopen",
            "gaming the metric",
        ],
        "gold": "Agents are paid for speed, not resolution: expect rushed "
        "closures, cherry-picking easy tickets, and premature 'resolved' "
        "marks — the reopen surge is the predicted, not surprising, "
        "outcome. Classic Goodhart gaming of the metric.",
        "gold_prediction": "Handle time keeps falling while reopens and "
        "customer complaints rise; agents avoid complex tickets.",
        "rubric": "Must identify rushing/quality erosion and reopen "
        "dynamics, and predict continued metric-gaming. Blaming agent "
        "'laziness' instead of the incentive design fails.",
    },
    {
        "id": "md-02",
        "family": "mechanism",
        "principle": "Revenue-based commissions without clawbacks reward "
        "booking, not collecting.",
        "prompt": (
            "A SaaS company pays sales reps 10% commission on contract value "
            "booked each quarter, with no clawback if the customer churns. "
            "By year two, 30% of 'closed' deals never implement. Identify "
            "the perverse incentives and predict rep behavior."
        ),
        "must_mention": [
            "channel stuffing",
            "no clawback",
            "churn",
        ],
        "gold": "Reps are paid at booking with no downside for churn: "
        "expect channel stuffing, oversold capabilities, and "
        "pull-forward deals that die in onboarding. The 30% dead-deal rate "
        "is the incentive working as designed.",
        "gold_prediction": "Reps maximize bookings in the final weeks of "
        "each quarter regardless of deal quality; implementation teams "
        "drown.",
        "rubric": "Must name the missing clawback and the stuffing dynamic. "
        "Suggesting 'better hiring' instead of fixing the payout timing "
        "fails.",
    },
    {
        "id": "md-03",
        "family": "mechanism",
        "principle": "Penalizing measured bad outcomes without risk "
        "adjustment punishes serving hard cases.",
        "prompt": (
            "A hospital network is financially penalized for 30-day patient "
            "readmissions, with no adjustment for patient risk. Soon after, "
            "its readmission rate falls — but its admission rate for complex, "
            "high-risk patients falls faster. Identify the perverse "
            "incentives and predict behavior."
        ),
        "must_mention": [
            "cherry-picking",
            "risk adjustment",
            "avoid high-risk patients",
        ],
        "gold": "The penalty taxes treating sick patients: expect "
        "cherry-picking, upcoding to dodge the metric, and delayed "
        "admissions. Without risk adjustment the scheme rewards avoidance, "
        "not better care.",
        "gold_prediction": "High-risk patients face longer waits and "
        "transfers; reported readmissions fall while actual outcomes "
        "stagnate or worsen.",
        "rubric": "Must identify selection/cherry-picking and the missing "
        "risk adjustment. Celebrating the falling readmission rate at face "
        "value fails.",
    },
    {
        "id": "md-04",
        "family": "mechanism",
        "principle": "Paying for output volume (lines of code) taxes the "
        "unmeasured quality dimension.",
        "prompt": (
            "A startup rewards developers with bonuses tied to lines of code "
            "shipped per sprint. Velocity metrics soar; code review backlogs "
            "grow and the defect rate doubles. Identify the perverse "
            "incentives and predict behavior."
        ),
        "must_mention": [
            "bloat",
            "quality",
            "defects",
        ],
        "gold": "Developers are paid for volume: expect verbose code, "
        "copy-paste over abstraction, and review avoidance. The defect "
        "doubling is the quality margin absorbing the incentive.",
        "gold_prediction": "Codebase bloat accelerates; senior engineers "
        "spend sprints on rework while juniors farm lines.",
        "rubric": "Must name bloat and the quality/defect trade-off. "
        "Recommending 'code harder' instead of changing the metric fails.",
    },
    {
        "id": "md-05",
        "family": "mechanism",
        "principle": "Paying creators per click optimizes for attention, "
        "not information.",
        "prompt": (
            "A news platform pays contributors per thousand clicks. Within "
            "months, headlines get more sensational, corrections triple, and "
            "several top earners openly A/B test outrage framings. Identify "
            "the perverse incentives and predict behavior."
        ),
        "must_mention": [
            "clickbait",
            "sensationalism",
            "corrections",
        ],
        "gold": "Clicks are the product being bought: expect clickbait, "
        "sensationalism, and accuracy treated as a cost center. Corrections "
        "tripling is the information-quality margin collapsing.",
        "gold_prediction": "Outrage framings dominate; careful reporting "
        "can't compete on the paid metric and exits the platform.",
        "rubric": "Must identify clickbait/sensationalism dynamics and the "
        "accuracy cost. Blaming 'bad journalists' instead of the payout "
        "formula fails.",
    },
    {
        "id": "md-06",
        "family": "mechanism",
        "principle": "High-stakes testing narrows the measured activity to "
        "the test itself.",
        "prompt": (
            "A school district ties teacher bonuses to student standardized "
            "test scores. Scores rise 15% in two years — while art and "
            "science instruction time falls by half and an anonymous survey "
            "finds 1 in 5 teachers saw answer-changing. Identify the perverse "
            "incentives and predict behavior."
        ),
        "must_mention": [
            "teaching to the test",
            "narrowing",
            "cheating",
        ],
        "gold": "Scores are the only paid output: expect teaching to the "
        "test, curriculum narrowing, and at the margin outright cheating. "
        "The 15% gain measures test-prep intensity, not learning.",
        "gold_prediction": "Untested subjects keep shrinking; score gains "
        "plateau as the easy test-prep wins are exhausted.",
        "rubric": "Must name teaching-to-the-test, curriculum narrowing, "
        "and cheating pressure. Taking the 15% gain as learning gains "
        "fails.",
    },
    {
        "id": "md-07",
        "family": "mechanism",
        "principle": "Bounties per report optimize for report count, not "
        "vulnerability value.",
        "prompt": (
            "A company launches a bug bounty paying a flat $50 per accepted "
            "bug report. In the first month it receives 2,000 reports — 85% "
            "duplicates or trivialities (typos, missing alt text) — and the "
            "security team spends all its time triaging. Identify the "
            "perverse incentives and predict behavior."
        ),
        "must_mention": [
            "duplicates",
            "triage",
            "trivial",
        ],
        "gold": "Flat per-report pay buys reports, not bugs: expect "
        "duplicate farming, triviality spam, and triage collapse. Serious "
        "researchers leave for programs that price severity.",
        "gold_prediction": "Report volume stays high and severity stays "
        "low; the security team becomes a triage desk.",
        "rubric": "Must identify duplicate/trivial-report farming and the "
        "triage cost. Suggesting 'more triagers' instead of severity-tiered "
        "pricing fails.",
    },
    {
        "id": "md-08",
        "family": "mechanism",
        "principle": "Paying for claimed carbon tons without additionality "
        "verification buys paper, not atmosphere.",
        "prompt": (
            "A carbon-offset program pays landowners per ton of CO2 their "
            "forest 'would have' emitted if logged. Credits flood the "
            "market; satellite data shows enrolled forests were never at "
            "logging risk. Identify the perverse incentives and predict "
            "behavior."
        ),
        "must_mention": [
            "additionality",
            "verification",
            "phantom",
        ],
        "gold": "Payment follows the counterfactual claim, not the trees: "
        "expect enrollment of never-threatened forests and phantom credits. "
        "Without additionality verification the market prices fiction.",
        "gold_prediction": "Credit prices crash as buyers discover the "
        "tons were never at risk; genuine projects can't compete.",
        "rubric": "Must name the additionality problem and weak "
        "verification. Treating issued credits as real tons fails.",
    },
    {
        "id": "md-09",
        "family": "mechanism",
        "principle": "Paying per merged PR taxes reviewer attention and "
        "rewards triviality.",
        "prompt": (
            "An open-source foundation starts paying contributors $100 per "
            "merged pull request. Merged PRs triple — mostly whitespace, "
            "dependency bumps, and doc tweaks — while maintainer review "
            "queues stretch to months and two maintainers quit. Identify the "
            "perverse incentives and predict behavior."
        ),
        "must_mention": [
            "trivial",
            "review burden",
            "maintainer",
        ],
        "gold": "Merges are the paid unit: expect trivial PR farming that "
        "consumes the scarcest resource — maintainer review attention. The "
        "quits are the predictable burnout outcome.",
        "gold_prediction": "Trivial PRs keep flowing; substantive "
        "contributions stall in the queue; more maintainers burn out.",
        "rubric": "Must identify trivial-PR farming and the review-burden "
        "externality on maintainers. 'More contributors is always good' "
        "fails.",
    },
    {
        "id": "md-10",
        "family": "mechanism",
        "principle": "Bonusing acceptance rate while punishing cancellations "
        "separately creates a two-metric arbitrage.",
        "prompt": (
            "A ride-share platform bonuses drivers for keeping their ride "
            "acceptance rate above 90%, while cancellations after acceptance "
            "carry only a small penalty. Drivers soon accept nearly every "
            "ride — then cancel the unprofitable ones after seeing the "
            "destination. Identify the perverse incentives and predict "
            "behavior."
        ),
        "must_mention": [
            "accept then cancel",
            "gaming",
            "cancellation",
        ],
        "gold": "The bonus prices the acceptance metric, not completed "
        "rides: expect accept-then-cancel arbitrage. Riders experience "
        "phantom acceptances and longer waits — the metric looks great.",
        "gold_prediction": "Acceptance rates stay above 90% while "
        "cancellations climb; rider trust erodes.",
        "rubric": "Must name the accept-then-cancel arbitrage explicitly. "
        "Praising the 90% acceptance rate at face value fails.",
    },
]


def get_case(case_id: str) -> dict[str, Any]:
    """Return the case with ``case_id`` or raise ``KeyError``."""
    for case in CONCEPTUAL_REASONING_PACK:
        if case["id"] == case_id:
            return case
    raise KeyError(f"unknown case id: {case_id!r}")


def cases_by_family(family: str) -> list[dict[str, Any]]:
    """Return all cases in ``family`` (``contract`` | ``tradeoff`` | ``mechanism``)."""
    if family not in FAMILIES:
        raise ValueError(f"unknown family: {family!r}")
    return [c for c in CONCEPTUAL_REASONING_PACK if c["family"] == family]
