#!/usr/bin/env python3
"""
Wizardry‑style dungeon RPG — single‑file Pygame prototype (wireframe + levels + UX fit)

New in this version
- **Readable UI**: smaller pixel font, tighter layout, trimmed labels so everything fits
- **Wireframe readability**: always‑visible corridor rails + depth crossbars, thicker near lines, special node glyphs
- **Safety check**: require all party members alive before entering the Labyrinth
- **Special nodes**: Town portal, Stairs Down/Up; multi‑level maze with correct up/down pairing
- **Hit effects**: shake+flash remain for both enemies and party entries
- **Local font**: uses `fonts/prstart.ttf` (falls back if missing)

Controls
- Menus: Arrow keys / number keys / Enter / Esc
- Maze: ←/→ turn, ↑ move, V toggle top‑down/wireframe
- Battle: A Attack, S Spell (Mage), H Heal (Priest), R Run

Tested with: Python 3.10+, pygame 2.5+
"""

import json
import math
import os
import random
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple, Dict, Any

import pygame

# ------------------------------ Constants ----------------------------------
WIDTH, HEIGHT = 960, 600
VIEW_H = 420
PANEL_W = 300
LOG_H = HEIGHT - VIEW_H
FPS = 60
FONT_NAME = None  # system fallback if local font missing
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
MODE_TOWN = "TOWN"
MODE_CREATE = "CREATE"
MODE_PARTY = "PARTY"
MODE_SHOP = "SHOP"
MODE_TEMPLE = "TEMPLE"
MODE_TRAINING = "TRAINING"
MODE_MAZE = "MAZE"
MODE_BATTLE = "BATTLE"
MODE_SAVELOAD = "SAVELOAD"

# View style
VIEW_TOPDOWN = 0
VIEW_WIREFRAME = 1

# Map tiles
T_EMPTY = 0
T_WALL = 1
T_TOWN = 2      # node returns to town
T_STAIRS_D = 3  # stairs down
T_STAIRS_U = 4  # stairs up

# ------------------------------ Data Models --------------------------------
RACES = ["Human", "Elf", "Dwarf", "Gnome", "Halfling"]
CLASSES = ["Fighter", "Mage", "Priest", "Thief"]

BASE_HP = {"Fighter": 12, "Mage": 6, "Priest": 8, "Thief": 8}
BASE_MP = {"Fighter": 0, "Mage": 8, "Priest": 6, "Thief": 0}
AC_BASE = 10  # lower is better

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

DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]  # N E S W
DIR_NAMES = ["N", "E", "S", "W"]


def roll_stat():
    return sum(random.randint(1, 6) for _ in range(3))  # 3d6 classic


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
        c = Character(d["name"], d["race"], d["cls"])  # will roll stats but we overwrite below
        for k, v in d.items():
            if k == "equipment":
                c.equipment = Equipment(**v)
            elif hasattr(c, k):
                setattr(c, k, v)
        return c


