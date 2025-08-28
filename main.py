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
MODE_SAVELOAD = "SAVELOAD"
MODE_PAUSE = "PAUSE"
MODE_ITEMS = "ITEMS"

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

ENEMY_TABLE = [
    {"name": "Giant Rat", "hp": (6, 10), "ac": 8, "atk": (1, 4), "exp": 12, "gold": (1, 8)},
    {"name": "Goblin", "hp": (8, 14), "ac": 7, "atk": (1, 6), "exp": 20, "gold": (2, 12)},
    {"name": "Skeleton", "hp": (10, 16), "ac": 6, "atk": (1, 8), "exp": 28, "gold": (4, 18)},
    {"name": "Kobold", "hp": (8, 12), "ac": 7, "atk": (1, 6), "exp": 18, "gold": (2, 10)},
]

SHOP_ITEMS = [
    {"id": "potion_small", "name": "Small Potion (+10 HP)", "type": "consumable", "heal": 10, "price": 20},
    {"id": "sword_basic", "name": "Basic Sword (+2 ATK)", "type": "weapon", "atk": 2, "price": 60},
    {"id": "leather_armor", "name": "Leather Armor (-1 AC)", "type": "armor", "ac": -1, "price": 60},
]
ITEMS_BY_ID = {it["id"]: it for it in SHOP_ITEMS}

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
    gold: int = 50
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
        return self.ac + self.equipment.armor_ac

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
        return {"members": [m.to_dict() for m in self.members], "active": self.active}

    @staticmethod
    def from_dict(d):
        p = Party()
        p.members = [Character.from_dict(m) for m in d.get("members", [])]
        p.active = d.get("active", [])
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

    @staticmethod
    def random_enemy():
        e = random.choice(ENEMY_TABLE)
        hp = random.randint(*e["hp"])
        return Enemy(
            name=e["name"],
            hp=hp,
            ac=e["ac"],
            atk_low=e["atk"][0],
            atk_high=e["atk"][1],
            exp=e["exp"],
            gold_low=e["gold"][0],
            gold_high=e["gold"][1],
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
    def draw_combat_party_windows(self, party: "Party", effects: "HitEffects", highlight: set = None, acting: set = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
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
            ry = y + oy
            rect = pygame.Rect(rx, ry, w, h)
            pygame.draw.rect(view, (20, 20, 28), rect)
            pygame.draw.rect(view, border_col, rect, 2)
            name = m.name[:14]
            self.text(view, name, (rx + 8, ry + 6), border_col)
            self.text_small(view, f"HP {m.hp}/{m.max_hp}", (rx + 8, ry + 26), WHITE)
            self.text_small(view, f"MP {m.mp}/{m.max_mp}", (rx + w // 2 + 8, ry + 26), WHITE)
            rects[gi] = rect
        return rects

    def draw_combat_enemy_windows(self, enemies: List["Enemy"], effects: "HitEffects", highlight: set = None, acting: set = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        alive = [(i, e) for i, e in enumerate(enemies) if e.hp > 0]
        if not alive:
            return {}
        n = len(alive)
        gap = 16
        w = min(220, (WIDTH - gap * (n + 1)) // n)
        h = 60
        total = n * w + (n + 1) * gap
        x = (WIDTH - total) // 2 + gap
        y = 16
        rects: Dict[int, pygame.Rect] = {}
        for j, (i, e) in enumerate(alive):
            (ox, oy), hit_color = effects.sample("enemy", i, base_color=WHITE)
            border_col = hit_color
            if border_col == WHITE:
                now = pygame.time.get_ticks()
                if i in acting and (now // 120) % 2 == 0:
                    border_col = YELLOW
                elif i in highlight:
                    border_col = YELLOW
            rx = x + j * (w + gap) + ox
            ry = y + oy
            rect = pygame.Rect(rx, ry, w, h)
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

    def add(self, txt: str):
        self.lines.append(txt)


# ------------------------------ Battle -------------------------------------
class Battle:
    def __init__(self, party: Party, log: MessageLog, effects: HitEffects):
        self.party = party
        self.log = log
        self.effects = effects
        self.enemies: List[Enemy] = []
        self.turn_index = 0
        self.battle_over = False
        self.result: Optional[str] = None

        # UI/flow
        self.state: str = 'menu'  # 'menu' | 'target' | 'anim' | 'postpause'
        self.ui_menu_open: bool = True
        self.ui_menu_index: int = 0
        self.ui_menu_options: List[Tuple[str, str]] = []  # (id,label)
        self.anim: Optional[Dict[str, Any]] = None
        self.enemy_queue: List[Dict[str, Any]] = []
        self.floaters: List[Dict[str, Any]] = []  # {side:'party'|'enemy', index:int, text:str, start:int, dur:int}
        self.pause_between_ms: int = 180
        self.pause_until: int = 0
        self.next_after_anim: Optional[Dict[str, Any]] = None

        # Target selection
        self.target_menu_index: int = 0

    def start_random(self):
        count = random.randint(1, 3)
        self.enemies = [Enemy.random_enemy() for _ in range(count)]
        self.log.add(f"Ambushed by {', '.join(e.name for e in self.enemies)}!")
        self.turn_index = 0
        self.begin_player_turn()

    def current_actor(self) -> Optional[Character]:
        alive = self.party.alive_active_members()
        if not alive:
            return None
        if self.turn_index >= len(alive):
            self.turn_index = 0
        return alive[self.turn_index]

    def current_actor_global_ix(self) -> Optional[int]:
        actor = self.current_actor()
        if not actor:
            return None
        try:
            return self.party.members.index(actor)
        except ValueError:
            return None

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
        self.ui_menu_options.append(('attack', 'Attack'))
        if a.cls == 'Mage' and a.mp > 0:
            self.ui_menu_options.append(('spell', 'Spell'))
        if a.cls == 'Priest' and a.mp > 0:
            self.ui_menu_options.append(('heal', 'Heal'))
        self.ui_menu_options.append(('run', 'Run'))

    def queue_enemy_round(self):
        self.enemy_queue = []
        for i, e in enumerate(self.enemies):
            if e.hp <= 0:
                continue
            targets = self.party.alive_active_members()
            if not targets:
                break
            t = random.choice(targets)
            gi = self.party.members.index(t)
            hit = random.random() < 0.65
            dmg = random.randint(e.atk_low, e.atk_high)
            self.enemy_queue.append({
                'type': 'attack',
                'actor_side': 'enemy', 'actor_index': i,
                'target_side': 'party', 'target_index': gi,
                'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                'miss_label': f"{e.name} misses {t.name}.",
            })

    def start_animation(self, action: Dict[str, Any]):
        now = pygame.time.get_ticks()
        self.anim = {'action': action, 'stage': 0, 't0': now, 'dur': [220, 240, 160]}
        self.state = 'anim'

    def add_floater(self, side: str, index: int, text: str, dur: int = 700):
        self.floaters.append({'side': side, 'index': index, 'text': text, 'start': pygame.time.get_ticks(), 'dur': dur})

    def update(self):
        now = pygame.time.get_ticks()
        # prune floaters
        self.floaters = [f for f in self.floaters if now - f['start'] < f['dur']]
        if self.battle_over:
            return
        if self.state == 'anim' and self.anim:
            a = self.anim
            stage = a['stage']
            t = now - a['t0']
            wind, impact, recover = a['dur']
            act = a['action']
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
        elif self.state == 'postpause' and now >= self.pause_until:
            if self.check_end_and_maybe_finish():
                return
            na = self.next_after_anim or {}
            if na.get('actor_side') == 'party':
                if na.get('type') == 'run' and na.get('run_success'):
                    return
                self.turn_index += 1
                if self.turn_index >= len(self.party.alive_active_members()):
                    self.turn_index = 0
                    self.queue_enemy_round()
                    if self.enemy_queue:
                        self.start_animation(self.enemy_queue.pop(0))
                        return
                self.begin_player_turn()
            else:  # enemy acted
                if self.enemy_queue:
                    self.start_animation(self.enemy_queue.pop(0))
                else:
                    self.turn_index = 0
                    self.begin_player_turn()

    def resolve_action_impact(self, act: Dict[str, Any]):
        if act['type'] in ('attack', 'spell'):
            if act.get('hit', False):
                dmg = max(1, int(act.get('dmg', 1)))
                if act['target_side'] == 'enemy':
                    i = act['target_index']
                    if 0 <= i < len(self.enemies):
                        self.enemies[i].hp -= dmg
                        self.effects.trigger('enemy', i, 300, 7)
                else:
                    gi = act['target_index']
                    if 0 <= gi < len(self.party.members):
                        t = self.party.members[gi]
                        t.hp -= dmg
                        if t.hp <= 0:
                            t.hp = 0
                            t.alive = False
                        self.effects.trigger('party', gi, 300, 7)
                self.log.add(act.get('label', 'A hit lands.'))
            else:
                idx = act['target_index']
                side = act['target_side']
                self.add_floater(side, idx, 'MISS', 700)
                self.log.add(act.get('miss_label', 'The attack misses.'))
        elif act['type'] == 'heal':
            gi = act['target_index']
            amt = act.get('heal', 0)
            if 0 <= gi < len(self.party.members):
                t = self.party.members[gi]
                before = t.hp
                t.hp = min(t.max_hp, t.hp + amt)
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
        total_exp = random.randint(20, 60)
        total_gold = random.randint(10, 40)
        alive = self.party.alive_active_members()
        for m in alive:
            m.exp += total_exp // max(1, len(alive))
            m.gold += total_gold // max(1, len(self.party.active_members()))
        self.log.add(f"Victory! +~{total_exp} EXP, +~{total_gold}g")
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

    def make_spell_action(self, actor: Character) -> Optional[Dict[str, Any]]:
        if actor.cls != 'Mage' or actor.mp <= 0:
            return None
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

    def make_heal_action(self, actor: Character) -> Optional[Dict[str, Any]]:
        if actor.cls != 'Priest' or actor.mp <= 0:
            return None
        target = min((m for m in self.party.active_members() if m.alive), key=lambda c: c.hp / max(1, c.max_hp), default=None)
        if not target:
            return None
        actor.mp -= 1
        amt = max(1, random.randint(6, 10) + ability_mod(actor.piety))
        gi = self.party.members.index(actor)
        ti = self.party.members.index(target)
        return {
            'type': 'heal', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'party', 'target_index': ti,
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
        self.mode = MODE_TITLE
        self.return_mode = MODE_TOWN

        self.dun = Dungeon(MAZE_W, MAZE_H)
        self.level_ix = 0
        self.dun.ensure_level(0)
        self.pos = (2, 2)
        self.facing = 1
        self.effects = HitEffects()
        self.in_battle: Optional[Battle] = None

        self.menu_index = 0
        self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
        self.create_confirm_index = 0
        self.shop_index = 0
        self.pause_index = 0

        # Items UI state
        self.items_phase = 'member'
        self.items_member_ix = 0
        self.items_item_ix = 0

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

        self.encounter_rate = 0.22

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
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((12, 12, 18))
        overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        t = pygame.time.get_ticks() / 1000.0
        for i in range(8):
            phase = t * (0.8 + i*0.07) + i * 0.9
            amp = 10 + i * 2.0
            freq = 0.010 + i * 0.0015
            pts = []
            step = 8
            mid = VIEW_H // 2 + int(math.sin(phase*0.5)*12)
            for x in range(0, WIDTH+step, step):
                y = mid + int(math.sin(x*freq + phase) * amp) + int(math.sin(x*freq*0.5 + phase*1.7) * amp * 0.25)
                pts.append((x, y))
            col = (120, 140, 220, 22) if i % 2 == 0 else (160, 140, 220, 16)
            if len(pts) >= 2:
                pygame.draw.aalines(overlay, col, False, pts)
        view.blit(overlay, (0, 0))

        title = "Dankest Deilou"
        self.r.text_big(view, title, (WIDTH//2 - self.r.font_big.size(title)[0]//2 + 2, 82 + 2), (0,0,0))
        self.r.text_big(view, title, (WIDTH//2 - self.r.font_big.size(title)[0]//2, 82), YELLOW)

        options = ["New Game", "Load", "Exit"]
        self.r.draw_center_menu(options, self.title_index)
    
    def title_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.title_index = (self.title_index - 1) % 3
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.title_index = (self.title_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.title_index == 0:  # New Game
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
        options = [
            "Tavern (Roster)",
            "Form Party (Choose Active)",
            "Status",
            "Training (Level Up)",
            "Temple (Heal/Revive)",
            "Trader (Shop)",
            "Enter the Labyrinth",
            "Save / Load",
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
                self.menu_index = (self.menu_index - 1) % 8
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % 8
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_town_option(self.menu_index)
            elif pygame.K_1 <= event.key <= pygame.K_8:
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
        elif ix == 5:
            self.mode = MODE_SHOP
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
            self.mode = MODE_SAVELOAD

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
            pad_x, pad_y = 16, 12
            card_w, card_h = 600, 260
            x = WIDTH//2 - card_w//2
            y = VIEW_H//2 - card_h//2
            rect = pygame.Rect(x, y, card_w, card_h)
            pygame.draw.rect(view, (20, 20, 28), rect)
            pygame.draw.rect(view, YELLOW, rect, 2)
            self.r.text_big(view, f"{m.name} — Lv{m.level} {m.cls}", (x + 16, y + 14))
            self.r.text(view, f"HP {m.hp}/{m.max_hp}   MP {m.mp}/{m.max_mp}", (x + 16, y + 48))
            self.r.text(view, f"STR {m.str_}  IQ {m.iq}  PIE {m.piety}  VIT {m.vit}  AGI {m.agi}  LCK {m.luck}", (x + 16, y + 72))
            self.r.text(view, f"AC {m.defense_ac:+}  ATK {m.atk_bonus:+}  Gold {m.gold}", (x + 16, y + 96))
            self.r.text(view, f"Weapon ATK +{m.equipment.weapon_atk}   Armor AC {m.equipment.armor_ac:+}", (x + 16, y + 120))
            inv = ", ".join(ITEMS_BY_ID.get(iid, {"name": iid})["name"] for iid in m.inventory) or "(no items)"
            self.r.text(view, f"Items: {inv}", (x + 16, y + 152))
            self.r.draw_center_menu(["Back"], 0)

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
                if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
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
            self.r.text(view, "Race (←/→, Enter)", (32, y))
            self.r.text_big(view, RACES[s["race_ix"]], (32, y + 30), YELLOW)
        elif s["step"] == 2:
            self.r.text(view, "Class (←/→, Enter)", (32, y))
            self.r.text_big(view, CLASSES[s["class_ix"]], (32, y + 30), YELLOW)
        elif s["step"] == 3:
            temp = Character(s["name"], RACES[s["race_ix"]], CLASSES[s["class_ix"]])
            self.r.text(view, f"Name: {temp.name}", (32, y))
            self.r.text(view, f"Race: {temp.race}  Class: {temp.cls}", (32, y + 20))
            y2 = y + 44
            stats = [("STR", temp.str_), ("IQ", temp.iq), ("PIE", temp.piety), ("VIT", temp.vit), ("AGI", temp.agi), ("LCK", temp.luck)]
            for i, (k, v) in enumerate(stats):
                self.r.text(view, f"{k}:{v:2d}", (32 + (i % 3) * 120, y2 + (i // 3) * 20))
            self.r.text(view, f"HP {temp.max_hp}  MP {temp.mp}", (32, y2 + 44))
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
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    s["race_ix"] = (s["race_ix"] - 1) % len(RACES)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    s["race_ix"] = (s["race_ix"] + 1) % len(RACES)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s["step"] = 2
            elif s["step"] == 2:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    s["class_ix"] = (s["class_ix"] - 1) % len(CLASSES)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    s["class_ix"] = (s["class_ix"] + 1) % len(CLASSES)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s["step"] = 3
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
                            newc = Character(s["name"], RACES[s["race_ix"]], CLASSES[s["class_ix"]])
                            self.party.members.append(newc)
                            self.log.add(f"{newc.name} the {newc.cls} joins the roster.")
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
        self.r.text_big(view, "Trader — Buy", (20, 16))
        y = 56
        for i, it in enumerate(SHOP_ITEMS):
            prefix = "> " if i == self.shop_index else "  "
            self.r.text(view, f"{prefix}{it['name']} — {it['price']}g", (32, y), YELLOW if i == self.shop_index else WHITE)
            y += 20
        self.r.text_small(view, "Enter: Buy  Esc: Back", (32, y + 4), LIGHT)

    def shop_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.shop_index = (self.shop_index - 1) % len(SHOP_ITEMS)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.shop_index = (self.shop_index + 1) % len(SHOP_ITEMS)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if not self.party.members:
                    self.log.add("No one to equip.")
                    return
                buyer = self.party.members[0]
                item = SHOP_ITEMS[self.shop_index]
                if buyer.gold < item["price"]:
                    self.log.add("Not enough gold.")
                    return
                buyer.gold -= item["price"]
                if item["type"] == "consumable":
                    buyer.inventory.append(item["id"])
                    self.log.add("Bought a potion.")
                elif item["type"] == "weapon":
                    buyer.equipment.weapon_atk = item["atk"]
                    self.log.add("Equipped a Basic Sword (+2 ATK).")
                elif item["type"] == "armor":
                    buyer.equipment.armor_ac = item["ac"]
                    self.log.add("Equipped Leather Armor (-1 AC).")
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    def draw_temple(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Temple — Healer", (20, 16))
        y = 56
        for i, m in enumerate(self.party.members):
            self.r.text(view, f"{i+1}. {m.name} HP {m.hp}/{m.max_hp} {'(DOWN)' if not m.alive else ''}", (32, y))
            y += 18
        self.r.text_small(view, "1‑9 heal (10g) / revive (50g). Esc: Back", (32, y + 4), LIGHT)

    def temple_input(self, event):
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_9:
                ix = event.key - pygame.K_1
                if ix < len(self.party.members):
                    m = self.party.members[ix]
                    if not m.alive:
                        cost = 50
                        if self.total_gold() >= cost:
                            self.take_gold(cost)
                            m.alive = True
                            m.hp = max(1, m.max_hp // 2)
                            self.log.add(f"{m.name} is revived.")
                        else:
                            self.log.add("Not enough gold to revive.")
                    else:
                        cost = 10
                        if self.total_gold() >= cost:
                            self.take_gold(cost)
                            m.hp = m.max_hp
                            self.log.add(f"{m.name} healed to full.")
                        else:
                            self.log.add("Not enough gold to heal.")
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    def draw_training(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Training Grounds", (20, 16))
        y = 56
        self.r.text_small(view, "Each level costs 100 EXP. Press number to level up.", (32, y)); y += 18
        for i, m in enumerate(self.party.members):
            self.r.text(view, f"{i+1}. {m.name} Lv{m.level} EXP {m.exp}", (32, y)); y += 18
        self.r.text_small(view, "Esc: Back", (32, y + 4), LIGHT)

    def training_input(self, event):
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_9:
                ix = event.key - pygame.K_1
                if ix < len(self.party.members):
                    m = self.party.members[ix]
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
        self.in_battle = Battle(self.party, self.log, self.effects)
        self.in_battle.start_random()
        self.mode = MODE_BATTLE

    def draw_maze(self):
        self.r.draw_topdown(self.grid(), self.pos, self.facing, self.level_ix)
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        self.r.text_small(view, "Esc: Menu  ↑: Move  ←/→: Turn", (12, VIEW_H - 22), LIGHT)

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
        self.r.text_big(view, "Menu", (WIDTH//2 - 40, 80))
        opts = ["Status", "Items", "Close"]
        y = 140
        for i, opt in enumerate(opts):
            prefix = "> " if i == self.pause_index else "  "
            self.r.text(view, f"{prefix}{opt}", (WIDTH//2 - 80, y), YELLOW if i == self.pause_index else WHITE)
            y += 24

    def pause_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.pause_index = (self.pause_index - 1) % 3
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.pause_index = (self.pause_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.pause_index == 0:
                    self.return_mode = MODE_PAUSE
                    self.mode = MODE_STATUS
                elif self.pause_index == 1:
                    self.items_phase = 'member'
                    self.items_member_ix = 0
                    self.items_item_ix = 0
                    self.mode = MODE_ITEMS
                elif self.pause_index == 2:
                    self.mode = MODE_MAZE
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_MAZE

    def draw_items(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Items", (20, 16))
        if self.items_phase == 'member':
            self.r.text_small(view, "Choose member (Enter)", (32, 46), LIGHT)
            y = 66
            actives = self.party.active_members()
            for i, m in enumerate(actives):
                prefix = "> " if i == self.items_member_ix else "  "
                self.r.text(view, f"{prefix}{m.name}  HP {m.hp}/{m.max_hp}", (32, y), YELLOW if i == self.items_member_ix else WHITE)
                y += 20
            self.r.text_small(view, "Esc: Back", (32, y + 6), LIGHT)
        else:
            actives = self.party.active_members()
            if not actives:
                self.items_phase = 'member'
                return
            m = actives[self.items_member_ix % len(actives)]
            self.r.text(view, f"{m.name}'s items:", (32, 50))
            y = 72
            if not m.inventory:
                self.r.text_small(view, "(none)", (40, y), LIGHT)
            for i, iid in enumerate(m.inventory):
                it = ITEMS_BY_ID.get(iid, {"name": iid})
                prefix = "> " if i == self.items_item_ix else "  "
                self.r.text(view, f"{prefix}{it['name']}", (32, y), YELLOW if i == self.items_item_ix else WHITE)
                y += 20
            self.r.text_small(view, "Enter: Use  Esc: Back", (32, y + 6), LIGHT)

    def items_input(self, event):
        actives = self.party.active_members()
        if event.type == pygame.KEYDOWN:
            if self.items_phase == 'member':
                if event.key in (pygame.K_UP, pygame.K_k):
                    if actives:
                        self.items_member_ix = (self.items_member_ix - 1) % len(actives)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    if actives:
                        self.items_member_ix = (self.items_member_ix + 1) % len(actives)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.items_phase = 'items'
                    self.items_item_ix = 0
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_PAUSE
            else:
                sel_member = actives[self.items_member_ix % len(actives)] if actives else None
                if event.key in (pygame.K_UP, pygame.K_k):
                    if sel_member and sel_member.inventory:
                        self.items_item_ix = (self.items_item_ix - 1) % len(sel_member.inventory)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    if sel_member and sel_member.inventory:
                        self.items_item_ix = (self.items_item_ix + 1) % len(sel_member.inventory)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if sel_member and sel_member.inventory:
                        iid = sel_member.inventory[self.items_item_ix]
                        self.use_item(sel_member, iid)
                        it = ITEMS_BY_ID.get(iid, {})
                        if it.get("type") == "consumable":
                            sel_member.inventory.pop(self.items_item_ix)
                            if self.items_item_ix >= len(sel_member.inventory):
                                self.items_item_ix = max(0, len(sel_member.inventory) - 1)
                elif event.key == pygame.K_ESCAPE:
                    self.items_phase = 'member'

    def use_item(self, target: Character, iid: str):
        it = ITEMS_BY_ID.get(iid)
        if not it:
            self.log.add("Nothing happens.")
            return
        if it["id"] == "potion_small":
            before = target.hp
            target.hp = min(target.max_hp, target.hp + it.get("heal", 0))
            self.log.add(f"{target.name} drinks a potion (+{target.hp - before} HP).")

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
                        alive_enemy_indices = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                        b.target_menu_index = 0
                        if not alive_enemy_indices:
                            b.begin_player_turn()
                    elif chosen_id == 'spell':
                        act = b.make_spell_action(actor)
                        if act:
                            b.start_animation(act)
                    elif chosen_id == 'heal':
                        act = b.make_heal_action(actor)
                        if act:
                            b.start_animation(act)
                    elif chosen_id == 'run':
                        act = b.make_run_action()
                        b.start_animation(act)
            elif b.state == 'target':
                alive = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                if not alive:
                    b.begin_player_turn(); return
                if event.key in (pygame.K_UP, pygame.K_k):
                    b.target_menu_index = (b.target_menu_index - 1) % len(alive)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    b.target_menu_index = (b.target_menu_index + 1) % len(alive)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    actor = b.current_actor()
                    target_i = alive[b.target_menu_index]
                    act = b.make_attack_action(actor, target_i)
                    if act:
                        b.start_animation(act)
                elif event.key == pygame.K_ESCAPE:
                    b.begin_player_turn()

    def draw_battle(self):
        b = self.in_battle
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((12, 12, 18))
        self.r.text_big(view, "Battle!", (20, 16))
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
                alive = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                if alive:
                    enemy_highlight.add(alive[b.target_menu_index])
            if b.state == 'anim' and b.anim:
                act = b.anim['action']
                if act['actor_side'] == 'party' and act['actor_index'] is not None:
                    party_acting.add(act['actor_index'])
                elif act['actor_side'] == 'enemy':
                    enemy_acting.add(act['actor_index'])
        enemy_rects = self.r.draw_combat_enemy_windows(b.enemies if b else [], self.effects, enemy_highlight, enemy_acting) if b else {}
        party_rects = self.r.draw_combat_party_windows(self.party, self.effects, party_highlight, party_acting)
        if b:
            if b.state == 'menu':
                self.r.draw_center_menu([label for _id, label in b.ui_menu_options], b.ui_menu_index)
                self.r.text_small(view, "^/v Select  Enter Confirm", (40, VIEW_H - 100), LIGHT)
            elif b.state == 'target':
                options = [b.enemies[i].name for i in range(len(b.enemies)) if b.enemies[i].hp > 0] or ["(no targets)"]
                self.r.draw_center_menu(options + ["Back"], b.target_menu_index if options else 0)
        now = pygame.time.get_ticks()
        for f in (b.floaters if b else []):
            rect = None
            if f['side'] == 'party':
                rect = party_rects.get(f['index'])
            else:
                rect = enemy_rects.get(f['index'])
            if not rect:
                continue
            t = now - f['start']
            p = max(0.0, min(1.0, t / f['dur']))
            y = rect.top - 10 - int(20 * p)
            alpha = max(0, 255 - int(255 * p))
            surf = self.r.font_big.render(f['text'], True, WHITE)
            surf.set_alpha(alpha)
            view.blit(surf, (rect.centerx - surf.get_width() // 2, y))

    # --------------- Gold helpers ---------------
    def total_gold(self) -> int:
        return sum(m.gold for m in self.party.members)

    def take_gold(self, amount: int):
        if self.party.members:
            self.party.members[0].gold = max(0, self.party.members[0].gold - amount)

    # --------------- Main loop ---------------
    def update(self):
        if self.mode == MODE_BATTLE and self.in_battle:
            self.in_battle.update()
            if self.in_battle.battle_over:
                if self.in_battle.result in ('victory', 'fled'):
                    self.mode = MODE_MAZE
                else:
                    self.mode = MODE_TOWN

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
                    elif self.mode == MODE_BATTLE:
                        self.battle_input(event)

            self.update()

            self.r.draw_frame()
            if self.mode == MODE_TITLE:
                self.draw_title()
            elif self.mode == MODE_TOWN:
                self.draw_town()
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
            elif self.mode == MODE_BATTLE:
                self.draw_battle()

            self.r.draw_log(self.log.lines)
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
