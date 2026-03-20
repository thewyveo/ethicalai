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
# Epic rarity (matches hover label); used for frame + godray tint.
EPIC_PURPLE = (160, 90, 220)
# Epic: extra margin around the face rect so godrays render *behind* the card but stay visible as a halo.
EPIC_GODRAY_HALO_PAD = 14
# Multiplier for the rotating ray fan texture size (extends into halo; clipped to the layer).
EPIC_GODRAY_VISUAL_SCALE = 2.8
# Epic godray overlay alpha pulse (slow continuous): 100 -> 50 -> 100 -> ...
EPIC_GODRAY_ALPHA_MIN = 50
EPIC_GODRAY_ALPHA_MAX = 100
EPIC_GODRAY_ALPHA_PERIOD_S = 8.0
# Cursed: single centered horns image, nudged up from the card top.
CURSED_HORN_TOP_INSET = 5
CURSED_HORN_RAISE_PX = 29


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
    pygame.display.set_caption("ETHICAL STACK")

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
    _sfx_dir = os.path.join(_src_dir, "sfx")
    CARD_W, CARD_H = 80, 104
    # Phase 2: base size multiplier; actual target size is dynamic so cards fit.
    PHASE2_BASE_SCALE = 1.58
    PHASE2_BASE_W, PHASE2_BASE_H = int(CARD_W * PHASE2_BASE_SCALE), int(CARD_H * PHASE2_BASE_SCALE)
    _PHASE2_BASE_ASPECT = PHASE2_BASE_H / float(PHASE2_BASE_W) if PHASE2_BASE_W else 1.0

    # Phase 2 top UI layout (green container, golden divider, strike on right 10%).
    PHASE2_UI_X = 16
    PHASE2_UI_Y = 12
    PHASE2_UI_W = LOW_W - 32
    PHASE2_UI_H = 94
    PHASE2_UI_LEFT_W = int(PHASE2_UI_W * 0.86)
    PHASE2_UI_DIV_X = PHASE2_UI_X + PHASE2_UI_LEFT_W
    PHASE2_UI_CROSS_CENTER = (
        PHASE2_UI_DIV_X + (PHASE2_UI_W - PHASE2_UI_LEFT_W) // 2,
        PHASE2_UI_Y + PHASE2_UI_H // 2 - 2,
    )
    PHASE2_UI_QUESTION_TEXT_X = PHASE2_UI_X + 12
    PHASE2_UI_QUESTION_TEXT_Y = PHASE2_UI_Y + 30
    PHASE2_PLAY_TARGET = (PHASE2_UI_X + PHASE2_UI_LEFT_W // 2, PHASE2_UI_Y + 80)
    PHASE2_SCORE_CORRECT = 8
    PHASE2_SCORE_WRONG = 6
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

    # --- SFX ---
    sfx: Dict[str, pygame.mixer.Sound] = {}
    sfx_enabled = False
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sfx_enabled = True
    except Exception:
        sfx_enabled = False

    def _load_sfx(name: str) -> None:
        if not sfx_enabled:
            return
        p = os.path.join(_sfx_dir, f"{name}.mp3")
        if not os.path.isfile(p):
            return
        try:
            sfx[name] = pygame.mixer.Sound(p)
        except Exception:
            pass

    for _n in (
        "bin",
        "button",
        "draw",
        "equip_common",
        "equip_rare",
        "equip_epic",
        "equip_cursed",
        "hover",
        "lose",
        "win",
        "woosh",
    ):
        _load_sfx(_n)

    # User preference (Settings); independent of mixer init failure.
    sfx_on = True

    # Dev-only: show/enable the Admin Phase2 menu button.
    # Default is disabled; enable by setting `EAI_ADMIN_PHASE2=1` (or true/yes).
    ADMIN_PHASE2_ENABLED = os.environ.get("EAI_ADMIN_PHASE2", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "dev",
    )

    def play_sfx(name: str) -> None:
        if not sfx_on:
            return
        snd = sfx.get(name)
        if snd is None:
            return
        try:
            snd.play()
        except Exception:
            pass

    def play_equip_sfx(card: Card) -> None:
        rarity = str(getattr(card, "rarity", "common")).lower()
        mapped = f"equip_{rarity}" if rarity in ("common", "rare", "epic", "cursed") else "equip_common"
        play_sfx(mapped)

    # Credits: author logos (scaled slightly bigger than hand card size).
    author1_logo_surf: Optional[pygame.Surface] = None
    _author1_path = os.path.join(_src_dir, "author1.png")
    if os.path.isfile(_author1_path):
        try:
            _author1_surf = pygame.image.load(_author1_path).convert_alpha()
            author1_logo_surf = pygame.transform.smoothscale(
                _author1_surf, (int(CARD_W * 1.6), int(CARD_H * 1.6))
            )
        except Exception:
            author1_logo_surf = None
    author2_logo_surf: Optional[pygame.Surface] = None
    _author2_path = os.path.join(_src_dir, "author2.png")
    if os.path.isfile(_author2_path):
        try:
            _author2_raw = pygame.image.load(_author2_path).convert_alpha()
            author2_logo_surf = pygame.transform.smoothscale(
                _author2_raw, (int(CARD_W * 1.6), int(CARD_H * 1.6))
            )
        except Exception:
            author2_logo_surf = None

    # Settings screen: SFX icon (decorative).
    sfx_settings_icon_surf: Optional[pygame.Surface] = None
    _sfx_icon_path = os.path.join(_src_dir, "sfx_settings.png")
    if os.path.isfile(_sfx_icon_path):
        try:
            _sfx_raw = pygame.image.load(_sfx_icon_path).convert_alpha()
            _iw, _ih = _sfx_raw.get_width(), _sfx_raw.get_height()
            _icon_max = 78  # 1.5× previous 52px cap
            _w, _h = _iw, _ih
            if _w <= _icon_max and _h <= _icon_max:
                _w = max(1, int(_iw * 1.5))
                _h = max(1, int(_ih * 1.5))
            if _w > _icon_max or _h > _icon_max:
                _scale = min(_icon_max / float(_w), _icon_max / float(_h))
                _w = max(1, int(_w * _scale))
                _h = max(1, int(_h * _scale))
            sfx_settings_icon_surf = pygame.transform.smoothscale(_sfx_raw, (_w, _h))
        except Exception:
            sfx_settings_icon_surf = None

    # cards.txt: number, color (r/w), key, rarity — border from card.suit
    cards_pool: List[Card] = load_cards_from_file(_cards_dir)

    def card_border_color(c: Card) -> Tuple[int, int, int]:
        """Border from card suit: r = red, w = white."""
        if getattr(c, "suit", None) == "r":
            return RED
        if getattr(c, "suit", None) == "w":
            return WHITE
        return GOLD

    def _normalize_card_rarity(c: Card) -> str:
        r = str(getattr(c, "rarity", "common") or "common").lower()
        return r if r in ("common", "rare", "epic", "cursed") else "common"

    def card_frame_outer_color(c: Card) -> Tuple[int, int, int]:
        """Outer frame: rare/epic match rarity text colors; others use suit colors."""
        r = _normalize_card_rarity(c)
        if r == "rare":
            return BLUE
        if r == "epic":
            return EPIC_PURPLE
        return card_border_color(c)

    # Cursed: one horns.png (both horns), centered on top. Epic: godray layer (helpers below).
    horns_raw: Optional[pygame.Surface] = None
    _horns_path = os.path.join(_src_dir, "horns.png")
    if os.path.isfile(_horns_path):
        try:
            horns_raw = pygame.image.load(_horns_path).convert_alpha()
        except Exception:
            horns_raw = None
    # Intro tutorial overlays.
    cursor_raw: Optional[pygame.Surface] = None
    _cursor_paths = [
        os.path.join(_src_dir, "cursor.webp"),
        os.path.join(_src_dir, "cursor.png"),
    ]
    for _cp in _cursor_paths:
        if os.path.isfile(_cp):
            try:
                cursor_raw = pygame.image.load(_cp).convert_alpha()
                break
            except Exception:
                cursor_raw = None

    question_mark_raw: Optional[pygame.Surface] = None
    _q_paths = [
        os.path.join(_src_dir, "question_mark.webp"),
        os.path.join(_src_dir, "question_mark.png"),
    ]
    for _qp in _q_paths:
        if os.path.isfile(_qp):
            try:
                question_mark_raw = pygame.image.load(_qp).convert_alpha()
                break
            except Exception:
                question_mark_raw = None

    _intro_cursor_scaled_cache: Dict[Tuple[int, int], pygame.Surface] = {}
    _intro_question_scaled_cache: Dict[Tuple[int, int], pygame.Surface] = {}
    _intro_mini_card_face_cache: Dict[Tuple[str, int, int], pygame.Surface] = {}
    _intro_mini_deck_cache: Dict[Tuple[int, int], pygame.Surface] = {}
    _intro_demo_art_keys: List[str] = sorted(card_art_surfs.keys())
    _intro_demo_card_key_1: Optional[str] = _intro_demo_art_keys[0] if _intro_demo_art_keys else None
    _intro_demo_card_key_2: Optional[str] = _intro_demo_art_keys[1] if len(_intro_demo_art_keys) > 1 else _intro_demo_card_key_1
    _horn_sprite_cache: Dict[Tuple[int, int], pygame.Surface] = {}
    _epic_ray_base_cache: Dict[Tuple[str, int], pygame.Surface] = {}

    def _epic_halo_pad(card: Card) -> int:
        return EPIC_GODRAY_HALO_PAD if _normalize_card_rarity(card) == "epic" else 0

    def _padded_face_wh(card: Card, w: int, h: int) -> Tuple[int, int, int]:
        """Composite surface size (pw, ph) and offset pad so face stays w×h at (pad, pad)."""
        pad = _epic_halo_pad(card)
        return w + 2 * pad, h + 2 * pad, pad

    def blit_epic_godrays_behind_card_layer(dest: pygame.Surface, card: Card, rect: pygame.Rect) -> None:
        """Layer-sized halo behind the card face; blit *before* opaque art so only edges / aura show."""
        pad = _epic_halo_pad(card)
        if pad == 0:
            return
        w, h = max(1, rect.w), max(1, rect.h)
        bw, bh = w + 2 * pad, h + 2 * pad
        layer = pygame.Surface((bw, bh), pygame.SRCALPHA)
        draw_epic_rays_on_card_surface(layer, card, bw, bh)
        dest.blit(layer, (rect.x - pad, rect.y - pad))

    def _horn_sprite_for_card(card_w: int, card_h: int) -> Optional[pygame.Surface]:
        if horns_raw is None:
            return None
        max_w = max(14, card_w - 8)
        th = max(14, min(56, int(card_h * 0.3)))
        iw, ih = horns_raw.get_width(), horns_raw.get_height()
        if ih <= 0:
            return None
        tw = max(1, int(iw * (th / float(ih))))
        if tw > max_w:
            th = max(1, int(ih * (max_w / float(iw))))
            tw = max_w
        key = (tw, th)
        hit = _horn_sprite_cache.get(key)
        if hit is not None:
            return hit
        scaled = pygame.transform.scale(horns_raw, (tw, th))
        _horn_sprite_cache[key] = scaled
        return scaled

    def _epic_sheet_size(cw: int, ch: int) -> int:
        """Large fan inside the (possibly halo-padded) drawable area."""
        m = min(max(1, cw), max(1, ch))
        margin = min(8, max(2, m // 5))
        base = max(6, int((m - margin) / math.sqrt(2.0)))
        sz = max(8, int(base * 2.5))
        max_sz = max(8, int(m * 0.95))
        sz = min(sz, max_sz)
        sz = max(8, int(round(sz * EPIC_GODRAY_VISUAL_SCALE)))
        # Sheet can exceed the layer — center blit still shows longer rays up to the halo edge.
        cap = max(8, int(m * 4.0))
        sz = min(sz, cap)
        if sz % 2:
            sz -= 1
        return max(8, sz)

    def _build_epic_ray_base(sz: int) -> pygame.Surface:
        ck = ("v5", sz)
        hit = _epic_ray_base_cache.get(ck)
        if hit is not None:
            return hit
        s = pygame.Surface((sz, sz), pygame.SRCALPHA)
        cx = cy = sz // 2
        n = 12
        R = max(6, sz // 2 - 4)
        # Lilac/purple fan; drawn on halo layer *behind* the opaque card face.
        pr, pg, pb = EPIC_PURPLE
        # Draw rays fully opaque in their own pixels; final opacity is animated via surface alpha.
        ray_rgba = (min(255, pr + 55), min(255, pg + 70), min(255, pb + 35), 255)
        for i in range(n):
            if i % 2 == 0:
                continue
            a0 = (i / n) * 2 * math.pi - math.pi / 2
            a1 = ((i / n) + 0.68 / n) * 2 * math.pi - math.pi / 2
            x0 = int(cx + R * math.cos(a0))
            y0 = int(cy + R * math.sin(a0))
            x1 = int(cx + R * math.cos(a1))
            y1 = int(cy + R * math.sin(a1))
            pygame.draw.polygon(s, ray_rgba, [(cx, cy), (x0, y0), (x1, y1)])
        _epic_ray_base_cache[ck] = s
        return s

    def _epic_rotation_deg() -> float:
        """Slow rotation (~3.2°/s) for fake godrays."""
        return (pygame.time.get_ticks() / 1000.0) * 4.8

    def draw_epic_rays_on_card_surface(surf: pygame.Surface, card: Card, w: int, h: int) -> None:
        if _normalize_card_rarity(card) != "epic":
            return
        sz = _epic_sheet_size(w, h)
        base = _build_epic_ray_base(sz)
        rot = pygame.transform.rotate(base, _epic_rotation_deg())
        # Slow continuous opacity modulation: 100 -> 50 -> 100 -> ...
        t = pygame.time.get_ticks() / 1000.0
        phase = math.sin(2.0 * math.pi * (t / EPIC_GODRAY_ALPHA_PERIOD_S))
        alpha = int(0.5 * (EPIC_GODRAY_ALPHA_MIN + EPIC_GODRAY_ALPHA_MAX) +
                    0.5 * (EPIC_GODRAY_ALPHA_MAX - EPIC_GODRAY_ALPHA_MIN) * phase)
        alpha = max(0, min(255, alpha))
        rot.set_alpha(alpha)
        cx, cy = w // 2, h // 2
        rr = rot.get_rect(center=(cx, cy))
        surf.blit(rot, rr.topleft)

    def blit_cursed_horns_on_screen(dest: pygame.Surface, card: Card, rect: pygame.Rect) -> None:
        if _normalize_card_rarity(card) != "cursed":
            return
        spr = _horn_sprite_for_card(rect.w, rect.h)
        if spr is None:
            return
        hx = rect.centerx - spr.get_width() // 2
        hy = rect.y + CURSED_HORN_TOP_INSET - CURSED_HORN_RAISE_PX
        dest.blit(spr, (hx, hy))

    def draw_cursed_horns_on_card_surface(
        surf: pygame.Surface, card: Card, w: int, h: int, *, ox: int = 0, oy: int = 0
    ) -> None:
        if _normalize_card_rarity(card) != "cursed":
            return
        spr = _horn_sprite_for_card(w, h)
        if spr is None:
            return
        hx = ox + w // 2 - spr.get_width() // 2
        hy = oy + CURSED_HORN_TOP_INSET - CURSED_HORN_RAISE_PX
        surf.blit(spr, (hx, hy))

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

    message = "Click deck to draw & advance. Max 5 in hand. Active cards = your stats."
    story_line = "Objective will be set when you start."
    objective_setting_line = ""
    objective_stats_line = ""
    mode: str = "menu"  # menu -> intro -> game -> over
    hover_idx: int | None = None
    hover_active_idx: Optional[int] = None
    frame: int = 0
    intro_start_ms: Optional[int] = None
    game_over_retry_rect: Optional[pygame.Rect] = None
    game_over_menu_rect: Optional[pygame.Rect] = None
    game_over_primary_is_menu: bool = False
    menu_play_rect: Optional[pygame.Rect] = None
    menu_credits_rect: Optional[pygame.Rect] = None
    menu_settings_rect: Optional[pygame.Rect] = None
    menu_admin_rect: Optional[pygame.Rect] = None
    credits_back_rect: Optional[pygame.Rect] = None
    settings_back_rect: Optional[pygame.Rect] = None
    settings_sfx_toggle_rect: Optional[pygame.Rect] = None
    contract_eval_passed: bool = False
    game_over_from_contract_eval: bool = False
    # Phase 2: post-contract card quiz (only if contract met at end of round 10).
    phase2_played: bool = False
    phase2_passed_challenge: bool = False
    phase2_cards: List[Card] = []
    phase2_start_centers: List[Tuple[int, int]] = []
    phase2_anim_progress: float = 0.0
    PHASE2_ANIM_FRAMES = 52
    phase2_subphase: str = ""  # anim | play | celebrate
    phase2_questions: List[Dict[str, Any]] = []
    phase2_q_index: int = 0
    phase2_strikes: int = 0
    phase2_correct: int = 0
    phase2_used: List[bool] = []
    # Wrong picks are disabled only for the current question.
    phase2_wrong_locked: set[int] = set()
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
    phase2_pending_outcome: Optional[bool] = None
    # Win celebration (5s) before auto-advancing to final page.
    phase2_win_celebrate_frames: int = 0
    PHASE2_WIN_CELEBRATE_TOTAL = 165  # 55% of prior duration
    # (x, y, vx, vy, spin, rot, scale, alpha)
    phase2_win_burst: List[Tuple[float, float, float, float, float, float, float, float]] = []
    last_hover_token: Optional[str] = None
    win_sfx_played: bool = False
    lose_sfx_played: bool = False

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
        nonlocal phase2_strikes, phase2_correct, phase2_used, phase2_wrong_locked, phase2_scaled_art_cache, phase2_pending_outcome
        nonlocal phase2_win_celebrate_frames, phase2_win_burst
        nonlocal win_sfx_played, lose_sfx_played
        if hard_loss():
            if not lose_sfx_played:
                play_sfx("lose")
                lose_sfx_played = True
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
                    if not lose_sfx_played:
                        play_sfx("lose")
                        lose_sfx_played = True
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
                phase2_wrong_locked.clear()
                phase2_scaled_art_cache.clear()
                phase2_play_anims.clear()
                phase2_pending_outcome = None
                phase2_win_celebrate_frames = 0
                phase2_win_burst.clear()
                win_sfx_played = False
                lose_sfx_played = False
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
            # While dragging, hide the card in its original slot (only the mouse-drag copy is rendered).
            if dragging_active_idx is not None and i == dragging_active_idx:
                card = None
            if card:
                # Card present: draw with same shake/wobble as old selected-hand-cards animation
                outer = card_frame_outer_color(card)
                aw, ah = ACTIVE_CARD_W, ACTIVE_CARD_H
                pw, ph, pp = _padded_face_wh(card, aw, ah)
                card_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                has_art = card.art and card.art in card_art_surfs
                draw_epic_rays_on_card_surface(card_surf, card, pw, ph)
                if has_art:
                    scaled = pygame.transform.smoothscale(card_art_surfs[card.art], (aw, ah))
                    card_surf.blit(scaled, (pp, pp))
                else:
                    draw_pixel_border(card_surf, pygame.Rect(pp, pp, aw, ah), (250, 248, 240), outer)
                if not has_art:
                    pip = rtxt(font_tiny, card.suit[0].upper(), card_border_color(card), bold_px=0)
                    card_surf.blit(pip, (pp + 2, pp + 2))
                draw_pixel_frame(card_surf, pygame.Rect(pp, pp, aw, ah), outer, PAPER_DARK)
                draw_cursed_horns_on_card_surface(card_surf, card, aw, ah, ox=pp, oy=pp)
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
        t_anim = _phase2_ease(phase2_anim_progress) if phase2_subphase == "anim" else 1.0

        # Transition carry-over from Phase 1 while entering Phase 2.
        if phase2_subphase == "anim":
            fade_alpha = int((1.0 - t_anim) * 210)
            if fade_alpha > 0:
                top_ui = pygame.Surface((LOW_W, msg_text_y + 52), pygame.SRCALPHA)
                # Stats bar + objective strip silhouettes fading out.
                pygame.draw.rect(top_ui, (*FELT_DARK, fade_alpha), stat_bar)
                pygame.draw.rect(top_ui, (*FELT_DARK, fade_alpha), pygame.Rect(8, msg_text_y, LOW_W - 16, 44))
                pygame.draw.rect(top_ui, (*GOLD, int(fade_alpha * 0.8)), stat_bar, 2)
                pygame.draw.rect(top_ui, (*GOLD, int(fade_alpha * 0.8)), pygame.Rect(8, msg_text_y, LOW_W - 16, 44), 2)
                screen.blit(top_ui, (0, 0))

            # Trash exits to the right.
            tx = int(trash_rect.x + (LOW_W - trash_rect.x + 30) * t_anim)
            tr = pygame.Rect(tx, trash_rect.y, trash_rect.w, trash_rect.h)
            if trash_card_surf is not None:
                screen.blit(trash_card_surf, tr)
            else:
                draw_pixel_border(screen, tr, FELT_DARK, (140, 80, 60))

        # Deck remains in Phase 2 as a persistent element.
        deck_t = t_anim if phase2_subphase == "anim" else 1.0
        dcx = int(deck_rect.centerx + (LOW_W // 2 - deck_rect.centerx) * deck_t)
        if deck_back_card_surf is not None:
            rot = pygame.transform.rotozoom(deck_back_card_surf, -90.0 * deck_t, 1.0)
            dcy_target = LOW_H - rot.get_height() // 2 + 2
            dcy = int(deck_rect.centery + (dcy_target - deck_rect.centery) * deck_t)
            screen.blit(rot, rot.get_rect(center=(dcx, dcy)))
        else:
            # Fallback if no deck art available.
            w0, h0 = CARD_W, CARD_H
            w1, h1 = CARD_H, CARD_W
            ww = int(w0 + (w1 - w0) * deck_t)
            hh = int(h0 + (h1 - h0) * deck_t)
            dcy_target = LOW_H - hh // 2 + 2
            dcy = int(deck_rect.centery + (dcy_target - deck_rect.centery) * deck_t)
            dr = pygame.Rect(0, 0, ww, hh)
            dr.center = (dcx, dcy)
            draw_pixel_border(screen, dr, PAPER_DARK, GOLD)

        # Top UI: green container for the question + right-side strike strip.
        ui_panel = pygame.Rect(PHASE2_UI_X, PHASE2_UI_Y, PHASE2_UI_W, PHASE2_UI_H)
        ui_alpha_mult = 1.0
        if phase2_subphase == "anim":
            # Two-step transition: Phase 1 UI fades out first, then Phase 2 UI fades in.
            ui_alpha_mult = max(0.0, min(1.0, (t_anim - 0.45) / 0.55))
        ui_fill_alpha = int(235 * ui_alpha_mult)
        if ui_alpha_mult < 1.0:
            # Fade both border and fill together to avoid a bright gold rectangle flash.
            panel_surf = pygame.Surface((ui_panel.w, ui_panel.h), pygame.SRCALPHA)
            draw_pixel_border_alpha(
                panel_surf,
                pygame.Rect(0, 0, ui_panel.w, ui_panel.h),
                FELT_DARK,
                GOLD,
                fill_alpha=ui_fill_alpha,
            )
            # Draw divider on the same fading surface (prevents full-opacity yellow flash).
            div_local_x = PHASE2_UI_DIV_X - ui_panel.x
            for yy in range(10, ui_panel.h - 10, 6):
                pygame.draw.rect(panel_surf, GOLD, pygame.Rect(div_local_x - 1, yy, 3, 3))
            panel_surf.set_alpha(max(0, min(255, int(255 * ui_alpha_mult))))
            screen.blit(panel_surf, ui_panel.topleft)
        else:
            draw_pixel_border_alpha(screen, ui_panel, FELT_DARK, GOLD, fill_alpha=ui_fill_alpha)
            # Golden pixel divider between question area (left) and strike area (right).
            for yy in range(PHASE2_UI_Y + 10, PHASE2_UI_Y + PHASE2_UI_H - 10, 6):
                pygame.draw.rect(screen, GOLD, pygame.Rect(PHASE2_UI_DIV_X - 1, yy, 3, 3))

        nq = len(phase2_questions)
        # Avoid per-text alpha during fade-in (can cause scanline-like artifacts with colorkey text).
        show_ui_text = ui_alpha_mult >= 0.78 or phase2_subphase != "anim"
        if show_ui_text:
            score_txt = rtxt(font_small, f"Score {state.score}", GOLD, bold_px=1)
            screen.blit(score_txt, (PHASE2_UI_X + 10, PHASE2_UI_Y + PHASE2_UI_H - score_txt.get_height() - 6))

        # Question text (top-left, ~90% width).
        if show_ui_text and nq > 0 and phase2_subphase in ("play", "anim") and phase2_q_index < nq:
            q = phase2_questions[phase2_q_index]
            counter = rtxt(
                font_small,
                f"Question {phase2_q_index + 1} of {nq}",
                GOLD,
                bold_px=1,
            )
            counter_x = PHASE2_UI_DIV_X - 10 - counter.get_width()
            screen.blit(counter, (counter_x, PHASE2_UI_Y + 6))

            qy = PHASE2_UI_QUESTION_TEXT_Y - 2
            qtext = str(q.get("question", ""))
            parts = qtext.split("\n")
            for pi, part in enumerate(parts):
                for line in wrap_text(part, PHASE2_UI_LEFT_W - 24):
                    # Top line (context) in red, question line in paper.
                    col = RED if pi == 0 else PAPER
                    qt = rtxt(font_small, line, col, bold_px=0)
                    screen.blit(qt, (PHASE2_UI_QUESTION_TEXT_X, qy))
                    qy += font_small.get_linesize() + 3
                if pi < len(parts) - 1:
                    qy += 2

        # Strike indicator (first wrong answer): red cross on the right 10%.
        if show_ui_text and phase2_strikes >= 1 and phase2_subphase in ("play", "anim"):
            cx, cy = PHASE2_UI_CROSS_CENTER
            L = 13
            pygame.draw.line(screen, RED, (cx - L, cy - L), (cx + L, cy + L), 4)
            pygame.draw.line(screen, RED, (cx - L, cy + L), (cx + L, cy - L), 4)
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
            outer = card_frame_outer_color(card)
            locked_wrong = i in phase2_wrong_locked
            hovered = phase2_hover_i == i and phase2_subphase == "play" and not locked_wrong

            if phase2_subphase == "anim":
                # Fade the whole animated-to-middle card uniformly.
                # Without this, blending differences against the dark UI panel can make it look like only part fades.
                fade_alpha = int(255 * max(0.0, 1.0 - phase2_anim_progress))
                if fade_alpha > 0:
                    pw, ph, pp = _padded_face_wh(card, r.w, r.h)
                    card_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                    draw_epic_rays_on_card_surface(card_surf, card, pw, ph)

                    has_art = card.art and card.art in card_art_surfs
                    if has_art:
                        art_surf = _phase2_get_scaled_art(card.art, r.w, r.h)
                        card_surf.blit(art_surf, (pp, pp))
                    else:
                        draw_pixel_border(card_surf, pygame.Rect(pp, pp, r.w, r.h), PAPER, outer)
                        pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                        card_surf.blit(pip, (pp + 4, pp + 3))

                    draw_pixel_frame(card_surf, pygame.Rect(pp, pp, r.w, r.h), outer, PAPER_DARK)
                    draw_cursed_horns_on_card_surface(card_surf, card, r.w, r.h, ox=pp, oy=pp)

                    card_surf.set_alpha(max(0, min(255, fade_alpha)))
                    screen.blit(card_surf, (r.x - pp, r.y - pp))
                continue

            if hovered:
                # Reuse the original "active card wobble": rotate the whole card.
                angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                lift_y = -4
                wobble_scale = 1.03
                p2w, p2h, p2p = _padded_face_wh(card, r.w, r.h)
                card_surf = pygame.Surface((p2w, p2h), pygame.SRCALPHA)
                draw_epic_rays_on_card_surface(card_surf, card, p2w, p2h)
                if card.art and card.art in card_art_surfs:
                    art_surf = _phase2_get_scaled_art(card.art, r.w, r.h)
                    card_surf.blit(art_surf, (p2p, p2p))
                else:
                    draw_pixel_border(card_surf, pygame.Rect(p2p, p2p, r.w, r.h), PAPER, outer)
                if not (card.art and card.art in card_art_surfs):
                    pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                    card_surf.blit(pip, (p2p + 4, p2p + 3))
                draw_pixel_frame(card_surf, pygame.Rect(p2p, p2p, r.w, r.h), outer, PAPER_DARK)
                draw_cursed_horns_on_card_surface(card_surf, card, r.w, r.h, ox=p2p, oy=p2p)
                rotated = pygame.transform.rotozoom(card_surf, angle, wobble_scale)
                screen.blit(rotated, rotated.get_rect(center=(r.centerx, r.centery + lift_y)))
            else:
                blit_epic_godrays_behind_card_layer(screen, card, r)
                if card.art and card.art in card_art_surfs:
                    art_surf = _phase2_get_scaled_art(card.art, r.w, r.h)
                    screen.blit(art_surf, r.topleft)
                else:
                    draw_pixel_border(screen, r, PAPER, outer)
                    pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                    screen.blit(pip, (r.x + 6, r.y + 5))
                draw_pixel_frame(screen, r, outer, PAPER_DARK)
                blit_cursed_horns_on_screen(screen, card, r)
            if locked_wrong:
                dim = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                # Dark transparent fade for wrong picks (this question only).
                dim.fill((20, 18, 20, 140))
                screen.blit(dim, r.topleft)

        # Played-card "throw & fade" animations.
        for card_idx, start_r, prog, target_center in phase2_play_anims:
            if card_idx < 0 or card_idx >= len(phase2_cards):
                continue
            card = phase2_cards[card_idx]
            outer = card_frame_outer_color(card)

            t = max(0.0, min(1.0, prog))
            ease = _phase2_ease(t)
            arc_h = int(start_r.h * 0.45)
            xc = int(start_r.centerx + (target_center[0] - start_r.centerx) * ease)
            yc = int(start_r.centery + (target_center[1] - start_r.centery) * ease - arc_h * math.sin(math.pi * ease))
            rot = math.sin(math.pi * ease) * 10.0
            pop_scale = 1.0 + 0.08 * math.sin(math.pi * ease)
            # Fade out faster as the card approaches the middle target.
            # (Use linear t so fading isn't delayed by the easing curve.)
            alpha = int(255 * (1.0 - t) ** 2.2)

            # Render the card into a surface once per frame (small N so it's fine).
            tw, th, tp = _padded_face_wh(card, start_r.w, start_r.h)
            base = pygame.Surface((tw, th), pygame.SRCALPHA)
            draw_epic_rays_on_card_surface(base, card, tw, th)
            if card.art and card.art in card_art_surfs:
                art_surf = _phase2_get_scaled_art(card.art, start_r.w, start_r.h)
                base.blit(art_surf, (tp, tp))
            else:
                draw_pixel_border(base, pygame.Rect(tp, tp, start_r.w, start_r.h), PAPER, outer)
            if not (card.art and card.art in card_art_surfs):
                pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                base.blit(pip, (tp + 4, tp + 3))
            draw_pixel_frame(base, pygame.Rect(tp, tp, start_r.w, start_r.h), outer, PAPER_DARK)
            draw_cursed_horns_on_card_surface(base, card, start_r.w, start_r.h, ox=tp, oy=tp)

            # Apply fade by scaling the per-pixel alpha directly.
            # Using surface-wide set_alpha after rotozoom can look non-uniform when
            # the card overlaps semi-transparent UI areas.
            a = max(0, min(255, alpha))
            if a < 255:
                base.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)

            animated = pygame.transform.rotozoom(base, rot, pop_scale)
            screen.blit(animated, animated.get_rect(center=(xc, yc)))

        # Phase 2 hover label: title only.
        if phase2_hover_i is not None and 0 <= phase2_hover_i < len(phase2_cards):
            hc = phase2_cards[phase2_hover_i]
            title = rtxt(font_small, hc.name, PAPER, bold_px=1)
            pad_x, pad_y = 8, 5
            box = pygame.Rect(
                (LOW_W - (title.get_width() + pad_x * 2)) // 2,
                LOW_H - 86,
                title.get_width() + pad_x * 2,
                title.get_height() + pad_y * 2,
            )
            draw_pixel_border_alpha(screen, box, FELT_DARK, GOLD, fill_alpha=220)
            screen.blit(title, (box.x + pad_x, box.y + pad_y))

        # No separate click-through overlay: end transitions auto-advance to game-over page.
        if phase2_subphase == "celebrate":
            if deck_back_card_surf is not None:
                for x, y, _vx, _vy, _spin, rot, scale, alpha in phase2_win_burst:
                    c = pygame.transform.rotozoom(deck_back_card_surf, rot, scale)
                    c.set_alpha(max(0, min(255, int(alpha))))
                    screen.blit(c, c.get_rect(center=(int(x), int(y))))

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
        rarity_color = {"common": pos_c, "rare": BLUE, "epic": EPIC_PURPLE, "cursed": RED}.get(rarity, neutral_c)

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
                    if dragging_hand_idx is not None and i == dragging_hand_idx:
                        continue
                    outer = card_frame_outer_color(c)
                    if i == hidden_hand_index and deck_back_card_surf is not None:
                        screen.blit(deck_back_card_surf, r)
                    elif i in selected:
                        ha = c.art and c.art in card_art_surfs
                        pw, ph, pp = _padded_face_wh(c, r.w, r.h)
                        card_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                        draw_epic_rays_on_card_surface(card_surf, c, pw, ph)
                        if ha:
                            sc = pygame.transform.smoothscale(card_art_surfs[c.art], (r.w, r.h))
                            card_surf.blit(sc, (pp, pp))
                        else:
                            draw_pixel_border(card_surf, pygame.Rect(pp, pp, r.w, r.h), (250, 248, 240), outer)
                        if not ha:
                            pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                            card_surf.blit(pip, (pp + 4, pp + 3))
                        draw_pixel_frame(card_surf, pygame.Rect(pp, pp, r.w, r.h), outer, PAPER_DARK)
                        draw_cursed_horns_on_card_surface(card_surf, c, r.w, r.h, ox=pp, oy=pp)
                        angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                        rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                        screen.blit(rotated, rotated.get_rect(center=r.center))
                    else:
                        ha = c.art and c.art in card_art_surfs
                        blit_epic_godrays_behind_card_layer(screen, c, r)
                        if ha:
                            sc = pygame.transform.smoothscale(card_art_surfs[c.art], (r.w, r.h))
                            screen.blit(sc, r.topleft)
                        else:
                            draw_pixel_border(screen, r, PAPER, outer)
                            pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                            screen.blit(pip, (r.x + 4, r.y + 3))
                        draw_pixel_frame(screen, r, outer, PAPER_DARK)
                        blit_cursed_horns_on_screen(screen, c, r)
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
                outer = card_frame_outer_color(c)
                if dragging_hand_idx is not None and i == dragging_hand_idx:
                    continue
                if i == hidden_hand_index and deck_back_card_surf is not None:
                    screen.blit(deck_back_card_surf, r)
                elif i in selected:
                    ha = c.art and c.art in card_art_surfs
                    pw, ph, pp = _padded_face_wh(c, w, h)
                    card_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                    draw_epic_rays_on_card_surface(card_surf, c, pw, ph)
                    if ha:
                        sc = pygame.transform.smoothscale(card_art_surfs[c.art], (w, h))
                        card_surf.blit(sc, (pp, pp))
                    else:
                        draw_pixel_border(card_surf, pygame.Rect(pp, pp, w, h), (250, 248, 240), outer)
                    if not ha:
                        pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                        card_surf.blit(pip, (pp + 4, pp + 3))
                    draw_pixel_frame(card_surf, pygame.Rect(pp, pp, w, h), outer, PAPER_DARK)
                    draw_cursed_horns_on_card_surface(card_surf, c, w, h, ox=pp, oy=pp)
                    angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                    rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                    screen.blit(rotated, rotated.get_rect(center=r.center))
                else:
                    ha = c.art and c.art in card_art_surfs
                    blit_epic_godrays_behind_card_layer(screen, c, r)
                    if ha:
                        sc = pygame.transform.smoothscale(card_art_surfs[c.art], (r.w, r.h))
                        screen.blit(sc, r.topleft)
                    else:
                        draw_pixel_border(screen, r, PAPER, outer)
                        pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                        screen.blit(pip, (r.x + 4, r.y + 3))
                    draw_pixel_frame(screen, r, outer, PAPER_DARK)
                    blit_cursed_horns_on_screen(screen, c, r)

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
            if dragging_hand_idx is not None and i == dragging_hand_idx:
                continue
            outer = card_frame_outer_color(c)
            inner = PAPER_DARK
            if i == hidden_hand_index and deck_back_card_surf is not None:
                screen.blit(deck_back_card_surf, r)
            elif i in selected:
                ha = c.art and c.art in card_art_surfs
                pw, ph, pp = _padded_face_wh(c, r.w, r.h)
                card_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                draw_epic_rays_on_card_surface(card_surf, c, pw, ph)
                if ha:
                    sc = pygame.transform.smoothscale(card_art_surfs[c.art], (r.w, r.h))
                    card_surf.blit(sc, (pp, pp))
                else:
                    draw_pixel_border(card_surf, pygame.Rect(pp, pp, r.w, r.h), (250, 248, 240), outer)
                if not ha:
                    pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                    card_surf.blit(pip, (pp + 4, pp + 3))
                draw_pixel_frame(card_surf, pygame.Rect(pp, pp, r.w, r.h), outer, inner)
                draw_cursed_horns_on_card_surface(card_surf, c, r.w, r.h, ox=pp, oy=pp)
                angle = math.sin((frame * 0.22) + i * 1.1) * 2.0
                rotated = pygame.transform.rotozoom(card_surf, angle, 1.0)
                screen.blit(rotated, rotated.get_rect(center=r.center))
            else:
                ha = c.art and c.art in card_art_surfs
                blit_epic_godrays_behind_card_layer(screen, c, r)
                if ha:
                    sc = pygame.transform.smoothscale(card_art_surfs[c.art], (r.w, r.h))
                    screen.blit(sc, r.topleft)
                else:
                    draw_pixel_border(screen, r, PAPER, outer)
                    pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                    screen.blit(pip, (r.x + 4, r.y + 3))
                draw_pixel_frame(screen, r, outer, inner)
                blit_cursed_horns_on_screen(screen, c, r)

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
            outer = card_frame_outer_color(card)
            ha = card.art and card.art in card_art_surfs
            blit_epic_godrays_behind_card_layer(screen, card, anim_r)
            if ha:
                sc = pygame.transform.smoothscale(card_art_surfs[card.art], (anim_r.w, anim_r.h))
                screen.blit(sc, anim_r.topleft)
            else:
                draw_pixel_border(screen, anim_r, PAPER, outer)
                pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                screen.blit(pip, (anim_r.x + 4, anim_r.y + 3))
            draw_pixel_frame(screen, anim_r, outer, PAPER_DARK)
            blit_cursed_horns_on_screen(screen, card, anim_r)

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
            outer = card_frame_outer_color(card)
            ha = card.art and card.art in card_art_surfs
            blit_epic_godrays_behind_card_layer(screen, card, anim_r)
            if ha:
                sc = pygame.transform.smoothscale(card_art_surfs[card.art], (anim_r.w, anim_r.h))
                screen.blit(sc, anim_r.topleft)
            else:
                draw_pixel_border(screen, anim_r, PAPER, outer)
                pip = rtxt(font_small, card.suit[0].upper(), card_border_color(card), bold_px=0)
                screen.blit(pip, (anim_r.x + 4, anim_r.y + 3))
            draw_pixel_frame(screen, anim_r, outer, PAPER_DARK)
            blit_cursed_horns_on_screen(screen, card, anim_r)

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
                pkw, pkh, pkp = _padded_face_wh(peek_card, ACTIVE_CARD_W, ACTIVE_CARD_H)
                peek_rect = pygame.Rect(deck_rect.centerx - pkw // 2, deck_rect.y - pkh - 8, pkw, pkh)
                phase = 0.5 + 0.5 * math.sin(frame * 0.08)
                alpha = int(50 + 20 * phase)
                peek_surf = pygame.Surface((pkw, pkh), pygame.SRCALPHA)
                peek_outer = card_frame_outer_color(peek_card)
                pha = peek_card.art and peek_card.art in card_art_surfs
                draw_epic_rays_on_card_surface(peek_surf, peek_card, pkw, pkh)
                if pha:
                    scaled = pygame.transform.smoothscale(card_art_surfs[peek_card.art], (ACTIVE_CARD_W, ACTIVE_CARD_H))
                    peek_surf.blit(scaled, (pkp, pkp))
                else:
                    peek_surf.fill((240, 236, 228, 255), rect=pygame.Rect(pkp, pkp, ACTIVE_CARD_W, ACTIVE_CARD_H))
                    draw_pixel_border(peek_surf, pygame.Rect(pkp, pkp, ACTIVE_CARD_W, ACTIVE_CARD_H), (250, 248, 240), peek_outer)
                if not pha:
                    pip = rtxt(font_tiny, peek_card.suit[0].upper(), card_border_color(peek_card), bold_px=0)
                    peek_surf.blit(pip, (pkp + 2, pkp + 2))
                draw_pixel_frame(peek_surf, pygame.Rect(pkp, pkp, ACTIVE_CARD_W, ACTIVE_CARD_H), peek_outer, PAPER_DARK)
                draw_cursed_horns_on_card_surface(peek_surf, peek_card, ACTIVE_CARD_W, ACTIVE_CARD_H, ox=pkp, oy=pkp)
                peek_surf.set_alpha(alpha)
                screen.blit(peek_surf, peek_rect)

            # Red warning: flash red mask + single-line compact text above deck
            if deck_warning_frames > 0:
                mask_inset = 4
                pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * (deck_warning_frames / 25))
                red_alpha = int(100 * pulse + 100)
                deck_mask = pygame.Surface((CARD_W - mask_inset * 2, CARD_H - mask_inset * 2), pygame.SRCALPHA)
                deck_mask.fill((220, 72, 72, red_alpha))
                screen.blit(deck_mask, (deck_rect.x + mask_inset, deck_rect.y + mask_inset))
                warn_text = "Max 5 cards at hand" if deck_warning_hand_full else "No cards to draw."
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
        # Objective block: scenario-specific *setting/explanation* (content.py line 2),
        # with "Objective:" removed (we only show the scenario name above).
        _line1, setting_line, _line3 = get_scenario_objective_lines(state.scenario_key)
        objective_text = setting_line

        title = rtxt(font_big, "DEPLOYMENT SCENARIO", GOLD)
        screen.blit(title, ((LOW_W - title.get_width()) // 2, 24))
        sub = rtxt(font_small, scenario_name, PAPER)
        screen.blit(sub, ((LOW_W - sub.get_width()) // 2, 52))

        # Objective text centered under the scenario name.
        # Requirements/description block starts slightly below the scenario title.
        objective_y = 76 + 15
        objective_step = font_small.get_linesize() + 4
        # Requirements label (red), inserted between scenario name and description.
        req_label = rtxt(font_small, "Requirements:", RED, bold_px=1)
        screen.blit(req_label, ((LOW_W - req_label.get_width()) // 2, objective_y))
        objective_y += objective_step
        for line in wrap_text(objective_text, LOW_W - 28):
            rr = rtxt(font_small, line, (210, 208, 198), bold_px=0)
            screen.blit(rr, ((LOW_W - rr.get_width()) // 2, objective_y))
            objective_y += objective_step

        # Gap between the scenario subtitle block and the "HOW TO PLAY" title.
        objective_y += 50

        # Fade-in timing: HOW TO PLAY section starts 1.5s after the page opens.
        elapsed_ms = 0
        if intro_start_ms is not None:
            elapsed_ms = max(0, pygame.time.get_ticks() - intro_start_ms)
        # Fade-in timing: start a bit earlier (requested shorter total effect).
        fade_delay_ms = 800
        fade_duration_ms = 500
        how_mult = 0.0
        if elapsed_ms > fade_delay_ms:
            how_mult = min(1.0, (elapsed_ms - fade_delay_ms) / float(fade_duration_ms))
        how_alpha = int(255 * how_mult)

        how_title_surf = rtxt(font_big, "HOW TO PLAY", GOLD)
        if how_alpha < 255:
            how_title_surf.set_alpha(how_alpha)
        screen.blit(how_title_surf, ((LOW_W - how_title_surf.get_width()) // 2, objective_y))

        # Split the remaining area into two vertical halves.
        split_top = objective_y + how_title_surf.get_height() + 10
        usable_x0 = 20
        usable_x1 = LOW_W - 8
        usable_w = max(1, usable_x1 - usable_x0)
        half_w = usable_w // 2
        left_x = usable_x0
        right_x = usable_x0 + half_w
        block_inset_x = min(12, max(6, half_w // 12))

        line_color = (200, 198, 188)
        phase_title_color = PAPER
        active_color = GOLD

        phase1_inner_shift_x = 8
        # Phase 2 inner lines: extra right shift for readability.
        phase2_inner_shift_x = 56

        def _blit_left_line(x: int, yy: int, s: str, *, bold: bool = False, col: Tuple[int, int, int] = line_color) -> pygame.Surface:
            surf = rtxt(font_tiny, s, col, bold_px=1 if bold else 0)
            if how_alpha < 255:
                surf.set_alpha(how_alpha)
            screen.blit(surf, (x, yy))
            return surf

        def _blit_phase_title(prefix: str, rest: str, center_x: int, y: int) -> None:
            # Prefix bolded (“PHASE 1:” / “PHASE 2:”).
            sp = rtxt(font_small, prefix, phase_title_color, bold_px=1)
            sr = rtxt(font_small, rest, phase_title_color, bold_px=0)
            if how_alpha < 255:
                sp.set_alpha(how_alpha)
                sr.set_alpha(how_alpha)
            total_w = sp.get_width() + sr.get_width()
            sx = center_x - total_w // 2
            screen.blit(sp, (sx, y))
            screen.blit(sr, (sx + sp.get_width(), y))

        line_step_tiny = font_tiny.get_linesize() + 3

        # --- Phase 1 ---
        phase1_center_x = left_x + half_w // 2
        _blit_phase_title("PHASE 1:", " Build", phase1_center_x, split_top)

        p1_title_h = font_small.get_height() if hasattr(font_small, "get_height") else font_small.get_linesize()
        p1_y = split_top + (rtxt(font_small, "PHASE 1: Build", phase_title_color, bold_px=0)).get_height() + 8
        # Draw cards from DECK: only the word "DECK" is yellow + bold like ACTIVE.
        x_cursor = left_x + block_inset_x + phase1_inner_shift_x
        s1 = _blit_left_line(x_cursor, p1_y, "Draw cards from ", bold=False, col=line_color)
        x_cursor += s1.get_width()
        s2 = _blit_left_line(x_cursor, p1_y, "DECK", bold=True, col=active_color)
        x_cursor += s2.get_width()
        _blit_left_line(x_cursor, p1_y, ". Max 5 in hand.", bold=False, col=line_color)
        p1_y += line_step_tiny

        # Fill ACTIVE slots to shape your stats.
        x_cursor = left_x + block_inset_x + phase1_inner_shift_x
        prefix = _blit_left_line(x_cursor, p1_y, "Fill ")
        x_cursor += prefix.get_width()
        active = _blit_left_line(x_cursor, p1_y, "ACTIVE", bold=True, col=active_color)
        x_cursor += active.get_width()
        _blit_left_line(x_cursor, p1_y, " slots to shape your stats.")
        p1_y += line_step_tiny

        # Phase 1 line: only the words "scenario requirements" are red.
        _x_req = left_x + block_inset_x + phase1_inner_shift_x
        _meet_s = rtxt(font_tiny, "Meet ", line_color, bold_px=0)
        _req_s = rtxt(font_tiny, "scenario requirements", RED, bold_px=0)
        _suf_s = rtxt(font_tiny, " before Round 10.", line_color, bold_px=0)
        if how_alpha < 255:
            _meet_s.set_alpha(how_alpha)
            _req_s.set_alpha(how_alpha)
            _suf_s.set_alpha(how_alpha)
        screen.blit(_meet_s, (_x_req, p1_y))
        _x_req += _meet_s.get_width()
        screen.blit(_req_s, (_x_req, p1_y))
        _x_req += _req_s.get_width()
        screen.blit(_suf_s, (_x_req, p1_y))

        # --- Phase 2 ---
        phase2_center_x = right_x + half_w // 2
        _blit_phase_title("PHASE 2:", " Action", phase2_center_x, split_top)

        p2_y = split_top + (rtxt(font_small, "PHASE 2: Action", phase_title_color, bold_px=0)).get_height() + 8
        # ACTIVE cards become your hand.
        x_cursor = right_x + block_inset_x + phase2_inner_shift_x
        active = _blit_left_line(x_cursor, p2_y, "ACTIVE", bold=True, col=active_color)
        x_cursor += active.get_width()
        _blit_left_line(x_cursor, p2_y, " cards become your hand.")
        p2_y += line_step_tiny

        _blit_left_line(right_x + block_inset_x + phase2_inner_shift_x, p2_y, "Respond to ethical scenarios.")
        p2_y += line_step_tiny

        # 4/5 correct answers to win.
        x_cursor = right_x + block_inset_x + phase2_inner_shift_x
        n_b = _blit_left_line(x_cursor, p2_y, "4/5", bold=True, col=RED)
        x_cursor += n_b.get_width()
        _blit_left_line(x_cursor, p2_y, " correct answers to win.")

        # --- Intro tutorial mini-animations (cursor/cards) ---
        # These run under the Phase 1/Phase 2 text blocks and loop with a 1s delay.
        # No sound effects are used.
        if cursor_raw is not None or question_mark_raw is not None:
            t_intro = elapsed_ms

            def _clamp01(v: float) -> float:
                return max(0.0, min(1.0, v))

            def _lerp(a: float, b: float, u: float) -> float:
                return a + (b - a) * u

            # Small graphics size (keeps everything side-by-side under phases).
            mini_card_w = int(max(52, min(72, half_w * 0.22)))
            mini_card_h = int(max(52, min(95, mini_card_w * (CARD_H / float(CARD_W)))))
            gap_small = max(4, int(mini_card_w * 0.08))
            # Bigger inter-group spacing: decks on left, 2 hand cards on right.
            gap_big = gap_small + 28

            cursor_w = int(max(18, min(34, mini_card_w * 0.55)))
            cursor_h = int(cursor_w * (cursor_raw.get_height() / float(cursor_raw.get_width()))) if cursor_raw is not None else cursor_w

            q_w = int(max(16, min(30, mini_card_w * 0.45)))
            q_h = int(q_w * (question_mark_raw.get_height() / float(question_mark_raw.get_width()))) if question_mark_raw is not None else q_w

            def _get_scaled_from_cache(raw: Optional[pygame.Surface], cache: Dict[Tuple[int, int], pygame.Surface], w: int, h: int) -> Optional[pygame.Surface]:
                if raw is None:
                    return None
                key = (w, h)
                hit = cache.get(key)
                if hit is not None:
                    return hit
                try:
                    scaled = pygame.transform.smoothscale(raw, (w, h))
                except Exception:
                    scaled = None
                if scaled is not None:
                    cache[key] = scaled
                return cache.get(key)

            cursor_mini = _get_scaled_from_cache(cursor_raw, _intro_cursor_scaled_cache, cursor_w, cursor_h)
            q_mini = _get_scaled_from_cache(question_mark_raw, _intro_question_scaled_cache, q_w, q_h)

            def _get_mini_card_face(art_key: Optional[str]) -> pygame.Surface:
                # Cache the non-faded face (alpha handled by copy + set_alpha).
                key = (art_key or "__none__", mini_card_w, mini_card_h)
                hit = _intro_mini_card_face_cache.get(key)
                if hit is not None:
                    return hit
                surf = pygame.Surface((mini_card_w, mini_card_h), pygame.SRCALPHA)
                # Base card face.
                surf.fill((*PAPER, 255))
                draw_pixel_frame(surf, pygame.Rect(0, 0, mini_card_w, mini_card_h), GOLD, PAPER_DARK)
                if art_key and art_key in card_art_surfs:
                    art = pygame.transform.smoothscale(card_art_surfs[art_key], (mini_card_w - 4, mini_card_h - 4))
                    surf.blit(art, (2, 2))
                _intro_mini_card_face_cache[key] = surf
                return surf

            # Mini deck (front/back stand-in).
            deck_w, deck_h = mini_card_w, mini_card_h
            if deck_back_card_surf is not None:
                deck_key = (deck_w, deck_h)
                deck_mini = _intro_mini_deck_cache.get(deck_key)
                if deck_mini is None:
                    deck_mini = pygame.transform.smoothscale(deck_back_card_surf, (deck_w, deck_h))
                    _intro_mini_deck_cache[deck_key] = deck_mini
            else:
                deck_mini = None

            # Vertical anchors under the text blocks.
            phase1_line_bottom = p1_y + line_step_tiny + 10
            phase2_line_bottom = p2_y + line_step_tiny + 16

            # Phase 1 mini group positions (deck + 2 cards on the left side).
            group_center_x1 = left_x + half_w // 2
            group_w1 = deck_w + gap_big + mini_card_w + gap_small + mini_card_w
            group_left_x1 = group_center_x1 - group_w1 // 2
            # Layout: top row = 2 cards, second row = deck (under them).
            # Shift cards left + down so they don't interfere with the phase text.
            # Deck movement: 15px left, 35px down (relative to current layout).
            deck_y1 = phase1_line_bottom + 73  # 38 + 35
            # Hand/card movement: +20px down.
            # Align hand cards with the decks/ACTIVE slot (same horizontal axis).
            cards_top_y1 = deck_y1
            card1_x1 = left_x + block_inset_x + 20
            card2_x1 = card1_x1 + mini_card_w + gap_small
            card1_y1 = cards_top_y1
            card2_y1 = cards_top_y1
            # Deck is slightly shifted left to create extra margin before the first drawn card.
            deck_x1 = (card1_x1 + card2_x1 + mini_card_w) // 2 - deck_w // 2 - (gap_small + 8 + 15) + 35

            # Phase 1 active slots (two slots, cursor drags left card into left slot).
            # Bring active slots up so they don't run out of the window.
            # ACTIVE movement: up 70px for fit, then extra 15px up.
            slot_y1 = deck_y1
            slot_gap_x1 = gap_small * 2
            slot_w_total1 = mini_card_w * 2 + slot_gap_x1
            # ACTIVE movement: +5px right.
            # Move ACTIVE (and the mini DECK sitting on top of it) to the right by +95px total.
            slot1_x1 = left_x + block_inset_x + 15 + 50 + 45
            slot2_x1 = slot1_x1 + mini_card_w + slot_gap_x1
            slot_h1 = mini_card_h

            # Place the mini DECK exactly where the ACTIVE slot will appear.
            deck_x1 = slot1_x1
            deck_y1 = slot_y1

            # Hand cards on the right, with a larger gap from the decks than between the hand cards.
            card1_x1 = deck_x1 + deck_w + gap_big
            card2_x1 = card1_x1 + mini_card_w + gap_small
            card1_y1 = deck_y1
            card2_y1 = deck_y1

            # Shift the entire Phase 1 mini-animation area into its final position.
            # (All cursor/cards/decks/active anchors are derived from these.)
            phase1_mini_dx = -95
            phase1_mini_dy = -35
            deck_x1 += phase1_mini_dx
            deck_y1 += phase1_mini_dy
            slot1_x1 += phase1_mini_dx
            slot2_x1 += phase1_mini_dx
            slot_y1 += phase1_mini_dy
            card1_x1 += phase1_mini_dx
            card2_x1 += phase1_mini_dx
            card1_y1 += phase1_mini_dy
            card2_y1 += phase1_mini_dy

            card_face_a = _get_mini_card_face(_intro_demo_card_key_1)
            card_face_b = _get_mini_card_face(_intro_demo_card_key_2)

            # Cursor bubble positioning.
            def _blit_alpha(surf: pygame.Surface, x: int, y: int, alpha: int) -> None:
                if alpha <= 0:
                    return
                if alpha >= 255:
                    screen.blit(surf, (x, y))
                    return
                # Multiply alpha into the surface to avoid fringe/black-box artifacts
                # that can happen when using set_alpha on certain scaled WEBP assets.
                cp = surf.copy()
                cp.fill((255, 255, 255, max(0, min(255, alpha))), special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(cp, (x, y))

            def _slot_surf(x: int, y: int, alpha: int) -> None:
                if alpha <= 0:
                    return
                slot = pygame.Surface((mini_card_w, mini_card_h), pygame.SRCALPHA)
                slot.fill((*FELT_DARK, 255))
                draw_pixel_border(slot, pygame.Rect(0, 0, mini_card_w, mini_card_h), FELT_DARK, GOLD)
                _blit_alpha(slot, x, y, alpha)

            # Phase 2 positions (active slots + question mark + cursor/click).
            group_center_x2 = right_x + half_w // 2
            slot_w_total2 = mini_card_w * 2 + gap_small * 2
            slot_group_left_x2 = group_center_x2 - slot_w_total2 // 2
            slot1_x2 = slot_group_left_x2
            slot2_x2 = slot1_x2 + mini_card_w + gap_small * 2
            # Move the whole mini hand/cursor area up by ~10px.
            slot_y2 = phase2_line_bottom + 30
            slot_w2 = mini_card_w

            # Timing: start after HOW TO PLAY finishes fading in.
            anim1_start = fade_delay_ms + fade_duration_ms
            anim1_seq = 6900
            anim1_pause = 1000
            anim1_cycle = anim1_seq + anim1_pause
            anim1_fade_out_start = 6300

            # Start Phase 2 tutorial at the same time as Phase 1.
            anim2_start = anim1_start
            anim2_seq = 5100
            anim2_pause = 1000
            anim2_cycle = anim2_seq + anim2_pause

            # --- Animation 1 (Phase 1) ---
            t1 = t_intro - anim1_start
            if t1 >= 0:
                t1m = t1 % anim1_cycle
                if t1m < anim1_seq:
                    # Cursor visuals were previously too high: push down to match the intended click target.
                    cursor_y_offset = 40
                    u = t1m / float(anim1_seq)
                    global_out = 1.0
                    if t1m > anim1_fade_out_start:
                        global_out = 1.0 - _clamp01((t1m - anim1_fade_out_start) / float(anim1_seq - anim1_fade_out_start))
                    global_out_a = int(255 * global_out)

                    deck_in_end = 1200
                    deck_hold_end = 2550
                    deck_out_end = 3450

                    def _piece_alpha(t: float, a: float, b: float) -> float:
                        return _clamp01((t - a) / float(b - a)) if b > a else 1.0

                    deck_a = 0.0
                    if t1m < deck_in_end:
                        deck_a = _piece_alpha(t1m, 0, deck_in_end)
                    elif t1m < deck_hold_end:
                        deck_a = 1.0
                    elif t1m < deck_out_end:
                        deck_a = 1.0 - _clamp01((t1m - deck_hold_end) / float(deck_out_end - deck_hold_end))
                    else:
                        deck_a = 0.0
                    deck_alpha = int(deck_a * global_out_a)

                    # Cursor fades in and performs the "click deck" motion.
                    cur_a = 0.0
                    if t1m < 750:
                        cur_a = 0.0
                    elif t1m < 1350:
                        cur_a = _piece_alpha(t1m, 750, 1350)
                    else:
                        cur_a = 1.0
                    cursor_alpha = int(cur_a * global_out_a)

                    # Cards fade in after the click and slide into place.
                    cards_in_start = 2400
                    cards_in_end = 3100
                    cards_a = 0.0
                    if t1m < cards_in_start:
                        cards_a = 0.0
                    elif t1m < cards_in_end:
                        cards_a = _clamp01((t1m - cards_in_start) / float(cards_in_end - cards_in_start))
                    else:
                        cards_a = 1.0

                    card1_alpha = int(cards_a * global_out_a)
                    card2_alpha = int(cards_a * global_out_a)

                    # Active slots fade in after deck fades out.
                    # Start ACTIVE after the deck is fully faded away.
                    active_in_start = 3600
                    active_in_end = 3900
                    active_a = 0.0
                    if t1m < active_in_start:
                        active_a = 0.0
                    elif t1m < active_in_end:
                        active_a = _clamp01((t1m - active_in_start) / float(active_in_end - active_in_start))
                    else:
                        active_a = 1.0
                    active_alpha = int(active_a * global_out_a)

                    # Drag card1 into slot1.
                    drag_start = 3900
                    drag_end = 5700
                    drag_u = _clamp01((t1m - drag_start) / float(drag_end - drag_start)) if t1m >= drag_start else 0.0
                    card1_x = int(_lerp(card1_x1, slot1_x1, drag_u))
                    card1_y = int(_lerp(card1_y1, slot_y1, drag_u))

                    # Cursor follows the deck first, then follows the dragged card.
                    deck_cx = deck_x1 + deck_w // 2
                    deck_cy = deck_y1 + deck_h // 2
                    deck_anchor_x = deck_cx - cursor_w // 2
                    deck_anchor_y = deck_y1 - cursor_h - 10 + cursor_y_offset
                    # Cursor should track the *drawn* card position during the mini "cards in" slide,
                    # not the final drag position (to avoid apparent cursor teleport/misalignment).
                    x_start = deck_x1 + deck_w - 8
                    if t1m < cards_in_start:
                        _slide_u_anchor = 0.0
                    elif t1m < cards_in_end:
                        _slide_u_anchor = _clamp01((t1m - cards_in_start) / float(cards_in_end - cards_in_start))
                    else:
                        _slide_u_anchor = 1.0
                    card_draw_x = int(_lerp(x_start, card1_x1, _slide_u_anchor))
                    card_draw_y = card1_y1
                    # When drag begins, use the dragged position.
                    if t1m >= drag_start:
                        card_draw_x = card1_x
                        card_draw_y = card1_y
                    card_anchor_x = card_draw_x + mini_card_w // 2 - cursor_w // 2
                    card_anchor_y = card_draw_y - cursor_h - 4 + cursor_y_offset
                    cursor_spawn_x = deck_anchor_x - 25
                    cursor_spawn_y = deck_anchor_y + 50
                    cursor_draw_x = cursor_spawn_x
                    cursor_draw_y = cursor_spawn_y

                    # Deck click timing:
                    # - cursor fades in until ~1350ms
                    # - click begins 0.3s later (~1650ms)
                    # Cursor should start clicking the deck 0.5s later.
                    click_start = 2150
                    click_end = 2750
                    # Cursor moves smoothly (no teleport) from spawn -> deck -> card -> drag.
                    if cursor_mini is not None:
                        if t1m < click_start:
                            # Smoothly move from spawn to deck before clicking.
                            pre_move_start = 750.0
                            if click_start > pre_move_start:
                                u_pre = _clamp01((t1m - pre_move_start) / float(click_start - pre_move_start))
                            else:
                                u_pre = 1.0
                            cursor_draw_x = int(_lerp(cursor_spawn_x, deck_anchor_x, u_pre))
                            cursor_draw_y = int(_lerp(cursor_spawn_y, deck_anchor_y, u_pre))
                        elif t1m < click_end:
                            click_u = _clamp01((t1m - click_start) / float(click_end - click_start))
                            bob = int(8 * (1.0 - abs(2.0 * click_u - 1.0)))
                            cursor_draw_x = deck_anchor_x
                            cursor_draw_y = deck_anchor_y + bob
                        elif t1m < drag_start:
                            move_u = _clamp01((t1m - click_end) / float(drag_start - click_end))
                            cursor_draw_x = int(_lerp(deck_anchor_x, card_anchor_x, move_u))
                            cursor_draw_y = int(_lerp(deck_anchor_y, card_anchor_y, move_u))
                        else:
                            cursor_draw_x = card_anchor_x
                            cursor_draw_y = card_anchor_y

                    # Draw order: deck -> cards -> active slots -> cursor -> drag card placement.
                    if deck_alpha > 0:
                        dl = rtxt(font_tiny, "DECK", GOLD, bold_px=1)
                        dl.set_alpha(max(0, min(255, deck_alpha)))
                        screen.blit(dl, (deck_x1 + deck_w // 2 - dl.get_width() // 2, deck_y1 - dl.get_height() - 6))
                    if deck_mini is not None and deck_alpha > 0:
                        _blit_alpha(deck_mini, deck_x1, deck_y1, deck_alpha)
                    # Active slot (behind the dragged card as the card moves into it).
                    if active_alpha > 0:
                        al = rtxt(font_tiny, "ACTIVE", GOLD, bold_px=1)
                        al.set_alpha(max(0, min(255, active_alpha)))
                        screen.blit(al, (slot1_x1 + mini_card_w // 2 - al.get_width() // 2, slot_y1 - al.get_height() - 6))
                        _slot_surf(slot1_x1, slot_y1, active_alpha)

                    # Card2 stays to the right of deck.
                    if card2_alpha > 0:
                        # Slide during cards-in.
                        if t1m < cards_in_start:
                            slide_u = 0.0
                        elif t1m < cards_in_end:
                            slide_u = _clamp01((t1m - cards_in_start) / float(cards_in_end - cards_in_start))
                        else:
                            slide_u = 1.0
                        x_start = deck_x1 + deck_w - 8
                        x_now = int(_lerp(x_start, card2_x1, slide_u))
                        _blit_alpha(card_face_b, x_now, card2_y1, card2_alpha)

                    # Card1 (the one to drag) moves continuously.
                    if card1_alpha > 0:
                        # During "cards drawn" it slides into place, then continues to drag.
                        if t1m < cards_in_start:
                            slide_u = 0.0
                        elif t1m < cards_in_end:
                            slide_u = _clamp01((t1m - cards_in_start) / float(cards_in_end - cards_in_start))
                        else:
                            slide_u = 1.0
                        x_start = deck_x1 + deck_w - 8
                        x_place = int(_lerp(x_start, card1_x1, slide_u))
                        y_place = card1_y1
                        # If dragging already started, override with drag positions.
                        if t1m >= drag_start:
                            x_place = card1_x
                            y_place = card1_y
                        # Shake the card when it settles into the active slot.
                        shake_u = 0.0
                        if t1m >= drag_end:
                            shake_u = _clamp01((t1m - drag_end) / 1800.0)
                        if shake_u > 0:
                            ang = math.sin((frame * 0.22) + 0.7) * (2.5 * shake_u)
                            sc = 1.0 + 0.04 * shake_u * math.sin(frame * 0.15 + 1.1)
                            rotated = pygame.transform.rotozoom(card_face_a, ang, sc)
                            cx = x_place + mini_card_w // 2
                            cy = y_place + mini_card_h // 2
                            r = rotated.get_rect(center=(cx, cy))
                            _blit_alpha(rotated, r.x, r.y, card1_alpha)
                        else:
                            _blit_alpha(card_face_a, x_place, y_place, card1_alpha)

                    if cursor_mini is not None and cursor_alpha > 0:
                        _blit_alpha(cursor_mini, cursor_draw_x, cursor_draw_y, cursor_alpha)

            # --- Animation 2 (Phase 2) ---
            t2 = t_intro - anim2_start
            if t2 >= 0:
                t2m = t2 % anim2_cycle
                if t2m < anim2_seq:
                    # Fade out everything at the end of the sequence.
                    fade_out_start = 4800
                    fade_out_dur = max(1, anim2_seq - fade_out_start)
                    global_out = 1.0
                    if t2m > fade_out_start:
                        global_out = 1.0 - _clamp01((t2m - fade_out_start) / float(fade_out_dur))
                    global_out_a = int(255 * global_out)

                    # Active slots with already-cards fade in.
                    active_in_start = 0
                    active_in_end = 1500
                    active_a = _clamp01((t2m - active_in_start) / float(active_in_end - active_in_start)) if t2m > active_in_start else 0.0
                    active_alpha = int(active_a * global_out_a)

                    # Question mark fades in after active cards.
                    q_alpha = 0
                    if q_mini is not None:
                        q_in_start = 1200
                        q_in_end = 2100
                        q_a = 0.0
                        if t2m < q_in_start:
                            q_a = 0.0
                        elif t2m < q_in_end:
                            q_a = _clamp01((t2m - q_in_start) / float(q_in_end - q_in_start))
                        else:
                            q_a = 1.0
                        q_alpha = int(q_a * global_out_a)

                    # Cursor fades in after question mark.
                    # Cursor appears after question mark dots.
                    cur_in_start = 3350
                    cur_in_end = 3650
                    cur_a = 0.0
                    if t2m < cur_in_start:
                        cur_a = 0.0
                    elif t2m < cur_in_end:
                        cur_a = _clamp01((t2m - cur_in_start) / float(cur_in_end - cur_in_start))
                    else:
                        cur_a = 1.0
                    cursor_alpha = int(cur_a * global_out_a)

                    # Click target is the left active card.
                    # Click first, then the card starts moving toward the question mark.
                    card_play_start = 4550
                    card_play_end = 4950
                    play_u = _clamp01((t2m - card_play_start) / float(card_play_end - card_play_start)) if t2m >= card_play_start else 0.0

                    # Move clicked card up and fade it out.
                    clicked_card_alpha = int(active_alpha * max(0.0, 1.0 - play_u))
                    # Move clicked card toward the question mark as it fades.
                    # Question mark should be ~5px to the right.
                    q_target_x = slot2_x2 + mini_card_w - q_w // 2 + 11
                    q_target_y = slot_y2 - q_h - 6 - 15
                    clicked_card_x = int(_lerp(slot1_x2, q_target_x + q_w // 2 - mini_card_w // 2, play_u))
                    clicked_card_y = int(_lerp(slot_y2, q_target_y + q_h // 2 - mini_card_h // 2, play_u))
                    # Question mark fades away with the clicked card, but still keeps
                    # its own fade-in. So we clamp it down as the clicked card fades.
                    q_alpha = min(q_alpha, clicked_card_alpha)

                    # Cursor motion: spawn near the destination card bottom-left,
                    # then take a small arched move onto the card (about 15px up, 5px right),
                    # and finally do a short click dip (~0.3s after arrival).
                    target_cx = slot1_x2 + mini_card_w // 2
                    # Cursor "resting" position above the card (matches the baseline look).
                    dest_x = target_cx - cursor_w // 2
                    dest_y = slot_y2 - cursor_h - 6 + 40

                    # Spawn is slightly away from the card bottom-left.
                    spawn_x = dest_x - 5
                    spawn_y = dest_y + 15

                    # Move the cursor into position before clicking (card moves later).
                    move_start = cur_in_end
                    move_end = 3950  # cursor arrival time
                    if t2m < move_start:
                        cursor_x = spawn_x
                        cursor_y = spawn_y
                    elif t2m < move_end:
                        u = _clamp01((t2m - move_start) / float(move_end - move_start))
                        arch_u = math.sin(math.pi * u)  # 0 at endpoints, 1 in the middle
                        cursor_x = int(_lerp(spawn_x, dest_x, u) + 5 * arch_u)
                        cursor_y_lin = int(_lerp(spawn_y, dest_y, u))
                        cursor_y = cursor_y_lin - int(15 * arch_u)
                    else:
                        cursor_x = dest_x
                        cursor_y = dest_y

                    # Click dip starts after the cursor is correctly positioned.
                    dip_start = 4250
                    dip_end = 4550
                    if t2m >= dip_start:
                        v = _clamp01((t2m - dip_start) / float(dip_end - dip_start)) if dip_end > dip_start else 1.0
                        dip_amp = 7
                        # Peaked down then returns.
                        dip = dip_amp * (1.0 - abs(2.0 * v - 1.0))
                        cursor_y = int(dest_y + dip)

                    # Draw order: active cards -> question mark -> cursor -> play movement.
                    if active_alpha > 0:
                        # Title above the mini active hand.
                        h = rtxt(font_tiny, "HAND", GOLD, bold_px=1)
                        h.set_alpha(max(0, min(255, active_alpha)))
                        hand_group_w = mini_card_w * 2 + gap_small * 2
                        hand_group_cx = (slot1_x2 + slot2_x2 + mini_card_w) // 2
                        screen.blit(h, (hand_group_cx - h.get_width() // 2, slot_y2 - h.get_height() - 6))
                        # Right card stays in place until the sequence fades away.
                        _blit_alpha(card_face_a, slot2_x2, slot_y2, active_alpha)
                        # Left card (clicked) moves toward question mark and fades out.
                        if clicked_card_alpha > 0:
                            # Mini grow-click effect during cursor click.
                            pop_start = 4250
                            pop_end = pop_start + 220
                            pop_u = _clamp01((t2m - pop_start) / float(pop_end - pop_start)) if t2m >= pop_start else 0.0
                            pop_scale = 1.0 + 0.15 * math.sin(math.pi * pop_u) if pop_u > 0 else 1.0
                            rotated = pygame.transform.rotozoom(card_face_b, 0.0, pop_scale)
                            rc = rotated.get_rect(
                                center=(clicked_card_x + mini_card_w // 2, clicked_card_y + mini_card_h // 2)
                            )
                            _blit_alpha(rotated, rc.x, rc.y, clicked_card_alpha)

                    if q_mini is not None and q_alpha > 0:
                        _blit_alpha(q_mini, q_target_x, q_target_y, q_alpha)

                        # Three dots: appear next to the question mark, one-by-one every 0.4s.
                        dot_base = q_in_end + 100
                        dot_interval = 400
                        dot_fade = 250
                        dot_size = 4
                        dot_y = q_target_y + q_h // 2 - dot_size // 2
                        dot_x0 = q_target_x + q_w + 6
                        for di in range(3):
                            ds = dot_base + di * dot_interval
                            de = ds + dot_fade
                            if t2m < ds:
                                on = 0.0
                            elif t2m < de:
                                on = (t2m - ds) / float(dot_fade)
                            else:
                                on = 1.0
                            if on <= 0.0:
                                continue
                            a = int(q_alpha * on)
                            if a <= 0:
                                continue
                            dot_s = pygame.Surface((dot_size, dot_size), pygame.SRCALPHA)
                            pygame.draw.circle(
                                dot_s,
                                (*RED, a),
                                (dot_size // 2, dot_size // 2),
                                dot_size // 2,
                            )
                            _blit_alpha(dot_s, dot_x0 + di * (dot_size + 3), dot_y, a)

                    if cursor_mini is not None and cursor_alpha > 0:
                        # Cursor click pop (sync with the card grow-click).
                        pop_start = 4250
                        pop_end = pop_start + 220
                        pop_u = _clamp01((t2m - pop_start) / float(pop_end - pop_start)) if t2m >= pop_start else 0.0
                        pop_scale = 1.0 + 0.10 * math.sin(math.pi * pop_u) if pop_u > 0 else 1.0
                        cursor_draw = cursor_mini if pop_scale == 1.0 else pygame.transform.rotozoom(cursor_mini, 0.0, pop_scale)
                        rc = cursor_draw.get_rect(center=(cursor_x + cursor_w // 2, cursor_y + cursor_h // 2))
                        _blit_alpha(cursor_draw, rc.x, rc.y, cursor_alpha)

        # Bottom-right prompt: always visible on intro screen.
        start_tip = rtxt(font_small, "Click to start. ESC to quit.", GOLD)
        screen.blit(start_tip, (LOW_W - start_tip.get_width() - 14, LOW_H - 30))

    def draw_menu() -> None:
        nonlocal menu_play_rect, menu_credits_rect, menu_settings_rect, menu_admin_rect
        draw_tiled_background()
        draw_pixel_border(screen, pygame.Rect(8, 8, LOW_W - 16, LOW_H - 16), FELT_DARK, GOLD)
        menu_admin_rect = None  # hide by default unless dev-enabled
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
        esc = rtxt(font_small, "ESC to quit.", GOLD, bold_px=1)
        screen.blit(esc, (LOW_W - esc.get_width() - 20, LOW_H - 30))

        if ADMIN_PHASE2_ENABLED:
            # Admin Phase 2 test button (dev only)
            admin_y = set_y + btn_h + 12
            menu_admin_rect = pygame.Rect(cx - btn_w // 2, admin_y, btn_w, btn_h)
            draw_pixel_border(screen, menu_admin_rect, GOLD, (80, 70, 40))
            atxt = rtxt(font_small, "Admin Phase2", INK)
            screen.blit(
                atxt,
                (menu_admin_rect.centerx - atxt.get_width() // 2, menu_admin_rect.centery - atxt.get_height() // 2),
            )

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
        if author2_logo_surf is not None:
            # Gentle "breathing" scale pulse — distinct from author1's vertical bob; no rotation.
            _breathe = 0.96 + 0.04 * (0.5 + 0.5 * math.sin(frame * 0.065 + 0.8))
            _w2 = max(1, int(author2_logo_surf.get_width() * _breathe))
            _h2 = max(1, int(author2_logo_surf.get_height() * _breathe))
            _a2_scaled = pygame.transform.smoothscale(author2_logo_surf, (_w2, _h2))
            screen.blit(
                _a2_scaled,
                (br_cx - _a2_scaled.get_width() // 2, br_cy - _a2_scaled.get_height() // 2),
            )
        else:
            screen.blit(logo_placeholder, (br_cx - logo_placeholder.get_width() // 2, br_cy - logo_placeholder.get_height() // 2))
        # Text blocks: centered name over a bulleted contribution list.
        right_center_x = 8 + half_w + (half_w // 2)
        left_center_x = 8 + (half_w // 2)

        # Top-right: author 1
        a1_top_y = 8 + 14
        author1_name = rtxt(font_big, "Kayra", GOLD, bold_px=1)
        screen.blit(author1_name, (right_center_x - author1_name.get_width() // 2, a1_top_y))

        contrib1_lines = ["-game mechanics", "-development", "-management", "-idea"]
        contrib_font = font_small
        line_step = contrib_font.get_linesize() + 3
        c1_y = a1_top_y + author1_name.get_height() + 8
        for line in contrib1_lines:
            cs = rtxt(contrib_font, line, PAPER, bold_px=0)
            screen.blit(cs, (right_center_x - cs.get_width() // 2, c1_y))
            c1_y += line_step

        # Bottom-left: author 2
        a2_top_y = 8 + half_h + 14
        author2_name = rtxt(font_big, "Fatih", GOLD, bold_px=1)
        screen.blit(author2_name, (left_center_x - author2_name.get_width() // 2, a2_top_y))

        contrib2_lines = ["-game design", "-development", "-story", "-idea"]
        c2_y = a2_top_y + author2_name.get_height() + 8
        for line in contrib2_lines:
            cs = rtxt(contrib_font, line, PAPER, bold_px=0)
            screen.blit(cs, (left_center_x - cs.get_width() // 2, c2_y))
            c2_y += line_step
        # Back (text only, no box; rect for click)
        credits_back_rect = pygame.Rect(LOW_W // 2 - 60, LOW_H - 44, 120, 28)
        back_txt = rtxt(font_small, "Back", GOLD)
        screen.blit(back_txt, (credits_back_rect.centerx - back_txt.get_width() // 2, credits_back_rect.centery - back_txt.get_height() // 2))

    def draw_settings() -> None:
        nonlocal settings_back_rect, settings_sfx_toggle_rect
        draw_tiled_background()
        draw_pixel_border(screen, pygame.Rect(8, 8, LOW_W - 16, LOW_H - 16), FELT_DARK, GOLD)
        title = rtxt(font_big, "SETTINGS", GOLD)
        screen.blit(title, ((LOW_W - title.get_width()) // 2, 20))
        icon_y = 52
        if sfx_settings_icon_surf is not None:
            ix = (LOW_W - sfx_settings_icon_surf.get_width()) // 2
            screen.blit(sfx_settings_icon_surf, (ix, icon_y))
            icon_y += sfx_settings_icon_surf.get_height() + 15  # gap + 5px lower than prior layout
        else:
            icon_y += 15
        toggle_w, toggle_h = 200, 36
        settings_sfx_toggle_rect = pygame.Rect((LOW_W - toggle_w) // 2, icon_y, toggle_w, toggle_h)
        draw_pixel_border(
            screen,
            settings_sfx_toggle_rect,
            GOLD if sfx_on else FELT_DARK,
            (80, 70, 40),
        )
        toggle_label = "SFX: On" if sfx_on else "SFX: Off"
        tcol = INK if sfx_on else PAPER
        ttxt = rtxt(font_small, toggle_label, tcol)
        screen.blit(
            ttxt,
            (
                settings_sfx_toggle_rect.centerx - ttxt.get_width() // 2,
                settings_sfx_toggle_rect.centery - ttxt.get_height() // 2,
            ),
        )
        settings_back_rect = pygame.Rect(LOW_W // 2 - 60, LOW_H - 44, 120, 28)
        back_txt = rtxt(font_small, "Back", GOLD)
        screen.blit(
            back_txt,
            (
                settings_back_rect.centerx - back_txt.get_width() // 2,
                settings_back_rect.centery - back_txt.get_height() // 2,
            ),
        )

    def draw_game_over() -> None:
        nonlocal game_over_retry_rect, game_over_menu_rect, game_over_primary_is_menu
        draw_tiled_background()
        draw_pixel_border_alpha(screen, pygame.Rect(40, 60, LOW_W - 80, 180), FELT_DARK, GOLD, fill_alpha=235)
        game_over_retry_rect = None
        game_over_menu_rect = None
        game_over_primary_is_menu = False
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
        if game_over_from_contract_eval and contract_eval_passed:
            # Win page: single "Menu" button.
            game_over_primary_is_menu = True
            draw_pixel_border(screen, game_over_retry_rect, GOLD, (80, 70, 40))
            rtxt_surf = rtxt(font_small, "Menu", INK)
            screen.blit(rtxt_surf, (game_over_retry_rect.centerx - rtxt_surf.get_width() // 2, game_over_retry_rect.centery - rtxt_surf.get_height() // 2))
        else:
            # Loss page: keep Retry, and add Menu underneath.
            draw_pixel_border(screen, game_over_retry_rect, GOLD, (80, 70, 40))
            rtxt_surf = rtxt(font_small, "Retry", INK)
            screen.blit(rtxt_surf, (game_over_retry_rect.centerx - rtxt_surf.get_width() // 2, game_over_retry_rect.centery - rtxt_surf.get_height() // 2))
            game_over_menu_rect = pygame.Rect((LOW_W - retry_w) // 2, yy + retry_h + 8, retry_w, retry_h)
            draw_pixel_border(screen, game_over_menu_rect, FELT_DARK, GOLD)
            mtxt = rtxt(font_small, "Menu", PAPER)
            screen.blit(mtxt, (game_over_menu_rect.centerx - mtxt.get_width() // 2, game_over_menu_rect.centery - mtxt.get_height() // 2))
        esc = rtxt(font_small, "ESC to quit.", GOLD, bold_px=1)
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
        nonlocal phase2_strikes, phase2_correct, phase2_used, phase2_wrong_locked, phase2_scaled_art_cache, phase2_play_anims, phase2_pending_outcome
        nonlocal phase2_win_celebrate_frames, phase2_win_burst
        nonlocal phase2_hover_i, phase2_end_panel_rect, contract_eval_passed, game_over_from_contract_eval
        nonlocal win_sfx_played, lose_sfx_played

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
        phase2_wrong_locked.clear()
        phase2_scaled_art_cache.clear()
        phase2_play_anims.clear()
        phase2_pending_outcome = None
        phase2_win_celebrate_frames = 0
        phase2_win_burst.clear()
        win_sfx_played = False
        lose_sfx_played = False
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
        phase2_wrong_locked.clear()

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
                        play_sfx("button")
                        contracts = get_contracts()
                        if contracts:
                            state.scenario_key = rng.choice([c["key"] for c in contracts])
                        mode = "intro"
                        intro_start_ms = pygame.time.get_ticks()
                    elif menu_credits_rect and menu_credits_rect.collidepoint(mouse_low):
                        play_sfx("button")
                        mode = "credits"
                    elif menu_settings_rect and menu_settings_rect.collidepoint(mouse_low):
                        play_sfx("button")
                        mode = "settings"
                    elif menu_admin_rect and menu_admin_rect.collidepoint(mouse_low):
                        play_sfx("button")
                        start_admin_phase2()
                    continue
                if mode == "settings":
                    if settings_back_rect and settings_back_rect.collidepoint(mouse_low):
                        play_sfx("button")
                        mode = "menu"
                    elif settings_sfx_toggle_rect and settings_sfx_toggle_rect.collidepoint(mouse_low):
                        sfx_on = not sfx_on
                        if sfx_on:
                            play_sfx("button")
                    continue
                if mode == "credits" and credits_back_rect and credits_back_rect.collidepoint(mouse_low):
                    play_sfx("button")
                    mode = "menu"
                    continue
                if mode == "intro":
                    start_round()
                    recompute_stats_from_active(state)
                    message = "Click deck to draw & advance. Max 5 in hand. Active cards = your stats."
                    mode = "game"
                    intro_start_ms = None
                    continue
                if mode == "phase2":
                    if phase2_subphase == "play" and phase2_q_index < len(phase2_questions):
                        # Don't allow multiple answers while a played-card cleanup animation is running.
                        if phase2_play_anims:
                            continue
                        rects = phase2_card_layout_rects()
                        for i, cr in enumerate(rects):
                            if i >= len(phase2_cards) or (i < len(phase2_used) and phase2_used[i]) or i in phase2_wrong_locked:
                                continue
                            if not cr.collidepoint(mouse_low):
                                continue
                            q = phase2_questions[phase2_q_index]
                            acc = set(q.get("acceptable") or [])
                            card = phase2_cards[i]
                            if card.key in acc:
                                phase2_correct += 1
                                state.score += PHASE2_SCORE_CORRECT
                                phase2_used[i] = True
                                # Animate the played card toward the question, then fade away.
                                # Anchor is near the question text block.
                                play_sfx("woosh")
                                phase2_play_anims.append(
                                    (i, cr.copy(), 0.0, PHASE2_PLAY_TARGET)
                                )
                                phase2_q_index += 1
                                phase2_wrong_locked.clear()
                                n = len(phase2_questions)
                                if phase2_q_index >= n:
                                    need = max(0, n - 1)
                                    phase2_pending_outcome = phase2_correct >= need
                            else:
                                # Wrong answer: card is disabled only for this question.
                                phase2_wrong_locked.add(i)
                                state.score -= PHASE2_SCORE_WRONG
                                phase2_strikes += 1
                                if phase2_strikes >= 2:
                                    phase2_pending_outcome = False
                            break
                    continue
                if mode == "over" and game_over_retry_rect and game_over_retry_rect.collidepoint(mouse_low):
                    play_sfx("button")
                    # Win screen primary button is Menu; otherwise it's Retry.
                    if game_over_primary_is_menu:
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
                        phase2_wrong_locked.clear()
                        phase2_scaled_art_cache.clear()
                        phase2_play_anims.clear()
                        phase2_pending_outcome = None
                        phase2_win_celebrate_frames = 0
                        phase2_win_burst.clear()
                        win_sfx_played = False
                        lose_sfx_played = False
                        phase2_subphase = ""
                        phase2_anim_progress = 0.0
                        hidden_hand_index = None
                        mode = "menu"
                        collect_anim_list.clear()
                        continue
                    # Retry: show the intro again first (then the player starts from the intro).
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
                    phase2_wrong_locked.clear()
                    phase2_scaled_art_cache.clear()
                    phase2_play_anims.clear()
                    phase2_pending_outcome = None
                    phase2_win_celebrate_frames = 0
                    phase2_win_burst.clear()
                    win_sfx_played = False
                    lose_sfx_played = False
                    phase2_subphase = ""
                    phase2_anim_progress = 0.0
                    hidden_hand_index = None
                    contracts = get_contracts()
                    if contracts:
                        state.scenario_key = rng.choice([c["key"] for c in contracts])
                    intro_start_ms = pygame.time.get_ticks()
                    mode = "intro"
                    collect_anim_list.clear()
                    continue
                if mode == "over" and game_over_menu_rect and game_over_menu_rect.collidepoint(mouse_low):
                    play_sfx("button")
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
                    phase2_wrong_locked.clear()
                    phase2_scaled_art_cache.clear()
                    phase2_play_anims.clear()
                    phase2_pending_outcome = None
                    phase2_win_celebrate_frames = 0
                    phase2_win_burst.clear()
                    win_sfx_played = False
                    lose_sfx_played = False
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
                        play_sfx("draw")
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
                                play_sfx("bin")
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
                                                    play_equip_sfx(card)
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
                                                play_equip_sfx(card)
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
                                play_sfx("bin")
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
                                play_sfx("woosh")
                                active_to_hand_anim_list.append((card, start_r, 0.0, dragging_active_idx))
                        dragging_active_idx = None

        # Losing from a stat < 0 can happen mid-round (equip / trash / move) before end_round().
        # draw_game_over() already shows the loss screen when hard_loss(), but mode stayed "game",
        # so MOUSEBUTTONDOWN hit `continue` and never ran the Retry/Menu handlers.
        if mode == "game" and (hard_loss() or state.round_idx > state.rounds_total):
            if hard_loss():
                game_over_from_contract_eval = False
                if not lose_sfx_played:
                    play_sfx("lose")
                    lose_sfx_played = True
            mode = "over"

        # Hover detection (only in game mode, when not dragging)
        hover_idx = None
        hover_active_idx = None
        hover_peek_card = None
        phase2_hover_i = None
        if mode == "phase2" and phase2_subphase == "play":
            rects = phase2_card_layout_rects()
            for i, cr in enumerate(rects):
                if (i < len(phase2_used) and phase2_used[i]) or i in phase2_wrong_locked:
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

        # Hover SFX: play once when entering a hover target.
        hover_token: Optional[str] = None
        if mode == "phase2" and phase2_hover_i is not None:
            hover_token = f"p2:{phase2_hover_i}"
        elif mode == "game":
            if hover_active_idx is not None:
                hover_token = f"a:{hover_active_idx}"
            elif hover_idx is not None:
                hover_token = f"h:{hover_idx}"
            elif deck_rect.collidepoint(mouse_low):
                hover_token = "deck"
        if hover_token != last_hover_token:
            if hover_token is not None:
                play_sfx("hover")
            last_hover_token = hover_token

        if mode == "menu":
            draw_menu()
        elif mode == "credits":
            draw_credits()
        elif mode == "settings":
            draw_settings()
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
                if dragging_hand_idx == hidden_hand_index and deck_back_card_surf is not None:
                    screen.blit(deck_back_card_surf, dr)
                    draw_pixel_frame(screen, dr, GOLD, PAPER_DARK)
                else:
                    outer = card_frame_outer_color(c)
                    dha = c.art and c.art in card_art_surfs
                    blit_epic_godrays_behind_card_layer(screen, c, dr)
                    if dha:
                        sc = pygame.transform.smoothscale(card_art_surfs[c.art], (dr.w, dr.h))
                        screen.blit(sc, dr.topleft)
                    else:
                        draw_pixel_border(screen, dr, PAPER, outer)
                        pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                        screen.blit(pip, (dr.x + 4, dr.y + 3))
                    draw_pixel_frame(screen, dr, outer, PAPER_DARK)
                    blit_cursed_horns_on_screen(screen, c, dr)
            elif dragging_active_idx is not None and dragging_active_idx < len(state.active_slots) and state.active_slots[dragging_active_idx]:
                c = state.active_slots[dragging_active_idx]
                dr = pygame.Rect(lmx - CARD_W // 2, lmy - CARD_H // 2, CARD_W, CARD_H)
                outer = card_frame_outer_color(c)
                dha = c.art and c.art in card_art_surfs
                blit_epic_godrays_behind_card_layer(screen, c, dr)
                if dha:
                    sc = pygame.transform.smoothscale(card_art_surfs[c.art], (dr.w, dr.h))
                    screen.blit(sc, dr.topleft)
                else:
                    draw_pixel_border(screen, dr, PAPER, outer)
                    pip = rtxt(font_small, c.suit[0].upper(), card_border_color(c), bold_px=0)
                    screen.blit(pip, (dr.x + 4, dr.y + 3))
                draw_pixel_frame(screen, dr, outer, PAPER_DARK)
                blit_cursed_horns_on_screen(screen, c, dr)
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

        # Start result flow from Phase 2 (after card animations complete).
        if mode == "phase2" and phase2_pending_outcome is not None and not phase2_play_anims:
            won = bool(phase2_pending_outcome)
            if won:
                # 5s solitaire-like celebration before moving to win page.
                if phase2_subphase != "celebrate":
                    if not win_sfx_played:
                        play_sfx("win")
                        win_sfx_played = True
                    phase2_subphase = "celebrate"
                    phase2_win_celebrate_frames = PHASE2_WIN_CELEBRATE_TOTAL
                    phase2_win_burst.clear()
                phase2_pending_outcome = None
            else:
                if not lose_sfx_played:
                    play_sfx("lose")
                    lose_sfx_played = True
                phase2_passed_challenge = False
                contract_eval_passed = False
                game_over_from_contract_eval = True
                phase2_pending_outcome = None
                mode = "over"

        # Win celebration update: spawn + simulate many bouncing deck cards.
        if mode == "phase2" and phase2_subphase == "celebrate":
            spawn_rate = 3  # cards per frame
            for _ in range(spawn_rate):
                vx = rng.uniform(-3.6, 3.6)
                vy = rng.uniform(-9.0, -4.5)
                spin = rng.uniform(-8.5, 8.5)
                scale = rng.uniform(0.85, 1.2)
                phase2_win_burst.append((LOW_W / 2, LOW_H - 24, vx, vy, spin, 0.0, scale, 255.0))
            g = 0.28
            updated: List[Tuple[float, float, float, float, float, float, float, float]] = []
            for x, y, vx, vy, spin, rot, scale, alpha in phase2_win_burst:
                x += vx
                y += vy
                vy += g
                rot += spin
                alpha -= 1.0
                # Bounce off side walls.
                if x < -40:
                    x = -40
                    vx = abs(vx) * 0.9
                elif x > LOW_W + 40:
                    x = LOW_W + 40
                    vx = -abs(vx) * 0.9
                # Bounce from "floor" near bottom edge.
                floor_y = LOW_H - 6
                if y > floor_y:
                    y = floor_y
                    vy = -abs(vy) * 0.72
                if alpha > 8:
                    updated.append((x, y, vx, vy, spin, rot, scale, alpha))
            # Keep buffer bounded.
            phase2_win_burst = updated[-220:]
            if phase2_win_celebrate_frames > 0:
                phase2_win_celebrate_frames -= 1
            if phase2_win_celebrate_frames <= 0:
                phase2_passed_challenge = True
                contract_eval_passed = True
                game_over_from_contract_eval = True
                phase2_subphase = ""
                phase2_win_burst.clear()
                mode = "over"

        if headless:
            headless_frames += 1
            # Run a couple frames then exit successfully.
            if headless_frames > 3:
                running = False

