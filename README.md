# Ethical Stack

A singleplayer card game about **ethical AI tradeoffs**, inspired by the digital card game Balatro:
you draw cards, assemble an **ACTIVE** deck, and your stats determine whether deployment is approved.

You track 5 stats, computed from your **ACTIVE** cards:

- **Transparency**
- **Stability**
- **Automation**
- **Generalizability**
- **Integrity**

Cards have two kinds of impact:

- **Stat effects** (when placed in ACTIVE)
- **Passives** (some cards have special abilities)

## Game flow

### Phase 1: Deployment run

1. A deployment scenario (contract) is chosen randomly when you start.
2. For each round (total of 10), do the following: Click **DECK** to draw **up to 3** cards into your **Hand** (Hand is capped at **5**). Drag cards from **Hand** to **ACTIVE** (equip) or **TRASH** (discard). Stats update immediately when you equip/remove cards.
3. Click **DECK** to advance to the next round, and get dealt another up to 3 cards.
4. **Hard loss:** if *any* of the 5 stats drops below **0** at any point, the run fails immediately.
5. **Contract check:** After round 10, your stats are compared against the randomly selected contract requirements.

If your build meets all minimum thresholds, you proceed to Phase 2.
If it does not, deployment is denied and the run ends.

### Phase 2: Readiness quiz

If the contract is satisfied, you enter phase 2. Your active cards in phase 1 become your hand. You must answer a set of questions using your hand.

Click the card that best matches the question's acceptable answers.
Failure: you can make at most **one** mistake overall (you effectively need at least `N-1` correct picks). After enough wrong picks (strikes), the quiz ends and deployment is denied.

If you pass the quiz, deployment is approved.




## Run

Default = the pygame pixel UI:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m ethical_stack
```




## Credits

- Dev 1: Kayra
- Dev 2: Fatih

This game was built as a group project for the course Ethical AI.
Group 21.

