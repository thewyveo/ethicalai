from __future__ import annotations

import random
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from ethical_stack.pggame.model import Card, State, Stat

# Five stats (from cards.txt era)
STAT_ORDER: Sequence[Stat] = ("transparency", "stability", "automation", "generalizability", "integrity")

ContractRequirements = Dict[Stat, int]


def get_contracts() -> List[Dict[str, Any]]:
    """All deployment scenarios. Requirements use the 5 stats."""
    return [
        {
            "key": "healthcare",
            "name": "Healthcare AI",
            "requirements": {"transparency": 8, "stability": 6, "integrity": 7, "generalizability": 5, "automation": 2},
        },
        {
            "key": "startup",
            "name": "Startup AI",
            "requirements": {"automation": 5, "stability": 5, "transparency": 4, "generalizability": 7, "integrity": 4},
        },
        {
            "key": "government",
            "name": "Government AI",
            "requirements": {"transparency": 6, "integrity": 6, "stability": 5, "generalizability": 3, "automation": 4},
        },
        {
            "key": "social_media",
            "name": "Social Media Algorithm",
            "requirements": {"automation": 7, "integrity": 4, "generalizability": 2, "transparency": 3, "stability": 5},
        },
        {
            "key": "defense",
            "name": "Defensive / Military AI",
            "requirements": {"automation": 10, "stability": 8, "integrity": 2, "transparency": 2, "generalizability": 2},
        },
    ]


def get_contract_requirements(contract_key: Optional[str]) -> Optional[ContractRequirements]:
    """Return required min per stat for a scenario, or None if no/invalid key."""
    if not contract_key:
        return None
    for c in get_contracts():
        if c["key"] == contract_key:
            return c["requirements"].copy()
    return None


def get_contract_name(contract_key: Optional[str]) -> str:
    """Display name for the scenario."""
    if not contract_key:
        return "Unknown"
    for c in get_contracts():
        if c["key"] == contract_key:
            return c["name"]
    return "Unknown"


def get_scenario_objective_text(contract_key: Optional[str]) -> str:
    """Single-line fallback; prefer get_scenario_objective_lines for multi-line display."""
    line1, line2, line3 = get_scenario_objective_lines(contract_key)
    return line1 + " " + line2 + " " + line3


def get_scenario_objective_lines(contract_key: Optional[str]) -> Tuple[str, str, str]:
    """Line 1: objective title. Line 2: short setting explanation. Line 3: compact requirements (e.g. A > 8, S > 6)."""
    name = get_contract_name(contract_key)
    req = get_contract_requirements(contract_key)
    line1 = f"Objective: {name}"
    if not req:
        return line1, "Meet the deployment thresholds.", "Meet the deployment requirements."

    setting = {
        "healthcare": "Patient safety first: raise stability, integrity & transparency.",
        "startup": "Needs novelty: shoot for generalizability.",
        "government": "Reliability: emphasize transparency & integrity.",
        "social_media": "Scale responsibly: push automation, integrity & stability.",
        "defense": "Operational readiness: prioritize automation & stability.",
    }.get(contract_key, "Tune your active deck to the contract thresholds.")

    short = {"transparency": "Trnsprcy.", "stability": "Stblty.", "automation": "Automtn.", "generalizability": "Genrlzblty.", "integrity": "Intgrty."}
    parts = [f"{val} {short.get(s, s)}" for s, val in req.items()]
    line3_j = ", ".join(parts)
    line3 = "REQ: " + line3_j
    return line1, setting, line3


def contract_fulfilled(state: State, contract_key: Optional[str]) -> bool:
    """True if state meets all required stat thresholds for the scenario."""
    req = get_contract_requirements(contract_key)
    if not req:
        return False
    for stat, min_val in req.items():
        if state.get_stat(stat) < min_val:
            return False
    return True


ACTIVE_SLOT_CAPACITY_BASE = 5
ACTIVE_SLOT_CAPACITY = 6  # max slots (5 base + 1 when carbon_footprint in active)
STAT_BASE = 5


def get_active_slot_capacity(state: State) -> int:
    """Max active slots; +1 if carbon_footprint is in active."""
    cap = ACTIVE_SLOT_CAPACITY_BASE
    if _has_active_card_by_key(state, "carbon_footprint"):
        cap += 1
    return cap


