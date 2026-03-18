from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

Stat = Literal["trust", "automation", "fairness", "transparency"]


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    text: str
    effects: Dict[Stat, int]
    suit: Literal["spade", "heart", "club", "diamond"] = "spade"
    rarity: Literal["common", "uncommon", "rare"] = "common"


@dataclass
class State:
    rounds_total: int = 13
    round_idx: int = 1

    trust: int = 5
    automation: int = 5
    fairness: int = 5
    transparency: int = 5

    score: int = 0

    def apply(self, effects: Dict[Stat, int]) -> None:
        self.trust += int(effects.get("trust", 0))
        self.automation += int(effects.get("automation", 0))
        self.fairness += int(effects.get("fairness", 0))
        self.transparency += int(effects.get("transparency", 0))

    def base_points(self) -> int:
        return self.trust + self.automation + self.fairness + self.transparency

    def get_stat(self, stat: Stat) -> int:
        return getattr(self, stat)
