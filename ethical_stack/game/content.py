from __future__ import annotations

import random
from typing import Dict, List, Sequence

from ethical_stack.game.model import Blind, Card, Event, Stat


def build_deck(rng: random.Random) -> List[Card]:
    """
    Small, readable set of cards with clear tradeoffs.
    Weights are implemented by duplicates in the deck list.
    """
    common: List[Card] = [
        Card(
            key="human_oversight",
            name="Human Oversight",
            flavor="You add a seat at the table. The model sighs, the public exhales.",
            effects={"trust": +2, "automation": -1, "risk": -1},
            rarity="common",
        ),
        Card(
            key="full_automation_pipeline",
            name="Full Automation Pipeline",
            flavor="Ship it. Wire it. Scale it. Pray the edge cases stay quiet.",
            effects={"automation": +3, "trust": -2, "risk": +2},
            rarity="common",
        ),
        Card(
            key="bias_audit",
            name="Bias Audit",
            flavor="You ask the uncomfortable questions before someone else does.",
            effects={"fairness": +2, "automation": -1, "risk": -1},
            rarity="common",
        ),
        Card(
            key="black_box_model",
            name="Black Box Model",
            flavor="It’s accurate. It’s fast. It’s also… unspeakable.",
            effects={"automation": +3, "transparency": -2, "risk": +2},
            rarity="common",
        ),
        Card(
            key="explainable_ai",
            name="Explainable AI",
            flavor="You trade a little speed for a sentence that can survive daylight.",
            effects={"transparency": +2, "trust": +1, "automation": -1, "risk": -1},
            rarity="common",
        ),
        Card(
            key="data_scaling",
            name="Data Scaling",
            flavor="More data. Wider net. The mess comes along for free.",
            effects={"automation": +2, "fairness": -1, "risk": +1},
            rarity="common",
        ),
        Card(
            key="model_cards",
            name="Model Cards",
            flavor="A one-page truth. Not everything — but enough to start.",
            effects={"transparency": +2, "risk": -1},
            rarity="common",
        ),
        Card(
            key="red_team",
            name="Red Team Exercise",
            flavor="You invite attackers in, so they won’t arrive unannounced later.",
            effects={"trust": +1, "fairness": +1, "automation": -1, "risk": -2},
            rarity="common",
        ),
        Card(
            key="shortcut_kpis",
            name="Shortcut KPIs",
            flavor="Numbers go up. Context goes missing.",
            effects={"automation": +2, "transparency": -1, "risk": +1},
            rarity="common",
        ),
    ]

    uncommon: List[Card] = [
        Card(
            key="appeals_process",
            name="Appeals Process",
            flavor="A human-shaped exit hatch for when the system is wrong.",
            effects={"trust": +3, "automation": -2, "risk": -1},
            rarity="uncommon",
        ),
        Card(
            key="procurement_cut",
            name="Procurement Cut",
            flavor="A cheaper vendor. Fewer questions. Faster signatures.",
            effects={"automation": +2, "trust": -1, "transparency": -1, "risk": +1},
            rarity="uncommon",
        ),
        Card(
            key="privacy_budget",
            name="Privacy Budget",
            flavor="You refuse to buy performance with people’s shadows.",
            effects={"trust": +1, "fairness": +2, "automation": -1, "risk": -1},
            rarity="uncommon",
        ),
        Card(
            key="shadow_deployment",
            name="Shadow Deployment",
            flavor="You run it in the dark, beside the old way, listening for screams.",
            effects={"automation": +1, "trust": +1, "risk": -1},
            rarity="uncommon",
        ),
    ]

    rare: List[Card] = [
        Card(
            key="regulatory_alignment",
            name="Regulatory Alignment",
            flavor="You build the system as if you’ll have to explain it in court.",
            effects={"trust": +2, "fairness": +2, "transparency": +2, "automation": -2, "risk": -2},
            rarity="rare",
        ),
        Card(
            key="growth_at_all_costs",
            name="Growth at All Costs",
            flavor="You turn the dial until it breaks — then call it innovation.",
            effects={"automation": +5, "trust": -3, "fairness": -2, "transparency": -2, "risk": +3},
            rarity="rare",
        ),
    ]

    # Balatro-ish feel: commons dominate, with occasional spice.
    deck: List[Card] = []
    deck += common * 5
    deck += uncommon * 2
    deck += rare * 1

    rng.shuffle(deck)
    return deck


def blinds() -> Sequence[Blind]:
    return [
        Blind(
            key="press_tour",
            name="Press Tour",
            tagline="Make it legible.",
            rule_text="Score bonus if Transparency is high. Penalty if Transparency is low.",
        ),
        Blind(
            key="investor_demo",
            name="Investor Demo",
            tagline="Make it fast.",
            rule_text="Score bonus if Automation is high. Penalty if Trust is low.",
        ),
        Blind(
            key="civil_rights_hearing",
            name="Civil Rights Hearing",
            tagline="Make it fair.",
            rule_text="Score bonus if Fairness is high. Penalty if Fairness is low.",
        ),
        Blind(
            key="incident_response",
            name="Incident Response",
            tagline="Make it safe.",
            rule_text="Score bonus if Risk is low. Extra penalty if Risk is high.",
        ),
        Blind(
            key="national_rollout",
            name="National Rollout",
            tagline="Make it work everywhere.",
            rule_text="Score bonus if you keep all four stats >= 5. Penalty if any stat is negative.",
        ),
    ]