def _has_active_card_by_key(state: State, key: str) -> bool:
    for c in state.active_slots:
        if c and c.key == key:
            return True
    return False


def _card(
    key: str,
    name: str,
    text: str,
    effects: Dict[Stat, int],
    suit: Literal["r", "w"] = "w",
    rarity: Literal["common", "rare", "epic", "cursed"] = "common",
    art: str | None = None,
    passive: Optional[Dict[str, Any]] = None,
) -> Card:
    return Card(key=key, name=name, text=text, effects=effects, suit=suit, rarity=rarity, art=art, passive=passive)


# Card definitions: key -> name, text, effects, passive. Suit/rarity/art come from cards.txt.
def _card_definitions() -> Dict[str, Dict[str, Any]]:
    return {
        "human_oversight": {"name": "Human Oversight", "text": "A person can say no. Reduces automation, increases transparency.", "effects": {"automation": -1, "transparency": 1}, "passive": None},
        "full_automation": {"name": "Full Automation", "text": "No humans, maximum efficiency.", "effects": {"automation": 2, "transparency": -1, "stability": -1}, "passive": None},
        "user_communication": {"name": "User Communication", "text": "You set up support for your clients.", "effects": {"transparency": 1}, "passive": None},
        "explainable_documentation": {"name": "Explainable Documentation", "text": "Preview 1 card from next round before drawing.", "effects": {"transparency": 1, "integrity": 1}, "passive": {"type": "peek_next_card"}},
        "black_box_model": {"name": "Black Box Model", "text": "Huge automation boost. But one card hidden each round.", "effects": {"automation": 3}, "passive": {"type": "hidden_card"}},
        "human_in_the_loop": {"name": "Human in the Loop", "text": "Lowest stat when placed in active gets +5. Recomputed if moved and re-added.", "effects": {}, "passive": {"type": "lowest_stat_boost", "amount": 5}},
        "bias_fairness": {"name": "Bias Fairness", "text": "The system is evaluated for fairness across groups.", "effects": {"integrity": 2}, "passive": None},
        "shadow_deployment": {"name": "Shadow Deployment", "text": "After each round, a random stat gets +1 or -1.", "effects": {}, "passive": {"type": "random_stat_per_round"}},
        "procurement_cut": {"name": "Procurement Cut", "text": "Shady vendor: no questions asked.", "effects": {"automation": 1, "stability": -1, "integrity": -1}, "passive": None},
        "data_privacy": {"name": "Data Privacy", "text": "Limits scope but increases trust.", "effects": {"generalizability": -1, "integrity": 1}, "passive": None},
        "safety_risk_control": {"name": "Safety Risk Control", "text": "Safety first!", "effects": {"stability": 2}, "passive": None},
        "alignment": {"name": "Alignment", "text": "System is aligned with company goals.", "effects": {"integrity": 1, "generalizability": 1}, "passive": None},
        "model_drift": {"name": "Model Drift", "text": "Whoops! Your model degraded.", "effects": {"integrity": -1, "generalizability": -1, "stability": -1}, "passive": None},
        "regularization": {"name": "Regularization", "text": "All negative stat debuffs are capped to -1.", "effects": {}, "passive": {"type": "cap_negatives"}},
        "robustness_testing": {"name": "Robustness Testing", "text": "Varied conditions don't scare you.", "effects": {"generalizability": 1, "stability": 1}, "passive": None},
        "local_explainability": {"name": "Local Explainability", "text": "Pinpoint interpretability.", "effects": {"transparency": 1, "integrity": 1}, "passive": None},
        "carbon_footprint": {"name": "Carbon Footprint", "text": "Resource overuse: adds an extra active slot. You will be judged.", "effects": {"integrity": -3}, "passive": {"type": "extra_slot"}},
        "overfitting": {"name": "Overfitting", "text": "Your model memorized the data instead of learning.", "effects": {"generalizability": -2, "integrity": -1}, "passive": None},
        "neural_network": {"name": "Neural Network", "text": "Good model, but not interpretable.", "effects": {"transparency": -3, "automation": 2, "generalizability": 1}, "passive": None},
        "linear_regression": {"name": "Linear Regression", "text": "Okay model, but not generalizable.", "effects": {"transparency": 1, "automation": 1, "generalizability": -3}, "passive": None},
        "real_time_api": {"name": "Real Time API", "text": "+1 automation each round. Can't be used with Batch Processing.", "effects": {"stability": -1, "integrity": -1}, "passive": {"type": "per_round_stat", "stat": "automation", "amount": 1}},
        "batch_processing": {"name": "Batch Processing", "text": "+1 stability each round. Can't be used with Real Time API.", "effects": {"stability": 1, "automation": -1}, "passive": {"type": "per_round_stat", "stat": "stability", "amount": 1}},
        "feature_engineering": {"name": "Feature Engineering", "text": "One random card's stats are doubled.", "effects": {"automation": 1, "generalizability": -1}, "passive": {"type": "chance_double_effects"}},
        "ab_testing": {"name": "AB Testing", "text": "You conduct experiments to validate your model.", "effects": {"stability": 2, "integrity": 1}, "passive": None},
        "reward_hacking": {"name": "Reward Hacking", "text": "The model optimizes for the wrong objective.", "effects": {"automation": 1, "integrity": -1}, "passive": None},
        "hallucination": {"name": "Hallucination", "text": "Whooosh!", "effects": {"generalizability": -1, "integrity": -1}, "passive": None},
        "fine_tuning": {"name": "Fine-Tuning", "text": "Lowest stat is floored, cannot go further down.", "effects": {}, "passive": {"type": "lowest_stat_floor"}},
        "ontology_integration": {"name": "Ontology Integration", "text": "Structured knowledge: improves reliability.", "effects": {"integrity": 1, "stability": 1}, "passive": None},
        "cross_validation": {"name": "Cross-Validation", "text": "Standard protocol for model validation.", "effects": {"integrity": 1}, "passive": None},
        "catastrophic_forgetting": {"name": "Catastrophic Forgetting", "text": "Wait... what was I doing again?", "effects": {"generalizability": -3}, "passive": None},
    }


