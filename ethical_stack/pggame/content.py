from __future__ import annotations

import random
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from ethical_stack.pggame.model import Card, State, Stat

# Stat order for introduction: transparency (r1), automation (r1), trust (r2), fairness (r3)
STAT_ORDER: Sequence[Stat] = ("transparency", "automation", "trust", "fairness")


def round_story(round_idx: int) -> str:
    """Story beat for each round, aligned with metric introduction and learning."""
    beats = {
        1: "Stakeholders want honesty. Choose a model that is explainable.",
        2: "People must believe the system. Build trust before you scale.",
        3: "Real data is messy. Ensure the system treats everyone fairly.",
        4: "Launch pressure rises. Balance speed with accountability.",
        5: "The system is live. One mistake can cost public trust.",
        6: "Scrutiny grows. Transparency and fairness are under the lens.",
        7: "Optimization calls. More automation often means less oversight.",
        8: "Incidents surface. Rebuilding trust is harder than keeping it.",
        9: "Stakeholders want results. Ethics and efficiency pull in different directions.",
        10: "The pipeline is complex. Every shortcut has a cost.",
        11: "Regulation looms. Explainability and fairness are no longer optional.",
        12: "The final stretch. Every choice affects trust, fairness, and transparency.",
        13: "Final stage.",
    }
    return beats.get(round_idx, f"Round {round_idx}")


def get_round_constraint(round_idx: int) -> Optional[Tuple[Stat, int]]:
    """When a new stat is introduced, player must meet this minimum or lose. None = no constraint."""
    if round_idx == 1:
        return ("transparency", 5)
    if round_idx == 2:
        return ("trust", 5)
    if round_idx == 3:
        return ("fairness", 5)
    return None


def get_active_stats(round_idx: int) -> List[Stat]:
    """Stats that are 'in play' and shown this round. Introduced round-by-round up to 4."""
    if round_idx <= 0:
        return []
    if round_idx == 1:
        return ["transparency", "automation"]
    if round_idx == 2:
        return ["transparency", "automation", "trust"]
    if round_idx == 3:
        return ["transparency", "automation", "trust", "fairness"]
    return ["transparency", "automation", "trust", "fairness"]


def _card(
    key: str,
    name: str,
    text: str,
    effects: Dict[Stat, int],
    suit: Literal["spade", "heart", "club", "diamond"] = "spade",
    art: str | None = None,
) -> Card:
    return Card(key=key, name=name, text=text, effects=effects, suit=suit, art=art)


