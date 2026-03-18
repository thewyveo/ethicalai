from __future__ import annotations

import os
import random
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

from ethical_stack.pggame.content import (
    get_active_stats,
    get_deck_for_round,
    get_final_stage_intro,
    get_final_stage_outcome,
    get_final_stage_questions,
    get_round_constraint,
    round_story,
)
from ethical_stack.pggame.model import Card, State, Stat


# --- Visual constants (simple “Balatro-ish” table vibe) ---
# Higher internal res + lower scale = sharper text.
LOW_W, LOW_H = 640, 400
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


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    enabled: bool = True


def run_game(seed: int | None = None, headless: bool = False) -> None:
    """
    Run the graphical game.

    Note: In some headless environments (CI/sandboxes), opening a real window can abort.
    We fall back to SDL's dummy video driver so the module can still be executed safely.
    """
    try:
        pygame.init()
        _run(seed=seed, headless=headless)
    except Exception:
        # Retry once with dummy drivers (no real window).
        try:
            pygame.quit()
        except Exception:
            pass
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        _run(seed=seed, headless=True)
    finally:
        pygame.quit()


def _run(seed: int | None = None, headless: bool = False) -> None:
    rng = random.Random(seed)

    window = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Ethical Stack — Balatro-ish prototype")

    screen = pygame.Surface((LOW_W, LOW_H))

    # Prefer a system font; we render without antialias for crisp pixel look.
    try:
        font = pygame.font.SysFont("Arial", 18, bold=True)
        font_small = pygame.font.SysFont("Arial", 15, bold=True)
        font_big = pygame.font.SysFont("Arial", 24, bold=True)
        font_tiny = pygame.font.SysFont("Arial", 12, bold=True)
    except Exception:
        font = pygame.font.Font(None, 24)
        font_small = pygame.font.Font(None, 20)
        font_big = pygame.font.Font(None, 30)
        font_tiny = pygame.font.Font(None, 16)

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

    # Mechanics knobs (simple and readable)
    hand_limit = 5
    draw_per_round = 3
    play_limit = 3

    # UI layout (low-res coords)
    stat_bar = pygame.Rect(8, 8, LOW_W - 16, 22)
    msg_box = pygame.Rect(8, 34, LOW_W - 16, 72)
    hover_box = pygame.Rect(8, 110, LOW_W - 16, 46)

    # Card size and row position (used for button, deck, trash, cards).
    CARD_W, CARD_H = 80, 104
    card_base_y = LOW_H - CARD_H - 8

    constraint_failed: bool = False

    # Final stage (hospital triage) state
    boss_step: int = 0  # 0 = intro, 1..len(questions) = question, len+1 = outcome
    boss_readiness_deltas: List[int] = []
    boss_option_rects: List[pygame.Rect] = []  # filled during draw for click detection

    # PLAY button: centered above the card row; shown only when at least 1 card selected.
    # Bigger button to fit updated play.png
    btn_play = Button(pygame.Rect((LOW_W - 240) // 2, card_base_y - 64, 240, 56), "PLAY")

    # After PLAY, user must click deck to draw; hint after 2.5s.
    pending_draw: bool = False
    pending_draw_frames: int = 0
    PENDING_DRAW_HINT_FRAMES = 150  # ~2.5s at 60fps

    # Deck-draw animation (cards are added to `hand` one-by-one to allow smooth motion).
    deck_draw_in_progress: bool = False
    deck_draw_buffer: List[Card] = []
    deck_draw_step_index: int = 0  # how many cards from buffer are already committed to hand
    DECK_DRAW_STEP_FRAMES = 18  # frames per "add one card" animation step

    message = "Select up to 3 cards. PLAY commits and scores the round."
    story_line = round_story(state.round_idx)
    mode: str = "intro"  # intro -> game -> over -> boss
    hover_idx: int | None = None
    frame: int = 0

    def draw_from_deck(n: int) -> None:
        nonlocal deck, hand
        for _ in range(n):
            if len(hand) >= hand_limit or not deck:
                break
            hand.append(deck.pop())

    def start_round() -> None:
        nonlocal selected, story_line, message, played_this_round, deck_anim_frames, deck, discard, pending_draw, pending_draw_frames
        nonlocal deck_draw_in_progress, deck_draw_buffer, deck_draw_step_index
        selected = []
        played_this_round = False
        played_effects_this_round.clear()
        story_line = round_story(state.round_idx)
        if state.round_idx == 13:
            return
        deck = get_deck_for_round(rng, state.round_idx)
        discard = []
        deck_draw_in_progress = False
        deck_draw_buffer = []
        deck_draw_step_index = 0
        deck_anim_frames = 0
        # User must click the deck to draw (no auto-draw).
        pending_draw = True
        pending_draw_frames = 0
        message = "Meet this round's requirement to advance."

    def hard_loss() -> bool:
        return state.trust < 0 or state.fairness < 0 or state.transparency < 0 or state.automation < 0

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
        nonlocal message, story_line, mode, constraint_failed
        if hard_loss():
            return
        if check_round_constraint():
            constraint_failed = True
            c = get_round_constraint(state.round_idx)
            if c:
                stat, min_val = c
                stat_name = stat.replace("_", " ").title()
                message = f"Requirement not met: {stat_name} must be >= {min_val}."
            mode = "over"
            return

        base = state.base_points()
        state.score += max(0, base)

        if state.round_idx < state.rounds_total:
            state.round_idx += 1
            if state.round_idx == 13:
                story_line = "Final stage."
                message = "Boss / final stage - placeholder."
                mode = "boss"
                return
            start_round()
        else:
            story_line = "Run complete."
            message = "Your choices outlive your dashboard."
            mode = "over"

    def suit_color(suit: str) -> Tuple[int, int, int]:
        return RED if suit in ("heart", "diamond") else BLUE

    def card_effect_line(c: Card) -> str:
        active = get_active_stats(state.round_idx)
        parts: List[str] = []
        shorts = {"trust": "T", "automation": "A", "fairness": "F", "transparency": "TP"}
        for key in active:
            short = shorts.get(key, key[:2])
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
        labels = {"trust": "T", "automation": "A", "fairness": "F", "transparency": "TP"}
        metrics = "  ".join(f"{labels.get(s, s)}:{state.get_stat(s)}" for s in active)
        mtxt = rtxt(font_small, metrics, PAPER)
        screen.blit(mtxt, (stat_bar.x + 6, stat_bar.y + 5))
        score_str = f"SCORE:{state.score}"
        stxt = rtxt(font_small, score_str, PAPER)
        screen.blit(stxt, (stat_bar.centerx - stxt.get_width() // 2, stat_bar.y + 5))
        if state.round_idx >= 13:
            rlabel = "Final Round"
        else:
            rlabel = f"Round {state.round_idx} of 12"
        rts = rtxt(font_small, rlabel, GOLD)
        screen.blit(rts, (stat_bar.right - rts.get_width() - 6, stat_bar.y + 5))

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

    def draw_message() -> None:
        draw_pixel_border_alpha(screen, msg_box, FELT_DARK, GOLD, fill_alpha=235)
        y = msg_box.y + 4
        max_w = msg_box.w - 12
        line_step = font_small.get_linesize() + 5
        for line in wrap_text(story_line, max_w):
            t = rtxt(font_small, line, PAPER)
            screen.blit(t, (msg_box.x + 6, y))
            y += line_step
        if message:
            for line in wrap_text(message, max_w):
                m = rtxt(font_small, line, GOLD)
                screen.blit(m, (msg_box.x + 6, y))
                y += line_step
        c = get_round_constraint(state.round_idx)
        if c and state.round_idx <= 3:
            stat, min_val = c
            req = f"Requirement: {stat.replace('_', ' ').title()} >= {min_val}"
            for line in wrap_text(req, max_w):
                r = rtxt(font_small, line, (200, 198, 188), bold_px=0)
                screen.blit(r, (msg_box.x + 6, y))
                y += line_step

    def draw_hover_panel() -> None:
        if hover_idx is None or hover_idx < 0 or hover_idx >= len(hand):
            return
        c = hand[hover_idx]
        draw_pixel_border_alpha(screen, hover_box, FELT_DARK, GOLD, fill_alpha=235)

        name = rtxt(font_small, c.name, PAPER)
        screen.blit(name, (hover_box.x + 6, hover_box.y + 4))
        # Effect line: each stat token colored by sign (green for +, red for -).
        active = get_active_stats(state.round_idx)
        shorts = {"trust": "T", "automation": "A", "fairness": "F", "transparency": "TP"}
        x = hover_box.x + 6
        y = hover_box.y + 16
        pos_c = (80, 210, 130)
        neg_c = (220, 72, 72)
        neutral_c = (200, 198, 188)
        any_token = False
        for key in active:
            v = int(c.effects.get(key, 0))
            if not v:
                continue
            any_token = True
            short = shorts.get(key, key[:2])
            sign = "+" if v > 0 else ""
            token = f"{short} {sign}{v}  "
            color = pos_c if v > 0 else neg_c
            surf = rtxt(font_small, token, color)
            screen.blit(surf, (x, y))
            x += surf.get_width()
        if not any_token:
            eff = rtxt(font_small, "—", neutral_c, bold_px=0)
            screen.blit(eff, (x, y))

        # wrap the ethical blurb into 2 lines max
        blurb = c.text.strip()
        words = blurb.split()
        line1: List[str] = []
        line2: List[str] = []
        current = line1
        for w in words:
            trial = " ".join(current + [w])
            if font_small.size(trial)[0] <= (hover_box.w - 12):
                current.append(w)
            elif current is line1:
                current = line2
                if font_small.size(w)[0] <= (hover_box.w - 12):
                    current.append(w)
            else:
                break
        l1 = rtxt(font_small, " ".join(line1), (200, 198, 188), bold_px=0)
        l2 = rtxt(font_small, " ".join(line2), (200, 198, 188), bold_px=0)
        screen.blit(l1, (hover_box.x + 6, hover_box.y + 28))
        if line2:
            screen.blit(l2, (hover_box.x + 6, hover_box.y + 38))

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
                    outer = GOLD
                    if c.art and c.art in card_art_surfs:
                        screen.blit(card_art_surfs[c.art], r)
                        draw_pixel_frame(screen, r, outer, PAPER_DARK)
                    else:
                        body = PAPER if i not in selected else (250, 248, 240)
                        edge = GOLD
                        draw_pixel_border(screen, r, body, edge)
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

                outer = GOLD
                if c.art and c.art in card_art_surfs:
                    screen.blit(card_art_surfs[c.art], r)
                    draw_pixel_frame(screen, r, outer, PAPER_DARK)
                else:
                    body = PAPER if i not in selected else (250, 248, 240)
                    edge = GOLD
                    draw_pixel_border(screen, r, body, edge)
                    pip = rtxt(font_small, c.suit[0].upper(), edge, bold_px=0)
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

        # Normal (no animation): draw real hand at its current centered positions.
        rects = card_rects()
        for i, (c, r) in enumerate(zip(hand, rects)):
            outer = GOLD
            inner = PAPER_DARK

            if c.art and c.art in card_art_surfs:
                if i in selected:
                    card_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                    card_surf.blit(card_art_surfs[c.art], (0, 0))
                    draw_pixel_frame(card_surf, pygame.Rect(0, 0, r.w, r.h), outer, inner)
                    angle = math.sin((frame * 0.22) + i * 1.1) * 2.0  # degrees, gentle roll
                    rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                    dest = rotated.get_rect(center=r.center)
                    screen.blit(rotated, dest)
                else:
                    screen.blit(card_art_surfs[c.art], r)
                    draw_pixel_frame(screen, r, outer, inner)
            else:
                # Fallback when no artwork is assigned.
                body = PAPER if i not in selected else (250, 248, 240)
                edge = GOLD
                pip = rtxt(font_small, c.suit[0].upper(), edge, bold_px=0)
                if i in selected:
                    card_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                    draw_pixel_border(card_surf, pygame.Rect(0, 0, r.w, r.h), body, edge)
                    card_surf.blit(pip, (4, 3))
                    angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                    rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                    dest = rotated.get_rect(center=r.center)
                    screen.blit(rotated, dest)
                else:
                    draw_pixel_border(screen, r, body, edge)
                    screen.blit(pip, (r.x + 4, r.y + 3))

    deck_rect = pygame.Rect(10, card_base_y, CARD_W, CARD_H)
    collected_rect = pygame.Rect(LOW_W - 10 - CARD_W, card_base_y, CARD_W, CARD_H)
    deck_anim_frames = 0
    trash_flash_frames = 0

    # Deck back image (card back graphic)
    _pggame_dir = os.path.dirname(os.path.abspath(__file__))
    _src_dir = os.path.join(_pggame_dir, "..", "src")
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

    # Cached at the card size so deck animation can reuse it without rescaling every frame.
    deck_back_card_surf: Optional[pygame.Surface] = None
    if deck_back_surf is not None:
        deck_back_card_surf = pygame.transform.smoothscale(deck_back_surf, (CARD_W, CARD_H))

    # Card artwork cache (optional artwork provided by files in `src/cards/`).
    card_art_surfs: Dict[str, pygame.Surface] = {}
    _cards_dir = os.path.join(_src_dir, "cards")
    if os.path.isdir(_cards_dir):
        for _fn in os.listdir(_cards_dir):
            if not _fn.lower().endswith((".png", ".webp")):
                continue
            _path = os.path.join(_cards_dir, _fn)
            try:
                _surf = pygame.image.load(_path).convert_alpha()
                # Use non-smooth scaling to keep pixel-art-ish edges.
                card_art_surfs[_fn] = pygame.transform.scale(_surf, (CARD_W, CARD_H))
            except Exception:
                pass

    _play_paths = [
        os.path.join(_src_dir, "play.png"),
        os.path.join(_src_dir, "play.webp"),
    ]
    play_surf: Optional[pygame.Surface] = None
    play_btn_surf: Optional[pygame.Surface] = None
    play_btn_draw_surf: Optional[pygame.Surface] = None
    play_btn_hit_rect: Optional[pygame.Rect] = None
    for _path in _play_paths:
        if os.path.isfile(_path):
            try:
                play_surf = pygame.image.load(_path).convert_alpha()
                # Scale to FIT the button rect (no distortion).
                iw, ih = play_surf.get_width(), play_surf.get_height()
                if iw > 0 and ih > 0:
                    scale = min(btn_play.rect.w / iw, btn_play.rect.h / ih)
                    tw = max(1, int(iw * scale))
                    th = max(1, int(ih * scale))
                    play_btn_surf = pygame.transform.smoothscale(play_surf, (tw, th))
                    # 2x visual size (image only). Hitbox stays at fitted size.
                    play_btn_draw_surf = pygame.transform.smoothscale(play_surf, (max(1, tw * 2), max(1, th * 2)))
                    # Hitbox will be set each frame from the actual blit rect.
                break
            except Exception:
                pass

    def draw_play_button(hover: bool) -> None:
        nonlocal play_btn_hit_rect
        if play_btn_surf is None:
            draw_button(btn_play, hover)
            play_btn_hit_rect = btn_play.rect.copy()
            return
        # Hitbox uses fitted image rect; draw uses a 2x visual surface.
        play_btn_hit_rect = play_btn_surf.get_rect(center=btn_play.rect.center)
        draw_surf = play_btn_draw_surf or play_btn_surf
        dest = draw_surf.get_rect(center=play_btn_hit_rect.center)
        if hover and btn_play.enabled:
            dest.x += 1
            dest.y += 1
        screen.blit(draw_surf, dest)

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
            # Deck pile: use card back image if loaded, else placeholder
            if deck_back_card_surf is not None:
                screen.blit(deck_back_card_surf, deck_rect)
            else:
                draw_pixel_border(screen, deck_rect, PAPER_DARK, GOLD)

            # Draw hint above deck (small, yellow, pulsing).
            if pending_draw and pending_draw_frames >= PENDING_DRAW_HINT_FRAMES:
                hint_text = "Click to draw"
                hint = rtxt(font_tiny, hint_text, GOLD, bold_px=1)
                t = pending_draw_frames - PENDING_DRAW_HINT_FRAMES
                period = 90  # ~1.5s at 60fps
                pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * (t / period))
                alpha = int(210 + 45 * pulse)
                hint.set_alpha(alpha)
                hx = deck_rect.centerx - hint.get_width() // 2
                hy = deck_rect.y - hint.get_height() - 2
                screen.blit(hint, (hx, hy))

            # Collected pile area (right side, where trash used to be)
            label = rtxt(font_tiny, "COLLECTED", GOLD, bold_px=1)
            lx = collected_rect.centerx - label.get_width() // 2
            ly = collected_rect.y - label.get_height() - 6
            # subtle shadow for visibility
            shadow = rtxt(font_tiny, "COLLECTED", INK, bold_px=1)
            shadow.set_alpha(160)
            screen.blit(shadow, (lx + 1, ly + 1))
            screen.blit(label, (lx, ly))

            if not collected:
                draw_pixel_border(screen, collected_rect, FELT_DARK, GOLD)
            else:
                max_show = 5
                show = collected[-max_show:]
                for j, card in enumerate(show):
                    dx = -2 * (len(show) - 1 - j)
                    dy = -2 * (len(show) - 1 - j)
                    r = pygame.Rect(collected_rect.x + dx, collected_rect.y + dy, CARD_W, CARD_H)
                    outer = GOLD
                    if card.art and card.art in card_art_surfs:
                        screen.blit(card_art_surfs[card.art], r)
                        draw_pixel_frame(screen, r, outer, PAPER_DARK)
                    else:
                        edge = GOLD
                        draw_pixel_border(screen, r, PAPER_DARK, edge)

    def draw_intro() -> None:
        draw_tiled_background()
        draw_pixel_border(screen, pygame.Rect(8, 8, LOW_W - 16, LOW_H - 16), FELT_DARK, GOLD)

        lines = [
            "The stakes are high. You are a CEO of an AI startup.",
            "",
            "",
            "",
            "There are four stats that will determine the success of your company:",
            "- Transparency: How transparent your AI is to the public.",
            "- Trust: How trusted your AI is by the public.",
            "- Fairness: How fair your AI is to the public.",
            "- Automation: How automated your AI is.",
            "",
            "",
            "",
            "You will be given a deck of cards. Each card will have a stat and a value.",
            "Select up to 3 cards, LOCK IN once ready. If any stat goes below 0, you lose.",
            "Hover cards to see effects. Meet the requirement of the round to advance.",
            "",
            "",
            "",
            "Be careful! The cards you collect will matter..."
        ]
        y = 52
        line_step = font_small.get_linesize() + 5
        for ln in lines:
            for sub in wrap_text(ln, LOW_W - 28):
                rr = rtxt(font_small, sub, (210, 208, 198), bold_px=0)
                screen.blit(rr, (14, y))
                y += line_step
            y += 2

        tip = rtxt(font_small, "Click anywhere to begin. ESC quits.", GOLD)
        screen.blit(tip, (14, LOW_H - 20))

    def draw_game_over() -> None:
        draw_bg()
        if constraint_failed:
            msg = "RUN FAILED"
            sub = message
        elif hard_loss():
            msg = "RUN FAILED"
            sub = "A stat dropped below zero."
        else:
            msg = "RUN COMPLETE"
            sub = "Your choices outlive your dashboard."
        big = font_big.render(msg, True, RED if (constraint_failed or hard_loss()) else GOLD)
        screen.blit(big, (10, 90))
        yy = 112
        for line in wrap_text(sub, LOW_W - 20):
            small = font_small.render(line, True, PAPER)
            screen.blit(small, (10, yy))
            yy += 10
        esc = font_small.render("Press ESC to quit.", True, GOLD)
        screen.blit(esc, (10, LOW_H - 24))

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
            stats_line = f"Your run: Trust {state.trust}  Automation {state.automation}  Fairness {state.fairness}  Transparency {state.transparency}"
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

        # Compute play button hitbox from actual drawn rect (so clicks work even before first draw).
        if play_btn_surf is not None:
            play_btn_hit_rect = play_btn_surf.get_rect(center=btn_play.rect.center)
        else:
            play_btn_hit_rect = btn_play.rect.copy()

        # buttons enabled rules (must have drawn cards this round before playing)
        btn_play.enabled = (
            (not hard_loss())
            and (state.round_idx <= state.rounds_total)
            and (len(selected) > 0)
            and (not played_this_round)
            and (not pending_draw)
            and (not deck_draw_in_progress)
        )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if mode == "intro":
                    mode = "game"
                    message = "Play up to 3 cards. LOCK IN once ready."
                    continue
                if mode == "boss":
                    questions = get_final_stage_questions()
                    if boss_step == 0:
                        boss_step = 1
                        continue
                    if 1 <= boss_step <= len(questions):
                        for i, rect in enumerate(boss_option_rects):
                            if rect.collidepoint(mouse_low) and i < len(questions[boss_step - 1]["options"]):
                                opt = questions[boss_step - 1]["options"][i]
                                boss_readiness_deltas.append(opt["readiness_delta"])
                                boss_step += 1
                                if boss_step > len(questions):
                                    boss_step = len(questions) + 1
                                break
                    continue
                if hard_loss() or state.round_idx > state.rounds_total or mode != "game":
                    continue
                if deck_draw_in_progress:
                    # During deck animation, ignore card selection/play.
                    continue

                # Deck click: draw cards when waiting for draw
                if pending_draw and deck_rect.collidepoint(mouse_low):
                    # Pop cards into an animation buffer (do not add to hand until each step completes).
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
                    continue

                # Card clicks
                rects = card_rects()
                for i, r in enumerate(rects):
                    if r.collidepoint(mouse_low):
                        if i in selected:
                            selected.remove(i)
                        else:
                            if len(selected) < play_limit:
                                selected.append(i)
                        break

                # Button clicks
                if btn_play.enabled and (play_btn_hit_rect or btn_play.rect).collidepoint(mouse_low):
                    # Play selected cards: apply effects, then remove them from hand.
                    # (Balatro-ish commitment: once played, they’re gone.)
                    # Play order is left->right, so the rightmost selected becomes "last played".
                    sel_lr = sorted(selected)
                    cards_to_play = [hand[i] for i in sel_lr]
                    for card in cards_to_play:
                        state.apply(card.effects)
                        discard.append(card)
                        collected.append(card)
                    # Remove from hand safely (highest index first).
                    for idx in sorted(selected, reverse=True):
                        hand.pop(idx)
                    selected = []
                    played_this_round = True
                    message = "Committed. Scoring round..."
                    end_round()

        # Hover detection (only in game mode)
        hover_idx = None
        if mode == "game":
            if not deck_draw_in_progress:
                rects = card_rects()
                for i, r in enumerate(rects):
                    if r.collidepoint(mouse_low):
                        hover_idx = i
                        break

        if mode == "intro":
            draw_intro()
        elif mode == "boss":
            draw_boss()
        elif state.round_idx > state.rounds_total or hard_loss() or mode == "over":
            draw_game_over()
        else:
            draw_bg()
            draw_stats()
            draw_message()
            draw_hover_panel()
            draw_cards()

            # PLAY button only when at least one card is selected
            if len(selected) > 0:
                hover_play = play_btn_hit_rect.collidepoint(mouse_low)
                draw_play_button(hover_play)

        pygame.transform.scale(screen, (W, H), window)
        pygame.display.flip()

        if deck_draw_in_progress and deck_anim_frames > 0:
            deck_anim_frames -= 1
        if deck_draw_in_progress and deck_anim_frames <= 0:
            # Commit the next card from the draw buffer.
            if deck_draw_step_index < len(deck_draw_buffer):
                hand.append(deck_draw_buffer[deck_draw_step_index])
                deck_draw_step_index += 1

            if deck_draw_step_index >= len(deck_draw_buffer):
                deck_draw_in_progress = False
                deck_draw_buffer = []
                deck_anim_frames = 0
            else:
                deck_anim_frames = DECK_DRAW_STEP_FRAMES
        # (Removed) trash flash animation
        if pending_draw:
            pending_draw_frames += 1

        if headless:
            headless_frames += 1
            # Run a couple frames then exit successfully.
            if headless_frames > 3:
                running = False

