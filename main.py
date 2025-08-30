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
    def draw_topdown(self, grid, pos: Tuple[int, int], facing: int, level_ix: int):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 22))
        px, py = pos
        radius = 10
        visible = radius * 2 + 1
        margin = 40
        cell = min((WIDTH - margin * 2) // visible, (VIEW_H - margin * 2) // visible)
        total_w = visible * cell
        total_h = visible * cell
        ox = (WIDTH - total_w) // 2
        oy = (VIEW_H - total_h) // 2
        for y in range(py - radius, py + radius + 1):
            for x in range(px - radius, px + radius + 1):
                sx = ox + (x - (px - radius)) * cell
                sy = oy + (y - (py - radius)) * cell
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
        pys = oy + radius * cell + cell // 2
        pygame.draw.circle(view, PURPLE, (pxs, pys), max(4, cell // 4))
        d = DIRS[facing]
        pygame.draw.line(view, PURPLE, (pxs, pys), (pxs + d[0] * max(10, cell // 2), pys + d[1] * max(10, cell // 2)), 2)
        self.text_small(view, f"L{level_ix} pos {pos} {DIR_NAMES[facing]}", (12, 6))

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
        # chars per second; tune for comfortable reading
        self._cps: float = 90.0

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
                self._reveal_chars = min(len(self._current), self._reveal_chars + add_chars)
                if self._reveal_chars >= len(self._current):
                    # push finished line into history, reset current
                    self.lines.append(self._current)
                    self._current = ""
                    self._reveal_chars = 0
                    # small delay before next line begins revealing
                    # by leaving update until next frame to pull from queue

    def render_lines(self) -> List[str]:
        # return lines including partially revealed current line (if any)
        if self._current and self._reveal_chars > 0:
            return self.lines + [self._current[: self._reveal_chars]]
        return self.lines


# ------------------------------ Battle -------------------------------------
class Battle:
    def __init__(self, party: Party, log: MessageLog, effects: HitEffects, items_by_id: Dict[str, Any], monsters_by_id: Dict[str, Any], skills_config: Dict[str, List[Dict[str, Any]]]):
        self.party = party
        self.log = log
        self.effects = effects
        self.items_by_id = items_by_id
        self.monsters_by_id = monsters_by_id
        self.skills_config = skills_config
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
        self.log.add(f"Ambushed by {', '.join(e.name for e in self.enemies)}!")
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
        self.log.add(f"Victory! +~{total_exp} EXP, +~{total_gold}g (party)")
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
        pygame.display.set_caption("Wizardry‑style Dungeon RPG (Top‑down)")
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
        self.shop_phase = 'menu'  # 'menu' | 'buy_items' | 'buy_target' | 'sell_member' | 'sell_items'
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
        # Defeat screen fade
        self.defeat_t0: int = 0


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
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.title_index = (self.title_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % 11
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_town_option(self.menu_index)
            elif pygame.K_1 <= event.key <= pygame.K_9:
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.party_actions_index = (self.party_actions_index + 1) % opts_len
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.party_dismiss_index = (self.party_dismiss_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % max(1, len(self.party.members))
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
            for i, it in enumerate(SHOP_ITEMS):
                prefix = "> " if i == self.shop_buy_ix else "  "
                col = YELLOW if i == self.shop_buy_ix else WHITE
                self.r.text(view, f"{prefix}{it['name']} — {it['price']}g", (32, y), col); y += 20
            self.r.text_small(view, "Enter: Buy  Esc: Back", (32, y + 4), LIGHT)
        else:  # sell_items
            self.r.text(view, f"Sell items — Party", (32, 50))
            if not self.party.inventory:
                self.r.text_small(view, "(no items)", (32, y), LIGHT)
            else:
                for i, iid in enumerate(self.party.inventory):
                    it = ITEMS_BY_ID.get(iid, {"name": iid, "price": 10})
                    sellp = int(it.get('price', 10) * 0.5)
                    prefix = "> " if i == self.shop_sell_item_ix else "  "
                    col = YELLOW if i == self.shop_sell_item_ix else WHITE
                    self.r.text(view, f"{prefix}{it['name']} — {sellp}g", (32, y), col); y += 20
            self.r.text_small(view, "Enter: Sell  Esc: Back", (32, y + 6), LIGHT)

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
            if event.key in (pygame.K_UP, pygame.K_k):
                self.shop_buy_ix = (self.shop_buy_ix - 1) % len(SHOP_ITEMS)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.shop_buy_ix = (self.shop_buy_ix + 1) % len(SHOP_ITEMS)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                it = SHOP_ITEMS[self.shop_buy_ix]
                if self.party.gold < it['price']:
                    self.log.add("Not enough gold.")
                    return
                self.party.gold -= it['price']
                self.party.inventory.append(it['id'])
                self.log.add(f"Bought {it['name']}.")
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'menu'; self.shop_index = 0
        # Phase: sell_items
        else:
            if event.key in (pygame.K_UP, pygame.K_k):
                if self.party.inventory:
                    self.shop_sell_item_ix = (self.shop_sell_item_ix - 1) % len(self.party.inventory)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                if self.party.inventory:
                    self.shop_sell_item_ix = (self.shop_sell_item_ix + 1) % len(self.party.inventory)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.party.inventory:
                    iid = self.party.inventory.pop(self.shop_sell_item_ix)
                    it = ITEMS_BY_ID.get(iid, {"price": 10, "name": iid})
                    sellp = int(it.get('price', 10) * 0.5)
                    self.party.gold += sellp
                    self.log.add(f"Sold {it.get('name', iid)} for {sellp}g.")
                    if self.shop_sell_item_ix >= len(self.party.inventory):
                        self.shop_sell_item_ix = max(0, len(self.party.inventory) - 1)
            elif event.key == pygame.K_ESCAPE:
                self.shop_phase = 'menu'; self.shop_index = 1

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
        options = [f"{m.name} — Lv{m.level}  EXP {m.exp}" for m in self.party.members] or ["(no characters)"]
        if not hasattr(self, 'training_index'):
            self.training_index = 0
        self.training_index = self.training_index % max(1, len(options))
        self.r.draw_center_menu(options + ["Back"], self.training_index)

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
            self.pos = (nx, ny)
            special = self.grid()[ny][nx] in (T_TOWN, T_STAIRS_D, T_STAIRS_U)
            self.check_special_tile()
            if not special and random.random() < self.encounter_rate:
                self.start_battle()
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
        self.in_battle = Battle(self.party, self.log, self.effects, self.items_by_id, self.monsters_by_id, self.skills_config)
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
        self.r.draw_topdown(self.grid(), self.pos, self.facing, self.level_ix)
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
        self.r.text_big(view, "Items", (20, 16))
        if self.items_phase == 'items':
            actives = self.party.active_members()
            self.r.text(view, f"Party items:", (32, 50))
            y = 72
            if not self.party.inventory:
                self.r.text_small(view, "(none)", (40, y), LIGHT)
            for i, iid in enumerate(self.party.inventory):
                it = ITEMS_BY_ID.get(iid, {"name": iid})
                prefix = "> " if i == self.items_item_ix else "  "
                self.r.text(view, f"{prefix}{it['name']}", (32, y), YELLOW if i == self.items_item_ix else WHITE)
                y += 20
            self.r.text_small(view, "Enter: Actions  Esc: Back", (32, y + 6), LIGHT)
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
                if event.key in (pygame.K_UP, pygame.K_k):
                    if self.party.inventory:
                        self.items_item_ix = (self.items_item_ix - 1) % len(self.party.inventory)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    if self.party.inventory:
                        self.items_item_ix = (self.items_item_ix + 1) % len(self.party.inventory)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.party.inventory:
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
                    if not self.party.inventory:
                        self.items_phase = 'items'
                    else:
                        iid = self.party.inventory[self.items_item_ix]
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
                        if self.party.inventory and actives:
                            iid = self.party.inventory[self.items_item_ix]
                            target = actives[self.items_target_ix]
                            self.use_item(target, iid)
                            it = ITEMS_BY_ID.get(iid, {})
                            if it.get('type') == 'consumable':
                                try:
                                    self.party.inventory.pop(self.items_item_ix)
                                except IndexError:
                                    pass
                                if self.items_item_ix >= len(self.party.inventory):
                                    self.items_item_ix = max(0, len(self.party.inventory) - 1)
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
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_member_ix = (self.equip_member_ix + 1) % n
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.party.members:
                    self.equip_phase = 'slot'
                    self.equip_slot_ix = 0
            elif event.key == pygame.K_ESCAPE:
                self.mode = self.return_mode
        elif self.equip_phase == 'slot':
            if event.key in (pygame.K_UP, pygame.K_k):
                self.equip_slot_ix = (self.equip_slot_ix - 1) % 5
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_slot_ix = (self.equip_slot_ix + 1) % 5
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.equip_choose_ix = (self.equip_choose_ix + 1) % max(1, list_len)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.ui_menu_index = (b.ui_menu_index + 1) % len(b.ui_menu_options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.skill_menu_index = (b.skill_menu_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        b.target_menu_index = (b.target_menu_index + 1) % len(alive)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        b.target_menu_index = (b.target_menu_index + 1) % len(alive_gi)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.item_menu_index = (b.item_menu_index + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.item_action_index = (b.item_action_index + 1) % 2
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
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
        view.fill((12, 12, 18))
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
        # Draw a few faint, animated rings that expand/contract subtly.
        now = pygame.time.get_ticks() / 1000.0
        # Create a transparent surface for additive-like layering
        overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        # Parameters
        base_radius = 28
        ring_gap = 34
        speed = 0.85
        amp = 10
        color = (120, 140, 220, 22)  # soft bluish alpha
        for cx, cy in self.ripple_centers:
            # draw 3 rings per center
            for k in range(3):
                # phase-shift each ring
                r = base_radius + k * ring_gap + int(amp * (1.0 + math.sin(now * speed + k * 1.8)) * 0.5)
                # Outer circle (thin)
                pygame.draw.circle(overlay, color, (cx, cy), max(2, r), 1)
        # Very faint global fade to keep it subtle
        overlay.set_alpha(90)
        surf.blit(overlay, (0, 0))

    # --------------- Victory Screen ---------------
    def draw_victory(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((10, 14, 10))
        # Panel
        pad_x, pad_y = 14, 12
        lines = [
            "Victory!",
            f"EXP gained: {self.victory_info.get('exp', 0)}",
            f"Gold found: {self.victory_info.get('gold', 0)}g",
        ]
        text_h = self.r.font.get_height()
        w = max(self.r.font_big.size(lines[0])[0], max(self.r.font.size(l)[0] for l in lines[1:])) + pad_x * 2
        h = text_h * (len(lines) + 2) + pad_y * 2 + 12
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (16, 24, 16), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        # Title
        self.r.text_big(view, lines[0], (x + pad_x, y + pad_y), YELLOW)
        cy = y + pad_y + text_h + 8
        for ln in lines[1:]:
            self.r.text(view, ln, (x + pad_x, cy))
            cy += text_h
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
            if self.in_battle.battle_over:
                if self.in_battle.result == 'victory':
                    # Capture victory results for display
                    exp = getattr(self.in_battle, 'victory_exp', 0)
                    gold = getattr(self.in_battle, 'victory_gold', 0)
                    self.victory_info = {'exp': exp, 'gold': gold}
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
