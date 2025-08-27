#!/usr/bin/env python3
"""
Wizardry‑style dungeon RPG — single‑file Pygame prototype (Top‑down, 4‑party, Pause Menu, Levels)

Updates in this version
- Removed wireframe view (top‑down only) and the right‑side status panel
- Max **active party** size is now **4**; choose actives from Town (Form Party)
- Town options include **Status** screen and **Form Party (choose Active)**
- Labyrinth: victory/flee returns to the maze at the same position
- No random encounters when stepping onto **Stairs** or **Town** tiles
- Pause menu in labyrinth (press **Esc**): **Status / Items / Close**
  - **Status** shows the same party status screen; closing returns to the pause menu
  - **Items** lists active members' inventories; use items (e.g., potions) here; closing returns to the pause menu
  - **Close** resumes the labyrinth
- Multi‑level dungeon persists: Town node (blue), Stairs Down (yellow △), Stairs Up (green ▽)
- Local font: uses `fonts/prstart.ttf` with system fallback

Controls
- Menus: Arrow keys / number keys / Enter / Esc
- Maze: ←/→ turn, ↑ move, Esc pause menu
- Battle: A Attack, S Spell (Mage), H Heal (Priest), R Run

Tested with: Python 3.10+, pygame 2.5+
"""

import json
import os
import random
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
MODE_TOWN = "TOWN"
MODE_CREATE = "CREATE"
MODE_PARTY = "PARTY"       # roster management
MODE_FORM = "FORM"         # choose active party (max 4)
MODE_STATUS = "STATUS"     # view status screen
MODE_SHOP = "SHOP"
MODE_TEMPLE = "TEMPLE"
MODE_TRAINING = "TRAINING"
MODE_MAZE = "MAZE"
MODE_BATTLE = "BATTLE"
MODE_SAVELOAD = "SAVELOAD"
MODE_PAUSE = "PAUSE"       # pause menu in maze
MODE_ITEMS = "ITEMS"       # item use screen from pause

# Map tiles
T_EMPTY = 0
T_WALL = 1
T_TOWN = 2      # node returns to town
T_STAIRS_D = 3  # stairs down
T_STAIRS_U = 4  # stairs up

# Limits
ACTIVE_MAX = 4
ROSTER_MAX = 10

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
ITEMS_BY_ID = {it["id"]: it for it in SHOP_ITEMS}

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
        c = Character(d["name"], d["race"], d["cls"])  # will roll stats but overwrite
        for k, v in d.items():
            if k == "equipment":
                c.equipment = Equipment(**v)
            elif hasattr(c, k):
                setattr(c, k, v)
        return c


class Party:
    def __init__(self):
        self.members: List[Character] = []
        self.active: List[int] = []  # indices into members

    # Roster helpers
    def alive_members(self) -> List[Character]:
        return [c for c in self.members if c.alive and c.hp > 0]

    # Active helpers
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


