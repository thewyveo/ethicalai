from collections import Counter, defaultdict
from statistics import mean, median

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

# Put every card that exists in your game here.
ALL_CARDS = [
    "human_oversight",
    "full_automation",
    "user_communication",
    "explainable_documentation",
    "black_box_model",
    "human_in_the_loop",
    "bias_fairness",
    "data_privacy",
    "safety_risk_control",
    "alignment",
    "model_drift",
    "regularization",
    "robustness_testing",
    "local_explainability",
    "overfitting",
    "neural_network",
    "linear_regression",
    "real_time_api",
    "batch_processing",
    "feature_engineering",
    "ab_testing",
    "shadow_deployment",
    "procurement_cut",
    "carbon_footprint",
    "reward_hacking",
    "hallucination",
    "fine_tuning",
    "ontology_integration",
    "cross_validation",
    "catastrophic_forgetting",
]

# Tweak these thresholds to match your design goals.
MIN_ACCEPTABLES_PER_QUESTION = 4
MIN_CARD_COVERAGE = 2  # how many different questions a card should appear in at minimum


def analyze_question_pool(question_pool, all_cards):
    coverage = Counter()
    card_to_questions = defaultdict(list)
    question_sizes = {}
    duplicate_ids = set()
    seen_ids = set()

    for q in question_pool:
        qid = q["id"]
        if qid in seen_ids:
            duplicate_ids.add(qid)
        seen_ids.add(qid)

        acceptable = q["acceptable"]
        question_sizes[qid] = len(acceptable)

        for card in acceptable:
            coverage[card] += 1
            card_to_questions[card].append(qid)

    dead_cards = [c for c in all_cards if coverage[c] == 0]
    underrepresented_cards = [c for c in all_cards if 0 < coverage[c] < MIN_CARD_COVERAGE]
    low_branch_questions = [
        q for q in question_pool if len(q["acceptable"]) < MIN_ACCEPTABLES_PER_QUESTION
    ]

    unknown_cards_in_questions = sorted(
        {card for q in question_pool for card in q["acceptable"] if card not in all_cards}
    )

    unused_question_count = len(question_pool)
    avg_acceptables = mean(question_sizes.values()) if question_sizes else 0
    med_acceptables = median(question_sizes.values()) if question_sizes else 0
    min_acceptables = min(question_sizes.values()) if question_sizes else 0
    max_acceptables = max(question_sizes.values()) if question_sizes else 0

    return {
        "coverage": coverage,
        "card_to_questions": card_to_questions,
        "dead_cards": dead_cards,
        "underrepresented_cards": underrepresented_cards,
        "low_branch_questions": low_branch_questions,
        "unknown_cards_in_questions": unknown_cards_in_questions,
        "duplicate_ids": sorted(duplicate_ids),
        "stats": {
            "num_questions": unused_question_count,
            "num_cards": len(all_cards),
            "avg_acceptables_per_question": avg_acceptables,
            "median_acceptables_per_question": med_acceptables,
            "min_acceptables_per_question": min_acceptables,
            "max_acceptables_per_question": max_acceptables,
        },
    }


def print_report(result):
    print("=" * 80)
    print("PHASE 2 QUESTION POOL ANALYSIS")
    print("=" * 80)
    print()

    print("Summary")
    for k, v in result["stats"].items():
        print(f"- {k}: {v}")
    print()

    if result["duplicate_ids"]:
        print("Duplicate question IDs found:")
        for qid in result["duplicate_ids"]:
            print(f"  - {qid}")
        print()
    else:
        print("No duplicate question IDs found.\n")

    if result["unknown_cards_in_questions"]:
        print("Cards referenced in questions but missing from ALL_CARDS:")
        for card in result["unknown_cards_in_questions"]:
            print(f"  - {card}")
        print()
    else:
        print("No unknown card references found.\n")

    print("Question sizes")
    for q in _PHASE2_QUESTION_POOL:
        n = len(q["acceptable"])
        status = "OK" if n >= MIN_ACCEPTABLES_PER_QUESTION else "TOO LOW"
        print(f"- {q['id']} ({q['title']}): {n} acceptable cards [{status}]")
    print()

    if result["low_branch_questions"]:
        print(f"Questions with fewer than {MIN_ACCEPTABLES_PER_QUESTION} acceptable cards:")
        for q in result["low_branch_questions"]:
            print(f"  - {q['id']} ({q['title']}): {len(q['acceptable'])} acceptable")
        print()
    else:
        print(f"All questions have at least {MIN_ACCEPTABLES_PER_QUESTION} acceptable cards.\n")

    print("Card coverage counts")
    for card in sorted(ALL_CARDS):
        count = result["coverage"][card]
        if count == 0:
            flag = "DEAD"
        elif count < MIN_CARD_COVERAGE:
            flag = "UNDERREPRESENTED"
        else:
            flag = "OK"
        print(f"- {card}: {count} question(s) [{flag}]")
    print()

    if result["dead_cards"]:
        print("Dead cards (appear in 0 questions):")
        for card in result["dead_cards"]:
            print(f"  - {card}")
        print()
    else:
        print("No dead cards.\n")

    if result["underrepresented_cards"]:
        print(f"Underrepresented cards (appear in < {MIN_CARD_COVERAGE} questions):")
        for card in result["underrepresented_cards"]:
            print(f"  - {card}: {result['coverage'][card]} question(s)")
        print()
    else:
        print(f"No underrepresented cards using threshold < {MIN_CARD_COVERAGE}.\n")

    print("Question membership by card")
    for card in sorted(ALL_CARDS):
        qids = result["card_to_questions"].get(card, [])
        print(f"- {card}: {qids}")
    print()

    print("Suggested next action")
    if result["dead_cards"] or result["underrepresented_cards"] or result["low_branch_questions"]:
        print("- Add questions that include dead / underrepresented cards.")
        print("- Increase acceptable-card counts for low-branch questions.")
        print("- Prefer new questions that solve multiple weak cards at once.")
    else:
        print("- Coverage looks healthy based on the current thresholds.")
    print()


if __name__ == "__main__":
    result = analyze_question_pool(_PHASE2_QUESTION_POOL, ALL_CARDS)
    print_report(result)