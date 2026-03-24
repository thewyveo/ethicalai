from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

Stat = Literal["transparency", "stability", "automation", "generalizability", "integrity"]


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    text: str
    effects: Dict[Stat, int]
    suit: Literal["r", "w"] = "w"  # r = red border, w = white border (from cards.txt)
    rarity: Literal["common", "rare", "epic", "cursed"] = "common"
    art: str | None = None
    passive: Dict[str, Any] | None = None


@dataclass
class State:
    rounds_total: int = 11
    round_idx: int = 1
    scenario_key: str | None = None

    transparency: int = 5
    stability: int = 5
    automation: int = 5
    generalizability: int = 5
    integrity: int = 5

    score: int = 0
    active_slots: List["Card | None"] = field(default_factory=lambda: [None] * 6)  # 5 base + 1 if carbon_footprint active

    # Per-card passive state (updated when cards added/removed or each round)
    realtime_api_bonus: int = 0
    batch_processing_bonus: int = 0
    human_in_loop_boost: Dict[int, Optional[Stat]] = field(default_factory=dict)  # slot_idx -> stat that gets +5
    # Stats that tied for highest when Fine-Tuning was added to active; each gets +amount on recompute.
    fine_tune_boost_stats: List[Stat] = field(default_factory=list)
    # Feature engineering: id(card) -> bound stat; recompute adds that stat's snapshot (pre-FE doubling) once per instance
    feature_engineering_stat_by_card_id: Dict[int, Stat] = field(default_factory=dict)

    def apply(self, effects: Dict[Stat, int]) -> None:
        for stat, delta in effects.items():
            if hasattr(self, stat):
                setattr(self, stat, getattr(self, stat) + int(delta))

    def base_points(self) -> int:
        return (
            self.transparency
            + self.stability
            + self.automation
            + self.generalizability
            + self.integrity
        )

    def get_stat(self, stat: Stat) -> int:
        return getattr(self, stat)