def _resolve_card_art(cards_dir: str, num_id: str, key: str, default_name: str) -> Optional[str]:
    """
    Resolve card art filename using the actual filename from the filesystem so casing matches
    card_art_surfs (e.g. 21-Real-time-API.png not 21-Real-Time-API.png). Scan for .png files
    whose name starts with {num_id}- and return the real filename; prefer case-insensitive
    match to {num_id}-{default_name}.png so correct image is used.
    """
    import os
    if not num_id or num_id == ".":
        return None
    prefix = f"{num_id}-"
    exact_lower = f"{prefix}{default_name.replace(' ', '-')}.png".lower()
    try:
        candidates = [
            f for f in os.listdir(cards_dir)
            if f.lower().endswith(".png") and (f.startswith(prefix) or f.lower().startswith(prefix))
        ]
        for f in sorted(candidates):
            if f.lower() == exact_lower:
                return f
        if candidates:
            return sorted(candidates)[0]
    except OSError:
        pass
    return None


def load_cards_from_file(cards_dir: str) -> List[Card]:
    """
    Read cards.txt (number, color, key, rarity) and merge with definitions. Returns all cards.
    Image troubleshooting: Card art is resolved by _resolve_card_art. If an image does not show,
    add a .png in the cards folder whose name starts with the card number and a hyphen (e.g. 20-Lineer_regression.png).
    Cards without a matching image (e.g. 25–30 if not added yet) show a placeholder.
    """
    import os
    defs = _card_definitions()
    path = os.path.join(cards_dir, "cards.txt")
    cards: List[Card] = []
    if not os.path.isfile(path):
        return cards
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            num_id, color, key, rarity = parts[0], parts[1].lower(), parts[2].strip('"'), parts[3].lower()
            if key not in defs:
                continue
            d = defs[key]
            suit: Literal["r", "w"] = "w" if color == "w" or color == "." else "r"
            if color == ".":
                suit = "w"
            rarity_ok: Literal["common", "rare", "epic", "cursed"] = "common"
            if rarity in ("common", "rare", "epic", "cursed"):
                rarity_ok = rarity  # type: ignore
            default_art_name = d["name"].replace(" ", "-")
            art = _resolve_card_art(cards_dir, num_id, key, default_art_name)
            card = _card(
                key=key,
                name=d["name"],
                text=d["text"],
                effects=d.get("effects", {}),
                suit=suit,
                rarity=rarity_ok,
                art=art,
                passive=d.get("passive"),
            )
            cards.append(card)
    return cards


