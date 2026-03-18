# Ethical Stack (Balatro-inspired) — Pixel UI

A tiny singleplayer card game about **ethical AI tradeoffs**, styled like Balatro’s loop: **draw cards**, **pick plays**, manage **risk**, and chase a **high score** — now with a simple **pixel-table graphical UI**.

## What you do

- You have four stats: **Trust**, **Automation**, **Fairness**, **Transparency**
- Cards apply flat stat changes and also affect **Risk**
- Game lasts **5 rounds**
- Each round:
  - Draw up to a hand limit
  - Select up to **2** cards and **PLAY** them
  - **END** the round to score and run a **Risk Check**

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m ethical_stack
```

## Controls

- Mouse:
  - Click cards to select (max 2)
  - Click **PLAY** to commit selected cards
  - Click **END** to finish the round

## Balatro-ish pressure mechanic

**Risk** is your “push-your-luck” meter:

- At **Risk ≥ 5**, there’s a 50% chance of a negative incident at round end
- At **Risk ≥ 8**, an incident is guaranteed and harsher

Greedy Automation / Black Box decisions can spike points, but also spike Risk and collapse the run.

## Notes

Graphics are placeholders (simple pixel rectangles + stripes). You can swap in real card art later.

