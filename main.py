#!/usr/bin/env python3
"""
Wizardry‑style dungeon RPG — single‑file Pygame prototype (Top‑down, 4‑party, Menus, Animations)

Update summary
- Centered menus now have **no headers** (cleaner look).
- Tavern actions are **Create / Dismiss / Back** and the menu opens **automatically**.
- **Back** in Tavern returns to **Town**.
- **Dismiss** now lets you choose a character and confirms via a popup.
- (Kept from prior) Target selection in battle, inter‑animation pauses, acting highlights, enemy windows, etc.

Controls
- Menus: Arrow keys / Enter / Esc
- Maze: ←/→ turn, ↑ move, Esc pause menu

Tested with: Python 3.10+, pygame 2.5+
"""

import json
import os
import random
import math
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple, Dict, Any

import pygame

# ------------------------------ Constants ----------------------------------
WIDTH, HEIGHT = 960, 600
VIEW_H = 440
LOG_H = HEIGHT - VIEW_H
FPS = 60
FONT_NAME = None
FONT_PATH = "fonts/prstart.ttf"

# Music asset filenames (placed in project root or alongside main.py)
MUSIC_TOWN = "town.wav"
MUSIC_LABYRINTH = "labyrinth.wav"
MUSIC_BATTLE = "battle.wav"

MAZE_W, MAZE_H = 24, 24

WHITE = (240, 240, 240)
GRAY = (160, 160, 160)
DARK = (24, 24, 28)
LIGHT = (210, 210, 220)
RED = (220, 64, 64)
GREEN = (64, 200, 100)
BLUE = (80, 160, 240)
YELLOW = (240, 220, 80)
PURPLE = (180, 120, 240)

# Modes
MODE_TITLE = "TITLE"
MODE_TOWN = "TOWN"
MODE_CREATE = "CREATE"
MODE_PARTY = "PARTY"
MODE_FORM = "FORM"
MODE_STATUS = "STATUS"
MODE_SHOP = "SHOP"
MODE_TEMPLE = "TEMPLE"
MODE_TRAINING = "TRAINING"
MODE_MAZE = "MAZE"
MODE_BATTLE = "BATTLE"
MODE_VICTORY = "VICTORY"
MODE_DEFEAT = "DEFEAT"
MODE_SAVELOAD = "SAVELOAD"
MODE_PAUSE = "PAUSE"
MODE_ITEMS = "ITEMS"
MODE_COMBAT_INTRO = "COMBAT_INTRO"
MODE_EQUIP = "EQUIP"
MODE_SCENE = "SCENE"  # town<->labyrinth transition

# Temple costs
TEMPLE_HEAL_PARTY_COST = 30
REVIVE_BASE_COST = 30
REVIVE_PER_LEVEL = 10

# Map tiles
T_EMPTY = 0
T_WALL = 1
T_TOWN = 2
T_STAIRS_D = 3
T_STAIRS_U = 4

# Limits
ACTIVE_MAX = 4
ROSTER_MAX = 10

# ------------------------------ Data Models --------------------------------
RACES = ["Human", "Elf", "Dwarf", "Gnome", "Halfling"]
CLASSES = ["Fighter", "Mage", "Priest", "Thief"]

BASE_HP = {"Fighter": 12, "Mage": 6, "Priest": 8, "Thief": 8}
BASE_MP = {"Fighter": 0, "Mage": 8, "Priest": 6, "Thief": 0}
AC_BASE = 10

# Data resources are loaded from JSON (monsters, items, skills, levels)
# Module-level placeholders populated by Game.load_data()
SHOP_ITEMS: List[Dict[str, Any]] = []
ITEMS_BY_ID: Dict[str, Dict[str, Any]] = {}

# Recruiting costs per class (party pays on creation)
CLASS_COSTS = {"Thief": 25, "Fighter": 35, "Priest": 40, "Mage": 45}

DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]
DIR_NAMES = ["N", "E", "S", "W"]


class MusicManager:
    def __init__(self):
        self.enabled = False
        try:
            pygame.mixer.init()
            self.enabled = True
        except Exception:
            self.enabled = False
            return
        # Preload available tracks
        self.tracks: Dict[str, Optional[pygame.mixer.Sound]] = {
            'town': self._load_sound(MUSIC_TOWN),
            'labyrinth': self._load_sound(MUSIC_LABYRINTH),
            'battle': self._load_sound(MUSIC_BATTLE),
        }
        # Two channels for crossfading
        try:
            self.chan_a = pygame.mixer.Channel(0)
            self.chan_b = pygame.mixer.Channel(1)
        except Exception:
            self.enabled = False
            return
        self.chan_a.set_volume(1.0)
        self.chan_b.set_volume(1.0)
        self.current_key: Optional[str] = None
        self.current_channel: Optional[pygame.mixer.Channel] = None

    def _load_sound(self, filename: str) -> Optional[pygame.mixer.Sound]:
        if not filename:
            return None
        try_paths = [filename, os.path.join('data', filename)]
        for p in try_paths:
            if os.path.exists(p):
                try:
                    return pygame.mixer.Sound(p)
                except Exception:
                    return None
        return None

    def _pick_inactive(self) -> pygame.mixer.Channel:
        # Use the other channel than the current, default to A
        return self.chan_b if self.current_channel is self.chan_a else self.chan_a

    def crossfade_to(self, key: str, fade_ms: int = 1200):
        if not self.enabled:
            return
        if key == self.current_key:
            return
        snd = self.tracks.get(key)
        # If target missing, just fade out current to silence
        if snd is None:
            self.fade_out_all(fade_ms)
            self.current_key = None
            self.current_channel = None
            return
        new_ch = self._pick_inactive()
        # Fade out current
        if self.current_channel:
            try:
                self.current_channel.fadeout(max(0, int(fade_ms)))
            except Exception:
                pass
        # Fade in new on the other channel, loop indefinitely
        try:
            new_ch.set_volume(1.0)
            new_ch.play(snd, loops=-1, fade_ms=max(0, int(fade_ms)))
        except Exception:
            return
        self.current_channel = new_ch
        self.current_key = key

    def play_immediate(self, key: str):
        if not self.enabled:
            return
        snd = self.tracks.get(key)
        # Stop everything first
        try:
            self.chan_a.stop(); self.chan_b.stop()
        except Exception:
            pass
        if snd is None:
            self.current_key = None
            self.current_channel = None
            return
        # Play immediately, loop indefinitely
        try:
            self.chan_a.set_volume(1.0)
            self.chan_a.play(snd, loops=-1)
            self.current_channel = self.chan_a
            self.current_key = key
        except Exception:
            pass

    def fade_out_all(self, fade_ms: int = 1000):
        if not self.enabled:
            return
        try:
            self.chan_a.fadeout(max(0, int(fade_ms)))
            self.chan_b.fadeout(max(0, int(fade_ms)))
        except Exception:
            pass
        self.current_key = None
        self.current_channel = None


class SfxManager:
    def __init__(self):
        # If mixer failed to init in MusicManager, we still try; ignore errors.
        self.enabled = pygame.mixer.get_init() is not None
        self.sounds: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._load_defaults()

    def _find_file(self, base: str) -> Optional[str]:
        # Try common extensions and locations
        exts = [".wav", ".ogg", ".mp3"]
        for ext in exts:
            for root in ("data", "."):
                path = os.path.join(root, base + ext)
                if os.path.exists(path):
                    return path
        return None

    def _load(self, key: str, base: str) -> Optional[pygame.mixer.Sound]:
        if not self.enabled:
            return None
        fn = self._find_file(base)
        if not fn:
            return None
        try:
            return pygame.mixer.Sound(fn)
        except Exception:
            return None

    def _load_defaults(self):
        self.sounds = {
            'ui_move': self._load('ui_move', 'sfx_ui_move'),
            'ui_select': self._load('ui_select', 'sfx_ui_select'),
            'step': self._load('step', 'sfx_step'),
            'miss': self._load('miss', 'sfx_miss'),
            'party_hurt': self._load('party_hurt', 'sfx_party_hurt'),
            'enemy_hurt': self._load('enemy_hurt', 'sfx_enemy_hurt'),
            'heal': self._load('heal', 'sfx_heal'),
            'typer': self._load('typer', 'sfx_typer'),
        }

    def play(self, key: str, volume: float = 1.0):
        if not self.enabled:
            return
        snd = self.sounds.get(key)
        if snd is None:
            return
        try:
            old = snd.get_volume()
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
            snd.set_volume(old)
        except Exception:
            pass


def roll_stat():
    return sum(random.randint(1, 6) for _ in range(3))


def ability_mod(score: int) -> int:
    return (score - 10) // 2


@dataclass
class Equipment:
    weapon_atk: int = 0
    armor_ac: int = 0
    weapon_id: Optional[str] = None
    armor_id: Optional[str] = None
    acc1_id: Optional[str] = None
    acc2_id: Optional[str] = None


@dataclass
class Character:
    name: str
    race: str
    cls: str
    level: int = 1
    str_: int = field(default_factory=roll_stat)
    iq: int = field(default_factory=roll_stat)
    piety: int = field(default_factory=roll_stat)
    vit: int = field(default_factory=roll_stat)
    agi: int = field(default_factory=roll_stat)
    luck: int = field(default_factory=roll_stat)
    max_hp: int = 0
    hp: int = 0
    max_mp: int = 0
    mp: int = 0
    ac: int = AC_BASE
    exp: int = 0
    gold: int = 0
    alive: bool = True
    equipment: Equipment = field(default_factory=Equipment)
    inventory: List[str] = field(default_factory=list)

    def __post_init__(self):
        base_hp = BASE_HP[self.cls]
        self.max_hp = max(1, base_hp + ability_mod(self.vit))
        self.hp = self.max_hp
        self.max_mp = max(0, BASE_MP[self.cls] + ability_mod(self.iq if self.cls == "Mage" else self.piety))
        self.mp = self.max_mp

    @property
    def atk_bonus(self) -> int:
        return ability_mod(self.str_) + self.equipment.weapon_atk

    @property
    def defense_ac(self) -> int:
        # Base AC plus armor and accessory AC modifiers
        acc_ac = 0
        for iid in (self.equipment.acc1_id, self.equipment.acc2_id):
            if iid:
                acc_ac += ITEMS_BY_ID.get(iid, {}).get('ac', 0)
        return self.ac + self.equipment.armor_ac + acc_ac

    @property
    def agi_effective(self) -> int:
        # Base AGI plus accessory bonuses
        bonus = 0
        for iid in (self.equipment.acc1_id, self.equipment.acc2_id):
            if iid:
                bonus += ITEMS_BY_ID.get(iid, {}).get('agi', 0)
        return self.agi + bonus

    def to_dict(self):
        d = asdict(self)
        d["equipment"] = asdict(self.equipment)
        return d

    @staticmethod
    def from_dict(d):
        c = Character(d["name"], d["race"], d["cls"])
        for k, v in d.items():
            if k == "equipment":
                c.equipment = Equipment(**v)
            elif hasattr(c, k):
                setattr(c, k, v)
        return c


class Party:
    def __init__(self):
        self.members: List[Character] = []
        self.active: List[int] = []
        self.gold: int = 0
        self.inventory: List[str] = []

    def alive_members(self) -> List[Character]:
        return [c for c in self.members if c.alive and c.hp > 0]

    def active_members(self) -> List[Character]:
        return [self.members[i] for i in self.active if 0 <= i < len(self.members)]

    def alive_active_members(self) -> List[Character]:
        return [c for c in self.active_members() if c.alive and c.hp > 0]

    def all_active_alive(self) -> bool:
        return len(self.active) > 0 and all(self.members[i].alive and self.members[i].hp > 0 for i in self.active if 0 <= i < len(self.members))

    def any_active_alive(self) -> bool:
        return len(self.alive_active_members()) > 0

    def clamp_active(self):
        self.active = [i for i in self.active if 0 <= i < len(self.members)]
        if len(self.active) > ACTIVE_MAX:
            self.active = self.active[:ACTIVE_MAX]

    def to_dict(self):
        return {
            "members": [m.to_dict() for m in self.members],
            "active": self.active,
            "gold": self.gold,
            "inventory": list(self.inventory),
        }

    @staticmethod
    def from_dict(d):
        p = Party()
        p.members = [Character.from_dict(m) for m in d.get("members", [])]
        p.active = d.get("active", [])
        p.gold = int(d.get("gold", 0))
        p.inventory = list(d.get("inventory", []))
        p.clamp_active()
        return p


@dataclass
class Enemy:
    name: str
    hp: int
    ac: int
    atk_low: int
    atk_high: int
    exp: int
    gold_low: int
    gold_high: int
    agi: int = 8

    @staticmethod
    def from_base(base: Dict[str, Any]):
        hp = random.randint(base.get("hp_low", 6), base.get("hp_high", 10))
        return Enemy(
            name=base.get("name", "Monster"),
            hp=hp,
            ac=int(base.get("ac", 8)),
            atk_low=int(base.get("atk_low", 1)),
            atk_high=int(base.get("atk_high", 4)),
            exp=int(base.get("exp", 10)),
            gold_low=int(base.get("gold_low", 1)),
            gold_high=int(base.get("gold_high", 8)),
            agi=int(base.get("agi", random.randint(5, 12))),
        )


# ------------------------------ Maze / Levels -------------------------------