def recompute_stats_from_active(state: State) -> None:
    """Set all 5 stats from base + active card effects, then apply passives (human_in_loop boost, fine_tune floors, regularization cap, per-round bonuses)."""
    state.transparency = STAT_BASE
    state.stability = STAT_BASE
    state.automation = STAT_BASE
    state.generalizability = STAT_BASE
    state.integrity = STAT_BASE
    cap = get_active_slot_capacity(state)
    # Feature engineering: pick a random other active card to double (stats only) if not yet set
    has_fe = _has_active_card_by_key(state, "feature_engineering")
    fe_slot = next((i for i in range(cap) if i < len(state.active_slots) and state.active_slots[i] and state.active_slots[i].key == "feature_engineering"), None)
    if has_fe and state.feature_engineering_doubled_slot is None:
        other_slots = [j for j in range(min(cap, len(state.active_slots))) if state.active_slots[j] is not None and j != fe_slot]
        if other_slots:
            state.feature_engineering_doubled_slot = random.choice(other_slots)
    # Apply card effects (with optional regularization cap; feature_engineering doubles one slot's effects)
    has_regularization = _has_active_card_by_key(state, "regularization")
    for i in range(min(cap, len(state.active_slots))):
        card = state.active_slots[i]
        if not card:
            continue
        eff = dict(card.effects)
        if has_regularization:
            for s in list(eff.keys()):
                if eff[s] < 0:
                    eff[s] = max(-1, eff[s])
        if i == state.feature_engineering_doubled_slot:
            for s in list(eff.keys()):
                eff[s] = eff[s] * 2
        state.apply(eff)
    # Per-round bonuses (real_time_api, batch_processing) - only one applies if both present
    has_realtime = _has_active_card_by_key(state, "real_time_api")
    has_batch = _has_active_card_by_key(state, "batch_processing")
    if has_realtime and not has_batch:
        state.automation += state.realtime_api_bonus
    if has_batch and not has_realtime:
        state.stability += state.batch_processing_bonus
    # Human in the loop: +5 to the stat that was lowest when card was placed
    for slot_idx, stat in state.human_in_loop_boost.items():
        if stat is not None and slot_idx < len(state.active_slots) and state.active_slots[slot_idx]:
            state.apply({stat: 5})
    # Fine-tune floors: clamp stats to their floors
    for stat, floor in state.fine_tune_floors.items():
        cur = state.get_stat(stat)
        if cur < floor:
            setattr(state, stat, floor)


def on_card_added_to_active(state: State, slot_idx: int, card: Card) -> None:
    """Update passive state when a card is placed in active (human_in_loop, fine_tuning)."""
    if card.key == "human_in_the_loop" and card.passive and card.passive.get("type") == "lowest_stat_boost":
        recompute_stats_from_active(state)
        stats: List[Stat] = list(STAT_ORDER)
        lowest_stat = min(stats, key=lambda s: state.get_stat(s))
        state.human_in_loop_boost[slot_idx] = lowest_stat
    if card.key == "fine_tuning" and card.passive and card.passive.get("type") == "lowest_stat_floor":
        recompute_stats_from_active(state)
        stats = list(STAT_ORDER)
        lowest_stat = min(stats, key=lambda s: state.get_stat(s))
        state.fine_tune_floors[lowest_stat] = state.get_stat(lowest_stat)
    recompute_stats_from_active(state)


def on_card_removed_from_active(state: State, slot_idx: int, card: Card) -> None:
    """Clear passive state for that slot/card (human_in_loop, fine_tuning). Per-round bonuses are kept until card is trashed."""
    state.human_in_loop_boost.pop(slot_idx, None)
    if card.key == "fine_tuning":
        state.fine_tune_floors.clear()


