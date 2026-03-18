from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Tuple

Stat = Literal["trust", "automation", "fairness", "transparency", "risk"]


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    flavor: str
    effects: Dict[Stat, int]
    rarity: Literal["common", "uncommon", "rare"] = "common"

    def effect_line(self) -> str:
        parts: List[str] = []
        for stat in ("trust", "automation", "fairness", "transparency", "risk"):
            v = int(self.effects.get(stat, 0))
            if v:
                sign = "+" if v > 0 else ""
                parts.append(f"{stat[:1].upper()}{stat[1:3]} {sign}{v}")
        return " • ".join(parts) if parts else "No effect"


@dataclass(frozen=True)
class Blind:
    key: str
    name: str
    tagline: str
    rule_text: str


@dataclass
class RunState:
    round_idx: int = 1
    rounds_total: int = 5

    trust: int = 5
    automation: int = 5
    fairness: int = 5
    transparency: int = 5
    risk: int = 0

    score: int = 0
    log: List[str] | None = None

    def stats_tuple(self) -> Tuple[int, int, int, int]:
        return (self.trust, self.automation, self.fairness, self.transparency)

    def as_dict(self) -> Dict[str, int]:
        return {
            "trust": self.trust,
            "automation": self.automation,
            "fairness": self.fairness,
            "transparency": self.transparency,
            "risk": self.risk,
        }

    def apply(self, effects: Dict[Stat, int]) -> None:
        self.trust += int(effects.get("trust", 0))
        self.automation += int(effects.get("automation", 0))
        self.fairness += int(effects.get("fairness", 0))
        self.transparency += int(effects.get("transparency", 0))
        self.risk += int(effects.get("risk", 0))
        if self.risk < 0:
            self.risk = 0

    def add_log(self, line: str) -> None:
        if self.log is None:
            self.log = []
        self.log.append(line)


@dataclass(frozen=True)
class Event:
    key: str
    name: str
    blurb: str
    effects: Dict[Stat, int]


def clamp_nonneg(x: int) -> int:
    return x if x >= 0 else 0


def format_effects(effects: Dict[Stat, int]) -> str:
    order: Iterable[Stat] = ("trust", "automation", "fairness", "transparency", "risk")
    parts: List[str] = []
    for s in order:
        v = int(effects.get(s, 0))
        if v:
            sign = "+" if v > 0 else ""
            parts.append(f"{s.capitalize()} {sign}{v}")
    return ", ".join(parts) if parts else "No change"