class Party:
    def __init__(self):
        self.members: List[Character] = []

    def alive_members(self) -> List[Character]:
        return [c for c in self.members if c.alive and c.hp > 0]

    def all_alive(self) -> bool:
        return len(self.members) > 0 and all(c.alive and c.hp > 0 for c in self.members)

    def any_alive(self) -> bool:
        return len(self.alive_members()) > 0

    def to_dict(self):
        return {"members": [m.to_dict() for m in self.members]}

    @staticmethod
    def from_dict(d):
        p = Party()
        p.members = [Character.from_dict(m) for m in d.get("members", [])]
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
    """0 empty, 1 wall. Simple box w/ corridors + start room."""
    grid = [[T_WALL] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            grid[y][x] = T_EMPTY
    # carve some simple walls
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

    def is_open(self, level_ix: int, x: int, y: int) -> bool:
        g = self.levels[level_ix].grid
        return self.in_bounds(x, y) and g[y][x] != T_WALL

    def ensure_level(self, ix: int, arrival_pos: Optional[Tuple[int, int]] = None) -> None:
        while len(self.levels) <= ix:
            # create new level
            grid = generate_base_grid(self.w, self.h)
            lvl = Level(grid=grid)
            self.levels.append(lvl)
        lvl = self.levels[ix]
        # place special nodes if not present
        if ix == 0 and not lvl.town_portal:
            lvl.town_portal = (2, 2)
            x, y = lvl.town_portal
            lvl.grid[y][x] = T_TOWN
        if arrival_pos is not None:
            # we arrived from stairs down in previous level; mark this tile as stairs up
            ax, ay = arrival_pos
            lvl.stairs_up = (ax, ay)
            lvl.grid[ay][ax] = T_STAIRS_U
        if not lvl.stairs_down:
            # choose a far-ish open tile for stairs down
            sx, sy = self._find_far_open(ix)
            lvl.stairs_down = (sx, sy)
            lvl.grid[sy][sx] = T_STAIRS_D

    def _find_far_open(self, ix: int) -> Tuple[int, int]:
        grid = self.levels[ix].grid
        # try bottom-right area first
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


# ------------------------------ Hit Effects --------------------------------
class HitEffects:
    """Shake + flash storage for entities.
    Keys are tuples like ("enemy", index) or ("party", index).
    """
    def __init__(self):
        self.effects: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def trigger(self, kind: str, index: int, duration_ms: int = 300, intensity: int = 5):
        now = pygame.time.get_ticks()
        self.effects[(kind, index)] = {
            "until": now + duration_ms,
            "duration": duration_ms,
            "intensity": intensity,
        }

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
        # decay intensity over time
        frac = max(0.0, t_left / e["duration"])
        amp = max(1, int(e["intensity"] * (0.5 + 0.5 * frac)))
        ox = random.randint(-amp, amp)
        oy = random.randint(-amp, amp)
        # flash color between WHITE and RED
        flash = (now // 60) % 2 == 0
        color = RED if flash else base_color
        return (ox, oy), color


# ------------------------------ Rendering ----------------------------------
class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = self._load_font(16)       # smaller for fit
        self.font_small = self._load_font(12)
        self.font_big = self._load_font(20)

    def _load_font(self, size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(FONT_PATH, size)
        except Exception:
            return pygame.font.SysFont(FONT_NAME, size)

    def draw_frame(self):
        self.screen.fill(DARK)
        # Panels
        pygame.draw.rect(self.screen, (30, 30, 34), (0, 0, WIDTH - PANEL_W, VIEW_H))  # view
        pygame.draw.rect(self.screen, (34, 34, 40), (WIDTH - PANEL_W, 0, PANEL_W, HEIGHT))  # side panel
        pygame.draw.rect(self.screen, (28, 28, 32), (0, VIEW_H, WIDTH - PANEL_W, LOG_H))  # log

    def text(self, surf, txt, pos, color=WHITE, aa=True):
        surf.blit(self.font.render(txt, aa, color), pos)

    def text_small(self, surf, txt, pos, color=LIGHT, aa=True):
        surf.blit(self.font_small.render(txt, aa, color), pos)

    def text_big(self, surf, txt, pos, color=WHITE, aa=True):
        surf.blit(self.font_big.render(txt, aa, color), pos)

    # ---- Panels ----
    def draw_party_panel(self, party: "Party", effects: "HitEffects"):
        panel = self.screen.subsurface(pygame.Rect(WIDTH - PANEL_W, 0, PANEL_W, HEIGHT))
        y = 8
        self.text_big(panel, "Party", (12, y)); y += 26
        for i, m in enumerate(party.members):
            base_color = WHITE if m.alive else GRAY
            (ox, oy), color = effects.sample("party", i, base_color=base_color)
            self.text(panel, f"{i+1}. {m.name[:14]}  Lv{m.level} {m.cls[:5]}", (12 + ox, y + oy), color); y += 18
            self.text_small(panel, f"HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}  AC {m.defense_ac:+}  ATK {m.atk_bonus:+}", (16 + ox, y + oy), color); y += 16
        y += 4
        pygame.draw.line(panel, GRAY, (8, y), (PANEL_W - 8, y))
        y += 8
        self.text_small(panel, "Town: 1 Tav 2 Train 3 Temple", (12, y)); y += 14
        self.text_small(panel, "      4 Shop 5 Enter 6 Save", (12, y)); y += 14
        self.text_small(panel, "Maze: Arrows move/turn, V view", (12, y)); y += 14

    def draw_log(self, log_lines: List[str]):
        panel = self.screen.subsurface(pygame.Rect(0, VIEW_H, WIDTH - PANEL_W, LOG_H))
        y = 6
        for ln in log_lines[-9:]:
            self.text_small(panel, ln, (10, y))
            y += 14

    # ---- Top‑down ----
    def draw_topdown(self, grid, pos: Tuple[int, int], facing: int):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 22))
        cell = 16
        ox, oy = 16, 16
        px, py = pos
        radius = 10
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
                            pygame.draw.circle(view, BLUE, (sx + cell // 2, sy + cell // 2), 4)
                        elif t == T_STAIRS_D:
                            pygame.draw.polygon(view, YELLOW, [(sx + 4, sy + 4), (sx + cell - 4, sy + 4), (sx + cell // 2, sy + cell - 4)])
                        elif t == T_STAIRS_U:
                            pygame.draw.polygon(view, GREEN, [(sx + 4, sy + cell - 4), (sx + cell - 4, sy + cell - 4), (sx + cell // 2, sy + 4)])
        # player
        pxs = ox + radius * cell + cell // 2
        pys = oy + radius * cell + cell // 2
        pygame.draw.circle(view, PURPLE, (pxs, pys), 5)
        d = DIRS[facing]
        pygame.draw.line(view, PURPLE, (pxs, pys), (pxs + d[0] * 10, pys + d[1] * 10), 2)
        self.text_small(view, f"pos {pos} facing {DIR_NAMES[facing]}", (12, 6))

    # ---- Wizardry‑style Wireframe ----
    def draw_wireframe(self, grid, pos: Tuple[int, int], facing: int):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((8, 8, 12))
        vw, vh = view.get_size()
        horizon = 42
        max_depth = 6
        rail_col = (180, 180, 220)
        faint = (110, 110, 150)

        def get(x, y):
            if 0 <= x < len(grid[0]) and 0 <= y < len(grid):
                return grid[y][x]
            return T_WALL

        # Precompute perspective rectangles (near to far)
        xL, xR, yT, yB = {}, {}, {}, {}
        for d in range(1, max_depth + 2):  # +1 far boundary
            margin = int(22 + d * 28)
            top = horizon + d * 24
            bottom = vh - top
            xL[d], xR[d], yT[d], yB[d] = margin, vw - margin, top, bottom

        fx, fy = pos
        dx, dy = DIRS[facing]
        ldx, ldy = DIRS[(facing - 1) % 4]
        rdx, rdy = DIRS[(facing + 1) % 4]

        # Always draw corridor rails and crossbars for readability
        for depth in range(1, max_depth + 1):
            t = get(fx + dx * depth, fy + dy * depth)
            # rails (thicker when near)
            thick = 3 if depth == 1 else 2 if depth == 2 else 1
            pygame.draw.line(view, rail_col, (xL[depth], yT[depth]), (xL[depth + 1], yT[depth + 1]), thick)
            pygame.draw.line(view, rail_col, (xR[depth], yT[depth]), (xR[depth + 1], yT[depth + 1]), thick)
            pygame.draw.line(view, rail_col, (xL[depth], yB[depth]), (xL[depth + 1], yB[depth + 1]), thick)
            pygame.draw.line(view, rail_col, (xR[depth], yB[depth]), (xR[depth + 1], yB[depth + 1]), thick)
            # depth crossbars
            pygame.draw.line(view, faint, (xL[depth], yT[depth]), (xR[depth], yT[depth]), 1)
            pygame.draw.line(view, faint, (xL[depth], yB[depth]), (xR[depth], yB[depth]), 1)

        # Side fill lines when an immediate side is a wall (gives strong cue)
        for depth in range(1, max_depth + 1):
            left_x = fx + ldx + dx * (depth - 1)
            left_y = fy + ldy + dy * (depth - 1)
            right_x = fx + rdx + dx * (depth - 1)
            right_y = fy + rdy + dy * (depth - 1)
            col = (200, 200, 240)
            if get(left_x, left_y) == T_WALL:
                pygame.draw.line(view, col, (xL[depth], yT[depth]), (xL[depth], yB[depth]), 2 if depth < 3 else 1)
            if get(right_x, right_y) == T_WALL:
                pygame.draw.line(view, col, (xR[depth], yT[depth]), (xR[depth], yB[depth]), 2 if depth < 3 else 1)

        # Front walls and special glyphs
        for depth in range(1, max_depth + 1):
            ahead_x = fx + dx * depth
            ahead_y = fy + dy * depth
            tile = get(ahead_x, ahead_y)
            if tile == T_WALL:
                col = (220, 220, 255)
                pygame.draw.line(view, col, (xL[depth], yT[depth]), (xR[depth], yT[depth]), 2)
                pygame.draw.line(view, col, (xL[depth], yB[depth]), (xR[depth], yB[depth]), 2)
                pygame.draw.line(view, col, (xL[depth], yT[depth]), (xL[depth], yB[depth]), 2)
                pygame.draw.line(view, col, (xR[depth], yT[depth]), (xR[depth], yB[depth]), 2)
                break
            # draw special node glyphs on the floor plane for near depths
            cx = (xL[depth] + xR[depth]) // 2
            cy = (yB[depth] - 6)
            if tile == T_TOWN and depth <= 3:
                pygame.draw.circle(view, BLUE, (cx, cy), max(2, 8 - depth))
            elif tile == T_STAIRS_D and depth <= 3:
                pygame.draw.polygon(view, YELLOW, [(cx - 6, cy - 2), (cx + 6, cy - 2), (cx, cy - 12)])
            elif tile == T_STAIRS_U and depth <= 3:
                pygame.draw.polygon(view, GREEN, [(cx - 6, cy - 6), (cx + 6, cy - 6), (cx, cy + 4)])

        self.text_small(view, f"Wireframe (V)  pos {pos}  {DIR_NAMES[facing]}", (12, 6))


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
        self.turn_index = 0  # party index
        self.awaiting_input = True
        self.battle_over = False

    def start_random(self):
        count = random.randint(1, 3)
        self.enemies = [Enemy.random_enemy() for _ in range(count)]
        self.log.add(f"Ambushed by {', '.join(e.name for e in self.enemies)}!")
        self.turn_index = 0
        self.awaiting_input = True

    def current_actor(self) -> Optional[Character]:
        alive = self.party.alive_members()
        if not alive:
            return None
        if self.turn_index >= len(alive):
            self.turn_index = 0
        return alive[self.turn_index]

    def enemy_alive(self) -> bool:
        return any(e.hp > 0 for e in self.enemies)

    def step_enemies(self):
        # enemies act once per round after party
        for e in self.enemies:
            if e.hp <= 0:
                continue
            targets = self.party.alive_members()
            if not targets:
                break
            t = random.choice(targets)
            dmg = random.randint(e.atk_low, e.atk_high)
            hit = random.random() < 0.65
            if hit:
                t.hp -= dmg
                if t.hp <= 0:
                    t.hp = 0
                    t.alive = False
                    self.log.add(f"{e.name} hits {t.name} for {dmg}. {t.name} is down!")
                else:
                    self.log.add(f"{e.name} hits {t.name} for {dmg}.")
                # trigger party hit effect
                try:
                    idx = self.party.members.index(t)
                    self.effects.trigger("party", idx, duration_ms=300, intensity=5)
                except ValueError:
                    pass
            else:
                self.log.add(f"{e.name} misses {t.name}.")

    def end_round_and_check(self) -> bool:
        # cleanup dead enemies, check victory/defeat
        self.enemies = [e for e in self.enemies if e.hp > 0]
        if not self.enemy_alive():
            total_exp = random.randint(20, 60)
            total_gold = random.randint(10, 40)
            for m in self.party.alive_members():
                m.exp += total_exp // max(1, len(self.party.alive_members()))
                m.gold += total_gold // max(1, len(self.party.members))
            self.log.add(f"Victory! +~{total_exp} EXP, +~{total_gold}g")
            self.battle_over = True
            return True
        if not self.party.any_alive():
            self.log.add("The party has fallen...")
            self.battle_over = True
            return True
        return False

    def party_attack(self, actor: Character):
        # choose first alive enemy
        target = next((e for e in self.enemies if e.hp > 0), None)
        if not target:
            return
        # simple hit calc: base 65% + attack bonus*3% - target AC*2%
        hit_chance = 0.65 + actor.atk_bonus * 0.03 - (10 - target.ac) * 0.02
        if random.random() < hit_chance:
            dmg = max(1, random.randint(1, 6) + actor.atk_bonus)
            target.hp -= dmg
            self.log.add(f"{actor.name} hits {target.name} for {dmg}.")
            # trigger enemy hit effect
            try:
                idx = self.enemies.index(target)
                self.effects.trigger("enemy", idx, duration_ms=300, intensity=6)
            except ValueError:
                pass
        else:
            self.log.add(f"{actor.name} misses {target.name}.")

    def party_cast(self, actor: Character):
        if actor.cls != "Mage" or actor.mp <= 0:
            self.log.add(f"{actor.name} cannot cast.")
            return
        target = next((e for e in self.enemies if e.hp > 0), None)
        if not target:
            return
        actor.mp -= 1
        dmg = random.randint(4, 8) + ability_mod(actor.iq)
        dmg = max(1, dmg)
        target.hp -= dmg
        self.log.add(f"{actor.name} casts Spark for {dmg}!")
        try:
            idx = self.enemies.index(target)
            self.effects.trigger("enemy", idx, duration_ms=350, intensity=7)
        except ValueError:
            pass

    def party_heal(self, actor: Character):
        if actor.cls != "Priest" or actor.mp <= 0:
            self.log.add(f"{actor.name} cannot heal.")
            return
        target = min((m for m in self.party.members if m.alive), key=lambda c: c.hp / max(1, c.max_hp), default=None)
        if not target:
            return
        actor.mp -= 1
        amt = random.randint(6, 10) + ability_mod(actor.piety)
        amt = max(1, amt)
        target.hp = min(target.max_hp, target.hp + amt)
        self.log.add(f"{actor.name} heals {target.name} for {amt}.")

    def try_run(self):
        if random.random() < 0.55:
            self.log.add("You successfully fled!")
            self.battle_over = True
        else:
            self.log.add("You failed to run!")


# ------------------------------ Game ---------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Wizardry‑style Dungeon RPG (Wireframe Levels)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.r = Renderer(self.screen)
        self.log = MessageLog()
        self.party = Party()
        self.mode = MODE_TOWN
        self.view_style = VIEW_WIREFRAME

        self.dun = Dungeon(MAZE_W, MAZE_H)
        self.level_ix = 0
        self.dun.ensure_level(0)
        self.pos = (2, 2)  # entrance
        self.facing = 1  # East
        self.effects = HitEffects()
        self.in_battle: Optional[Battle] = None

        self.menu_index = 0
        self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
        self.shop_index = 0

        # encounter timer — roll per step
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

    # --------------- Town ---------------
    def draw_town(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Town Square", (20, 16))
        options = [
            "Tavern (Party)",
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
        self.r.text_small(view, "Up/Down + Enter. All members must be alive to enter.", (32, y + 6), LIGHT)

    def town_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                self.menu_index = (self.menu_index - 1) % 6
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % 6
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_town_option(self.menu_index)
            elif pygame.K_1 <= event.key <= pygame.K_6:
                self.select_town_option(event.key - pygame.K_1)

    def select_town_option(self, ix):
        if ix == 0:
            self.mode = MODE_PARTY
        elif ix == 1:
            self.mode = MODE_TRAINING
        elif ix == 2:
            self.mode = MODE_TEMPLE
        elif ix == 3:
            self.mode = MODE_SHOP
        elif ix == 4:
            if not self.party.all_alive():
                self.log.add("You need a full, alive party to enter the Labyrinth.")
            else:
                # enter level 0 at entrance
                self.level_ix = 0
                self.dun.ensure_level(0)
                self.pos = (2, 2)
                self.facing = 1
                self.mode = MODE_MAZE
                self.log.add("You descend into the Labyrinth...")
        elif ix == 5:
            self.mode = MODE_SAVELOAD

    # --------------- Party / Creation ---------------
    def draw_party(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Tavern — Party", (20, 16))
        y = 50
        for i, m in enumerate(self.party.members):
            self.r.text(view, f"{i+1}. {m.name} Lv{m.level} {m.cls}", (32, y)); y += 18
            self.r.text_small(view, f"HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}  AC {m.defense_ac:+}  ATK {m.atk_bonus:+}", (44, y)); y += 16
        y += 6
        self.r.text_small(view, "N: New  D: Dismiss  Esc: Back", (32, y), LIGHT)

    def party_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_n:
                self.mode = MODE_CREATE
                self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
            elif event.key == pygame.K_d:
                if self.party.members:
                    self.party.members.pop()
                    self.log.add("Last party member dismissed.")
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    def draw_create(self):
        s = self.create_state
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Create Adventurer", (20, 16))
        y = 60
        if s["step"] == 0:
            self.r.text(view, "Enter name: ", (32, y))
            self.r.text(view, s["name"] + "_", (170, y), YELLOW)
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
            self.r.text_small(view, "Enter: Accept  R: Reroll  Esc: Cancel", (32, y2 + 66), LIGHT)

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
                if event.key == pygame.K_RETURN:
                    newc = Character(s["name"], RACES[s["race_ix"]], CLASSES[s["class_ix"]])
                    if len(self.party.members) < 6:
                        self.party.members.append(newc)
                        self.log.add(f"{newc.name} the {newc.cls} joins the party.")
                    else:
                        self.log.add("Party is full.")
                    self.mode = MODE_PARTY
                elif event.key == pygame.K_r:
                    s["step"] = 2; s["step"] = 3
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_PARTY

    # --------------- Shop & Temple & Training ---------------
    def draw_shop(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
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
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Temple — Healer", (20, 16))
        y = 56
        for i, m in enumerate(self.party.members):
            self.r.text(view, f"{i+1}. {m.name} HP {m.hp}/{m.max_hp} {'(DOWN)' if not m.alive else ''}", (32, y))
            y += 18
        self.r.text_small(view, "1‑6 heal (10g) / revive (50g). Esc: Back", (32, y + 4), LIGHT)

    def temple_input(self, event):
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_6:
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
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Training Grounds", (20, 16))
        y = 56
        self.r.text_small(view, "Each level costs 100 EXP. Press number to level up.", (32, y)); y += 18
        for i, m in enumerate(self.party.members):
            self.r.text(view, f"{i+1}. {m.name} Lv{m.level} EXP {m.exp}", (32, y)); y += 18
        self.r.text_small(view, "Esc: Back", (32, y + 4), LIGHT)

    def training_input(self, event):
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_6:
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
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Save / Load", (20, 16))
        self.r.text(view, "S: Save  L: Load  Esc: Back", (32, 56), LIGHT)

    def saveload_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_s:
                self.save()
            elif event.key == pygame.K_l:
                self.load()
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
            self.check_special_tile()
            # encounter?
            if random.random() < self.encounter_rate:
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
        # ensure new level exists with stairs up at arrival position
        self.dun.ensure_level(self.level_ix, arrival_pos=down_pos)
        # place player at that same coordinate
        self.pos = down_pos
        self.facing = 1
        self.mode = MODE_MAZE
        self.log.add(f"Descend to level {self.level_ix}.")

    def go_up_stairs(self):
        if self.level_ix == 0:
            self.log.add("You are at the surface level.")
            return
        prev_level = self.level_ix - 1
        # go back to previous level at its stairs down position
        up_from_here = self.pos
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
        if self.view_style == VIEW_TOPDOWN:
            self.r.draw_topdown(self.grid(), self.pos, self.facing)
        else:
            self.r.draw_wireframe(self.grid(), self.pos, self.facing)
        # footer
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        self.r.text_small(view, f"L{self.level_ix}  Arrows: move/turn  V: view  Esc: Town", (12, VIEW_H - 22), LIGHT)

    def maze_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.turn_left()
            elif event.key == pygame.K_RIGHT:
                self.turn_right()
            elif event.key == pygame.K_UP:
                self.step_forward()
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN
            elif event.key == pygame.K_v:
                self.view_style = VIEW_TOPDOWN if self.view_style == VIEW_WIREFRAME else VIEW_WIREFRAME

    # --------------- Battle ---------------
    def draw_battle(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH - PANEL_W, VIEW_H))
        view.fill((12, 12, 18))
        self.r.text_big(view, "Battle!", (20, 16))
        # enemies (apply hit effects)
        y = 54
        for i, e in enumerate(self.in_battle.enemies):
            (ox, oy), color = self.effects.sample("enemy", i, base_color=WHITE)
            bar_w = 220
            hp_ratio = max(0.0, e.hp / 20.0)
            pygame.draw.rect(view, (50, 50, 80), (40 + ox, y + oy, bar_w, 14), 1)
            pygame.draw.rect(view, RED, (40 + ox, y + oy, int(bar_w * hp_ratio), 14))
            self.r.text_small(view, f"{e.name}  HP:{e.hp:>2}", (270 + ox, y - 2 + oy), color)
            y += 22
        # current actor
        actor = self.in_battle.current_actor()
        if actor is not None:
            self.r.text_small(view, f"{actor.name}'s turn — A,S,H,R", (40, VIEW_H - 44), LIGHT)
        else:
            self.r.text_small(view, "Enemy phase...", (40, VIEW_H - 44), LIGHT)

    def battle_input(self, event):
        b = self.in_battle
        if event.type == pygame.KEYDOWN and not b.battle_over:
            actor = b.current_actor()
            if not actor:
                return
            if event.key == pygame.K_a:
                b.party_attack(actor)
                b.turn_index += 1
            elif event.key == pygame.K_s:
                b.party_cast(actor)
                b.turn_index += 1
            elif event.key == pygame.K_h:
                b.party_heal(actor)
                b.turn_index += 1
            elif event.key == pygame.K_r:
                b.try_run()
            # end of party round?
            if b.turn_index >= len(self.party.alive_members()) and not b.battle_over:
                b.step_enemies()
                b.turn_index = 0
            # check victory/defeat
            if b.end_round_and_check():
                self.mode = MODE_MAZE if self.party.any_alive() and not b.battle_over else MODE_TOWN

    # --------------- Gold helpers ---------------
    def total_gold(self) -> int:
        return sum(m.gold for m in self.party.members)

    def take_gold(self, amount: int):
        if self.party.members:
            self.party.members[0].gold = max(0, self.party.members[0].gold - amount)

    # --------------- Main loop ---------------
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    if self.mode == MODE_TOWN:
                        self.town_input(event)
                    elif self.mode == MODE_PARTY:
                        self.party_input(event)
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
                    elif self.mode == MODE_BATTLE:
                        self.battle_input(event)

            # draw
            self.r.draw_frame()
            if self.mode == MODE_TOWN:
                self.draw_town()
            elif self.mode == MODE_PARTY:
                self.draw_party()
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
            elif self.mode == MODE_BATTLE:
                self.draw_battle()

            self.r.draw_party_panel(self.party, self.effects)
            self.r.draw_log(self.log.lines)
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