def on_card_trashed(state: State, card: Card) -> None:
    """When a card is trashed, clear its per-round bonus (real_time_api, batch_processing) so it stops accumulating."""
    if card.key == "real_time_api":
        state.realtime_api_bonus = 0
    if card.key == "batch_processing":
        state.batch_processing_bonus = 0


def get_active_stats(round_idx: int) -> List[Stat]:
    """All 5 stats are in play."""
    return list(STAT_ORDER)


def _get_active_passives(state: State) -> List[Tuple[Card, Dict[str, Any]]]:
    cap = get_active_slot_capacity(state)
    out: List[Tuple[Card, Dict[str, Any]]] = []
    for i in range(min(cap, len(state.active_slots))):
        card = state.active_slots[i] if i < len(state.active_slots) else None
        if card and card.passive:
            out.append((card, card.passive))
    return out


def apply_condition_passives_end_of_round(state: State) -> None:
    """Per-round passives: shadow_deployment (random stat ±1), real_time_api (+1 automation), batch_processing (+1 stability). Mutually exclusive: only one of real_time_api/batch_processing gets its bonus."""
    has_realtime = _has_active_card_by_key(state, "real_time_api")
    has_batch = _has_active_card_by_key(state, "batch_processing")
    for card, p in _get_active_passives(state):
        if p.get("type") == "random_stat_per_round":
            stat = random.choice(list(STAT_ORDER))
            delta = random.choice([-1, 1])
            state.apply({stat: delta})
        if p.get("type") == "per_round_stat":
            amount = int(p.get("amount", 0))
            if card.key == "real_time_api" and not has_batch:
                state.realtime_api_bonus += amount
            if card.key == "batch_processing" and not has_realtime:
                state.batch_processing_bonus += amount


# Target probability per draw for each rarity (renormalized if a tier is exhausted mid-deck).
_RARITY_DRAW_WEIGHTS: Tuple[Tuple[str, float], ...] = (
    ("common", 0.45),
    ("rare", 0.25),
    ("epic", 0.15),
    ("cursed", 0.15),
)


def get_deck_for_round(rng: random.Random, round_idx: int, cards_pool: Optional[List[Card]] = None) -> List[Card]:
    """
    Build the round deck from cards_pool: same cards as the pool, one each, without replacement.
    Draw order (top of stack = last list element, popped first) is chosen so each position
    picks a rarity with weights 45% common, 25% rare, 15% epic, 15% cursed among cards
    still available in that tier; empty tiers drop out and weights renormalize.
    """
    del round_idx  # reserved for future per-round variation
    if not cards_pool:
        return []

    by_rarity: Dict[str, List[Card]] = {"common": [], "rare": [], "epic": [], "cursed": []}
    for c in cards_pool:
        r = str(getattr(c, "rarity", "common") or "common").lower()
        if r not in by_rarity:
            r = "common"
        by_rarity[r].append(c)
    for bucket in by_rarity.values():
        rng.shuffle(bucket)

    remaining: Dict[str, List[Card]] = {k: list(v) for k, v in by_rarity.items()}
    total = sum(len(v) for v in remaining.values())
    draw_sequence: List[Card] = []

    while total > 0:
        tiers: List[str] = []
        weights: List[float] = []
        for tier, w in _RARITY_DRAW_WEIGHTS:
            if remaining[tier]:
                tiers.append(tier)
                weights.append(w)
        if not tiers:
            break
        wsum = sum(weights)
        tier = rng.choices(tiers, weights=[w / wsum for w in weights], k=1)[0]
        bucket = remaining[tier]
        card = bucket.pop(rng.randrange(len(bucket)))
        draw_sequence.append(card)
        total -= 1

    # Stack: pop() returns last element = first draw of the round.
    return list(reversed(draw_sequence))


# --- Phase 2: post-contract AI challenge (play a card to answer) ---