def generate_base_grid(w: int, h: int) -> List[List[int]]:
    grid = [[T_WALL] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            grid[y][x] = T_EMPTY
    # simple internal walls
    for x in range(2, w - 2, 4):
        for y in range(2, h - 2):
            if y % 3 != 0:
                grid[y][x] = T_WALL
    # starting room
    for y in range(1, 5):
        for x in range(1, 5):
            grid[y][x] = T_EMPTY
    return grid


@dataclass
class Level:
    grid: List[List[int]]
    stairs_down: Optional[Tuple[int, int]] = None
    stairs_up: Optional[Tuple[int, int]] = None
    town_portal: Optional[Tuple[int, int]] = None
    # Encounter config loaded from JSON
    encounter_monsters: List[str] = field(default_factory=list)
    encounter_group: Tuple[int, int] = (1, 3)


class Dungeon:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.levels: List[Level] = []

    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def ensure_level(self, ix: int, arrival_pos: Optional[Tuple[int, int]] = None) -> None:
        while len(self.levels) <= ix:
            grid = generate_base_grid(self.w, self.h)
            lvl = Level(grid=grid)
            self.levels.append(lvl)
        lvl = self.levels[ix]
        # Load level JSON if available (grid, markers, encounters)
        try:
            path = os.path.join('data', 'levels', f'level{ix}.json')
            if os.path.exists(path):
                with open(path) as f:
                    data = json.load(f)
                # Grid
                g = data.get('grid')
                if isinstance(g, list) and g and isinstance(g[0], list):
                    h = min(self.h, len(g))
                    w = min(self.w, len(g[0]))
                    newg = generate_base_grid(self.w, self.h)
                    for y in range(h):
                        for x in range(w):
                            try:
                                newg[y][x] = int(g[y][x])
                            except Exception:
                                pass
                    lvl.grid = newg
                # Markers
                sd = data.get('stairs_down'); su = data.get('stairs_up'); tp = data.get('town_portal')
                lvl.stairs_down = tuple(sd) if isinstance(sd, list) and len(sd) == 2 else lvl.stairs_down
                lvl.stairs_up = tuple(su) if isinstance(su, list) and len(su) == 2 else lvl.stairs_up
                if ix == 0 and isinstance(tp, list) and len(tp) == 2:
                    lvl.town_portal = tuple(tp)
                # Encounters
                enc = data.get('encounters', {})
                mons = enc.get('monsters', [])
                grp = enc.get('group', [1, 3])
                lvl.encounter_monsters = mons if isinstance(mons, list) else []
                if isinstance(grp, list) and len(grp) == 2:
                    lvl.encounter_group = (int(grp[0]), int(grp[1]))
        except Exception:
            pass
        if ix == 0 and not lvl.town_portal:
            lvl.town_portal = (2, 2)
            x, y = lvl.town_portal
            lvl.grid[y][x] = T_TOWN
        if arrival_pos is not None:
            ax, ay = arrival_pos
            lvl.stairs_up = (ax, ay)
            lvl.grid[ay][ax] = T_STAIRS_U
        if not lvl.stairs_down:
            sx, sy = self._find_far_open(ix)
            lvl.stairs_down = (sx, sy)
            lvl.grid[sy][sx] = T_STAIRS_D

    def _find_far_open(self, ix: int) -> Tuple[int, int]:
        grid = self.levels[ix].grid
        candidates = []
        for y in range(self.h - 5, 2, -1):
            for x in range(self.w - 5, 2, -1):
                if grid[y][x] == T_EMPTY:
                    candidates.append((x, y))
        if not candidates:
            for y in range(1, self.h - 1):
                for x in range(1, self.w - 1):
                    if grid[y][x] == T_EMPTY:
                        candidates.append((x, y))
        return random.choice(candidates) if candidates else (2, 2)


# ------------------------------ Hit/FX --------------------------------------
class HitEffects:
    def __init__(self):
        self.effects: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def trigger(self, kind: str, index: int, duration_ms: int = 300, intensity: int = 5):
        now = pygame.time.get_ticks()
        self.effects[(kind, index)] = {"until": now + duration_ms, "duration": duration_ms, "intensity": intensity}

    def sample(self, kind: str, index: int, base_color=WHITE) -> Tuple[Tuple[int, int], Tuple[int, int, int]]:
        now = pygame.time.get_ticks()
        key = (kind, index)
        e = self.effects.get(key)
        if not e:
            return (0, 0), base_color
        t_left = e["until"] - now
        if t_left <= 0:
            self.effects.pop(key, None)
            return (0, 0), base_color
        frac = max(0.0, t_left / e["duration"])
        amp = max(1, int(e["intensity"] * (0.5 + 0.5 * frac)))
        ox = random.randint(-amp, amp)
        oy = random.randint(-amp, amp)
        color = RED if (now // 60) % 2 == 0 else base_color
        return (ox, oy), color


# ------------------------------ Rendering ----------------------------------
class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = self._load_font(16)
        self.font_small = self._load_font(12)
        self.font_big = self._load_font(20)

    def _load_font(self, size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(FONT_PATH, size)
        except Exception:
            return pygame.font.SysFont(FONT_NAME, size)

    def draw_frame(self):
        self.screen.fill(DARK)
        pygame.draw.rect(self.screen, (30, 30, 34), (0, 0, WIDTH, VIEW_H))
        pygame.draw.rect(self.screen, (28, 28, 32), (0, VIEW_H, WIDTH, LOG_H))

    def text(self, surf, txt, pos, color=WHITE, aa=True):
        surf.blit(self.font.render(txt, aa, color), pos)

    def text_small(self, surf, txt, pos, color=LIGHT, aa=True):
        surf.blit(self.font_small.render(txt, aa, color), pos)

    def text_big(self, surf, txt, pos, color=WHITE, aa=True):
        surf.blit(self.font_big.render(txt, aa, color), pos)

    def draw_log(self, log_lines: List[str]):
        panel = self.screen.subsurface(pygame.Rect(0, VIEW_H, WIDTH, LOG_H))
        y = 6
        for ln in log_lines[-10:]:
            self.text_small(panel, ln, (10, y))
            y += 14

    # ---- Top‑down centered & larger ----
    def draw_topdown(self, grid, pos: Tuple[int, int], facing: int, level_ix: int,
                     world_shift_tiles: Tuple[float, float] = (0.0, 0.0), player_bob_px: int = 0,
                     player_frac: Tuple[float, float] = (0.0, 0.0)):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 22))
        px, py = pos
        # Zoom in closer: smaller radius shows fewer tiles, larger cells
        radius = 4
        visible = radius * 2 + 1
        margin = 40
        cell = min((WIDTH - margin * 2) // visible, (VIEW_H - margin * 2) // visible)
        total_w = visible * cell
        total_h = visible * cell
        ox = (WIDTH - total_w) // 2
        oy = (VIEW_H - total_h) // 2
        # Precompute pixel shift from tile shift
        shift_px = (world_shift_tiles[0] * cell, world_shift_tiles[1] * cell)
        for y in range(py - radius, py + radius + 1):
            for x in range(px - radius, px + radius + 1):
                sx = ox + (x - (px - radius)) * cell + int(shift_px[0])
                sy = oy + (y - (py - radius)) * cell + int(shift_px[1])
                if 0 <= x < len(grid[0]) and 0 <= y < len(grid):
                    t = grid[y][x]
                    if t == T_WALL:
                        pygame.draw.rect(view, (40, 40, 70), (sx, sy, cell - 1, cell - 1), 1)
                    else:
                        pygame.draw.rect(view, (24, 24, 34), (sx, sy, cell - 1, cell - 1))
                        if t == T_TOWN:
                            pygame.draw.circle(view, BLUE, (sx + cell // 2, sy + cell // 2), max(3, cell // 6))
                        elif t == T_STAIRS_D:
                            pygame.draw.polygon(view, YELLOW, [(sx + cell // 5, sy + cell // 5), (sx + cell - cell // 5, sy + cell // 5), (sx + cell // 2, sy + cell - cell // 5)])
                        elif t == T_STAIRS_U:
                            pygame.draw.polygon(view, GREEN, [(sx + cell // 5, sy + cell - cell // 5), (sx + cell - cell // 5, sy + cell - cell // 5), (sx + cell // 2, sy + cell // 5)])
        # player marker
        pxs = ox + radius * cell + cell // 2
        pys = oy + radius * cell + cell // 2 + int(player_bob_px)
        pygame.draw.circle(view, PURPLE, (pxs, pys), max(4, cell // 4))
        d = DIRS[facing]
        pygame.draw.line(view, PURPLE, (pxs, pys), (pxs + d[0] * max(10, cell // 2), pys + d[1] * max(10, cell // 2)), 2)
        # Apply a torch-like FOV: LOS-based, cone-shaped, with subtle flicker
        pxf = px + float(player_frac[0])
        pyf = py + float(player_frac[1])
        self._overlay_torch_fov(view, grid, px, py, facing, cell, ox, oy, radius,
                                 world_px_off=int(shift_px[0]), world_py_off=int(shift_px[1]),
                                 player_center_frac=(pxf, pyf))
        self.text_small(view, f"L{level_ix} pos {pos} {DIR_NAMES[facing]}", (12, 6))

    def _overlay_vision_cone(self, surf: pygame.Surface, center: Tuple[int, int], facing: int,
                              spread_deg: float = 80.0, steps: int = 16, edge_alpha: int = 220):
        """Darken outside the player's field of view completely, and inside the cone
        keep it bright near the player (no darkening) and fade darker with distance.
        """
        try:
            # Full black overlay everywhere to start
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 255))

            # We build a mask whose alpha is the desired local darkness (lower alpha = brighter)
            # Start with fully opaque (black) everywhere, then progressively take the minimum
            # alpha inside the cone using BLEND_RGBA_MIN across steps to form a gradient.
            mask = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            mask.fill((0, 0, 0, 255))

            # Facing to angle (radians). 0:N,1:E,2:S,3:W
            angle_map = {0: -math.pi / 2, 1: 0.0, 2: math.pi / 2, 3: math.pi}
            ang = angle_map.get(facing, 0.0)
            spread = math.radians(spread_deg)
            length = max(WIDTH, VIEW_H) * 1.35  # extend beyond view

            steps = max(4, int(steps))
            # Reusable temp surface for min-blending each step
            step_surf = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            # Use a slight easing so brightness persists a bit near player
            for i in range(1, steps + 1):
                frac = i / steps  # 0..1 outward
                # Darkness grows with distance (0 near, edge_alpha near far)
                a = int(edge_alpha * (frac ** 1.2))
                L = length * frac
                a0 = ang - spread / 2
                a1 = ang + spread / 2
                p1 = (center[0] + math.cos(a0) * L, center[1] + math.sin(a0) * L)
                p2 = (center[0] + math.cos(a1) * L, center[1] + math.sin(a1) * L)
                # Draw this step's cone to a temp surface, then MIN-blit into mask
                step_surf.fill((0, 0, 0, 255))
                pygame.draw.polygon(step_surf, (0, 0, 0, a), [center, p1, p2])
                mask.blit(step_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

            # Ensure absolute brightness at the player's immediate position
            pygame.draw.circle(mask, (0, 0, 0, 0), (int(center[0]), int(center[1])), 4)

            # Apply minimum: overlay alpha becomes the mask alpha, leaving outside-of-cone fully black
            overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            surf.blit(overlay, (0, 0))
        except Exception:
            # Fallback: hard cone with transparency ramp using concentric blits
            angle_map = {0: -math.pi / 2, 1: 0.0, 2: math.pi / 2, 3: math.pi}
            ang = angle_map.get(facing, 0.0)
            spread = math.radians(spread_deg)
            length = max(WIDTH, VIEW_H) * 1.3
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 255))
            for i in range(1, max(4, int(steps)) + 1):
                frac = i / max(4, int(steps))
                a = int(edge_alpha * (frac ** 1.2))
                a0 = ang - spread / 2
                a1 = ang + spread / 2
                L = length * frac
                p1 = (center[0] + math.cos(a0) * L, center[1] + math.sin(a0) * L)
                p2 = (center[0] + math.cos(a1) * L, center[1] + math.sin(a1) * L)
                temp = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                pygame.draw.polygon(temp, (0, 0, 0, a), [center, p1, p2])
                overlay.blit(temp, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            pygame.draw.circle(overlay, (0, 0, 0, 0), (int(center[0]), int(center[1])), 4)
            surf.blit(overlay, (0, 0))

    def _angle_for_facing(self, facing: int) -> float:
        return {0: -math.pi / 2, 1: 0.0, 2: math.pi / 2, 3: math.pi}.get(facing, 0.0)

    def _angle_diff(self, a: float, b: float) -> float:
        d = (a - b + math.pi) % (2 * math.pi) - math.pi
        return abs(d)

    def _los_clear(self, grid: List[List[int]], x0: int, y0: int, x1: int, y1: int) -> bool:
        """Return True if line from (x0,y0) to (x1,y1) is not blocked by walls.
        Allows seeing the first wall cell itself, but not beyond it."""
        x, y = x0, y0
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        w = len(grid[0]); h = len(grid)
        while True:
            if not (0 <= x < w and 0 <= y < h):
                return False
            if (x, y) == (x1, y1):
                return True
            # If we hit a wall before reaching target, blocked
            if (x, y) != (x0, y0) and (x, y) != (x1, y1) and grid[y][x] == T_WALL:
                return False
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def _overlay_torch_fov(self, surf: pygame.Surface, grid: List[List[int]],
                            px: int, py: int, facing: int,
                            cell: int, ox: int, oy: int, radius: int,
                            world_px_off: int = 0, world_py_off: int = 0,
                            player_center_frac: Tuple[float, float] = None,
                            spread_deg: float = 80.0, edge_alpha: int = 240, gamma: float = 1.2):
        """Wall-occluding cone FOV with distance-based darkening and subtle flicker.
        - Outside the cone is fully black.
        - Near the player is bright (alpha ~0), darkens with distance.
        - Light flickers slightly over time like a torch."""
        try:
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 255))  # fully black everywhere

            mask = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            mask.fill((0, 0, 0, 255))  # start fully dark; lower alpha in lit tiles

            ang_face = self._angle_for_facing(facing)
            half = math.radians(spread_deg) / 2.0
            max_dist = max(1.0, float(radius))
            now = pygame.time.get_ticks() / 1000.0
            # fractional player center (for smooth FOV following during movement)
            pxf, pyf = (float(px), float(py))
            if player_center_frac is not None:
                pxf, pyf = player_center_frac

            # Iterate tiles within the drawn radius
            for ty in range(py - radius, py + radius + 1):
                if not (0 <= ty < len(grid)):
                    continue
                for tx in range(px - radius, px + radius + 1):
                    if not (0 <= tx < len(grid[0])):
                        continue
                    dx = tx - pxf
                    dy = ty - pyf
                    # Skip far corners outside circular-ish bound for a nicer edge
                    if dx * dx + dy * dy > (radius + 0.5) * (radius + 0.5):
                        continue
                    ang = math.atan2(dy, dx)
                    near3 = (max(abs(dx), abs(dy)) <= 1.0)
                    if not near3:
                        if self._angle_diff(ang, ang_face) > half:
                            continue  # outside facing cone
                        # Use integer tile for LOS from the closest of start/end tiles
                        los_px, los_py = px, py
                        # Prefer the nearer whole tile to the fractional center
                        npx = round(pxf)
                        npy = round(pyf)
                        if 0 <= npx < len(grid[0]) and 0 <= npy < len(grid):
                            los_px, los_py = int(npx), int(npy)
                        if not self._los_clear(grid, los_px, los_py, tx, ty):
                            continue  # blocked by walls

                    # Distance-based darkness (0 near -> edge_alpha far)
                    dist = max(0.0, math.hypot(dx, dy))
                    if near3:
                        # Always-visible comfort bubble around player (3x3). Keep very bright.
                        # Use a very small base darkness by distance to hint depth.
                        base = min(1.0, (dist / 1.5) ** 1.0)
                        a = int(min(50, 35 * base))  # 0..~35
                    else:
                        base = (dist / max_dist) ** gamma
                        a = int(edge_alpha * min(1.0, max(0.0, base)))

                    # Subtle torch flicker: vary phase per tile, mild amplitude
                    phase = ((tx * 37 + ty * 71) % 256) / 256.0 * 2 * math.pi
                    if near3:
                        amp = 4 + 2 * (dist / 1.5)  # very subtle close to player
                    else:
                        amp = 12 + 6 * (dist / max_dist)  # slightly stronger farther
                    flicker = math.sin(now * 6.0 + phase) * amp
                    a = int(max(0, min(255, a + flicker)))

                    # Brighten player's own tile fully
                    if int(round(pxf)) == tx and int(round(pyf)) == ty:
                        a = 0

                    # Draw to mask at the tile's screen rect, leave a 1px gutter
                    sx = ox + (tx - (px - radius)) * cell
                    sy = oy + (ty - (py - radius)) * cell
                    rect = pygame.Rect(int(sx + world_px_off), int(sy + world_py_off), max(1, cell - 1), max(1, cell - 1))
                    pygame.draw.rect(mask, (0, 0, 0, a), rect)

            # Apply min blending so mask alpha reduces darkness in lit areas
            overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            surf.blit(overlay, (0, 0))
        except Exception:
            # If anything goes wrong, fall back to simple non-LOS cone
            self._overlay_vision_cone(surf, (ox + radius * cell + cell // 2, oy + radius * cell + cell // 2), facing,
                                      spread_deg=spread_deg, steps=12, edge_alpha=edge_alpha)

    # ---- Generic centered menu (no header) ----
    def draw_center_menu(self, options: List[str], selected: int):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        if not options:
            return
        pad_x, pad_y = 12, 10
        text_w = max(self.font.size(s + "  ")[0] for s in options)
        text_h = self.font.get_height()
        w = text_w + pad_x * 2
        h = text_h * len(options) + pad_y * 2
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (16, 16, 20), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        cy = y + pad_y
        for i, s in enumerate(options):
            color = YELLOW if i == selected else WHITE
            prefix = "> " if i == selected else "  "
            self.text(view, prefix + s, (x + pad_x, cy), color)
            cy += text_h

    # ---- Combat HUDs ----
    def draw_combat_party_windows(self, party: "Party", effects: "HitEffects", highlight: set = None, acting: set = None, offsets: Dict[int, int] = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
        offsets = offsets or {}
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        members = party.active_members()
        if not members:
            return {}
        n = len(members)
        gap = 16
        w = min(220, (WIDTH - gap * (n + 1)) // n)
        h = 60
        total = n * w + (n + 1) * gap
        x = (WIDTH - total) // 2 + gap
        y = VIEW_H - h - 16
        rects: Dict[int, pygame.Rect] = {}
        for i, m in enumerate(members):
            try:
                gi = party.members.index(m)
            except ValueError:
                gi = i
            (ox, oy), hit_color = effects.sample("party", gi, base_color=WHITE)
            border_col = hit_color
            if border_col == WHITE:
                now = pygame.time.get_ticks()
                if gi in acting and (now // 120) % 2 == 0:
                    border_col = YELLOW
                elif gi in highlight:
                    border_col = YELLOW
            rx = x + i * (w + gap) + ox
            # Apply optional lunge offset (negative moves up)
            ry = y + oy + int(offsets.get(gi, 0))
            rect = pygame.Rect(rx, ry, w, h)
            pygame.draw.rect(view, (20, 20, 28), rect)
            pygame.draw.rect(view, border_col, rect, 2)
            name = m.name[:14]
            self.text(view, name, (rx + 8, ry + 6), border_col)
            self.text_small(view, f"HP {m.hp}/{m.max_hp}", (rx + 8, ry + 26), WHITE)
            self.text_small(view, f"MP {m.mp}/{m.max_mp}", (rx + w // 2 + 8, ry + 26), WHITE)
            rects[gi] = rect
        return rects

    def draw_combat_enemy_windows(self, enemies: List["Enemy"], effects: "HitEffects", highlight: set = None, acting: set = None, dying: Dict[int, float] = None, offsets: Dict[int, int] = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
        dying = dying or {}
        offsets = offsets or {}
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        alive = [(i, e) for i, e in enumerate(enemies) if e.hp > 0]
        # include dying entries for fade-out (keep original index order)
        extra = [(i, enemies[i]) for i in dying.keys() if 0 <= i < len(enemies) and enemies[i].hp <= 0]
        # merge without duplicates and sort by original index so defeated enemies
        # animate in-place rather than being pushed to the end
        merged = {i: e for i, e in alive}
        for i, e in extra:
            if i not in merged:
                merged[i] = e
        draw_list = sorted(merged.items(), key=lambda t: t[0])
        if not draw_list:
            return {}
        n = len(draw_list)
        gap = 16
        w = min(220, (WIDTH - gap * (n + 1)) // n)
        h = 60
        total = n * w + (n + 1) * gap
        x = (WIDTH - total) // 2 + gap
        # Slightly lower enemy windows for better composition
        y = 28
        rects: Dict[int, pygame.Rect] = {}
        for j, (i, e) in enumerate(draw_list):
            (ox, oy), hit_color = effects.sample("enemy", i, base_color=WHITE)
            border_col = hit_color
            if border_col == WHITE:
                now = pygame.time.get_ticks()
                if i in acting and (now // 120) % 2 == 0:
                    border_col = YELLOW
                elif i in highlight:
                    border_col = YELLOW
            rx = x + j * (w + gap) + ox
            # Apply optional lunge offset (positive moves down)
            ry = y + oy + int(offsets.get(i, 0))
            rect = pygame.Rect(rx, ry, w, h)
            # draw to a temp surface if fading
            fade_p = dying.get(i, 0.0)
            if fade_p > 0:
                alpha = max(0, min(255, int(255 * (1.0 - fade_p))))
                temp = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(temp, (20, 20, 28), temp.get_rect())
                pygame.draw.rect(temp, border_col, temp.get_rect(), 2)
                name = e.name[:14]
                temp.blit(self.font.render(name, True, border_col), (8, 6))
                temp.blit(self.font_small.render(f"HP {max(0,e.hp):>2}", True, WHITE), (8, 26))
                temp.set_alpha(alpha)
                view.blit(temp, (rx, ry))
            else:
                pygame.draw.rect(view, (20, 20, 28), rect)
                pygame.draw.rect(view, border_col, rect, 2)
                name = e.name[:14]
                self.text(view, name, (rx + 8, ry + 6), border_col)
                self.text_small(view, f"HP {max(0,e.hp):>2}", (rx + 8, ry + 26), WHITE)
            rects[i] = rect
        return rects


# ------------------------------ Message Log --------------------------------
class MessageLog:
    def __init__(self):
        self.lines: List[str] = ["Welcome to the Labyrinth of Trials."]
        self._queue: List[str] = []
        self._current: str = ""
        self._reveal_chars: int = 0
        self._last_tick: int = pygame.time.get_ticks()
        # chars per second; tune for comfortable reading (slower)
        self._cps: float = 70.0
        # optional sound manager for typewriter sfx
        self._sfx: Optional[SfxManager] = None
        self._typer_last_ms: int = 0
        self._typer_interval_ms: int = 45

    def add(self, txt: str):
        # queue text to be revealed with typewriter effect
        self._queue.append(txt)

    def _advance_queue(self):
        if not self._current and self._queue:
            self._current = self._queue.pop(0)
            self._reveal_chars = 0

    def update(self):
        # progress typewriter reveal
        now = pygame.time.get_ticks()
        dt = max(0, now - self._last_tick)
        self._last_tick = now
        self._advance_queue()
        if self._current:
            add_chars = int(self._cps * (dt / 1000.0))
            if add_chars > 0:
                before = self._reveal_chars
                self._reveal_chars = min(len(self._current), self._reveal_chars + add_chars)
                # play soft typewriter sfx while revealing
                if self._sfx and self._reveal_chars > before:
                    if now - self._typer_last_ms >= self._typer_interval_ms:
                        try:
                            self._sfx.play('typer', 0.35)
                        except Exception:
                            pass
                        self._typer_last_ms = now
                if self._reveal_chars >= len(self._current):
                    # push finished line into history, reset current
                    self.lines.append(self._current)
                    self._current = ""
                    self._reveal_chars = 0
                    # small delay before next line begins revealing
                    # by leaving update until next frame to pull from queue

    def set_sfx(self, sfx: "SfxManager"):
        self._sfx = sfx

    def render_lines(self) -> List[str]:
        # return lines including partially revealed current line (if any)
        if self._current and self._reveal_chars > 0:
            return self.lines + [self._current[: self._reveal_chars]]
        return self.lines


# ------------------------------ Battle -------------------------------------
class Battle:
    def __init__(self, party: Party, log: MessageLog, effects: HitEffects, items_by_id: Dict[str, Any], monsters_by_id: Dict[str, Any], skills_config: Dict[str, List[Dict[str, Any]]], sfx: Optional["SfxManager"] = None):
        self.party = party
        self.log = log
        self.effects = effects
        self.items_by_id = items_by_id
        self.monsters_by_id = monsters_by_id
        self.skills_config = skills_config
        self.sfx = sfx
        self.enemies: List[Enemy] = []
        self.turn_index = 0  # kept for compatibility in some calls
        self.turn_order: List[Tuple[str, int]] = []  # list of (side, index) where index is party global index or enemy index
        self.turn_pos: int = 0
        self.battle_over = False
        self.result: Optional[str] = None

        # UI/flow
        self.state: str = 'menu'  # 'menu' | 'skillmenu' | 'target' | 'anim' | 'postpause'
        self.ui_menu_open: bool = True
        self.ui_menu_index: int = 0
        self.ui_menu_options: List[Tuple[str, str]] = []  # (id,label)
        self.skill_menu_index: int = 0
        self.skill_options: List[Tuple[str, str]] = []  # per-actor skills
        self.anim: Optional[Dict[str, Any]] = None
        self.enemy_queue: List[Dict[str, Any]] = []  # no longer used for rounds; kept for compatibility
        self.floaters: List[Dict[str, Any]] = []  # {side:'party'|'enemy', index:int, text:str, start:int, dur:int}
        self.pause_between_ms: int = 180
        self.pause_until: int = 0
        self.next_after_anim: Optional[Dict[str, Any]] = None

        # Target selection
        self.target_menu_index: int = 0
        self.target_mode: Optional[Dict[str, Any]] = None  # {'side': 'enemy'|'party', 'action': 'attack'|'spell'|'heal'}

        # Items UI
        self.item_menu_index: int = 0
        self.item_action_index: int = 0
        self.selected_item_iid: Optional[str] = None

        # Defeat animations
        self.dying_enemies: Dict[int, Dict[str, int]] = {}  # i -> {'start':ms,'dur':ms}
        self.downed_party: Dict[int, Dict[str, int]] = {}   # gi -> {'start':ms,'dur':ms}

    def start_random(self, allowed: Optional[List[str]] = None, group: Tuple[int, int] = (1, 3)):
        # Build enemy group from allowed ids and monster base data
        ids = [k for k in (allowed or list(self.monsters_by_id.keys())) if k in self.monsters_by_id]
        nmin, nmax = group
        count = random.randint(max(1, nmin), max(nmin, nmax))
        chosen = [random.choice(ids) for _ in range(count)] if ids else []
        self.enemies = [Enemy.from_base(self.monsters_by_id[cid]) for cid in chosen]
        # No ambush message; battle UI/intro handles the transition
        self.build_turn_order()
        self.turn_pos = 0

    def build_turn_order(self):
        # Build mixed initiative order by AGI (descending). Ties: party before enemy, then index.
        party_tokens = [("party", i, self.party.members[i].agi_effective) for i in self.party.active if 0 <= i < len(self.party.members) and self.party.members[i].alive and self.party.members[i].hp > 0]
        enemy_tokens = [("enemy", i, e.agi) for i, e in enumerate(self.enemies) if e.hp > 0]
        combined = party_tokens + enemy_tokens
        combined.sort(key=lambda t: (-t[2], 0 if t[0] == 'party' else 1, t[1]))
        self.turn_order = [(side, ix) for side, ix, _agi in combined]
        if not self.turn_order:
            self.turn_pos = 0

    def next_turn(self):
        # Check victory/defeat
        if not self.enemy_alive():
            self.finish_victory(); return
        if not self.party.any_active_alive():
            self.finish_defeat(); return
        # Ensure current token is valid; if not, rebuild and reset
        if not self.turn_order:
            self.build_turn_order()
            self.turn_pos = 0
        if self.turn_pos >= len(self.turn_order):
            self.build_turn_order()
            self.turn_pos = 0
        # Skip invalid tokens (dead/removed) and advance
        safety = 0
        while safety < 10 and self.turn_order:
            side, ix = self.turn_order[self.turn_pos]
            if side == 'party':
                if 0 <= ix < len(self.party.members) and self.party.members[ix].alive and self.party.members[ix].hp > 0 and ix in self.party.active:
                    break
            else:
                if 0 <= ix < len(self.enemies) and self.enemies[ix].hp > 0:
                    break
            # invalid -> advance
            self.turn_pos = (self.turn_pos + 1) % max(1, len(self.turn_order))
            safety += 1
        if not self.turn_order:
            self.build_turn_order()
            self.turn_pos = 0
        # Act based on token
        side, ix = self.turn_order[self.turn_pos]
        if side == 'party':
            self.state = 'menu'
            self.ui_menu_index = 0
            self.ui_menu_options = []
            a = self.current_actor()
            if not a:
                # if no current actor, advance turn
                self.advance_turn()
                return
            self.ui_menu_options.append(('attack', 'Attack'))
            # Build skills list for current actor
            skills: List[Tuple[str, str]] = []
            if a.cls == 'Mage':
                skills.append(('spell', 'Spark'))
            if a.cls == 'Priest':
                skills.append(('heal', 'Heal'))
            # Filter by resource availability
            filt: List[Tuple[str, str]] = []
            for sid, label in skills:
                if sid in ('spell', 'heal') and a.mp <= 0:
                    continue
                filt.append((sid, label))
            self.skill_options = filt
            self.ui_menu_options.append(('skill', 'Skill'))
            self.ui_menu_options.append(('item', 'Items'))
            self.ui_menu_options.append(('run', 'Run'))
            self.skill_menu_index = 0
        else:
            # Enemy acts automatically (basic attack random target)
            e = self.enemies[ix]
            targets = self.party.alive_active_members()
            if not targets:
                self.finish_defeat(); return
            t = random.choice(targets)
            gi = self.party.members.index(t)
            hit = random.random() < 0.65
            dmg = random.randint(e.atk_low, e.atk_high)
            act = {
                'type': 'attack',
                'actor_side': 'enemy', 'actor_index': ix,
                'target_side': 'party', 'target_index': gi,
                'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                'miss_label': f"{e.name} misses {t.name}.",
            }
            self.start_animation(act)

    def advance_turn(self):
        # Move to next token and trigger next_turn
        if self.turn_order:
            self.turn_pos = (self.turn_pos + 1) % len(self.turn_order)
        self.next_turn()

    def current_actor(self) -> Optional[Character]:
        # Current token must be a party member
        if not self.turn_order:
            return None
        if self.turn_pos >= len(self.turn_order):
            return None
        side, gi = self.turn_order[self.turn_pos]
        if side != 'party':
            return None
        if 0 <= gi < len(self.party.members):
            return self.party.members[gi]
        return None

    def current_actor_global_ix(self) -> Optional[int]:
        # Using token's stored index
        if not self.turn_order:
            return None
        if self.turn_pos >= len(self.turn_order):
            return None
        side, gi = self.turn_order[self.turn_pos]
        return gi if side == 'party' else None

    def enemy_alive(self) -> bool:
        return any(e.hp > 0 for e in self.enemies)

    # ---- Turn flow ----
    def begin_player_turn(self):
        if not self.enemy_alive():
            self.finish_victory(); return
        if not self.party.any_active_alive():
            self.finish_defeat(); return
        self.state = 'menu'
        self.ui_menu_index = 0
        self.ui_menu_options = []
        a = self.current_actor()
        if not a:
            self.finish_defeat(); return
        # Main menu
        self.ui_menu_options.append(('attack', 'Attack'))
        self.ui_menu_options.append(('skill', 'Skill'))
        self.ui_menu_options.append(('item', 'Items'))
        self.ui_menu_options.append(('run', 'Run'))
        # Build skills list for current actor from config
        skills: List[Tuple[str, str]] = []
        for ent in self.skills_config.get(a.cls, []):
            sid = ent.get('id')
            label = ent.get('name', sid)
            if sid:
                skills.append((sid, label))
        # Could add more per-class skills here later
        # Filter by resource availability (e.g., MP > 0)
        filt: List[Tuple[str, str]] = []
        for sid, label in skills:
            if sid in ('spell', 'heal') and a.mp <= 0:
                continue
            filt.append((sid, label))
        self.skill_options = filt
        self.skill_menu_index = 0

    def usable_items(self) -> List[str]:
        # Return list of item ids in party inventory that can be used in battle (consumables)
        items = []
        for iid in self.party.inventory:
            it = self.items_by_id.get(iid, {})
            if it.get('type') == 'consumable':
                items.append(iid)
        return items

    def queue_enemy_round(self):
        # Deprecated in mixed initiative; kept for compatibility
        self.enemy_queue = []

    def start_animation(self, action: Dict[str, Any]):
        now = pygame.time.get_ticks()
        # Staged timing: windup (actor flashes) -> pre-impact pause -> impact (target animates) -> recover
        self.anim = {'action': action, 'stage': 0, 't0': now, 'dur': [240, 140, 240, 160]}
        self.state = 'anim'

    def add_floater(self, side: str, index: int, text: str, dur: int = 700, color=WHITE):
        self.floaters.append({'side': side, 'index': index, 'text': text, 'start': pygame.time.get_ticks(), 'dur': dur, 'color': color})

    def make_item_use_action(self, actor: Character, target_gi: int, iid: str) -> Optional[Dict[str, Any]]:
        it = self.items_by_id.get(iid)
        if not it or it.get('type') != 'consumable':
            return None
        # For now only handle healing potions
        heal = it.get('heal', 0)
        gi = self.party.members.index(actor)
        return {
            'type': 'heal', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'party', 'target_index': target_gi,
            'heal': heal, 'actor_name': actor.name,
        }

    def update(self):
        now = pygame.time.get_ticks()
        # prune floaters
        self.floaters = [f for f in self.floaters if now - f['start'] < f['dur']]
        # prune finished defeat animations
        self.dying_enemies = {i: d for i, d in self.dying_enemies.items() if now - d['start'] < d['dur']}
        self.downed_party = {i: d for i, d in self.downed_party.items() if now - d['start'] < d['dur']}
        if self.battle_over:
            return
        if self.state == 'anim' and self.anim:
            a = self.anim
            stage = a['stage']
            t = now - a['t0']
            # Support both legacy 3-stage and new 4-stage animations
            act = a['action']
            if len(a['dur']) == 3:
                wind, impact, recover = a['dur']
                if stage == 0 and t >= wind:
                    a['stage'] = 1
                    a['t0'] = now
                    self.resolve_action_impact(act)
                elif stage == 1 and t >= impact:
                    a['stage'] = 2
                    a['t0'] = now
                elif stage == 2 and t >= recover:
                    # finish anim -> small pause, then continue
                    self.anim = None
                    self.next_after_anim = {'actor_side': act['actor_side'], 'type': act.get('type'), 'run_success': act.get('success', False)}
                    self.pause_until = now + self.pause_between_ms
                    self.state = 'postpause'
            else:
                wind, pre, impact, recover = a['dur']
                if stage == 0 and t >= wind:
                    # windup finished; brief pause before impact
                    a['stage'] = 1
                    a['t0'] = now
                elif stage == 1 and t >= pre:
                    # now apply the impact (target animates)
                    a['stage'] = 2
                    a['t0'] = now
                    self.resolve_action_impact(act)
                elif stage == 2 and t >= impact:
                    a['stage'] = 3
                    a['t0'] = now
                elif stage == 3 and t >= recover:
                    # finish anim -> small pause, then continue
                    self.anim = None
                    self.next_after_anim = {'actor_side': act['actor_side'], 'type': act.get('type'), 'run_success': act.get('success', False)}
                    self.pause_until = now + self.pause_between_ms
                    self.state = 'postpause'
        elif self.state == 'postpause' and now >= self.pause_until:
            if self.check_end_and_maybe_finish():
                return
            # Mixed initiative: advance to next token
            na = self.next_after_anim or {}
            # If player successfully ran, battle ends (handled earlier). Otherwise continue.
            self.advance_turn()

    def resolve_action_impact(self, act: Dict[str, Any]):
        if act['type'] in ('attack', 'spell'):
            if act.get('hit', False):
                dmg = max(1, int(act.get('dmg', 1)))
                if act['target_side'] == 'enemy':
                    i = act['target_index']
                    if 0 <= i < len(self.enemies):
                        self.enemies[i].hp -= dmg
                        self.effects.trigger('enemy', i, 300, 7)
                        try:
                            # enemy hurt sfx
                            self.sfx.play('enemy_hurt', 0.7)
                        except Exception:
                            pass
                        # damage floater (enemy)
                        self.add_floater('enemy', i, str(dmg), 800, WHITE)
                        if self.enemies[i].hp <= 0:
                            self.enemies[i].hp = 0
                            # start defeat animation
                            self.dying_enemies[i] = {'start': pygame.time.get_ticks(), 'dur': 600}
                else:
                    gi = act['target_index']
                    if 0 <= gi < len(self.party.members):
                        t = self.party.members[gi]
                        t.hp -= dmg
                        try:
                            # party hurt sfx
                            self.sfx.play('party_hurt', 0.7)
                        except Exception:
                            pass
                        # damage floater (party)
                        self.add_floater('party', gi, str(dmg), 800, WHITE)
                        if t.hp <= 0:
                            t.hp = 0
                            t.alive = False
                            # animate a brief downed effect
                            self.downed_party[gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                        self.effects.trigger('party', gi, 300, 7)
                self.log.add(act.get('label', 'A hit lands.'))
            else:
                idx = act['target_index']
                side = act['target_side']
                self.add_floater(side, idx, 'MISS', 700, WHITE)
                try:
                    self.sfx.play('miss', 0.6)
                except Exception:
                    pass
                self.log.add(act.get('miss_label', 'The attack misses.'))
        elif act['type'] == 'heal':
            gi = act['target_index']
            amt = act.get('heal', 0)
            if 0 <= gi < len(self.party.members):
                t = self.party.members[gi]
                before = t.hp
                t.hp = min(t.max_hp, t.hp + amt)
                # heal floater (party)
                self.add_floater('party', gi, str(amt), 800, YELLOW)
                try:
                    self.sfx.play('heal', 0.6)
                except Exception:
                    pass
                self.log.add(f"{act.get('actor_name','Priest')} heals {t.name} for {t.hp - before}.")
        elif act['type'] == 'run':
            if act.get('success'):
                self.log.add("You fled!")
                self.battle_over = True
                self.result = 'fled'
            else:
                self.log.add("You failed to run!")

    def check_end_and_maybe_finish(self) -> bool:
        if not self.enemy_alive():
            self.finish_victory()
            return True
        if not self.party.any_active_alive():
            self.finish_defeat()
            return True
        return False

    def finish_victory(self):
        # If any defeat animations are still running, delay victory finalize
        if self.dying_enemies:
            # try again after animations complete
            self.next_after_anim = {'actor_side': 'enemy'}  # dummy to keep loop flowing
            return
        total_exp = random.randint(20, 60)
        total_gold = random.randint(10, 40)
        alive = self.party.alive_active_members()
        for m in alive:
            m.exp += total_exp // max(1, len(alive))
        # Gold now goes to the party pool
        self.party.gold += total_gold
        # Do not log battle results here; show them only on the Victory screen
        # Record for victory screen
        self.victory_exp = total_exp
        self.victory_gold = total_gold
        self.battle_over = True
        self.result = 'victory'

    def finish_defeat(self):
        self.log.add("The party has fallen...")
        self.battle_over = True
        self.result = 'defeat'

    # ---- Player action creators ----
    def make_attack_action(self, actor: Character, target_i: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if target_i is None:
            target_i = next((i for i, e in enumerate(self.enemies) if e.hp > 0), None)
        if target_i is None:
            return None
        e = self.enemies[target_i]
        hit_chance = 0.65 + actor.atk_bonus * 0.03 - (10 - e.ac) * 0.02
        hit = random.random() < hit_chance
        dmg = max(1, random.randint(1, 6) + actor.atk_bonus)
        gi = self.party.members.index(actor)
        return {
            'type': 'attack', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'enemy', 'target_index': target_i,
            'hit': hit, 'dmg': dmg,
            'label': f"{actor.name} hits {e.name} for {dmg}.",
            'miss_label': f"{actor.name} misses {e.name}.",
        }

    def make_spell_action(self, actor: Character, target_i: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if actor.cls != 'Mage' or actor.mp <= 0:
            return None
        if target_i is None:
            target_i = next((i for i, e in enumerate(self.enemies) if e.hp > 0), None)
        if target_i is None:
            return None
        actor.mp -= 1
        dmg = max(1, random.randint(4, 8) + ability_mod(actor.iq))
        gi = self.party.members.index(actor)
        e = self.enemies[target_i]
        return {
            'type': 'spell', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'enemy', 'target_index': target_i,
            'hit': True, 'dmg': dmg,
            'label': f"{actor.name} casts Spark for {dmg}!",
        }

    def make_heal_action(self, actor: Character, target_gi: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if actor.cls != 'Priest' or actor.mp <= 0:
            return None
        if target_gi is None:
            target = min((m for m in self.party.active_members() if m.alive), key=lambda c: c.hp / max(1, c.max_hp), default=None)
            if not target:
                return None
            target_gi = self.party.members.index(target)
        actor.mp -= 1
        amt = max(1, random.randint(6, 10) + ability_mod(actor.piety))
        gi = self.party.members.index(actor)
        return {
            'type': 'heal', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'party', 'target_index': target_gi,
            'heal': amt, 'actor_name': actor.name,
        }

    def make_run_action(self) -> Dict[str, Any]:
        success = random.random() < 0.55
        gi = self.current_actor_global_ix()
        return {'type': 'run', 'actor_side': 'party', 'actor_index': gi, 'success': success}


# ------------------------------ Game ---------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Dankest Deilou")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.r = Renderer(self.screen)
        self.log = MessageLog()
        self.party = Party()
        # New games start with party-level gold and no items
        self.party.gold = 100
        self.party.inventory = []
        self.mode = MODE_TITLE
        self.return_mode = MODE_TOWN

        self.dun = Dungeon(MAZE_W, MAZE_H)
        self.level_ix = 0
        self.dun.ensure_level(0)
        self.pos = (2, 2)
        self.facing = 1
        self.effects = HitEffects()
        self.in_battle: Optional[Battle] = None
        # Subtle battle background ripples (centers and phase)
        self.ripple_centers: List[Tuple[int, int]] = [
            (WIDTH // 2, VIEW_H // 3),
            (WIDTH // 3, VIEW_H * 2 // 3),
            (WIDTH * 2 // 3, VIEW_H // 2),
        ]
        self.ripple_phase: float = 0.0

        # Music
        self.music = MusicManager()
        # Sound effects
        self.sfx = SfxManager()
        # Hook sfx into message log for typewriter clicks
        try:
            self.log.set_sfx(self.sfx)
        except Exception:
            pass

        # Smooth maze movement animation
        self.move_active: bool = False
        self.move_from: Tuple[int, int] = (0, 0)
        self.move_to: Tuple[int, int] = (0, 0)
        self.move_t0: int = 0
        self.move_dur: int = 320  # ms
        self.move_step_sfx_count: int = 0  # 0,1 -> two footfalls per step

        # Data
        self.items_list: List[Dict[str, Any]] = []
        self.items_by_id: Dict[str, Dict[str, Any]] = {}
        self.monsters_by_id: Dict[str, Dict[str, Any]] = {}
        self.skills_config: Dict[str, List[Dict[str, Any]]] = {}
        self.load_data()
        # Battle intro transition
        self.combat_intro_active: bool = False
        self.combat_intro_stage: int = 0  # 0 flash1, 1 pause, 2 flash2, 3 fade
        self.combat_intro_t0: int = 0
        self.combat_intro_done_triggered: bool = False

        self.menu_index = 0
        self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
        self.create_confirm_index = 0
        # Shop UI state
        self.shop_phase = 'menu'  # 'menu' | 'buy_items' | 'sell_items' | 'buy_confirm' | 'sell_confirm'
        self.shop_confirm_ix = 1  # 0 Yes, 1 No
        self.shop_pending_iid: Optional[str] = None
        self.shop_pending_name: str = ''
        self.shop_pending_gold: int = 0
        self.shop_index = 0       # generic index for current phase
        self.shop_buy_ix = 0
        self.shop_target_ix = 0
        self.shop_sell_member_ix = 0
        self.shop_sell_item_ix = 0
        self.shop_pending_item: Optional[str] = None
        self.pause_index = 0
        self.pause_confirming_quit = False
        self.pause_confirm_index = 1  # default to No

        # Items UI state (party inventory focused)
        self.items_phase = 'items'  # 'items' | 'item_action' | 'use_target'
        self.items_item_ix = 0
        self.items_action_ix = 0
        self.items_target_ix = 0
        self.items_selected_iid: Optional[str] = None

        # Equip UI state
        self.equip_phase = 'member'  # 'member' | 'slot' | 'choose'
        self.equip_member_ix = 0
        self.equip_slot_ix = 0  # 0 Weapon, 1 Armor, 2 Acc1, 3 Acc2
        self.equip_choose_ix = 0

        # Tavern UI state
        self.party_mode: str = 'menu'  # 'menu' | 'dismiss_select' | 'dismiss_confirm'
        self.party_actions_index = 0
        self.party_dismiss_index = 0
        self.party_confirm_index = 0

        # Status screen state
        self.status_phase = 'select'
        self.status_index = 0

        # Save/Load menu index
        self.saveload_index = 0
        # Title screen menu index
        self.title_index = 0

        # Temple UI state
        self.temple_phase = 'menu'  # 'menu' | 'revive'
        self.temple_menu_index = 0  # 0 Heal party, 1 Revive member
        self.temple_revive_index = 0

        self.encounter_rate = 0.22
        # Victory screen info
        self.victory_info: Dict[str, Any] = {}
        # Victory typewriter
        self.victory_type_t0: int = 0
        self.victory_type_chars: int = 0
        self.victory_type_cps: float = 24.0  # chars per second (much slower)
        self.victory_text_lines: List[str] = []
        self.victory_done: bool = False
        self.victory_type_last_sfx: int = 0
        # Defeat screen fade
        self.defeat_t0: int = 0

        # Track mode transitions for audio changes
        self._last_mode: Optional[str] = None

        # Scene transition (town <-> labyrinth)
        self.scene_active: bool = False
        self.scene_from: Optional[str] = None
        self.scene_to: Optional[str] = None
        self.scene_stage: int = 0  # 0 fade-out, 1 hold, 2 fade-in
        self.scene_t0: int = 0
        self.scene_dur: Tuple[int, int, int] = (0, 0, 0)


    def load_json(self, path: str, default):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default

    def load_data(self):
        # Items
        items = self.load_json(os.path.join('data', 'items.json'), [])
        self.items_list = items
        self.items_by_id = {it.get('id'): it for it in items if it.get('id')}
        # Shop stock (ids) — if not present, default to all items
        stock_path = os.path.join('data', 'shop.json')
        try:
            with open(stock_path) as f:
                stock_ids = json.load(f)
        except Exception:
            stock_ids = [it.get('id') for it in items if it.get('id')]
        # Expose to module-level for existing code paths
        global SHOP_ITEMS, ITEMS_BY_ID
        ITEMS_BY_ID = self.items_by_id
        SHOP_ITEMS = [self.items_by_id[i] for i in stock_ids if i in self.items_by_id]
        # Monsters
        monsters = self.load_json(os.path.join('data', 'monsters.json'), [])
        self.monsters_by_id = {m.get('id'): m for m in monsters if m.get('id')}
        # Skills
        skills = self.load_json(os.path.join('data', 'skills.json'), {})
        self.skills_config = skills.get('classes', {})

    # --------------- Audio / Music ---------------
    def on_mode_changed(self, old_mode: Optional[str], new_mode: str):
        # Crossfade between town and labyrinth; immediate start for battle; fade out on victory.
        # Intercept town <-> maze transitions to run a longer fade-to-black scene transition
        if (old_mode in (MODE_TOWN, MODE_MAZE)) and (new_mode in (MODE_TOWN, MODE_MAZE)):
            # Start visual transition
            # Longer timings to make the fade more noticeable
            fade_out, hold, fade_in = 1000, 300, 1100
            # Use old_mode as the from-scene to avoid flashing the target early
            self.start_scene_transition(old_mode, new_mode, fade_out, hold, fade_in)
            # Start a slightly longer music crossfade to match the scene change
            total = fade_out + hold + fade_in
            if self.music.enabled:
                if new_mode == MODE_TOWN:
                    self.music.crossfade_to('town', fade_ms=total)
                else:
                    self.music.crossfade_to('labyrinth', fade_ms=total)
            return
        # Ignore events from transition finishing
        if old_mode == MODE_SCENE:
            return
        if not self.music.enabled:
            return
        try:
            if new_mode == MODE_TOWN:
                self.music.crossfade_to('town', fade_ms=1200)
            elif new_mode == MODE_MAZE:
                self.music.crossfade_to('labyrinth', fade_ms=1200)
            elif new_mode in (MODE_COMBAT_INTRO, MODE_BATTLE):
                # Start battle immediately (no crossfade)
                self.music.play_immediate('battle')
            elif new_mode == MODE_VICTORY:
                # Fade the battle music to silence over 3 seconds
                self.music.fade_out_all(fade_ms=3000)
            elif new_mode == MODE_TITLE:
                # Keep title silent; gently fade out anything playing
                self.music.fade_out_all(fade_ms=700)
        except Exception:
            pass

    def start_scene_transition(self, from_mode: str, to_mode: str, fade_out_ms: int, hold_ms: int, fade_in_ms: int):
        self.scene_active = True
        self.scene_from = from_mode  # explicit source visual
        self.scene_to = to_mode
        self.scene_stage = 0
        self.scene_t0 = pygame.time.get_ticks()
        self.scene_dur = (fade_out_ms, hold_ms, fade_in_ms)
        self.mode = MODE_SCENE

    def draw_scene_transition(self):
        # 0: fade-out from scene_from, 1: black hold, 2: fade-in to scene_to
        now = pygame.time.get_ticks()
        fade_out_ms, hold_ms, fade_in_ms = self.scene_dur
        t = now - self.scene_t0
        stage = self.scene_stage
        # Decide which background to render
        if stage == 0:
            # draw from-scene
            if self.scene_from == MODE_TOWN:
                self.draw_town()
            else:
                self.draw_maze()
            # overlay increasing black
            p = max(0.0, min(1.0, t / max(1, fade_out_ms)))
            alpha = int(255 * p)
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
            view.blit(overlay, (0, 0))
            if t >= fade_out_ms:
                self.scene_stage = 1
                self.scene_t0 = now
        elif stage == 1:
            # full black screen during hold
            view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
            view.fill((0, 0, 0))
            if t >= hold_ms:
                self.scene_stage = 2
                self.scene_t0 = now
        else:
            # fade-in to target scene
            if self.scene_to == MODE_TOWN:
                self.draw_town()
            else:
                self.draw_maze()
            p = max(0.0, min(1.0, t / max(1, fade_in_ms)))
            alpha = int(255 * (1.0 - p))
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
            view.blit(overlay, (0, 0))
            if t >= fade_in_ms:
                # end transition
                self.scene_active = False
                self.mode = self.scene_to or MODE_MAZE

    # --------------- Save/Load ---------------
    def save(self, path="save.json"):
        data = {
            "party": self.party.to_dict(),
            "pos": self.pos,
            "facing": self.facing,
            "level": self.level_ix,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.log.add("Game saved.")

    def load(self, path="save.json"):
        if not os.path.exists(path):
            self.log.add("No save file found.")
            return
        with open(path) as f:
            data = json.load(f)
        self.party = Party.from_dict(data.get("party", {}))
        self.level_ix = int(data.get("level", 0))
        self.dun.ensure_level(self.level_ix)
        self.pos = tuple(data.get("pos", (2, 2)))
        self.facing = int(data.get("facing", 1))
        self.log.add("Game loaded.")

    
    def draw_title(self):
        # Fullscreen title screen without bottom log; center title and menu
        screen = self.screen
        screen.fill((12, 12, 18))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        t = pygame.time.get_ticks() / 1000.0
        for i in range(8):
            phase = t * (0.8 + i * 0.07) + i * 0.9
            amp = 10 + i * 2.0
            freq = 0.010 + i * 0.0015
            pts = []
            step = 8
            mid = HEIGHT // 2 + int(math.sin(phase * 0.5) * 12)
            for x in range(0, WIDTH + step, step):
                y = mid + int(math.sin(x * freq + phase) * amp) + int(math.sin(x * freq * 0.5 + phase * 1.7) * amp * 0.25)
                pts.append((x, y))
            col = (120, 140, 220, 22) if i % 2 == 0 else (160, 140, 220, 16)
            if len(pts) >= 2:
                pygame.draw.aalines(overlay, col, False, pts)
        screen.blit(overlay, (0, 0))

        title = "Dankest Deilou"
        options = ["New Game", "Load", "Exit"]

        # Compute menu height to position title above it while keeping composition centered
        pad_y = 10
        text_h = self.r.font.get_height()
        menu_h = text_h * len(options) + pad_y * 2
        title_x = WIDTH // 2 - self.r.font_big.size(title)[0] // 2
        title_y = HEIGHT // 2 - menu_h // 2 - 60
        self.r.text_big(screen, title, (title_x + 2, title_y + 2), (0, 0, 0))
        self.r.text_big(screen, title, (title_x, title_y), YELLOW)

        # Centered menu using full screen height
        if options:
            pad_x, pad_y = 12, 10
            text_w = max(self.r.font.size(s + "  ")[0] for s in options)
            w = text_w + pad_x * 2
            h = text_h * len(options) + pad_y * 2
            x = WIDTH // 2 - w // 2
            y = HEIGHT // 2 - h // 2
            rect = pygame.Rect(x, y, w, h)
            pygame.draw.rect(screen, (16, 16, 20), rect)
            pygame.draw.rect(screen, YELLOW, rect, 2)
            cy = y + pad_y
            for i, s in enumerate(options):
                color = YELLOW if i == self.title_index else WHITE
                prefix = "> " if i == self.title_index else "  "
                self.r.text(screen, prefix + s, (x + pad_x, cy), color)
                cy += text_h
    
    def title_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.title_index = (self.title_index - 1) % 3
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.title_index = (self.title_index + 1) % 3
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                if self.title_index == 0:  # New Game
                    # reset party and resources
                    self.party = Party()
                    self.party.gold = 100
                    self.party.inventory = []
                    self.mode = MODE_TOWN
                elif self.title_index == 1:  # Load
                    path = "save.json"
                    if os.path.exists(path):
                        self.load(path)
                        self.mode = MODE_TOWN
                    else:
                        self.log.add("No save file found.")
                else:  # Exit
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
    # --------------- Town ---------------
    def draw_town(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Town Square", (20, 16))
        self.r.text_small(view, f"Gold: {self.party.gold}", (WIDTH - 140, 20), YELLOW)
        options = [
            "Tavern (Roster)",
            "Form Party (Choose Active)",
            "Status",
            "Training (Level Up)",
            "Temple (Heal/Revive)",
            "Trader (Shop)",
            "Enter the Labyrinth",
            "Equip",
            "Items",
            "Save / Load",
            "Exit to Title",
        ]
        y = 56
        for i, opt in enumerate(options):
            prefix = "> " if i == self.menu_index else "  "
            self.r.text(view, f"{prefix}{i+1}. {opt}", (32, y), YELLOW if i == self.menu_index else WHITE)
            y += 22
        self.r.text_small(view, "Note: You must pick up to 4 active, living members to enter.", (32, y + 6), LIGHT)

    def town_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.menu_index = (self.menu_index - 1) % 11
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % 11
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                self.select_town_option(self.menu_index)
            elif pygame.K_1 <= event.key <= pygame.K_9:
                self.sfx.play('ui_select', 0.6)
                self.select_town_option(event.key - pygame.K_1)

    def select_town_option(self, ix):
        if ix == 0:
            self.mode = MODE_PARTY
            self.party_mode = 'menu'  # auto-open menu
            self.party_actions_index = 0
        elif ix == 1:
            self.mode = MODE_FORM
        elif ix == 2:
            self.return_mode = MODE_TOWN
            self.mode = MODE_STATUS
        elif ix == 3:
            self.mode = MODE_TRAINING
        elif ix == 4:
            self.mode = MODE_TEMPLE
            self.temple_phase = 'menu'
            self.temple_menu_index = 0
        elif ix == 5:
            self.mode = MODE_SHOP
            self.shop_phase = 'menu'
            self.shop_index = 0
        elif ix == 6:
            if not self.party.active:
                self.log.add("Choose up to 4 active members first (Form Party).")
            elif not self.party.all_active_alive():
                self.log.add("All active members must be alive.")
            else:
                self.level_ix = 0
                self.dun.ensure_level(0)
                self.pos = (2, 2)
                self.facing = 1
                self.mode = MODE_MAZE
                self.log.add("You descend into the Labyrinth...")
        elif ix == 7:
            # Equip from town
            self.equip_phase = 'member'
            self.equip_member_ix = 0
            self.equip_slot_ix = 0
            self.equip_choose_ix = 0
            self.return_mode = MODE_TOWN
            self.mode = MODE_EQUIP
        elif ix == 8:
            # Items from town
            self.return_mode = MODE_TOWN
            self.items_phase = 'items'
            self.items_item_ix = 0
            self.mode = MODE_ITEMS
        elif ix == 9:
            self.mode = MODE_SAVELOAD
        elif ix == 10:
            # Exit to title screen
            self.title_index = 0
            self.mode = MODE_TITLE

    # --------------- Party / Tavern ---------------
    def draw_party(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Tavern — Roster", (20, 16))
        y = 50
        for i, m in enumerate(self.party.members):
            active_tag = "*" if i in self.party.active else " "
            self.r.text(view, f"{i+1:>2}{active_tag} {m.name} Lv{m.level} {m.cls}", (32, y)); y += 18
            self.r.text_small(view, f"HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}  AC {m.defense_ac:+}  ATK {m.atk_bonus:+}", (44, y)); y += 14
        # Centered menu (automatically open)
        if self.party_mode == 'menu':
            opts = ["Create", "Dismiss", "Back"]
            self.r.draw_center_menu(opts, self.party_actions_index)
        elif self.party_mode == 'dismiss_select':
            opts = [f"{i+1:>2}. {m.name} — Lv{m.level} {m.cls}" for i, m in enumerate(self.party.members)] or ["(no characters)"]
            self.r.draw_center_menu(opts + ["Back"], self.party_dismiss_index)
        elif self.party_mode == 'dismiss_confirm':
            # darken background
            s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            s.fill((0, 0, 0, 160))
            view.blit(s, (0, 0))
            # message and yes/no menu
            if self.party.members:
                name = self.party.members[self.party_dismiss_index % len(self.party.members)].name
            else:
                name = "(nobody)"
            # draw message above menu
            msg = f"Dismiss {name}?"
            tw = self.r.font_big.size(msg)[0]
            tx = WIDTH // 2 - tw // 2
            ty = VIEW_H // 2 - 80
            self.r.text_big(view, msg, (tx, ty))
            self.r.draw_center_menu(["Yes", "No"], self.party_confirm_index)

    def _dismiss_member(self, ix: int):
        if ix < 0 or ix >= len(self.party.members):
            return
        # adjust active indices
        new_active = []
        for a in self.party.active:
            if a == ix:
                continue
            new_active.append(a - 1 if a > ix else a)
        self.party.active = new_active
        self.party.members.pop(ix)
        self.party.clamp_active()

    def party_input(self, event):
        if event.type == pygame.KEYDOWN:
            if self.party_mode == 'menu':
                opts_len = 3
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.party_actions_index = (self.party_actions_index - 1) % opts_len
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.party_actions_index = (self.party_actions_index + 1) % opts_len
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    choice = self.party_actions_index
                    if choice == 0:  # Create
                        if len(self.party.members) >= ROSTER_MAX:
                            self.log.add("Roster is full.")
                        else:
                            self.mode = MODE_CREATE
                            self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
                    elif choice == 1:  # Dismiss
                        if not self.party.members:
                            self.log.add("No one to dismiss.")
                        else:
                            self.party_mode = 'dismiss_select'
                            self.party_dismiss_index = 0
                    else:  # Back
                        self.mode = MODE_TOWN
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_TOWN
            elif self.party_mode == 'dismiss_select':
                n = max(1, len(self.party.members) + 1)  # +1 for Back
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.party_dismiss_index = (self.party_dismiss_index - 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.party_dismiss_index = (self.party_dismiss_index + 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    if self.party_dismiss_index == len(self.party.members):
                        self.party_mode = 'menu'
                        self.party_actions_index = 1  # keep focus on Dismiss
                    else:
                        self.party_mode = 'dismiss_confirm'
                        self.party_confirm_index = 0
                elif event.key == pygame.K_ESCAPE:
                    self.party_mode = 'menu'
            elif self.party_mode == 'dismiss_confirm':
                if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                    self.party_confirm_index = 1 - self.party_confirm_index  # toggle between 0 and 1
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    if self.party_confirm_index == 0:  # Yes
                        if self.party.members:
                            ix = self.party_dismiss_index % len(self.party.members)
                            name = self.party.members[ix].name
                            self._dismiss_member(ix)
                            self.log.add(f"{name} has been dismissed.")
                        self.party_mode = 'menu'
                        self.party_actions_index = 1
                    else:  # No
                        self.party_mode = 'dismiss_select'
                elif event.key == pygame.K_ESCAPE:
                    self.party_mode = 'dismiss_select'

    # --------------- Form Party ---------------
    def draw_form(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Form Party (max 4)", (20, 16))
        y = 50
        for i, m in enumerate(self.party.members):
            sel = "> " if i == self.menu_index else "  "
            mark = "[*]" if i in self.party.active else "[ ]"
            dead = not (m.alive and m.hp > 0)
            color = GRAY if dead else WHITE
            self.r.text(view, f"{sel}{mark} {i+1:>2} {m.name} Lv{m.level} {m.cls}", (32, y), color); y += 18
        y += 6
        self.r.text_small(view, "Up/Down to select, Space/Enter to toggle, Esc: Back", (32, y), LIGHT)

    def form_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.menu_index = (self.menu_index - 1) % max(1, len(self.party.members))
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % max(1, len(self.party.members))
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                i = self.menu_index
                if i < len(self.party.members):
                    if i in self.party.active:
                        self.party.active.remove(i)
                    else:
                        if len(self.party.active) >= ACTIVE_MAX:
                            self.log.add("Active party is full (max 4).")
                        elif not (self.party.members[i].alive and self.party.members[i].hp > 0):
                            self.log.add("Member must be alive to join active party.")
                        else:
                            self.party.active.append(i)
            elif event.key == pygame.K_ESCAPE:
                self.party.clamp_active()
                self.mode = MODE_TOWN

    # --------------- Status ---------------
    def draw_status(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        if self.status_phase == 'select':
            self.r.text_big(view, "Status — Choose Character", (20, 16))
            options = [f"{i+1:>2}. {m.name} — Lv{m.level} {m.cls}" for i, m in enumerate(self.party.members)] or ["(no characters)"]
            self.r.draw_center_menu(options, 0)
            # selected index visual handled by separate render? adjust call:
            self.r.draw_center_menu(options, self.status_index)
            self.r.text_small(view, "Enter: View  Esc: Back", (32, VIEW_H - 28), LIGHT)
        else:
            if not self.party.members:
                self.status_phase = 'select'
                return
            m = self.party.members[self.status_index % len(self.party.members)]
            # Header
            header_x, header_y = 20, 16
            self.r.text_big(view, f"{m.name}", (header_x, header_y))
            self.r.text(view, f"{m.cls} - Lv {m.level}", (header_x, header_y + 34))
            self.r.text(view, f"HP: {m.hp}/{m.max_hp}", (header_x, header_y + 60))
            self.r.text(view, f"MP: {m.mp}/{m.max_mp}", (header_x, header_y + 84))

            # Columns
            left_x, left_y = 32, header_y + 118
            right_x, right_y = WIDTH // 2 + 20, left_y

            # Left: core stats
            self.r.text(view, f"STR: {m.str_}", (left_x, left_y)); left_y += 20
            self.r.text(view, f"IQ:  {m.iq}", (left_x, left_y)); left_y += 20
            self.r.text(view, f"PIE: {m.piety}", (left_x, left_y)); left_y += 20
            self.r.text(view, f"VIT: {m.vit}", (left_x, left_y)); left_y += 20
            self.r.text(view, f"AGI: {m.agi}", (left_x, left_y)); left_y += 20
            self.r.text(view, f"LCK: {m.luck}", (left_x, left_y)); left_y += 20

            # Right: auxiliary stats
            self.r.text(view, f"ATK: {m.atk_bonus:+}", (right_x, right_y)); right_y += 20
            self.r.text(view, f"AC:  {m.defense_ac:+}", (right_x, right_y)); right_y += 20
            self.r.text(view, f"Weapon ATK: +{m.equipment.weapon_atk}", (right_x, right_y)); right_y += 20
            self.r.text(view, f"Armor AC:  {m.equipment.armor_ac:+}", (right_x, right_y)); right_y += 20

            # Hint: how to go back
            self.r.text_small(view, "Enter/Esc: Back", (20, VIEW_H - 28), LIGHT)

    def status_input(self, event):
        if event.type == pygame.KEYDOWN:
            if self.status_phase == 'select':
                n = max(1, len(self.party.members))
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.status_index = (self.status_index - 1) % n
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.status_index = (self.status_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.party.members:
                        self.status_phase = 'detail'
                elif event.key == pygame.K_ESCAPE:
                    self.mode = self.return_mode
            else:
                if event.key in (pygame.K_LEFT, pygame.K_h):
                    n = max(1, len(self.party.members))
                    self.status_index = (self.status_index - 1) % n
                elif event.key in (pygame.K_RIGHT, pygame.K_l):
                    n = max(1, len(self.party.members))
                    self.status_index = (self.status_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                    self.status_phase = 'select'
                    if self.return_mode != MODE_STATUS:
                        self.mode = self.return_mode

    # --------------- Creation ---------------
    def draw_create(self):
        s = self.create_state
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Create Adventurer", (20, 16))
        y = 60
        if s["step"] == 0:
            self.r.text(view, "Enter name:", (32, y))
            self.r.text(view, s["name"] + "_", (260, y), YELLOW)
            self.r.text_small(view, "Enter to confirm", (32, y + 28), LIGHT)
        elif s["step"] == 1:
            # Race list menu
            self.r.text(view, "Choose Race (Enter)", (32, y))
            self.r.draw_center_menu(RACES, s["race_ix"])
            self.r.text_small(view, "↑/↓ to move, Enter to confirm", (32, VIEW_H - 28), LIGHT)
        elif s["step"] == 2:
            # Class list with prices
            self.r.text(view, "Choose Class (Enter)", (32, y))
            class_opts = [f"{c} — {CLASS_COSTS.get(c,0)}g" for c in CLASSES]
            self.r.draw_center_menu(class_opts, s["class_ix"])
            # Show party gold and affordability
            chosen = CLASSES[s["class_ix"]]
            cost = CLASS_COSTS.get(chosen, 0)
            col = YELLOW if self.party.gold >= cost else RED
            self.r.text_small(view, f"Gold: {self.party.gold}g  Selected cost: {cost}g", (32, VIEW_H - 28), col)
        elif s["step"] == 3:
            temp = Character(s["name"], RACES[s["race_ix"]], CLASSES[s["class_ix"]])
            self.r.text(view, f"Name: {temp.name}", (32, y))
            self.r.text(view, f"Race: {temp.race}  Class: {temp.cls}", (32, y + 20))
            y2 = y + 44
            stats = [("STR", temp.str_), ("IQ", temp.iq), ("PIE", temp.piety), ("VIT", temp.vit), ("AGI", temp.agi), ("LCK", temp.luck)]
            for i, (k, v) in enumerate(stats):
                self.r.text(view, f"{k}:{v:2d}", (32 + (i % 3) * 120, y2 + (i // 3) * 20))
            self.r.text(view, f"HP {temp.max_hp}  MP {temp.mp}", (32, y2 + 44))
            # Show recruit cost and party gold
            cost = CLASS_COSTS.get(temp.cls, 0)
            self.r.text(view, f"Cost: {cost}g    Party Gold: {self.party.gold}", (32, y2 + 66), YELLOW if self.party.gold >= cost else RED)
            self.r.draw_center_menu(["Accept", "Reroll", "Cancel"], self.create_confirm_index)

    def create_input(self, event):
        s = self.create_state
        if event.type == pygame.KEYDOWN:
            if s["step"] == 0:
                if event.key == pygame.K_RETURN:
                    if s["name"].strip():
                        s["step"] = 1
                elif event.key == pygame.K_BACKSPACE:
                    s["name"] = s["name"][:-1]
                else:
                    ch = event.unicode
                    if ch.isprintable() and len(s["name"]) < 16:
                        s["name"] += ch
            elif s["step"] == 1:
                if event.key in (pygame.K_UP, pygame.K_k):
                    s["race_ix"] = (s["race_ix"] - 1) % len(RACES)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    s["race_ix"] = (s["race_ix"] + 1) % len(RACES)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s["step"] = 2
                elif event.key == pygame.K_ESCAPE:
                    s["step"] = 0
            elif s["step"] == 2:
                if event.key in (pygame.K_UP, pygame.K_k):
                    s["class_ix"] = (s["class_ix"] - 1) % len(CLASSES)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    s["class_ix"] = (s["class_ix"] + 1) % len(CLASSES)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s["step"] = 3
                elif event.key == pygame.K_ESCAPE:
                    s["step"] = 1
            elif s["step"] == 3:
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.create_confirm_index = (self.create_confirm_index - 1) % 3
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.create_confirm_index = (self.create_confirm_index + 1) % 3
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    choice = self.create_confirm_index
                    if choice == 0:  # Accept
                        if len(self.party.members) >= ROSTER_MAX:
                            self.log.add("Roster is full.")
                        else:
                            cls = CLASSES[s["class_ix"]]
                            cost = CLASS_COSTS.get(cls, 0)
                            if self.party.gold < cost:
                                self.log.add(f"Not enough gold to recruit a {cls}.")
                            else:
                                self.party.gold -= cost
                                newc = Character(s["name"], RACES[s["race_ix"]], cls)
                                self.party.members.append(newc)
                                self.log.add(f"{newc.name} the {newc.cls} joins the roster (-{cost}g).")
                        self.mode = MODE_PARTY
                        self.party_mode = 'menu'
                        self.party_actions_index = 0
                    elif choice == 1:  # Reroll
                        s["step"] = 2; s["step"] = 3
                    else:  # Cancel
                        self.mode = MODE_PARTY
                        self.party_mode = 'menu'
                        self.party_actions_index = 0
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_PARTY
                    self.party_mode = 'menu'
                    self.party_actions_index = 0

    # --------------- Shop / Temple / Training ---------------
    def draw_shop(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Trader", (20, 16))
        self.r.text_small(view, f"Gold: {self.party.gold}", (WIDTH - 140, 20), YELLOW)
        y = 56
        if self.shop_phase == 'menu':
            opts = ["Buy", "Sell", "Back"]
            for i, s in enumerate(opts):
                prefix = "> " if i == self.shop_index else "  "
                col = YELLOW if i == self.shop_index else WHITE
                self.r.text(view, f"{prefix}{s}", (32, y), col); y += 22
            self.r.text_small(view, "Enter: Select  Esc: Back", (32, y + 4), LIGHT)
        elif self.shop_phase == 'buy_items':
            # Centered menu: item names only + Back
            labels = [it.get('name', it.get('id', 'Item')) for it in SHOP_ITEMS]
            options = labels + ["Back"] if labels else ["Back"]
            if not hasattr(self, 'shop_buy_ix'):
                self.shop_buy_ix = 0
            self.shop_buy_ix = self.shop_buy_ix % max(1, len(options))
            self.r.draw_center_menu(options, self.shop_buy_ix)
        elif self.shop_phase == 'buy_confirm':
            # Darken and show confirmation
            s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            s.fill((0,0,0,160)); view.blit(s,(0,0))
            name = self.shop_pending_name or 'Item'
            gold = self.shop_pending_gold
            msg = f"Do you want to buy {name} for {gold}g?"
            tw = self.r.font_big.size(msg)[0]
            tx = WIDTH//2 - tw//2
            ty = VIEW_H//2 - 80
            self.r.text_big(view, msg, (tx, ty))
            self.r.draw_center_menu(["Yes","No"], self.shop_confirm_ix)
        else:  # sell_items
            # Condensed list with quantities, centered menu (names only)
            ordered: List[str] = []
            counts: Dict[str, int] = {}
            for iid in self.party.inventory:
                if iid not in counts:
                    counts[iid] = 1
                    ordered.append(iid)
                else:
                    counts[iid] += 1
            labels = []
            for iid in ordered:
                name = ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid)
                c = counts.get(iid, 1)
                labels.append(f"{name} x{c}" if c > 1 else name)
            options = labels + ["Back"] if labels else ["Back"]
            if not hasattr(self, 'shop_sell_item_ix'):
                self.shop_sell_item_ix = 0
            self.shop_sell_item_ix = self.shop_sell_item_ix % max(1, len(options))
            self.r.draw_center_menu(options, self.shop_sell_item_ix)
        if self.shop_phase == 'sell_confirm':
            s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            s.fill((0,0,0,160)); view.blit(s,(0,0))
            name = self.shop_pending_name or 'Item'
            gold = self.shop_pending_gold
            msg = f"Do you want to sell {name} for {gold}g?"
            tw = self.r.font_big.size(msg)[0]
            tx = WIDTH//2 - tw//2
            ty = VIEW_H//2 - 80
            self.r.text_big(view, msg, (tx, ty))
            self.r.draw_center_menu(["Yes","No"], self.shop_confirm_ix)

    def shop_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        # Phase: menu
        if self.shop_phase == 'menu':
            if event.key in (pygame.K_UP, pygame.K_k):
                self.shop_index = (self.shop_index - 1) % 3
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.shop_index = (self.shop_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.shop_index == 0:
                    self.shop_phase = 'buy_items'; self.shop_buy_ix = 0
                elif self.shop_index == 1:
                    self.shop_phase = 'sell_items'; self.shop_sell_item_ix = 0
                else:
                    self.mode = MODE_TOWN
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN
        # Phase: buy_items
        elif self.shop_phase == 'buy_items':
            n = max(1, len(SHOP_ITEMS) + 1)  # +1 Back
            if event.key in (pygame.K_UP, pygame.K_k):
                self.shop_buy_ix = (self.shop_buy_ix - 1) % n
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.shop_buy_ix = (self.shop_buy_ix + 1) % n
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.shop_buy_ix == len(SHOP_ITEMS):
                    self.shop_phase = 'menu'; self.shop_index = 0
                else:
                    it = SHOP_ITEMS[self.shop_buy_ix]
                    self.shop_pending_iid = it.get('id', '')
                    self.shop_pending_name = it.get('name', 'Item')
                    self.shop_pending_gold = int(it.get('price', 0))
                    self.shop_confirm_ix = 1
                    self.shop_phase = 'buy_confirm'
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'menu'; self.shop_index = 0
        # Phase: buy_confirm
        elif self.shop_phase == 'buy_confirm':
            if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                self.shop_confirm_ix = 1 - self.shop_confirm_ix
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.shop_confirm_ix == 0:
                    price = self.shop_pending_gold
                    if self.party.gold < price:
                        self.log.add("Not enough gold.")
                    else:
                        self.party.gold -= price
                        if self.shop_pending_iid:
                            self.party.inventory.append(self.shop_pending_iid)
                        self.log.add(f"Bought {self.shop_pending_name}.")
                self.shop_phase = 'buy_items'
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'buy_items'
        # Phase: sell_items
        elif self.shop_phase == 'sell_items':
            seen=set(); ordered=[]
            for iid in self.party.inventory:
                if iid not in seen:
                    seen.add(iid); ordered.append(iid)
            n = max(1, len(ordered) + 1)  # +1 Back
            if event.key in (pygame.K_UP, pygame.K_k):
                self.shop_sell_item_ix = (self.shop_sell_item_ix - 1) % n
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.shop_sell_item_ix = (self.shop_sell_item_ix + 1) % n
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.shop_sell_item_ix == len(ordered):
                    self.shop_phase = 'menu'; self.shop_index = 1
                else:
                    if not ordered:
                        return
                    iid_sel = ordered[self.shop_sell_item_ix]
                    it = ITEMS_BY_ID.get(iid_sel, {"price": 10, "name": iid_sel})
                    sellp = int(it.get('price', 10) * 0.5)
                    self.shop_pending_iid = iid_sel
                    self.shop_pending_name = it.get('name', iid_sel)
                    self.shop_pending_gold = sellp
                    self.shop_confirm_ix = 1
                    self.shop_phase = 'sell_confirm'
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'menu'; self.shop_index = 1
        # Phase: sell_confirm
        elif self.shop_phase == 'sell_confirm':
            if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                self.shop_confirm_ix = 1 - self.shop_confirm_ix
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.shop_confirm_ix == 0:
                    try:
                        self.party.inventory.remove(self.shop_pending_iid or '')
                    except ValueError:
                        pass
                    self.party.gold += int(self.shop_pending_gold)
                    self.log.add(f"Sold {self.shop_pending_name} for {self.shop_pending_gold}g.")
                self.shop_phase = 'sell_items'
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'sell_items'

    def draw_temple(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Temple", (20, 16))
        any_dead = any(not m.alive for m in self.party.members)
        if self.temple_phase == 'menu':
            opts = ["Heal Party", "Revive Member"]
            enabled = [True, any_dead]
            y = 64
            for i, opt in enumerate(opts):
                is_sel = (i == self.temple_menu_index)
                col = YELLOW if is_sel and enabled[i] else (GRAY if not enabled[i] else WHITE)
                prefix = "> " if is_sel else "  "
                self.r.text(view, f"{prefix}{opt}", (32, y), col)
                y += 24
            self.r.text_small(view, f"Gold: {self.party.gold}", (WIDTH - 140, 20), YELLOW)
            if self.temple_menu_index == 0:
                self.r.text_small(view, f"Cost: {TEMPLE_HEAL_PARTY_COST}g — heals all living members", (32, y + 6), LIGHT)
            else:
                self.r.text_small(view, f"Select to choose a fallen ally to revive", (32, y + 6), LIGHT)
        else:
            # Revive list: show dead members with per-level cost
            dead = [(i, m) for i, m in enumerate(self.party.members) if not m.alive]
            options = [f"{m.name} — Lv{m.level} ({REVIVE_BASE_COST + REVIVE_PER_LEVEL * m.level}g)" for _, m in dead] or ["(no one to revive)"]
            # Show a Back item
            opts = options + ["Back"]
            idx = min(self.temple_revive_index, len(opts) - 1)
            self.r.draw_center_menu(opts, idx)
            self.r.text_small(view, f"Gold: {self.party.gold}", (WIDTH - 140, 20), YELLOW)

    def temple_input(self, event):
        if event.type == pygame.KEYDOWN:
            if self.temple_phase == 'menu':
                any_dead = any(not m.alive for m in self.party.members)
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.temple_menu_index = (self.temple_menu_index - 1) % 2
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.temple_menu_index = (self.temple_menu_index + 1) % 2
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.temple_menu_index == 0:
                        # Heal party for fixed cost (alive members only)
                        living = [m for m in self.party.members if m.alive]
                        if not living:
                            self.log.add("No one to heal.")
                            return
                        need = any(m.hp < m.max_hp for m in living)
                        if not need:
                            self.log.add("Everyone is already at full HP.")
                            return
                        if self.party.gold >= TEMPLE_HEAL_PARTY_COST:
                            self.party.gold -= TEMPLE_HEAL_PARTY_COST
                            for m in living:
                                m.hp = m.max_hp
                            self.log.add("The party is fully healed.")
                        else:
                            self.log.add("Not enough gold to heal party.")
                    else:
                        if any_dead:
                            self.temple_phase = 'revive'
                            self.temple_revive_index = 0
                        else:
                            # Disabled: no action when no one is dead
                            pass
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_TOWN
            else:
                # revive list
                dead = [(i, m) for i, m in enumerate(self.party.members) if not m.alive]
                n = max(1, len(dead) + 1)  # +1 for Back
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.temple_revive_index = (self.temple_revive_index - 1) % n
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.temple_revive_index = (self.temple_revive_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.temple_revive_index == len(dead):
                        # Back
                        self.temple_phase = 'menu'
                        self.temple_menu_index = 0
                    else:
                        gi, m = dead[self.temple_revive_index]
                        cost = REVIVE_BASE_COST + REVIVE_PER_LEVEL * m.level
                        if self.party.gold >= cost:
                            self.party.gold -= cost
                            m.alive = True
                            m.hp = max(1, m.max_hp // 2)
                            self.log.add(f"{m.name} is revived.")
                            # After revive, recompute dead list and adjust index
                            dead = [(i, mm) for i, mm in enumerate(self.party.members) if not mm.alive]
                            if not dead:
                                self.temple_phase = 'menu'
                                self.temple_menu_index = 0
                            else:
                                self.temple_revive_index = min(self.temple_revive_index, len(dead) - 1)
                        else:
                            self.log.add("Not enough gold to revive.")
                elif event.key == pygame.K_ESCAPE:
                    self.temple_phase = 'menu'

    def draw_training(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Training Grounds", (20, 16))
        y = 56
        self.r.text_small(view, "Each level costs 100 EXP.", (32, y)); y += 18
        # Build menu: list party members (if any) + Back. Ensure index wraps across all entries.
        member_count = len(self.party.members)
        options = [f"{m.name} — Lv{m.level}  EXP {m.exp}" for m in self.party.members] if member_count > 0 else []
        if not hasattr(self, 'training_index'):
            self.training_index = 0
        total_entries = max(1, member_count + 1)  # members + Back, or just Back if none
        self.training_index = self.training_index % total_entries
        display = options + ["Back"] if member_count > 0 else ["Back"]
        self.r.draw_center_menu(display, self.training_index)

    def training_input(self, event):
        if event.type == pygame.KEYDOWN:
            n = max(1, len(self.party.members) + 1)
            if event.key in (pygame.K_UP, pygame.K_k):
                self.training_index = (self.training_index - 1) % n
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.training_index = (self.training_index + 1) % n
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.training_index == len(self.party.members):
                    self.mode = MODE_TOWN
                else:
                    m = self.party.members[self.training_index]
                    if m.exp >= 100:
                        m.exp -= 100
                        m.level += 1
                        gain = random.randint(2, 6)
                        m.max_hp += gain
                        m.hp = m.max_hp
                        if m.cls in ("Mage", "Priest"):
                            m.max_mp += 1
                            m.mp = m.max_mp
                        self.log.add(f"{m.name} reached Lv{m.level}! +{gain} HP")
                    else:
                        self.log.add("Not enough EXP.")
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    # --------------- Save/Load ---------------
    def draw_saveload(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Save / Load", (20, 16))
        opts = ["Save", "Load", "Back"]
        self.r.draw_center_menu(opts, self.saveload_index)

    def saveload_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.saveload_index = (self.saveload_index - 1) % 3
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.saveload_index = (self.saveload_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.saveload_index == 0:
                    self.save()
                elif self.saveload_index == 1:
                    self.load()
                else:
                    self.mode = MODE_TOWN
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    # --------------- Maze Helpers ---------------
    def grid(self) -> List[List[int]]:
        return self.dun.levels[self.level_ix].grid

    def in_bounds(self, x, y):
        return self.dun.in_bounds(x, y)

    def is_open(self, x, y):
        g = self.grid()
        return self.in_bounds(x, y) and g[y][x] != T_WALL

    def step_forward(self):
        dx, dy = DIRS[self.facing]
        nx, ny = self.pos[0] + dx, self.pos[1] + dy
        if self.is_open(nx, ny):
            # Begin smooth movement animation
            if not self.move_active:
                self.move_active = True
                self.move_from = self.pos
                self.move_to = (nx, ny)
                self.move_t0 = pygame.time.get_ticks()
                self.move_step_sfx_count = 0
        else:
            self.log.add("You bump into a wall.")

    def turn_left(self):
        self.facing = (self.facing - 1) % 4

    def turn_right(self):
        self.facing = (self.facing + 1) % 4

    def check_special_tile(self):
        x, y = self.pos
        t = self.grid()[y][x]
        if t == T_TOWN:
            self.mode = MODE_TOWN
            self.log.add("You return to town.")
        elif t == T_STAIRS_D:
            self.go_down_stairs()
        elif t == T_STAIRS_U:
            self.go_up_stairs()

    def go_down_stairs(self):
        cur = self.dun.levels[self.level_ix]
        down_pos = cur.stairs_down or self.pos
        self.level_ix += 1
        self.dun.ensure_level(self.level_ix, arrival_pos=down_pos)
        self.pos = down_pos
        self.facing = 1
        self.mode = MODE_MAZE
        self.log.add(f"Descend to level {self.level_ix}.")

    def go_up_stairs(self):
        if self.level_ix == 0:
            self.log.add("You are at the surface level.")
            return
        prev_level = self.level_ix - 1
        self.level_ix = prev_level
        self.dun.ensure_level(self.level_ix)
        target = self.dun.levels[self.level_ix].stairs_down or (2, 2)
        self.pos = target
        self.facing = 1
        self.mode = MODE_MAZE
        self.log.add(f"Ascend to level {self.level_ix}.")

    def start_battle(self):
        self.in_battle = Battle(self.party, self.log, self.effects, self.items_by_id, self.monsters_by_id, self.skills_config, self.sfx)
        # Use level-specific encounter config if available
        lvl = self.dun.levels[self.level_ix]
        allowed = lvl.encounter_monsters or list(self.monsters_by_id.keys())
        group = getattr(lvl, 'encounter_group', (1,3))
        self.in_battle.start_random(allowed=allowed, group=group)
        # Begin transition on the labyrinth view first
        self.mode = MODE_COMBAT_INTRO
        self.combat_intro_active = True
        self.combat_intro_stage = 0  # flashes happen in maze
        self.combat_intro_t0 = pygame.time.get_ticks()
        self.combat_intro_done_triggered = False

    def draw_maze(self):
        # Smooth movement offsets during walking animation
        shift_tiles = (0.0, 0.0)
        bob_px = 0
        move_p = 0.0
        if self.move_active:
            dx, dy = DIRS[self.facing]
            now = pygame.time.get_ticks()
            move_p = max(0.0, min(1.0, (now - self.move_t0) / max(1, self.move_dur)))
            shift_tiles = (-dx * move_p, -dy * move_p)
            # Two bops over the duration
            amp = 4
            bob_px = int(-abs(math.sin(move_p * math.pi * 2)) * amp)
        # fractional player offset in tiles for FOV center
        frac = (0.0, 0.0)
        if self.move_active:
            dx, dy = DIRS[self.facing]
            frac = (dx * move_p, dy * move_p)
        self.r.draw_topdown(self.grid(), self.pos, self.facing, self.level_ix, shift_tiles, bob_px, frac)
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        self.r.text_small(view, "Esc: Menu  ↑: Move  ←/→: Turn", (12, VIEW_H - 22), LIGHT)
        # During combat intro flashes, overlay on maze
        if self.mode == MODE_COMBAT_INTRO and self.combat_intro_active:
            now = pygame.time.get_ticks()
            t = now - self.combat_intro_t0
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            if self.combat_intro_stage in (0, 2):
                alpha = 220 if (self.combat_intro_stage == 0 and t < 180) or (self.combat_intro_stage == 2 and t < 180) else 0
                overlay.fill((255, 255, 255, alpha))
            view.blit(overlay, (0, 0))

    def maze_input(self, event):
        if event.type == pygame.KEYDOWN:
            if self.move_active:
                # ignore movement/turn keys during step animation
                return
            if event.key == pygame.K_LEFT:
                self.turn_left()
            elif event.key == pygame.K_RIGHT:
                self.turn_right()
            elif event.key == pygame.K_UP:
                self.step_forward()
            elif event.key == pygame.K_ESCAPE:
                self.pause_index = 0
                self.mode = MODE_PAUSE

    # --------------- Pause Menu & Items ---------------
    def draw_pause(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 160))
        view.blit(s, (0, 0))
        if self.pause_confirming_quit:
            # Confirm quit prompt
            self.r.text_big(view, "Are you sure?", (WIDTH//2 - 100, 100), YELLOW)
            self.r.draw_center_menu(["Yes", "No"], self.pause_confirm_index)
        else:
            self.r.text_big(view, "Menu", (WIDTH//2 - 40, 80))
            opts = ["Status", "Items", "Equip", "Quit", "Close"]
            y = 140
            for i, opt in enumerate(opts):
                prefix = "> " if i == self.pause_index else "  "
                self.r.text(view, f"{prefix}{opt}", (WIDTH//2 - 80, y), YELLOW if i == self.pause_index else WHITE)
                y += 24

    def pause_input(self, event):
        if event.type == pygame.KEYDOWN:
            if self.pause_confirming_quit:
                # Handle Yes/No
                if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                    self.pause_confirm_index = 1 - self.pause_confirm_index
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.pause_confirm_index == 0:  # Yes
                        self.title_index = 0
                        self.pause_confirming_quit = False
                        self.mode = MODE_TITLE
                    else:  # No
                        self.pause_confirming_quit = False
                        self.mode = MODE_MAZE
                elif event.key == pygame.K_ESCAPE:
                    self.pause_confirming_quit = False
                    self.mode = MODE_MAZE
            else:
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.pause_index = (self.pause_index - 1) % 5
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.pause_index = (self.pause_index + 1) % 5
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.pause_index == 0:
                        self.return_mode = MODE_PAUSE
                        self.mode = MODE_STATUS
                    elif self.pause_index == 1:
                        # Items opened from Labyrinth; return to Maze when exiting
                        self.return_mode = MODE_MAZE
                        self.items_phase = 'items'
                        self.items_item_ix = 0
                        self.mode = MODE_ITEMS
                    elif self.pause_index == 2:
                        self.equip_phase = 'member'
                        self.equip_member_ix = 0
                        self.equip_slot_ix = 0
                        self.equip_choose_ix = 0
                        self.return_mode = MODE_PAUSE
                        self.mode = MODE_EQUIP
                    elif self.pause_index == 3:
                        # Quit -> confirm prompt
                        self.pause_confirming_quit = True
                        self.pause_confirm_index = 1  # default to No
                    elif self.pause_index == 4:
                        self.mode = MODE_MAZE
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_MAZE

    def draw_items(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        # Header
        self.r.text_big(view, "Party Items", (20, 16))
        # Centered menu interface for Items
        if self.items_phase == 'items':
            # Build condensed inventory with quantities, preserving order of first appearance
            ordered: List[str] = []
            counts: Dict[str, int] = {}
            for iid in self.party.inventory:
                if iid not in counts:
                    counts[iid] = 1
                    ordered.append(iid)
                else:
                    counts[iid] += 1
            labels = []
            for iid in ordered:
                name = ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid)
                c = counts.get(iid, 1)
                labels.append(f"{name} x{c}" if c > 1 else name)
            options = labels + ["Back"]
            # Clamp index into range (ordered + Back)
            self.items_item_ix = self.items_item_ix % max(1, len(ordered) + 1)
            self.r.draw_center_menu(options, self.items_item_ix)
        elif self.items_phase == 'item_action':
            self.r.draw_center_menu(["Use", "Cancel"], self.items_action_ix)
        elif self.items_phase == 'use_target':
            actives = self.party.active_members()
            opts = [m.name for m in actives] or ["(no active members)"]
            self.r.draw_center_menu(opts + ["Back"], self.items_target_ix)

    def items_input(self, event):
        actives = self.party.active_members()
        if event.type == pygame.KEYDOWN:
            if self.items_phase == 'items':
                # Condensed inventory for navigation
                ordered: List[str] = []
                counts: Dict[str, int] = {}
                for iid in self.party.inventory:
                    if iid not in counts:
                        counts[iid] = 1
                        ordered.append(iid)
                    else:
                        counts[iid] += 1
                n = max(1, len(ordered) + 1)  # +1 for Back
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.items_item_ix = (self.items_item_ix - 1) % n
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.items_item_ix = (self.items_item_ix + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # If Back selected, return to previous mode
                    if self.items_item_ix == len(ordered):
                        self.mode = self.return_mode
                    else:
                        # Store selected iid from condensed list
                        self.items_selected_iid = ordered[self.items_item_ix]
                        self.items_action_ix = 0
                        self.items_phase = 'item_action'
                elif event.key == pygame.K_ESCAPE:
                    # Return to the mode that opened Items (Town or Maze)
                    self.mode = self.return_mode
            elif self.items_phase == 'item_action':
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.items_action_ix = (self.items_action_ix - 1) % 2
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.items_action_ix = (self.items_action_ix + 1) % 2
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # If no items, go back
                    if not self.party.inventory or not self.items_selected_iid:
                        self.items_phase = 'items'
                    else:
                        iid = self.items_selected_iid
                        it = ITEMS_BY_ID.get(iid, {})
                        if self.items_action_ix == 0:  # Use
                            if it.get('type') == 'consumable':
                                # Choose a target among active members
                                self.items_target_ix = 0
                                self.items_phase = 'use_target'
                            else:
                                self.log.add("Cannot use that here.")
                                self.items_phase = 'items'
                        else:  # Cancel
                            self.items_phase = 'items'
                elif event.key == pygame.K_ESCAPE:
                    self.items_phase = 'items'
            else:  # use_target
                n = max(1, len(actives) + 1)
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.items_target_ix = (self.items_target_ix - 1) % n
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.items_target_ix = (self.items_target_ix + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.items_target_ix == len(actives):
                        self.items_phase = 'item_action'
                    else:
                        if self.party.inventory and actives and self.items_selected_iid:
                            iid = self.items_selected_iid
                            target = actives[self.items_target_ix]
                            self.use_item(target, iid)
                            it = ITEMS_BY_ID.get(iid, {})
                            if it.get('type') == 'consumable':
                                # remove a single instance of the used item
                                try:
                                    self.party.inventory.remove(iid)
                                except ValueError:
                                    pass
                                # Clamp selection to condensed list length
                                ordered_after = []
                                seen = set()
                                for j in self.party.inventory:
                                    if j not in seen:
                                        seen.add(j); ordered_after.append(j)
                                if ordered_after:
                                    self.items_item_ix = min(self.items_item_ix, len(ordered_after) - 1)
                                else:
                                    self.items_item_ix = 0
                        self.items_phase = 'items'
                elif event.key == pygame.K_ESCAPE:
                    self.items_phase = 'item_action'

    def use_item(self, target: Character, iid: str):
        it = ITEMS_BY_ID.get(iid)
        if not it:
            self.log.add("Nothing happens.")
            return
        if it["id"] == "potion_small":
            before = target.hp
            target.hp = min(target.max_hp, target.hp + it.get("heal", 0))
            self.log.add(f"{target.name} drinks a potion (+{target.hp - before} HP).")

    # --------------- Equip ---------------
    def _slot_name(self, ix: int) -> str:
        return ["Weapon", "Armor", "Accessory 1", "Accessory 2"][ix]

    def _equipped_label(self, m: Character, ix: int) -> str:
        if ix == 0:
            iid = m.equipment.weapon_id
            if iid:
                it = ITEMS_BY_ID.get(iid, {"name": iid, "atk": m.equipment.weapon_atk})
                bonus = it.get('atk', m.equipment.weapon_atk)
                return f"{it['name']} (+{bonus} ATK)"
            return "(empty)"
        if ix == 1:
            iid = m.equipment.armor_id
            if iid:
                it = ITEMS_BY_ID.get(iid, {"name": iid, "ac": m.equipment.armor_ac})
                bonus = it.get('ac', m.equipment.armor_ac)
                return f"{it['name']} ({bonus:+} AC)"
            return "(empty)"
        iid = m.equipment.acc1_id if ix == 2 else m.equipment.acc2_id
        if iid:
            it = ITEMS_BY_ID.get(iid, {"name": iid})
            return it.get('name', iid)
        return "(empty)"

    def draw_equip(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Equip", (20, 16))
        if self.equip_phase == 'member':
            y = 60
            for i, m in enumerate(self.party.members):
                prefix = "> " if i == self.equip_member_ix else "  "
                col = YELLOW if i == self.equip_member_ix else WHITE
                self.r.text(view, f"{prefix}{m.name} Lv{m.level} {m.cls}", (32, y), col); y += 20
            self.r.text_small(view, "Enter: Select  Esc: Back", (32, y + 6), LIGHT)
        elif self.equip_phase == 'slot':
            if not self.party.members:
                self.equip_phase = 'member'; return
            m = self.party.members[self.equip_member_ix % len(self.party.members)]
            options = [
                f"Weapon — {self._equipped_label(m,0)}",
                f"Armor  — {self._equipped_label(m,1)}",
                f"Acc 1  — {self._equipped_label(m,2)}",
                f"Acc 2  — {self._equipped_label(m,3)}",
            ]
            self.r.draw_center_menu(options + ["Back"], self.equip_slot_ix)
        else:  # choose
            m = self.party.members[self.equip_member_ix % len(self.party.members)]
            slot_ix = self.equip_slot_ix
            # Filter inventory by slot
            if slot_ix == 0:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'weapon']
            elif slot_ix == 1:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'armor']
            else:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'accessory']
            options = [ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid) for iid in pool]
            # Allow unequip when something is equipped
            can_unequip = (
                (slot_ix == 0 and m.equipment.weapon_id) or
                (slot_ix == 1 and m.equipment.armor_id) or
                (slot_ix == 2 and m.equipment.acc1_id) or
                (slot_ix == 3 and m.equipment.acc2_id)
            )
            if can_unequip:
                options = ["(Unequip)"] + options
            options = options + ["Back"]
            self.r.draw_center_menu(options, self.equip_choose_ix)

    def _equip_apply(self, m: Character, slot_ix: int, iid: Optional[str]):
        # Put currently equipped back to inventory
        if slot_ix == 0:
            if m.equipment.weapon_id:
                self.party.inventory.append(m.equipment.weapon_id)
            m.equipment.weapon_id = iid
            m.equipment.weapon_atk = ITEMS_BY_ID.get(iid, {}).get('atk', 0) if iid else 0
        elif slot_ix == 1:
            if m.equipment.armor_id:
                self.party.inventory.append(m.equipment.armor_id)
            m.equipment.armor_id = iid
            m.equipment.armor_ac = ITEMS_BY_ID.get(iid, {}).get('ac', 0) if iid else 0
        elif slot_ix == 2:
            if m.equipment.acc1_id:
                self.party.inventory.append(m.equipment.acc1_id)
            m.equipment.acc1_id = iid
        else:
            if m.equipment.acc2_id:
                self.party.inventory.append(m.equipment.acc2_id)
            m.equipment.acc2_id = iid

    def equip_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self.equip_phase == 'member':
            n = max(1, len(self.party.members))
            if event.key in (pygame.K_UP, pygame.K_k):
                self.equip_member_ix = (self.equip_member_ix - 1) % n
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_member_ix = (self.equip_member_ix + 1) % n
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                if self.party.members:
                    self.equip_phase = 'slot'
                    self.equip_slot_ix = 0
            elif event.key == pygame.K_ESCAPE:
                self.mode = self.return_mode
        elif self.equip_phase == 'slot':
            if event.key in (pygame.K_UP, pygame.K_k):
                self.equip_slot_ix = (self.equip_slot_ix - 1) % 5
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_slot_ix = (self.equip_slot_ix + 1) % 5
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                # If Back selected
                if self.equip_slot_ix == 4:
                    self.equip_phase = 'member'
                else:
                    self.equip_phase = 'choose'
                    self.equip_choose_ix = 0
            elif event.key == pygame.K_ESCAPE:
                self.equip_phase = 'member'
        else:
            # choose item to equip / unequip / back
            m = self.party.members[self.equip_member_ix % len(self.party.members)]
            slot_ix = self.equip_slot_ix
            if slot_ix == 0:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'weapon']
            elif slot_ix == 1:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'armor']
            else:
                pool = [iid for iid in self.party.inventory if ITEMS_BY_ID.get(iid,{}).get('type') == 'accessory']
            can_unequip = (
                (slot_ix == 0 and m.equipment.weapon_id) or
                (slot_ix == 1 and m.equipment.armor_id) or
                (slot_ix == 2 and m.equipment.acc1_id) or
                (slot_ix == 3 and m.equipment.acc2_id)
            )
            list_len = len(pool) + 1 + (1 if can_unequip else 0)
            if event.key in (pygame.K_UP, pygame.K_k):
                self.equip_choose_ix = (self.equip_choose_ix - 1) % max(1, list_len)
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_choose_ix = (self.equip_choose_ix + 1) % max(1, list_len)
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play('ui_select', 0.6)
                # Back
                if self.equip_choose_ix == list_len - 1:
                    self.equip_phase = 'slot'
                    return
                # Unequip
                if can_unequip and self.equip_choose_ix == 0:
                    self._equip_apply(m, slot_ix, None)
                    self.equip_phase = 'slot'
                    return
                # Equip selected
                pick_ix = self.equip_choose_ix - (1 if can_unequip else 0)
                if 0 <= pick_ix < len(pool):
                    iid = pool[pick_ix]
                    # remove from inventory and equip
                    # remove first occurrence
                    try:
                        self.party.inventory.remove(iid)
                    except ValueError:
                        pass
                    self._equip_apply(m, slot_ix, iid)
                    self.equip_phase = 'slot'
            elif event.key == pygame.K_ESCAPE:
                self.equip_phase = 'slot'

    # --------------- Battle ---------------
    def battle_input(self, event):
        b = self.in_battle
        if not b or b.battle_over:
            return
        if event.type == pygame.KEYDOWN:
            if b.state == 'menu':
                if event.key in (pygame.K_UP, pygame.K_k):
                    b.ui_menu_index = (b.ui_menu_index - 1) % len(b.ui_menu_options)
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.ui_menu_index = (b.ui_menu_index + 1) % len(b.ui_menu_options)
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    chosen_id = b.ui_menu_options[b.ui_menu_index][0]
                    actor = b.current_actor()
                    if chosen_id == 'attack':
                        b.state = 'target'
                        b.target_mode = {'side': 'enemy', 'action': 'attack'}
                        alive_enemy_indices = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                        b.target_menu_index = 0
                        if not alive_enemy_indices:
                            b.begin_player_turn()
                    elif chosen_id == 'skill':
                        # Only enter skill menu if there are skills available
                        if not b.skill_options:
                            return
                        # open skill submenu
                        b.state = 'skillmenu'
                        b.skill_menu_index = 0
                    elif chosen_id == 'item':
                        # Only open if there are usable items
                        if not b.usable_items():
                            return
                        b.state = 'itemmenu'
                        b.item_menu_index = 0
                    elif chosen_id == 'run':
                        act = b.make_run_action()
                        b.start_animation(act)
            elif b.state == 'skillmenu':
                # show per-actor skills and Back
                n = max(1, len(b.skill_options) + 1)
                if event.key in (pygame.K_UP, pygame.K_k):
                    b.skill_menu_index = (b.skill_menu_index - 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.skill_menu_index = (b.skill_menu_index + 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    if b.skill_menu_index == len(b.skill_options):
                        # Back
                        b.state = 'menu'
                    else:
                        sid, _ = b.skill_options[b.skill_menu_index]
                        actor = b.current_actor()
                        if sid == 'spell':
                            # choose enemy target
                            b.state = 'target'
                            b.target_mode = {'side': 'enemy', 'action': 'spell'}
                            b.target_menu_index = 0
                        elif sid == 'heal':
                            # choose party target
                            b.state = 'target'
                            b.target_mode = {'side': 'party', 'action': 'heal'}
                            b.target_menu_index = 0
                elif event.key == pygame.K_ESCAPE:
                    b.state = 'menu'
            elif b.state == 'target':
                # choose from enemies or party based on target_mode
                if not b.target_mode:
                    b.begin_player_turn(); return
                if b.target_mode['side'] == 'enemy':
                    alive = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    if not alive:
                        b.begin_player_turn(); return
                    if event.key in (pygame.K_LEFT, pygame.K_h):
                        b.target_menu_index = (b.target_menu_index - 1) % len(alive)
                        self.sfx.play('ui_move', 0.5)
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        b.target_menu_index = (b.target_menu_index + 1) % len(alive)
                        self.sfx.play('ui_move', 0.5)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.sfx.play('ui_select', 0.6)
                        actor = b.current_actor()
                        target_i = alive[b.target_menu_index]
                        if b.target_mode.get('action') == 'attack':
                            act = b.make_attack_action(actor, target_i)
                        else:
                            act = b.make_spell_action(actor, target_i)
                        if act:
                            b.start_animation(act)
                    elif event.key == pygame.K_ESCAPE:
                        # go back to combat menu
                        b.state = 'menu'
                else:
                    # party targeting (for heal) — follow on-screen order (self.party.active)
                    alive_gi = [i for i in self.party.active
                                if 0 <= i < len(self.party.members)
                                and self.party.members[i].alive and self.party.members[i].hp > 0]
                    if not alive_gi:
                        b.begin_player_turn(); return
                    if event.key in (pygame.K_LEFT, pygame.K_h):
                        b.target_menu_index = (b.target_menu_index - 1) % len(alive_gi)
                        self.sfx.play('ui_move', 0.5)
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        b.target_menu_index = (b.target_menu_index + 1) % len(alive_gi)
                        self.sfx.play('ui_move', 0.5)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.sfx.play('ui_select', 0.6)
                        actor = b.current_actor()
                        target_gi = alive_gi[b.target_menu_index]
                        if b.target_mode.get('action') == 'heal':
                            act = b.make_heal_action(actor, target_gi)
                        elif b.target_mode.get('action') == 'item':
                            iid = b.selected_item_iid
                            act = b.make_item_use_action(actor, target_gi, iid) if iid else None
                            # consume the item now
                            if act and iid in self.party.inventory:
                                try:
                                    self.party.inventory.remove(iid)
                                except ValueError:
                                    pass
                        else:
                            act = None
                        if act:
                            b.start_animation(act)
                    elif event.key == pygame.K_ESCAPE:
                        # go back to combat menu
                        b.state = 'menu'
            elif b.state == 'itemmenu':
                items = b.usable_items()
                n = max(1, len(items) + 1)  # +1 Back
                if event.key in (pygame.K_UP, pygame.K_k):
                    b.item_menu_index = (b.item_menu_index - 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.item_menu_index = (b.item_menu_index + 1) % n
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    if b.item_menu_index == len(items):
                        b.state = 'menu'
                    else:
                        b.selected_item_iid = items[b.item_menu_index]
                        b.item_action_index = 0
                        b.state = 'itemaction'
                elif event.key == pygame.K_ESCAPE:
                    b.state = 'menu'
            elif b.state == 'itemaction':
                if event.key in (pygame.K_UP, pygame.K_k):
                    b.item_action_index = (b.item_action_index - 1) % 2
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.item_action_index = (b.item_action_index + 1) % 2
                    self.sfx.play('ui_move', 0.5)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.sfx.play('ui_select', 0.6)
                    if b.item_action_index == 0 and b.selected_item_iid:
                        # choose party target for the item
                        b.state = 'target'
                        b.target_mode = {'side': 'party', 'action': 'item'}
                        b.target_menu_index = 0
                    else:
                        b.state = 'itemmenu'
                elif event.key == pygame.K_ESCAPE:
                    b.state = 'itemmenu'
            

    def draw_battle(self):
        b = self.in_battle
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Slightly brighter base to make background more visible
        view.fill((14, 14, 22))
        # Background: subtle ripple rings (like water drips)
        self.draw_battle_ripples(view)
        party_highlight = set()
        party_acting = set()
        enemy_highlight = set()
        enemy_acting = set()
        if b:
            if b.state == 'menu':
                gi = b.current_actor_global_ix()
                if gi is not None:
                    party_highlight.add(gi)
            if b.state == 'target':
                if b.target_mode and b.target_mode.get('side') == 'party':
                    # Highlight using on-screen order
                    alive_gi = [i for i in self.party.active
                                if 0 <= i < len(self.party.members)
                                and self.party.members[i].alive and self.party.members[i].hp > 0]
                    if alive_gi:
                        party_highlight.add(alive_gi[b.target_menu_index])
                else:
                    alive = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    if alive:
                        enemy_highlight.add(alive[b.target_menu_index])
            if b.state == 'anim' and b.anim:
                act = b.anim['action']
                if act['actor_side'] == 'party' and act['actor_index'] is not None:
                    party_acting.add(act['actor_index'])
                elif act['actor_side'] == 'enemy':
                    enemy_acting.add(act['actor_index'])
        # dying enemies fade-out progress
        dying_prog: Dict[int, float] = {}
        if b:
            now = pygame.time.get_ticks()
            for i, d in b.dying_enemies.items():
                p = max(0.0, min(1.0, (now - d['start']) / max(1, d['dur'])))
                dying_prog[i] = p
        # Actor lunge offsets during animation
        offsets_enemy: Dict[int, int] = {}
        offsets_party: Dict[int, int] = {}
        if b and b.state == 'anim' and b.anim:
            act = b.anim['action']
            stage = b.anim.get('stage', 0)
            now = pygame.time.get_ticks()
            t0 = b.anim.get('t0', now)
            # Determine current stage duration
            durs = b.anim.get('dur', [0, 0, 0])
            # Compute progress within current stage
            dur = durs[stage] if stage < len(durs) else 0
            p = 0.0
            if dur > 0:
                p = max(0.0, min(1.0, (now - t0) / float(dur)))
            max_off = 10  # pixels
            off = 0
            if len(durs) >= 4:
                # 4-stage: 0 windup, 1 pre, 2 impact, 3 recover
                if stage == 1:
                    # ease-out to move forward quicker
                    pe = 1.0 - (1.0 - p) * (1.0 - p)
                    off = int(max_off * pe)
                elif stage == 2:
                    off = max_off
                elif stage == 3:
                    off = int(max_off * (1.0 - p))
                else:
                    off = 0
            else:
                # 3-stage: 0 wind, 1 impact, 2 recover
                if stage == 0:
                    off = 0
                elif stage == 1:
                    off = max_off
                elif stage == 2:
                    off = int(max_off * (1.0 - p))
            if act.get('actor_side') == 'party' and act.get('actor_index') is not None:
                # Party lunges upward (negative y)
                offsets_party[act['actor_index']] = -off
            elif act.get('actor_side') == 'enemy' and act.get('actor_index') is not None:
                # Enemy lunges downward (positive y)
                offsets_enemy[act['actor_index']] = off

        enemy_rects = self.r.draw_combat_enemy_windows(b.enemies if b else [], self.effects, enemy_highlight, enemy_acting, dying_prog, offsets_enemy) if b else {}
        party_rects = self.r.draw_combat_party_windows(self.party, self.effects, party_highlight, party_acting, offsets_party)
        # Turn order panel on the left (vertically centered, padded)
        if b and b.turn_order:
            inner_px, inner_py = 10, 10
            header = "Turn Order"
            line_h = self.r.font_small.get_height()
            header_h = line_h
            lines = min(8, len(b.turn_order))
            panel_w = 180
            panel_h = inner_py + header_h + 6 + lines * line_h + inner_py
            rect_x = 12
            rect_y = max(0, VIEW_H // 2 - panel_h // 2)
            panel_rect = pygame.Rect(rect_x, rect_y, panel_w, panel_h)
            pygame.draw.rect(view, (16, 16, 20), panel_rect)
            pygame.draw.rect(view, YELLOW, panel_rect, 1)
            # Header
            hx = rect_x + inner_px
            hy = rect_y + inner_py
            self.r.text_small(view, header, (hx, hy), LIGHT)
            # Lines
            y = hy + header_h + 6
            x = hx
            for off in range(lines):
                pos = (b.turn_pos + off) % len(b.turn_order)
                side, ix = b.turn_order[pos]
                if side == 'party' and 0 <= ix < len(self.party.members):
                    label = self.party.members[ix].name
                elif side == 'enemy' and 0 <= ix < len(b.enemies):
                    label = b.enemies[ix].name
                else:
                    label = "?"
                pre = "> " if off == 0 else "  "
                col = YELLOW if off == 0 else WHITE
                self.r.text_small(view, pre + label, (x, y), col)
                y += line_h
        if b:
            if b.state == 'menu':
                # Draw combat menu with disabled state for Skill/Items when unavailable
                labels = [label for _id, label in b.ui_menu_options]
                disabled = set()
                for i, (oid, _lab) in enumerate(b.ui_menu_options):
                    if oid == 'skill' and not b.skill_options:
                        disabled.add(i)
                    if oid == 'item' and not b.usable_items():
                        disabled.add(i)
                options = labels
                if options:
                    pad_x, pad_y = 12, 10
                    text_w = max(self.r.font.size(s + "  ")[0] for s in options)
                    text_h = self.r.font.get_height()
                    w = text_w + pad_x * 2
                    h = text_h * len(options) + pad_y * 2
                    x = WIDTH // 2 - w // 2
                    y = VIEW_H // 2 - h // 2
                    rect = pygame.Rect(x, y, w, h)
                    pygame.draw.rect(view, (16, 16, 20), rect)
                    pygame.draw.rect(view, YELLOW, rect, 2)
                    cy = y + pad_y
                    for i, s in enumerate(options):
                        is_sel = (i == b.ui_menu_index)
                        is_disabled = (i in disabled)
                        color = GRAY if is_disabled else (YELLOW if is_sel else WHITE)
                        prefix = "> " if is_sel else "  "
                        self.r.text(view, prefix + s, (x + pad_x, cy), color)
                        cy += text_h
            elif b.state == 'skillmenu':
                opts = [label for _id, label in b.skill_options] or ["(No skills)"]
                opts = opts + ["Back"]
                self.r.draw_center_menu(opts, b.skill_menu_index)
            elif b.state == 'itemmenu':
                items = b.usable_items()
                options = [ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid) for iid in items] or ["(no usable items)"]
                options = options + ["Back"]
                self.r.draw_center_menu(options, b.item_menu_index)
            elif b.state == 'itemaction':
                self.r.draw_center_menu(["Use", "Cancel"], b.item_action_index)
            elif b.state == 'target':
                # No center menu in target selection; use highlights only
                pass
        # Overlay combat intro transition: two white flashes then black fade
        if self.combat_intro_active:
            now = pygame.time.get_ticks()
            t = now - self.combat_intro_t0
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            if self.combat_intro_stage in (0, 2):
                # white flash
                alpha = 200 if t < 120 else 0
                overlay.fill((255, 255, 255, alpha))
            elif self.combat_intro_stage == 3:
                # fade from black to transparent
                # at t=0 alpha=255, at t=500 alpha=0
                alpha = max(0, 255 - int(255 * (t / 500.0)))
                overlay.fill((0, 0, 0, alpha))
            view.blit(overlay, (0, 0))

        # Draw floaters (damage, heal, MISS) above windows, on top of overlays
        if b:
            now = pygame.time.get_ticks()
            for f in b.floaters:
                rect = party_rects.get(f['index']) if f.get('side') == 'party' else enemy_rects.get(f['index'])
                if not rect:
                    continue
                t = now - f['start']
                p = max(0.0, min(1.0, t / max(1, f.get('dur', 700))))
                base = rect.top + 26
                if str(f.get('text', '')).upper() == 'MISS':
                    base = rect.top + 34
                y = base - int(20 * p)
                alpha = max(0, 255 - int(255 * p))
                color = f.get('color', WHITE)
                surf = self.r.font_big.render(str(f.get('text', '')), True, color)
                surf.set_alpha(alpha)
                view.blit(surf, (rect.centerx - surf.get_width() // 2, y))

    def draw_battle_ripples(self, surf: pygame.Surface):
        # Draw animated ripple rings and soft sine-wave bands to make the battle
        # background slightly more visible and wavy, while staying subtle.
        now = pygame.time.get_ticks() / 1000.0
        # Ripple rings ------------------------------------------------------
        rings = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        base_radius = 28
        ring_gap = 34
        speed = 0.9
        amp = 12
        ring_color = (120, 140, 220, 36)  # increased alpha for visibility
        for cx, cy in self.ripple_centers:
            for k in range(3):
                r = base_radius + k * ring_gap + int(amp * (1.0 + math.sin(now * speed + k * 1.8)) * 0.5)
                pygame.draw.circle(rings, ring_color, (cx, cy), max(2, r), 2)
        rings.set_alpha(120)
        surf.blit(rings, (0, 0))

        # Wavy horizontal bands --------------------------------------------
        waves = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        band_h = 52
        band_amp = 24
        band_speed = 0.6
        wave_colors = [
            (60, 80, 160, 34),
            (40, 60, 140, 28),
            (80, 100, 180, 24),
        ]
        for i, col in enumerate(wave_colors):
            # base center distributed vertically
            base_y = int(VIEW_H * (i + 1) / (len(wave_colors) + 1))
            cy = base_y + int(math.sin(now * band_speed + i * 1.7) * band_amp)
            rect = pygame.Rect(0, max(0, cy - band_h // 2), WIDTH, band_h)
            pygame.draw.rect(waves, col, rect)
        waves.set_alpha(110)
        surf.blit(waves, (0, 0))

    # --------------- Victory Screen ---------------
    def draw_victory(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((10, 14, 10))
        # Panel
        pad_x, pad_y = 14, 12
        title = "Victory!"
        # Prepare lines from current state (fallback if not set)
        if not self.victory_text_lines:
            self.victory_text_lines = [
                f"EXP gained: {self.victory_info.get('exp', 0)}",
                f"Gold found: {self.victory_info.get('gold', 0)}g",
            ]
        lines = [title] + self.victory_text_lines
        text_h = self.r.font.get_height()
        w = max(self.r.font_big.size(lines[0])[0], max(self.r.font.size(l)[0] for l in lines[1:])) + pad_x * 2
        h = text_h * (len(lines) + 2) + pad_y * 2 + 12
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (16, 24, 16), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        # Title
        self.r.text_big(view, title, (x + pad_x, y + pad_y), YELLOW)

        # Typewriter effect for result lines (sequential across lines)
        now = pygame.time.get_ticks()
        if not self.victory_done:
            elapsed = max(0, now - self.victory_type_t0)
            target = int(self.victory_type_cps * (elapsed / 1000.0))
            prev_chars = self.victory_type_chars
            self.victory_type_chars = max(self.victory_type_chars, target)
            # typer sfx during reveal (throttled)
            if self.victory_type_chars > prev_chars and now - self.victory_type_last_sfx >= 50:
                try:
                    self.sfx.play('typer', 0.35)
                except Exception:
                    pass
                self.victory_type_last_sfx = now

        total = sum(len(s) for s in self.victory_text_lines)
        shown = min(total, self.victory_type_chars)
        cy = y + pad_y + text_h + 8
        remaining = shown
        for ln in self.victory_text_lines:
            n = min(len(ln), max(0, remaining))
            text = ln[:n]
            self.r.text(view, text, (x + pad_x, cy))
            remaining -= n
            cy += text_h

        self.victory_done = (shown >= total)
        if self.victory_done:
            self.r.text_small(view, "Enter: Continue", (x + pad_x, cy + 8), LIGHT)

    def draw_defeat(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((8, 8, 10))
        now = pygame.time.get_ticks()
        t = now - self.defeat_t0
        dur = 900
        alpha = max(0, min(255, int(255 * (t / dur))))
        overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        view.blit(overlay, (0, 0))
        pad_x, pad_y = 14, 12
        title = "Defeat..."
        msg = "Your party has fallen."
        text_h = self.r.font.get_height()
        w = max(self.r.font_big.size(title)[0], self.r.font.size(msg)[0]) + pad_x * 2
        h = text_h * 3 + pad_y * 2 + 12
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (18, 12, 12), rect)
        pygame.draw.rect(view, RED, rect, 2)
        self.r.text_big(view, title, (x + pad_x, y + pad_y), RED)
        self.r.text(view, msg, (x + pad_x, y + pad_y + text_h + 6))
        self.r.text_small(view, "Enter: Return to Title", (x + pad_x, y + pad_y + text_h * 2 + 12), LIGHT)

    def defeat_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.title_index = 0
                self.mode = MODE_TITLE

    def victory_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                # If typewriter not finished, reveal instantly; otherwise continue
                if not self.victory_done:
                    self.victory_type_chars = sum(len(s) for s in self.victory_text_lines)
                    self.victory_done = True
                else:
                    # Return to labyrinth after victory
                    self.mode = MODE_MAZE
        # no-op additional rendering in victory input

    # --------------- Gold helpers ---------------
    def total_gold(self) -> int:
        # Kept for compatibility; now reflects party gold
        return self.party.gold

    def take_gold(self, amount: int):
        # Kept for compatibility; subtracts from party gold
        self.party.gold = max(0, self.party.gold - amount)

    # --------------- Main loop ---------------
    def update(self):
        # progress typewriter for message log every frame
        self.log.update()
        # Smooth maze movement animation progression
        if self.mode in (MODE_MAZE, MODE_COMBAT_INTRO, MODE_SCENE) and self.move_active:
            now = pygame.time.get_ticks()
            p = max(0.0, min(1.0, (now - self.move_t0) / max(1, self.move_dur)))
            # Trigger a single footstep sound once during movement
            try:
                if self.move_step_sfx_count == 0 and p >= 0.33:
                    self.sfx.play('step', 0.8)
                    # Skip to 2 so it won't trigger again this move
                    self.move_step_sfx_count = 2
            except Exception:
                pass
            if p >= 1.0:
                # finalize movement
                self.pos = self.move_to
                self.move_active = False
                # After arriving, handle special tiles and encounters
                x, y = self.pos
                t = self.grid()[y][x]
                special = t in (T_TOWN, T_STAIRS_D, T_STAIRS_U)
                self.check_special_tile()
                if self.mode == MODE_MAZE and not special and random.random() < self.encounter_rate:
                    self.start_battle()
        # Handle combat intro sequence across modes
        if self.combat_intro_active:
            now = pygame.time.get_ticks()
            dt = now - self.combat_intro_t0
            # Longer timings: flashes 180ms each, pause 150ms, fade 700ms
            if self.mode == MODE_COMBAT_INTRO:
                if self.combat_intro_stage == 0 and dt >= 180:
                    self.combat_intro_stage = 1; self.combat_intro_t0 = now
                elif self.combat_intro_stage == 1 and dt >= 150:
                    self.combat_intro_stage = 2; self.combat_intro_t0 = now
                elif self.combat_intro_stage == 2 and dt >= 180:
                    # Switch to battle and begin fade
                    self.mode = MODE_BATTLE
                    self.combat_intro_stage = 3
                    self.combat_intro_t0 = now
            elif self.mode == MODE_BATTLE:
                if self.combat_intro_stage == 3 and dt >= 700:
                    self.combat_intro_active = False
        # Drive battle normally when in battle and not during intro
        if self.mode == MODE_BATTLE and self.in_battle and not self.combat_intro_active:
            self.in_battle.update()
            # Kick off first turn once after intro completes
            if not self.combat_intro_done_triggered:
                self.combat_intro_done_triggered = True
                self.in_battle.next_turn()
            # Only react to battle end states when battle_over is set
            if self.in_battle.battle_over:
                if self.in_battle.result == 'victory':
                    # Capture victory results for display
                    exp = getattr(self.in_battle, 'victory_exp', 0)
                    gold = getattr(self.in_battle, 'victory_gold', 0)
                    self.victory_info = {'exp': exp, 'gold': gold}
                    # Prepare typewriter state for victory screen
                    self.victory_text_lines = [
                        f"EXP gained: {exp}",
                        f"Gold found: {gold}g",
                    ]
                    self.victory_type_t0 = pygame.time.get_ticks()
                    self.victory_type_chars = 0
                    self.victory_done = False
                    self.mode = MODE_VICTORY
                elif self.in_battle.result == 'fled':
                    self.mode = MODE_MAZE
                else:
                    self.defeat_t0 = pygame.time.get_ticks()
                    self.mode = MODE_DEFEAT

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    if self.mode == MODE_TITLE:
                        self.title_input(event)
                    elif self.mode == MODE_TOWN:
                        self.town_input(event)
                    elif self.mode == MODE_PARTY:
                        self.party_input(event)
                    elif self.mode == MODE_FORM:
                        self.form_input(event)
                    elif self.mode == MODE_STATUS:
                        self.status_input(event)
                    elif self.mode == MODE_CREATE:
                        self.create_input(event)
                    elif self.mode == MODE_SHOP:
                        self.shop_input(event)
                    elif self.mode == MODE_TEMPLE:
                        self.temple_input(event)
                    elif self.mode == MODE_TRAINING:
                        self.training_input(event)
                    elif self.mode == MODE_SAVELOAD:
                        self.saveload_input(event)
                    elif self.mode == MODE_MAZE:
                        self.maze_input(event)
                    elif self.mode == MODE_PAUSE:
                        self.pause_input(event)
                    elif self.mode == MODE_ITEMS:
                        self.items_input(event)
                    elif self.mode == MODE_EQUIP:
                        self.equip_input(event)
                    elif self.mode == MODE_DEFEAT:
                        self.defeat_input(event)
                    elif self.mode == MODE_VICTORY:
                        self.victory_input(event)
                    elif self.mode == MODE_BATTLE:
                        self.battle_input(event)

            self.update()

            # Detect and react to mode changes for music control
            if self._last_mode != self.mode:
                self.on_mode_changed(self._last_mode, self.mode)
                self._last_mode = self.mode

            if self.mode == MODE_TITLE:
                # Title renders fullscreen and hides log
                self.draw_title()
            else:
                self.r.draw_frame()
                if self.mode == MODE_TOWN:
                    self.draw_town()
                elif self.mode == MODE_COMBAT_INTRO:
                    # Show maze background during intro flashes
                    self.draw_maze()
                elif self.mode == MODE_SCENE:
                    # Custom town<->maze fade with black hold
                    self.draw_scene_transition()
                elif self.mode == MODE_PARTY:
                    self.draw_party()
                elif self.mode == MODE_FORM:
                    self.draw_form()
                elif self.mode == MODE_STATUS:
                    self.draw_status()
                elif self.mode == MODE_CREATE:
                    self.draw_create()
                elif self.mode == MODE_SHOP:
                    self.draw_shop()
                elif self.mode == MODE_TEMPLE:
                    self.draw_temple()
                elif self.mode == MODE_TRAINING:
                    self.draw_training()
                elif self.mode == MODE_SAVELOAD:
                    self.draw_saveload()
                elif self.mode == MODE_MAZE:
                    self.draw_maze()
                elif self.mode == MODE_PAUSE:
                    self.draw_maze(); self.draw_pause()
                elif self.mode == MODE_ITEMS:
                    self.draw_items()
                elif self.mode == MODE_EQUIP:
                    self.draw_equip()
                elif self.mode == MODE_DEFEAT:
                    self.draw_defeat()
                elif self.mode == MODE_VICTORY:
                    self.draw_victory()
                elif self.mode == MODE_BATTLE:
                    self.draw_battle()

                # Draw message log for non-title scenes (with typewriter effect)
                self.r.draw_log(self.log.render_lines())
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
