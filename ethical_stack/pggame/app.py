from __future__ import annotations

import os
import random
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ethical_stack.pggame.content import (
    ACTIVE_SLOT_CAPACITY,
    apply_condition_passives_end_of_round,
    contract_fulfilled,
    get_active_slot_capacity,
    get_active_stats,
    get_contract_name,
    get_contract_requirements,
    get_contracts,
    get_deck_for_round,
    pick_phase2_questions,
    get_final_stage_intro,
    get_final_stage_outcome,
    get_final_stage_questions,
    get_round_constraint,
    get_scenario_objective_lines,
    get_scenario_objective_text,
    load_cards_from_file,
    on_card_added_to_active,
    on_card_removed_from_active,
    on_card_trashed,
    recompute_stats_from_active,
)
from ethical_stack.pggame.model import Card, State, Stat


# --- Visual constants (simple “Balatro-ish” table vibe) ---
# Higher internal res + lower scale = sharper text.
LOW_W, LOW_H = 650, 450
SCALE = 2
W, H = int(LOW_W * SCALE), int(LOW_H * SCALE)

FELT = (20, 110, 60)
FELT_DARK = (15, 85, 45)
GOLD = (235, 205, 120)
INK = (20, 18, 20)
PAPER = (240, 236, 228)
PAPER_DARK = (214, 208, 196)
RED = (220, 72, 72)
BLUE = (60, 140, 220)
WHITE = (255, 255, 255)


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    enabled: bool = True


def run_game(seed: int | None = None, headless: bool = False, admin_phase2: bool = False) -> None:
    """
    Run the graphical game.

    Note: In some headless environments (CI/sandboxes), opening a real window can abort.
    We fall back to SDL's dummy video driver so the module can still be executed safely.
    """
    try:
        pygame.init()
        _run(seed=seed, headless=headless, admin_phase2=admin_phase2)
    except Exception:
        # Retry once with dummy drivers (no real window).
        try:
            pygame.quit()
        except Exception:
            pass
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        _run(seed=seed, headless=True, admin_phase2=admin_phase2)
    finally:
        pygame.quit()


