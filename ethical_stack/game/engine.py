from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence

from ethical_stack.game.content import (
    blind_score_delta,
    blind_story,
    blinds,
    build_deck,
    final_bonuses,
    risk_events,
    story_intro,
    story_round_open,
)
from ethical_stack.game.model import Blind, Card, Event, RunState
from ethical_stack.game.ui import UI


@dataclass
class RoundContext:
    blind: Blind
    hand: List[Card]
    played: List[Card]


class Game:
    def __init__(self, seed: int | None = None, interactive: bool = True) -> None:
        self.rng = random.Random(seed)
        self.ui = UI()
        self.state = RunState()
        self.deck: List[Card] = []
        self._events: Sequence[Event] = risk_events()
        self.interactive = interactive

    def run(self) -> None:
        self.ui.clear()
        self.ui.title("A Balatro-ish ethical AI run")
        self.ui.story(story_intro())
        self.ui.pause()

        self.deck = build_deck(self.rng)

        while self.state.round_idx <= self.state.rounds_total:
            ctx = self.play_round()
            if ctx is None:
                return
            if self._check_hard_losses():
                return
            self.state.round_idx += 1

        self._end_screen()

    def play_round(self) -> RoundContext | None:
        self.ui.clear()
        self.ui.title()
        self.ui.stats_panel(self.state)
        self.ui.story(story_round_open(self.state.round_idx))

        blind = self._choose_blind()
        self.ui.story(blind_story(blind.key))

        hand = self._draw_hand(3)
        played: List[Card] = []

        plays = self._choose_plays(hand)
        for idx in plays:
            card = hand[idx]
            played.append(card)
            self.state.apply(card.effects)

        self.ui.clear()
        self.ui.title(f"Round {self.state.round_idx} results")
        self.ui.stats_panel(self.state)

        if played:
            self.ui.cards_table(played, title="Played")
        else:
            self.ui.banner("No play", "You hold your cards close. Sometimes restraint is a strategy.", style="cyan")

        soft_penalty = self._apply_soft_rules()
        if self._check_hard_losses():
            return None

        risk_event = self._risk_check()
        if risk_event is not None:
            self.ui.banner(risk_event.name, risk_event.blurb, style="red")
            self.ui.effects_popup("Event effects", risk_event.effects)
            self.state.apply(risk_event.effects)
            if self._check_hard_losses():
                return None

        base = self.state.trust + self.state.automation + self.state.fairness + self.state.transparency
        blind_delta = blind_score_delta(blind.key, self.state.as_dict())
        round_total = max(0, base + blind_delta + soft_penalty)
        self.state.score += round_total

        self.ui.round_scoring(
            base=base,
            blind_delta=blind_delta,
            soft_penalty=soft_penalty,
            total=round_total,
            blind_name=blind.name,
        )
        self.ui.banner("Score", f"Run Score is now: {self.state.score}", style="magenta")
        self.ui.pause()

        return RoundContext(blind=blind, hand=hand, played=played)

    def _choose_blind(self) -> Blind:
        options = list(blinds())
        if not self.interactive:
            # Simple heuristic: pick a Blind that pressures the weakest dimension.
            t, a, f, x = self.state.trust, self.state.automation, self.state.fairness, self.state.transparency
            if min(t, f) <= 2:
                return next(b for b in options if b.key == "civil_rights_hearing")
            if x <= 2:
                return next(b for b in options if b.key == "press_tour")
            if self.state.risk >= 5:
                return next(b for b in options if b.key == "incident_response")
            if a < 6:
                return next(b for b in options if b.key == "investor_demo")
            return self.rng.choice(options)

        self.ui.blinds_table(options)
        while True:
            raw = self.ui.prompt("Pick a Blind (1-5)")
            try:
                n = int(raw.strip())
            except ValueError:
                continue
            if 1 <= n <= len(options):
                return options[n - 1]

    def _draw_hand(self, n: int) -> List[Card]:
        if len(self.deck) < n:
            # reshuffle a fresh deck for simplicity
            self.deck = build_deck(self.rng)
        hand = [self.deck.pop() for _ in range(n)]
        self.ui.cards_table(hand)
        return hand

    def _choose_plays(self, hand: List[Card]) -> List[int]:
        if not self.interactive:
            return self._auto_pick(hand)

        self.ui.banner(
            "Play",
            "Choose up to 2 cards to play. Enter numbers like: 1 3\nOr press Enter to play none.",
            style="yellow",
        )
        while True:
            raw = self.ui.prompt("Your play")
            raw = raw.strip()
            if not raw:
                return []
            bits = raw.replace(",", " ").split()
            try:
                nums = [int(b) for b in bits]
            except ValueError:
                continue
            nums = [n for n in nums if 1 <= n <= len(hand)]
            nums = list(dict.fromkeys(nums))  # unique, keep order
            if len(nums) > 2:
                continue
            return [n - 1 for n in nums]

    def _auto_pick(self, hand: List[Card]) -> List[int]:
        """
        Non-interactive autoplayer:
        pick up to 2 cards that increase "good" stats while controlling risk.
        """
        def eval_card(c: Card) -> float:
            e = c.effects
            # prioritize not losing (trust/fairness) and building a decent base.
            return (
                1.5 * e.get("trust", 0)
                + 1.2 * e.get("fairness", 0)
                + 1.0 * e.get("transparency", 0)
                + 0.8 * e.get("automation", 0)
                - 1.4 * e.get("risk", 0)
            )

        scored = sorted([(eval_card(c), i) for i, c in enumerate(hand)], reverse=True)
        picks: List[int] = []
        trial = RunState(
            round_idx=self.state.round_idx,
            rounds_total=self.state.rounds_total,
            trust=self.state.trust,
            automation=self.state.automation,
            fairness=self.state.fairness,
            transparency=self.state.transparency,
            risk=self.state.risk,
            score=self.state.score,
        )

        for _, i in scored:
            if len(picks) >= 2:
                break
            trial.apply(hand[i].effects)
            if trial.trust < 0 or trial.fairness < 0:
                # Don't auto-pick a losing line.
                trial = RunState(
                    round_idx=self.state.round_idx,
                    rounds_total=self.state.rounds_total,
                    trust=self.state.trust,
                    automation=self.state.automation,
                    fairness=self.state.fairness,
                    transparency=self.state.transparency,
                    risk=self.state.risk,
                    score=self.state.score,
                )
                for j in picks:
                    trial.apply(hand[j].effects)
                continue
            picks.append(i)
        return picks

    def _apply_soft_rules(self) -> int:
        """
        Soft constraints that create Balatro-like tension without complexity.
        Returns a score delta (usually negative) to be added for the round.
        """
        penalty = 0

        # Over-automation bleeds trust.
        if self.state.automation > 10:
            overflow = self.state.automation - 10
            self.state.trust -= overflow
            penalty -= overflow * 2
            self.ui.banner(
                "Automation Overload",
                f"Automation exceeded 10 by {overflow}. Trust drops by {overflow}.",
                style="yellow",
            )

        # Low transparency erodes trust every round.
        if self.state.transparency < 2:
            self.state.trust -= 1
            penalty -= 2
            self.ui.banner(
                "Opaque System",
                "Transparency is below 2. Trust drops by 1 this round.",
                style="yellow",
            )

        return penalty

    def _risk_check(self) -> Event | None:
        """
        The one added mechanic: Risk triggers negative events.
        - Risk >= 8: guaranteed event
        - Risk >= 5: 50% chance
        """
        if self.state.risk >= 8:
            return self.rng.choice(self._events)
        if self.state.risk >= 5 and self.rng.random() < 0.5:
            return self.rng.choice(self._events)
        return None

    def _check_hard_losses(self) -> bool:
        if self.state.trust < 0:
            self._game_over("Trust collapsed", "No one will use a system they don’t believe in.")
            return True
        if self.state.fairness < 0:
            self._game_over("Fairness collapsed", "Harm scales faster than any metric.")
            return True
        return False

    def _game_over(self, title: str, reason: str) -> None:
        self.ui.clear()
        self.ui.title("RUN FAILED")
        self.ui.banner(title, reason, style="red")
        self.ui.banner("Final run score", str(self.state.score), style="magenta")
        self.ui.pause("Press Enter to exit.")

    def _end_screen(self) -> None:
        self.ui.clear()
        self.ui.title("RUN COMPLETE")
        self.ui.stats_panel(self.state)
        bonuses = final_bonuses(self.state.as_dict())
        self.ui.final_score(self.state, bonuses)
        self.ui.banner("Run Score (round totals)", str(self.state.score), style="magenta")
        self.ui.pause("Press Enter to exit.")