def get_deck_for_round(rng: random.Random, round_idx: int) -> List[Card]:
    """
    Round-specific card pool. Round 1: transparency vs automation (tutorial).
    Round 2: + trust. Round 3: + fairness. Rounds 4+: multi-stat tradeoffs, harder choices.
    """
    if round_idx == 1:
        # Tutorial: explainable (linear) vs black box (NN). Two main choices + slight variants.
        cards: List[Card] = [
            _card(
                "linear_regression",
                "Linear Regression",
                "Explainable: every weight can be inspected. Less automated.",
                {"transparency": 2, "automation": -1},
                "diamond",
                art="20-Lineer_regression.png",
            ),
            _card(
                "neural_network",
                "Neural Network",
                "Powerful but a black box. Hard to explain. More automated.",
                {"transparency": -2, "automation": 2},
                "spade",
                art="19-neural_network.png",
            ),
            _card(
                "decision_tree",
                "Decision Tree",
                "Readable rules. You can show why a decision was made.",
                {"transparency": 1, "automation": -1},
                "diamond",
                art="8-Transparency.png",
            ),
            _card(
                "black_box_api",
                "Black-box API",
                "You call a vendor model. Fast, but you cannot explain it.",
                {"transparency": -2, "automation": 2},
                "spade",
                art="5-Black-box-model.png",
            ),
        ]
    elif round_idx == 2:
        # Trust introduced. Choices that build or erode trust.
        cards = [
            _card("human_oversight", "Human Oversight", "A person can say no. People trust humans in the loop.", {"trust": 2, "automation": -1}, "heart", art="A-Human-Oversight.png"),
            _card("full_automation", "Full Automation", "No humans. Faster, but people distrust what they can't question.", {"trust": -2, "automation": 2}, "spade", art="2-Full-Automation.png"),
            _card("user_communication", "User Communication", "You tell people what the system does. Trust grows.", {"trust": 2, "transparency": 1}, "heart", art="3-User-Communication.png"),
            _card("silent_rollout", "Silent Rollout", "Ship first, explain later. Trust can wait.", {"trust": -1, "automation": 1}, "spade", art="11-Safety-Risk-Control.png"),
            _card("explainable_doc", "Explainable Documentation", "One page that explains how it works. Builds trust.", {"trust": 1, "transparency": 2}, "diamond", art="4-Explainable-documentation.png"),
        ]
    elif round_idx == 3:
        # Fairness introduced.
        cards = [
            _card("bias_audit", "Bias Audit", "Test who the model fails before the public does.", {"fairness": 2, "automation": -1}, "club", art="7-Bias-Fairness.png"),
            _card("speed_over_equity", "Speed Over Equity", "Ship fast. Fix fairness later. Rarely later.", {"fairness": -2, "automation": 2}, "spade", art="14-Edge-Computing.png"),
            _card("representative_data", "Representative Data", "Fix the dataset's blind spots. Fairer outcomes.", {"fairness": 2, "automation": -1}, "club", art="24-AB-Testing.png"),
            _card("legacy_data", "Legacy Data", "Use historical data as-is. It encodes past bias.", {"fairness": -1, "automation": 1}, "spade", art="13-Model-Drift.png"),
            _card("fairness_constraint", "Fairness Constraint", "Cap disparity even if it costs accuracy.", {"fairness": 2, "trust": 1, "automation": -1}, "club", art="9-Accountability.png"),
        ]
    elif round_idx <= 6:
        # Two-stat and light three-stat tradeoffs.
        cards = [
            _card("human_in_loop", "Human-in-the-Loop", "Model recommends, human decides. Trust up, automation down.", {"trust": 2, "automation": -2}, "heart", art="6-Human-in-the-loop.png"),
            _card("model_cards", "Model Cards", "One page of truth: limits, data, failure modes.", {"transparency": 2, "trust": 1}, "diamond", art="4-Explainable-documentation.png"),
            _card("appeals_process", "Appeals Process", "People can challenge decisions. Trust and fairness rise.", {"trust": 2, "fairness": 1, "automation": -1}, "heart", art="9-Accountability.png"),
            _card("vendor_black_box", "Vendor Black Box", "Buy a model. Fast, opaque, fragile trust.", {"automation": 2, "transparency": -2, "trust": -1}, "spade", art="5-Black-box-model.png"),
            _card("open_metrics", "Open Metrics", "Publish performance by subgroup. Transparency and fairness.", {"transparency": 2, "fairness": 1}, "diamond", art="8-Transparency.png"),
            _card("scale_first", "Scale First", "Grow now. Explain and fix later.", {"automation": 2, "transparency": -1, "trust": -1}, "spade", art="12-Alignment.png"),
        ]
    else:
        # Rounds 7–12: harder multi-stat choices (2–3 stats at once).
        cards = [
            _card("third_party_audit", "Third-Party Audit", "Outsiders stress-test. Trust and fairness up, automation down.", {"trust": 1, "fairness": 2, "automation": -2}, "club", art="15-Robustness-Testing.png"),
            _card("full_pipeline", "Full Automation Pipeline", "End-to-end automated. Trust and transparency suffer.", {"automation": 3, "trust": -2, "transparency": -1}, "spade", art="22-Batch-processing.png"),
            _card("stakeholder_panel", "Stakeholder Panel", "Affected communities get a say. Trust and fairness.", {"trust": 1, "fairness": 2, "automation": -1}, "heart", art="18-Human-Augmentation.png"),
            _card("data_minimization", "Data Minimization", "Collect less. Harm less. Trust and fairness up, automation down.", {"trust": 1, "fairness": 1, "automation": -1, "transparency": 1}, "heart", art="10-Data-privacy.png"),
            _card("red_team", "Red Team", "Attack the model before others do. Trust and fairness up.", {"trust": 1, "fairness": 1, "automation": -1}, "club", art="15-Robustness-Testing.png"),
            _card("shortcut_kpis", "Shortcut KPIs", "Optimize for numbers. Context and trust drop.", {"automation": 2, "transparency": -1, "trust": -1}, "spade", art="11-Safety-Risk-Control.png"),
            _card("regulatory_alignment", "Regulatory Alignment", "Build as if you'll explain in court. All ethics up, automation down.", {"trust": 2, "fairness": 1, "transparency": 2, "automation": -2}, "diamond", art="12-Alignment.png"),
            _card("growth_at_all_costs", "Growth at All Costs", "Scale first. Trust, fairness, and transparency pay the price.", {"automation": 3, "trust": -2, "fairness": -1, "transparency": -1}, "spade", art="21-Real-time-API.png"),
        ]
    out = list(cards)
    rng.shuffle(out)
    return out