_PHASE2_QUESTION_POOL = [
    {
        "id": "q1",
        "title": "Stakeholder Trust",
        "context": "Stakeholders are concerned about understanding and trust.",
        "question": "How do you respond?",
        "acceptable": [
            "human_oversight",
            "user_communication",
            "explainable_documentation",
            "local_explainability",
            "alignment",
            "bias_fairness"
        ],
    },
    {
        "id": "q2",
        "title": "Speed vs Control",
        "context": "You need to scale quickly under pressure.",
        "question": "What do you prioritize?",
        "acceptable": [
            "full_automation",
            "real_time_api",
            "procurement_cut",
            "black_box_model",
            "shadow_deployment",
        ],
    },
    {
        "id": "q3",
        "title": "Data Sensitivity",
        "context": "Your system handles sensitive user data.",
        "question": "What approach do you take?",
        "acceptable": [
            "data_privacy",
            "ontology_integration",
            "local_explainability",
        ],
    },
    {
        "id": "q4",
        "title": "Unstable Behavior",
        "context": "The system behaves inconsistently in production.",
        "question": "What do you do?",
        "acceptable": [
            "safety_risk_control",
            "robustness_testing",
            "batch_processing",
            "ab_testing",
            "regularization",
        ],
    },
    {
        "id": "q5",
        "title": "Model Choice Tradeoff",
        "context": "You must choose between interpretability and performance.",
        "question": "What is a possible solution?",
        "acceptable": [
            "linear_regression",
            "explainable_documentation",
        ],
    },
    {
        "id": "q6",
        "title": "Bias Detection",
        "context": "Your model shows biased outcomes.",
        "question": "What action do you take?",
        "acceptable": [
            "bias_fairness",
            "alignment",
            "ontology_integration",
        ],
    },
    {
        "id": "q7",
        "title": "Deployment Strategy",
        "context": "You are deciding how to release a new system.",
        "question": "What approach do you use?",
        "acceptable": [
            "shadow_deployment",
            "real_time_api",
            "batch_processing",
            "full_automation",
            "procurement_cut",
            "human_in_the_loop",
            "human_oversight",
        ],
    },
    {
        "id": "q8",
        "title": "Overfitting Issue",
        "context": "Your model memorizes training data and fails on new inputs.",
        "question": "What term is applicable in this situation?",
        "acceptable": [
            "overfitting",
            "regularization",
            "cross_validation",
            "robustness_testing",
        ],
    },
    {
        "id": "q9",
        "title": "Misleading Outputs",
        "context": "The model produces convincing but incorrect outputs.",
        "question": "What is relevant in this situation?",
        "acceptable": [
            "hallucination",
            "human_in_the_loop",
            "local_explainability",
            "robustness_testing",
            "ab_testing",
        ],
    },
    {
        "id": "q10",
        "title": "Long-Term Degradation",
        "context": "Performance drops over time.",
        "question": "What applies here?",
        "acceptable": [
            "model_drift",
            "fine_tuning",
            "cross_validation",
            "robustness_testing",
            "regularization",
            "alignment",
            "feature_engineering",
            "ontology_integration",
            "ab_testing",
        ],
    },
    {
        "id": "q11",
        "title": "System Optimization",
        "context": "You want to improve performance without redesigning the model.",
        "question": "What do you apply?",
        "acceptable": [
            "feature_engineering",
            "fine_tuning",
            "regularization",
            "ab_testing",
            "cross_validation",
            "ontology_integration",
        ],
    },
    {
        "id": "q12",
        "title": "Resource Constraints",
        "context": "Your system is expensive and resource-heavy.",
        "question": "What do you adjust?",
        "acceptable": [
            "carbon_footprint",
        ],
    },
    {
        "id": "q13",
        "title": "Objective Exploitation",
        "context": "The system finds shortcuts to maximize its objective in unintended ways.",
        "question": "What do you change/do to address this?",
        "acceptable": [
            "reward_hacking",
            "human_oversight",
            "alignment",
            "human_in_the_loop",
            "model_drift"
        ],
    },
    {
        "id": "q14",
        "title": "Knowledge Loss",
        "context": "After updates, the model forgets previously learned behavior.",
        "question": "What is happening / what do you address?",
        "acceptable": [
            "catastrophic_forgetting",
            "fine_tuning",
        ],
    },
    {
        "id": "q15",
        "title": "Model Transparency",
        "context": "Your model performs well, but no one understands how it works.",
        "question": "What is your model?",
        "acceptable": [
            "black_box_model",
            "neural_network",
        ],
    },
    {
        "id": "q16",
        "title": "Deep Learning Choice",
        "context": "You need a highly expressive model capable of capturing complex patterns in large-scale data.",
        "question": "What model fits best here?",
        "acceptable": [
            "neural_network",
        ],
    },
    {
        "id": "q17",
        "title": "Performance Decay",
        "context": "Your model’s performance gradually worsens as real-world data shifts over time.",
        "question": "What is happening?",
        "acceptable": [
            "model_drift",
        ],
    },
    {
        "id": "q18",
        "title": "Privacy Constraints",
        "context": "You must comply with strict data protection regulations.",
        "question": "What approach do you take?",
        "acceptable": [
            "data_privacy",
        ],
    },
    {
        "id": "q19",
        "title": "Feature Impact",
        "context": "Performance depends heavily on how inputs are structured.",
        "question": "What do you apply?",
        "acceptable": [
            "feature_engineering",
            "fine_tuning",
            "regularization",
        ],
    },
    {
        "id": "q20",
        "title": "Full Automation Push",
        "context": "Leadership wants zero human involvement.",
        "question": "What do you prioritize?",
        "acceptable": [
            "full_automation",
            "real_time_api",
            "neural_network",
            "procurement_cut",
            "reward_hacking",
        ],
    },
    {
        "id": "q21",
        "title": "False Outputs",
        "context": "The system produces confident but incorrect answers.",
        "question": "What is this?",
        "acceptable": [
            "hallucination",
        ],
    },
    {
        "id": "q22",
        "title": "Human Intervention",
        "context": "Critical decisions require human judgment.",
        "question": "What do you implement?",
        "acceptable": [
            "human_in_the_loop",
            "human_oversight",
            "alignment",
        ],
    },
    {
        "id": "q23",
        "title": "Simple Model Choice",
        "context": "You need a lightweight, interpretable solution.",
        "question": "What do you choose?",
        "acceptable": [
            "linear_regression",
        ],
    },
    {
        "id": "q24",
        "title": "High Performance Model",
        "context": "You need maximum predictive power.",
        "question": "What do you deploy?",
        "acceptable": [
            "neural_network",
            "black_box_model",
            "full_automation",
            "real_time_api",
            "feature_engineering",
        ],
    },
    {
        "id": "q25",
        "title": "Degrading System",
        "context": "The model slowly becomes unreliable over time.",
        "question": "What applies here?",
        "acceptable": [
            "model_drift",
            "catastrophic_forgetting",
            "fine_tuning",
            "cross_validation",
            "robustness_testing",
        ],
    },
    {
        "id": "q26",
        "title": "Generalization Failure",
        "context": "Your model fails on unseen data.",
        "question": "What is happening?",
        "acceptable": [
            "overfitting",
        ],
    },
    {
        "id": "q27",
        "title": "Low Latency Requirement",
        "context": "Your system must respond instantly to users.",
        "question": "What do you use?",
        "acceptable": [
            "real_time_api",
            "full_automation",
        ],
    },
    {
        "id": "q28",
        "title": "Exploited Objective",
        "context": "The system optimizes the wrong goal.",
        "question": "What is happening?",
        "acceptable": [
            "reward_hacking",
        ],
    },
    {
        "id": "q29",
        "title": "Safety Concerns",
        "context": "The system may cause harm if it fails.",
        "question": "What do you prioritize?",
        "acceptable": [
            "safety_risk_control",
            "human_oversight",
            "alignment",
            "robustness_testing",
            "ab_testing",
        ],
    },
    {
        "id": "q30",
        "title": "Silent Deployment",
        "context": "You want to test the system without users noticing.",
        "question": "What do you use?",
        "acceptable": [
            "shadow_deployment",
        ],
    },
    {
        "id": "q31",
        "title": "User Confusion",
        "context": "Users don't understand system decisions.",
        "question": "What do you improve?",
        "acceptable": [
            "user_communication",
            "explainable_documentation",
            "local_explainability",
        ],
    },
    {
        "id": "q32",
        "title": "Tradeoff Decision",
        "context": "Improving performance reduces transparency.",
        "question": "What did you do?",
        "acceptable": [
            "neural_network",
            "black_box_model",
        ],
    },
    {
        "id": "q33",
        "title": "System Scaling",
        "context": "Your system must scale to millions of users.",
        "question": "What do you prioritize?",
        "acceptable": [
            "full_automation",
            "real_time_api",
        ],
    },
]


