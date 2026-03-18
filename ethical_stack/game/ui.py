from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ethical_stack.game.model import Blind, Card, RunState, format_effects


@dataclass(frozen=True)
class Choice:
    key: str
    label: str


class UI:
    def __init__(self) -> None:
        self.console = Console()

    def clear(self) -> None:
        self.console.clear()

    def title(self, subtitle: str | None = None) -> None:
        t = Text("ETHICAL STACK", style="bold magenta")
        if subtitle:
            t.append("  ")
            t.append(subtitle, style="bold cyan")
        self.console.print(Align.center(t))
        self.console.print()

    def story(self, lines: Sequence[str]) -> None:
        if not lines:
            return
        body = "\n".join(lines)
        self.console.print(Panel(body, title="Log", border_style="cyan", box=box.ROUNDED))
        self.console.print()

    def stats_panel(self, s: RunState) -> None:
        display_round = min(s.round_idx, s.rounds_total)
        tbl = Table.grid(expand=True)
        tbl.add_column(justify="center")
        tbl.add_column(justify="center")
        tbl.add_column(justify="center")
        tbl.add_column(justify="center")
        tbl.add_column(justify="center")

        def stat_cell(name: str, v: int, style: str) -> Text:
            t = Text()
            t.append(name, style=f"bold {style}")
            t.append("\n")
            t.append(str(v), style=f"bold {style}")
            return t

        tbl.add_row(
            stat_cell("TRUST", s.trust, "green"),
            stat_cell("AUTO", s.automation, "yellow"),
            stat_cell("FAIR", s.fairness, "blue"),
            stat_cell("TRANS", s.transparency, "cyan"),
            stat_cell("RISK", s.risk, "red"),
        )
        self.console.print(Panel(tbl, title=f"Round {display_round}/{s.rounds_total}", border_style="magenta"))

    def cards_table(self, cards: Sequence[Card], title: str = "Hand") -> None:
        table = Table(title=title, box=box.SIMPLE_HEAVY, border_style="white")
        table.add_column("#", justify="right", style="bold")
        table.add_column("Card", style="bold")
        table.add_column("Effects", style="white")
        table.add_column("Flavor", style="dim")
        for i, c in enumerate(cards, start=1):
            rarity_style = {"common": "white", "uncommon": "cyan", "rare": "magenta"}[c.rarity]
            table.add_row(str(i), Text(c.name, style=rarity_style), c.effect_line(), c.flavor)
        self.console.print(table)

    def blinds_table(self, blinds: Sequence[Blind]) -> None:
        table = Table(title="Choose a Blind", box=box.SIMPLE_HEAVY, border_style="white")
        table.add_column("#", justify="right", style="bold")
        table.add_column("Blind", style="bold yellow")
        table.add_column("Tagline", style="cyan")
        table.add_column("Rule", style="white")
        for i, b in enumerate(blinds, start=1):
            table.add_row(str(i), b.name, b.tagline, b.rule_text)
        self.console.print(table)

    def prompt(self, text: str) -> str:
        try:
            return self.console.input(f"[bold cyan]{text}[/bold cyan] ")
        except EOFError:
            # Non-interactive environments (tests/CI) should not crash.
            return ""

    def pause(self, text: str = "Press Enter to continue.") -> None:
        try:
            _ = self.console.input(f"[dim]{text}[/dim]")
        except EOFError:
            return

    def banner(self, title: str, body: str, style: str = "cyan") -> None:
        self.console.print(Panel(body, title=title, border_style=style, box=box.ROUNDED))
        self.console.print()

    def round_scoring(self, base: int, blind_delta: int, soft_penalty: int, total: int, blind_name: str) -> None:
        t = Table(title="Round Score", box=box.SIMPLE_HEAVY, border_style="white")
        t.add_column("Part", style="bold")
        t.add_column("Value", justify="right")
        t.add_row("Base (sum of 4 stats)", str(base))
        t.add_row(f"Blind: {blind_name}", f"{blind_delta:+d}")
        if soft_penalty:
            t.add_row("Soft penalties", f"{soft_penalty:+d}")
        t.add_row("Total added", str(total), style="bold green")
        self.console.print(t)
        self.console.print()

    def effects_popup(self, title: str, effects: dict) -> None:
        self.console.print(Panel(format_effects(effects), title=title, border_style="yellow"))

    def final_score(self, s: RunState, bonuses: dict[str, int]) -> None:
        base = s.trust + s.automation + s.fairness + s.transparency
        bonus_total = sum(bonuses.values())
        grand = base + bonus_total

        t = Table(title="Final Score", box=box.SIMPLE_HEAVY, border_style="white")
        t.add_column("Component", style="bold")
        t.add_column("Value", justify="right")
        t.add_row("Trust", str(s.trust))
        t.add_row("Automation", str(s.automation))
        t.add_row("Fairness", str(s.fairness))
        t.add_row("Transparency", str(s.transparency))
        t.add_row("Base", str(base), style="bold")
        if bonuses:
            for k, v in bonuses.items():
                t.add_row(k, f"+{v}", style="magenta")
        t.add_row("Grand Total", str(grand), style="bold green")
        self.console.print(t)