# ------------------------------ Hit Effects --------------------------------
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
        pygame.draw.rect(self.screen, (30, 30, 34), (0, 0, WIDTH, VIEW_H))  # view
        pygame.draw.rect(self.screen, (28, 28, 32), (0, VIEW_H, WIDTH, LOG_H))  # log

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

    # ---- Top‑down ----
    def draw_topdown(self, grid, pos: Tuple[int, int], facing: int, level_ix: int):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 22))
        cell = 18
        ox, oy = 20, 20
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
        pygame.draw.circle(view, PURPLE, (pxs, pys), 6)
        d = DIRS[facing]
        pygame.draw.line(view, PURPLE, (pxs, pys), (pxs + d[0] * 12, pys + d[1] * 12), 2)
        self.text_small(view, f"L{level_ix} pos {pos} {DIR_NAMES[facing]}", (12, 6))


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
        self.result: Optional[str] = None  # 'victory' | 'defeat' | 'fled'

    def start_random(self):
        count = random.randint(1, 3)
        self.enemies = [Enemy.random_enemy() for _ in range(count)]
        self.log.add(f"Ambushed by {', '.join(e.name for e in self.enemies)}!")
        self.turn_index = 0

    def current_actor(self) -> Optional[Character]:
        alive = self.party.alive_active_members()
        if not alive:
            return None
        if self.turn_index >= len(alive):
            self.turn_index = 0
        return alive[self.turn_index]

    def enemy_alive(self) -> bool:
        return any(e.hp > 0 for e in self.enemies)

    def step_enemies(self):
        for e in self.enemies:
            if e.hp <= 0:
                continue
            targets = self.party.alive_active_members()
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
                # optional: party shake effect (not visible without panel)
            else:
                self.log.add(f"{e.name} misses {t.name}.")

    def end_round_and_check(self) -> bool:
        self.enemies = [e for e in self.enemies if e.hp > 0]
        if not self.enemy_alive():
            total_exp = random.randint(20, 60)
            total_gold = random.randint(10, 40)
            alive = self.party.alive_active_members()
            for m in alive:
                m.exp += total_exp // max(1, len(alive))
                m.gold += total_gold // max(1, len(self.party.active_members()))
            self.log.add(f"Victory! +~{total_exp} EXP, +~{total_gold}g")
            self.battle_over = True
            self.result = 'victory'
            return True
        if not self.party.any_active_alive():
            self.log.add("The party has fallen...")
            self.battle_over = True
            self.result = 'defeat'
            return True
        return False

    def party_attack(self, actor: Character):
        target = next((e for e in self.enemies if e.hp > 0), None)
        if not target:
            return
        hit_chance = 0.65 + actor.atk_bonus * 0.03 - (10 - target.ac) * 0.02
        if random.random() < hit_chance:
            dmg = max(1, random.randint(1, 6) + actor.atk_bonus)
            target.hp -= dmg
            self.log.add(f"{actor.name} hits {target.name} for {dmg}.")
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
        dmg = max(1, random.randint(4, 8) + ability_mod(actor.iq))
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
        target = min((m for m in self.party.active_members() if m.alive), key=lambda c: c.hp / max(1, c.max_hp), default=None)
        if not target:
            return
        actor.mp -= 1
        amt = max(1, random.randint(6, 10) + ability_mod(actor.piety))
        target.hp = min(target.max_hp, target.hp + amt)
        self.log.add(f"{actor.name} heals {target.name} for {amt}.")

    def try_run(self):
        if random.random() < 0.55:
            self.log.add("You fled!")
            self.battle_over = True
            self.result = 'fled'
        else:
            self.log.add("You failed to run!")


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
        self.mode = MODE_TOWN
        self.return_mode = MODE_TOWN  # where to return after modal screens

        self.dun = Dungeon(MAZE_W, MAZE_H)
        self.level_ix = 0
        self.dun.ensure_level(0)
        self.pos = (2, 2)
        self.facing = 1  # East
        self.effects = HitEffects()
        self.in_battle: Optional[Battle] = None

        self.menu_index = 0
        self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
        self.shop_index = 0
        self.pause_index = 0

        # Items UI state
        self.items_phase = 'member'  # 'member' -> 'items'
        self.items_member_ix = 0
        self.items_item_ix = 0

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
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Town Square", (20, 16))
        options = [
            "Tavern (Roster)",         # 0
            "Form Party (Choose Active)", # 1
            "Status",                  # 2
            "Training (Level Up)",     # 3
            "Temple (Heal/Revive)",    # 4
            "Trader (Shop)",           # 5
            "Enter the Labyrinth",     # 6
            "Save / Load",             # 7
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

    # --------------- Party / Creation ---------------
    def draw_party(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Tavern — Roster", (20, 16))
        y = 50
        for i, m in enumerate(self.party.members):
            active_tag = "*" if i in self.party.active else " "
            self.r.text(view, f"{i+1:>2}{active_tag} {m.name} Lv{m.level} {m.cls}", (32, y)); y += 18
            self.r.text_small(view, f"HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}  AC {m.defense_ac:+}  ATK {m.atk_bonus:+}", (44, y)); y += 14
        y += 6
        self.r.text_small(view, "N: New  D: Dismiss last  Esc: Back", (32, y), LIGHT)

    def party_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_n:
                if len(self.party.members) >= ROSTER_MAX:
                    self.log.add("Roster is full.")
                else:
                    self.mode = MODE_CREATE
                    self.create_state = {"step": 0, "name": "", "race_ix": 0, "class_ix": 0}
            elif event.key == pygame.K_d:
                if self.party.members:
                    ix = len(self.party.members) - 1
                    self.party.members.pop()
                    if ix in self.party.active:
                        self.party.active.remove(ix)
                    self.party.clamp_active()
                    self.log.add("Last roster member dismissed.")
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

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

    def draw_status(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Status", (20, 16))
        y = 50
        # Active first
        if self.party.active:
            self.r.text(view, "Active:", (32, y)); y += 18
            for idx in self.party.active:
                if 0 <= idx < len(self.party.members):
                    m = self.party.members[idx]
                    self.r.text(view, f"• {m.name} Lv{m.level} {m.cls}", (48, y)); y += 16
                    self.r.text_small(view, f"HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}  STR {m.str_} IQ {m.iq} PIE {m.piety} VIT {m.vit} AGI {m.agi} LCK {m.luck}", (60, y)); y += 14
            y += 8
        self.r.text(view, "Roster:", (32, y)); y += 18
        for i, m in enumerate(self.party.members):
            star = "*" if i in self.party.active else " "
            self.r.text_small(view, f"{star} {i+1:>2} {m.name} Lv{m.level} {m.cls}  HP {m.hp}/{m.max_hp}  MP {m.mp}/{m.max_mp}", (48, y)); y += 14
        y += 6
        self.r.text_small(view, "Esc: Close", (32, y), LIGHT)

    def status_input(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.mode = self.return_mode

    def draw_create(self):
        s = self.create_state
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
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
                    if len(self.party.members) >= ROSTER_MAX:
                        self.log.add("Roster is full.")
                    else:
                        newc = Character(s["name"], RACES[s["race_ix"]], CLASSES[s["class_ix"]])
                        self.party.members.append(newc)
                        self.log.add(f"{newc.name} the {newc.cls} joins the roster.")
                    self.mode = MODE_PARTY
                elif event.key == pygame.K_r:
                    s["step"] = 2; s["step"] = 3
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_PARTY

    # --------------- Shop & Temple & Training ---------------
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
            # special tile behavior first
            special = self.grid()[ny][nx] in (T_TOWN, T_STAIRS_D, T_STAIRS_U)
            self.check_special_tile()
            # encounters only on empty tiles
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
        # dim overlay
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
                if self.pause_index == 0:  # Status
                    self.return_mode = MODE_PAUSE
                    self.mode = MODE_STATUS
                elif self.pause_index == 1:  # Items
                    self.items_phase = 'member'
                    self.items_member_ix = 0
                    self.items_item_ix = 0
                    self.mode = MODE_ITEMS
                elif self.pause_index == 2:  # Close
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
        else:  # items list for selected member
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
            else:  # items phase
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
                        # remove item if consumed
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
        # you can extend with more items here

    # --------------- Battle ---------------
    def draw_battle(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((12, 12, 18))
        self.r.text_big(view, "Battle!", (20, 16))
        # enemies with hit effects
        y = 54
        for i, e in enumerate(self.in_battle.enemies):
            (ox, oy), color = self.effects.sample("enemy", i, base_color=WHITE)
            bar_w = 240
            hp_ratio = max(0.0, e.hp / 20.0)
            pygame.draw.rect(view, (50, 50, 80), (40 + ox, y + oy, bar_w, 14), 1)
            pygame.draw.rect(view, RED, (40 + ox, y + oy, int(bar_w * hp_ratio), 14))
            self.r.text_small(view, f"{e.name}  HP:{e.hp:>2}", (290 + ox, y - 2 + oy), color)
            y += 22
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
            if b.turn_index >= len(self.party.alive_active_members()) and not b.battle_over:
                b.step_enemies()
                b.turn_index = 0
            if b.end_round_and_check():
                if b.result in ('victory', 'fled'):
                    self.mode = MODE_MAZE
                else:
                    self.mode = MODE_TOWN

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
            _dt = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    if self.mode == MODE_TOWN:
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

            # draw
            self.r.draw_frame()
            if self.mode == MODE_TOWN:
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