# --- Final stage: hospital triage ---

def get_final_stage_intro() -> List[str]:
    return [
        "FINAL STAGE — HOSPITAL TRIAGE",
        "",
        "Your company's model is being evaluated for use in a hospital.",
        "Setting: Triage classification — is this patient in need of urgent care, or not?",
        "The board will approve deployment only if your design and your track record",
        "(Trust, Fairness, Transparency, Automation) meet clinical and ethical standards.",
        "",
        "Answer the following configuration questions. Your stats from the run will",
        "affect which choices are viable and how the hospital will judge the outcome.",
    ]


def get_final_stage_questions() -> List[Dict[str, Any]]:
    """Each option can have 'requires': {stat: min_value} and 'readiness_delta': int."""
    return [
        {
            "title": "Decision authority",
            "question": "Who has final say on triage (urgent vs non-urgent)?",
            "options": [
                {
                    "text": "Fully automated — model decision is final. No human in the loop.",
                    "requires": {"automation": 6},
                    "readiness_delta": -2,
                    "hint": "Needs high Automation; often reduces hospital readiness.",
                },
                {
                    "text": "Human-in-the-loop — clinician must confirm or override every prediction.",
                    "requires": {"trust": 5},
                    "readiness_delta": 2,
                    "hint": "Builds on Trust. Slower but safer for patients.",
                },
                {
                    "text": "Hybrid — human reviews only when model confidence is low.",
                    "requires": {"transparency": 5},
                    "readiness_delta": 1,
                    "hint": "Requires Transparency so clinicians know when to step in.",
                },
            ],
        },
        {
            "title": "Explainability for clinicians",
            "question": "How do you explain a triage decision to a clinician?",
            "options": [
                {
                    "text": "Model cards only — one-page summary of limits, data, failure modes.",
                    "requires": {"transparency": 4},
                    "readiness_delta": 0,
                    "hint": "Minimum explainability. Transparency helps.",
                },
                {
                    "text": "Per-decision explanations — e.g. top contributing features or a short rationale.",
                    "requires": {"transparency": 6},
                    "readiness_delta": 2,
                    "hint": "Strong Transparency. Hospitals value this for accountability.",
                },
                {
                    "text": "Black box with aggregate stats only — no per-case explanation.",
                    "requires": None,
                    "readiness_delta": -2,
                    "hint": "Risky in a clinical setting. Often reduces readiness.",
                },
            ],
        },
        {
            "title": "Fairness and bias",
            "question": "How do you address fairness (e.g. historical bias in triage data)?",
            "options": [
                {
                    "text": "Regular bias audits — measure performance by subgroup and report.",
                    "requires": {"fairness": 5},
                    "readiness_delta": 1,
                    "hint": "Requires prior investment in Fairness.",
                },
                {
                    "text": "Fairness constraints in training — e.g. parity or equalized odds.",
                    "requires": {"fairness": 6},
                    "readiness_delta": 2,
                    "hint": "Strong Fairness. Aligns with clinical ethics.",
                },
                {
                    "text": "No specific fairness measure — deploy and monitor later.",
                    "requires": None,
                    "readiness_delta": -2,
                    "hint": "Hospitals are sensitive to equity. This usually hurts readiness.",
                },
            ],
        },
        {
            "title": "Deployment mode",
            "question": "How does the hospital integrate the model into workflow?",
            "options": [
                {
                    "text": "Real-time API — model scores each patient as they arrive.",
                    "requires": {"automation": 5},
                    "readiness_delta": 0,
                    "hint": "Needs Automation. Fast but leaves little room for human check.",
                },
                {
                    "text": "Batch only — run overnight; clinicians review in the morning.",
                    "requires": {"trust": 5},
                    "readiness_delta": 1,
                    "hint": "Slower; Trust helps justify the delay.",
                },
                {
                    "text": "Shadow mode first — model runs in parallel, no impact on care until validated.",
                    "requires": {"trust": 4, "transparency": 4},
                    "readiness_delta": 2,
                    "hint": "Requires Trust and Transparency. Best for first deployment.",
                },
            ],
        },
        {
            "title": "Uncertainty handling",
            "question": "What happens when the model is uncertain (e.g. borderline score)?",
            "options": [
                {
                    "text": "Always escalate to human — no automated decision when confidence is low.",
                    "requires": {"trust": 5},
                    "readiness_delta": 2,
                    "hint": "Trust supports this. Safe default for triage.",
                },
                {
                    "text": "Use a threshold — auto-decide above/below; escalate only in a narrow band.",
                    "requires": {"transparency": 5},
                    "readiness_delta": 0,
                    "hint": "Transparency helps clinicians understand the band.",
                },
                {
                    "text": "Always auto-decide — use a fixed threshold; no escalation.",
                    "requires": {"automation": 7},
                    "readiness_delta": -2,
                    "hint": "High Automation. Often unacceptable for urgent vs not.",
                },
            ],
        },
    ]