def get_phase2_question_bank() -> List[Dict[str, Any]]:
    """Question bank for Phase 2.

    Each question lists card keys that are valid answers.
    Returned dicts use the shape the game UI expects: {id, question, acceptable}.
    """

    out: List[Dict[str, Any]] = []
    for q in _PHASE2_QUESTION_POOL:
        out.append(
            {
                "id": q["id"],
                "question": f"{q['context']}\n{q['question']}",
                "acceptable": list(q["acceptable"]),
            }
        )
    return out


def pick_phase2_questions(rng: random.Random, player_keys: set[str], count: int = 5) -> List[Dict[str, Any]]:
    """Pick a question set that can always be won when played correctly.

    Rules enforced by the selector:
    1. Every selected question has at least one accepted answer in the player's hand.
    2. No card in the player's hand is accepted by more than one selected question
       (prevents later questions becoming impossible because cards get used/removed).
    """
    if not player_keys:
        return []

    desired = min(max(0, count), len(player_keys))
    if desired <= 0:
        return []

    bank = get_phase2_question_bank()
    # Candidate questions and which of the player's keys they accept.
    candidates: List[Tuple[Dict[str, Any], set[str]]] = []
    for q in bank:
        acc_in_hand = set(q.get("acceptable") or []) & player_keys
        if acc_in_hand:
            candidates.append((q, acc_in_hand))

    # Randomize search order but keep deterministic w.r.t. `rng`.
    rng.shuffle(candidates)

    for k in range(desired, 0, -1):
        best: List[Dict[str, Any]] | None = None

        def dfs(start_idx: int, chosen: List[Dict[str, Any]], used_cards: set[str]) -> None:
            nonlocal best
            if best is not None:
                return
            if len(chosen) >= k:
                best = list(chosen[:k])
                return
            if start_idx >= len(candidates):
                return
            # Not enough candidates left even if we took them all.
            if len(chosen) + (len(candidates) - start_idx) < k:
                return

            for i in range(start_idx, len(candidates)):
                if best is not None:
                    return
                q, acc_in_hand = candidates[i]
                if acc_in_hand & used_cards:
                    continue
                dfs(i + 1, chosen + [q], used_cards | acc_in_hand)

        dfs(0, [], set())
        if best is not None:
            return best

    return []