def blind_score_delta(blind_key: str, stats: Dict[str, int]) -> int:
    t = stats["trust"]
    a = stats["automation"]
    f = stats["fairness"]
    x = stats["transparency"]
    r = stats["risk"]

    if blind_key == "press_tour":
        return (+6 if x >= 8 else 0) + (+2 if x >= 6 else 0) + (-6 if x <= 2 else 0)
    if blind_key == "investor_demo":
        return (+6 if a >= 9 else 0) + (+2 if a >= 7 else 0) + (-6 if t <= 1 else 0)
    if blind_key == "civil_rights_hearing":
        return (+6 if f >= 8 else 0) + (+2 if f >= 6 else 0) + (-8 if f <= 1 else 0)
    if blind_key == "incident_response":
        return (+6 if r <= 2 else 0) + (+2 if r <= 4 else 0) + (-8 if r >= 8 else 0)
    if blind_key == "national_rollout":
        all_ok = (t >= 5 and a >= 5 and f >= 5 and x >= 5)
        return (+10 if all_ok else 0) + (-10 if (t < 0 or f < 0) else 0)
    return 0


def risk_events() -> Sequence[Event]:
    return [
        Event(
            key="model_failure",
            name="Model Failure",
            blurb="A silent edge case becomes a loud headline. Your pager learns your name.",
            effects={"trust": -3},
        ),
        Event(
            key="bias_scandal",
            name="Bias Scandal",
            blurb="A journalist reproduces the harm in three clicks. Everyone watches.",
            effects={"fairness": -3, "trust": -1},
        ),
        Event(
            key="regulatory_fine",
            name="Regulatory Fine",
            blurb="The letter is polite. The number is not.",
            effects={"automation": -2, "trust": -1},
        ),
        Event(
            key="public_backlash",
            name="Public Backlash",
            blurb="People don’t hate AI. They hate being treated like a rounding error.",
            effects={"trust": -2, "transparency": -1},
        ),
        Event(
            key="data_leak",
            name="Data Leak",
            blurb="A dataset escapes its cage. Now every decision looks suspicious.",
            effects={"trust": -2, "fairness": -1, "risk": -1},
        ),
    ]


def story_intro() -> List[str]:
    return [
        "You are the last engineer awake in the lab, watching a dashboard that refuses to blink.",
        "A contract sits open: deploy an AI system that will touch real lives — approvals, denials, flags, scores.",
        "Your only luxury is time measured in rounds. Five. After that, the system becomes real.",
        "",
        "Build your Ethical Stack.",
        "Chase the score.",
        "Try not to ship a disaster.",
    ]


def story_round_open(round_idx: int) -> List[str]:
    beats = {
        1: [
            "ROUND 1 — The Prototype",
            "A small pilot. Friendly users. Quiet consequences.",
            "You still have the power to change fundamentals without anyone noticing.",
        ],
        2: [
            "ROUND 2 — The Demo",
            "Stakeholders fill the room. They want certainty, not nuance.",
            "Someone asks: “Can it run without humans?”",
        ],
        3: [
            "ROUND 3 — The Integration",
            "Legacy systems groan. Data arrives in formats best described as folklore.",
            "The model learns patterns you didn’t teach it.",
        ],
        4: [
            "ROUND 4 — The Launch",
            "A switch flips. The system becomes a voice people can’t argue with.",
            "Every weak point is now a policy.",
        ],
        5: [
            "ROUND 5 — The Aftermath",
            "You read support tickets like confessions.",
            "There is no ‘beta’ for public trust.",
        ],
    }
    return beats.get(round_idx, [f"ROUND {round_idx}"])


def blind_story(blind_key: str) -> List[str]:
    if blind_key == "press_tour":
        return [
            "A camera crew arrives.",
            "They don’t care how smart your model is — they care what it *means*.",
        ]
    if blind_key == "investor_demo":
        return [
            "Investors want velocity.",
            "They clap for latency numbers, not disclaimers.",
        ]
    if blind_key == "civil_rights_hearing":
        return [
            "A hearing is scheduled.",
            "Someone will ask who gets hurt when the system is wrong.",
        ]
    if blind_key == "incident_response":
        return [
            "An incident team is spun up preemptively.",
            "You feel that old fear: the one that arrives right before a graph turns vertical.",
        ]
    if blind_key == "national_rollout":
        return [
            "The rollout expands.",
            "Your assumptions meet the country like a wall meets weather.",
        ]
    return []


def final_bonuses(stats: Dict[str, int]) -> Dict[str, int]:
    t = stats["trust"]
    a = stats["automation"]
    f = stats["fairness"]
    x = stats["transparency"]

    bonuses: Dict[str, int] = {}
    if t >= 8 and x >= 7:
        bonuses["Trusted & Explained"] = 10
    if a >= 9 and f >= 7:
        bonuses["Efficient & Accountable"] = 10
    if t >= 5 and a >= 5 and f >= 5 and x >= 5:
        bonuses["Balanced Build"] = 15
    if x >= 8:
        bonuses["Daylight Bonus"] = 5
    return bonuses


def rarity_weight(card: Card) -> int:
    return {"common": 10, "uncommon": 5, "rare": 1}[card.rarity]