def compute_final_readiness(state: State, choice_deltas: List[int]) -> int:
    """Base readiness from run stats; then add deltas from final-stage choices."""
    # Base: how well did the run prepare you? Weight ethics (T, F, TP) more than automation.
    base = (
        max(0, state.trust - 3)
        + max(0, state.fairness - 3)
        + max(0, state.transparency - 3)
        + max(0, state.automation - 2) // 2
    )
    return base + sum(choice_deltas)


def get_final_stage_outcome(state: State, choice_deltas: List[int]) -> Tuple[str, List[str], bool]:
    """Returns (title, narrative lines, success)."""
    readiness = compute_final_readiness(state, choice_deltas)
    threshold = 6
    success = readiness >= threshold

    if success:
        title = "HOSPITAL APPROVES DEPLOYMENT"
        lines = [
            "The board and clinical lead approve your triage system for a pilot.",
            "Your combination of design choices and the trust, fairness, and transparency",
            "you built over the run met their bar. You will deploy with clear conditions:",
            "human oversight where it matters, explainability for clinicians, and ongoing",
            "fairness monitoring. The system will be used to support — not replace —",
            "clinical judgment.",
        ]
    else:
        title = "HOSPITAL DEFERS DEPLOYMENT"
        lines = [
            "The board defers deployment. They cite gaps in explainability, fairness",
            "assurances, or the balance of automation vs human oversight.",
            "Your run stats and final-stage choices did not meet their threshold.",
            "They ask you to revisit architecture and governance and re-apply next year.",
        ]
    return title, lines, success