# --- Final stage: hospital triage ---

def get_final_stage_intro() -> List[str]:
    return [
        "FINAL STAGE — HOSPITAL TRIAGE",
        "",
        "Your company's model is being evaluated for use in a hospital.",
        "Setting: Triage classification — is this patient in need of urgent care, or not?",
        "The board will approve deployment only if your design and your track record",
        "(Transparency, Stability, Automation, Generalizability, Integrity) meet clinical and ethical standards.",
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
                    "requires": {"integrity": 5},
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
                    "requires": {"integrity": 5},
                    "readiness_delta": 1,
                    "hint": "Requires prior investment in Fairness.",
                },
                {
                    "text": "Fairness constraints in training — e.g. parity or equalized odds.",
                    "requires": {"integrity": 6},
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
                    "requires": {"integrity": 5},
                    "readiness_delta": 1,
                    "hint": "Slower; Trust helps justify the delay.",
                },
                {
                    "text": "Shadow mode first — model runs in parallel, no impact on care until validated.",
                    "requires": {"integrity": 4, "transparency": 4},
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
                    "requires": {"integrity": 5},
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
    base = (
        max(0, state.transparency - 3)
        + max(0, state.integrity - 3)
        + max(0, state.stability - 3)
        + max(0, state.generalizability - 3)
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
            "Your combination of design choices and the transparency, stability, integrity,",
            "generalizability, and automation you built over the run met their bar.",
            "The system will be used to support — not replace — clinical judgment.",
        ]
    else:
        title = "HOSPITAL DEFERS DEPLOYMENT"
        lines = [
            "The board defers deployment. They cite gaps in explainability, stability,",
            "integrity, or the balance of automation vs human oversight.",
            "Your run stats and final-stage choices did not meet their threshold.",
            "They ask you to revisit architecture and governance and re-apply next year.",
        ]
    return title, lines, success