def _run(seed: int | None = None, headless: bool = False, admin_phase2: bool = False) -> None:
    rng = random.Random(seed)

    window = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Ethical Stack — Balatro-ish prototype")

    screen = pygame.Surface((LOW_W, LOW_H))

    # Compact fonts for more card space; crisp pixel look.
    try:
        font = pygame.font.SysFont("Arial", 14, bold=True)
        font_small = pygame.font.SysFont("Arial", 12, bold=True)
        font_big = pygame.font.SysFont("Arial", 20, bold=True)
        font_tiny = pygame.font.SysFont("Arial", 10, bold=True)
    except Exception:
        font = pygame.font.Font(None, 20)
        font_small = pygame.font.Font(None, 16)
        font_big = pygame.font.Font(None, 26)
        font_tiny = pygame.font.Font(None, 14)

    def rtxt(f: pygame.font.Font, text: str, color: Tuple[int, int, int], bold_px: int = 1) -> pygame.Surface:
        """Pixel-crisp text with slight bolding (keeps readability)."""
        base = f.render(text, True, color)
        if bold_px <= 0:
            return base
        surf = pygame.Surface((base.get_width() + bold_px, base.get_height() + bold_px), pygame.SRCALPHA)
        surf.blit(base, (0, 0))
        # small extra blit to thicken strokes
        surf.blit(base, (bold_px, 0))
        return surf

    state = State()
    deck: List[Card] = []
    discard: List[Card] = []
    collected: List[Card] = []
    hand: List[Card] = []
    selected: List[int] = []
    played_this_round = False
    played_effects_this_round: List[Dict[str, int]] = []

    # Mechanics: hand max 5; draw up to 3 per round; trash to discard; active = build (max 5), stats from active
    hand_limit = 5
    draw_per_round = 3

    stat_bar = pygame.Rect(8, 6, LOW_W - 16, 16)
    active_row_y = 20
    active_label_y = active_row_y + 4
    active_slot_y = active_row_y + 20
    active_margin_right = 16
    msg_text_y = stat_bar.bottom + 6
    msg_max_w = LOW_W - 24
    # Hover panel should not overlap the 4-line objective block.
    hover_box = pygame.Rect(8, msg_text_y + 58, LOW_W // 2 - 16, 58)

    # Card size (small so they fit the window); art is smooth-scaled to this for readability.
    _pggame_dir = os.path.dirname(os.path.abspath(__file__))
    _src_dir = os.path.join(_pggame_dir, "..", "src")
    CARD_W, CARD_H = 80, 104
    # Phase 2: base size multiplier; actual target size is dynamic so cards fit.
    PHASE2_BASE_SCALE = 1.58
    PHASE2_BASE_W, PHASE2_BASE_H = int(CARD_W * PHASE2_BASE_SCALE), int(CARD_H * PHASE2_BASE_SCALE)
    _PHASE2_BASE_ASPECT = PHASE2_BASE_H / float(PHASE2_BASE_W) if PHASE2_BASE_W else 1.0

    # Phase 2 top UI layout (green container, golden divider, strike on right 10%).
    PHASE2_UI_X = 16
    PHASE2_UI_Y = 12
    PHASE2_UI_W = LOW_W - 32
    PHASE2_UI_H = 128
    PHASE2_UI_LEFT_W = int(PHASE2_UI_W * 0.9)
    PHASE2_UI_DIV_X = PHASE2_UI_X + PHASE2_UI_LEFT_W
    PHASE2_UI_CROSS_CENTER = (
        PHASE2_UI_DIV_X + (PHASE2_UI_W - PHASE2_UI_LEFT_W) // 2,
        PHASE2_UI_Y + 52,
    )
    PHASE2_UI_QUESTION_TEXT_X = PHASE2_UI_X + 12
    PHASE2_UI_QUESTION_TEXT_Y = PHASE2_UI_Y + 30
    PHASE2_PLAY_TARGET = (PHASE2_UI_X + PHASE2_UI_LEFT_W // 2, PHASE2_UI_Y + 80)
    card_art_surfs: Dict[str, pygame.Surface] = {}
    _cards_dir = os.path.join(_src_dir, "cards")
    if os.path.isdir(_cards_dir):
        for _fn in sorted(os.listdir(_cards_dir)):
            if not _fn.lower().endswith((".png", ".webp")):
                continue
            _path = os.path.join(_cards_dir, _fn)
            try:
                _surf = pygame.image.load(_path).convert_alpha()
                # Smooth scaling preserves readability when downscaling (vs. nearest-neighbor).
                card_art_surfs[_fn] = pygame.transform.smoothscale(_surf, (CARD_W, CARD_H))
            except Exception:
                pass

    # Credits: author logo (scaled to 1.5x hand card size).
    author1_logo_surf: Optional[pygame.Surface] = None
    _author1_path = os.path.join(_src_dir, "author1.png")
    if os.path.isfile(_author1_path):
        try:
            _author1_surf = pygame.image.load(_author1_path).convert_alpha()
            author1_logo_surf = pygame.transform.smoothscale(
                _author1_surf, (int(CARD_W * 1.5), int(CARD_H * 1.5))
            )
        except Exception:
            author1_logo_surf = None

    # cards.txt: number, color (r/w), key, rarity — border from card.suit
    cards_pool: List[Card] = load_cards_from_file(_cards_dir)

    def card_border_color(c: Card) -> Tuple[int, int, int]:
        """Border from card suit: r = red, w = white."""
        if getattr(c, "suit", None) == "r":
            return RED
        if getattr(c, "suit", None) == "w":
            return WHITE
        return GOLD

    # Hand cards: moved up into the middle. Deck/collected stay at bottom corners.
    card_base_y = LOW_H - CARD_H - 78
    deck_base_y = LOW_H - CARD_H - 8

    constraint_failed: bool = False

    # Final stage (hospital triage) state
    boss_step: int = 0  # 0 = intro, 1..len(questions) = question, len+1 = outcome
    boss_readiness_deltas: List[int] = []
    boss_option_rects: List[pygame.Rect] = []  # filled during draw for click detection

    # Deck click = draw cards AND advance round (only if hand ≤ 3).
    pending_draw: bool = False
    pending_draw_frames: int = 0
    end_round_after_draw: bool = False
    deck_warning_frames: int = 0  # When >0: red mask + warning
    deck_warning_hand_full: bool = True  # True = "max 3 cards" message, False = "no cards to draw"
    active_slot_conflict_flash: Optional[int] = None  # Slot index to flash red (real_time_api vs batch_processing)
    active_slot_conflict_frames: int = 0
    PENDING_DRAW_HINT_FRAMES = 150  # ~2.5s at 60fps

    # Deck-draw animation (cards are added to `hand` one-by-one to allow smooth motion).
    deck_draw_in_progress: bool = False
    deck_draw_buffer: List[Card] = []
    deck_draw_step_index: int = 0  # how many cards from buffer are already committed to hand
    deck_draw_start_hand_len: int = 0  # hand size when this draw started (for black box: which cards were just drawn)
    deck_draw_start_had_black_box: bool = False  # whether black box model was in ACTIVE when this draw started
    DECK_DRAW_STEP_FRAMES = 18  # frames per "add one card" animation step
    # Black box model: one hand card is shown as card back until next draw.
    hidden_hand_index: Optional[int] = None
    # Explainable documentation: hover over next-card preview shows this card in hover panel.
    hover_peek_card: Optional[Card] = None

    # Collect animation: played cards fly to the collection pile (like deck draw arch).
    collect_anim_list: List[Tuple[Card, pygame.Rect, float]] = []  # (card, start_rect, progress 0..1)
    collect_anim_frames_per_card = 20

    message = "Click deck to draw & advance. Max 3 in hand. Active cards = your stats."
    story_line = "Objective will be set when you start."
    objective_setting_line = ""
    objective_stats_line = ""
    mode: str = "menu"  # menu -> intro -> game -> over
    hover_idx: int | None = None
    hover_active_idx: Optional[int] = None
    frame: int = 0
    game_over_retry_rect: Optional[pygame.Rect] = None
    menu_play_rect: Optional[pygame.Rect] = None
    menu_credits_rect: Optional[pygame.Rect] = None
    menu_settings_rect: Optional[pygame.Rect] = None
    menu_admin_rect: Optional[pygame.Rect] = None
    credits_back_rect: Optional[pygame.Rect] = None
    contract_eval_passed: bool = False
    game_over_from_contract_eval: bool = False
    # Phase 2: post-contract card quiz (only if contract met at end of round 10).
    phase2_played: bool = False
    phase2_passed_challenge: bool = False
    phase2_cards: List[Card] = []
    phase2_start_centers: List[Tuple[int, int]] = []
    phase2_anim_progress: float = 0.0
    PHASE2_ANIM_FRAMES = 52
    phase2_subphase: str = ""  # anim | play | won | lost
    phase2_questions: List[Dict[str, Any]] = []
    phase2_q_index: int = 0
    phase2_strikes: int = 0
    phase2_correct: int = 0
    phase2_used: List[bool] = []
    phase2_target_w: int = PHASE2_BASE_W
    phase2_target_h: int = PHASE2_BASE_H
    # Cache for scaled art at different intermediate sizes during animation.
    # Key = (art_filename, w, h)
    phase2_scaled_art_cache: Dict[Tuple[str, int, int], pygame.Surface] = {}
    phase2_hover_i: Optional[int] = None
    phase2_end_panel_rect: Optional[pygame.Rect] = None
    # When the player answers a question correctly, the played card is animated
    # (thrown toward the question and faded away). Kept separate from `phase2_used`.
    phase2_play_anims: List[Tuple[int, pygame.Rect, float, Tuple[int, int]]] = []
    PHASE2_PLAY_ANIM_FRAMES = 26

    # Active row geometry (used by end_round snapshot and draw_active_row).
    ACTIVE_CARD_W, ACTIVE_CARD_H = int(40 * 1.07), int(52 * 1.07)
    active_gap = 6

    def active_slot_rects() -> List[pygame.Rect]:
        cap = get_active_slot_capacity(state)
        total_w = cap * ACTIVE_CARD_W + (cap - 1) * active_gap
        start_x = LOW_W - total_w - active_margin_right
        return [
            pygame.Rect(start_x + i * (ACTIVE_CARD_W + active_gap), active_slot_y, ACTIVE_CARD_W, ACTIVE_CARD_H)
            for i in range(cap)
        ]

    def draw_from_deck(n: int) -> None:
        nonlocal deck, hand
        for _ in range(n):
            if len(hand) >= hand_limit or not deck:
                break
            hand.append(deck.pop())

    def start_round() -> None:
        nonlocal selected, story_line, objective_setting_line, objective_stats_line, message, played_this_round, deck_anim_frames, deck, discard, pending_draw, pending_draw_frames
        nonlocal deck_draw_in_progress, deck_draw_buffer, deck_draw_step_index
        selected = []
        played_this_round = False
        played_effects_this_round.clear()
        story_line, objective_setting_line, objective_stats_line = get_scenario_objective_lines(state.scenario_key)
        if state.round_idx == 11:
            return
        deck = get_deck_for_round(rng, state.round_idx, cards_pool)
        discard = []
        deck_draw_in_progress = False
        deck_draw_buffer = []
        deck_draw_step_index = 0
        deck_anim_frames = 0
        pending_draw = True
        pending_draw_frames = 0
        message = "Drag cards to TRASH or ACTIVE."

    def hard_loss() -> bool:
        return (
            state.transparency < 0 or state.stability < 0 or state.automation < 0
            or state.generalizability < 0 or state.integrity < 0
        )

    def check_round_constraint() -> bool:
        """True if constraint failed (player loses)."""
        c = get_round_constraint(state.round_idx)
        if c is None:
            return False
        stat, min_val = c
        return state.get_stat(stat) < min_val

    def risk_check() -> Tuple[bool, Optional[str]]:
        """
        THE “critical decisions” mechanic:
        - Risk >= 6: guaranteed crash event (big penalty)
        - Risk >= 4: 50% chance of a smaller hit
        """
        return False, None

    def apply_risk_event(kind: str) -> None:
        """Removed: no risk mechanic."""
        return
        if kind == "100":
            if roll == 0:
                # Public backlash
                state.trust -= 4
            elif roll == 1:
                # Bias scandal
                state.fairness -= 4
            elif roll == 2:
                # “Why can’t you explain this?”
                state.transparency -= 3
                state.trust -= 2
            else:
                # Emergency rollback slows everything
                state.automation -= 3
                state.trust -= 2
        else:
            if roll == 0:
                state.trust -= 2
            elif roll == 1:
                state.fairness -= 2
            elif roll == 2:
                state.transparency -= 2
            else:
                state.automation -= 2
            pass

        # Round 5: “no rollback” means the same incident hurts trust more.
        if state.round_idx == 5:
            state.trust -= 1

    def end_round() -> None:
        nonlocal message, story_line, mode, contract_eval_passed, game_over_from_contract_eval
        nonlocal phase2_played, phase2_passed_challenge, phase2_cards, phase2_start_centers
        nonlocal phase2_anim_progress, phase2_subphase, phase2_questions, phase2_q_index
        nonlocal phase2_strikes, phase2_correct, phase2_used, phase2_scaled_art_cache
        if hard_loss():
            mode = "over"
            return
        # No round-constraint game over here: always advance to next round so user can draw again.
        # Contract/requirements are evaluated at final stage.

        apply_condition_passives_end_of_round(state)
        base = state.base_points()
        state.score += max(0, base)

        if state.round_idx < state.rounds_total:
            state.round_idx += 1
            if state.round_idx == 11:
                contract_ok = contract_fulfilled(state, state.scenario_key)
                contract_eval_passed = contract_ok
                if not contract_ok:
                    phase2_played = False
                    phase2_passed_challenge = False
                    game_over_from_contract_eval = True
                    mode = "over"
                    return
                # Contract satisfied → Phase 2 (readiness quiz with active cards).
                phase2_played = True
                phase2_passed_challenge = False
                phase2_cards = []
                phase2_start_centers = []
                cap = get_active_slot_capacity(state)
                slot_rects = active_slot_rects()
                for i in range(cap):
                    c = state.active_slots[i] if i < len(state.active_slots) else None
                    if c is not None:
                        phase2_cards.append(c)
                        phase2_start_centers.append((slot_rects[i].centerx, slot_rects[i].centery))
                if not phase2_cards:
                    phase2_passed_challenge = True
                    game_over_from_contract_eval = True
                    mode = "over"
                    return
                pk = {c.key for c in phase2_cards}
                desired_q = 6 if "carbon_footprint" in pk else 5
                desired_q = min(desired_q, len(phase2_cards))
                phase2_questions = pick_phase2_questions(rng, pk, desired_q)
                if not phase2_questions:
                    phase2_passed_challenge = True
                    game_over_from_contract_eval = True
                    mode = "over"
                    return
                phase2_anim_progress = 0.0
                phase2_subphase = "anim"
                phase2_q_index = 0
                phase2_strikes = 0
                phase2_correct = 0
                phase2_used = [False] * len(phase2_cards)
                phase2_scaled_art_cache.clear()
                phase2_play_anims.clear()
                game_over_from_contract_eval = False
                mode = "phase2"
                return
            start_round()
            mode = "game"
        else:
            story_line = "Run complete."
            message = "Your choices outlive your dashboard."
            mode = "over"

    def suit_color(suit: str) -> Tuple[int, int, int]:
        return RED if suit in ("heart", "diamond") else BLUE

    def card_effect_line(c: Card) -> str:
        active = get_active_stats(state.round_idx)
        parts: List[str] = []
        shorts = {"transparency": "T", "stability": "S", "automation": "A", "generalizability": "G", "integrity": "I"}
        for key in active:
            short = shorts.get(key, key[0])
            v = int(c.effects.get(key, 0))
            if v:
                sign = "+" if v > 0 else ""
                parts.append(f"{short}{sign}{v}")
        return " ".join(parts) if parts else "—"

    def draw_pixel_border(surf: pygame.Surface, r: pygame.Rect, c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> None:
        pygame.draw.rect(surf, c2, r)
        inner = r.inflate(-2, -2)
        pygame.draw.rect(surf, c1, inner)

    def draw_pixel_border_alpha(
        surf: pygame.Surface,
        r: pygame.Rect,
        fill: Tuple[int, int, int],
        edge: Tuple[int, int, int],
        fill_alpha: int,
    ) -> None:
        """Pixel border with slightly transparent fill (edge stays opaque)."""
        pygame.draw.rect(surf, edge, r)
        inner = r.inflate(-2, -2)
        s = pygame.Surface((inner.w, inner.h), pygame.SRCALPHA)
        s.fill((*fill, max(0, min(255, int(fill_alpha)))))
        surf.blit(s, (inner.x, inner.y))

    def draw_pixel_frame(surf: pygame.Surface, r: pygame.Rect, outer: Tuple[int, int, int], inner: Tuple[int, int, int]) -> None:
        """Border-only frame (doesn't cover the interior), suitable for card art."""
        pygame.draw.rect(surf, outer, r, 2)
        inner_r = r.inflate(-2, -2)
        pygame.draw.rect(surf, inner, inner_r, 1)

    def draw_button(btn: Button, hover: bool) -> None:
        base = GOLD if btn.enabled else PAPER_DARK
        edge = (80, 70, 40) if btn.enabled else (90, 90, 90)
        draw_pixel_border(screen, btn.rect, base, edge)
        label = rtxt(font_small, btn.label, INK)
        lx = btn.rect.centerx - label.get_width() // 2
        ly = btn.rect.centery - label.get_height() // 2
        if hover and btn.enabled:
            lx += 1
            ly += 1
        screen.blit(label, (lx, ly))

    def draw_stats() -> None:
        draw_pixel_border_alpha(screen, stat_bar, FELT_DARK, GOLD, fill_alpha=235)
        active = get_active_stats(state.round_idx)
        labels = {"transparency": "T", "stability": "S", "automation": "A", "generalizability": "G", "integrity": "I"}
        metrics = "  ".join(f"{labels.get(s, s)}:{state.get_stat(s)}" for s in active)
        mtxt = rtxt(font_small, metrics, PAPER)
        screen.blit(mtxt, (stat_bar.x + 6, stat_bar.y + 2))
        score_str = f"SCORE:{state.score}"
        stxt = rtxt(font_small, score_str, PAPER)
        screen.blit(stxt, (stat_bar.centerx - stxt.get_width() // 2, stat_bar.y + 2))
        if state.round_idx >= 11:
            rlabel = "Final Round"
        else:
            rlabel = f"Round {state.round_idx} of 10"
        rts = rtxt(font_small, rlabel, GOLD)
        screen.blit(rts, (stat_bar.right - rts.get_width() - 6, stat_bar.y + 2))

    def draw_active_row() -> None:
        """Draw ACTIVE zone: 5 or 6 card slots (build); stats come from these cards."""
        slot_rects = active_slot_rects()
        label = rtxt(font_tiny, "ACTIVE", GOLD, bold_px=1)
        total_w = slot_rects[-1].right - slot_rects[0].left if slot_rects else 0
        lx = slot_rects[0].left + total_w // 2 - label.get_width() // 2 if slot_rects else 0
        ly = active_label_y
        # subtle shadow for visibility (same style as COLLECTED)
        shadow = rtxt(font_tiny, "ACTIVE", INK, bold_px=1)
        shadow.set_alpha(160)
        screen.blit(shadow, (lx + 1, ly + 1))
        screen.blit(label, (lx, ly))
        for i, r in enumerate(slot_rects):
            card = state.active_slots[i] if i < len(state.active_slots) else None
            if card:
                # Card present: draw with same shake/wobble as old selected-hand-cards animation
                outer = card_border_color(card)
                card_surf = pygame.Surface((ACTIVE_CARD_W, ACTIVE_CARD_H), pygame.SRCALPHA)
                if card.art and card.art in card_art_surfs:
                    scaled = pygame.transform.smoothscale(card_art_surfs[card.art], (ACTIVE_CARD_W, ACTIVE_CARD_H))
                    card_surf.blit(scaled, (0, 0))
                    draw_pixel_frame(card_surf, pygame.Rect(0, 0, ACTIVE_CARD_W, ACTIVE_CARD_H), outer, PAPER_DARK)
                else:
                    draw_pixel_border(card_surf, pygame.Rect(0, 0, ACTIVE_CARD_W, ACTIVE_CARD_H), (250, 248, 240), outer)
                    pip = rtxt(font_tiny, card.suit[0].upper(), outer, bold_px=0)
                    card_surf.blit(pip, (2, 2))
                angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                screen.blit(rotated, rotated.get_rect(center=r.center))
                if active_slot_conflict_flash == i and active_slot_conflict_frames > 0:
                    pulse = 0.4 + 0.35 * math.sin(2.0 * math.pi * (active_slot_conflict_frames / 15))
                    flash_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                    flash_surf.fill((220, 72, 72, int(180 * pulse)))
                    screen.blit(flash_surf, r.topleft)
            else:
                # Empty slot: dark green border only
                draw_pixel_border(screen, r, FELT_DARK, GOLD)
                empty = rtxt(font_tiny, "—", (100, 98, 80), bold_px=0)
                screen.blit(empty, (r.centerx - empty.get_width() // 2, r.centery - empty.get_height() // 2))

    def wrap_text(text: str, max_width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current: List[str] = []
        for w in words:
            current.append(w)
            if font_small.size(" ".join(current))[0] > max_width:
                current.pop()
                if current:
                    lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        return lines

    def _phase2_ease(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _phase2_compute_target_layout(n: int) -> Tuple[int, int, int, List[Tuple[int, int]]]:
        """
        Returns: (target_w, target_h, gap, end_centers).
        Target size is dynamic to prevent overflow when the player has 5–6 cards.
        """
        if n <= 0:
            return 0, 0, 0, []

        # Wider spacing for 4–5 cards; tighter when we have 6.
        gap = 12 if n >= 5 else 14
        pad_x = 18
        max_total_w = max(1, LOW_W - pad_x * 2)
        w_max = max(1, (max_total_w - (n - 1) * gap) // n)

        w = min(PHASE2_BASE_W, w_max)
        # Keep it slightly bigger than Phase 1 hand cards where possible.
        min_w = int(CARD_W * 1.1)
        w = min(max(w, min_w), w_max)
        h = max(1, int(w * _PHASE2_BASE_ASPECT))

        # Middle-ish, but slightly lower to leave room for the question text.
        target_cy = LOW_H // 2 + 45

        total_w = n * w + (n - 1) * gap
        x0 = (LOW_W - total_w) // 2 + w // 2
        centers = [(x0 + i * (w + gap), target_cy) for i in range(n)]
        return w, h, gap, centers

    def _phase2_get_scaled_art(art_key: str, w: int, h: int) -> pygame.Surface:
        """Scale from the cached 80×104 art; quantize sizes to keep the cache small."""
        # Quantize to 2px steps.
        wq = int(max(1, round(w / 2) * 2))
        hq = int(max(1, round(h / 2) * 2))
        key = (art_key, wq, hq)
        surf = phase2_scaled_art_cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(card_art_surfs[art_key], (wq, hq))
            phase2_scaled_art_cache[key] = surf
        return surf

    def phase2_card_layout_rects() -> List[pygame.Rect]:
        n = len(phase2_cards)
        if n == 0:
            return []

        target_w, target_h, _, ends = _phase2_compute_target_layout(n)
        # During play, we want the stable end positions.
        t_anim = _phase2_ease(phase2_anim_progress) if phase2_subphase == "anim" else 1.0

        out: List[pygame.Rect] = []
        for i in range(n):
            sx, sy = phase2_start_centers[i]
            ex, ey = ends[i]
            cx = int(sx + (ex - sx) * t_anim)
            cy = int(sy + (ey - sy) * t_anim)
            w = int(ACTIVE_CARD_W + (target_w - ACTIVE_CARD_W) * t_anim)
            h = int(ACTIVE_CARD_H + (target_h - ACTIVE_CARD_H) * t_anim)
            out.append(pygame.Rect(cx - w // 2, cy - h // 2, w, h))
        return out

    def draw_phase2() -> None:
        nonlocal phase2_end_panel_rect
        draw_tiled_background()
        phase2_end_panel_rect = None

        # Top UI: green container for the question + right-side strike strip.
        ui_panel = pygame.Rect(PHASE2_UI_X, PHASE2_UI_Y, PHASE2_UI_W, PHASE2_UI_H)
        draw_pixel_border_alpha(screen, ui_panel, FELT_DARK, GOLD, fill_alpha=235)

        # Golden pixel divider between question area (left) and strike area (right).
        for yy in range(PHASE2_UI_Y + 10, PHASE2_UI_Y + PHASE2_UI_H - 10, 6):
            pygame.draw.rect(
                screen,
                GOLD,
                pygame.Rect(PHASE2_UI_DIV_X - 1, yy, 3, 3),
            )

        nq = len(phase2_questions)

        # Question text (top-left, ~90% width).
        if nq > 0 and phase2_subphase in ("play", "anim") and phase2_q_index < nq:
            q = phase2_questions[phase2_q_index]
            counter = rtxt(
                font_tiny,
                f"Question {phase2_q_index + 1} of {nq}",
                GOLD,
                bold_px=0,
            )
            screen.blit(counter, (PHASE2_UI_QUESTION_TEXT_X, PHASE2_UI_Y + 6))

            qy = PHASE2_UI_QUESTION_TEXT_Y
            qtext = str(q.get("question", ""))
            parts = qtext.split("\n")
            for pi, part in enumerate(parts):
                for line in wrap_text(part, PHASE2_UI_LEFT_W - 24):
                    qt = rtxt(font_small, line, PAPER, bold_px=0)
                    screen.blit(qt, (PHASE2_UI_QUESTION_TEXT_X, qy))
                    qy += font_small.get_linesize() + 3
                if pi < len(parts) - 1:
                    qy += 2

        # Strike indicator (first wrong answer): red cross on the right 10%.
        if phase2_strikes >= 1 and phase2_subphase in ("play", "anim"):
            cx, cy = PHASE2_UI_CROSS_CENTER
            L = 12
            pygame.draw.line(screen, RED, (cx - L, cy - L), (cx + L, cy + L), 3)
            pygame.draw.line(screen, RED, (cx - L, cy + L), (cx + L, cy - L), 3)
            lc = rtxt(font_tiny, "Last chance!", RED, bold_px=0)
            screen.blit(lc, (cx - lc.get_width() // 2, cy + L + 6))

        rects = phase2_card_layout_rects()
        for i, card in enumerate(phase2_cards):
            if i >= len(rects):
                break
            if i < len(phase2_used) and phase2_used[i]:
                # Correctly played cards are animated away.
                continue
            r = rects[i]
            outer = card_border_color(card)
            hovered = phase2_hover_i == i and phase2_subphase == "play"

            if hovered:
                # Reuse the original "active card wobble": rotate the whole card.
                angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                lift_y = -4
                wobble_scale = 1.03
                card_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                if card.art and card.art in card_art_surfs:
                    art_surf = _phase2_get_scaled_art(card.art, r.w, r.h)
                    card_surf.blit(art_surf, (0, 0))
                    draw_pixel_frame(card_surf, pygame.Rect(0, 0, r.w, r.h), outer, PAPER_DARK)
                else:
                    draw_pixel_border(card_surf, pygame.Rect(0, 0, r.w, r.h), PAPER, outer)
                    pip = rtxt(font_small, card.suit[0].upper(), outer, bold_px=0)
                    card_surf.blit(pip, (4, 3))
                rotated = pygame.transform.rotozoom(card_surf, angle, wobble_scale)
                screen.blit(rotated, rotated.get_rect(center=(r.centerx, r.centery + lift_y)))
            else:
                if card.art and card.art in card_art_surfs:
                    art_surf = _phase2_get_scaled_art(card.art, r.w, r.h)
                    screen.blit(art_surf, r)
                    draw_pixel_frame(screen, r, outer, PAPER_DARK)
                else:
                    draw_pixel_border(screen, r, PAPER, outer)
                    pip = rtxt(font_small, card.suit[0].upper(), outer, bold_px=0)
                    screen.blit(pip, (r.x + 6, r.y + 5))

        # Played-card "throw & fade" animations.
        for card_idx, start_r, prog, target_center in phase2_play_anims:
            if card_idx < 0 or card_idx >= len(phase2_cards):
                continue
            card = phase2_cards[card_idx]
            outer = card_border_color(card)

            t = max(0.0, min(1.0, prog))
            ease = _phase2_ease(t)
            arc_h = int(start_r.h * 0.45)
            xc = int(start_r.centerx + (target_center[0] - start_r.centerx) * ease)
            yc = int(start_r.centery + (target_center[1] - start_r.centery) * ease - arc_h * math.sin(math.pi * ease))
            rot = math.sin(math.pi * ease) * 10.0
            pop_scale = 1.0 + 0.08 * math.sin(math.pi * ease)
            alpha = int(255 * (1.0 - ease) ** 1.2)

            # Render the card into a surface once per frame (small N so it's fine).
            base = pygame.Surface((start_r.w, start_r.h), pygame.SRCALPHA)
            if card.art and card.art in card_art_surfs:
                art_surf = _phase2_get_scaled_art(card.art, start_r.w, start_r.h)
                base.blit(art_surf, (0, 0))
                draw_pixel_frame(base, pygame.Rect(0, 0, start_r.w, start_r.h), outer, PAPER_DARK)
            else:
                draw_pixel_border(base, pygame.Rect(0, 0, start_r.w, start_r.h), PAPER, outer)
                pip = rtxt(font_small, card.suit[0].upper(), outer, bold_px=0)
                base.blit(pip, (4, 3))

            animated = pygame.transform.rotozoom(base, rot, pop_scale)
            animated.set_alpha(max(0, min(255, alpha)))
            screen.blit(animated, animated.get_rect(center=(xc, yc)))

        if phase2_subphase in ("won", "lost"):
            panel = pygame.Rect(32, LOW_H // 2 - 52, LOW_W - 64, 104)
            phase2_end_panel_rect = panel
            draw_pixel_border_alpha(screen, panel, FELT_DARK, GOLD, fill_alpha=245)
            if phase2_subphase == "won":
                title = rtxt(font_big, "READINESS PASSED", GOLD)
                sub = rtxt(font_small, "Click to see deployment outcome.", PAPER, bold_px=0)
            else:
                title = rtxt(font_big, "READINESS FAILED", RED)
                sub = rtxt(
                    font_small,
                    "Too many wrong answers. Click to continue.",
                    PAPER,
                    bold_px=0,
                )
            screen.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 18))
            screen.blit(sub, (panel.centerx - sub.get_width() // 2, panel.y + 52))

    def draw_message() -> None:
        # Line 1: Objective: [name]
        # Line 2: short setting/context (very concise)
        # Line 3: requirements (red)
        # Line 4: drag instruction (gold)
        x, y = 12, msg_text_y
        line_step = font_tiny.get_linesize() + 2

        def draw_line(text: str, color: Tuple[int, int, int], y0: int) -> None:
            t = rtxt(font_tiny, text, color, bold_px=0)
            shadow_t = rtxt(font_tiny, text, INK, bold_px=0)
            shadow_t.set_alpha(160)
            screen.blit(shadow_t, (x + 1, y0 + 1))
            screen.blit(t, (x, y0))

        if story_line:
            draw_line(story_line, PAPER, y)
            y += line_step
        if objective_setting_line:
            draw_line(objective_setting_line, (200, 198, 188), y)
            y += line_step
        if objective_stats_line:
            draw_line(objective_stats_line, RED, y)
            y += line_step
        if message:
            # Message is expected to be short; wrap only if needed.
            for line in wrap_text(message, msg_max_w):
                draw_line(line, GOLD, y)
                y += line_step

    def draw_hover_panel() -> None:
        # Format: Line 1 = [card name] · [rarity] (white name, no black fill). Line 2 = +2S etc. if stats. Line 3 = passive text if passive.
        c: Optional[Card] = None
        # While dragging, ignore hover targets and force the hover panel to match what the user is holding.
        if dragging_hand_idx is not None and dragging_hand_idx < len(hand):
            if hidden_hand_index is not None and dragging_hand_idx == hidden_hand_index:
                # Black box: hidden hand card — show only "Hidden card"
                draw_pixel_border_alpha(screen, hover_box, FELT_DARK, GOLD, fill_alpha=235)
                hidden_txt = rtxt(font_tiny, "Hidden card", PAPER, bold_px=0)
                screen.blit(hidden_txt, (hover_box.x + 4, hover_box.y + 4))
                return
            c = hand[dragging_hand_idx]
        elif hover_peek_card is not None:
            c = hover_peek_card
        elif hover_idx is not None and hover_idx == hidden_hand_index:
            # Black box: hidden hand card — show only "Hidden card"
            draw_pixel_border_alpha(screen, hover_box, FELT_DARK, GOLD, fill_alpha=235)
            hidden_txt = rtxt(font_tiny, "Hidden card", PAPER, bold_px=0)
            screen.blit(hidden_txt, (hover_box.x + 4, hover_box.y + 4))
            return
        if c is None and hover_active_idx is not None and 0 <= hover_active_idx < len(state.active_slots):
            card_in_slot = state.active_slots[hover_active_idx]
            if card_in_slot:
                c = card_in_slot
        if c is None and hover_idx is not None and 0 <= hover_idx < len(hand):
            c = hand[hover_idx]
        if c is None:
            return
        draw_pixel_border_alpha(screen, hover_box, FELT_DARK, GOLD, fill_alpha=235)
        x, y = hover_box.x + 4, hover_box.y + 2
        line_step = font_tiny.get_linesize() + 2
        max_w = hover_box.w - 8

        pos_c = (80, 210, 130)
        neg_c = (220, 72, 72)
        neutral_c = (200, 198, 188)
        rarity = str(getattr(c, "rarity", "common")).lower()
        rarity_str = rarity.upper()
        rarity_color = {"common": pos_c, "rare": BLUE, "epic": (160, 90, 220), "cursed": RED}.get(rarity, neutral_c)

        # Line 1: card name (white) · rarity (colored), no black fill
        name_surf = rtxt(font_tiny, c.name, PAPER, bold_px=0)
        name_surf.set_colorkey((0, 0, 0))
        screen.blit(name_surf, (x, y))
        cx = x + name_surf.get_width()
        sep = rtxt(font_tiny, " · ", neutral_c, bold_px=0)
        sep.set_colorkey((0, 0, 0))
        screen.blit(sep, (cx, y))
        cx += sep.get_width()
        rar = rtxt(font_tiny, rarity_str, rarity_color, bold_px=0)
        rar.set_colorkey((0, 0, 0))
        screen.blit(rar, (cx, y))
        y += line_step

        # Line 2: full stat names in hover only (e.g. -1 Stability, +2 Automation)
        if getattr(c, "key", None) == "carbon_footprint":
            # Custom formatting requested for this specific card.
            integ_v = int((c.effects or {}).get("integrity", 0))
            token1 = f"{integ_v:+d} Integrity" if integ_v != 0 else "Integrity"
            t1 = rtxt(font_tiny, token1, neg_c if integ_v < 0 else pos_c, bold_px=0)
            t1.set_colorkey((0, 0, 0))
            screen.blit(t1, (x, y))
            cx = x + t1.get_width()
            space = rtxt(font_tiny, " ", neutral_c, bold_px=0)
            space.set_colorkey((0, 0, 0))
            screen.blit(space, (cx, y))
            cx += space.get_width()
            t2 = rtxt(font_tiny, "+1 Active Slot", pos_c, bold_px=0)
            t2.set_colorkey((0, 0, 0))
            screen.blit(t2, (cx, y))
            y += line_step
        else:
            active = get_active_stats(state.round_idx)
            full_names = {
                "transparency": "Transparency",
                "stability": "Stability",
                "automation": "Automation",
                "generalizability": "Generalizability",
                "integrity": "Integrity",
            }
            tokens: List[Tuple[str, Tuple[int, int, int]]] = []
            for key in active:
                v = int(c.effects.get(key, 0))
                if v:
                    name = full_names.get(key, key.replace("_", " ").title())
                    tokens.append((f"{v:+d} {name}", pos_c if v > 0 else neg_c))
            if tokens:
                cx = x
                for i, (tok, col) in enumerate(tokens):
                    if i > 0:
                        comma = rtxt(font_tiny, ", ", neutral_c, bold_px=0)
                        comma.set_colorkey((0, 0, 0))
                        screen.blit(comma, (cx, y))
                        cx += comma.get_width()
                    surf = rtxt(font_tiny, tok, col, bold_px=0)
                    surf.set_colorkey((0, 0, 0))
                    screen.blit(surf, (cx, y))
                    cx += surf.get_width()
                y += line_step

        # Line 3: card text (setting/gameplay hint). Show for every card, not only passives.
        if getattr(c, "key", None) == "carbon_footprint":
            c_text = "Resource overuse. You will be judged."
        else:
            c_text = (getattr(c, "text", "") or "").strip()
        if c_text:
            for line in wrap_text(c_text, max_w):
                bl = rtxt(font_tiny, line, neutral_c, bold_px=0)
                bl.set_colorkey((0, 0, 0))
                screen.blit(bl, (x, y))
                y += line_step

    def card_rects() -> List[pygame.Rect]:
        base_y = card_base_y
        w, h = CARD_W, CARD_H
        gap = 8
        total_w = min(len(hand), hand_limit) * w + max(0, min(len(hand), hand_limit) - 1) * gap
        start_x = (LOW_W - total_w) // 2
        rects: List[pygame.Rect] = []
        for i in range(len(hand)):
            x = start_x + i * (w + gap)
            y = base_y
            # Hover lift
            if hover_idx == i and i not in selected:
                y -= 4
            # Selected lift (rotation handled during draw)
            if i in selected:
                y -= 10
            rects.append(pygame.Rect(x, y, w, h))
        return rects

    def draw_cards() -> None:
        # Deck-draw animation: smoothly re-center the hand layout as cards are added one-by-one.
        if deck_draw_in_progress and deck_draw_step_index < len(deck_draw_buffer):
            w, h = CARD_W, CARD_H
            gap = 8
            old_count = len(hand)
            # We animate "adding one card", so target count is old_count + 1 (capped by hand_limit).
            new_count = min(old_count + 1, hand_limit)
            if new_count == old_count:
                rects = card_rects()
                for i, (c, r) in enumerate(zip(hand, rects)):
                    outer = card_border_color(c)
                    if i == hidden_hand_index and deck_back_card_surf is not None:
                        screen.blit(deck_back_card_surf, r)
                    elif i in selected:
                        card_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                        if c.art and c.art in card_art_surfs:
                            card_surf.blit(card_art_surfs[c.art], (0, 0))
                            draw_pixel_frame(card_surf, pygame.Rect(0, 0, r.w, r.h), outer, PAPER_DARK)
                        else:
                            draw_pixel_border(card_surf, pygame.Rect(0, 0, r.w, r.h), (250, 248, 240), outer)
                            pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                            card_surf.blit(pip, (4, 3))
                        angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                        rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                        screen.blit(rotated, rotated.get_rect(center=r.center))
                    else:
                        if c.art and c.art in card_art_surfs:
                            screen.blit(card_art_surfs[c.art], r)
                            draw_pixel_frame(screen, r, outer, PAPER_DARK)
                        else:
                            draw_pixel_border(screen, r, PAPER, outer)
                            pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                            screen.blit(pip, (r.x + 4, r.y + 3))
                return

            # Normalized progress for this step.
            norm = 1.0 - (deck_anim_frames / float(DECK_DRAW_STEP_FRAMES))
            norm = max(0.0, min(1.0, norm))
            # Ease-in-out for smooth motion.
            ease = norm * norm * (3.0 - 2.0 * norm)

            def layout_start_x(count: int) -> int:
                total_w = min(count, hand_limit) * w + max(0, min(count, hand_limit) - 1) * gap
                return (LOW_W - total_w) // 2

            old_start_x = layout_start_x(old_count)
            new_start_x = layout_start_x(new_count)

            # First draw the existing hand cards, shifting them to their new centered positions.
            for i, c in enumerate(hand):
                old_x = old_start_x + i * (w + gap)
                new_x = new_start_x + i * (w + gap)
                x = int(old_x + (new_x - old_x) * ease)
                y = card_base_y - (5 if i in selected else 0)
                r = pygame.Rect(x, y, w, h)
                outer = card_border_color(c)
                if i == hidden_hand_index and deck_back_card_surf is not None:
                    screen.blit(deck_back_card_surf, r)
                elif i in selected:
                    card_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                    if c.art and c.art in card_art_surfs:
                        card_surf.blit(card_art_surfs[c.art], (0, 0))
                        draw_pixel_frame(card_surf, pygame.Rect(0, 0, w, h), outer, PAPER_DARK)
                    else:
                        draw_pixel_border(card_surf, pygame.Rect(0, 0, w, h), (250, 248, 240), outer)
                        pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                        card_surf.blit(pip, (4, 3))
                    angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                    rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                    screen.blit(rotated, rotated.get_rect(center=r.center))
                else:
                    if c.art and c.art in card_art_surfs:
                        screen.blit(card_art_surfs[c.art], r)
                        draw_pixel_frame(screen, r, outer, PAPER_DARK)
                    else:
                        draw_pixel_border(screen, r, PAPER, outer)
                        pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                        screen.blit(pip, (r.x + 4, r.y + 3))

            # Then draw the new card on an arch path from the deck to its final slot.
            target_x = new_start_x + old_count * (w + gap)
            target_rect = pygame.Rect(target_x, card_base_y, w, h)

            arch_height = int(CARD_H * 0.55)
            sx, sy = deck_rect.centerx, deck_rect.centery
            tx, ty = target_rect.centerx, target_rect.centery

            x_center = int(sx + (tx - sx) * ease)
            y_center = int(sy + (ty - sy) * ease - arch_height * math.sin(math.pi * norm))

            anim_rect = pygame.Rect(0, 0, w, h)
            anim_rect.center = (x_center, y_center)
            if deck_back_card_surf is not None:
                screen.blit(deck_back_card_surf, anim_rect)
            else:
                draw_pixel_border(screen, anim_rect, PAPER, GOLD)
            return

        # Normal (no animation): draw real hand; selected cards get a slight shake/wobble.
        rects = card_rects()
        for i, (c, r) in enumerate(zip(hand, rects)):
            outer = card_border_color(c)
            inner = PAPER_DARK
            if i == hidden_hand_index and deck_back_card_surf is not None:
                screen.blit(deck_back_card_surf, r)
            elif i in selected:
                card_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                if c.art and c.art in card_art_surfs:
                    card_surf.blit(card_art_surfs[c.art], (0, 0))
                    draw_pixel_frame(card_surf, pygame.Rect(0, 0, r.w, r.h), outer, inner)
                else:
                    draw_pixel_border(card_surf, pygame.Rect(0, 0, r.w, r.h), (250, 248, 240), outer)
                    pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                    card_surf.blit(pip, (4, 3))
                angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                screen.blit(rotated, rotated.get_rect(center=r.center))
            else:
                if c.art and c.art in card_art_surfs:
                    screen.blit(card_art_surfs[c.art], r)
                    draw_pixel_frame(screen, r, outer, inner)
                else:
                    draw_pixel_border(screen, r, PAPER, outer)
                    pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                    screen.blit(pip, (r.x + 4, r.y + 3))

        # Collect animation: cards flying to collection pile (arch like deck draw).
        for card, start_r, progress in collect_anim_list:
            norm = min(1.0, progress)
            ease = norm * norm * (3.0 - 2.0 * norm)
            arch_h = int(CARD_H * 0.55)
            sx, sy = start_r.centerx, start_r.centery
            tx, ty = trash_rect.centerx, trash_rect.centery
            xc = int(sx + (tx - sx) * ease)
            yc = int(sy + (ty - sy) * ease - arch_h * math.sin(math.pi * norm))
            anim_r = pygame.Rect(0, 0, CARD_W, CARD_H)
            anim_r.center = (xc, yc)
            outer = card_border_color(card)
            if card.art and card.art in card_art_surfs:
                screen.blit(card_art_surfs[card.art], anim_r)
                draw_pixel_frame(screen, anim_r, outer, PAPER_DARK)
            else:
                draw_pixel_border(screen, anim_r, PAPER, outer)
                pip = rtxt(font_small, card.suit[0].upper(), outer, bold_px=0)
                screen.blit(pip, (anim_r.x + 4, anim_r.y + 3))

        # Active-to-hand animation: card flies from active slot to hand (click without drag).
        for card, start_r, progress, _slot_idx in active_to_hand_anim_list:
            norm = min(1.0, progress)
            ease = norm * norm * (3.0 - 2.0 * norm)
            arch_h = int(CARD_H * 0.55)
            sx, sy = start_r.centerx, start_r.centery
            tx, ty = hand_drop_rect.centerx, hand_drop_rect.centery
            xc = int(sx + (tx - sx) * ease)
            yc = int(sy + (ty - sy) * ease - arch_h * math.sin(math.pi * norm))
            anim_r = pygame.Rect(0, 0, CARD_W, CARD_H)
            anim_r.center = (xc, yc)
            outer = card_border_color(card)
            if card.art and card.art in card_art_surfs:
                screen.blit(card_art_surfs[card.art], anim_r)
                draw_pixel_frame(screen, anim_r, outer, PAPER_DARK)
            else:
                draw_pixel_border(screen, anim_r, PAPER, outer)
                pip = rtxt(font_small, card.suit[0].upper(), outer, bold_px=0)
                screen.blit(pip, (anim_r.x + 4, anim_r.y + 3))

    TRASH_SCALE = 1.25
    TRASH_CARD_W, TRASH_CARD_H = int(CARD_W * TRASH_SCALE), int(CARD_H * TRASH_SCALE)
    deck_rect = pygame.Rect(10, deck_base_y, CARD_W, CARD_H)
    # Trash is larger than hand/deck cards; raise it so it doesn't overflow the bottom.
    trash_y = deck_base_y - (TRASH_CARD_H - CARD_H) // 2
    trash_rect = pygame.Rect(LOW_W - 10 - TRASH_CARD_W, trash_y, TRASH_CARD_W, TRASH_CARD_H)
    # Hand drop zone: center row where hand cards sit (max 3); drop active card here to return to hand.
    _hand_gap = 8
    _hand_total_w = hand_limit * CARD_W + (hand_limit - 1) * _hand_gap
    hand_drop_rect = pygame.Rect((LOW_W - _hand_total_w) // 2, card_base_y, _hand_total_w, CARD_H)
    deck_anim_frames = 0
    trash_flash_frames = 0

    # Drag state: hand index or active index being dragged; card follows mouse until drop (trash or active slot).
    dragging_hand_idx: Optional[int] = None
    dragging_active_idx: Optional[int] = None
    drag_start_pos: Tuple[int, int] = (0, 0)

    # Click on active card (no drag): fly card back to hand.
    active_to_hand_anim_list: List[Tuple[Card, pygame.Rect, float, int]] = []  # (card, start_rect, progress, slot_idx)
    active_to_hand_frames = 20

    # Deck back image (card back graphic)
    _deck_back_paths = [
        os.path.join(_src_dir, "back_of_card.webp"),
        os.path.join(_src_dir, "back_of_card.png"),
    ]
    deck_back_surf: Optional[pygame.Surface] = None
    for _path in _deck_back_paths:
        if os.path.isfile(_path):
            try:
                deck_back_surf = pygame.image.load(_path).convert_alpha()
                break
            except Exception:
                pass

    _trash_paths = [
        os.path.join(_src_dir, "trash.png"),
        os.path.join(_src_dir, "trash.webp"),
    ]
    trash_surf: Optional[pygame.Surface] = None
    trash_card_surf: Optional[pygame.Surface] = None
    for _path in _trash_paths:
        if os.path.isfile(_path):
            try:
                trash_surf = pygame.image.load(_path).convert_alpha()
                trash_card_surf = pygame.transform.smoothscale(trash_surf, (TRASH_CARD_W, TRASH_CARD_H))
                break
            except Exception:
                pass

    # Cached at the card size so deck animation can reuse it without rescaling every frame.
    deck_back_card_surf: Optional[pygame.Surface] = None
    if deck_back_surf is not None:
        deck_back_card_surf = pygame.transform.smoothscale(deck_back_surf, (CARD_W, CARD_H))

    _bg_paths = [
        os.path.join(_src_dir, "background.png"),
        os.path.join(_src_dir, "background.webp"),
    ]
    bg_surf: Optional[pygame.Surface] = None
    bg_tile_surf: Optional[pygame.Surface] = None
    BG_TILE_SCALE = 0.25
    for _path in _bg_paths:
        if os.path.isfile(_path):
            try:
                bg_surf = pygame.image.load(_path).convert()
                iw, ih = bg_surf.get_width(), bg_surf.get_height()
                tw = max(1, int(iw * BG_TILE_SCALE))
                th = max(1, int(ih * BG_TILE_SCALE))
                bg_tile_surf = pygame.transform.smoothscale(bg_surf, (tw, th))
                break
            except Exception:
                pass

    def draw_tiled_background() -> None:
        if bg_tile_surf is None:
            screen.fill(FELT)
            # simple felt noise fallback
            for y in range(0, LOW_H, 6):
                pygame.draw.line(screen, FELT_DARK, (0, y), (LOW_W, y), 1)
            return
        iw, ih = bg_tile_surf.get_width(), bg_tile_surf.get_height()
        if iw <= 0 or ih <= 0:
            screen.fill(FELT)
            return
        for yy in range(0, LOW_H, ih):
            for xx in range(0, LOW_W, iw):
                screen.blit(bg_tile_surf, (xx, yy))

    def draw_bg() -> None:
        draw_tiled_background()

        # Deck, trash, and draw animation only during normal play (not game over).
        if mode == "game":
            # Deck label above the deck
            deck_label = rtxt(font_tiny, "DECK", GOLD, bold_px=1)
            dlx = deck_rect.centerx - deck_label.get_width() // 2
            dly = deck_rect.y - deck_label.get_height() - 4
            screen.blit(deck_label, (dlx, dly))

            # Deck pile: stacked card backs (3 layers) for a deck look
            for offset in (4, 2, 0):
                r = pygame.Rect(deck_rect.x + offset, deck_rect.y + offset, CARD_W, CARD_H)
                if deck_back_card_surf is not None:
                    screen.blit(deck_back_card_surf, r)
                else:
                    draw_pixel_border(screen, r, PAPER_DARK, GOLD)

            # Explainable documentation: preview next card above deck (half transparent, phasing 50–70 alpha)
            has_explainable = any(c and c.key == "explainable_documentation" for c in state.active_slots)
            if has_explainable and deck and not deck_draw_in_progress:
                peek_card = deck[-1]
                peek_rect = pygame.Rect(deck_rect.centerx - ACTIVE_CARD_W // 2, deck_rect.y - ACTIVE_CARD_H - 8, ACTIVE_CARD_W, ACTIVE_CARD_H)
                phase = 0.5 + 0.5 * math.sin(frame * 0.08)
                alpha = int(50 + 20 * phase)
                peek_surf = pygame.Surface((ACTIVE_CARD_W, ACTIVE_CARD_H), pygame.SRCALPHA)
                if peek_card.art and peek_card.art in card_art_surfs:
                    scaled = pygame.transform.smoothscale(card_art_surfs[peek_card.art], (ACTIVE_CARD_W, ACTIVE_CARD_H))
                    scaled.set_alpha(alpha)
                    peek_surf.blit(scaled, (0, 0))
                else:
                    peek_surf.fill((240, 236, 228, alpha))
                    draw_pixel_border(peek_surf, pygame.Rect(0, 0, ACTIVE_CARD_W, ACTIVE_CARD_H), PAPER_DARK, GOLD)
                screen.blit(peek_surf, peek_rect)

            # Red warning: flash red mask + single-line compact text above deck
            if deck_warning_frames > 0:
                mask_inset = 4
                pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * (deck_warning_frames / 25))
                red_alpha = int(100 * pulse + 100)
                deck_mask = pygame.Surface((CARD_W - mask_inset * 2, CARD_H - mask_inset * 2), pygame.SRCALPHA)
                deck_mask.fill((220, 72, 72, red_alpha))
                screen.blit(deck_mask, (deck_rect.x + mask_inset, deck_rect.y + mask_inset))
                warn_text = "Max 3 cards at hand" if deck_warning_hand_full else "No cards to draw."
                warn = rtxt(font_tiny, warn_text, RED, bold_px=1)
                warn.set_colorkey((0, 0, 0))
                wx = deck_rect.centerx - warn.get_width() // 2
                wy = max(0, dly - warn.get_height() - 2)
                screen.blit(warn, (wx, wy))
            # When "click to draw" hint is visible: flashing dark mask over deck (inset a few px on each side)
            elif pending_draw and pending_draw_frames >= PENDING_DRAW_HINT_FRAMES:
                t = pending_draw_frames - PENDING_DRAW_HINT_FRAMES
                hint_period = 60
                pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * (t / hint_period))
                mask_alpha = int(80 * pulse)
                mask_inset = 4
                deck_mask = pygame.Surface((CARD_W - mask_inset * 2, CARD_H - mask_inset * 2), pygame.SRCALPHA)
                deck_mask.fill((0, 0, 0, mask_alpha))
                screen.blit(deck_mask, (deck_rect.x + mask_inset, deck_rect.y + mask_inset))

            # Draw hint: text + left-pointing arrow (only when not showing red warning)
            if deck_warning_frames == 0 and pending_draw and pending_draw_frames >= PENDING_DRAW_HINT_FRAMES:
                t = pending_draw_frames - PENDING_DRAW_HINT_FRAMES
                hint_period = 60
                pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * (t / hint_period))
                # Text alpha: more "black" (lower min) than before, still not as strong as mask
                text_alpha = int(140 + 115 * pulse)
                hint_text = "Draw"
                hint = rtxt(font_tiny, hint_text, GOLD, bold_px=1)
                hint.set_alpha(text_alpha)
                hx = deck_rect.right + 6
                hy = deck_rect.centery - hint.get_height() // 2
                screen.blit(hint, (hx, hy))
                # Left-pointing arrow (tip on left)
                arrow_w, arrow_h = 16, 12
                ax = hx - arrow_w - 4
                ay = hy + hint.get_height() // 2 - arrow_h // 2
                arrow_surf = pygame.Surface((arrow_w + 2, arrow_h + 2), pygame.SRCALPHA)
                pts = [(1, arrow_h // 2 + 1), (arrow_w + 1, 1), (arrow_w + 1, arrow_h + 1)]
                pygame.draw.polygon(arrow_surf, (*GOLD, text_alpha), pts)
                screen.blit(arrow_surf, (ax - 1, ay - 1))

            # Trash: bottom right (icon only, no label)
            if trash_card_surf is not None:
                screen.blit(trash_card_surf, trash_rect)
            else:
                draw_pixel_border(screen, trash_rect, FELT_DARK, (140, 80, 60))

    def draw_intro() -> None:
        draw_tiled_background()
        draw_pixel_border(screen, pygame.Rect(8, 8, LOW_W - 16, LOW_H - 16), FELT_DARK, GOLD)
        scenario_name = get_contract_name(state.scenario_key)
        objective_text = get_scenario_objective_text(state.scenario_key)
        title = rtxt(font_big, "DEPLOYMENT SCENARIO", GOLD)
        screen.blit(title, ((LOW_W - title.get_width()) // 2, 24))
        sub = rtxt(font_small, scenario_name, PAPER)
        screen.blit(sub, ((LOW_W - sub.get_width()) // 2, 52))
        y = 76
        line_step = font_small.get_linesize() + 4
        for line in wrap_text(objective_text, LOW_W - 28):
            rr = rtxt(font_small, line, (210, 208, 198), bold_px=0)
            screen.blit(rr, (20, y))
            y += line_step
        y += 12
        for line in wrap_text("You have 10 rounds. Build your stats with Active cards. Click deck to draw & advance. Max 3 in hand. Meet the objective by round 10 to win.", LOW_W - 28):
            rr = rtxt(font_tiny, line, (200, 198, 188), bold_px=0)
            screen.blit(rr, (20, y))
            y += line_step
        tip = rtxt(font_small, "Click anywhere to begin. ESC quits.", GOLD)
        screen.blit(tip, (14, LOW_H - 20))

    def draw_menu() -> None:
        nonlocal menu_play_rect, menu_credits_rect, menu_settings_rect, menu_admin_rect
        draw_tiled_background()
        draw_pixel_border(screen, pygame.Rect(8, 8, LOW_W - 16, LOW_H - 16), FELT_DARK, GOLD)
        # Title (placeholder; user will upload image later)
        title = rtxt(font_big, "ETHICAL STACK", GOLD)
        tx = (LOW_W - title.get_width()) // 2
        screen.blit(title, (tx, 52))
        # Buttons: Play, Credits, Settings
        btn_h = 36
        btn_w = 200
        cx = LOW_W // 2
        play_y = 130
        menu_play_rect = pygame.Rect(cx - btn_w // 2, play_y, btn_w, btn_h)
        draw_pixel_border(screen, menu_play_rect, GOLD, (80, 70, 40))
        ptxt = rtxt(font_small, "Play", INK)
        screen.blit(ptxt, (menu_play_rect.centerx - ptxt.get_width() // 2, menu_play_rect.centery - ptxt.get_height() // 2))
        cred_y = play_y + btn_h + 12
        menu_credits_rect = pygame.Rect(cx - btn_w // 2, cred_y, btn_w, btn_h)
        draw_pixel_border(screen, menu_credits_rect, FELT_DARK, GOLD)
        ctxt = rtxt(font_small, "Credits", PAPER)
        screen.blit(ctxt, (menu_credits_rect.centerx - ctxt.get_width() // 2, menu_credits_rect.centery - ctxt.get_height() // 2))
        set_y = cred_y + btn_h + 12
        menu_settings_rect = pygame.Rect(cx - btn_w // 2, set_y, btn_w, btn_h)
        draw_pixel_border(screen, menu_settings_rect, FELT_DARK, GOLD)
        stxt = rtxt(font_small, "Settings", PAPER)
        screen.blit(stxt, (menu_settings_rect.centerx - stxt.get_width() // 2, menu_settings_rect.centery - stxt.get_height() // 2))
        # Admin Phase 2 test button
        admin_y = set_y + btn_h + 12
        menu_admin_rect = pygame.Rect(cx - btn_w // 2, admin_y, btn_w, btn_h)
        draw_pixel_border(screen, menu_admin_rect, GOLD, (80, 70, 40))
        atxt = rtxt(font_small, "Admin Phase2", INK)
        screen.blit(atxt, (menu_admin_rect.centerx - atxt.get_width() // 2, menu_admin_rect.centery - atxt.get_height() // 2))
        esc = rtxt(font_small, "ESC to quit", (160, 158, 148), bold_px=0)
        screen.blit(esc, (LOW_W - esc.get_width() - 12, LOW_H - 20))

    def draw_credits() -> None:
        """Credits: background and text/logos only, no borders or boxes."""
        nonlocal credits_back_rect
        draw_tiled_background()
        half_w = (LOW_W - 16) // 2
        half_h = (LOW_H - 16) // 2
        # Top-left & bottom-right: logo placeholders (centers of quadrants)
        tl_cx, tl_cy = 8 + half_w // 2, 8 + half_h // 2
        br_cx, br_cy = 8 + half_w + half_w // 2, 8 + half_h + half_h // 2
        logo_placeholder = rtxt(font_small, "[Logo]", (120, 118, 100), bold_px=0)
        if author1_logo_surf is not None:
            # "First creator" logo goes in the LEFT placeholder quadrant.
            # Add a subtle floating/hover animation.
            bob = int(3 * math.sin(frame * 0.05))
            screen.blit(
                author1_logo_surf,
                (tl_cx - author1_logo_surf.get_width() // 2, tl_cy - author1_logo_surf.get_height() // 2 + bob),
            )
        else:
            screen.blit(logo_placeholder, (tl_cx - logo_placeholder.get_width() // 2, tl_cy - logo_placeholder.get_height() // 2))
        screen.blit(logo_placeholder, (br_cx - logo_placeholder.get_width() // 2, br_cy - logo_placeholder.get_height() // 2))
        # Top-right: author 1 (yellow name, white contributions)
        tr_x, tr_y = 8 + half_w + 12, 8 + 14
        author1_name = rtxt(font_small, "Author One", GOLD)
        screen.blit(author1_name, (tr_x, tr_y))
        contrib1 = rtxt(font_tiny, "Placeholder contributions for author one.", PAPER, bold_px=0)
        screen.blit(contrib1, (tr_x, tr_y + 20))
        # Bottom-left: author 2
        bl_x, bl_y = 8 + 12, 8 + half_h + 14
        author2_name = rtxt(font_small, "Author Two", GOLD)
        screen.blit(author2_name, (bl_x, bl_y))
        contrib2 = rtxt(font_tiny, "Placeholder contributions for author two.", PAPER, bold_px=0)
        screen.blit(contrib2, (bl_x, bl_y + 20))
        # Back (text only, no box; rect for click)
        credits_back_rect = pygame.Rect(LOW_W // 2 - 60, LOW_H - 44, 120, 28)
        back_txt = rtxt(font_small, "Back", GOLD)
        screen.blit(back_txt, (credits_back_rect.centerx - back_txt.get_width() // 2, credits_back_rect.centery - back_txt.get_height() // 2))

    def draw_game_over() -> None:
        nonlocal game_over_retry_rect
        draw_tiled_background()
        draw_pixel_border_alpha(screen, pygame.Rect(40, 60, LOW_W - 80, 180), FELT_DARK, GOLD, fill_alpha=235)
        if game_over_from_contract_eval:
            failed = not contract_eval_passed
            msg = "DEPLOYMENT APPROVED" if contract_eval_passed else "DEPLOYMENT DENIED"
            if phase2_played and contract_eval_passed and phase2_passed_challenge:
                sub = "You met the contract and passed the final AI readiness review."
            elif phase2_played and not contract_eval_passed:
                sub = "You satisfied the deployment contract but failed the readiness challenge."
            elif contract_eval_passed:
                sub = "You met the contract requirements."
            else:
                sub = "You did not meet the deployment contract requirements."
            title_color = GOLD if contract_eval_passed else RED
        else:
            failed = constraint_failed or hard_loss()
            if constraint_failed:
                msg = "RUN FAILED"
                sub = message
            elif hard_loss():
                msg = "RUN FAILED"
                sub = "A stat dropped below zero."
            else:
                msg = "RUN COMPLETE"
                sub = "Your choices outlive your dashboard."
            title_color = RED if failed else GOLD
        big = rtxt(font_big, msg, title_color)
        screen.blit(big, ((LOW_W - big.get_width()) // 2, 80))
        yy = 118
        line_step = font_small.get_linesize() + 5
        for line in wrap_text(sub, LOW_W - 100):
            small = rtxt(font_small, line, PAPER, bold_px=0)
            screen.blit(small, ((LOW_W - small.get_width()) // 2, yy))
            yy += line_step
        yy += 16
        retry_w, retry_h = 140, 36
        game_over_retry_rect = pygame.Rect((LOW_W - retry_w) // 2, yy, retry_w, retry_h)
        draw_pixel_border(screen, game_over_retry_rect, GOLD, (80, 70, 40))
        rtxt_surf = rtxt(font_small, "Retry", INK)
        screen.blit(rtxt_surf, (game_over_retry_rect.centerx - rtxt_surf.get_width() // 2, game_over_retry_rect.centery - rtxt_surf.get_height() // 2))
        esc = rtxt(font_small, "ESC to quit", GOLD, bold_px=0)
        screen.blit(esc, ((LOW_W - esc.get_width()) // 2, LOW_H - 24))

    def draw_boss() -> None:
        nonlocal boss_option_rects
        draw_tiled_background()
        boss_option_rects = []
        max_w = LOW_W - 40
        y = 24

        if boss_step == 0:
            for line in get_final_stage_intro():
                if line == "":
                    y += 8
                    continue
                for sub in wrap_text(line, max_w):
                    t = font_small.render(sub, True, PAPER if not sub.startswith("FINAL") else GOLD)
                    screen.blit(t, (20, y))
                    y += 14
                y += 2
            stats_line = f"Transparency {state.transparency}  Stability {state.stability}  Automation {state.automation}  Generalizability {state.generalizability}  Integrity {state.integrity}"
            st = font_small.render(stats_line, True, GOLD)
            screen.blit(st, (20, y))
            y += 24
            tip = font_small.render("Click to continue.", True, GOLD)
            screen.blit(tip, (20, y))
            return

        questions = get_final_stage_questions()
        if boss_step >= 1 and boss_step <= len(questions):
            q = questions[boss_step - 1]
            tit = font_big.render(q["title"], True, GOLD)
            screen.blit(tit, (20, 20))
            y = 50
            for sub in wrap_text(q["question"], max_w):
                t = font_small.render(sub, True, PAPER)
                screen.blit(t, (20, y))
                y += 14
            y += 12
            opt_h = 52
            for opt in q["options"]:
                rect = pygame.Rect(20, y, LOW_W - 40, opt_h)
                boss_option_rects.append(rect)
                draw_pixel_border(screen, rect, FELT_DARK, GOLD)
                ty = y + 6
                for sub in wrap_text(opt["text"], max_w - 16):
                    line = font_small.render(sub, True, PAPER)
                    screen.blit(line, (28, ty))
                    ty += 14
                y += opt_h + 8
            return

        # Outcome
        title, lines, success = get_final_stage_outcome(state, boss_readiness_deltas)
        tit = font_big.render(title, True, GOLD if success else RED)
        screen.blit(tit, ((LOW_W - tit.get_width()) // 2, 24))
        y = 58
        for line in lines:
            for sub in wrap_text(line, max_w):
                t = font_small.render(sub, True, PAPER)
                screen.blit(t, (20, y))
                y += 14
            y += 4
        esc = font_small.render("Press ESC to quit.", True, GOLD)
        screen.blit(esc, ((LOW_W - esc.get_width()) // 2, LOW_H - 28))

    def start_admin_phase2() -> None:
        nonlocal mode, phase2_played, phase2_passed_challenge, phase2_cards, phase2_start_centers
        nonlocal phase2_anim_progress, phase2_subphase, phase2_questions, phase2_q_index
        nonlocal phase2_strikes, phase2_correct, phase2_used, phase2_scaled_art_cache, phase2_play_anims
        nonlocal phase2_hover_i, phase2_end_panel_rect, contract_eval_passed, game_over_from_contract_eval

        # Curated active set for Phase 2 testing (up to 6 slots).
        admin_keys = [
            "explainable_documentation",
            "human_in_the_loop",
            "bias_fairness",
            "data_privacy",
            "robustness_testing",
            "carbon_footprint",
        ]

        # Clear & seed ACTIVE cards.
        state.active_slots = [None] * 6
        cards_by_key: Dict[str, Card] = {c.key: c for c in cards_pool}
        for i, k in enumerate(admin_keys[: len(state.active_slots)]):
            state.active_slots[i] = cards_by_key.get(k)

        recompute_stats_from_active(state)

        phase2_played = True
        phase2_passed_challenge = False
        phase2_cards = []
        phase2_start_centers = []
        phase2_q_index = 0
        phase2_strikes = 0
        phase2_correct = 0
        phase2_used = []
        phase2_scaled_art_cache.clear()
        phase2_play_anims.clear()
        phase2_hover_i = None
        phase2_end_panel_rect = None
        phase2_anim_progress = 0.0
        phase2_subphase = "anim"

        cap = get_active_slot_capacity(state)
        slot_rects = active_slot_rects()
        for i in range(cap):
            c = state.active_slots[i] if i < len(state.active_slots) else None
            if c is not None:
                phase2_cards.append(c)
                phase2_start_centers.append((slot_rects[i].centerx, slot_rects[i].centery))

        pk = {c.key for c in phase2_cards}
        desired_q = 6 if "carbon_footprint" in pk else 5
        desired_q = min(desired_q, len(phase2_cards))
        phase2_questions = pick_phase2_questions(rng, pk, desired_q)
        phase2_used = [False] * len(phase2_cards)

        contract_eval_passed = False
        game_over_from_contract_eval = False

        mode = "phase2"

    # Start in menu; start_round() is called when leaving menu (Play -> intro)
    if admin_phase2:
        start_admin_phase2()
    elif mode != "menu":
        start_round()

    clock = pygame.time.Clock()
    running = True
    headless_frames = 0
    while running:
        frame += 1
        dt = clock.tick(60)
        _ = dt  # reserved for later animations

        mx, my = pygame.mouse.get_pos()
        lmx, lmy = mx // SCALE, my // SCALE
        mouse_low = (lmx, lmy)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if mode == "menu":
                    if menu_play_rect and menu_play_rect.collidepoint(mouse_low):
                        contracts = get_contracts()
                        if contracts:
                            state.scenario_key = rng.choice([c["key"] for c in contracts])
                        mode = "intro"
                    elif menu_credits_rect and menu_credits_rect.collidepoint(mouse_low):
                        mode = "credits"
                    elif menu_admin_rect and menu_admin_rect.collidepoint(mouse_low):
                        start_admin_phase2()
                    # Settings: placeholder, no-op
                    continue
                if mode == "credits" and credits_back_rect and credits_back_rect.collidepoint(mouse_low):
                    mode = "menu"
                    continue
                if mode == "intro":
                    start_round()
                    recompute_stats_from_active(state)
                    message = "Click deck to draw & advance. Max 5 in hand. Active cards = your stats."
                    mode = "game"
                    continue
                if mode == "phase2":
                    if phase2_subphase in ("won", "lost"):
                        pr = phase2_end_panel_rect
                        if pr is None or pr.collidepoint(mouse_low):
                            won = phase2_subphase == "won"
                            phase2_passed_challenge = won
                            contract_eval_passed = won
                            game_over_from_contract_eval = True
                            mode = "over"
                    elif phase2_subphase == "play" and phase2_q_index < len(phase2_questions):
                        # Don't allow multiple answers while a played-card cleanup animation is running.
                        if phase2_play_anims:
                            continue
                        rects = phase2_card_layout_rects()
                        for i, cr in enumerate(rects):
                            if i >= len(phase2_cards) or (i < len(phase2_used) and phase2_used[i]):
                                continue
                            if not cr.collidepoint(mouse_low):
                                continue
                            q = phase2_questions[phase2_q_index]
                            acc = set(q.get("acceptable") or [])
                            card = phase2_cards[i]
                            if card.key in acc:
                                phase2_correct += 1
                                phase2_used[i] = True
                                # Animate the played card toward the question, then fade away.
                                # Anchor is near the question text block.
                                phase2_play_anims.append(
                                    (i, cr.copy(), 0.0, PHASE2_PLAY_TARGET)
                                )
                                phase2_q_index += 1
                                n = len(phase2_questions)
                                if phase2_q_index >= n:
                                    need = max(0, n - 1)
                                    if phase2_correct >= need:
                                        phase2_subphase = "won"
                                    else:
                                        phase2_subphase = "lost"
                            else:
                                phase2_strikes += 1
                                if phase2_strikes >= 2:
                                    phase2_subphase = "lost"
                            break
                    continue
                if mode == "over" and game_over_retry_rect and game_over_retry_rect.collidepoint(mouse_low):
                    state = State()
                    deck, discard, collected, hand = [], [], [], []
                    selected = []
                    played_this_round = False
                    played_effects_this_round.clear()
                    constraint_failed = False
                    game_over_from_contract_eval = False
                    contract_eval_passed = False
                    phase2_played = False
                    phase2_passed_challenge = False
                    phase2_cards.clear()
                    phase2_start_centers.clear()
                    phase2_questions.clear()
                    phase2_used.clear()
                    phase2_scaled_art_cache.clear()
                    phase2_play_anims.clear()
                    phase2_subphase = ""
                    phase2_anim_progress = 0.0
                    hidden_hand_index = None
                    mode = "menu"
                    collect_anim_list.clear()
                    continue
                if hard_loss() or state.round_idx > state.rounds_total or mode != "game":
                    continue
                if deck_draw_in_progress:
                    # During deck animation, ignore card selection/play.
                    continue

                # Deck click: only draw when hand has fewer than 3 cards and deck has cards
                if pending_draw and deck_rect.collidepoint(mouse_low):
                    can_draw = len(hand) < hand_limit and len(deck) > 0
                    if not can_draw:
                        deck_warning_frames = 45
                        deck_warning_hand_full = len(hand) >= hand_limit
                    else:
                        deck_draw_start_hand_len = len(hand)
                        deck_draw_start_had_black_box = any(c and c.key == "black_box_model" for c in state.active_slots)
                        # Black box: pick the first card slot to face-down immediately.
                        # This prevents the first newly appended card from flashing face-up
                        # during the multi-step draw animation.
                        hidden_hand_index = deck_draw_start_hand_len if deck_draw_start_had_black_box else None
                        deck_draw_buffer = []
                        for _ in range(draw_per_round):
                            if len(deck_draw_buffer) >= draw_per_round:
                                break
                            if len(hand) + len(deck_draw_buffer) >= hand_limit:
                                break
                            if not deck:
                                break
                            deck_draw_buffer.append(deck.pop())
                        pending_draw = False
                        pending_draw_frames = 0
                        deck_draw_step_index = 0
                        deck_draw_in_progress = True
                        deck_anim_frames = DECK_DRAW_STEP_FRAMES
                        end_round_after_draw = True
                    continue

                # Start drag from hand or active
                rects = card_rects()
                for i, r in enumerate(rects):
                    if r.collidepoint(mouse_low):
                        dragging_hand_idx = i
                        drag_start_pos = mouse_low
                        break
                if dragging_hand_idx is None:
                    slot_rects = active_slot_rects()
                    for i, r in enumerate(slot_rects):
                        if i < len(state.active_slots) and state.active_slots[i] and r.collidepoint(mouse_low):
                            dragging_active_idx = i
                            break

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if mode == "game":
                    if dragging_hand_idx is not None:
                        if dragging_hand_idx < len(hand):
                            card = hand[dragging_hand_idx]
                            if trash_rect.collidepoint(mouse_low):
                                if dragging_hand_idx == hidden_hand_index:
                                    hidden_hand_index = None
                                elif hidden_hand_index is not None and dragging_hand_idx < hidden_hand_index:
                                    hidden_hand_index -= 1
                                on_card_trashed(state, card)
                                hand.pop(dragging_hand_idx)
                            else:
                                slot_rects = active_slot_rects()
                                dropped_on_active = False
                                cap = get_active_slot_capacity(state)
                                conflict_slot = None
                                # Black box rule: the currently hidden hand card cannot be placed into ACTIVE.
                                if dragging_hand_idx == hidden_hand_index:
                                    for slot_i, sr in enumerate(slot_rects):
                                        if slot_i >= cap:
                                            continue
                                        if sr.collidepoint(mouse_low) and slot_i < len(state.active_slots):
                                            active_slot_conflict_flash = slot_i
                                            active_slot_conflict_frames = 60
                                            break
                                    dropped_on_active = True
                                else:
                                    if card.key in ("real_time_api", "batch_processing"):
                                        other = "batch_processing" if card.key == "real_time_api" else "real_time_api"
                                        for j in range(cap):
                                            oc = state.active_slots[j] if j < len(state.active_slots) else None
                                            if oc and oc.key == other:
                                                conflict_slot = j
                                                break
                                    if conflict_slot is not None:
                                        active_slot_conflict_flash = conflict_slot
                                        active_slot_conflict_frames = 60
                                    else:
                                        for slot_i, sr in enumerate(slot_rects):
                                            if slot_i >= cap:
                                                continue
                                            if sr.collidepoint(mouse_low) and slot_i < len(state.active_slots):
                                                n_active = sum(1 for c in state.active_slots if c is not None)
                                                if n_active < cap:
                                                    first_empty = next((j for j in range(cap) if state.active_slots[j] is None), slot_i)
                                                    state.active_slots[first_empty] = card
                                                    if hidden_hand_index is not None and dragging_hand_idx < hidden_hand_index:
                                                        hidden_hand_index -= 1
                                                    hand.pop(dragging_hand_idx)
                                                    on_card_added_to_active(state, first_empty, card)
                                                    recompute_stats_from_active(state)
                                                    dropped_on_active = True
                                                break
                                if not dropped_on_active and conflict_slot is None:
                                    rects = card_rects()
                                    if dragging_hand_idx < len(rects) and rects[dragging_hand_idx].collidepoint(mouse_low):
                                        conflict_slot_click = None
                                        if card.key in ("real_time_api", "batch_processing"):
                                            other = "batch_processing" if card.key == "real_time_api" else "real_time_api"
                                            for j in range(cap):
                                                oc = state.active_slots[j] if j < len(state.active_slots) else None
                                                if oc and oc.key == other:
                                                    conflict_slot_click = j
                                                    break
                                        if conflict_slot_click is not None:
                                            active_slot_conflict_flash = conflict_slot_click
                                            active_slot_conflict_frames = 60
                                        else:
                                            cap = get_active_slot_capacity(state)
                                            n_active = sum(1 for c in state.active_slots if c is not None)
                                            if n_active < cap:
                                                first_empty = next((j for j in range(cap) if state.active_slots[j] is None), 0)
                                                state.active_slots[first_empty] = card
                                                if hidden_hand_index is not None and dragging_hand_idx < hidden_hand_index:
                                                    hidden_hand_index -= 1
                                                hand.pop(dragging_hand_idx)
                                                on_card_added_to_active(state, first_empty, card)
                                                recompute_stats_from_active(state)
                        dragging_hand_idx = None
                    elif dragging_active_idx is not None:
                        if dragging_active_idx < len(state.active_slots) and state.active_slots[dragging_active_idx]:
                            card = state.active_slots[dragging_active_idx]
                            slot_rects = active_slot_rects()
                            same_slot = slot_rects[dragging_active_idx].collidepoint(mouse_low)
                            if hand_drop_rect.collidepoint(mouse_low) and len(hand) < hand_limit:
                                hand.append(card)
                                state.active_slots[dragging_active_idx] = None
                                on_card_removed_from_active(state, dragging_active_idx, card)
                                recompute_stats_from_active(state)
                            elif trash_rect.collidepoint(mouse_low):
                                state.active_slots[dragging_active_idx] = None
                                on_card_removed_from_active(state, dragging_active_idx, card)
                                on_card_trashed(state, card)
                                recompute_stats_from_active(state)
                            elif same_slot and len(hand) < hand_limit:
                                # Click (no drag) on active card: return to hand with animation
                                state.active_slots[dragging_active_idx] = None
                                on_card_removed_from_active(state, dragging_active_idx, card)
                                recompute_stats_from_active(state)
                                start_r = slot_rects[dragging_active_idx].copy()
                                active_to_hand_anim_list.append((card, start_r, 0.0, dragging_active_idx))
                        dragging_active_idx = None

        # Hover detection (only in game mode, when not dragging)
        hover_idx = None
        hover_active_idx = None
        hover_peek_card = None
        phase2_hover_i = None
        if mode == "phase2" and phase2_subphase == "play":
            rects = phase2_card_layout_rects()
            for i, cr in enumerate(rects):
                if i < len(phase2_used) and phase2_used[i]:
                    continue
                if cr.collidepoint(mouse_low):
                    phase2_hover_i = i
                    break
        elif mode == "game" and dragging_hand_idx is None and dragging_active_idx is None:
            if not deck_draw_in_progress:
                # Explainable documentation: next-card preview above deck
                has_explainable = any(c and c.key == "explainable_documentation" for c in state.active_slots)
                if has_explainable and deck:
                    peek_rect = pygame.Rect(deck_rect.centerx - ACTIVE_CARD_W // 2, deck_rect.y - ACTIVE_CARD_H - 8, ACTIVE_CARD_W, ACTIVE_CARD_H)
                    if peek_rect.collidepoint(mouse_low):
                        hover_peek_card = deck[-1]
                if hover_peek_card is None:
                    slot_rects = active_slot_rects()
                    for i, r in enumerate(slot_rects):
                        if r.collidepoint(mouse_low) and i < len(state.active_slots) and state.active_slots[i]:
                            hover_active_idx = i
                            break
                    if hover_active_idx is None:
                        rects = card_rects()
                        for i, r in enumerate(rects):
                            if r.collidepoint(mouse_low):
                                hover_idx = i
                                break

        if mode == "menu":
            draw_menu()
        elif mode == "credits":
            draw_credits()
        elif mode == "intro":
            draw_intro()
        elif mode == "phase2":
            draw_phase2()
        elif state.round_idx > state.rounds_total or hard_loss() or mode == "over":
            draw_game_over()
        else:
            draw_bg()
            draw_stats()
            draw_active_row()
            draw_message()
            draw_hover_panel()
            draw_cards()
            # Dragged card follows cursor
            if dragging_hand_idx is not None and dragging_hand_idx < len(hand):
                c = hand[dragging_hand_idx]
                dr = pygame.Rect(lmx - CARD_W // 2, lmy - CARD_H // 2, CARD_W, CARD_H)
                outer = card_border_color(c)
                if dragging_hand_idx == hidden_hand_index and deck_back_card_surf is not None:
                    screen.blit(deck_back_card_surf, dr)
                    draw_pixel_frame(screen, dr, outer, PAPER_DARK)
                elif c.art and c.art in card_art_surfs:
                    screen.blit(card_art_surfs[c.art], dr)
                    draw_pixel_frame(screen, dr, outer, PAPER_DARK)
                else:
                    draw_pixel_border(screen, dr, PAPER, outer)
                    pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                    screen.blit(pip, (dr.x + 4, dr.y + 3))
            elif dragging_active_idx is not None and dragging_active_idx < len(state.active_slots) and state.active_slots[dragging_active_idx]:
                c = state.active_slots[dragging_active_idx]
                dr = pygame.Rect(lmx - CARD_W // 2, lmy - CARD_H // 2, CARD_W, CARD_H)
                outer = card_border_color(c)
                if c.art and c.art in card_art_surfs:
                    screen.blit(card_art_surfs[c.art], dr)
                    draw_pixel_frame(screen, dr, outer, PAPER_DARK)
                else:
                    draw_pixel_border(screen, dr, PAPER, outer)
                    pip = rtxt(font_small, c.suit[0].upper(), outer, bold_px=0)
                    screen.blit(pip, (dr.x + 4, dr.y + 3))
        pygame.transform.scale(screen, (W, H), window)
        pygame.display.flip()

        # Advance collect animation: add to collected when progress >= 1
        for i in range(len(collect_anim_list) - 1, -1, -1):
            card, start_r, progress = collect_anim_list[i]
            progress += 1.0 / collect_anim_frames_per_card
            if progress >= 1.0:
                collected.append(card)
                collect_anim_list.pop(i)
            else:
                collect_anim_list[i] = (card, start_r, progress)

        # Advance active-to-hand animation: add to hand when progress >= 1
        for i in range(len(active_to_hand_anim_list) - 1, -1, -1):
            card, start_r, progress, slot_idx = active_to_hand_anim_list[i]
            progress += 1.0 / active_to_hand_frames
            if progress >= 1.0:
                hand.append(card)
                active_to_hand_anim_list.pop(i)
            else:
                active_to_hand_anim_list[i] = (card, start_r, progress, slot_idx)

        if deck_draw_in_progress and deck_anim_frames > 0:
            deck_anim_frames -= 1
        if deck_draw_in_progress and deck_anim_frames <= 0:
            # Commit the next card from the draw buffer.
            if deck_draw_step_index < len(deck_draw_buffer):
                hand.append(deck_draw_buffer[deck_draw_step_index])
                deck_draw_step_index += 1

            if deck_draw_step_index >= len(deck_draw_buffer):
                # Black box model:
                # - The hidden card is revealed only when the next deck draw completes.
                # - If we are continuing the hidden cycle, we hide the *first* newly-drawn card.
                #   (This prevents alternating between different cards within the same round draw.)
                # - Even if the black box model card was removed from ACTIVE, the previously hidden card
                #   should stay hidden until this draw completes.
                hidden_hand_index = deck_draw_start_hand_len if deck_draw_start_had_black_box and deck_draw_start_hand_len < len(hand) else None
                deck_draw_in_progress = False
                deck_draw_buffer = []
                deck_anim_frames = 0
                if end_round_after_draw:
                    end_round_after_draw = False
                    end_round()
            else:
                deck_anim_frames = DECK_DRAW_STEP_FRAMES
        if deck_warning_frames > 0:
            deck_warning_frames -= 1
        if active_slot_conflict_frames > 0:
            active_slot_conflict_frames -= 1
        if pending_draw:
            pending_draw_frames += 1

        if mode == "phase2" and phase2_subphase == "anim":
            phase2_anim_progress += 1.0 / float(PHASE2_ANIM_FRAMES)
            if phase2_anim_progress >= 1.0:
                phase2_anim_progress = 1.0
                phase2_subphase = "play"

        # Cleanup animation: played cards fly toward the question and fade out.
        if mode == "phase2" and phase2_play_anims:
            for j in range(len(phase2_play_anims) - 1, -1, -1):
                card_idx, start_r, prog, target_center = phase2_play_anims[j]
                prog += 1.0 / float(PHASE2_PLAY_ANIM_FRAMES)
                if prog >= 1.0:
                    phase2_play_anims.pop(j)
                else:
                    phase2_play_anims[j] = (card_idx, start_r, prog, target_center)

        if headless:
            headless_frames += 1
            # Run a couple frames then exit successfully.
            if headless_frames > 3:
                running = False

