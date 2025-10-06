#!/usr/bin/env python3
"""
Wizardry-style dungeon RPG — single-file Pygame prototype (Top-down, 4-party, Menus, Animations)

Update summary
- Centered menus now have **no headers** (cleaner look).
- Tavern actions are **Create / Dismiss / Back** and the menu opens **automatically**.
- **Back** in Tavern returns to **Town**.
- **Dismiss** now lets you choose a character and confirms via a popup.
- (Kept from prior) Target selection in battle, inter-animation pauses, acting highlights, enemy windows, etc.

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
MUSIC_ELITE_BATTLE = "elite_battle.ogg"
MUSIC_PROLOGUE = "violet_eerie_ambient.wav"
MUSIC_ENDING = "violet_ending_ambient.wav"

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
MODE_PROLOGUE = "PROLOGUE"
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
MODE_TRAIT = "TRAIT"   # post-creation trait selection
MODE_DIALOG = "DIALOG" # NPC dialog
MODE_QUESTS = "QUESTS" # Quests list
MODE_WAYPOINT = "WAYPOINT"  # Waypoint fast-travel selection
MODE_ENDING_TRANSITION = "ENDING_TRANSITION"
MODE_ENDING = "ENDING"

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
T_LOCKED = 5
T_END = 6

# Limits
ACTIVE_MAX = 4
ROSTER_MAX = 10

# ------------------------------ Data Models --------------------------------
CLASSES = ["Fighter", "Mage", "Priest", "Rogue"]

BASE_HP = {"Fighter": 12, "Mage": 6, "Priest": 8, "Rogue": 8}
BASE_MP = {"Fighter": 0, "Mage": 8, "Priest": 6, "Rogue": 0}
AC_BASE = 10

# Data resources are loaded from JSON (monsters, items, skills, levels)
# Module-level placeholders populated by Game.load_data()
SHOP_ITEMS: List[Dict[str, Any]] = []
ITEMS_BY_ID: Dict[str, Dict[str, Any]] = {}

BONUS_KEY_MAP = {
    'str': 'STR',
    'iq': 'IQ',
    'pie': 'PIE',
    'piety': 'PIE',
    'vit': 'VIT',
    'agi': 'AGI',
    'hp': 'HP',
    'mp': 'MP',
}

# Recruiting costs per class (party pays on creation)
CLASS_COSTS = {"Rogue": 25, "Fighter": 35, "Priest": 40, "Mage": 45}

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
            'elite_battle': self._load_sound(MUSIC_ELITE_BATTLE),
            'prologue': self._load_sound(MUSIC_PROLOGUE),
            'ending': self._load_sound(MUSIC_ENDING),
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
        self._last_play_ms: Dict[str, int] = {}
        self._len_ms_cache: Dict[str, int] = {}
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
            'voice_human_man': self._load('voice_human_man', 'sfx_voice_human_man'),
        }

    def play(self, key: str, volume: float = 1.0):
        if not self.enabled:
            return
        snd = self.sounds.get(key)
        if snd is None:
            return
        try:
            # Avoid overlapping voice ticks: if a voice clip is still playing, skip
            if key.startswith('voice_'):
                now = pygame.time.get_ticks()
                ln = self._len_ms_cache.get(key)
                if ln is None:
                    try:
                        ln = int(snd.get_length() * 1000)
                    except Exception:
                        ln = 120
                    self._len_ms_cache[key] = ln
                last = self._last_play_ms.get(key, -10**9)
                if now - last < max(60, ln):
                    return
            old = snd.get_volume()
            snd.set_volume(max(0.0, min(1.0, volume)))
            ch = snd.play()
            snd.set_volume(old)
            if key.startswith('voice_'):
                # Record start time to throttle subsequent plays
                self._last_play_ms[key] = pygame.time.get_ticks()
        except Exception:
            pass


def roll_stat():
    return sum(random.randint(1, 6) for _ in range(3))


def ability_mod(score: int) -> int:
    return (score - 5) // 2


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
    statuses: Dict[str, int] = field(default_factory=dict)
    gear_bonus: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        base_hp = BASE_HP[self.cls]
        self.max_hp = max(1, base_hp + ability_mod(self.vit))
        self.hp = self.max_hp
        self.max_mp = max(0, BASE_MP[self.cls] + ability_mod(self.iq if self.cls == "Mage" else self.piety))
        self.mp = self.max_mp

    @property
    def atk_bonus(self) -> int:
        bonus = ability_mod(self.str_) + self.equipment.weapon_atk
        for iid in (self.equipment.armor_id, self.equipment.acc1_id, self.equipment.acc2_id):
            if iid:
                bonus += int(ITEMS_BY_ID.get(iid, {}).get('atk', 0))
        return bonus

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
        return self.agi

    def to_dict(self):
        d = asdict(self)
        d["equipment"] = asdict(self.equipment)
        return d

    @staticmethod
    def from_dict(d):
        # Map legacy class names (e.g., Thief -> Rogue) for backward compatibility
        cls_name = d.get("cls", "Fighter")
        if cls_name == "Thief":
            cls_name = "Rogue"
        c = Character(d["name"], cls_name)
        for k, v in d.items():
            if k == "equipment":
                c.equipment = Equipment(**v)
            elif k == "cls":
                # Normalize legacy class names
                c.cls = "Rogue" if str(v) == "Thief" else str(v)
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
    id: str
    name: str
    hp: int
    max_hp: int
    ac: int
    atk_low: int
    atk_high: int
    exp: int
    gold_low: int
    gold_high: int
    agi: int = 8
    drops: List[Dict[str, Any]] = field(default_factory=list)
    statuses: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def from_base(base: Dict[str, Any], floor_num: int = 1):
        """Create an Enemy from base data.

        Supports legacy schema (hp_low/hp_high/ac/atk_low/atk_high/agi/exp)
        and new schema using archetype + tier. Gold and drops pass through.
        """
        # Common fields
        eid = base.get("id", base.get("name", "monster").lower().replace(' ', '_'))
        name = base.get("name", "Monster")
        gold_low = int(base.get("gold_low", 0))
        gold_high = int(base.get("gold_high", 0))
        drops = list(base.get("drops", [])) if isinstance(base.get("drops", []), list) else []

        # If archetype present, derive combat stats from archetype/tier and floor
        arch = base.get("archetype", base.get("archtype"))
        tier = str(base.get("tier", "mob")).lower()
        if arch:
            L = max(1, int(floor_num))
            archetype = str(arch).lower()
            # Estimate player frontliner HP for damage calibration
            hp_front = 10 + 4 * (L - 1)
            dmg_avg = max(1, int(round(0.25 * hp_front)))
            # Helpers
            def band(avg: int, lo_mult=0.6, hi_mult=1.4):
                lo = max(1, int(round(avg * lo_mult)))
                hi = max(lo + 1, int(round(avg * hi_mult)))
                return lo, hi
            # Base archetype stats
            if archetype in ("bruiser", "fighter"):
                hp = 10 + 6 * (L - 1)
                ac = min(12, 8 + (L // 2))
                agi = 4 + (L // 2)
                atk_low, atk_high = band(dmg_avg, 0.7, 1.4)
            elif archetype in ("skirmisher", "rogue"):
                hp = 6 + 4 * (L - 1)
                ac = min(11, 8 + (L // 3))
                agi = 6 + L
                atk_low, atk_high = band(max(1, dmg_avg - 1), 0.6, 1.5)
            elif archetype in ("acolyte", "priest"):
                hp = 8 + 5 * (L - 1)
                ac = 8 + (L // 3)
                agi = 5 + (L // 2)
                atk_low, atk_high = band(max(1, int(round(dmg_avg * 0.6))), 0.6, 1.3)
            elif archetype in ("adept", "mage"):
                hp = 5 + 3 * (L - 1)
                ac = 7 + (L // 3)
                agi = 5 + (L // 2)
                atk_low, atk_high = band(max(1, int(round(dmg_avg * 0.9))), 0.6, 1.6)
            else:
                # Default generic
                hp = 8 + 5 * (L - 1)
                ac = 8 + (L // 3)
                agi = 5 + (L // 2)
                atk_low, atk_high = band(dmg_avg)
            # Tier adjustments
            if tier == 'elite':
                # Scale HP to approximate the total HP of a 4‑member party at level L
                try:
                    base_sum = int(BASE_HP.get('Fighter', 12)) + int(BASE_HP.get('Rogue', 8)) \
                               + int(BASE_HP.get('Priest', 8)) + int(BASE_HP.get('Mage', 6))
                except Exception:
                    base_sum = 34  # fallback (12+8+8+6)
                party_total_hp = base_sum + 16 * (L - 1)  # ~ +4 HP per member per level
                hp = max(hp, int(party_total_hp))
                ac = min(13, ac + 1)
                atk_low = int(round(atk_low * 1.1)); atk_high = int(round(atk_high * 1.15))
            elif tier == 'boss':
                hp = int(hp * 2.0)
                ac = min(14, ac + 2)
                atk_low = int(round(atk_low * 1.25)); atk_high = int(round(atk_high * 1.35))
            # Build enemy
            return Enemy(
                id=eid, name=name, hp=int(hp), max_hp=int(hp), ac=int(ac), atk_low=int(atk_low), atk_high=int(atk_high),
                exp=0, gold_low=gold_low, gold_high=gold_high, agi=int(agi), drops=drops,
            )

        # Legacy schema fallback
        hp = random.randint(base.get("hp_low", 6), base.get("hp_high", 10))
        # If legacy base indicates elite tier, scale HP similarly
        try:
            if str(base.get('tier','')).lower() == 'elite':
                L = max(1, int(floor_num))
                base_sum = int(BASE_HP.get('Fighter', 12)) + int(BASE_HP.get('Rogue', 8)) \
                           + int(BASE_HP.get('Priest', 8)) + int(BASE_HP.get('Mage', 6))
                party_total_hp = base_sum + 16 * (L - 1)
                hp = max(hp, int(party_total_hp))
        except Exception:
            pass
        return Enemy(
            id=eid, name=name,
            hp=hp,
            max_hp=hp,
            ac=int(base.get("ac", 8)),
            atk_low=int(base.get("atk_low", 1)),
            atk_high=int(base.get("atk_high", 4)),
            exp=int(base.get("exp", 10)),
            gold_low=gold_low,
            gold_high=gold_high,
            agi=int(base.get("agi", random.randint(5, 12))),
            drops=drops,
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
    end_node: Optional[Tuple[int, int]] = None
    # Encounter config loaded from JSON
    encounter_monsters: List[str] = field(default_factory=list)
    encounter_group: Tuple[int, int] = (1, 3)
    # Treasure chests on this level: list of {'x':int,'y':int,'iid':str}
    chests: List[Dict[str, Any]] = field(default_factory=list)
    # NPC nodes on this level: list of {'x':int,'y':int,'id':str}
    npcs: List[Dict[str, Any]] = field(default_factory=list)
    # Elites on this level: list of {'x':int,'y':int,'id':str,'pattern':str}
    elites: List[Dict[str, Any]] = field(default_factory=list)


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
                    try:
                        json_h = len(g)
                        json_w = max(len(row) for row in g if isinstance(row, list))
                    except ValueError:
                        json_h = len(g)
                        json_w = 0
                    json_h = max(1, json_h)
                    json_w = max(1, json_w)
                    newg = generate_base_grid(json_w, json_h)
                    for y in range(json_h):
                        row = g[y] if y < len(g) and isinstance(g[y], list) else []
                        for x in range(json_w):
                            if x < len(row):
                                try:
                                    newg[y][x] = int(row[x])
                                except Exception:
                                    pass
                    lvl.grid = newg
                    # Expand dungeon bounds so procedurally created floors match the largest loaded grid
                    self.w = max(self.w, json_w)
                    self.h = max(self.h, json_h)
                # Markers
                sd = data.get('stairs_down'); su = data.get('stairs_up'); tp = data.get('town_portal')
                lvl.stairs_down = tuple(sd) if isinstance(sd, list) and len(sd) == 2 else lvl.stairs_down
                lvl.stairs_up = tuple(su) if isinstance(su, list) and len(su) == 2 else lvl.stairs_up
                if isinstance(tp, list) and len(tp) == 2:
                    try:
                        tx, ty = int(tp[0]), int(tp[1])
                        lvl.town_portal = (tx, ty)
                    except Exception:
                        pass
                end_pt = data.get('end_node')
                if isinstance(end_pt, list) and len(end_pt) == 2:
                    try:
                        ex, ey = int(end_pt[0]), int(end_pt[1])
                        lvl.end_node = (ex, ey)
                    except Exception:
                        lvl.end_node = None
                # Encounters
                enc = data.get('encounters', {})
                mons = enc.get('monsters', [])
                grp = enc.get('group', [1, 3])
                lvl.encounter_monsters = mons if isinstance(mons, list) else []
                if isinstance(grp, list) and len(grp) == 2:
                    lvl.encounter_group = (int(grp[0]), int(grp[1]))
                # Chests
                chests = data.get('chests', [])
                if isinstance(chests, list):
                    clean = []
                    for c in chests:
                        try:
                            x = int(c.get('x'))
                            y = int(c.get('y'))
                            iid = str(c.get('iid'))
                            clean.append({'x': x, 'y': y, 'iid': iid})
                        except Exception:
                            continue
                    lvl.chests = clean
                # NPCs
                npcs = data.get('npcs', [])
                if isinstance(npcs, list):
                    clean = []
                    for n in npcs:
                        try:
                            x = int(n.get('x'))
                            y = int(n.get('y'))
                            nid = str(n.get('id'))
                            clean.append({'x': x, 'y': y, 'id': nid})
                        except Exception:
                            continue
                    lvl.npcs = clean
                # Elites
                elites = data.get('elites', [])
                if isinstance(elites, list):
                    clean = []
                    for e in elites:
                        try:
                            x = int(e.get('x')); y = int(e.get('y'))
                            mid = str(e.get('id'))
                            pat = str(e.get('pattern', 'up_down'))
                            clean.append({'x': x, 'y': y, 'id': mid, 'pattern': pat})
                        except Exception:
                            continue
                    lvl.elites = clean
        except Exception:
            pass
        if ix == 0 and not lvl.town_portal:
            lvl.town_portal = (2, 2)
        if lvl.town_portal:
            try:
                x, y = int(lvl.town_portal[0]), int(lvl.town_portal[1])
                if 0 <= y < len(lvl.grid) and 0 <= x < len(lvl.grid[0]):
                    lvl.grid[y][x] = T_TOWN
            except Exception:
                pass
        if lvl.end_node:
            try:
                ex, ey = int(lvl.end_node[0]), int(lvl.end_node[1])
                if 0 <= ey < len(lvl.grid) and 0 <= ex < len(lvl.grid[0]):
                    lvl.grid[ey][ex] = T_END
            except Exception:
                lvl.end_node = None
        if arrival_pos is not None and not lvl.stairs_up:
            try:
                ax, ay = int(arrival_pos[0]), int(arrival_pos[1])
                lvl.stairs_up = (ax, ay)
                if 0 <= ay < len(lvl.grid) and 0 <= ax < len(lvl.grid[0]):
                    lvl.grid[ay][ax] = T_STAIRS_U
            except Exception:
                pass
        if not lvl.stairs_down and not lvl.end_node:
            sx, sy = self._find_far_open(ix)
            lvl.stairs_down = (sx, sy)
            lvl.grid[sy][sx] = T_STAIRS_D

    def _find_far_open(self, ix: int) -> Tuple[int, int]:
        grid = self.levels[ix].grid
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        candidates = []
        for y in range(height - 5, 2, -1):
            for x in range(width - 5, 2, -1):
                if 0 <= y < height and 0 <= x < width and grid[y][x] == T_EMPTY:
                    candidates.append((x, y))
        if not candidates:
            for y in range(1, max(0, height - 1)):
                for x in range(1, max(0, width - 1)):
                    if 0 <= y < height and 0 <= x < width and grid[y][x] == T_EMPTY:
                        candidates.append((x, y))
        return random.choice(candidates) if candidates else (2, 2)


# ------------------------------ Hit/FX --------------------------------------
class HitEffects:
    def __init__(self):
        self.effects: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def trigger(self, kind: str, index: int, duration_ms: int = 300, intensity: int = 5, color: Tuple[int, int, int] = RED):
        now = pygame.time.get_ticks()
        self.effects[(kind, index)] = {"until": now + duration_ms, "duration": duration_ms, "intensity": intensity, "color": color}

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
        flash_color = e.get("color", RED)
        color = flash_color if (now // 60) % 2 == 0 else base_color
        return (ox, oy), color


# ------------------------------ Rendering ----------------------------------
class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = self._load_font(16)
        self.font_small = self._load_font(12)
        self.font_big = self._load_font(20)
        # Status color mapping for stack displays
        self.status_colors: Dict[str, Tuple[int, int, int]] = {
            'bleed': RED,
            'poison': GREEN,
            'regen': YELLOW,
            'reassemble': (120, 220, 160),
            'blind': GRAY,
            'vulnerable': (240, 140, 60),  # orange
            'weak': BLUE,
            'stun': PURPLE,
        }

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
                     player_frac: Tuple[float, float] = (0.0, 0.0),
                     visible_tiles: set = None, seen_tiles: set = None, apply_fov: bool = False,
                     chests: List[Dict[str, Any]] = None, npcs: List[Dict[str, Any]] = None,
                     elites: List[Dict[str, Any]] = None):
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
                        elif t == T_LOCKED:
                            # Draw a locked door as a thick line with a small lock glyph
                            pygame.draw.rect(view, (36, 28, 22), (sx, sy + cell//3, cell - 1, cell//3))
                            pygame.draw.rect(view, (120, 100, 60), (sx, sy + cell//3, cell - 1, cell//3), 2)
                            # lock
                            lx = sx + cell//2 - 4; ly = sy + cell//2 - 6
                            pygame.draw.rect(view, (200, 180, 90), (lx, ly, 8, 8), 1)
                        elif t == T_END:
                            # Pulsing end node: bright purple core with soft glow
                            tick = pygame.time.get_ticks()
                            phase = (math.sin(tick / 260.0) + 1.0) * 0.5
                            cx = sx + cell // 2
                            cy = sy + cell // 2
                            core_radius = max(3, int(cell * (0.26 + 0.08 * phase)))
                            pygame.draw.circle(view, (210, 170, 255), (cx, cy), core_radius)
                            shell_radius = max(core_radius + 2, int(cell * (0.42 + 0.10 * phase)))
                            pygame.draw.circle(view, (160, 100, 240), (cx, cy), shell_radius, 2)
                            glow_size = int(cell * 2.2)
                            glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                            glow_center = glow_size // 2
                            outer_radius = min(glow_center, max(shell_radius + cell // 3, cell // 2))
                            inner_radius = max(core_radius + 2, int(outer_radius * 0.55))
                            pygame.draw.circle(glow, (150, 80, 220, int(110 + 60 * phase)), (glow_center, glow_center), outer_radius)
                            pygame.draw.circle(glow, (200, 150, 255, int(70 + 40 * phase)), (glow_center, glow_center), inner_radius)
                            view.blit(glow, (cx - glow_center, cy - glow_center))
        # Draw chests on top of floor tiles (simple icon), within the radius window
        if chests:
            for c in chests:
                cx, cy = int(c.get('x', -9999)), int(c.get('y', -9999))
                if py - radius <= cy <= py + radius and px - radius <= cx <= px + radius:
                    sx = ox + (cx - (px - radius)) * cell + int(shift_px[0])
                    sy = oy + (cy - (py - radius)) * cell + int(shift_px[1])
                    rect = pygame.Rect(sx + cell//4, sy + cell//3, cell//2, cell//3)
                    pygame.draw.rect(view, (120, 90, 40), rect)
                    pygame.draw.rect(view, (80, 60, 30), rect, 2)
        # Draw NPCs as small cyan dots with outline and initial, within the radius window
        if npcs:
            for n in npcs:
                try:
                    nx, ny = int(n.get('x', -9999)), int(n.get('y', -9999))
                except Exception:
                    continue
                if py - radius <= ny <= py + radius and px - radius <= nx <= px + radius:
                    sx = ox + (nx - (px - radius)) * cell + int(shift_px[0])
                    sy = oy + (ny - (py - radius)) * cell + int(shift_px[1])
                    cx = sx + cell // 2; cy = sy + cell // 2
                    r = max(4, cell // 5)
                    # outline
                    pygame.draw.circle(view, (10, 10, 14), (cx, cy), r + 2)
                    # fill
                    pygame.draw.circle(view, (60, 200, 200), (cx, cy), r)
                    # initial
                    try:
                        ch = str(n.get('id', '?'))[:1].upper()
                        self.text_small(view, ch, (cx - 3, cy - 6), (0,0,0))
                    except Exception:
                        pass
        # player marker
        pxs = ox + radius * cell + cell // 2
        pys = oy + radius * cell + cell // 2 + int(player_bob_px)
        pygame.draw.circle(view, PURPLE, (pxs, pys), max(4, cell // 4))
        d = DIRS[facing]
        pygame.draw.line(view, PURPLE, (pxs, pys), (pxs + d[0] * max(10, cell // 2), pys + d[1] * max(10, cell // 2)), 2)
        # Optional overlays: fog-of-war or legacy torch FOV
        if seen_tiles is not None:
            fog = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            now = pygame.time.get_ticks() / 1000.0
            for y in range(py - radius, py + radius + 1):
                for x in range(px - radius, px + radius + 1):
                    if not (0 <= x < len(grid[0]) and 0 <= y < len(grid)):
                        continue
                    sx = ox + (x - (px - radius)) * cell + int(shift_px[0])
                    sy = oy + (y - (py - radius)) * cell + int(shift_px[1])
                    rect = pygame.Rect(sx, sy, max(1, cell - 1), max(1, cell - 1))
                    if (x, y) not in seen_tiles:
                        # Unseen: match the maze background color for a seamless fog look
                        pygame.draw.rect(fog, (18, 18, 22, 255), rect)
                    else:
                        # Seen: dimmer if not currently visible (lighter than fog of war)
                        if visible_tiles is None or (x, y) not in visible_tiles:
                            pygame.draw.rect(fog, (0, 0, 0, 90), rect)
            view.blit(fog, (0, 0))
        elif apply_fov:
            # Legacy torch FOV
            pxf = px + float(player_frac[0])
            pyf = py + float(player_frac[1])
            self._overlay_torch_fov(view, grid, px, py, facing, cell, ox, oy, radius,
                                     world_px_off=int(shift_px[0]), world_py_off=int(shift_px[1]),
                                     player_center_frac=(pxf, pyf))
        # Draw elites after fog so they are visible
        if elites:
            for e in elites:
                try:
                    ex, ey = int(e.get('x', -9999)), int(e.get('y', -9999))
                    fx, fy = float(e.get('fx', 0.0)), float(e.get('fy', 0.0))
                except Exception:
                    continue
                if py - radius <= ey <= py + radius and px - radius <= ex <= px + radius:
                    sx = ox + (ex - (px - radius) + fx) * cell + int(shift_px[0])
                    sy = oy + (ey - (py - radius) + fy) * cell + int(shift_px[1])
                    pts = [
                        (int(sx + cell*0.5), int(sy + 4)),
                        (int(sx + cell - 4), int(sy + cell*0.5)),
                        (int(sx + cell*0.5), int(sy + cell - 4)),
                        (int(sx + 4), int(sy + cell*0.5)),
                    ]
                    pygame.draw.polygon(view, (220, 140, 40), pts)
                    pygame.draw.polygon(view, (240, 220, 80), pts, 1)
        # Floor/position/direction are rendered by Game.draw_floor_indicator()

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
            return pygame.Rect(0, 0, 0, 0)
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
        return rect

    # ---- Combat HUDs ----
    def draw_combat_party_windows(self, party: "Party", effects: "HitEffects", highlight: set = None, acting: set = None, offsets: Dict[int, int] = None, offsets_x: Dict[int, int] = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
        offsets = offsets or {}
        offsets_x = offsets_x or {}
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
            rx = x + i * (w + gap) + ox + int(offsets_x.get(gi, 0))
            # Apply optional lunge offset (negative moves up)
            ry = y + oy + int(offsets.get(gi, 0))
            rect = pygame.Rect(rx, ry, w, h)
            pygame.draw.rect(view, (20, 20, 28), rect)
            pygame.draw.rect(view, border_col, rect, 2)
            name = m.name[:14]
            self.text(view, name, (rx + 8, ry + 6), border_col)
            self.text_small(view, f"HP {m.hp}/{m.max_hp}", (rx + 8, ry + 26), WHITE)
            self.text_small(view, f"MP {m.mp}/{m.max_mp}", (rx + w // 2 + 8, ry + 26), WHITE)
            # Status stacks at bottom
            stacks: List[Tuple[str, Tuple[int, int, int]]] = []
            order = ['bleed', 'poison', 'regen', 'reassemble', 'blind', 'vulnerable', 'weak', 'stun']
            for key in order:
                try:
                    cnt = int(getattr(m, 'statuses', {}).get(key, 0))
                except Exception:
                    cnt = 0
                if cnt > 0:
                    cnt = min(9, cnt)
                    stacks.append((str(cnt), self.status_colors.get(key, WHITE)))
            if stacks:
                sx = rx + 8
                by = ry + h - self.font_small.get_height() - 4
                for i, (txt, col) in enumerate(stacks):
                    surf = self.font_small.render(txt, True, col)
                    view.blit(surf, (sx, by))
                    sx += surf.get_width() + 6
            rects[gi] = rect
        return rects

    def draw_combat_enemy_windows(self, enemies: List["Enemy"], effects: "HitEffects", highlight: set = None, acting: set = None, dying: Dict[int, float] = None, offsets: Dict[int, int] = None, offsets_x: Dict[int, int] = None, rotations: Dict[int, float] = None) -> Dict[int, pygame.Rect]:
        highlight = highlight or set()
        acting = acting or set()
        dying = dying or {}
        offsets = offsets or {}
        offsets_x = offsets_x or {}
        rotations = rotations or {}
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
            rx = x + j * (w + gap) + ox + int(offsets_x.get(i, 0))
            # Apply optional lunge offset (positive moves down)
            ry = y + oy + int(offsets.get(i, 0))
            rect = pygame.Rect(rx, ry, w, h)
            # draw to a temp surface if fading or rotating
            fade_p = dying.get(i, 0.0)
            angle = float(rotations.get(i, 0.0))
            if fade_p > 0 or abs(angle) > 0.01:
                alpha = max(0, min(255, int(255 * (1.0 - fade_p))))
                temp = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(temp, (20, 20, 28), temp.get_rect())
                pygame.draw.rect(temp, border_col, temp.get_rect(), 2)
                name = e.name[:14]
                temp.blit(self.font.render(name, True, border_col), (8, 6))
                temp.blit(self.font_small.render(f"HP {max(0,e.hp):>2}", True, WHITE), (8, 26))
                if abs(angle) > 0.01:
                    rot = pygame.transform.rotate(temp, angle)
                    rot.set_alpha(alpha)
                    # center the rotated surface over original rect
                    rrect = rot.get_rect(center=(rx + w // 2, ry + h // 2))
                    view.blit(rot, rrect.topleft)
                else:
                    temp.set_alpha(alpha)
                    view.blit(temp, (rx, ry))
            else:
                pygame.draw.rect(view, (20, 20, 28), rect)
                pygame.draw.rect(view, border_col, rect, 2)
                name = e.name[:14]
                self.text(view, name, (rx + 8, ry + 6), border_col)
                self.text_small(view, f"HP {max(0,e.hp):>2}", (rx + 8, ry + 26), WHITE)
                # Status stacks at bottom
                stacks: List[Tuple[str, Tuple[int, int, int]]] = []
                order = ['bleed', 'poison', 'regen', 'reassemble', 'blind', 'vulnerable', 'weak', 'stun']
                for key in order:
                    try:
                        cnt = int(getattr(e, 'statuses', {}).get(key, 0))
                    except Exception:
                        cnt = 0
                    if cnt > 0:
                        cnt = min(9, cnt)
                        stacks.append((str(cnt), self.status_colors.get(key, WHITE)))
                if stacks:
                    sx = rx + 8
                    by = ry + h - self.font_small.get_height() - 4
                    for i, (txt, col) in enumerate(stacks):
                        surf = self.font_small.render(txt, True, col)
                        view.blit(surf, (sx, by))
                        sx += surf.get_width() + 6
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
        # Battle context (set by Game on start)
        self.floor_num: int = 1
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

        # Party defend state (indices of global party members defending until their next turn)
        self.party_defending: set = set()
        # Enemy AI state flags
        self.slime_pulsed: Dict[int, bool] = {}
        self.goblin_stolen: Dict[int, Optional[str]] = {}
        self.goblin_steal_used: Dict[int, bool] = {}
        self.escaped_enemies: set = set()
        self.enemy_spin: Dict[int, Dict[str, int]] = {}
        self.pending_bone_piles: Dict[int, Dict[str, Any]] = {}
        self.kobold_dart_fx: Dict[int, Dict[str, Any]] = {}
        # Slime Mind (elite) support
        self._slime_mind_ids = set(['slime_mind'])
        # The Censor state
        self.censor_silence_done: set = set()  # enemy indices that have performed SILENCE
        self.censor_enraged: set = set()       # enemy indices past 50% HP that now cast Spark
        self.is_censor_battle: bool = False
        self.censor_silence_fx: Optional[Dict[str, Any]] = None
        self.censor_music_fade_pending: bool = False
        self.censor_pulse_disabled: bool = False

    # ----- Slime Mind helpers -----
    def _spawn_slime_with_hp(self, around_index: int, hp: int):
        """Spawn a new Slime enemy with current HP set to the given value.
        Insert it adjacent to around_index and rebuild turn order.
        """
        try:
            base = self.monsters_by_id.get('slime', {})
            if not base:
                return
            new_e = Enemy.from_base(base, floor_num=self.floor_num)
            new_e.hp = max(1, int(hp))
            # Ensure display max >= current hp
            try:
                new_e.max_hp = max(int(getattr(new_e, 'max_hp', new_e.hp)), int(new_e.hp))
            except Exception:
                pass
            insert_at = min(max(0, int(around_index) + 1), len(self.enemies))
            self.enemies.insert(insert_at, new_e)
            self.log.add("A new Slime oozes into the fight!")
            self.build_turn_order()
        except Exception:
            pass

    def _schedule_bone_pile(self, idx: int, hp: int):
        if idx < 0:
            return
        self.pending_bone_piles[idx] = {'hp': max(1, int(hp))}

    def _process_pending_bone_piles(self):
        if not self.pending_bone_piles:
            return
        for idx, info in list(self.pending_bone_piles.items()):
            if not (0 <= idx < len(self.enemies)):
                self.pending_bone_piles.pop(idx, None)
                continue
            if idx in self.dying_enemies:
                continue
            if getattr(self.enemies[idx], 'hp', 0) > 0:
                self.pending_bone_piles.pop(idx, None)
                continue
            base = self.monsters_by_id.get('bone_pile', {})
            if not base:
                self.pending_bone_piles.pop(idx, None)
                continue
            pile = Enemy.from_base(base, floor_num=self.floor_num)
            new_hp = max(1, int(info.get('hp', pile.hp)))
            pile.hp = new_hp
            try:
                pile.max_hp = max(int(getattr(pile, 'max_hp', new_hp)), new_hp)
            except Exception:
                pile.max_hp = new_hp
            self.enemies[idx] = pile
            self.dying_enemies.pop(idx, None)
            self._status_set('enemy', idx, 'reassemble', 2)
            try:
                self.effects.trigger('enemy', idx, 360, 7, GREEN)
            except Exception:
                pass
            self.log.add("The shattered bones collapse into a pile!")
            self.build_turn_order()
            for pos, tok in enumerate(self.turn_order):
                if tok == ('enemy', idx):
                    self.turn_pos = pos
                    break
            self.pending_bone_piles.pop(idx, None)

    def _bone_pile_transform(self, idx: int):
        if not (0 <= idx < len(self.enemies)):
            return
        pile = self.enemies[idx]
        base = self.monsters_by_id.get('skeleton', {})
        if not base:
            return
        new_enemy = Enemy.from_base(base, floor_num=self.floor_num)
        new_hp = max(1, int(getattr(pile, 'hp', 1)))
        new_enemy.hp = new_hp
        try:
            new_enemy.max_hp = max(int(getattr(new_enemy, 'max_hp', new_hp)), new_hp)
        except Exception:
            new_enemy.max_hp = new_hp
        self.enemies[idx] = new_enemy
        try:
            self.effects.trigger('enemy', idx, 420, 7, WHITE)
        except Exception:
            pass
        self.log.add(f"{new_enemy.name} reforms from the bone pile!")
        self.build_turn_order()
        for pos, tok in enumerate(self.turn_order):
            if tok == ('enemy', idx):
                self.turn_pos = pos
                break

    def _on_enemy_defeated(self, idx: int):
        """Hook for enemy death to trigger Slime Mind regen on allied slime death."""
        try:
            if not (0 <= idx < len(self.enemies)):
                return
            died = self.enemies[idx]
            if getattr(died, 'id', '') == 'slime':
                for i, e in enumerate(self.enemies):
                    if getattr(e, 'hp', 0) > 0 and getattr(e, 'id', '') in self._slime_mind_ids:
                        self._status_set('enemy', i, 'regen', 2)
            elif getattr(died, 'id', '') == 'skeleton':
                hp_source = max(1, int(getattr(died, 'max_hp', getattr(died, 'hp', 1))))
                self._schedule_bone_pile(idx, max(1, hp_source // 2))
        except Exception:
            pass

    # ----- The Censor helpers -----
    def _censor_preferred_target(self) -> Tuple[Optional[int], Optional["Character"]]:
        """Return (gi, character) of the highest-current-MP active member."""
        best_key = None
        best_pair: Tuple[Optional[int], Optional["Character"]] = (None, None)
        for gi in self.party.active:
            if not (0 <= gi < len(self.party.members)):
                continue
            member = self.party.members[gi]
            if not (member.alive and member.hp > 0):
                continue
            cur_mp = int(getattr(member, 'mp', 0))
            max_mp = int(getattr(member, 'max_mp', 0))
            key = (cur_mp, max_mp, -gi)
            if best_key is None or key > best_key:
                best_key = key
                best_pair = (gi, member)
        if best_pair[0] is None:
            alive = self.party.alive_active_members()
            if alive:
                member = alive[0]
                try:
                    return self.party.members.index(member), member
                except ValueError:
                    return None, None
        return best_pair

    def _party_adjacent_active(self, gi: int) -> List[int]:
        order = [idx for idx in self.party.active if 0 <= idx < len(self.party.members)]
        if gi not in order:
            return []
        pos = order.index(gi)
        adj = []
        if pos - 1 >= 0:
            adj.append(order[pos - 1])
        if pos + 1 < len(order):
            adj.append(order[pos + 1])
        result = []
        for idx in adj:
            member = self.party.members[idx]
            if member.alive and member.hp > 0:
                result.append(idx)
        return result

    # ----- Status helpers -----
    def _status_get(self, side: str, ix: int, name: str) -> int:
        if side == 'party' and 0 <= ix < len(self.party.members):
            return int(self.party.members[ix].statuses.get(name, 0))
        if side == 'enemy' and 0 <= ix < len(self.enemies):
            return int(self.enemies[ix].statuses.get(name, 0))
        return 0

    def _status_add(self, side: str, ix: int, name: str, stacks: int):
        if stacks <= 0:
            return
        old = self._status_get(side, ix, name)
        new = min(9, old + int(stacks))
        if side == 'party' and 0 <= ix < len(self.party.members):
            self.party.members[ix].statuses[name] = new
        elif side == 'enemy' and 0 <= ix < len(self.enemies):
            self.enemies[ix].statuses[name] = new
        # Log on first application
        if old == 0 and new > 0:
            who = self.party.members[ix].name if side == 'party' else self.enemies[ix].name
            label = {'poison':'Poison','bleed':'Bleed','stun':'Stun','regen':'Regen','blind':'Blind','vulnerable':'Vulnerable','weak':'Weak','reassemble':'Reassemble'}.get(name, name.title())
            self.log.add(f"{who} gains {label} ({new}).")

    def _status_set(self, side: str, ix: int, name: str, stacks: int):
        prev = self._status_get(side, ix, name)
        if side == 'party' and 0 <= ix < len(self.party.members):
            if stacks > 0:
                self.party.members[ix].statuses[name] = min(9, int(stacks))
            else:
                self.party.members[ix].statuses.pop(name, None)
        elif side == 'enemy' and 0 <= ix < len(self.enemies):
            if stacks > 0:
                self.enemies[ix].statuses[name] = min(9, int(stacks))
            else:
                self.enemies[ix].statuses.pop(name, None)
        # Log on expiry
        if prev > 0 and stacks <= 0:
            who = self.party.members[ix].name if side == 'party' else self.enemies[ix].name
            label = {'poison':'Poison','bleed':'Bleed','stun':'Stun','regen':'Regen','blind':'Blind','vulnerable':'Vulnerable','weak':'Weak','reassemble':'Reassemble'}.get(name, name.title())
            self.log.add(f"{label} on {who} expires.")

    def _status_dec(self, side: str, ix: int, name: str, amt: int = 1):
        cur = self._status_get(side, ix, name)
        cur = max(0, cur - amt)
        self._status_set(side, ix, name, cur)

    def _start_of_turn_effects(self, side: str, ix: int) -> bool:
        """Apply start-of-turn effects. Return True if the turn should be skipped (stun)."""
        # Stun: skip turn and remove
        if self._status_get(side, ix, 'stun') > 0:
            self._status_set(side, ix, 'stun', 0)
            name = self.party.members[ix].name if side == 'party' else self.enemies[ix].name
            self.log.add(f"{name} is stunned and loses a turn!")
            return True
        # Poison: X damage then reduce stack by 1
        p = self._status_get(side, ix, 'poison')
        if p > 0:
            if side == 'party' and 0 <= ix < len(self.party.members):
                t = self.party.members[ix]
                t.hp = max(0, t.hp - p)
                self.add_floater('party', ix, str(p), 700, WHITE)
            elif side == 'enemy' and 0 <= ix < len(self.enemies):
                e = self.enemies[ix]
                e.hp = max(0, e.hp - p)
                self.add_floater('enemy', ix, str(p), 700, WHITE)
            self._status_dec(side, ix, 'poison', 1)
        # Bleed: 1 damage
        if self._status_get(side, ix, 'bleed') > 0:
            if side == 'party':
                t = self.party.members[ix]
                t.hp = max(0, t.hp - 1)
                self.add_floater('party', ix, '1', 700, WHITE)
            else:
                e = self.enemies[ix]
                e.hp = max(0, e.hp - 1)
                self.add_floater('enemy', ix, '1', 700, WHITE)
        # Regen: heal X and reduce
        r = self._status_get(side, ix, 'regen')
        if r > 0:
            if side == 'party':
                t = self.party.members[ix]
                before = t.hp
                t.hp = min(t.max_hp, t.hp + r)
                self.add_floater('party', ix, str(t.hp - before), 700, YELLOW)
            else:
                e = self.enemies[ix]
                # assume no max hp known; clamp to current hp + r
                e.hp = max(0, e.hp + r)
                self.add_floater('enemy', ix, str(r), 700, YELLOW)
            self._status_dec(side, ix, 'regen', 1)
        # Vulnerable/Weak decay each turn by 1
        if self._status_get(side, ix, 'vulnerable') > 0:
            self._status_dec(side, ix, 'vulnerable', 1)
        if self._status_get(side, ix, 'weak') > 0:
            self._status_dec(side, ix, 'weak', 1)
        return False

    def start_random(self, allowed: Optional[List[str]] = None, group: Tuple[int, int] = (1, 3), floor_num: int = 1):
        # Build enemy group from allowed ids and monster base data
        ids = [k for k in (allowed or list(self.monsters_by_id.keys())) if k in self.monsters_by_id]
        nmin, nmax = group
        count = random.randint(max(1, nmin), max(nmin, nmax))
        chosen = [random.choice(ids) for _ in range(count)] if ids else []
        fn = max(1, int(floor_num))
        self.enemies = [Enemy.from_base(self.monsters_by_id[cid], floor_num=fn) for cid in chosen]
        try:
            self.is_censor_battle = any(getattr(e, 'id', '') == 'the_censor' for e in self.enemies)
        except Exception:
            self.is_censor_battle = False
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
            # Start-of-turn status for party actor
            skip = self._start_of_turn_effects('party', self.current_actor_global_ix())
            if skip:
                self.advance_turn()
                return
            # Expire defend status for this actor at the start of their turn
            cur_ix = self.current_actor_global_ix()
            if cur_ix is not None and hasattr(self, 'party_defending') and cur_ix in self.party_defending:
                try:
                    self.party_defending.remove(cur_ix)
                except Exception:
                    pass
            self.ui_menu_options.append(('attack', 'Attack'))
            self.ui_menu_options.append(('defend', 'Defend'))
            # Build skills list based on class and level (matches begin_player_turn)
            skills: List[Tuple[str, str]] = []
            if a.cls == 'Fighter':
                if a.level >= 1: skills.append(('sunder', 'Sunder'))
                if a.level >= 3: skills.append(('rush', 'Rush'))
                if a.level >= 5: skills.append(('combo', 'Combo'))
            elif a.cls == 'Rogue':
                if a.level >= 1: skills.append(('backstab', 'Backstab'))
                if a.level >= 3: skills.append(('dust', 'Dust'))
                if a.level >= 5: skills.append(('flashbang', 'Flashbang'))
            elif a.cls == 'Priest':
                if a.level >= 1: skills.append(('regen', 'Regen'))
                if a.level >= 3: skills.append(('mend', 'Mend'))
                if a.level >= 5: skills.append(('heal', 'Heal'))
            elif a.cls == 'Mage':
                if a.level >= 1: skills.append(('spell', 'Spark'))
                if a.level >= 3: skills.append(('surge', 'Surge'))
                if a.level >= 5: skills.append(('storm', 'Storm'))
            # All skills require 1 MP: hide if no MP
            filt: List[Tuple[str, str]] = []
            for sid, label in skills:
                if a.mp <= 0:
                    continue
                filt.append((sid, label))
            self.skill_options = filt
            self.ui_menu_options.append(('skill', 'Skill'))
            self.ui_menu_options.append(('item', 'Items'))
            self.ui_menu_options.append(('run', 'Run'))
            self.skill_menu_index = 0
        else:
            # Enemy AI chooses an action based on monster id/state
            # Start-of-turn status for enemy
            if self._start_of_turn_effects('enemy', ix):
                # skip turn
                self.advance_turn()
                return
            act = self.enemy_choose_action(ix)
            if act is None:
                # fallback basic attack
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

    def enemy_choose_action(self, ix: int) -> Optional[Dict[str, Any]]:
        if ix < 0 or ix >= len(self.enemies):
            return None
        e = self.enemies[ix]
        # Skip if dead
        if e.hp <= 0:
            return None
        # Generic target list
        targets = self.party.alive_active_members()
        if not targets:
            self.finish_defeat(); return None
        t = random.choice(targets)
        gi = self.party.members.index(t)
        # Dispatch by id
        mid = getattr(e, 'id', e.name.lower())
        # Kobold
        if mid == 'kobold':
            alive_idxs = [j for j, en in enumerate(self.enemies) if getattr(en, 'hp', 0) > 0]
            alone = len(alive_idxs) == 1 and alive_idxs[0] == ix
            # If alone, 50% chance to attempt Pack Yip; otherwise follow normal routine
            if alone and random.random() < 0.5:
                success = random.random() < 0.5
                return {
                    'type': 'kobold_pack_yip',
                    'actor_side': 'enemy', 'actor_index': ix,
                    'label': f"{e.name} lets out a piercing pack yip!",
                    'fail_label': f"No packmates answer {e.name}'s call.",
                    'success_label': 'Another kobold scurries into the fight!',
                    'success': success,
                }
            r = random.random()
            if r < 0.7:
                hit = random.random() < 0.65
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} slashes at {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            else:
                return {'type': 'kobold_poison_dart', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'label': f"{e.name} fires a poison dart at {t.name}!"}
        if mid == 'bat':
            if random.random() < 0.5:
                hit = random.random() < 0.65
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} claws at {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            hit = random.random() < 0.6
            dmg = random.randint(max(1, e.atk_low - 1), max(e.atk_low, e.atk_high))
            return {'type': 'suck_blood', 'actor_side': 'enemy', 'actor_index': ix,
                    'target_side': 'party', 'target_index': gi,
                    'hit': hit, 'dmg': dmg,
                    'label': f"{e.name} latches onto {t.name} and drinks deeply!",
                    'miss_label': f"{t.name} shrugs off the bite!"}
        if mid == 'skeleton':
            r = random.random()
            if r < 0.7:
                hit = random.random() < 0.68
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} slashes at {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            hit = random.random() < 0.7
            dmg = random.randint(e.atk_low + 1, e.atk_high + 2)
            return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                    'target_side': 'party', 'target_index': gi,
                    'hit': hit, 'dmg': dmg, 'label': f"{e.name} smashes {t.name} with Bone Bash!",
                    'miss_label': f"{e.name}'s Bone Bash whiffs past {t.name}.",
                    'bone_bash': True}
        if mid == 'bone_pile':
            stacks = self._status_get('enemy', ix, 'reassemble')
            if stacks <= 0:
                return {'type': 'bone_pile_reform', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} erupts into a new form!"}
            remaining = max(0, stacks - 1)
            return {'type': 'bone_pile_wait', 'actor_side': 'enemy', 'actor_index': ix,
                    'label': f"{e.name} rattles and knits itself together... ({remaining} turns)",
                    'stacks': stacks}
        # Giant Rat
        if mid == 'giant_rat':
            r = random.random()
            if r < 0.6:
                # Attack
                hit = random.random() < 0.65
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            elif r < 0.9:
                # Chitter (emote)
                return {'type': 'emote', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} chitters nervously."}
            else:
                # Eat Cheese (heal 1)
                return {'type': 'e_heal', 'actor_side': 'enemy', 'actor_index': ix,
                        'amount': 1, 'label': f"{e.name} eats some cheese and feels better."}
        # Slime
        if mid == 'slime':
            if self.slime_pulsed.get(ix):
                # Must Splash now
                return {'type': 'splash', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} splashes out into the team!"}
            # Otherwise choose Attack or Pulse equally
            if random.random() < 0.5:
                hit = True  # slime attacks always hit for simplicity
                dmg = max(1, e.atk_low)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            else:
                # Pulse prepares Splash next turn
                return {'type': 'pulse', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} pulses eerily..."}
        # Slime Mind (elite)
        if mid == 'slime_mind':
            # If there are allied slimes, command them to splash.
            slimes = [j for j, en in enumerate(self.enemies) if en.hp > 0 and en.id == 'slime']
            if slimes:
                # Splash more aggressively when below half HP
                maxhp = max(1, int(getattr(e, 'max_hp', e.hp * 2)))
                times = 3 if e.hp < max(1, int(0.5 * maxhp)) else 1
                label = "Slime Mind orchestrates a torrent of splashes!" if times > 1 else "Slime Mind signals the slimes to splash!"
                return {'type': 'slime_mass_splash', 'actor_side': 'enemy', 'actor_index': ix,
                        'times': times, 'label': label}
            # Otherwise, emote or basic attack while waiting to split
            r = random.random()
            if r < 0.5:
                return {'type': 'emote', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} gurgles with malice."}
            else:
                hit = True
                dmg = max(1, e.atk_low)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} lashes out at {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
        # The Censor (elite)
        if mid == 'the_censor':
            pref_gi, pref_target = self._censor_preferred_target()
            if pref_gi is not None and pref_target is not None:
                gi = pref_gi
                t = pref_target
            # One-time opening: SILENCE all party members
            if ix not in self.censor_silence_done:
                return {'type': 'censor_silence', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': 'The Censor bellows: SILENCE!'}
            # If crossing below half HP, declare ENOUGH once, then switch to Spark
            try:
                maxhp = max(1, int(getattr(e, 'max_hp', e.hp * 2)))
                if e.hp < max(1, int(0.5 * maxhp)) and ix not in self.censor_enraged:
                    self.censor_enraged.add(ix)
                    return {'type': 'emote', 'actor_side': 'enemy', 'actor_index': ix, 'label': 'ENOUGH.'}
            except Exception:
                pass
            # If enraged: cast Spark every turn
            if ix in self.censor_enraged:
                dmg = max(1, random.randint(4, 8))
                return {'type': 'spell', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': True, 'dmg': dmg,
                        'label': f"{e.name} unleashes Mana Surge for {dmg}!",
                        'spell_id': 'mana_surge'}
            # Otherwise: choose regular attack or Mana Burn
            if random.random() < 0.5:
                target = self.party.members[gi]
                missing = max(0, int(getattr(target, 'max_mp', 0)) - int(getattr(target, 'mp', 0)))
                stacks = max(1, int(math.ceil(max(1, missing) / 3)))
                dmg = max(1, stacks * 3)
                splash_indices = self._party_adjacent_active(gi)
                splash_dmg = 0
                if dmg > 0:
                    splash_dmg = max(1, int(math.ceil(dmg * 0.3)))
                splash = [{'gi': idx, 'dmg': splash_dmg} for idx in splash_indices if splash_dmg > 0]
                return {'type': 'censor_mana_burn', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi, 'dmg': dmg,
                        'label': f"{e.name} drains your power!", 'missing_mp': missing,
                        'stacks': stacks, 'splash': splash}
            else:
                hit = random.random() < 0.65
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} strikes {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
        # Goblin
        if mid == 'goblin':
            # Adjusted probabilities if stolen
            has_stolen = bool(self.goblin_stolen.get(ix))
            r = random.random()
            if has_stolen:
                # 50% run attempt, else attack/trip
                if r < 0.5:
                    return {'type': 'run_enemy', 'actor_side': 'enemy', 'actor_index': ix,
                            'label': f"{e.name} tries to run away!"}
                # Else fallback to attack or trip
                r = random.random()
                if r < 0.7:
                    hit = random.random() < 0.65
                    dmg = random.randint(e.atk_low, e.atk_high)
                    return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                            'target_side': 'party', 'target_index': gi,
                            'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                            'miss_label': f"{e.name} misses {t.name}."}
                else:
                    return {'type': 'trip', 'actor_side': 'enemy', 'actor_index': ix,
                            'label': f"{e.name} loses its footing and trips!"}
            # Default: mostly attack, sometimes trip/steal, rarely run
            if r < 0.6:
                hit = random.random() < 0.65
                dmg = random.randint(e.atk_low, e.atk_high)
                return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                        'target_side': 'party', 'target_index': gi,
                        'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                        'miss_label': f"{e.name} misses {t.name}."}
            elif r < 0.8:
                # Trip
                return {'type': 'trip', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} loses its footing and trips!"}
            elif r < 0.95 and not self.goblin_steal_used.get(ix):
                return {'type': 'steal', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} eyes your belongings..."}
            else:
                return {'type': 'run_enemy', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} looks for an escape!"}
        # Goblin Chief
        if mid == 'goblin_chief':
            # If alone, summon two goblins (war cry)
            alive_idxs = [i for i, en in enumerate(self.enemies) if en.hp > 0]
            if len(alive_idxs) == 1 and alive_idxs[0] == ix:
                return {'type': 'summon', 'actor_side': 'enemy', 'actor_index': ix,
                        'label': f"{e.name} lets out a war cry!"}
            # If below 50% HP and any goblin present, devour one to heal
            try:
                if e.hp < max(1, int(0.5 * e.max_hp)):
                    goblins = [j for j, en in enumerate(self.enemies) if en.hp > 0 and en.id == 'goblin']
                    if goblins:
                        # choose the fattest goblin for max heal
                        target_j = max(goblins, key=lambda j: self.enemies[j].hp)
                        return {'type': 'goblin_devour', 'actor_side': 'enemy', 'actor_index': ix,
                                'target_enemy_index': target_j,
                                'label': f"{e.name} devours a goblin!"}
            except Exception:
                pass
            # If any goblins present, throw one at the party
            goblins = [j for j, en in enumerate(self.enemies) if en.hp > 0 and en.id == 'goblin']
            if goblins:
                gj = random.choice(goblins)
                # choose party target among alive actives
                targets = self.party.alive_active_members()
                if not targets:
                    self.finish_defeat(); return None
                t = random.choice(targets)
                gi = self.party.members.index(t)
                dmg = max(1, int(self.enemies[gj].hp))
                return {'type': 'goblin_throw', 'actor_side': 'enemy', 'actor_index': ix,
                        'g_index': gj, 'target_side': 'party', 'target_index': gi, 'dmg': dmg,
                        'label': f"{e.name} hurls a goblin at {t.name}!"}
            # Otherwise, attack
            hit = random.random() < 0.7
            dmg = random.randint(e.atk_low + 1, e.atk_high + 2)
            return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                    'target_side': 'party', 'target_index': gi,
                    'hit': hit, 'dmg': dmg, 'label': f"{e.name} strikes {t.name}",
                    'miss_label': f"{e.name} misses {t.name}."}
        # Fallback: attack
        hit = random.random() < 0.65
        dmg = random.randint(e.atk_low, e.atk_high)
        return {'type': 'attack', 'actor_side': 'enemy', 'actor_index': ix,
                'target_side': 'party', 'target_index': gi,
                'hit': hit, 'dmg': dmg, 'label': f"{e.name} attacks {t.name}",
                'miss_label': f"{e.name} misses {t.name}."}

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
        # Expire defend on turn start for this actor
        cur_ix = self.current_actor_global_ix()
        if cur_ix is not None and cur_ix in self.party_defending:
            try:
                self.party_defending.remove(cur_ix)
            except KeyError:
                pass
        self.ui_menu_options.append(('attack', 'Attack'))
        self.ui_menu_options.append(('defend', 'Defend'))
        self.ui_menu_options.append(('skill', 'Skill'))
        self.ui_menu_options.append(('item', 'Items'))
        self.ui_menu_options.append(('run', 'Run'))
        # Build skills list based on class and level
        skills: List[Tuple[str, str]] = []
        if a.cls == 'Fighter':
            if a.level >= 1: skills.append(('sunder', 'Sunder'))
            if a.level >= 3: skills.append(('rush', 'Rush'))
            if a.level >= 5: skills.append(('combo', 'Combo'))
        elif a.cls == 'Rogue':
            if a.level >= 1: skills.append(('backstab', 'Backstab'))
            if a.level >= 3: skills.append(('dust', 'Dust'))
            if a.level >= 5: skills.append(('flashbang', 'Flashbang'))
        elif a.cls == 'Priest':
            if a.level >= 1: skills.append(('regen', 'Regen'))
            if a.level >= 3: skills.append(('mend', 'Mend'))
            if a.level >= 5: skills.append(('heal', 'Heal'))
        elif a.cls == 'Mage':
            if a.level >= 1: skills.append(('spell', 'Spark'))
            if a.level >= 3: skills.append(('surge', 'Surge'))
            if a.level >= 5: skills.append(('storm', 'Storm'))
        # Could add more per-class skills here later
        # All skills require 1 MP: hide if no MP
        filt: List[Tuple[str, str]] = []
        for sid, label in skills:
            if a.mp <= 0:
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
        # Slightly longer pre-impact pause for certain enemy skills (e.g., Goblin Trip)
        if action.get('type') == 'trip':
            self.anim['dur'] = [240, 220, 260, 180]
        # Spells (e.g., Spark): extend pre stage to 1000ms to allow visible projectile travel
        if action.get('type') == 'spell':
            self.anim['dur'] = [240, 1000, 240, 180]
        # Slime 'splash' (spray) projectile travel time
        if action.get('type') == 'splash':
            self.anim['dur'] = [240, 1000, 240, 180]
        if action.get('type') == 'kobold_poison_dart':
            # Fast dart: short windup and quick travel
            self.anim['dur'] = [200, 220, 220, 160]
        if action.get('type') == 'censor_mana_burn':
            # Allow longer charge-up for the mana drain
            self.anim['dur'] = [260, 520, 260, 200]
        if action.get('bone_bash'):
            self.anim['dur'] = [260, 220, 260, 200]
        if action.get('type') in ('bone_pile_wait', 'bone_pile_reform'):
            self.anim['dur'] = [200, 160, 200, 140]
        if action.get('type') == 'suck_blood' and action.get('hit'):
            self.anim['dur'] = [220, 240, 220, 160]
        # Goblin chief custom timings
        if action.get('type') == 'goblin_devour':
            # Move to goblin, eat, return
            self.anim['dur'] = [200, 380, 240, 200]
        if action.get('type') == 'goblin_throw':
            # Hop to goblin during windup; throw projectile during pre (same as Spark)
            self.anim['dur'] = [240, 1000, 240, 180]
            try:
                if self.sfx: self.sfx.play('miss', 0.6)
            except Exception:
                pass
        # Skill-specific timing/feel
        if action.get('type') in ('sunder',):
            # normal hit cadence like attack
            self.anim['dur'] = [240, 140, 240, 160]
        if action.get('type') in ('rush',):
            # longer pre to travel up to target, snappy impact
            self.anim['dur'] = [200, 380, 240, 180]
        if action.get('type') in ('combo',):
            # quick approach, longer impact for double bump
            self.anim['dur'] = [180, 260, 300, 200]
        if action.get('type') in ('backstab',):
            # fade/teleport feel: longer pre, then impact
            self.anim['dur'] = [200, 420, 240, 200]
        self.state = 'anim'

    def add_floater(self, side: str, index: int, text: str, dur: int = 700, color=WHITE):
        self.floaters.append({'side': side, 'index': index, 'text': text, 'start': pygame.time.get_ticks(), 'dur': dur, 'color': color})

    def make_defend_action(self) -> Optional[Dict[str, Any]]:
        gi = self.current_actor_global_ix()
        if gi is None:
            return None
        return {
            'type': 'defend', 'actor_side': 'party', 'actor_index': gi,
        }

    def make_item_use_action(self, actor: Character, target_gi: int, iid: str) -> Optional[Dict[str, Any]]:
        it = self.items_by_id.get(iid)
        if not it or it.get('type') != 'consumable':
            return None
        if it.get('trait_select'):
            name = it.get('name', 'The tome')
            self.log.add(f"No time to study {name.lower()} in the middle of battle!")
            return None
        # Consumables can restore HP and/or MP. Prefer MP if present, else HP.
        if ('mp' in it) or ('mp_low' in it) or ('mp_high' in it):
            low = int(it.get('mp_low', it.get('mp', 0)))
            high = int(it.get('mp_high', it.get('mp', low)))
            if high < low:
                low, high = high, low
            mp = random.randint(low, high)
            gi = self.party.members.index(actor)
            return {
                'type': 'mp', 'actor_side': 'party', 'actor_index': gi,
                'target_side': 'party', 'target_index': target_gi,
                'mp': mp, 'actor_name': actor.name,
            }
        # Otherwise, HP heal
        low = int(it.get('heal_low', it.get('heal', 0)))
        high = int(it.get('heal_high', it.get('heal', low)))
        if high < low:
            low, high = high, low
        heal = random.randint(low, high)
        gi = self.party.members.index(actor)
        return {
            'type': 'heal', 'actor_side': 'party', 'actor_index': gi,
            'target_side': 'party', 'target_index': target_gi,
            'heal': heal, 'actor_name': actor.name,
        }

    def make_skill_action(self, actor: Character, target_i: Optional[int], sid: str) -> Optional[Dict[str, Any]]:
        gi = self.party.members.index(actor)
        # All skills require 1 MP
        if actor.mp <= 0:
            return None
        # Map skills into actions
        if sid in ('sunder','rush','combo','backstab','dust') and target_i is None:
            return None
        if sid in ('flashbang','surge','storm'):
            actor.mp -= 1
            return {'type': sid, 'actor_side': 'party', 'actor_index': gi}
        if sid in ('regen','mend'):
            actor.mp -= 1
            return {'type': sid, 'actor_side': 'party', 'actor_index': gi, 'target_side': 'party', 'target_index': target_i}
        if sid in ('sunder','rush','combo','backstab','dust'):
            actor.mp -= 1
            return {'type': sid, 'actor_side': 'party', 'actor_index': gi, 'target_side': 'enemy', 'target_index': target_i}
        return None

    def update(self):
        now = pygame.time.get_ticks()
        # prune floaters
        self.floaters = [f for f in self.floaters if now - f['start'] < f['dur']]
        # prune finished defeat animations
        self.dying_enemies = {i: d for i, d in self.dying_enemies.items() if now - d['start'] < d['dur']}
        self.downed_party = {i: d for i, d in self.downed_party.items() if now - d['start'] < d['dur']}
        self.kobold_dart_fx = {
            gi: fx for gi, fx in self.kobold_dart_fx.items()
            if now - fx.get('start', now) < fx.get('dur', 520)
        }
        self._process_pending_bone_piles()
        # Safety: if all enemies are defeated and no death animations remain, finalize victory
        if not self.battle_over and not self.dying_enemies and not self.enemy_alive():
            self.finish_victory()
            # After forcing victory, stop updating further this frame
            return
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
                # During pre-impact for Goblin Trip, play a MISS sfx once before the spin
                if stage == 1 and act.get('type') == 'trip' and not a.get('trip_pre_sfx'):
                    a['trip_pre_sfx'] = True
                    try:
                        if self.sfx:
                            self.sfx.play('miss', 0.6)
                    except Exception:
                        pass
        elif self.state == 'postpause' and now >= self.pause_until:
            if self.check_end_and_maybe_finish():
                return
            # Mixed initiative: advance to next token
            na = self.next_after_anim or {}
            # If player successfully ran, battle ends (handled earlier). Otherwise continue.
            self.advance_turn()

    def resolve_action_impact(self, act: Dict[str, Any]):
        if act['type'] in ('attack', 'spell'):
            # Blind: attacking with blind causes miss and consumes 1 stack (attack only)
            if act.get('type') == 'attack':
                a_side = act.get('actor_side'); a_ix = act.get('actor_index')
                if self._status_get(a_side, a_ix, 'blind') > 0:
                    act['hit'] = False
                    self._status_dec(a_side, a_ix, 'blind', 1)
            # The Censor: immune to targeted magic -> miss + gains regen
            if act.get('type') == 'spell' and act.get('target_side') == 'enemy':
                i = act.get('target_index', -1)
                if 0 <= i < len(self.enemies):
                    tgt = self.enemies[i]
                    if getattr(tgt, 'id', '') == 'the_censor':
                        act['hit'] = False
                        self._status_add('enemy', i, 'regen', 3)
                        self.log.add(f"{tgt.name} smiles and absorbs the magic.")
            if act.get('hit', False):
                dmg = max(1, int(act.get('dmg', 1)))
                # Weak reduces outgoing damage; Vulnerable increases incoming damage
                a_side = act.get('actor_side'); a_ix = act.get('actor_index')
                if self._status_get(a_side, a_ix, 'weak') > 0:
                    dmg = max(1, int(math.ceil(dmg * 0.5)))
                if act['target_side'] == 'enemy':
                    i = act['target_index']
                    if 0 <= i < len(self.enemies):
                        if self._status_get('enemy', i, 'vulnerable') > 0:
                            dmg = max(1, int(math.ceil(dmg * 1.5)))
                        self.enemies[i].hp -= dmg
                        self.effects.trigger('enemy', i, 300, 7)
                        try:
                            # enemy hurt sfx
                            self.sfx.play('enemy_hurt', 0.7)
                        except Exception:
                            pass
                        # damage floater (enemy)
                        self.add_floater('enemy', i, str(dmg), 800, WHITE)
                        # Slime Mind split-on-hit: on party Fight, if <2 slimes exist, spawn one with HP equal to damage dealt
                        try:
                            if act.get('type') == 'attack' and act.get('actor_side') == 'party':
                                tgt = self.enemies[i]
                                if getattr(tgt, 'id', '') == 'slime_mind':
                                    alive_slimes = [j for j, en in enumerate(self.enemies) if en.hp > 0 and en.id == 'slime']
                                    if len(alive_slimes) < 2:
                                        self._spawn_slime_with_hp(i, dmg)
                        except Exception:
                            pass
                        if self.enemies[i].hp <= 0:
                            self.enemies[i].hp = 0
                            # start defeat animation
                            self.dying_enemies[i] = {'start': pygame.time.get_ticks(), 'dur': 600}
                            self._on_enemy_defeated(i)
                else:
                    gi = act['target_index']
                    if 0 <= gi < len(self.party.members):
                        t = self.party.members[gi]
                        # If defending, reduce incoming damage by 50% (rounded up), minimum 1
                        if gi in self.party_defending:
                            dmg = max(1, int(math.ceil(dmg * 0.5)))
                        if self._status_get('party', gi, 'vulnerable') > 0:
                            dmg = max(1, int(math.ceil(dmg * 1.5)))
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
                        if act.get('bone_bash') and act.get('hit'):
                            self._status_add('party', gi, 'vulnerable', 1)
                            self.add_floater('party', gi, 'VULN', 700, YELLOW)
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
        elif act['type'] == 'suck_blood':
            ai = act.get('actor_index', -1)
            gi = act.get('target_index', -1)
            hit = bool(act.get('hit'))
            dmg = max(0, int(act.get('dmg', 0)))
            if hit and 0 <= gi < len(self.party.members):
                target = self.party.members[gi]
                if gi in self.party_defending:
                    dmg = max(1, int(math.ceil(dmg * 0.5)))
                if self._status_get('party', gi, 'vulnerable') > 0:
                    dmg = max(1, int(math.ceil(dmg * 1.5)))
                target.hp = max(0, target.hp - dmg)
                try:
                    self.sfx.play('party_hurt', 0.7)
                except Exception:
                    pass
                self.effects.trigger('party', gi, 420, 9, RED)
                self.add_floater('party', gi, str(dmg), 800, WHITE)
                if target.hp <= 0:
                    target.hp = 0
                    target.alive = False
                    self.downed_party[gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                if 0 <= ai < len(self.enemies):
                    leech = self.enemies[ai]
                    before = leech.hp
                    leech.hp = min(leech.max_hp, leech.hp + dmg)
                    healed = max(0, leech.hp - before)
                    if healed > 0:
                        self.add_floater('enemy', ai, f"+{healed}", 700, YELLOW)
                        try:
                            self.sfx.play('heal', 0.5)
                        except Exception:
                            pass
                self.log.add(act.get('label', f"{self.enemies[ai].name} drains {target.name}!"))
            else:
                self.log.add(act.get('miss_label', f"{self.enemies[ai].name} fails to draw any blood."))
        elif act['type'] == 'censor_silence':
            ai = act.get('actor_index', -1)
            self.censor_silence_done.add(ai)
            self.censor_pulse_disabled = True
            # Remove 3 MP from all party members (clamped to 0)
            if act.get('label'):
                self.log.add(act.get('label'))
            total_drained = 0
            for gi, m in enumerate(self.party.members):
                before = int(getattr(m, 'mp', 0))
                after = max(0, before - 3)
                drained = max(0, before - after)
                m.mp = after
                if drained <= 0:
                    continue
                total_drained += drained
                # MP loss floater
                self.add_floater('party', gi, f'-{drained}', 700, BLUE)
            if total_drained > 0 and 0 <= ai < len(self.enemies):
                enemy = self.enemies[ai]
                if getattr(enemy, 'hp', 0) > 0:
                    self._status_add('enemy', ai, 'regen', total_drained)
            if getattr(self, 'is_censor_battle', False):
                now = pygame.time.get_ticks()
                segs = (900, 400, 700)
                enemy_index = ai if 0 <= ai < len(self.enemies) else None
                self.censor_silence_fx = {
                    'start': now,
                    'enemy_index': enemy_index,
                    'segments': segs,
                    'surface': None,
                }
                self.censor_music_fade_pending = True
        elif act['type'] == 'bone_pile_wait':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                stacks_before = max(0, int(self._status_get('enemy', ix, 'reassemble')))
                label = act.get('label')
                if label:
                    self.log.add(label)
                else:
                    remaining = max(0, stacks_before - 1)
                    self.log.add(f"{self.enemies[ix].name} clatters together ({remaining} turns remain).")
                if stacks_before > 0:
                    self._status_dec('enemy', ix, 'reassemble', 1)
                try:
                    self.effects.trigger('enemy', ix, 320, 6, GREEN)
                except Exception:
                    pass
                if self._status_get('enemy', ix, 'reassemble') <= 0:
                    self._bone_pile_transform(ix)
        elif act['type'] == 'bone_pile_reform':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                if act.get('label'):
                    self.log.add(act['label'])
                self._bone_pile_transform(ix)
        elif act['type'] == 'censor_mana_burn':
            gi = act.get('target_index', -1)
            base_dmg = max(0, int(act.get('dmg', 0)))
            stacks = max(1, int(act.get('stacks', 1)))
            splash_hits: List[Tuple[int, int]] = []
            primary_name = None
            primary_dmg = None
            damage_sfx_played = False
            if 0 <= gi < len(self.party.members):
                t = self.party.members[gi]
                primary_name = t.name
                dmg = base_dmg
                if gi in self.party_defending:
                    dmg = max(1, int(math.ceil(dmg * 0.5))) if dmg > 0 else 0
                if self._status_get('party', gi, 'vulnerable') > 0:
                    dmg = max(1, int(math.ceil(dmg * 1.5))) if dmg > 0 else 0
                t.hp = max(0, t.hp - dmg)
                if dmg > 0 and not damage_sfx_played:
                    try:
                        self.sfx.play('party_hurt', 0.7)
                    except Exception:
                        pass
                    damage_sfx_played = True
                self.add_floater('party', gi, str(dmg), 800, WHITE)
                if t.hp <= 0:
                    t.hp = 0
                    t.alive = False
                    self.downed_party[gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                self.effects.trigger('party', gi, 300, 7)
                primary_dmg = dmg
            for entry in act.get('splash', []) or []:
                s_gi = int(entry.get('gi', -1))
                s_base = max(0, int(entry.get('dmg', 0)))
                if not (0 <= s_gi < len(self.party.members)):
                    continue
                target = self.party.members[s_gi]
                if not (target.alive and target.hp > 0):
                    continue
                dmg = s_base
                if s_gi in self.party_defending:
                    dmg = max(1, int(math.ceil(dmg * 0.5))) if dmg > 0 else 0
                if self._status_get('party', s_gi, 'vulnerable') > 0:
                    dmg = max(1, int(math.ceil(dmg * 1.5))) if dmg > 0 else 0
                target.hp = max(0, target.hp - dmg)
                if dmg > 0 and not damage_sfx_played:
                    try:
                        self.sfx.play('party_hurt', 0.7)
                    except Exception:
                        pass
                    damage_sfx_played = True
                self.add_floater('party', s_gi, str(dmg), 800, WHITE)
                if target.hp <= 0:
                    target.hp = 0
                    target.alive = False
                    self.downed_party[s_gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                self.effects.trigger('party', s_gi, 300, 7)
                splash_hits.append((s_gi, dmg))
            label = act.get('label')
            if primary_name:
                dmg_value = primary_dmg if primary_dmg is not None else base_dmg
                if label:
                    main_msg = f"{label} {primary_name} takes {dmg_value}."
                else:
                    main_msg = f"Mana Burn hits {primary_name} for {dmg_value}."
                if stacks > 1:
                    main_msg = f"{main_msg} ({stacks} stacks)"
                self.log.add(main_msg)
            elif label:
                self.log.add(label)
            for s_idx, s_dmg in splash_hits:
                s_name = self.party.members[s_idx].name
                self.log.add(f"Splash scorches {s_name} for {s_dmg}.")
        elif act['type'] == 'summon':
            ai = act.get('actor_index', -1)
            if 0 <= ai < len(self.enemies):
                # Only summon if still alone (avoid overfilling if interrupted)
                alive = [i for i, e in enumerate(self.enemies) if e.hp > 0]
                if len(alive) == 1 and alive[0] == ai:
                    label = act.get('label')
                    if label:
                        self.log.add(label)
                    base = self.monsters_by_id.get('goblin', {})
                    if base:
                        left = Enemy.from_base(base, floor_num=self.floor_num)
                        right = Enemy.from_base(base, floor_num=self.floor_num)
                        # Keep reference to the chief object to find it after insertion
                        chief_obj = self.enemies[ai]
                        # Insert left and right around chief
                        self.enemies.insert(ai, left)
                        # Find new index of chief (shifted by +1)
                        try:
                            ai = self.enemies.index(chief_obj)
                        except ValueError:
                            pass
                        self.enemies.insert(ai + 1, right)
                        self.log.add("Two goblins join the fray!")
                        # Rebuild turn order to include new goblins
                        self.build_turn_order()
                        # Keep current token on the chief (if present)
                        for pos, tok in enumerate(self.turn_order):
                            if tok == ('enemy', ai):
                                self.turn_pos = pos
                                break
        elif act['type'] == 'goblin_devour':
            ai = act.get('actor_index', -1)
            ti = act.get('target_enemy_index', -1)
            if 0 <= ai < len(self.enemies) and 0 <= ti < len(self.enemies):
                chief = self.enemies[ai]
                snack = self.enemies[ti]
                if chief.hp > 0 and snack.hp > 0 and snack.id == 'goblin':
                    heal = int(snack.hp)
                    chief.hp = min(getattr(chief, 'max_hp', chief.hp + heal), chief.hp + heal)
                    # kill goblin with a quick fade
                    snack.hp = 0
                    self.dying_enemies[ti] = {'start': pygame.time.get_ticks(), 'dur': 500}
                    self._on_enemy_defeated(ti)
                    self.add_floater('enemy', ai, f"+{heal}", 800, YELLOW)
                    try:
                        self.sfx.play('heal', 0.6)
                    except Exception:
                        pass
                    self.log.add(f"{chief.name} devours a goblin and recovers {heal} HP!")
                    # Rebuild order to remove the downed goblin from initiative
                    self.build_turn_order()
        elif act['type'] == 'goblin_throw':
            ai = act.get('actor_index', -1)
            gi = act.get('target_index', -1)
            gix = act.get('g_index', -1)
            dmg = max(1, int(act.get('dmg', 1)))
            # Kill goblin and damage party target
            if 0 <= gix < len(self.enemies):
                self.enemies[gix].hp = 0
                self.dying_enemies[gix] = {'start': pygame.time.get_ticks(), 'dur': 500}
                self._on_enemy_defeated(gix)
            if 0 <= gi < len(self.party.members):
                t = self.party.members[gi]
                # apply defend/vulnerable like attack
                if gi in self.party_defending:
                    dmg = max(1, int(math.ceil(dmg * 0.5)))
                if self._status_get('party', gi, 'vulnerable') > 0:
                    dmg = max(1, int(math.ceil(dmg * 1.5)))
                t.hp -= dmg
                try:
                    self.sfx.play('party_hurt', 0.7)
                except Exception:
                    pass
                self.add_floater('party', gi, str(dmg), 800, WHITE)
                if t.hp <= 0:
                    t.hp = 0
                    t.alive = False
                    self.downed_party[gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                self.effects.trigger('party', gi, 300, 7)
                chief = self.enemies[ai] if 0 <= ai < len(self.enemies) else None
                self.log.add(act.get('label', f"A goblin hits {t.name} for {dmg}."))
            # Rebuild order to remove the thrown goblin from initiative
            self.build_turn_order()
        elif act['type'] == 'kobold_poison_dart':
            gi = act.get('target_index', -1)
            label = act.get('label')
            if label:
                self.log.add(label)
            if 0 <= gi < len(self.party.members):
                now = pygame.time.get_ticks()
                self._status_add('party', gi, 'poison', 2)
                self.add_floater('party', gi, 'POISON', 700, GREEN)
                try:
                    self.effects.trigger('party', gi, 360, 8, GREEN)
                except Exception:
                    pass
                self.kobold_dart_fx[gi] = {'start': now, 'dur': 520}
                try:
                    if self.sfx:
                        self.sfx.play('party_hurt', 0.7)
                except Exception:
                    pass
        elif act['type'] == 'kobold_pack_yip':
            ix = act.get('actor_index', -1)
            label = act.get('label')
            if label:
                self.log.add(label)
            if not (0 <= ix < len(self.enemies)):
                return
            if act.get('success'):
                base = self.monsters_by_id.get('kobold', {})
                if base:
                    newcomer = Enemy.from_base(base, floor_num=self.floor_num)
                    self.enemies.append(newcomer)
                    success_label = act.get('success_label')
                    if success_label:
                        self.log.add(success_label)
                    new_ix = len(self.enemies) - 1
                    try:
                        self.effects.trigger('enemy', new_ix, 360, 7, GREEN)
                    except Exception:
                        pass
                    # Rebuild turn order so the newcomer can act and keep current kobold's position stable
                    caller_idx = ix
                    self.build_turn_order()
                    for pos, tok in enumerate(self.turn_order):
                        if tok == ('enemy', caller_idx):
                            self.turn_pos = pos
                            break
                else:
                    self.log.add('But nothing appears...')
            else:
                fail_label = act.get('fail_label')
                if fail_label:
                    self.log.add(fail_label)
        elif act['type'] == 'defend':
            gi = act.get('actor_index')
            if gi is not None:
                self.party_defending.add(gi)
                # brief visual cue
                self.add_floater('party', gi, 'DEFEND', 700, BLUE)
                self.log.add(f"{self.party.members[gi].name} braces for impact.")
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
        elif act['type'] == 'mp':
            gi = act['target_index']
            amt = max(0, int(act.get('mp', 0)))
            if 0 <= gi < len(self.party.members):
                t = self.party.members[gi]
                before = t.mp
                t.mp = min(t.max_mp, t.mp + amt)
                # MP floater (party)
                self.add_floater('party', gi, str(amt), 800, BLUE)
                try:
                    self.sfx.play('heal', 0.5)
                except Exception:
                    pass
                self.log.add(f"{act.get('actor_name','Adventurer')} restores {t.name}'s MP by {t.mp - before}.")
        elif act['type'] == 'emote':
            # Enemy emote/log only
            label = act.get('label')
            if label:
                self.log.add(label)
        elif act['type'] == 'e_heal':
            ix = act.get('actor_index', -1)
            amt = int(act.get('amount', 1))
            if 0 <= ix < len(self.enemies):
                e = self.enemies[ix]
                before = e.hp
                e.hp = max(0, e.hp + amt)
                # heal floater (enemy)
                self.add_floater('enemy', ix, str(amt), 800, YELLOW)
                try:
                    self.sfx.play('heal', 0.5)
                except Exception:
                    pass
                self.log.add(act.get('label', f"{e.name} heals."))
        elif act['type'] in ('sunder','rush','combo','backstab','dust','flashbang','surge','storm','regen','mend'):
            # Implement class skills effects
            a_ix = act.get('actor_index')
            if act['type'] == 'regen':
                gi = act.get('target_index')
                if 0 <= gi < len(self.party.members):
                    self._status_add('party', gi, 'regen', 3)
                    self.add_floater('party', gi, 'REGEN', 700, YELLOW)
                    self.log.add(f"{self.party.members[a_ix].name} casts Regen.")
            elif act['type'] == 'mend':
                gi = act.get('target_index')
                if 0 <= gi < len(self.party.members):
                    for name in ('poison','bleed','blind','vulnerable','weak','stun'):
                        self._status_set('party', gi, name, 0)
                    self.add_floater('party', gi, 'MEND', 700, YELLOW)
                    self.log.add(f"{self.party.members[a_ix].name} uses Mend.")
            elif act['type'] == 'dust':
                i = act.get('target_index')
                if 0 <= i < len(self.enemies):
                    self._status_add('enemy', i, 'blind', 2)
                    self.add_floater('enemy', i, 'BLIND', 700, WHITE)
                    self.log.add(f"{self.party.members[a_ix].name} throws dust!")
            elif act['type'] == 'flashbang':
                for i, e in enumerate(self.enemies):
                    if e.hp > 0:
                        self._status_add('enemy', i, 'stun', 1)
                        self.add_floater('enemy', i, 'STUN', 700, WHITE)
                self.log.add(f"{self.party.members[a_ix].name} uses Flashbang!")
            elif act['type'] in ('sunder','rush','combo','backstab'):
                i = act.get('target_index')
                if 0 <= i < len(self.enemies):
                    # base damage like attack
                    actor = self.party.members[a_ix]
                    base = max(1, random.randint(1, 6) + actor.atk_bonus)
                    hit = True if act['type'] == 'backstab' else (random.random() < 0.65)
                    if act['type'] == 'sunder':
                        base += 1
                    if act['type'] == 'rush':
                        base += 3
                        self._status_add('party', a_ix, 'vulnerable', 1)
                    times = 2 if act['type'] == 'combo' else 1
                    total_dmg = 0
                    for _ in range(times):
                        if hit and self.enemies[i].hp > 0:
                            dmg = base
                            # apply weak/vulnerable modifiers
                            if self._status_get('party', a_ix, 'weak') > 0:
                                dmg = max(1, int(math.ceil(dmg * 0.5)))
                            if self._status_get('enemy', i, 'vulnerable') > 0:
                                dmg = max(1, int(math.ceil(dmg * 1.5)))
                            self.enemies[i].hp -= dmg
                            total_dmg += dmg
                            # play hit effects
                            self.effects.trigger('enemy', i, 300, 7)
                            try:
                                self.sfx.play('enemy_hurt', 0.7)
                            except Exception:
                                pass
                            self.add_floater('enemy', i, str(dmg), 700, WHITE)
                            if self.enemies[i].hp <= 0:
                                self.enemies[i].hp = 0
                                self.dying_enemies[i] = {'start': pygame.time.get_ticks(), 'dur': 600}
                                self._on_enemy_defeated(i)
                        else:
                            self.add_floater('enemy', i, 'MISS', 700, WHITE)
                    if act['type'] == 'sunder' and hit:
                        self._status_add('enemy', i, 'vulnerable', 2)
                    self.log.add(f"{self.party.members[a_ix].name} uses {act['type'].title()} for {total_dmg}.")
            elif act['type'] == 'surge':
                # Spark-like damage to all
                total_dmg = 0
                for i, e in enumerate(self.enemies):
                    if e.hp <= 0: continue
                    dmg = max(1, random.randint(4, 8))
                    if self._status_get('enemy', i, 'vulnerable') > 0:
                        dmg = max(1, int(math.ceil(dmg * 1.5)))
                    e.hp -= dmg
                    total_dmg += dmg
                    self.add_floater('enemy', i, str(dmg), 700, WHITE)
                    if e.hp <= 0:
                        e.hp = 0; self.dying_enemies[i] = {'start': pygame.time.get_ticks(), 'dur': 600}
                        self._on_enemy_defeated(i)
                self.log.add(f"{self.party.members[a_ix].name} casts Surge for {total_dmg}.")
            elif act['type'] == 'storm':
                total_dmg = 0
                for _ in range(3):
                    alive = [i for i,e in enumerate(self.enemies) if e.hp > 0]
                    if not alive: break
                    i = random.choice(alive)
                    dmg = max(1, random.randint(4, 8))
                    if self._status_get('enemy', i, 'vulnerable') > 0:
                        dmg = max(1, int(math.ceil(dmg * 1.5)))
                    self.enemies[i].hp -= dmg
                    total_dmg += dmg
                    self.add_floater('enemy', i, str(dmg), 700, WHITE)
                    if self.enemies[i].hp <= 0:
                        self.enemies[i].hp = 0; self.dying_enemies[i] = {'start': pygame.time.get_ticks(), 'dur': 600}
                        self._on_enemy_defeated(i)
                self.log.add(f"{self.party.members[a_ix].name} calls Storm for {total_dmg}.")
        elif act['type'] == 'pulse':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                self.slime_pulsed[ix] = True
                # Start a shake effect by repeatedly retriggering in draw
                self.log.add(act.get('label', 'It pulses eerily...'))
        elif act['type'] == 'splash':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                e = self.enemies[ix]
                alive_gi = [i for i in self.party.active if 0 <= i < len(self.party.members) and self.party.members[i].alive and self.party.members[i].hp > 0]
                hits = 0
                for gi in alive_gi:
                    t = self.party.members[gi]
                    t.hp = max(0, t.hp - 1)
                    hits += 1
                    # green flash on party windows (longer, slightly stronger)
                    self.effects.trigger('party', gi, 420, 7, GREEN)
                    self.add_floater('party', gi, '1', 700, YELLOW)
                # recoil damage to slime
                e.hp = max(0, e.hp - hits)
                if e.hp <= 0:
                    self.dying_enemies[ix] = {'start': pygame.time.get_ticks(), 'dur': 600}
                    self._on_enemy_defeated(ix)
                self.log.add(act.get('label', f"{e.name} splashes!"))
                # play party hurt sfx once when splash lands
                if hits > 0:
                    try:
                        if self.sfx:
                            self.sfx.play('party_hurt', 0.7)
                    except Exception:
                        pass
                # Clear pulse flag
                if ix in self.slime_pulsed:
                    self.slime_pulsed.pop(ix, None)
        elif act['type'] == 'slime_mass_splash':
            # Slime Mind command: all allied slimes perform Splash, possibly multiple times
            times = max(1, int(act.get('times', 1)))
            if act.get('label'):
                self.log.add(act.get('label'))
            alive_gi = [i for i in self.party.active if 0 <= i < len(self.party.members) and self.party.members[i].alive and self.party.members[i].hp > 0]
            per_wave_hits = len(alive_gi)
            for _ in range(times):
                # Apply party damage once per wave
                for gi in alive_gi:
                    t = self.party.members[gi]
                    t.hp = max(0, t.hp - 1)
                    self.effects.trigger('party', gi, 420, 7, GREEN)
                    self.add_floater('party', gi, '1', 700, YELLOW)
                    if t.hp <= 0 and t.alive:
                        t.alive = False
                        self.downed_party[gi] = {'start': pygame.time.get_ticks(), 'dur': 600}
                # Recoil to each slime
                for j, en in enumerate(self.enemies):
                    if getattr(en, 'hp', 0) > 0 and getattr(en, 'id', '') == 'slime':
                        en.hp = max(0, en.hp - per_wave_hits)
                        if en.hp <= 0:
                            self.dying_enemies[j] = {'start': pygame.time.get_ticks(), 'dur': 600}
                            self._on_enemy_defeated(j)
                # play sfx once per wave
                if per_wave_hits > 0:
                    try:
                        if self.sfx:
                            self.sfx.play('party_hurt', 0.7)
                    except Exception:
                        pass
        elif act['type'] == 'trip':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                e = self.enemies[ix]
                dmg = random.randint(1, 3)
                e.hp = max(0, e.hp - dmg)
                self.add_floater('enemy', ix, str(dmg), 800, WHITE)
                # spin effect
                self.enemy_spin[ix] = {'start': pygame.time.get_ticks(), 'dur': 500}
                if e.hp <= 0:
                    self.dying_enemies[ix] = {'start': pygame.time.get_ticks(), 'dur': 600}
                    self._on_enemy_defeated(ix)
                self.log.add(act.get('label', f"{e.name} trips!"))
        elif act['type'] == 'steal':
            ix = act.get('actor_index', -1)
            self.goblin_steal_used[ix] = True
            if self.party.inventory and random.random() < 0.5:
                # steal a random item
                iid = random.choice(self.party.inventory)
                try:
                    self.party.inventory.remove(iid)
                except ValueError:
                    pass
                self.goblin_stolen[ix] = iid
                self.log.add(f"{self.enemies[ix].name} steals your {self.items_by_id.get(iid, {}).get('name', iid)}!")
            else:
                self.log.add(f"{self.enemies[ix].name} fails to steal anything.")
        elif act['type'] == 'run_enemy':
            ix = act.get('actor_index', -1)
            if 0 <= ix < len(self.enemies):
                if random.random() < 0.5:
                    # Mark as escaped and fade out
                    self.escaped_enemies.add(ix)
                    self.log.add(f"{self.enemies[ix].name} runs away!")
                    self.enemies[ix].hp = 0
                    # If that was the last remaining enemy, don't add a dying animation
                    # so the battle can end immediately on the post-pause check.
                    if self.enemy_alive():
                        self.dying_enemies[ix] = {'start': pygame.time.get_ticks(), 'dur': 500}
                else:
                    self.log.add(f"{self.enemies[ix].name} fails to run!")
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
        # Gold based on each enemy's range (allows per-monster zero gold)
        total_gold = 0
        try:
            for i, e in enumerate(self.enemies):
                if i in self.escaped_enemies:
                    continue
                total_gold += random.randint(int(e.gold_low), int(e.gold_high))
        except Exception:
            total_gold = max(0, total_gold)
        # Roll item drops per enemy
        loot_counts: Dict[str, int] = {}
        for i, e in enumerate(self.enemies):
            if i in self.escaped_enemies:
                continue
            for drop in getattr(e, 'drops', []) or []:
                try:
                    iid = drop.get('iid') or drop.get('id')
                    ch = float(drop.get('chance', 0))
                    if iid and ch > 0 and random.random() < ch:
                        loot_counts[iid] = loot_counts.get(iid, 0) + 1
                except Exception:
                    continue
        # Return stolen items from defeated goblins
        for i, iid in list(self.goblin_stolen.items()):
            if iid and (i not in self.escaped_enemies):
                # ensure the thief is actually defeated
                e = self.enemies[i] if 0 <= i < len(self.enemies) else None
                if e and e.hp <= 0:
                    loot_counts[iid] = loot_counts.get(iid, 0) + 1
        # Compute EXP awards per character based on floor vs character level.
        floor_num = max(1, int(getattr(self, 'floor_num', 1)))
        awards: Dict[int, int] = {}
        before: Dict[int, int] = {}
        after: Dict[int, int] = {}
        # Count non-escaped defeated enemies for weighting (each enemy awards the same formula)
        defeated_count = sum(1 for i, e in enumerate(self.enemies) if (i not in self.escaped_enemies) and getattr(e, 'hp', 0) <= 0)
        defeated_count = max(0, defeated_count)
        # For each alive active member, compute per-enemy award and sum
        for gi in self.party.active:
            if not (0 <= gi < len(self.party.members)):
                continue
            m = self.party.members[gi]
            if not (m.alive and m.hp > 0):
                continue
            before_exp = int(getattr(m, 'exp', 0))
            per_enemy = int(math.floor(10.0 * (floor_num / max(1.0, float(m.level)))))
            total_award = max(0, per_enemy * defeated_count)
            # Cap the character's stored EXP to 100 total
            new_exp = min(100, before_exp + total_award)
            gain = max(0, new_exp - before_exp)
            m.exp = new_exp
            awards[gi] = gain
            before[gi] = before_exp
            after[gi] = new_exp
        # Gold now goes to the party pool
        self.party.gold += total_gold
        # Award items to party inventory
        for iid, c in loot_counts.items():
            for _ in range(c):
                self.party.inventory.append(iid)
        # Do not log battle results here; show them only on the Victory screen
        # Record for victory screen
        self.victory_exp_awards = awards
        self.victory_exp_before = before
        self.victory_exp_after = after
        self.victory_gold = total_gold
        # Also record loot for Game to display
        self.victory_loot = loot_counts
        self.battle_over = True
        self.result = 'victory'
        self.kobold_dart_fx.clear()
        self.pending_bone_piles.clear()

    def finish_defeat(self):
        self.log.add("The party has fallen...")
        self.battle_over = True
        self.result = 'defeat'
        self.kobold_dart_fx.clear()
        self.pending_bone_piles.clear()

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
        pygame.display.set_caption("DEILOU")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.r = Renderer(self.screen)
        self.log = MessageLog()
        self.party = Party()
        # New games start with party-level gold and no items
        self.party.gold = 100
        self.party.inventory = []
        self.unlocked_waypoints: set = {0}
        self.waypoint_positions: Dict[int, Tuple[int, int]] = {0: (2, 2)}
        self.waypoint_options: List[int] = []
        self.waypoint_index: int = 0
        self.refresh_party_gear_bonuses()
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
        self.create_state = {"step": 0, "name": "", "class_ix": 0}
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
        self.items_scroll = 0

        # Equip UI state
        self.equip_phase = 'member'  # 'member' | 'slot' | 'choose'
        self.equip_member_ix = 0
        self.equip_slot_ix = 0  # 0 Weapon, 1 Armor, 2 Acc1, 3 Acc2
        self.equip_choose_ix = 0

        # Trait selection state
        self.trait_state: Dict[str, Any] = {}

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
        # Save/Load confirmations
        self.saveload_confirm_active: bool = False
        self.saveload_confirm_kind: Optional[str] = None  # 'save' | 'load'
        self.saveload_confirm_index: int = 1  # 0 Yes, 1 No (default No)
        # Title screen menu index
        self.title_index = 0

        # Temple UI state
        self.temple_phase = 'menu'  # 'menu' | 'revive'
        self.temple_menu_index = 0  # 0 Heal party, 1 Revive member
        self.temple_revive_index = 0

        # Threat mechanic replaces flat random encounters
        self.encounter_rate = 0.0  # legacy, unused
        self.threat: int = 0
        self.threat_max: int = 100
        self.threat_step_inc: int = 18  # per completed step
        self.threat_red_threshold: int = 75
        self.threat_full_steps: int = 0  # steps taken while meter is full
        self.threat_flash_active: bool = False
        self.threat_flash_t0: int = 0
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

        # Save confirmation overlay
        self.save_feedback_active: bool = False
        self.save_feedback_t0: int = 0

        # Load transition (fade-out, load, fade-in to town)
        self.load_feedback_active: bool = False
        self.load_feedback_stage: int = 0  # 0 fade-out, 1 fade-in
        self.load_feedback_t0: int = 0

        # Prologue scene state
        self.prologue_lines: List[str] = []
        self.prologue_line_height: int = 0
        self.prologue_total_height: int = 0
        self.prologue_scroll_start_y: float = float(HEIGHT)
        self.prologue_scroll_y: float = float(HEIGHT)
        self.prologue_scroll_speed: float = 26.0  # pixels per second
        self.prologue_scroll_t0: int = 0
        self.prologue_done: bool = False
        self.prologue_skip_prompt_visible: bool = False
        self.prologue_fade_active: bool = False
        self.prologue_fade_t0: int = 0
        self.prologue_fade_dur: int = 700
        self.prologue_top_margin: int = int(HEIGHT * 0.1)
        self.prologue_bottom_margin: int = int(HEIGHT * 0.1)
        self.prologue_area_height: int = HEIGHT - self.prologue_top_margin - self.prologue_bottom_margin
        self.prologue_font: pygame.font.Font = self.r._load_font(24)

        # Ending (The End) scene state
        self.ending_transition_t0: int = 0
        self.ending_transition_dur: int = 900
        self.ending_lines: List[str] = []
        self.ending_line_height: int = 0
        self.ending_total_height: int = 0
        self.ending_scroll_start_y: float = float(HEIGHT)
        self.ending_scroll_y: float = float(HEIGHT)
        self.ending_scroll_speed: float = 26.0
        self.ending_scroll_t0: int = 0
        self.ending_phase: str = 'idle'  # 'scroll' | 'fade_to_black' | 'title_fade_in' | 'title'
        self.ending_top_margin: int = int(HEIGHT * 0.1)
        self.ending_bottom_margin: int = int(HEIGHT * 0.1)
        self.ending_area_height: int = HEIGHT - self.ending_top_margin - self.ending_bottom_margin
        self.ending_font: pygame.font.Font = self.r._load_font(24)
        self.ending_title_font: pygame.font.Font = self.r._load_font(48)
        self.ending_fade_t0: int = 0
        self.ending_fade_dur: int = 1000
        self.ending_title_alpha: int = 0
        self.ending_title_t0: int = 0
        self.ending_title_dur: int = 1200
        self.ending_exit_active: bool = False
        self.ending_exit_t0: int = 0
        self.ending_exit_dur: int = 800

        # Persistent state: fog-of-war and level chests
        self.seen_by_level: Dict[int, set] = {}
        self.chests_state: Dict[int, List[Dict[str, Any]]] = {}
        # Persistent state: doors unlocked per level (list of (x,y))
        self.doors_unlocked: Dict[int, List[Tuple[int, int]]] = {}
        # Persistent elites per level (alive elites)
        self.elites_state: Dict[int, List[Dict[str, Any]]] = {}
        # Runtime elite movement animation
        self.elite_moves: Dict[Tuple[int,int], Dict[str, Any]] = {}
        self.elite_battle_ctx: Optional[Dict[str, Any]] = None

        # Treasure popup
        self.treasure_popup_active: bool = False
        self.treasure_item_name: str = ''
        self.treasure_t0: int = 0

        # Apply any saved per-level state to the initially loaded level
        try:
            self.apply_level_state(self.level_ix)
        except Exception:
            pass

        # Door unlock confirmation
        self.door_confirm_active: bool = False
        self.door_confirm_index: int = 1  # 0 Yes, 1 No
        self.door_confirm_pos: Optional[Tuple[int, int]] = None
        # Dialog state
        self.dialog_active: bool = False
        self.dialog_npc_id: Optional[str] = None
        self.dialog_phase: str = 'root'  # 'root' | 'talk'
        self.dialog_menu_index: int = 0
        self.dialog_text: List[str] = []
        self.dialog_type_t0: int = 0
        self.dialog_type_chars: int = 0
        self.dialog_line_ix: int = 0
        self.dialog_desc: str = ''
        self.dialog_typer_prev_chars: int = 0
        self.dialog_desc_typing: bool = False
        self.dialog_item_ix: int = 0

    def party_average_level(self) -> float:
        # Prefer alive active members; fall back to alive members; else all members; default 1.0
        vals: List[int] = [m.level for m in self.party.alive_active_members()]
        if not vals:
            vals = [m.level for m in self.party.alive_members()]
        if not vals:
            vals = [m.level for m in self.party.members]
        if not vals:
            return 1.0
        try:
            return sum(vals) / float(len(vals))
        except Exception:
            return 1.0


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
        # NPCs
        try:
            npcs = self.load_json(os.path.join('data', 'npcs.json'), [])
            self.npcs_by_id: Dict[str, Dict[str, Any]] = {n.get('id'): n for n in npcs if n.get('id')}
        except Exception:
            self.npcs_by_id = {}
        # Quests
        try:
            qs = self.load_json(os.path.join('data', 'quests.json'), [])
            self.quests_data: Dict[str, Dict[str, Any]] = {q.get('id'): q for q in qs if q.get('id')}
        except Exception:
            self.quests_data = {}
        self.quests_state: Dict[str, str] = {}

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
            elif new_mode == MODE_COMBAT_INTRO:
                # Start battle immediately (no crossfade) once at intro.
                if self.in_battle and getattr(self.in_battle, 'is_elite', False):
                    self.music.play_immediate('elite_battle')
                else:
                    self.music.play_immediate('battle')
            elif new_mode == MODE_BATTLE:
                # Keep current battle music; do not restart on entering MODE_BATTLE
                pass
            elif new_mode == MODE_VICTORY:
                # Fade the battle music to silence over 3 seconds
                self.music.fade_out_all(fade_ms=3000)
            elif new_mode == MODE_TITLE:
                # Keep title silent; gently fade out anything playing
                self.music.fade_out_all(fade_ms=700)
            elif new_mode == MODE_PROLOGUE:
                # Fade in the prologue ambience
                self.music.crossfade_to('prologue', fade_ms=1500)
            elif new_mode == MODE_ENDING_TRANSITION:
                self.music.fade_out_all(fade_ms=900)
            elif new_mode == MODE_ENDING:
                self.music.crossfade_to('ending', fade_ms=1500)
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

    # --------------- Save feedback overlay ---------------
    def start_save_feedback(self):
        # Begin a brief visual confirmation for saving
        self.save_feedback_active = True
        self.save_feedback_t0 = pygame.time.get_ticks()

    def start_load_feedback(self):
        # Begin fade-out, then load, then fade-in to town
        self.load_feedback_active = True
        self.load_feedback_stage = 0
        self.load_feedback_t0 = pygame.time.get_ticks()

    def draw_save_feedback(self):
        if not self.save_feedback_active:
            return
        now = pygame.time.get_ticks()
        dt = now - self.save_feedback_t0
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Quick white flash; no popup
        if dt < 120:
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, 220))
            view.blit(overlay, (0, 0))
        else:
            # End feedback quickly and return to town
            self.save_feedback_active = False
            self.mode = MODE_TOWN

    def draw_load_feedback(self):
        if not self.load_feedback_active:
            return
        now = pygame.time.get_ticks()
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        if self.load_feedback_stage == 0:
            # Fade to black over 400ms on current screen
            dt = now - self.load_feedback_t0
            dur = 400
            p = max(0.0, min(1.0, dt / dur))
            alpha = int(255 * p)
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            view.blit(overlay, (0, 0))
            if dt >= dur:
                # Perform the load once, then switch to town and fade back in
                try:
                    self.load()
                except Exception:
                    pass
                self.mode = MODE_TOWN
                self.load_feedback_stage = 1
                self.load_feedback_t0 = now
        else:
            # Fade back in from black over 500ms while drawing town
            dt = now - self.load_feedback_t0
            dur = 500
            p = max(0.0, min(1.0, dt / dur))
            alpha = int(255 * (1.0 - p))
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            view.blit(overlay, (0, 0))
            if dt >= dur:
                self.load_feedback_active = False

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
        # Serialize seen tiles per level and remaining chests per level
        seen_ser = {str(k): [[int(x), int(y)] for (x, y) in sorted(v)] for k, v in self.seen_by_level.items()}
        chests_ser = {str(k): list(v) for k, v in self.chests_state.items()}
        doors_ser = {str(k): [[int(x), int(y)] for (x, y) in v] for k, v in self.doors_unlocked.items()}
        elites_ser = {str(k): list(v) for k, v in self.elites_state.items()}
        data = {
            "party": self.party.to_dict(),
            "pos": self.pos,
            "facing": self.facing,
            "level": self.level_ix,
            "seen": seen_ser,
            "chests": chests_ser,
            "doors": doors_ser,
            "elites": elites_ser,
            "quests": {k: v for k, v in self.quests_state.items()},
            "waypoints": sorted(self.unlocked_waypoints),
            "waypoint_positions": {str(k): list(v) for k, v in self.waypoint_positions.items()},
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.log.add("Game saved.")
        # Trigger visual confirmation
        self.start_save_feedback()

    def load(self, path="save.json"):
        if not os.path.exists(path):
            self.log.add("No save file found.")
            return
        with open(path) as f:
            data = json.load(f)
        self.party = Party.from_dict(data.get("party", {}))
        self.refresh_party_gear_bonuses()
        waypoints = data.get("waypoints")
        if isinstance(waypoints, list):
            try:
                self.unlocked_waypoints = set(int(v) for v in waypoints)
            except Exception:
                self.unlocked_waypoints = {0}
        else:
            self.unlocked_waypoints = {0}
        if 0 not in self.unlocked_waypoints:
            self.unlocked_waypoints.add(0)
        waypoint_pos = data.get("waypoint_positions")
        if isinstance(waypoint_pos, dict):
            wmap = {}
            for k, v in waypoint_pos.items():
                try:
                    ix = int(k)
                    if isinstance(v, (list, tuple)) and len(v) == 2:
                        x, y = int(v[0]), int(v[1])
                        wmap[ix] = (x, y)
                except Exception:
                    continue
            if wmap:
                self.waypoint_positions = wmap
        if 0 not in self.waypoint_positions:
            self.waypoint_positions[0] = (2, 2)
        self.level_ix = int(data.get("level", 0))
        self.dun.ensure_level(self.level_ix)
        # Restore fog-of-war and chests state
        self.seen_by_level = {}
        try:
            seen = data.get("seen", {})
            if isinstance(seen, dict):
                for k, v in seen.items():
                    try:
                        ix = int(k)
                        st = set()
                        for pair in v:
                            x, y = int(pair[0]), int(pair[1])
                            st.add((x, y))
                        self.seen_by_level[ix] = st
                    except Exception:
                        continue
        except Exception:
            pass
        self.chests_state = {}
        try:
            ch = data.get("chests", {})
            if isinstance(ch, dict):
                for k, v in ch.items():
                    try:
                        ix = int(k)
                        if isinstance(v, list):
                            self.chests_state[ix] = list(v)
                    except Exception:
                        continue
        except Exception:
            pass
        # Doors
        self.doors_unlocked = {}
        try:
            dd = data.get("doors", {})
            if isinstance(dd, dict):
                for k, v in dd.items():
                    try:
                        ix = int(k)
                        lst: List[Tuple[int, int]] = []
                        for pair in v:
                            x, y = int(pair[0]), int(pair[1])
                            lst.append((x, y))
                        self.doors_unlocked[ix] = lst
                    except Exception:
                        continue
        except Exception:
            pass
        self.apply_level_state(self.level_ix)
        # Elites
        self.elites_state = {}
        try:
            ed = data.get("elites", {})
            if isinstance(ed, dict):
                for k, v in ed.items():
                    try:
                        ix = int(k)
                        if isinstance(v, list):
                            self.elites_state[ix] = list(v)
                    except Exception:
                        continue
        except Exception:
            pass
        self.pos = tuple(data.get("pos", (2, 2)))
        self.facing = int(data.get("facing", 1))
        # Quests
        try:
            qd = data.get("quests", {})
            if isinstance(qd, dict):
                self.quests_state = {str(k): str(v) for k, v in qd.items()}
        except Exception:
            self.quests_state = {}
        self.log.add("Game loaded.")
        # After loading, ensure town menu starts at the top choice
        self.menu_index = 0

    
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

        title = "DEILOU"
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
                    self.refresh_party_gear_bonuses()
                    self.party.gold = 100
                    self.party.inventory = []
                    self.start_prologue()
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

    def start_prologue(self):
        path_options = [os.path.join('data', 'prologue.txt'), 'data/prologue.txt']
        text = ""
        for path in path_options:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    break
            except Exception:
                continue
        if not text:
            text = "Your story starts here."
        raw_lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        lines = self._wrap_text_lines(raw_lines, self.prologue_font, WIDTH - 120)
        if not lines:
            lines = [""]
        self.prologue_lines = lines
        # Cache line metrics for scrolling
        base_line = self.prologue_font.get_linesize()
        self.prologue_line_height = base_line + 6
        self.prologue_total_height = max(len(lines), 1) * self.prologue_line_height
        self.prologue_area_height = HEIGHT - self.prologue_top_margin - self.prologue_bottom_margin
        area_bottom = self.prologue_top_margin + self.prologue_area_height
        self.prologue_scroll_start_y = area_bottom + 40
        self.prologue_scroll_y = self.prologue_scroll_start_y
        self.prologue_scroll_t0 = pygame.time.get_ticks()
        self.prologue_done = False
        self.prologue_skip_prompt_visible = False
        self.prologue_fade_active = False
        self.prologue_fade_t0 = 0
        # Ensure audio eases out during the prologue
        self.mode = MODE_PROLOGUE

    def _wrap_text_lines(self, lines: List[str], font: pygame.font.Font, max_width: int) -> List[str]:
        wrapped: List[str] = []
        for line in lines:
            if not line.strip():
                # Preserve blank lines as paragraph breaks
                wrapped.append('')
                continue
            words = line.split()
            current = ''
            for word in words:
                candidate = word if not current else f"{current} {word}"
                try:
                    width = font.size(candidate)[0]
                except Exception:
                    width = 0
                if width <= max_width:
                    current = candidate
                    continue
                if current:
                    wrapped.append(current)
                # Handle individual word longer than max width by splitting characters
                chunk = ''
                for ch in word:
                    test = chunk + ch
                    try:
                        test_width = font.size(test)[0]
                    except Exception:
                        test_width = 0
                    if test_width <= max_width:
                        chunk = test
                    else:
                        if chunk:
                            wrapped.append(chunk)
                        chunk = ch
                current = chunk
            if current:
                wrapped.append(current)
        return wrapped

    def update_prologue(self):
        now = pygame.time.get_ticks()
        if not self.prologue_fade_active:
            elapsed = (now - self.prologue_scroll_t0) / 1000.0
            self.prologue_scroll_y = self.prologue_scroll_start_y - elapsed * self.prologue_scroll_speed
            if not self.prologue_done:
                if self.prologue_scroll_y + self.prologue_total_height <= self.prologue_top_margin:
                    self.prologue_done = True
                    self.start_prologue_fade()
        else:
            if now - self.prologue_fade_t0 >= self.prologue_fade_dur:
                self.finish_prologue()

    def draw_prologue(self):
        screen = self.screen
        screen.fill((10, 10, 16))
        # Title in top margin
        title = "PROLOGUE"
        title_surf = self.r.font_big.render(title, True, YELLOW)
        title_x = WIDTH // 2 - title_surf.get_width() // 2
        title_y = self.prologue_top_margin // 2 - title_surf.get_height() // 2
        screen.blit(title_surf, (title_x, title_y))

        font = self.prologue_font
        line_h = self.prologue_line_height or (font.get_linesize() + 6)
        base_y = int(self.prologue_scroll_y)
        text_rect = pygame.Rect(0, self.prologue_top_margin, WIDTH, self.prologue_area_height)
        prev_clip = screen.get_clip()
        screen.set_clip(text_rect)
        try:
            for idx, line in enumerate(self.prologue_lines):
                y = base_y + idx * line_h
                # Skip off-screen rows for efficiency
                if y < text_rect.top - line_h or y > text_rect.bottom + line_h:
                    continue
                if line.strip():
                    surf = font.render(line, True, LIGHT).convert_alpha()
                    line_center = y + line_h / 2.0
                    top_start = self.prologue_top_margin
                    top_full = top_start + self.prologue_area_height * 0.25
                    bottom_full = top_start + self.prologue_area_height * 0.75
                    bottom_end = top_start + self.prologue_area_height
                    top_factor = 1.0
                    if line_center <= top_full:
                        if line_center <= top_start:
                            top_factor = 0.0
                        else:
                            span = max(1e-6, top_full - top_start)
                            top_factor = max(0.0, min(1.0, (line_center - top_start) / span))
                    bottom_factor = 1.0
                    if line_center >= bottom_full:
                        if line_center >= bottom_end:
                            bottom_factor = 0.0
                        else:
                            span = max(1e-6, bottom_end - bottom_full)
                            bottom_factor = max(0.0, min(1.0, 1.0 - (line_center - bottom_full) / span))
                    alpha = int(255 * top_factor * bottom_factor)
                    if alpha <= 0:
                        continue
                    surf.set_alpha(alpha)
                    x = WIDTH // 2 - surf.get_width() // 2
                    screen.blit(surf, (x, y))
                else:
                    continue
        finally:
            screen.set_clip(prev_clip)
        if self.prologue_skip_prompt_visible and not self.prologue_fade_active and not self.prologue_done:
            prompt = "Press Enter to Skip"
            surf = self.r.font_small.render(prompt, True, LIGHT)
            px = WIDTH - surf.get_width() - 40
            py = HEIGHT - self.prologue_bottom_margin + (self.prologue_bottom_margin - surf.get_height()) // 2
            screen.blit(surf, (px, py))
        if self.prologue_fade_active:
            now = pygame.time.get_ticks()
            elapsed = now - self.prologue_fade_t0
            p = max(0.0, min(1.0, elapsed / max(1, self.prologue_fade_dur)))
            alpha = int(255 * p)
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            screen.blit(overlay, (0, 0))

    def prologue_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.prologue_fade_active:
                    return
                if not self.prologue_skip_prompt_visible and not self.prologue_done:
                    self.prologue_skip_prompt_visible = True
                else:
                    self.start_prologue_fade()

    def start_prologue_fade(self):
        if self.prologue_fade_active:
            return
        self.prologue_fade_active = True
        self.prologue_fade_t0 = pygame.time.get_ticks()
        self.prologue_skip_prompt_visible = False
        self.prologue_done = True
        try:
            self.music.fade_out_all(self.prologue_fade_dur)
        except Exception:
            pass

    def finish_prologue(self):
        self.prologue_fade_active = False
        self.mode = MODE_TOWN
        self.menu_index = 0

    def start_end_transition(self):
        if self.mode in (MODE_ENDING_TRANSITION, MODE_ENDING):
            return
        self.ending_exit_active = False
        self.ending_phase = 'idle'
        self.ending_transition_t0 = pygame.time.get_ticks()
        self.mode = MODE_ENDING_TRANSITION
        try:
            self.music.fade_out_all(self.ending_transition_dur)
        except Exception:
            pass

    def update_end_transition(self):
        now = pygame.time.get_ticks()
        if now - self.ending_transition_t0 >= self.ending_transition_dur:
            self.start_ending_scene()

    def draw_end_transition(self):
        now = pygame.time.get_ticks()
        elapsed = now - self.ending_transition_t0
        p = max(0.0, min(1.0, elapsed / max(1, self.ending_transition_dur)))
        alpha = int(255 * p)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, alpha))
        self.screen.blit(overlay, (0, 0))

    def start_ending_scene(self):
        path_options = [os.path.join('data', 'ending.txt'), 'data/ending.txt']
        text = ""
        for path in path_options:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    break
            except Exception:
                continue
        if not text:
            text = "The story draws to a close."
        raw_lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        lines = self._wrap_text_lines(raw_lines, self.ending_font, WIDTH - 120)
        if not lines:
            lines = [""]
        self.ending_lines = lines
        base_line = self.ending_font.get_linesize()
        self.ending_line_height = base_line + 6
        self.ending_total_height = max(len(lines), 1) * self.ending_line_height
        self.ending_area_height = HEIGHT - self.ending_top_margin - self.ending_bottom_margin
        area_bottom = self.ending_top_margin + self.ending_area_height
        self.ending_scroll_start_y = area_bottom + 40
        self.ending_scroll_y = self.ending_scroll_start_y
        self.ending_scroll_t0 = pygame.time.get_ticks()
        self.ending_phase = 'scroll'
        self.ending_exit_active = False
        self.ending_title_alpha = 0
        self.ending_title_t0 = 0
        self.mode = MODE_ENDING

    def update_ending(self):
        now = pygame.time.get_ticks()
        if self.ending_phase == 'scroll':
            elapsed = (now - self.ending_scroll_t0) / 1000.0
            self.ending_scroll_y = self.ending_scroll_start_y - elapsed * self.ending_scroll_speed
            if self.ending_scroll_y + self.ending_total_height <= self.ending_top_margin:
                self.ending_phase = 'fade_to_black'
                self.ending_fade_t0 = now
        elif self.ending_phase == 'fade_to_black':
            if now - self.ending_fade_t0 >= self.ending_fade_dur:
                self.ending_phase = 'title_fade_in'
                self.ending_title_t0 = now
                self.ending_title_alpha = 0
        elif self.ending_phase == 'title_fade_in':
            dur = max(1, self.ending_title_dur)
            p = max(0.0, min(1.0, (now - self.ending_title_t0) / float(dur)))
            self.ending_title_alpha = int(255 * p)
            if p >= 1.0:
                self.ending_phase = 'title'
        if self.ending_exit_active:
            dur = max(1, self.ending_exit_dur)
            p = max(0.0, min(1.0, (now - self.ending_exit_t0) / float(dur)))
            if p >= 1.0:
                self.finish_ending()

    def draw_ending(self):
        phase = self.ending_phase
        screen = self.screen
        text_color = (30, 30, 30)
        label = ""
        if phase in ('scroll', 'fade_to_black'):
            screen.fill((248, 248, 248))
            label_surf = self.r.font_big.render(label, True, (120, 90, 200))
            label_x = WIDTH // 2 - label_surf.get_width() // 2
            label_y = self.ending_top_margin // 2 - label_surf.get_height() // 2
            screen.blit(label_surf, (label_x, label_y))
            font = self.ending_font
            line_h = self.ending_line_height or (font.get_linesize() + 6)
            base_y = int(self.ending_scroll_y)
            text_rect = pygame.Rect(0, self.ending_top_margin, WIDTH, self.ending_area_height)
            prev_clip = screen.get_clip()
            screen.set_clip(text_rect)
            try:
                for idx, line in enumerate(self.ending_lines):
                    y = base_y + idx * line_h
                    if y < text_rect.top - line_h or y > text_rect.bottom + line_h:
                        continue
                    if line.strip():
                        surf = font.render(line, True, text_color).convert_alpha()
                        line_center = y + line_h / 2.0
                        top_start = self.ending_top_margin
                        top_full = top_start + self.ending_area_height * 0.25
                        bottom_full = top_start + self.ending_area_height * 0.75
                        bottom_end = top_start + self.ending_area_height
                        top_factor = 1.0
                        if line_center <= top_full:
                            if line_center <= top_start:
                                top_factor = 0.0
                            else:
                                span = max(1e-6, top_full - top_start)
                                top_factor = max(0.0, min(1.0, (line_center - top_start) / span))
                        bottom_factor = 1.0
                        if line_center >= bottom_full:
                            if line_center >= bottom_end:
                                bottom_factor = 0.0
                            else:
                                span = max(1e-6, bottom_end - bottom_full)
                                bottom_factor = max(0.0, min(1.0, 1.0 - (line_center - bottom_full) / span))
                        alpha = int(255 * top_factor * bottom_factor)
                        if alpha <= 0:
                            continue
                        surf.set_alpha(alpha)
                        x = WIDTH // 2 - surf.get_width() // 2
                        screen.blit(surf, (x, y))
                    else:
                        continue
            finally:
                screen.set_clip(prev_clip)
        else:
            screen.fill((0, 0, 0))

        if phase == 'fade_to_black':
            now = pygame.time.get_ticks()
            p = max(0.0, min(1.0, (now - self.ending_fade_t0) / float(max(1, self.ending_fade_dur))))
            alpha = int(255 * p)
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            screen.blit(overlay, (0, 0))
        elif phase in ('title_fade_in', 'title'):
            font = self.ending_title_font
            text = "THE END"
            surf = font.render(text, True, (180, 120, 255)).convert_alpha()
            alpha = self.ending_title_alpha if phase == 'title_fade_in' else 255
            surf.set_alpha(alpha)
            x = WIDTH // 2 - surf.get_width() // 2
            y = HEIGHT // 2 - surf.get_height() // 2
            screen.blit(surf, (x, y))
            if phase == 'title':
                prompt = "Press Enter to return to Title"
                prompt_surf = self.r.font_small.render(prompt, True, (200, 180, 240))
                px = WIDTH // 2 - prompt_surf.get_width() // 2
                py = y + surf.get_height() + 40
                screen.blit(prompt_surf, (px, py))

        if self.ending_exit_active:
            now = pygame.time.get_ticks()
            p = max(0.0, min(1.0, (now - self.ending_exit_t0) / float(max(1, self.ending_exit_dur))))
            alpha = int(255 * p)
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha))
            screen.blit(overlay, (0, 0))

    def ending_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.ending_phase == 'title' and not self.ending_exit_active:
                    self.start_ending_exit()

    def start_ending_exit(self):
        if self.ending_exit_active:
            return
        self.ending_exit_active = True
        self.ending_exit_t0 = pygame.time.get_ticks()
        try:
            self.music.fade_out_all(self.ending_exit_dur)
        except Exception:
            pass

    def finish_ending(self):
        self.mode = MODE_TITLE
        self.title_index = 0
        self.ending_phase = 'idle'
        self.ending_exit_active = False
        self.menu_index = 0
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
            "Quests",
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
            # Keep town menu length in sync with draw_town options
            town_options_len = 12
            if event.key in (pygame.K_UP, pygame.K_k):
                self.menu_index = (self.menu_index - 1) % town_options_len
                self.sfx.play('ui_move', 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.menu_index = (self.menu_index + 1) % town_options_len
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
                options = sorted(self.unlocked_waypoints) if getattr(self, 'unlocked_waypoints', None) else [0]
                if len(options) <= 1 and (not options or options[0] == 0):
                    self.enter_labyrinth_at_floor(0)
                else:
                    self.start_waypoint_select(options)
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
            self.items_scroll = 0
            self.mode = MODE_ITEMS
        elif ix == 9:
            # Quests screen
            self.return_mode = MODE_TOWN
            self.mode = MODE_QUESTS
            self.quests_index = 0
            self.quests_popup = False
        elif ix == 10:
            self.mode = MODE_SAVELOAD
        elif ix == 11:
            # Exit to title screen
            self.title_index = 0
            self.mode = MODE_TITLE

    def start_waypoint_select(self, options: List[int]):
        opts = sorted(set(options) | {0})
        if len(opts) <= 1 and opts[0] == 0:
            self.enter_labyrinth_at_floor(0)
            return
        self.waypoint_options = opts
        self.waypoint_index = 0
        self.mode = MODE_WAYPOINT

    def draw_waypoint_select(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Choose Waypoint", (20, 16))
        floor_labels = []
        for floor in self.waypoint_options:
            label = f"Floor {floor + 1}"
            if floor == 0:
                label += " (Entrance)"
            floor_labels.append(label)
        options = floor_labels + ["Back"]
        self.r.draw_center_menu(options, self.waypoint_index)

    def waypoint_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        total = len(self.waypoint_options) + 1  # + Back
        if event.key in (pygame.K_UP, pygame.K_k):
            self.waypoint_index = (self.waypoint_index - 1) % total
            self.sfx.play('ui_move', 0.5)
        elif event.key in (pygame.K_DOWN, pygame.K_j):
            self.waypoint_index = (self.waypoint_index + 1) % total
            self.sfx.play('ui_move', 0.5)
        elif pygame.K_1 <= event.key <= pygame.K_9:
            idx = event.key - pygame.K_1
            if idx < total:
                self.waypoint_index = idx
                self._confirm_waypoint_selection()
                return
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.sfx.play('ui_select', 0.6)
            self._confirm_waypoint_selection()
        elif event.key == pygame.K_ESCAPE:
            self.mode = MODE_TOWN

    def enter_labyrinth_at_floor(self, floor_ix: int):
        try:
            floor_ix = int(floor_ix)
        except Exception:
            floor_ix = 0
        self.level_ix = floor_ix
        self.dun.ensure_level(self.level_ix)
        try:
            self.apply_level_state(self.level_ix)
        except Exception:
            pass
        lvl = self.dun.levels[self.level_ix]
        pos = self.waypoint_positions.get(self.level_ix)
        if not pos:
            pos = getattr(lvl, 'town_portal', None)
        if not pos or len(pos) != 2:
            pos = (2, 2)
        try:
            px, py = int(pos[0]), int(pos[1])
        except Exception:
            px, py = 2, 2
        self.pos = (px, py)
        self.facing = 1
        self.move_active = False
        self.seen_by_level.setdefault(self.level_ix, set())
        self.mode = MODE_MAZE
        if self.level_ix == 0:
            self.log.add("You descend into the Labyrinth...")
        else:
            self.log.add(f"You warp to Floor {self.level_ix + 1}.")

    def _confirm_waypoint_selection(self):
        if self.waypoint_index == len(self.waypoint_options):
            self.mode = MODE_TOWN
        else:
            floor = self.waypoint_options[self.waypoint_index]
            self.enter_labyrinth_at_floor(floor)

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
                            self.create_state = {"step": 0, "name": "", "class_ix": 0}
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

            # Status effects section
            right_y += 8
            self.r.text(view, "Status Effects:", (right_x, right_y)); right_y += 20
            # Build stacks in the same order and style as battle windows
            order = ['bleed', 'poison', 'regen', 'reassemble', 'blind', 'vulnerable', 'weak', 'stun']
            stacks = []
            for key in order:
                try:
                    cnt = int(getattr(m, 'statuses', {}).get(key, 0))
                except Exception:
                    cnt = 0
                if cnt > 0:
                    cnt = min(9, cnt)
                    color = self.r.status_colors.get(key, WHITE)
                    stacks.append((str(cnt), color))
            if stacks:
                sx = right_x
                by = right_y
                for txt, col in stacks:
                    surf = self.r.font_small.render(txt, True, col)
                    view.blit(surf, (sx, by))
                    sx += surf.get_width() + 10
                right_y = by + self.r.font_small.get_height() + 4
            else:
                self.r.text_small(view, "<None>", (right_x, right_y), LIGHT); right_y += 18

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
            # Class list with prices
            self.r.text(view, "Choose Class (Enter)", (32, y))
            class_opts = [f"{c} — {CLASS_COSTS.get(c,0)}g" for c in CLASSES]
            self.r.draw_center_menu(class_opts, s["class_ix"])
            # Show party gold and affordability
            chosen = CLASSES[s["class_ix"]]
            cost = CLASS_COSTS.get(chosen, 0)
            col = YELLOW if self.party.gold >= cost else RED
            self.r.text_small(view, f"Gold: {self.party.gold}g  Selected cost: {cost}g", (32, VIEW_H - 28), col)
        elif s["step"] == 2:
            temp = Character(s["name"], CLASSES[s["class_ix"]])
            # Apply fixed starting stats per class (no random rolls)
            self.apply_fixed_starting_stats(temp)
            self.r.text(view, f"Name: {temp.name}", (32, y))
            self.r.text(view, f"Class: {temp.cls}", (32, y + 20))
            y2 = y + 44
            stats = [("STR", temp.str_), ("IQ", temp.iq), ("PIE", temp.piety), ("VIT", temp.vit), ("AGI", temp.agi), ("LCK", temp.luck)]
            for i, (k, v) in enumerate(stats):
                self.r.text(view, f"{k}:{v:2d}", (32 + (i % 3) * 120, y2 + (i // 3) * 20))
            self.r.text(view, f"HP {temp.max_hp}  MP {temp.mp}", (32, y2 + 44))
            # Show recruit cost and party gold
            cost = CLASS_COSTS.get(temp.cls, 0)
            self.r.text(view, f"Cost: {cost}g    Party Gold: {self.party.gold}", (32, y2 + 66), YELLOW if self.party.gold >= cost else RED)
            # No reroll with fixed stats
            self.r.draw_center_menu(["Accept", "Cancel"], self.create_confirm_index)

    def create_input(self, event):
        s = self.create_state
        if event.type == pygame.KEYDOWN:
            if s["step"] == 0:
                if event.key == pygame.K_RETURN:
                    if s["name"].strip():
                        s["step"] = 1
                elif event.key == pygame.K_ESCAPE:
                    # Cancel character creation and return to Party menu
                    self.create_state = {"step": 0, "name": "", "class_ix": 0}
                    self.mode = MODE_PARTY
                    self.party_mode = 'menu'
                    self.party_actions_index = 0
                elif event.key == pygame.K_BACKSPACE:
                    s["name"] = s["name"][:-1]
                else:
                    ch = event.unicode
                    if ch.isprintable() and len(s["name"]) < 16:
                        s["name"] += ch
            elif s["step"] == 1:
                if event.key in (pygame.K_UP, pygame.K_k):
                    s["class_ix"] = (s["class_ix"] - 1) % len(CLASSES)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    s["class_ix"] = (s["class_ix"] + 1) % len(CLASSES)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s["step"] = 2
                elif event.key == pygame.K_ESCAPE:
                    s["step"] = 0
            elif s["step"] == 2:
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.create_confirm_index = (self.create_confirm_index - 1) % 2
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.create_confirm_index = (self.create_confirm_index + 1) % 2
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
                                newc = Character(s["name"], cls)
                                # Apply fixed starting stats per class (no random rolls)
                                self.apply_fixed_starting_stats(newc)
                                self.party.members.append(newc)
                                self.log.add(f"{newc.name} the {newc.cls} joins the roster (-{cost}g).")
                                # Start post-creation trait selection for this new member
                                ix = len(self.party.members) - 1
                                self.start_trait_selection(ix)
                                return
                        # If creation didn’t proceed, return to party menu
                        self.mode = MODE_PARTY
                        self.party_mode = 'menu'
                        self.party_actions_index = 0
                    else:  # Cancel
                        self.mode = MODE_PARTY
                        self.party_mode = 'menu'
                        self.party_actions_index = 0
                elif event.key == pygame.K_ESCAPE:
                    # back to class select
                    s["step"] = 1

    # --------------- Trait Selection ---------------
    def start_trait_selection(self, member_ix: int, return_mode: str = MODE_PARTY):
        now = pygame.time.get_ticks()
        trait_options = ['Quick', 'Strong', 'Insightful', 'Devout', 'Stalwart', 'Focused', 'Tough']
        self.trait_state = {
            'member_ix': member_ix,
            'traits': trait_options,
            'return_mode': return_mode,
            'left_idx': random.randint(0, len(trait_options) - 1),
            'right_idx': random.randint(0, len(trait_options) - 1),
            'left_steps': random.randint(22, 34),
            'right_steps': random.randint(26, 40),
            'left_delay': 40,
            'right_delay': 40,
            'left_next': now,
            'right_next': now,
            'phase': 'roll',  # 'roll' | 'choose' | 'merge_flash'
            'selected': 0,    # 0 left, 1 right
            'flash_t0': 0,
            'flash_dur': 500,
        }
        self.mode = MODE_TRAIT

    def trait_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        st = self.trait_state
        if not st:
            return
        if st.get('phase') == 'choose':
            if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_h):
                st['selected'] = 0
            elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l):
                st['selected'] = 1
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Apply chosen trait
                trait = st['traits'][st['left_idx'] if st['selected'] == 0 else st['right_idx']]
                self.apply_trait_bonus(st['member_ix'], trait, double=False)
                self.finish_trait_selection()
            elif event.key == pygame.K_ESCAPE:
                # Cancel falls back to left by default
                trait = st['traits'][st['left_idx']]
                self.apply_trait_bonus(st['member_ix'], trait, double=False)
                self.finish_trait_selection()

    def draw_trait(self):
        st = self.trait_state
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Choose Your Trait", (20, 16))
        if not st:
            return
        traits = st['traits']
        # Current labels
        left_label = traits[st['left_idx'] % len(traits)]
        right_label = traits[st['right_idx'] % len(traits)]
        # Positions
        cx = WIDTH // 2
        cy = VIEW_H // 2 + 20
        box_w, box_h = 240, 80
        pad = 40
        left_rect = pygame.Rect(cx - box_w - pad, cy - box_h // 2, box_w, box_h)
        right_rect = pygame.Rect(cx + pad, cy - box_h // 2, box_w, box_h)
        # Draw boxes
        pygame.draw.rect(view, (50, 50, 60), left_rect, border_radius=6)
        pygame.draw.rect(view, (50, 50, 60), right_rect, border_radius=6)
        pygame.draw.rect(view, YELLOW if st.get('selected', 0) == 0 and st.get('phase') == 'choose' else (120,120,140), left_rect, 2, border_radius=6)
        pygame.draw.rect(view, YELLOW if st.get('selected', 0) == 1 and st.get('phase') == 'choose' else (120,120,140), right_rect, 2, border_radius=6)
        # Labels centered
        self.r.text_big(view, left_label, (left_rect.x + 16, left_rect.y + 22), WHITE)
        self.r.text_big(view, right_label, (right_rect.x + 16, right_rect.y + 22), WHITE)
        # Instructions
        if st.get('phase') == 'roll':
            self.r.text_small(view, "Rolling...", (cx - 40, right_rect.bottom + 18), LIGHT)
        elif st.get('phase') == 'choose':
            self.r.text_small(view, "Left/Right to choose, Enter to confirm", (cx - 160, right_rect.bottom + 18), LIGHT)
        elif st.get('phase') == 'merge_flash':
            self.r.text_small(view, "Double Trait!", (cx - 60, right_rect.bottom + 18), YELLOW)
            # Draw white flash overlay (ease-out)
            now = pygame.time.get_ticks()
            t0 = st.get('flash_t0', now)
            dur = st.get('flash_dur', 500)
            p = max(0.0, min(1.0, (now - t0) / float(max(1, dur))))
            alpha = int(220 * (1.0 - p))
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha))
            view.blit(overlay, (0, 0))

    def update_trait(self):
        st = self.trait_state
        if not st:
            return
        now = pygame.time.get_ticks()
        # Rolling phase: step indices with increasing delays until steps reach zero
        if st['phase'] == 'roll':
            # left
            if st['left_steps'] > 0 and now >= st['left_next']:
                st['left_idx'] = (st['left_idx'] + 1) % len(st['traits'])
                st['left_steps'] -= 1
                st['left_delay'] = min(260, int(st['left_delay'] * 1.08 + 1))
                st['left_next'] = now + st['left_delay']
            # right
            if st['right_steps'] > 0 and now >= st['right_next']:
                st['right_idx'] = (st['right_idx'] + 1) % len(st['traits'])
                st['right_steps'] -= 1
                st['right_delay'] = min(260, int(st['right_delay'] * 1.08 + 1))
                st['right_next'] = now + st['right_delay']
            # If both stopped, move to choose/merge
            if st['left_steps'] <= 0 and st['right_steps'] <= 0:
                if st['traits'][st['left_idx']] == st['traits'][st['right_idx']]:
                    # Double! flash and auto-apply
                    st['phase'] = 'merge_flash'
                    st['flash_t0'] = now
                else:
                    st['phase'] = 'choose'
                    st['selected'] = 0
        elif st['phase'] == 'merge_flash':
            # After flash, apply and finish
            if now - st.get('flash_t0', now) >= st.get('flash_dur', 500):
                trait = st['traits'][st['left_idx']]
                self.apply_trait_bonus(st['member_ix'], trait, double=True)
                self.finish_trait_selection()

    def finish_trait_selection(self):
        # Return to caller-specified mode (party by default)
        st = self.trait_state or {}
        ret = st.get('return_mode', MODE_PARTY)
        self.mode = ret
        if ret == MODE_PARTY:
            self.party_mode = 'menu'
            self.party_actions_index = 0
        # clear state
        self.trait_state = {}

    def apply_trait_bonus(self, member_ix: int, trait: str, double: bool = False):
        if not (0 <= member_ix < len(self.party.members)):
            return
        m = self.party.members[member_ix]
        mult = 2 if double else 1
        if trait == 'Quick':
            m.agi += 1 * mult
            self.log.add(f"{m.name} gains Quick (+{1*mult} AGI).")
        elif trait == 'Strong':
            m.str_ += 1 * mult
            self.log.add(f"{m.name} gains Strong (+{1*mult} STR).")
        elif trait == 'Insightful':
            m.iq += 1 * mult
            self.log.add(f"{m.name} gains Insightful (+{1*mult} IQ).")
        elif trait == 'Devout':
            m.piety += 1 * mult
            self.log.add(f"{m.name} gains Devout (+{1*mult} PIE).")
        elif trait == 'Stalwart':
            m.vit += 1 * mult
            self.log.add(f"{m.name} gains Stalwart (+{1*mult} VIT).")
        elif trait == 'Focused':
            m.max_mp += 2 * mult
            m.mp += 2 * mult
            self.log.add(f"{m.name} gains Focused (+{2*mult} MP).")
        elif trait == 'Tough':
            m.max_hp += 2 * mult
            m.hp += 2 * mult
            self.log.add(f"{m.name} gains Tough (+{2*mult} HP).")

    def apply_fixed_starting_stats(self, c: "Character") -> None:
        """Set fixed starting stats and HP/MP for a new character based on class.

        VIT is derived from the class's starting HP and STR using
        a simple heuristic to keep values in the same small scale
        as the other fixed stats.
        """
        fixed = {
            'Fighter': {'hp': 10, 'mp': 1, 'str_': 5, 'iq': 1, 'piety': 3, 'agi': 3, 'luck': 5},
            'Rogue':   {'hp': 6,  'mp': 3, 'str_': 2, 'iq': 3, 'piety': 3, 'agi': 5, 'luck': 5},
            'Priest':  {'hp': 8,  'mp': 4, 'str_': 3, 'iq': 3, 'piety': 5, 'agi': 1, 'luck': 5},
            'Mage':    {'hp': 5,  'mp': 6, 'str_': 1, 'iq': 5, 'piety': 3, 'agi': 2, 'luck': 5},
        }
        s = fixed.get(c.cls)
        if not s:
            return
        # Core ability scores
        c.str_ = int(s['str_'])
        c.iq = int(s['iq'])
        c.piety = int(s['piety'])
        c.agi = int(s['agi'])
        c.luck = int(s['luck'])
        # HP/MP
        c.max_hp = int(s['hp']); c.hp = int(s['hp'])
        c.max_mp = int(s['mp']); c.mp = int(s['mp'])
        # Derive VIT from HP and STR (bounded 1..6 to match small fixed stat scale)
        c.vit = self.compute_default_vit(c.cls, c.max_hp, c.str_)

    def compute_default_vit(self, cls: str, hp: int, str_: int) -> int:
        """Compute a default VIT from starting HP and STR.

        Heuristic: ceil(hp/2) + floor(STR/3), clamped to 1..6.
        This keeps VIT in line with the small fixed stat values while
        reflecting both durability (HP) and physical toughness (STR).
        """
        try:
            base = int(math.ceil(hp / 2.0))
            adj = int(str_ // 3)
            vit = base + adj
            return max(1, min(6, vit))
        except Exception:
            return 3

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
                        # Every 2 levels starting at 3 (3,5,7,...) grant a bonus trait
                        if m.level >= 3 and (m.level % 2 == 1):
                            self.start_trait_selection(self.training_index, return_mode=MODE_TRAINING)
                            return
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
        # Confirmation popup overlay
        if getattr(self, 'saveload_confirm_active', False):
            s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            s.fill((0, 0, 0, 160))
            view.blit(s, (0, 0))
            title = "Save game?" if self.saveload_confirm_kind == 'save' else "Load game?"
            self.r.text_big(view, title, (WIDTH//2 - 120, 100), YELLOW)
            self.r.draw_center_menu(["Yes", "No"], self.saveload_confirm_index)

    def saveload_input(self, event):
        if event.type == pygame.KEYDOWN:
            # Ignore input while save/load transition overlays are active
            if getattr(self, 'save_feedback_active', False) or getattr(self, 'load_feedback_active', False):
                return
            # Handle confirmation mode
            if getattr(self, 'saveload_confirm_active', False):
                if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                    self.saveload_confirm_index = 1 - self.saveload_confirm_index
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.saveload_confirm_index == 0:  # Yes
                        kind = self.saveload_confirm_kind
                        self.saveload_confirm_active = False
                        self.saveload_confirm_kind = None
                        self.saveload_confirm_index = 1
                        if kind == 'save':
                            self.save()
                        elif kind == 'load':
                            # Only begin transition if a save file exists
                            path = "save.json"
                            if os.path.exists(path):
                                # Start fade-out/in transition and perform load mid-way
                                self.start_load_feedback()
                            else:
                                self.log.add("No save file found.")
                    else:  # No
                        self.saveload_confirm_active = False
                        self.saveload_confirm_kind = None
                        self.saveload_confirm_index = 1
                elif event.key == pygame.K_ESCAPE:
                    self.saveload_confirm_active = False
                    self.saveload_confirm_kind = None
                    self.saveload_confirm_index = 1
                return
            if event.key in (pygame.K_UP, pygame.K_k):
                self.saveload_index = (self.saveload_index - 1) % 3
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.saveload_index = (self.saveload_index + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.saveload_index == 0:
                    # ask to confirm save
                    self.saveload_confirm_active = True
                    self.saveload_confirm_kind = 'save'
                    self.saveload_confirm_index = 1
                elif self.saveload_index == 1:
                    # ask to confirm load
                    self.saveload_confirm_active = True
                    self.saveload_confirm_kind = 'load'
                    self.saveload_confirm_index = 1
                else:
                    self.mode = MODE_TOWN
            elif event.key == pygame.K_ESCAPE:
                self.mode = MODE_TOWN

    # --------------- Maze Helpers ---------------
    def grid(self) -> List[List[int]]:
        return self.dun.levels[self.level_ix].grid

    def in_bounds(self, x, y):
        grid = self.grid()
        if not grid:
            return False
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        return 0 <= y < height and 0 <= x < width

    def is_open(self, x, y):
        g = self.grid()
        return self.in_bounds(x, y) and g[y][x] not in (T_WALL, T_LOCKED)

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
            # Try door unlock if locked door ahead
            try:
                t = self.grid()[ny][nx]
            except Exception:
                t = T_WALL
            if t == T_LOCKED:
                if self.party_has_rogue():
                    # Pick the lock automatically
                    self.grid()[ny][nx] = T_EMPTY
                    # record unlocked door for persistence
                    try:
                        lst = self.doors_unlocked.setdefault(self.level_ix, [])
                        if (nx, ny) not in lst:
                            lst.append((nx, ny))
                    except Exception:
                        pass
                    self.log.add("You pick the lock.")
                    # then move forward
                    if not self.move_active:
                        self.move_active = True
                        self.move_from = self.pos
                        self.move_to = (nx, ny)
                        self.move_t0 = pygame.time.get_ticks()
                        self.move_step_sfx_count = 0
                else:
                    # If the party has a Key, offer to use it
                    if 'key' in self.party.inventory:
                        self.door_confirm_active = True
                        self.door_confirm_index = 1  # default No
                        self.door_confirm_pos = (nx, ny)
                    else:
                        self.log.add("The door is locked.")
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
            self.unlock_waypoint(self.level_ix)
            self.mode = MODE_TOWN
            self.log.add("You return to town.")
        elif t == T_STAIRS_D:
            self.go_down_stairs()
        elif t == T_STAIRS_U:
            self.go_up_stairs()
        elif t == T_END:
            self.start_end_transition()

    def _move_elites_after_player(self):
        lvl = self.dun.levels[self.level_ix]
        elites = getattr(lvl, 'elites', []) or []
        if not elites:
            return
        # If player is standing on an elite, trigger battle immediately and do not move elites this step
        try:
            for i, e in enumerate(elites):
                if (int(e.get('x', -1)), int(e.get('y', -1))) == tuple(self.pos):
                    # Cancel any ongoing elite animations for this level to avoid post-collision motion
                    try:
                        for key in list(self.elite_moves.keys()):
                            if isinstance(key, tuple) and key[0] == self.level_ix:
                                self.elite_moves.pop(key, None)
                    except Exception:
                        pass
                    self._start_elite_battle(self.level_ix, i, e)
                    return
        except Exception:
            pass
        now = pygame.time.get_ticks()
        new_positions = []
        for i, e in enumerate(elites):
            ex, ey = int(e.get('x', -1)), int(e.get('y', -1))
            pat = str(e.get('pattern', 'up_down'))
            # Direction state per elite stored in dict
            dkey = '_dir'
            if dkey not in e:
                e[dkey] = -1 if pat == 'up_down' else -1  # up/left initially
            dx = dy = 0
            if pat == 'up_down':
                dy = e[dkey]
            else:
                dx = e[dkey]
            nx, ny = ex + dx, ey + dy
            # If blocked by wall/locked, reverse and recompute
            def blocked(xx, yy):
                if not self.in_bounds(xx, yy):
                    return True
                g = self.grid()
                return g[yy][xx] in (T_WALL, T_LOCKED)
            if blocked(nx, ny):
                # Bounce in place: reverse direction for next step, but do not change tile now.
                e[dkey] = -e[dkey]
                # Start a short in-place bounce animation along attempted direction
                self.elite_moves[(self.level_ix, i)] = {
                    'bounce': True,
                    'bdx': float(dx), 'bdy': float(dy),
                    't0': now, 'dur': int(self.move_dur * 0.6)
                }
                nx, ny = ex, ey
            else:
                # Start move anim to the next tile
                self.elite_moves[(self.level_ix, i)] = {'from': (ex, ey), 'to': (nx, ny), 't0': now, 'dur': self.move_dur}
            # Apply position
            e['x'], e['y'] = nx, ny
            new_positions.append((nx, ny))
        # Collision: if any elite now on player, start elite battle
        for i, e in enumerate(elites):
            if (int(e.get('x', -1)), int(e.get('y', -1))) == tuple(self.pos):
                self._start_elite_battle(self.level_ix, i, e)
                break

    def _start_elite_battle(self, lvl_ix: int, elite_ix: int, elite: Dict[str, Any]):
        # Record context for post-battle handling
        self.elite_battle_ctx = {'level': lvl_ix, 'index': elite_ix, 'pos': (int(elite.get('x',0)), int(elite.get('y',0))), 'id': str(elite.get('id',''))}
        # Kick battle with single elite monster
        self.in_battle = Battle(self.party, self.log, self.effects, self.items_by_id, self.monsters_by_id, self.skills_config, self.sfx)
        try:
            setattr(self.in_battle, 'is_elite', True)
        except Exception:
            pass
        mid = str(elite.get('id'))
        floor_num = int(self.level_ix) + 1
        mons = [Enemy.from_base(self.monsters_by_id.get(mid, {}), floor_num=floor_num)]
        self.in_battle.enemies = mons
        try:
            self.in_battle.is_censor_battle = (mid == 'the_censor')
        except Exception:
            pass
        self.in_battle.build_turn_order(); self.in_battle.turn_pos = 0
        # Music is handled in on_mode_changed when switching to COMBAT_INTRO
        # Transition
        self.mode = MODE_COMBAT_INTRO
        self.combat_intro_active = True
        self.combat_intro_stage = 0
        self.combat_intro_t0 = pygame.time.get_ticks()
        self.combat_intro_done_triggered = False

    def go_down_stairs(self):
        cur = self.dun.levels[self.level_ix]
        down_pos = cur.stairs_down or self.pos
        self.level_ix += 1
        self.dun.ensure_level(self.level_ix, arrival_pos=down_pos)
        self.apply_level_state(self.level_ix)
        nxt = self.dun.levels[self.level_ix]
        target = nxt.stairs_up or down_pos
        self.pos = target
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
        self.apply_level_state(self.level_ix)
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
        floor_num = int(self.level_ix) + 1
        self.in_battle.floor_num = floor_num
        self.in_battle.start_random(allowed=allowed, group=group, floor_num=floor_num)
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
        # Compute FOV-visible tiles and update fog-of-war memory
        visible_tiles = self.compute_visible_tiles(radius=4)
        seen = self.seen_by_level.setdefault(self.level_ix, set())
        for t in visible_tiles:
            seen.add(t)
        # Draw with fog-of-war overlay (pass both visible and seen)
        lvl = self.dun.levels[self.level_ix]
        # Prepare elite draw list with simple per-move offsets
        elites = []
        try:
            for i, e in enumerate(getattr(lvl, 'elites', []) or []):
                ex, ey = int(e.get('x', -1)), int(e.get('y', -1))
                mv = self.elite_moves.get((self.level_ix, i))
                base_x, base_y = ex, ey
                fx = fy = 0.0
                if mv:
                    t = max(0, pygame.time.get_ticks() - mv.get('t0', 0))
                    dur = int(mv.get('dur', self.move_dur))
                    p = min(1.0, t / float(max(1, dur)))
                    if mv.get('bounce'):
                        # In-place bounce: sine easing out/back along attempted direction
                        amp = 0.25
                        s = math.sin(math.pi * p)
                        bdx = float(mv.get('bdx', 0.0)); bdy = float(mv.get('bdy', 0.0))
                        fx = bdx * amp * s
                        fy = bdy * amp * s
                    else:
                        # Move from the prior tile toward the destination proportionally
                        frm = mv.get('from', (ex, ey)); to = mv.get('to', (ex, ey))
                        base_x, base_y = int(frm[0]), int(frm[1])
                        fx = (float(to[0]) - float(frm[0])) * p
                        fy = (float(to[1]) - float(frm[1])) * p
                elites.append({'x': base_x, 'y': base_y, 'fx': fx, 'fy': fy})
        except Exception:
            elites = []
        self.r.draw_topdown(self.grid(), self.pos, self.facing, self.level_ix, shift_tiles, bob_px, frac,
                            visible_tiles=visible_tiles, seen_tiles=seen, apply_fov=False,
                            chests=getattr(lvl, 'chests', []), npcs=getattr(lvl, 'npcs', []), elites=elites)
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Removed on-screen controls display for a cleaner labyrinth view
        # Draw threat flash (when meter is full) and indicator (top-right)
        try:
            self.draw_threat_flash()
            self.draw_threat_indicator()
            self.draw_floor_indicator()
            self.draw_treasure_popup()
            self.draw_door_confirm()
        except Exception:
            pass
        # During combat intro flashes, overlay on maze
        if self.mode == MODE_COMBAT_INTRO and self.combat_intro_active:
            now = pygame.time.get_ticks()
            t = now - self.combat_intro_t0
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            if self.combat_intro_stage in (0, 2):
                alpha = 220 if (self.combat_intro_stage == 0 and t < 180) or (self.combat_intro_stage == 2 and t < 180) else 0
                overlay.fill((255, 255, 255, alpha))
            view.blit(overlay, (0, 0))

    def compute_visible_tiles(self, radius: int = 4, spread_deg: float = 80.0) -> set:
        # Compute LOS-visible tiles around player using renderer helpers
        grid = self.grid()
        px, py = self.pos
        facing = self.facing
        visible: set = set()
        try:
            ang_face = self.r._angle_for_facing(facing)
            half = math.radians(spread_deg) / 2.0
            pxf, pyf = float(px), float(py)
            for ty in range(py - radius, py + radius + 1):
                if not (0 <= ty < len(grid)):
                    continue
                for tx in range(px - radius, px + radius + 1):
                    if not (0 <= tx < len(grid[0])):
                        continue
                    dx = tx - pxf; dy = ty - pyf
                    if dx * dx + dy * dy > (radius + 0.5) * (radius + 0.5):
                        continue
                    ang = math.atan2(dy, dx)
                    near3 = (max(abs(dx), abs(dy)) <= 1.0)
                    if not near3:
                        if self.r._angle_diff(ang, ang_face) > half:
                            continue
                        los_px, los_py = int(round(pxf)), int(round(pyf))
                        if not self.r._los_clear(grid, los_px, los_py, tx, ty):
                            continue
                    visible.add((tx, ty))
        except Exception:
            # Fallback: simple radius without LOS
            for ty in range(py - radius, py + radius + 1):
                for tx in range(px - radius, px + radius + 1):
                    visible.add((tx, ty))
        return visible

    def apply_level_state(self, ix: int):
        # Synchronize runtime level chests with saved state for this level, if present
        try:
            lvl = self.dun.levels[ix]
        except Exception:
            return
        try:
            if lvl.stairs_down and len(lvl.stairs_down) == 2:
                x, y = int(lvl.stairs_down[0]), int(lvl.stairs_down[1])
                if 0 <= y < len(lvl.grid) and 0 <= x < len(lvl.grid[0]):
                    lvl.grid[y][x] = T_STAIRS_D
        except Exception:
            pass
        try:
            if lvl.stairs_up and len(lvl.stairs_up) == 2:
                x, y = int(lvl.stairs_up[0]), int(lvl.stairs_up[1])
                if 0 <= y < len(lvl.grid) and 0 <= x < len(lvl.grid[0]):
                    lvl.grid[y][x] = T_STAIRS_U
        except Exception:
            pass
        saved = self.chests_state.get(ix)
        if isinstance(saved, list):
            lvl.chests = list(saved)
        # Apply unlocked doors: convert those grid cells to empty
        try:
            doors = self.doors_unlocked.get(ix, [])
            g = lvl.grid
            for (dx, dy) in doors:
                if 0 <= dy < len(g) and 0 <= dx < len(g[0]):
                    g[dy][dx] = T_EMPTY
        except Exception:
            pass
        # Apply elites: override level elites with saved state if present
        try:
            if ix in self.elites_state:
                lvl.elites = list(self.elites_state.get(ix, []))
        except Exception:
            pass
        try:
            pos = self.waypoint_positions.get(ix)
            if pos and len(pos) == 2:
                x, y = int(pos[0]), int(pos[1])
                if 0 <= y < len(lvl.grid) and 0 <= x < len(lvl.grid[0]):
                    tile = lvl.grid[y][x]
                    if tile not in (T_STAIRS_D, T_STAIRS_U):
                        lvl.grid[y][x] = T_TOWN
                    lvl.town_portal = (x, y)
        except Exception:
            pass

    def party_has_rogue(self) -> bool:
        # Check active, alive members for Rogue class
        try:
            for gi in self.party.active:
                if 0 <= gi < len(self.party.members):
                    m = self.party.members[gi]
                    if m.alive and m.hp > 0 and m.cls == 'Rogue':
                        return True
        except Exception:
            pass
        return False

    def draw_threat_indicator(self):
        # Simple vertical bar at top-right showing threat from green->yellow->orange->red
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        w, h = 14, 92
        margin = 10
        x = WIDTH - w - margin
        y = margin
        # Background frame
        pygame.draw.rect(view, (24, 24, 28), (x, y, w, h))
        pygame.draw.rect(view, (70, 70, 80), (x, y, w, h), 1)
        # Fill based on threat fraction
        frac = 0.0
        try:
            frac = max(0.0, min(1.0, self.threat / float(max(1, self.threat_max))))
        except Exception:
            pass
        filled = int(h * frac)
        # Color by fraction
        if frac < 0.33:
            col = (60, 200, 90)    # green
        elif frac < 0.66:
            col = (220, 200, 60)   # yellow
        elif frac < 0.90:
            col = (240, 140, 60)   # orange
        else:
            col = (230, 70, 60)    # red
        # Draw from bottom up
        if filled > 0:
            pygame.draw.rect(view, col, (x + 2, y + h - filled + 2, w - 4, filled - 4))

    def draw_floor_indicator(self):
        # Top-left label showing current floor (1-based) with position and facing under it
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        margin = 10
        x, y = margin, margin
        floor_num = int(self.level_ix) + 1
        label1 = f"Floor {floor_num}"
        px, py = self.pos
        try:
            facing_label = DIR_NAMES[self.facing]
        except Exception:
            facing_label = "?"
        label2 = f"({px},{py}) {facing_label}"
        # Measure text
        try:
            s1 = self.r.font_small.render(label1, True, WHITE)
            s2 = self.r.font_small.render(label2, True, WHITE)
            w1, h1 = s1.get_width(), s1.get_height()
            w2, h2 = s2.get_width(), s2.get_height()
        except Exception:
            w1 = max(88, len(label1) * 6); h1 = 16
            w2 = max(88, len(label2) * 6); h2 = 16
        pad_x, pad_y = 8, 4
        gap = 2
        width = max(w1, w2) + pad_x * 2
        height = h1 + h2 + gap + pad_y * 2
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(view, (24, 24, 28), rect, border_radius=6)
        pygame.draw.rect(view, (70, 70, 80), rect, 1, border_radius=6)
        # Draw text lines
        self.r.text_small(view, label1, (x + pad_x, y + pad_y), YELLOW)
        self.r.text_small(view, label2, (x + pad_x, y + pad_y + h1 + gap), LIGHT)

    def trigger_threat_flash(self):
        self.threat_flash_active = True
        self.threat_flash_t0 = pygame.time.get_ticks()

    def draw_threat_flash(self):
        if not getattr(self, 'threat_flash_active', False):
            return
        now = pygame.time.get_ticks()
        dt = now - getattr(self, 'threat_flash_t0', now)
        dur = 180
        if dt >= dur:
            self.threat_flash_active = False
            return
        # Ease-out alpha over duration
        p = max(0.0, min(1.0, dt / float(dur)))
        alpha = int(160 * (1.0 - p))
        overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        overlay.fill((200, 40, 40, alpha))
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.blit(overlay, (0, 0))

    def draw_treasure_popup(self):
        if not getattr(self, 'treasure_popup_active', False):
            return
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Dim background
        s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 160))
        view.blit(s, (0, 0))
        # Popup window
        pad_x, pad_y = 14, 12
        title = "Treasure Found!"
        item = self.treasure_item_name or "(item)"
        text_h = self.r.font.get_height()
        w = max(self.r.font_big.size(title)[0], self.r.font.size(item)[0]) + pad_x * 2
        h = text_h * 3 + pad_y * 2
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (16, 20, 16), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        self.r.text_big(view, title, (x + pad_x, y + pad_y), YELLOW)
        self.r.text(view, item, (x + pad_x, y + pad_y + text_h + 6))
        self.r.text_small(view, "Enter/Esc: Close", (x + pad_x, y + pad_y + text_h * 2 + 10), LIGHT)

    # --------------- Dialog ---------------
    def start_dialog(self, npc_id: str):
        self.dialog_active = True
        self.dialog_npc_id = npc_id
        self.dialog_phase = 'root'
        self.dialog_menu_index = 0
        # Prepare typewriter for description
        npc = (getattr(self, 'npcs_by_id', {}) or {}).get(npc_id, {})
        desc = str(npc.get('desc', npc.get('name', 'Someone stands here.')))
        self.dialog_desc = desc
        self.dialog_text = [desc]
        self.dialog_type_t0 = pygame.time.get_ticks()
        self.dialog_type_chars = 0
        self.dialog_typer_prev_chars = 0
        self.dialog_desc_typing = True  # on first open, typewriter for description
        self.dialog_line_ix = 0
        self.mode = MODE_DIALOG

    def dialog_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self.dialog_phase == 'root':
            opts = ['Talk', 'Item', 'Leave']
            if event.key in (pygame.K_UP, pygame.K_k):
                self.dialog_menu_index = (self.dialog_menu_index - 1) % len(opts)
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.dialog_menu_index = (self.dialog_menu_index + 1) % len(opts)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                choice = self.dialog_menu_index
                if choice == 0:  # Talk
                    npc = (getattr(self, 'npcs_by_id', {}) or {}).get(self.dialog_npc_id, {})
                    qid = str(npc.get('quest_id', ''))
                    if qid:
                        st = self.quests_state.get(qid, 'not_started')
                        if st == 'not_started':
                            self.quests_state[qid] = 'active'
                            payload = [str(npc.get('talk_intro', npc.get('desc', '...')))]
                        elif st == 'active':
                            lines = npc.get('talk_active', [])
                            if isinstance(lines, list) and lines:
                                pick = random.choice(lines)
                                if isinstance(pick, list):
                                    payload = [str(x) for x in pick]
                                else:
                                    payload = [str(pick)]
                            else:
                                payload = [str(npc.get('talk_intro', npc.get('desc', '...')))]
                        else:
                            lines = npc.get('talk_complete', [])
                            if isinstance(lines, list) and lines:
                                pick = random.choice(lines)
                                if isinstance(pick, list):
                                    payload = [str(x) for x in pick]
                                else:
                                    payload = [str(pick)]
                            else:
                                payload = [str(npc.get('talk_complete', "Thank you again."))]
                        self.dialog_text = payload
                    else:
                        # 'talk' supports either a single string, or a list where each entry is
                        # either a string (single-line) or a list of strings (multi-line).
                        t = npc.get('talk', ["..."])
                        if isinstance(t, list) and t:
                            pick = random.choice(t)
                            if isinstance(pick, list):
                                self.dialog_text = [str(x) for x in pick]
                            else:
                                self.dialog_text = [str(pick)]
                        else:
                            self.dialog_text = [str(t)]
                    self.dialog_phase = 'talk'
                    self.dialog_line_ix = 0
                    self.dialog_type_t0 = pygame.time.get_ticks(); self.dialog_type_chars = 0
                    self.dialog_typer_prev_chars = 0
                elif choice == 1:  # Item (simple placeholder)
                    # Open inventory (condensed list) for presentation to NPC
                    self.dialog_item_ix = 0
                    self.dialog_phase = 'item'
                else:  # Leave
                    self.dialog_active = False
                    self.mode = MODE_MAZE
            elif event.key == pygame.K_ESCAPE:
                self.dialog_active = False
                self.mode = MODE_MAZE
        elif self.dialog_phase == 'item':
            # Present item selection: condensed inventory + Back
            # Build condensed inventory with unique order
            ordered: List[str] = []
            seen: set = set()
            for iid in self.party.inventory:
                if iid not in seen:
                    seen.add(iid); ordered.append(iid)
            n = max(1, len(ordered) + 1)
            if event.key in (pygame.K_UP, pygame.K_k):
                self.dialog_item_ix = (self.dialog_item_ix - 1) % n
            elif event.key in (pygame.K_DOWN, pygame.K_j):
                self.dialog_item_ix = (self.dialog_item_ix + 1) % n
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Back
                if self.dialog_item_ix == len(ordered):
                    # Return to description
                    self.dialog_phase = 'root'
                    self.dialog_desc_typing = False
                else:
                    iid = ordered[self.dialog_item_ix]
                    # NPC-specific reactions
                    resp = "They don't seem interested."
                    handled = False
                    npc = (getattr(self, 'npcs_by_id', {}) or {}).get(self.dialog_npc_id, {})
                    qid = str(npc.get('quest_id', ''))
                    if qid:
                        st = self.quests_state.get(qid, 'not_started')
                        quest = (self.quests_data.get(qid) or {})
                        required_item = str(quest.get('required_item', npc.get('quest_item', '')) or '')
                        if st == 'active' and required_item and iid == required_item:
                            reward_gold = int(quest.get('reward_gold', 0) or 0)
                            if reward_gold:
                                try:
                                    self.party.gold += reward_gold
                                except Exception:
                                    pass
                            reward_item = quest.get('reward_item')
                            if reward_item:
                                if isinstance(reward_item, list):
                                    for rid in reward_item:
                                        if rid:
                                            self.party.inventory.append(str(rid))
                                else:
                                    self.party.inventory.append(str(reward_item))
                            resp = str(quest.get('complete_text', 'Quest complete!'))
                            self.quests_state[qid] = 'completed'
                            handled = True
                        elif st == 'not_started':
                            resp = str(npc.get('talk_intro', resp))
                            handled = True
                        elif st == 'completed' and required_item and iid == required_item:
                            lines = npc.get('talk_complete', [])
                            if isinstance(lines, list) and lines:
                                pick = random.choice(lines)
                                if isinstance(pick, list):
                                    resp = " ".join(str(x) for x in pick)
                                else:
                                    resp = str(pick)
                            else:
                                resp = str(npc.get('talk_complete', resp))
                            handled = True
                    if not handled:
                        # generic or rejection
                        pass
                    # Show response as talk and then return to root
                    self.dialog_text = [resp]
                    self.dialog_phase = 'talk'
                    self.dialog_line_ix = 0
                    self.dialog_type_t0 = pygame.time.get_ticks(); self.dialog_type_chars = 0
                    self.dialog_typer_prev_chars = 0
            elif event.key == pygame.K_ESCAPE:
                # Cancel -> back to description
                self.dialog_phase = 'root'
                self.dialog_desc_typing = False
        elif self.dialog_phase == 'talk':
            # Enter advances typewriter/line; Esc leaves
            if event.key == pygame.K_ESCAPE:
                self.dialog_active = False
                self.mode = MODE_MAZE
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Compute whether current line is fully revealed
                now = pygame.time.get_ticks()
                line = str(self.dialog_text[self.dialog_line_ix]) if (0 <= self.dialog_line_ix < len(self.dialog_text)) else ''
                cps = 40.0
                shown = int(cps * (max(0, now - self.dialog_type_t0) / 1000.0))
                if shown < len(line):
                    # Fast-forward to full line
                    needed_ms = int((len(line) / cps) * 1000.0)
                    self.dialog_type_t0 = now - needed_ms
                    self.dialog_typer_prev_chars = len(line)
                else:
                    # Advance to next line or finish
                    self.dialog_line_ix += 1
                    if self.dialog_line_ix >= len(self.dialog_text):
                        # Done talking: return to root with description restored (no typewriter)
                        self.dialog_phase = 'root'
                        self.dialog_menu_index = 0
                        self.dialog_text = [self.dialog_desc]
                        self.dialog_line_ix = 0
                        self.dialog_type_t0 = pygame.time.get_ticks(); self.dialog_type_chars = 0
                        self.dialog_typer_prev_chars = 0
                        self.dialog_desc_typing = False
                    else:
                        self.dialog_type_t0 = pygame.time.get_ticks(); self.dialog_type_chars = 0
                        self.dialog_typer_prev_chars = 0

    def _wrap_text(self, text: str, max_w: int) -> List[str]:
        # Simple word wrapping using main font metrics
        words = text.split(' ')
        lines: List[str] = []
        cur = ''
        for w in words:
            test = w if not cur else cur + ' ' + w
            try:
                tw = self.r.font.size(test)[0]
            except Exception:
                tw = len(test) * 8
            if tw <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_dialog(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Dim background
        s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 180))
        view.blit(s, (0, 0))
        pad_x, pad_y = 16, 12
        title = (getattr(self, 'npcs_by_id', {}) or {}).get(self.dialog_npc_id, {}).get('name', 'Someone')
        text_h = self.r.font.get_height()
        # Panel: top quarter of the view
        top_h = max(80, VIEW_H // 4)
        x = 20; y = 10; w = WIDTH - 40; h = top_h
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (18, 18, 26), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        self.r.text_big(view, title, (x + pad_x, y + pad_y), YELLOW)
        # Typewriter for current line only
        now = pygame.time.get_ticks()
        elapsed = max(0, now - self.dialog_type_t0)
        cps = 40.0
        shown = int(cps * (elapsed / 1000.0))
        # Clamp to line length to avoid runaway increments
        line = str(self.dialog_text[self.dialog_line_ix]) if (0 <= self.dialog_line_ix < len(self.dialog_text)) else ''
        shown_clamped = min(shown, len(line))
        self.dialog_type_chars = shown_clamped
        # Voice tick per newly revealed character (talk phase only)
        if self.dialog_phase == 'talk':
            try:
                prev = int(getattr(self, 'dialog_typer_prev_chars', 0))
                if shown_clamped > prev:
                    # Only tick once per frame for the most recently revealed character,
                    # and only if it is a letter (skip spaces/punctuation)
                    idx = shown_clamped - 1
                    if 0 <= idx < len(line):
                        ch = line[idx]
                        if isinstance(ch, str) and ch.isalpha():
                            voice_id = (getattr(self, 'npcs_by_id', {}) or {}).get(self.dialog_npc_id, {}).get('voice', 'human_man')
                            key = f"voice_{voice_id}"
                            vol = 0.18 + random.random() * 0.06
                            if self.sfx and (self.sfx.sounds.get(key) or self.sfx.sounds.get('typer')):
                                self.sfx.play(key if self.sfx.sounds.get(key) else 'typer', vol)
                    self.dialog_typer_prev_chars = shown_clamped
            except Exception:
                pass
        # Ensure description is shown whenever we are on the root menu
        if self.dialog_phase == 'root':
            try:
                if self.dialog_text != [self.dialog_desc]:
                    self.dialog_text = [self.dialog_desc]
                    self.dialog_line_ix = 0
                    if self.dialog_desc_typing:
                        # Only typewriter when first stepping onto the NPC
                        self.dialog_type_t0 = pygame.time.get_ticks(); self.dialog_type_chars = 0
                        self.dialog_typer_prev_chars = 0
                    else:
                        # Show instantly otherwise
                        self.dialog_type_t0 = 0; self.dialog_type_chars = 0
            except Exception:
                pass
        # Determine text to show
        line = str(self.dialog_text[self.dialog_line_ix]) if (0 <= self.dialog_line_ix < len(self.dialog_text)) else ''
        # When in root and not typing, show full description instantly
        display_len = len(line) if (self.dialog_phase == 'root' and not self.dialog_desc_typing) else shown_clamped
        partial = line[:max(0, display_len)]
        # Wrap inside panel
        max_w = w - pad_x * 2
        wrapped = self._wrap_text(partial, max_w)
        name_text_gap = 16
        cy = y + pad_y + text_h + name_text_gap
        for ln in wrapped:
            self.r.text(view, ln, (x + pad_x, cy))
            cy += text_h
        # Flashing prompt '>' when line complete
        if shown_clamped >= len(line) and self.dialog_phase == 'talk':
            if (now // 400) % 2 == 0:
                self.r.text(view, '>', (x + w - pad_x - 14, y + h - pad_y - text_h), YELLOW)
        # Menu below the window when in root phase
        if self.dialog_phase == 'root':
            opts = ['Talk', 'Item', 'Leave']
            menu_y = y + h + 16
            # Draw a simple list menu centered
            tws = [self.r.font.size(o)[0] for o in opts]
            mw = max(tws) if tws else 0
            mx = WIDTH // 2 - (mw // 2)
            for i, o in enumerate(opts):
                is_sel = (i == self.dialog_menu_index)
                color = YELLOW if is_sel else WHITE
                prefix = '> ' if is_sel else '  '
                self.r.text(view, prefix + o, (mx, menu_y), color)
                menu_y += text_h + 6
        elif self.dialog_phase == 'item':
            # Inventory selection list
            # Build condensed list
            ordered: List[str] = []
            counts: Dict[str, int] = {}
            for iid in self.party.inventory:
                if iid not in counts:
                    counts[iid] = 1; ordered.append(iid)
                else:
                    counts[iid] += 1
            labels = []
            for iid in ordered:
                name = ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid)
                c = counts.get(iid, 1)
                labels.append(f"{name} x{c}" if c > 1 else name)
            options = labels + ["Back"]
            n = max(1, len(options))
            # Draw centered
            pad_x2, pad_y2 = 12, 10
            text_w = max(self.r.font.size(s + "  ")[0] for s in options) if options else 200
            text_h2 = self.r.font.get_height()
            w2 = text_w + pad_x2 * 2
            h2 = text_h2 * n + pad_y2 * 2
            x2 = WIDTH // 2 - w2 // 2
            y2 = y + h + 12
            rect2 = pygame.Rect(x2, y2, w2, h2)
            pygame.draw.rect(view, (16,16,20), rect2)
            pygame.draw.rect(view, YELLOW, rect2, 2)
            cy2 = y2 + pad_y2
            for i, s in enumerate(options):
                is_sel = (i == self.dialog_item_ix)
                prefix = '> ' if is_sel else '  '
                color = YELLOW if is_sel else WHITE
                self.r.text(view, prefix + s, (x2 + pad_x2, cy2), color)
                cy2 += text_h2

    # --------------- Quests ---------------
    def draw_quests(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        self.r.text_big(view, "Active Quests", (20, 16))
        # Build active quests list only
        all_q = (getattr(self, 'quests_data', {}) or {})
        state = (getattr(self, 'quests_state', {}) or {})
        qlist = [(qid, q) for qid, q in all_q.items() if state.get(qid, 'not_started') == 'active']
        qlist = sorted(qlist, key=lambda x: str(x[1].get('name', '')))
        if not qlist:
            self.r.text(view, "(No active quests)", (32, 60), GRAY)
            self.r.text_small(view, "Esc: Back", (32, VIEW_H - 28), LIGHT)
            return
        # Clamp index
        try:
            self.quests_index = int(self.quests_index)
        except Exception:
            self.quests_index = 0
        if qlist:
            self.quests_index %= max(1, len(qlist))
        # Left column: list
        y = 56
        for i, (qid, q) in enumerate(qlist):
            st = (getattr(self, 'quests_state', {}) or {}).get(qid, 'not_started')
            label = f"{i+1:>2}. {q.get('name', qid)}"
            col = YELLOW if st == 'active' else WHITE
            prefix = "> " if i == self.quests_index else "  "
            self.r.text(view, prefix + label, (32, y), col if i != self.quests_index else YELLOW)
            y += 22
        # Right column: description for selected
        if qlist:
            qid, q = qlist[self.quests_index]
            st = (getattr(self, 'quests_state', {}) or {}).get(qid, 'not_started')
            # Panel
            rx = WIDTH // 2
            ry = 56
            rw = WIDTH - rx - 24
            rh = VIEW_H - ry - 56
            rect = pygame.Rect(rx, ry, rw, rh)
            pygame.draw.rect(view, (20, 20, 26), rect)
            pygame.draw.rect(view, YELLOW, rect, 2)
            pad_x, pad_y = 14, 12
            name = str(q.get('name', qid))
            status_map = {'not_started': 'Not started', 'active': 'Active', 'completed': 'Completed'}
            st_text = status_map.get(st, st)
            self.r.text_big(view, name, (rx + pad_x, ry + pad_y), YELLOW)
            self.r.text_small(view, f"Status: {st_text}", (rx + pad_x, ry + pad_y + 30), LIGHT)
            # Description text
            desc = str(q.get('desc', ''))
            lines = self._wrap_text(desc, rw - pad_x * 2)
            cy = ry + pad_y + 60
            for ln in lines:
                self.r.text(view, ln, (rx + pad_x, cy))
                cy += self.r.font.get_height()
        # Hint
        self.r.text_small(view, "Up/Down: Select   Enter: View   Esc: Back", (32, VIEW_H - 28), LIGHT)

        # Popup view (optional)
        if getattr(self, 'quests_popup', False) and qlist:
            # Dim
            s = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            s.fill((0, 0, 0, 160))
            view.blit(s, (0, 0))
            # Centered box with full text
            qid, q = qlist[self.quests_index]
            title = str(q.get('name', qid))
            desc = str(q.get('desc', ''))
            padx, pady = 16, 12
            text_h = self.r.font.get_height()
            # Rough width
            max_w = WIDTH - 200
            wrapped = self._wrap_text(desc, max_w - padx * 2)
            w = max(self.r.font_big.size(title)[0], max((self.r.font.size(ln)[0] for ln in wrapped), default=200)) + padx * 2
            h = text_h * (len(wrapped) + 4) + pady * 2
            x = WIDTH // 2 - w // 2
            y = VIEW_H // 2 - h // 2
            rect = pygame.Rect(x, y, w, h)
            pygame.draw.rect(view, (16, 16, 22), rect)
            pygame.draw.rect(view, YELLOW, rect, 2)
            self.r.text_big(view, title, (x + padx, y + pady), YELLOW)
            cy = y + pady + text_h + 12
            for ln in wrapped:
                self.r.text(view, ln, (x + padx, cy))
                cy += text_h
            self.r.text_small(view, "Enter/Esc: Close", (x + padx, y + h - pady - text_h), LIGHT)

    def quests_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        # Build list for bounds
        all_q = (getattr(self, 'quests_data', {}) or {})
        state = (getattr(self, 'quests_state', {}) or {})
        qlist = [(qid, q) for qid, q in all_q.items() if state.get(qid, 'not_started') == 'active']
        qlist = sorted(qlist, key=lambda x: str(x[1].get('name', '')))
        n = max(1, len(qlist))
        if getattr(self, 'quests_popup', False):
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.quests_popup = False
            return
        if event.key in (pygame.K_UP, pygame.K_k):
            self.quests_index = (self.quests_index - 1) % n
            self.sfx.play('ui_move', 0.5)
        elif event.key in (pygame.K_DOWN, pygame.K_j):
            self.quests_index = (self.quests_index + 1) % n
            self.sfx.play('ui_move', 0.5)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Open popup view (optional)
            if qlist:
                self.quests_popup = True
            self.sfx.play('ui_select', 0.6)
        elif event.key == pygame.K_ESCAPE:
            # Return to previous mode (Town from town menu, Pause/Maze otherwise)
            ret = getattr(self, 'return_mode', MODE_TOWN)
            self.mode = ret

    def draw_door_confirm(self):
        if not getattr(self, 'door_confirm_active', False):
            return
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        view.blit(overlay, (0, 0))
        # Centered confirm box
        msg = "Use a Key to unlock?"
        text_h = self.r.font.get_height()
        pad_x, pad_y = 14, 12
        w = max(self.r.font.size(msg)[0], self.r.font.size("Yes")[0] + self.r.font.size("No")[0] + 40) + pad_x * 2
        h = text_h * 3 + pad_y * 2
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (20, 20, 26), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        self.r.text(view, msg, (x + pad_x, y + pad_y))
        # Yes/No menu
        opts = ["Yes", "No"]
        self.r.draw_center_menu(opts, self.door_confirm_index)

    def maze_input(self, event):
        if event.type == pygame.KEYDOWN:
            # Door confirm
            if getattr(self, 'door_confirm_active', False):
                if event.key in (pygame.K_UP, pygame.K_k, pygame.K_DOWN, pygame.K_j):
                    self.door_confirm_index = 1 - self.door_confirm_index
                    return
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.door_confirm_index == 0 and self.door_confirm_pos:
                        # consume a key and unlock
                        try:
                            self.party.inventory.remove('key')
                        except ValueError:
                            pass
                        x, y = self.door_confirm_pos
                        if self.in_bounds(x, y):
                            self.grid()[y][x] = T_EMPTY
                            # record unlocked door for persistence
                            try:
                                lst = self.doors_unlocked.setdefault(self.level_ix, [])
                                if (x, y) not in lst:
                                    lst.append((x, y))
                            except Exception:
                                pass
                        # attempt to move into it immediately
                        dx, dy = DIRS[self.facing]
                        if (self.pos[0] + dx, self.pos[1] + dy) == (x, y):
                            if not self.move_active:
                                self.move_active = True
                                self.move_from = self.pos
                                self.move_to = (x, y)
                                self.move_t0 = pygame.time.get_ticks()
                                self.move_step_sfx_count = 0
                        self.log.add("You unlock the door with a key.")
                    # close popup regardless
                    self.door_confirm_active = False
                    self.door_confirm_pos = None
                    return
                elif event.key == pygame.K_ESCAPE:
                    self.door_confirm_active = False
                    self.door_confirm_pos = None
                    return
            # Close treasure popup if showing
            if getattr(self, 'treasure_popup_active', False):
                if event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                    self.treasure_popup_active = False
                    return
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
            opts = ["Status", "Items", "Equip", "Quests", "Quit", "Close"]
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
                opts_len = 6
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.pause_index = (self.pause_index - 1) % opts_len
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.pause_index = (self.pause_index + 1) % opts_len
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.pause_index == 0:
                        self.return_mode = MODE_PAUSE
                        self.mode = MODE_STATUS
                    elif self.pause_index == 1:
                        # Items opened from Labyrinth; return to Maze when exiting
                        self.return_mode = MODE_MAZE
                        self.items_phase = 'items'
                        self.items_item_ix = 0
                        self.items_scroll = 0
                        self.mode = MODE_ITEMS
                    elif self.pause_index == 2:
                        self.equip_phase = 'member'
                        self.equip_member_ix = 0
                        self.equip_slot_ix = 0
                        self.equip_choose_ix = 0
                        self.return_mode = MODE_PAUSE
                        self.mode = MODE_EQUIP
                    elif self.pause_index == 3:
                        # Quests from labyrinth; return to Pause when exiting
                        self.return_mode = MODE_PAUSE
                        self.quests_index = 0
                        self.quests_popup = False
                        self.mode = MODE_QUESTS
                    elif self.pause_index == 4:
                        # Quit -> confirm prompt
                        self.pause_confirming_quit = True
                        self.pause_confirm_index = 1  # default to No
                    elif self.pause_index == 5:
                        self.mode = MODE_MAZE
                elif event.key == pygame.K_ESCAPE:
                    self.mode = MODE_MAZE

    def _build_condensed_inventory(self) -> Tuple[List[str], Dict[str, int]]:
        ordered: List[str] = []
        counts: Dict[str, int] = {}
        for iid in self.party.inventory:
            if iid not in counts:
                counts[iid] = 1
                ordered.append(iid)
            else:
                counts[iid] += 1
        return ordered, counts

    def _sync_items_scroll(self, total: int, window: int = 10) -> None:
        if total <= 0:
            self.items_scroll = 0
            self.items_item_ix = 0
            return
        window = max(1, window)
        max_scroll = max(0, total - window)
        if self.items_scroll > max_scroll:
            self.items_scroll = max_scroll
        if self.items_item_ix < 0:
            self.items_item_ix = 0
        elif self.items_item_ix >= total:
            self.items_item_ix = total - 1
        if self.items_item_ix < self.items_scroll:
            self.items_scroll = self.items_item_ix
        elif self.items_item_ix >= self.items_scroll + window:
            self.items_scroll = self.items_item_ix - window + 1

    def draw_items(self):
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        view.fill((18, 18, 24))
        # Header
        self.r.text_big(view, "Party Items", (20, 16))
        # Centered menu interface for Items
        if self.items_phase == 'items':
            ordered, counts = self._build_condensed_inventory()
            labels = []
            for iid in ordered:
                name = ITEMS_BY_ID.get(iid, {"name": iid}).get('name', iid)
                c = counts.get(iid, 1)
                labels.append(f"{name} x{c}" if c > 1 else name)
            options = labels + ["Back"]
            total = len(options) or 1
            self.items_item_ix = self.items_item_ix % total
            window = 10
            self._sync_items_scroll(total, window)
            start = self.items_scroll
            end = min(start + window, total)
            visible = options[start:end]
            if not visible:
                visible = options
                start = 0
                end = total
                self.items_scroll = 0
            selected_local = max(0, min(self.items_item_ix - start, len(visible) - 1))
            menu_rect = self.r.draw_center_menu(visible, selected_local)
            if self.items_scroll > 0:
                self.r.text_small(view, '^', (menu_rect.centerx - 4, menu_rect.top - 14), color=YELLOW)
            if end < total:
                self.r.text_small(view, 'v', (menu_rect.centerx - 4, menu_rect.bottom + 4), color=YELLOW)
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
                ordered, _ = self._build_condensed_inventory()
                n = len(ordered) + 1  # +1 for Back
                if n <= 0:
                    n = 1
                window = 10
                self.items_item_ix %= n
                self._sync_items_scroll(n, window)
                if event.key in (pygame.K_UP, pygame.K_k):
                    self.items_item_ix = (self.items_item_ix - 1) % n
                    self._sync_items_scroll(n, window)
                elif event.key in (pygame.K_DOWN, pygame.K_j):
                    self.items_item_ix = (self.items_item_ix + 1) % n
                    self._sync_items_scroll(n, window)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # If Back selected, return to previous mode
                    if self.items_item_ix == len(ordered):
                        self.mode = self.return_mode
                    else:
                        # Store selected iid from condensed list
                        self.items_selected_iid = ordered[self.items_item_ix]
                        self.items_action_ix = 0
                        self.items_phase = 'item_action'
                        self._sync_items_scroll(n, window)
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
                                total_after = len(ordered_after) + 1
                                if ordered_after:
                                    self.items_item_ix = min(self.items_item_ix, len(ordered_after) - 1)
                                else:
                                    self.items_item_ix = 0
                                self._sync_items_scroll(total_after, 10)
                        self.items_phase = 'items'
                elif event.key == pygame.K_ESCAPE:
                    self.items_phase = 'item_action'

    def use_item(self, target: Character, iid: str):
        it = ITEMS_BY_ID.get(iid)
        if not it:
            self.log.add("Nothing happens.")
            return
        if it.get('type') == 'consumable':
            if it.get('trait_select'):
                try:
                    member_ix = self.party.members.index(target)
                except ValueError:
                    self.log.add("Nothing happens.")
                    return
                name = it.get('name', 'Trait Tome')
                self.log.add(f"{target.name} studies the {name}.")
                if hasattr(self, 'items_phase'):
                    self.items_phase = 'items'
                return_mode = MODE_ITEMS if self.mode == MODE_ITEMS else self.mode
                if return_mode == MODE_BATTLE:
                    return_mode = MODE_PARTY
                self.start_trait_selection(member_ix, return_mode=return_mode)
                return
            name = it.get('name', 'Item')
            lower = name.lower()
            # HP heal
            if ('heal' in it) or ('heal_low' in it) or ('heal_high' in it):
                low = int(it.get('heal_low', it.get('heal', 0)))
                high = int(it.get('heal_high', it.get('heal', low)))
                if high < low:
                    low, high = high, low
                heal = random.randint(low, high)
                before = target.hp
                target.hp = min(target.max_hp, target.hp + heal)
                verb = 'eats' if 'cheese' in lower else ('drinks' if ('potion' in lower or 'droplet' in lower) else 'uses')
                self.log.add(f"{target.name} {verb} {name} (+{target.hp - before} HP).")
            # MP restore
            elif ('mp' in it) or ('mp_low' in it) or ('mp_high' in it):
                low = int(it.get('mp_low', it.get('mp', 0)))
                high = int(it.get('mp_high', it.get('mp', low)))
                if high < low:
                    low, high = high, low
                gain = random.randint(low, high)
                before = target.mp
                target.mp = min(target.max_mp, target.mp + gain)
                verb = 'drinks'
                self.log.add(f"{target.name} {verb} {name} (+{target.mp - before} MP).")
            # Max MP increase (permanent)
            elif 'max_mp_up' in it:
                inc = int(it.get('max_mp_up', 0))
                before = target.max_mp
                target.max_mp = max(0, before + inc)
                target.mp = min(target.max_mp, target.mp + inc)
                self.log.add(f"{target.name} uses {name} (+{inc} Max MP).")
        else:
            self.log.add("Nothing happens.")

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
            buffs = []
            if 'agi' in it:
                buffs.append(f"AGI+{it['agi']}")
            if 'ac' in it:
                buffs.append(f"AC{it['ac']:+}")
            if 'atk' in it:
                buffs.append(f"ATK+{it['atk']}")
            suffix = f" ({', '.join(buffs)})" if buffs else ""
            return it.get('name', iid) + suffix
        return "(empty)"

    def _item_requirement_status(self, m: Optional[Character], item: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, str, bool, str]]]:
        reqs = item.get('req')
        if not isinstance(reqs, dict) or not reqs:
            return True, []
        parts: List[Tuple[str, str, bool, str]] = []
        meets = True
        # Class requirement
        cls_req = reqs.get('class')
        if cls_req:
            if isinstance(cls_req, (list, tuple, set)):
                allowed = list(cls_req)
            else:
                allowed = [str(cls_req)]
            current_cls = getattr(m, 'cls', '?') if m else '?'
            ok = m is not None and current_cls in allowed
            if not ok:
                meets = False
            parts.append(('Class', '/'.join(allowed), ok, current_cls))
        # Level requirement
        if 'level' in reqs:
            needed_level = int(reqs.get('level', 0))
            current_level = getattr(m, 'level', 0) if m else 0
            ok = current_level >= needed_level
            if not ok:
                meets = False
            parts.append(('Level', str(needed_level), ok, str(current_level)))
        return meets, parts

    def _format_requirement_label(self, parts: List[Tuple[str, str, bool, str]]) -> str:
        if not parts:
            return ""
        labels = []
        for label, needed, ok, _actual in parts:
            if label == 'Class':
                labels.append(f"{needed}{'' if ok else '✗'}")
            elif label == 'Level':
                labels.append(f"Lv {needed}{'' if ok else '✗'}")
        return "Req " + " ".join(labels)

    def _character_can_equip(self, m: Character, item: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, str, bool, str]]]:
        ok, parts = self._item_requirement_status(m, item)
        return ok, parts

    def _collect_item_bonuses(self, m: Character) -> Dict[str, int]:
        total: Dict[str, int] = {}
        for iid in filter(None, [m.equipment.weapon_id, m.equipment.armor_id, m.equipment.acc1_id, m.equipment.acc2_id]):
            it = ITEMS_BY_ID.get(iid, {})
            for key, value in it.items():
                norm = BONUS_KEY_MAP.get(str(key).lower())
                if not norm:
                    continue
                try:
                    val_int = int(value)
                except (TypeError, ValueError):
                    continue
                if val_int == 0:
                    continue
                total[norm] = total.get(norm, 0) + val_int
        return total

    def _apply_single_bonus(self, m: Character, key: str, delta: int):
        if delta == 0:
            return
        if key == 'STR':
            m.str_ += delta
        elif key == 'IQ':
            m.iq += delta
        elif key == 'PIE':
            m.piety += delta
        elif key == 'VIT':
            m.vit += delta
        elif key == 'AGI':
            m.agi += delta
        elif key == 'HP':
            old_max = m.max_hp
            m.max_hp = max(1, m.max_hp + delta)
            if delta > 0:
                m.hp = min(m.max_hp, m.hp + delta)
            else:
                m.hp = min(m.hp, m.max_hp)
                if m.hp <= 0:
                    m.hp = 1
            # ensure hp not below 1 when alive
            if m.alive and m.hp <= 0:
                m.hp = 1
        elif key == 'MP':
            m.max_mp = max(0, m.max_mp + delta)
            if delta > 0:
                m.mp = min(m.max_mp, m.mp + delta)
            else:
                m.mp = min(m.mp, m.max_mp)
                if m.mp < 0:
                    m.mp = 0

    def _apply_gear_bonuses(self, m: Character):
        prev = getattr(m, 'gear_bonus', {}) or {}
        if prev:
            for key, value in prev.items():
                self._apply_single_bonus(m, key, -value)
        new_bonus = self._collect_item_bonuses(m)
        for key, value in new_bonus.items():
            self._apply_single_bonus(m, key, value)
        m.gear_bonus = new_bonus

    def refresh_party_gear_bonuses(self):
        if not getattr(self, 'party', None):
            return
        for m in getattr(self.party, 'members', []):
            try:
                self._apply_gear_bonuses(m)
            except Exception:
                pass

    def unlock_waypoint(self, level_ix: int):
        try:
            level_ix = int(level_ix)
        except Exception:
            return
        if level_ix not in self.unlocked_waypoints:
            self.unlocked_waypoints.add(level_ix)
        try:
            x, y = int(self.pos[0]), int(self.pos[1])
            self.waypoint_positions[level_ix] = (x, y)
            lvl = self.dun.levels[level_ix]
            if 0 <= y < len(lvl.grid) and 0 <= x < len(lvl.grid[0]):
                tile = lvl.grid[y][x]
                if tile not in (T_STAIRS_D, T_STAIRS_U):
                    lvl.grid[y][x] = T_TOWN
            if getattr(lvl, 'town_portal', None) != (x, y):
                lvl.town_portal = (x, y)
        except Exception:
            pass
        if level_ix != 0:
            try:
                floor_label = level_ix + 1
                self.log.add(f"Waypoint to Floor {floor_label} attuned.")
            except Exception:
                self.log.add("A new waypoint has been attuned.")

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
            options = []
            for iid in pool:
                it = ITEMS_BY_ID.get(iid, {"name": iid})
                label = it.get('name', iid)
                _, parts = self._character_can_equip(m, it)
                req_label = self._format_requirement_label(parts)
                if req_label:
                    label = f"{label} [{req_label}]"
                unmet = []
                for lbl, need, ok, _val in parts:
                    if ok:
                        continue
                    if lbl == 'Class':
                        unmet.append(need)
                    elif lbl == 'Level':
                        unmet.append(f"Lv {need}")
                if unmet:
                    label = f"{label} (need {', '.join(unmet)})"
                options.append(label)
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
        try:
            self._apply_gear_bonuses(m)
        except Exception:
            pass

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
                    item = ITEMS_BY_ID.get(iid, {"name": iid})
                    ok, parts = self._character_can_equip(m, item)
                    if not ok:
                        unmet = []
                        for lbl, need, meet, _val in parts:
                            if meet:
                                continue
                            if lbl == 'Class':
                                unmet.append(need)
                            elif lbl == 'Level':
                                unmet.append(f"Lv {need}")
                        if unmet:
                            msg = f"{m.name} needs {', '.join(unmet)} for {item.get('name', iid)}."
                            self.log.add(msg)
                        else:
                            self.log.add(f"{m.name} cannot equip {item.get('name', iid)}.")
                        try:
                            self.sfx.play('miss', 0.6)
                        except Exception:
                            pass
                        return
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
                # Guard against early input before the menu is populated
                if not b.ui_menu_options:
                    return
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
                    elif chosen_id == 'defend':
                        act = b.make_defend_action()
                        if act:
                            b.start_animation(act)
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
                        elif sid in ('sunder','rush','combo','backstab','dust'):
                            b.state = 'target'
                            b.target_mode = {'side': 'enemy', 'action': sid}
                            b.target_menu_index = 0
                        elif sid in ('regen','mend','heal'):
                            # choose party target
                            b.state = 'target'
                            b.target_mode = {'side': 'party', 'action': sid}
                            b.target_menu_index = 0
                        elif sid in ('flashbang','surge','storm'):
                            # no target selection (AOE)
                            actor = b.current_actor()
                            act = b.make_skill_action(actor, None, sid)
                            if act:
                                b.start_animation(act)
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
                        action_id = b.target_mode.get('action')
                        if action_id == 'attack':
                            act = b.make_attack_action(actor, target_i)
                        elif action_id == 'spell':
                            act = b.make_spell_action(actor, target_i)
                        else:
                            act = b.make_skill_action(actor, target_i, action_id)
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
                        action_id = b.target_mode.get('action')
                        if action_id == 'heal':
                            act = b.make_heal_action(actor, target_gi)
                        elif action_id in ('regen','mend'):
                            act = b.make_skill_action(actor, target_gi, action_id)
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
        if b and getattr(b, 'censor_music_fade_pending', False):
            if self.music and getattr(self.music, 'enabled', False):
                try:
                    self.music.fade_out_all(fade_ms=1600)
                except Exception:
                    pass
            b.censor_music_fade_pending = False
        view = self.screen.subsurface(pygame.Rect(0, 0, WIDTH, VIEW_H))
        # Slightly brighter base to make background more visible
        view.fill((14, 14, 22))
        # Determine if special silence background should override regular effects
        censor_fx_draw: Optional[Dict[str, Any]] = None
        if b and getattr(b, 'is_censor_battle', False) and getattr(b, 'censor_pulse_disabled', False):
            # Silence cast: psychedelic melting rings on plain dark background
            view.fill((24, 24, 32))
            now = pygame.time.get_ticks()
            overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
            centers = [
                (WIDTH // 2, VIEW_H // 2),
                (WIDTH // 3, VIEW_H // 3),
                (WIDTH * 2 // 3, VIEW_H * 2 // 3),
                (WIDTH // 4, VIEW_H * 3 // 5),
                (WIDTH * 3 // 4, VIEW_H // 4),
            ]
            for idx in range(12):
                cx, cy = centers[idx % len(centers)]
                cx += int(16 * math.sin(now / 1400.0 + idx * 0.8))
                cy += int(22 * math.sin(now / 1600.0 + idx * 1.3))
                base_r = 60 + 40 * (idx % 4)
                puls = 0.6 + 0.4 * math.sin((now / 900.0) + idx * 0.9)
                melt = 0.5 + 0.5 * math.sin((now / 700.0) + idx * 1.7)
                radius_x = int(base_r * (1.0 + puls * 0.6))
                radius_y = int(base_r * (0.6 + melt * 0.5))
                color_shift = 50 + int(30 * math.sin(now / 1100.0 + idx))
                col = (90 + color_shift, 90 + color_shift, 120 + color_shift // 2, 70 + int(40 * puls))
                rect = pygame.Rect(0, 0, max(12, radius_x * 2), max(12, radius_y * 2))
                rect.center = (cx, cy)
                pygame.draw.ellipse(overlay, col, rect, 4)
            for smear in range(6):
                smear_overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                smear_alpha = max(10, 40 - smear * 6)
                smear_color = (120, 120, 140, smear_alpha)
                stretch = 1.1 + smear * 0.04
                melt_rect = pygame.Rect(0, 0, int(WIDTH * stretch), int(VIEW_H * 0.35))
                melt_rect.center = (WIDTH // 2, int(VIEW_H * (0.3 + smear * 0.1)))
                pygame.draw.ellipse(smear_overlay, smear_color, melt_rect, 2)
                overlay.blit(smear_overlay, (0, 0), special_flags=pygame.BLEND_ADD)
            view.blit(overlay, (0, 0))
        else:
            # Background: subtle ripple rings (like water drips)
            self.draw_battle_ripples(view)
        had_censor_noise = False
        if b and getattr(b, 'is_censor_battle', False):
            fx = getattr(b, 'censor_silence_fx', None)
            if fx:
                now_fx = pygame.time.get_ticks()
                grow, hold, fade = fx.get('segments', (900, 400, 700))
                if not isinstance(grow, (int, float)) or grow <= 0:
                    grow = 900
                if not isinstance(hold, (int, float)) or hold < 0:
                    hold = 400
                if not isinstance(fade, (int, float)) or fade < 0:
                    fade = 700
                total = grow + hold + fade
                dt = max(0, now_fx - fx.get('start', now_fx))
                if dt >= total:
                    b.censor_silence_fx = None
                else:
                    size_p = 1.0
                    travel_p = 1.0
                    bg_alpha = 0
                    text_alpha = 255
                    if dt <= grow:
                        frac = dt / float(max(1, grow))
                        ease = frac * frac
                        size_p = frac
                        travel_p = ease
                        bg_alpha = int(180 * frac)
                    elif dt <= grow + hold:
                        size_p = 1.0
                        travel_p = 1.0
                        bg_alpha = 180
                    else:
                        after = dt - grow - hold
                        fade_p = after / float(max(1, fade))
                        fade_p = max(0.0, min(1.0, fade_p))
                        size_p = 1.0
                        travel_p = 1.0
                        bg_alpha = int(180 * (1.0 - fade_p))
                        text_alpha = int(255 * (1.0 - fade_p))
                    bg_alpha = max(0, min(200, bg_alpha))
                    text_alpha = max(0, min(255, text_alpha))
                    if fx.get('surface') is None:
                        try:
                            big_font = self.r._load_font(240)
                        except Exception:
                            big_font = self.r.font_big
                        surf = big_font.render('SILENCE', True, WHITE)
                        fx['surface'] = surf.convert_alpha()
                    censor_fx_draw = {
                        'bg_alpha': bg_alpha,
                        'text_alpha': text_alpha,
                        'size_p': max(0.0, min(1.0, size_p)),
                        'travel_p': max(0.0, min(1.0, travel_p)),
                        'enemy_index': fx.get('enemy_index'),
                        'surface': fx.get('surface'),
                    }
                    had_censor_noise = True
        pulse_active = True
        pulse_fade = 1.0
        noise_boost = 1.0
        if censor_fx_draw:
            damp = max(0.0, min(1.0, 1.0 - censor_fx_draw.get('bg_alpha', 0) / 200.0))
            pulse_active = damp > 0.0
            pulse_fade = damp
            noise_boost = 1.0 + (1.0 - damp) * 1.6
        if b and getattr(b, 'is_censor_battle', False) and getattr(b, 'censor_pulse_disabled', False):
            pulse_active = False
            pulse_fade = 0.0
            noise_boost = 2.6
        # Elite battle visual treatment: slow red pulse + light noise
        if b and getattr(b, 'is_elite', False):
            now_ms = pygame.time.get_ticks()
            # Red pulse overlay
            if pulse_active:
                pulse = 0.5 + 0.5 * math.sin(now_ms / 900.0)
            else:
                pulse = 0.0
            alpha = int((40 + 50 * pulse) * pulse_fade)
            if pulse_active and alpha > 0:
                overlay = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                r = int(140 * pulse_fade + 60 * (1.0 - pulse_fade))
                g = int(20 * pulse_fade + 60 * (1.0 - pulse_fade))
                bcol = int(20 * pulse_fade + 70 * (1.0 - pulse_fade))
                overlay.fill((r, g, bcol, max(0, min(255, alpha))))
                view.blit(overlay, (0, 0))
            if had_censor_noise:
                base_noise_alpha = 40 if not pulse_active else 24
                noise_alpha = int(base_noise_alpha * max(0.2, pulse_fade) * noise_boost)
                count = int(220 * noise_boost)
                if noise_alpha > 0 and count > 0:
                    noise = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                    seed = int(now_ms // 120)
                    rng = random.Random(seed)
                    for _ in range(count):
                        x = rng.randint(0, WIDTH - 1)
                        y = rng.randint(0, VIEW_H - 1)
                        sz = rng.randint(1, 3)
                        if not pulse_active:
                            base = rng.randint(40, 90)
                            tint = base
                            col = (tint, tint, min(150, tint + 6), noise_alpha)
                        else:
                            base = rng.randint(120, 180)
                            tint = int(base * max(0.3, pulse_fade) + 120 * (1.0 - pulse_fade))
                            col = (tint, tint, min(210, tint + 20), noise_alpha)
                        pygame.draw.rect(noise, col, pygame.Rect(x, y, sz, sz))
                    view.blit(noise, (0, 0))
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
        offsets_enemy_x: Dict[int, int] = {}
        offsets_party_x: Dict[int, int] = {}
        rotations_enemy: Dict[int, float] = {}
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
                extra_bounce = 0
                extra_forward = 0
                # For Spark spell: add a small bounce during pre-shot
                if act.get('type') == 'spell' and len(durs) >= 4 and stage == 1:
                    extra_bounce = int(4 * math.sin(p * math.pi))
                # Rush/Combo/Backstab movement
                if act.get('type') in ('rush','combo','backstab') and len(durs) >= 4:
                    ai = act.get('actor_index')
                    ti = act.get('target_index')
                    # Compute base centers using renderer math (to match exact window positions)
                    gap = 16
                    # Party centers
                    members = [self.party.members[i] for i in self.party.active
                               if 0 <= i < len(self.party.members)
                               and self.party.members[i].alive and self.party.members[i].hp > 0]
                    n = max(1, len(members))
                    w = min(220, (WIDTH - gap * (n + 1)) // max(1, n))
                    total = n * w + (n + 1) * gap
                    xstart = (WIDTH - total) // 2 + gap
                    col = 0
                    for idx, m in enumerate(members):
                        try:
                            if self.party.members.index(m) == ai:
                                col = idx; break
                        except Exception:
                            pass
                    src_cx = xstart + col * (w + gap) + w // 2
                    base_party_y = VIEW_H - 60 - 16
                    # Enemy centers (from battle state)
                    alive = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    ne = max(1, len(alive))
                    we = min(220, (WIDTH - gap * (ne + 1)) // max(1, ne))
                    totale = ne * we + (ne + 1) * gap
                    xse = (WIDTH - totale) // 2 + gap
                    j = sorted(alive).index(ti) if ti in alive else 0
                    dst_cx = xse + j * (we + gap) + we // 2
                    enemy_y = 28
                    dy_full = enemy_y - base_party_y  # negative
                    dx_full = dst_cx - src_cx
                    if act.get('type') == 'rush':
                        # Rush: move exactly onto target center over stages
                        if stage == 1:
                            offsets_party[ai] = int(dy_full * (p * p * p))
                            offsets_party_x[ai] = int(dx_full * (p * p))
                        elif stage == 2:
                            offsets_party[ai] = dy_full + int(10 * abs(math.sin(p * math.pi)))
                            offsets_party_x[ai] = dx_full
                        elif stage == 3:
                            offsets_party[ai] = int(dy_full * (1.0 - p))
                            offsets_party_x[ai] = int(dx_full * (1.0 - p))
                    elif act.get('type') == 'combo':
                        # Partial forward lunge, double bump on impact
                        if stage == 1:
                            offsets_party[ai] = int(dy_full * 0.3 * (p * p))
                            offsets_party_x[ai] = int(dx_full * 0.3 * (p * p))
                        elif stage == 2:
                            offsets_party[ai] += int(8 * abs(math.sin(p * math.pi * 2)))
                    elif act.get('type') == 'backstab':
                        # Teleport-style: fade out, then appear at side of target (no pre motion)
                        side_dir = -1 if (ti or 0) % 2 else 1
                        side_gap = we // 2 + 14
                        target_x_side = dst_cx + side_dir * side_gap
                        dx_side = target_x_side - src_cx
                        if stage == 1:
                            if p < 0.5:
                                # no motion during fade-out
                                offsets_party[ai] = 0; offsets_party_x[ai] = 0
                            else:
                                # appear at side; keep Y aligned with enemy row before impact
                                offsets_party[ai] = dy_full
                                offsets_party_x[ai] = dx_side
                        elif stage == 2:
                            # bump into target from the side
                            offsets_party[ai] = dy_full + int(8 * abs(math.sin(p * math.pi)))
                            offsets_party_x[ai] = dx_side
                        elif stage == 3:
                            # return to origin
                            offsets_party[ai] = int(dy_full * (1.0 - p))
                            offsets_party_x[ai] = int(dx_side * (1.0 - p))
                base_up = -(off + extra_bounce)
                if act.get('type') not in ('rush','combo','backstab') or len(durs) < 4:
                    # Default behavior for non-special skills
                    offsets_party[act['actor_index']] = base_up - extra_forward
                # Backstab: approximate horizontal slide during pre without needing rects
                if act.get('type') == 'backstab' and len(durs) >= 4 and stage == 1:
                    ai = act.get('actor_index'); ti = act.get('target_index')
                    # Move toward the right for even targets, left for odd targets to simulate circling
                    dir_ = -1 if (ti or 0) % 2 else 1
                    max_dx = 120  # pixels
                    offsets_party_x[ai] = int(dir_ * max_dx * (p * p))
            elif act.get('actor_side') == 'enemy' and act.get('actor_index') is not None:
                # Enemy lunges downward (positive y) / special movements
                extra_bounce_e = 0
                if act.get('type') == 'splash' and len(durs) >= 4 and stage == 1:
                    extra_bounce_e = int(3 * math.sin(p * math.pi))
                ai = act.get('actor_index')
                ti = act.get('target_index')
                if act.get('type') == 'rush' and len(durs) >= 4:
                    # Compute exact centers for enemy actor and party target
                    gap = 16
                    # Enemy centers
                    alive_e = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    ne = max(1, len(alive_e))
                    we = min(220, (WIDTH - gap * (ne + 1)) // max(1, ne))
                    total_e = ne * we + (ne + 1) * gap
                    xse = (WIDTH - total_e) // 2 + gap
                    j_ai = sorted(alive_e).index(ai) if ai in alive_e else 0
                    src_cx = xse + j_ai * (we + gap) + we // 2
                    enemy_y = 28
                    # Party centers
                    members = [self.party.members[i] for i in self.party.active
                               if 0 <= i < len(self.party.members)
                               and self.party.members[i].alive and self.party.members[i].hp > 0]
                    n = max(1, len(members))
                    w = min(220, (WIDTH - gap * (n + 1)) // max(1, n))
                    total_p = n * w + (n + 1) * gap
                    xsp = (WIDTH - total_p) // 2 + gap
                    # find target col among actives
                    col_t = 0
                    for idx, m in enumerate(members):
                        try:
                            if self.party.members.index(m) == ti:
                                col_t = idx; break
                        except Exception:
                            pass
                    dst_cx = xsp + col_t * (w + gap) + w // 2
                    base_party_y = VIEW_H - 60 - 16
                    dy_full = base_party_y - enemy_y  # move down
                    dx_full = dst_cx - src_cx
                    if stage == 1:
                        offsets_enemy[ai] = int(dy_full * (p * p * p))
                        offsets_enemy_x[ai] = int(dx_full * (p * p))
                    elif stage == 2:
                        offsets_enemy[ai] = dy_full + int(10 * abs(math.sin(p * math.pi)))
                        offsets_enemy_x[ai] = dx_full
                    elif stage == 3:
                        offsets_enemy[ai] = int(dy_full * (1.0 - p))
                        offsets_enemy_x[ai] = int(dx_full * (1.0 - p))
                elif act.get('bone_bash') and len(durs) >= 4:
                    gap = 16
                    alive_e = [i for i, en in enumerate(b.enemies) if en.hp > 0]
                    if ai not in alive_e:
                        alive_e.append(ai)
                    alive_e = sorted(set(alive_e))
                    ne = max(1, len(alive_e))
                    we = min(220, (WIDTH - gap * (ne + 1)) // max(1, ne))
                    total_e = ne * we + (ne + 1) * gap
                    xse = (WIDTH - total_e) // 2 + gap
                    j_ai = alive_e.index(ai) if ai in alive_e else 0
                    src_cx = xse + j_ai * (we + gap) + we // 2
                    enemy_y = 28
                    members = [self.party.members[i] for i in self.party.active
                               if 0 <= i < len(self.party.members)
                               and self.party.members[i].alive and self.party.members[i].hp > 0]
                    n = max(1, len(members))
                    w = min(220, (WIDTH - gap * (n + 1)) // max(1, n))
                    total_p = n * w + (n + 1) * gap
                    xsp = (WIDTH - total_p) // 2 + gap
                    col_t = 0
                    for idx, m in enumerate(members):
                        try:
                            if self.party.members.index(m) == ti:
                                col_t = idx; break
                        except Exception:
                            pass
                    dst_cx = xsp + col_t * (w + gap) + w // 2
                    base_party_y = VIEW_H - 60 - 16
                    dy_full = base_party_y - enemy_y
                    dx_full = dst_cx - src_cx
                    if stage == 1:
                        offsets_enemy[ai] = int(dy_full * (p * p))
                        offsets_enemy_x[ai] = int(dx_full * (p * p))
                    elif stage == 2:
                        offsets_enemy[ai] = dy_full + int(8 * math.sin(p * math.pi))
                        offsets_enemy_x[ai] = dx_full
                    elif stage == 3:
                        offsets_enemy[ai] = int(dy_full * (1.0 - p))
                        offsets_enemy_x[ai] = int(dx_full * (1.0 - p))
                elif act.get('type') == 'goblin_devour' and len(durs) >= 4:
                    # Move horizontally to the target goblin, slight bump, then back
                    tgt = act.get('target_enemy_index')
                    gap = 16
                    alive_e = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    # Ensure both indices are represented for layout purposes
                    if ai not in alive_e: alive_e.append(ai)
                    if tgt not in alive_e: alive_e.append(tgt)
                    alive_e = sorted(set(alive_e))
                    ne = max(1, len(alive_e))
                    we = min(220, (WIDTH - gap * (ne + 1)) // max(1, ne))
                    total_e = ne * we + (ne + 1) * gap
                    xse = (WIDTH - total_e) // 2 + gap
                    j_ai = alive_e.index(ai) if ai in alive_e else 0
                    j_tg = alive_e.index(tgt) if tgt in alive_e else 0
                    src_cx = xse + j_ai * (we + gap) + we // 2
                    dst_cx = xse + j_tg * (we + gap) + we // 2
                    dx_full = dst_cx - src_cx
                    if stage == 1:
                        offsets_enemy[ai] = 0
                        offsets_enemy_x[ai] = int(dx_full * (p * p))
                    elif stage == 2:
                        offsets_enemy[ai] = int(8 * abs(math.sin(p * math.pi)))
                        offsets_enemy_x[ai] = dx_full
                    elif stage == 3:
                        offsets_enemy[ai] = 0
                        offsets_enemy_x[ai] = int(dx_full * (1.0 - p))
                elif act.get('type') == 'goblin_throw' and len(durs) >= 4:
                    # During windup, hop towards the goblin to pick it up; during projectile, hide source goblin
                    gix = act.get('g_index')
                    gap = 16
                    alive_e = [i for i, e in enumerate(b.enemies) if e.hp > 0]
                    if ai not in alive_e: alive_e.append(ai)
                    if gix not in alive_e: alive_e.append(gix)
                    alive_e = sorted(set(alive_e))
                    ne = max(1, len(alive_e))
                    we = min(220, (WIDTH - gap * (ne + 1)) // max(1, ne))
                    total_e = ne * we + (ne + 1) * gap
                    xse = (WIDTH - total_e) // 2 + gap
                    j_ai = alive_e.index(ai) if ai in alive_e else 0
                    j_g = alive_e.index(gix) if gix in alive_e else 0
                    src_cx = xse + j_ai * (we + gap) + we // 2
                    gob_cx = xse + j_g * (we + gap) + we // 2
                    dx_full = gob_cx - src_cx
                    if stage == 0:
                        offsets_enemy_x[ai] = int(dx_full * (p * p))
                    elif stage == 1:
                        # hide goblin window while in flight
                        offsets_enemy_x[gix] = offsets_enemy_x.get(gix, 0) + 2000
                    elif stage == 3:
                        offsets_enemy_x[ai] = int(dx_full * (1.0 - p))
                else:
                    offsets_enemy[ai] = off + extra_bounce_e
            # If an attack/spell missed, slide the target sideways on impact and return during recover
            if act.get('type') in ('attack', 'spell') and not act.get('hit', True):
                target_ix = act.get('target_index')
                target_side = act.get('target_side')
                # Direction based on index parity for variation
                dir_ = -1 if (target_ix or 0) % 2 == 0 else 1
                max_dx = 12
                dx = 0
                if len(durs) >= 4:
                    if stage == 2:
                        # move out
                        pe = 1.0 - (1.0 - p) * (1.0 - p)
                        dx = int(max_dx * pe) * dir_
                    elif stage == 3:
                        # move back
                        dx = int(max_dx * (1.0 - p)) * dir_
                else:
                    if stage == 1:
                        dx = int(max_dx) * dir_
                    elif stage == 2:
                        dx = int(max_dx * (1.0 - p)) * dir_
                if target_side == 'party' and target_ix is not None:
                    offsets_party_x[target_ix] = dx
                elif target_side == 'enemy' and target_ix is not None:
                    offsets_enemy_x[target_ix] = dx

        # Persistent enemy effects: slime pulse shake and goblin spin
        if b:
            now = pygame.time.get_ticks()
            # Slime shake: retrigger small jitter while pulsed
            for i, e in enumerate(b.enemies):
                if getattr(e, 'hp', 0) > 0 and b.slime_pulsed.get(i):
                    self.effects.trigger('enemy', i, 120, 4, WHITE)
                # Slime Mind low HP shake (like pulsing slime)
                try:
                    if getattr(e, 'hp', 0) > 0 and getattr(e, 'id', '') == 'slime_mind':
                        mhp = max(1, int(getattr(e, 'max_hp', e.hp * 2)))
                        if e.hp < max(1, int(0.5 * mhp)):
                            self.effects.trigger('enemy', i, 120, 5, WHITE)
                except Exception:
                    pass
            # Goblin trip spin: compute rotation angle over duration
            to_remove = []
            for i, info in b.enemy_spin.items():
                start = info.get('start', now)
                dur = max(1, info.get('dur', 500))
                p = max(0.0, min(1.0, (now - start) / float(dur)))
                angle = 360.0 * p
                rotations_enemy[i] = angle
                if p >= 1.0:
                    to_remove.append(i)
            for i in to_remove:
                b.enemy_spin.pop(i, None)

        # Screen shake on Rush impact
        if b and b.state == 'anim' and b.anim:
            act = b.anim['action']
            stage = b.anim.get('stage', 0)
            if act.get('type') == 'rush' and stage == 2:
                sx = random.randint(-4, 4)
                sy = random.randint(-4, 4)
                # apply to all visible windows
                for i in range(len(b.enemies)):
                    offsets_enemy[i] = offsets_enemy.get(i, 0) + sy
                    offsets_enemy_x[i] = offsets_enemy_x.get(i, 0) + sx
                party_active_ix = [i for i in self.party.active if 0 <= i < len(self.party.members) and self.party.members[i].alive and self.party.members[i].hp > 0]
                for gi in party_active_ix:
                    offsets_party[gi] = offsets_party.get(gi, 0) + sy
                    offsets_party_x[gi] = offsets_party_x.get(gi, 0) + sx

        enemy_rects = self.r.draw_combat_enemy_windows(b.enemies if b else [], self.effects, enemy_highlight, enemy_acting, dying_prog, offsets_enemy, offsets_enemy_x, rotations_enemy) if b else {}
        party_rects = self.r.draw_combat_party_windows(self.party, self.effects, party_highlight, party_acting, offsets_party, offsets_party_x)

        if b and b.kobold_dart_fx:
            now = pygame.time.get_ticks()
            for gi, fx in list(b.kobold_dart_fx.items()):
                rect = party_rects.get(gi)
                if not rect:
                    continue
                start = fx.get('start', now)
                dur = max(1, int(fx.get('dur', 520)))
                elapsed = now - start
                if elapsed < 0 or elapsed >= dur:
                    continue
                prog = max(0.0, min(1.0, elapsed / float(dur)))
                bubble = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                center_x = rect.width // 2
                base_y = rect.height // 2
                for idx in range(5):
                    phase = prog * (4.5 + idx * 0.4) + idx * 0.8
                    radius = max(3, int(7 - prog * 3 + math.sin(phase) * 1.5))
                    drift_x = int((rect.width * 0.25) * math.sin(phase * 1.3))
                    rise = int(prog * rect.height * 0.35 + idx * 4)
                    cy = base_y - rise
                    cx = center_x + drift_x
                    cx = max(radius, min(rect.width - radius, cx))
                    cy = max(radius, min(rect.height - radius, cy))
                    color_outer = (70, 230, 150, max(40, int(160 * (1.0 - prog))))
                    color_inner = (60, 180, 130, max(30, int(140 * (1.0 - prog))))
                    pygame.draw.circle(bubble, color_outer, (cx, cy), radius, 2)
                    if radius > 2:
                        pygame.draw.circle(bubble, color_inner, (cx, cy), max(1, radius - 2), 1)
                haze_height = max(4, int(rect.height * 0.4 * (1.0 - prog)))
                haze_rect = pygame.Rect(0, 0, rect.width, haze_height)
                haze_rect.midbottom = (rect.width // 2, rect.height)
                pygame.draw.rect(bubble, (40, 200, 120, max(20, int(90 * (1.0 - prog)))), haze_rect)
                view.blit(bubble, rect.topleft, special_flags=pygame.BLEND_ADD)

        def render_purple_burst(rect: Optional[pygame.Rect], prog: float, scale: float = 1.0, color: Tuple[int, int, int] = (190, 120, 255)):
            if not rect:
                return
            cx, cy = rect.centerx, rect.centery
            base_radius = rect.width * 0.3 * scale
            tip_radius = base_radius * (1.2 + 1.6 * prog)
            tri_angle = 0.45
            count = max(6, int(14 * scale))
            for i in range(count):
                ang = (2 * math.pi * i / count) + (prog * math.pi)
                tip = (cx + math.cos(ang) * tip_radius, cy + math.sin(ang) * tip_radius)
                left = (cx + math.cos(ang - tri_angle) * base_radius, cy + math.sin(ang - tri_angle) * base_radius)
                right = (cx + math.cos(ang + tri_angle) * base_radius, cy + math.sin(ang + tri_angle) * base_radius)
                pygame.draw.polygon(view, color, [tip, left, right])

        # Spell projectile (Spark): rotating triangle from caster to target during pre stage
        if b and b.state == 'anim' and b.anim:
            act = b.anim['action']
            if act.get('type') == 'spell':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    actor_side = act.get('actor_side')
                    ai = act.get('actor_index')
                    ti = act.get('target_index')
                    src_pos = dst_pos = None
                    if actor_side == 'party':
                        src_rect = party_rects.get(ai)
                        dst_rect = enemy_rects.get(ti)
                        if src_rect and dst_rect:
                            src_pos = (src_rect.centerx, src_rect.top)
                            dst_pos = (dst_rect.centerx, dst_rect.centery)
                    elif actor_side == 'enemy':
                        src_rect = enemy_rects.get(ai)
                        dst_rect = party_rects.get(ti)
                        if src_rect and dst_rect:
                            src_pos = (src_rect.centerx, src_rect.bottom)
                            dst_pos = (dst_rect.centerx, dst_rect.top)
                    if src_pos and dst_pos:
                        now = pygame.time.get_ticks()
                        t0 = b.anim.get('t0', now)
                        dur = durs[stage] if stage < len(durs) else 1
                        p = 0.0
                        if dur > 0:
                            p = max(0.0, min(1.0, (now - t0) / float(dur)))
                        sx, sy = src_pos
                        ex, ey = dst_pos
                        # Strong ease-in so it starts very slow and accelerates toward target
                        pe = p * p * p
                        cx = sx + (ex - sx) * pe
                        cy = sy + (ey - sy) * pe
                        spell_id = str(act.get('spell_id', 'spark'))
                        ang = math.atan2(ey - sy, ex - sx)
                        if actor_side == 'enemy' and spell_id == 'mana_surge':
                            base_size = 22
                            spin = (now / 380.0) % (2 * math.pi)
                            theta = ang + spin

                            def pentagon_points(cx_: float, cy_: float, radius: float, angle_: float) -> List[Tuple[float, float]]:
                                pts = []
                                for idx in range(5):
                                    a = angle_ + idx * (2 * math.pi / 5.0)
                                    pts.append((cx_ + math.cos(a) * radius, cy_ + math.sin(a) * radius))
                                return pts

                            trail = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                            for k in range(1, 9):
                                tk = p - k * 0.05
                                if tk <= 0:
                                    continue
                                tke = tk * tk
                                tx = sx + (ex - sx) * tke
                                ty = sy + (ey - sy) * tke
                                size_k = max(8, int(base_size * (0.9 ** k)))
                                pts = pentagon_points(tx, ty, size_k, theta - k * 0.25)
                                alpha = max(30, 150 - k * 14)
                                pygame.draw.polygon(trail, (200, 150, 255, alpha), pts)
                            view.blit(trail, (0, 0))
                            main_pts = pentagon_points(cx, cy, base_size, theta)
                            pygame.draw.polygon(view, (230, 180, 255), main_pts)
                            inner_pts = pentagon_points(cx, cy, base_size * 0.55, theta + math.pi / 5.0)
                            pygame.draw.polygon(view, (120, 60, 200), inner_pts, 2)
                        else:
                            base_size = 16
                            spin = (now / 500.0) % (2 * math.pi)
                            theta = ang + spin
                            trail = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                            for k in range(1, 6):
                                tk = p - k * 0.06
                                if tk <= 0:
                                    continue
                                tke = tk * tk
                                tx = sx + (ex - sx) * tke
                                ty = sy + (ey - sy) * tke
                                size_k = max(6, int(base_size * (0.85 ** k)))
                                tip_k = (tx + math.cos(theta) * size_k, ty + math.sin(theta) * size_k)
                                left_k = (tx + math.cos(theta + 2.0 * math.pi / 3.0) * size_k, ty + math.sin(theta + 2.0 * math.pi / 3.0) * size_k)
                                right_k = (tx + math.cos(theta - 2.0 * math.pi / 3.0) * size_k, ty + math.sin(theta - 2.0 * math.pi / 3.0) * size_k)
                                alpha = max(20, 120 - k * 18)
                                pygame.draw.polygon(trail, (240, 220, 80, alpha), [tip_k, left_k, right_k])
                            view.blit(trail, (0, 0))
                            tip = (cx + math.cos(theta) * base_size, cy + math.sin(theta) * base_size)
                            left = (cx + math.cos(theta + 2.0 * math.pi / 3.0) * base_size, cy + math.sin(theta + 2.0 * math.pi / 3.0) * base_size)
                            right = (cx + math.cos(theta - 2.0 * math.pi / 3.0) * base_size, cy + math.sin(theta - 2.0 * math.pi / 3.0) * base_size)
                            pygame.draw.polygon(view, YELLOW, [tip, left, right], 2)
            # Slime 'splash' visual: green circle projectiles to each party member
            elif act.get('type') == 'splash' and act.get('actor_side') == 'enemy':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    ei = act.get('actor_index')
                    src_rect = enemy_rects.get(ei)
                    if src_rect:
                        sx, sy = src_rect.centerx, src_rect.bottom
                        # Targets: alive active party members
                        alive_gi = [i for i in self.party.active
                                    if 0 <= i < len(self.party.members)
                                    and self.party.members[i].alive and self.party.members[i].hp > 0]
                        # Draw trail surface once
                        trail = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                        for gi in alive_gi:
                            dst_rect = party_rects.get(gi)
                            if not dst_rect:
                                continue
                            ex, ey = dst_rect.centerx, dst_rect.top
                            # strong ease-in for slower start
                            pe = p * p * p
                            cx = sx + (ex - sx) * pe
                            cy = sy + (ey - sy) * pe
                            # Trail: faded green circles along prior eased positions
                            for k in range(1, 6):
                                tk = p - k * 0.06
                                if tk <= 0:
                                    continue
                                tke = tk * tk * tk
                                tx = sx + (ex - sx) * tke
                                ty = sy + (ey - sy) * tke
                                r_k = max(3, int(8 * (0.85 ** k)))
                                alpha = max(20, 110 - k * 18)
                                pygame.draw.circle(trail, (64, 200, 100, alpha), (int(tx), int(ty)), r_k)
                            # Main circle outline
                            pygame.draw.circle(trail, GREEN, (int(cx), int(cy)), 10, 2)
                        view.blit(trail, (0, 0))
            elif act.get('type') == 'kobold_poison_dart' and act.get('actor_side') == 'enemy':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    ai = act.get('actor_index')
                    ti = act.get('target_index')
                    src_rect = enemy_rects.get(ai)
                    dst_rect = party_rects.get(ti)
                    if src_rect and dst_rect:
                        sx, sy = src_rect.centerx, src_rect.bottom
                        ex, ey = dst_rect.centerx, dst_rect.top + 6
                        # accelerate quickly toward target
                        pe = max(0.0, min(1.0, p * p * p * 1.4))
                        pe = min(1.0, pe)
                        cx = sx + (ex - sx) * pe
                        cy = sy + (ey - sy) * pe
                        trail = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                        for k in range(1, 5):
                            tk = p - k * 0.08
                            if tk <= 0:
                                continue
                            tke = max(0.0, min(1.0, tk * tk * tk))
                            tx = sx + (ex - sx) * tke
                            ty = sy + (ey - sy) * tke
                            radius = max(2, int(6 * (0.75 ** k)))
                            alpha = max(30, 130 - k * 20)
                            pygame.draw.circle(trail, (70, 220, 140, alpha), (int(tx), int(ty)), radius)
                        main_color = (90, 255, 160)
                        pygame.draw.circle(trail, main_color, (int(cx), int(cy)), 6)
                        # dart tip line for direction
                        tail_x = sx + (ex - sx) * max(0.0, pe - 0.12)
                        tail_y = sy + (ey - sy) * max(0.0, pe - 0.12)
                        pygame.draw.line(trail, main_color, (int(tail_x), int(tail_y)), (int(cx), int(cy)), 2)
                        view.blit(trail, (0, 0))
            elif act.get('type') == 'suck_blood' and act.get('hit'):
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    ai = act.get('actor_index')
                    ti = act.get('target_index')
                    src_rect = party_rects.get(ti)
                    dst_rect = enemy_rects.get(ai)
                    if src_rect and dst_rect:
                        sx, sy = src_rect.centerx, src_rect.centery
                        ex, ey = dst_rect.centerx, dst_rect.centery
                        pe = max(0.0, min(1.0, p * p * 1.6))
                        cx = sx + (ex - sx) * pe
                        cy = sy + (ey - sy) * pe
                        trail = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                        for k in range(1, 6):
                            tk = p - k * 0.08
                            if tk <= 0:
                                continue
                            tke = max(0.0, min(1.0, tk * tk))
                            tx = sx + (ex - sx) * tke
                            ty = sy + (ey - sy) * tke
                            radius = max(3, int(9 * (0.78 ** k)))
                            alpha = max(40, 150 - k * 18)
                            pygame.draw.circle(trail, (200, 40, 60, alpha), (int(tx), int(ty)), radius, 2)
                        pulse = int(4 + 3 * math.sin(now / 80.0))
                        pygame.draw.circle(trail, (220, 60, 80), (int(cx), int(cy)), 8 + pulse, 2)
                        pygame.draw.circle(trail, (255, 90, 110), (int(cx), int(cy)), max(3, 5 + pulse // 2))
                        view.blit(trail, (0, 0))
            # Goblin Chief throw: spin the goblin window towards the party target (Spark-like speed)
            elif act.get('type') == 'goblin_throw' and act.get('actor_side') == 'enemy':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    ai = act.get('actor_index')
                    gix = act.get('g_index')
                    ti = act.get('target_index')
                    # Start from the Goblin Chief's window so it looks like he throws it
                    src_rect = enemy_rects.get(ai)
                    dst_rect = party_rects.get(ti)
                    if src_rect and dst_rect:
                        sx, sy = src_rect.centerx, src_rect.centery
                        ex, ey = dst_rect.centerx, dst_rect.centery
                        pe = p * p * p
                        cx = sx + (ex - sx) * pe
                        cy = sy + (ey - sy) * pe
                        # Render a temp enemy card for the goblin and spin it
                        w, h = src_rect.width, src_rect.height
                        temp = pygame.Surface((w, h), pygame.SRCALPHA)
                        pygame.draw.rect(temp, (20, 20, 28), temp.get_rect())
                        pygame.draw.rect(temp, YELLOW, temp.get_rect(), 2)
                        name = b.enemies[gix].name[:14] if (0 <= gix < len(b.enemies)) else 'Goblin'
                        temp.blit(self.r.font.render(name, True, YELLOW), (8, 6))
                        hp_txt = max(0, int(act.get('dmg', 1)))
                        temp.blit(self.r.font_small.render(f"HP {hp_txt:>2}", True, WHITE), (8, 26))
                        spin = (now / 500.0) % (2 * math.pi)
                        ang = spin * 360.0 / (2 * math.pi) * 2.0
                        rot = pygame.transform.rotate(temp, ang)
                        rrect = rot.get_rect(center=(int(cx), int(cy)))
                        view.blit(rot, rrect.topleft)
            elif act.get('type') == 'censor_mana_burn' and act.get('actor_side') == 'enemy':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 2:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))

                    # Primary target burst (full size)
                    gi = act.get('target_index')
                    primary_rect = party_rects.get(gi)
                    render_purple_burst(primary_rect, p, 1.0, (190, 120, 255))

                    splash_list = act.get('splash', []) or []
                    for entry in splash_list:
                        s_gi = int(entry.get('gi', -1))
                        splash_rect = party_rects.get(s_gi)
                        render_purple_burst(splash_rect, p, 0.5, (160, 110, 230))
            elif act.get('type') == 'spell' and act.get('actor_side') == 'enemy' and act.get('spell_id') == 'mana_surge':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 2:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = 0.0
                    if dur > 0:
                        p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    gi = act.get('target_index')
                    primary_rect = party_rects.get(gi)
                    render_purple_burst(primary_rect, p, 1.0, (190, 120, 255))
                    splash_list = act.get('splash', []) or []
                    for entry in splash_list:
                        s_gi = int(entry.get('gi', -1))
                        splash_rect = party_rects.get(s_gi)
                        render_purple_burst(splash_rect, p, 0.5, (160, 110, 230))
            # Backstab fade effect: fade out then fade in near target during pre stage
            if act.get('type') == 'backstab' and act.get('actor_side') == 'party':
                stage = b.anim.get('stage', 0)
                durs = b.anim.get('dur', [0, 0, 0, 0])
                if len(durs) >= 4 and stage == 1:
                    now = pygame.time.get_ticks()
                    t0 = b.anim.get('t0', now)
                    dur = durs[stage] if stage < len(durs) else 1
                    p = max(0.0, min(1.0, (now - t0) / float(dur)))
                    ai = act.get('actor_index')
                    rect = party_rects.get(ai)
                    if rect:
                        # first half: fade out, second half: fade in
                        if p < 0.5:
                            a = int(255 * (p / 0.5))
                        else:
                            a = int(255 * (1.0 - (p - 0.5) / 0.5))
                        cover = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                        cover.fill((20, 20, 28, a))
                        view.blit(cover, (rect.x, rect.y))
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

        if censor_fx_draw:
            bg_alpha = censor_fx_draw.get('bg_alpha', 0)
            if bg_alpha > 0:
                gray = pygame.Surface((WIDTH, VIEW_H), pygame.SRCALPHA)
                gray.fill((60, 60, 60, bg_alpha))
                view.blit(gray, (0, 0))
            surf = censor_fx_draw.get('surface')
            if surf is not None:
                enemy_index = censor_fx_draw.get('enemy_index')
                src_rect = enemy_rects.get(enemy_index) if (enemy_index is not None) else None
                if src_rect:
                    start_c = (src_rect.centerx, src_rect.centery)
                else:
                    start_c = (WIDTH // 2, 60)
                end_c = (WIDTH // 2, VIEW_H // 2)
                travel_p = max(0.0, min(1.0, censor_fx_draw.get('travel_p', 1.0)))
                cx = int(start_c[0] + (end_c[0] - start_c[0]) * travel_p)
                cy = int(start_c[1] + (end_c[1] - start_c[1]) * travel_p)
                base_w = max(1, surf.get_width())
                base_h = max(1, surf.get_height())
                start_w = 140
                end_w = int(WIDTH * 1.05)
                size_p = max(0.0, min(1.0, censor_fx_draw.get('size_p', 1.0)))
                cur_w = max(1, int(start_w + (end_w - start_w) * size_p))
                scale = cur_w / float(base_w)
                cur_h = max(1, int(base_h * scale))
                scaled = pygame.transform.smoothscale(surf, (cur_w, cur_h)) if cur_w != base_w else surf
                if scaled is surf:
                    scaled = surf.copy()
                scaled.set_alpha(censor_fx_draw.get('text_alpha', 255))
                view.blit(scaled, (cx - cur_w // 2, cy - cur_h // 2))

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
        # Ripple rings removed per request — keep background bands only

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
        pad_x, pad_y = 16, 14
        title = "Victory!"
        text_h = self.r.font.get_height()
        # Spacing for rows and bars
        name_gap = 6      # space between name and bar
        row_gap = 14      # extra space between character rows
        bar_h = 10        # bar height
        row_h = text_h + name_gap + bar_h + row_gap
        title_gap = 18    # extra space between title and first character row
        # Compute panel size to fit member rows + gold/loot lines
        rows = max(1, len(self.party.members))
        panel_w = WIDTH * 2 // 3
        panel_h = pad_y * 2 + text_h + title_gap + rows * row_h + text_h * 2
        w = min(WIDTH - 80, panel_w)
        h = min(VIEW_H - 60, panel_h)
        x = WIDTH // 2 - w // 2
        y = VIEW_H // 2 - h // 2
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(view, (16, 24, 16), rect)
        pygame.draw.rect(view, YELLOW, rect, 2)
        self.r.text_big(view, title, (x + pad_x, y + pad_y), YELLOW)

        # Bars setup
        bar_x = x + pad_x
        cy = y + pad_y + text_h + title_gap
        bar_w = w - pad_x * 2
        awards = self.victory_info.get('awards', {}) or {}
        before = self.victory_info.get('before', {}) or {}
        after = self.victory_info.get('after', {}) or {}
        # Animate bars from before -> after
        now = pygame.time.get_ticks()
        t0 = getattr(self, 'victory_anim_t0', now)
        dur = max(1, int(getattr(self, 'victory_anim_dur', 1200)))
        p = max(0.0, min(1.0, (now - t0) / float(dur)))
        all_done = True
        for gi, m in enumerate(self.party.members):
            # Name
            self.r.text(view, m.name, (bar_x, cy - 2))
            # Determine exp values
            b = int(before.get(gi, m.exp))  # fallback to current if not recorded
            a = int(after.get(gi, m.exp))
            cur = int(round(b + (a - b) * p))
            if cur < a:
                all_done = False
            # Draw bar background
            by = cy + text_h + name_gap
            bg_rect = pygame.Rect(bar_x, by, bar_w, bar_h)
            pygame.draw.rect(view, (22, 30, 22), bg_rect)
            pygame.draw.rect(view, (60, 80, 60), bg_rect, 1)
            # Fill percentage
            frac = max(0.0, min(1.0, cur / 100.0))
            fill_w = int(bar_w * frac)
            if fill_w > 0:
                color = (220, 200, 80)
                # Flash if full
                if a >= 100 and cur >= 100:
                    if (now // 120) % 2 == 0:
                        color = (255, 255, 255)
                pygame.draw.rect(view, color, (bar_x, by, fill_w, bar_h))
            # No numeric labels on EXP bars per request
            cy += row_h

        self.victory_done = all_done
        # Footer: gold and loot
        gold = int(self.victory_info.get('gold', 0))
        loot = self.victory_info.get('loot', {}) or {}
        # Ensure footer text fits inside panel width; truncate with ellipsis if needed
        def fit_text(s: str, max_w: int) -> str:
            try:
                # fast path
                if self.r.font_small.size(s)[0] <= max_w:
                    return s
            except Exception:
                return s
            ell = "…"
            # binary chop length
            lo, hi = 0, len(s)
            best = ""
            while lo <= hi:
                mid = (lo + hi) // 2
                cand = s[:mid] + ell
                try:
                    wtest = self.r.font_small.size(cand)[0]
                except Exception:
                    wtest = 0
                if wtest <= max_w:
                    best = cand; lo = mid + 1
                else:
                    hi = mid - 1
            return best or s[:max(0, len(s)-1)]

        footer_y = y + h - pad_y - text_h
        gold_line = f"Gold found: {gold}g"
        max_line_w = w - pad_x * 2
        gold_line = fit_text(gold_line, max_line_w)
        self.r.text_small(view, gold_line, (x + pad_x, footer_y))
        # Optionally draw loot on a separate clipped line above gold to keep gold visible
        if loot:
            parts = []
            for iid, cnt in loot.items():
                name = self.items_by_id.get(iid, {}).get('name', iid)
                parts.append(f"{name} x{cnt}")
            loot_line = "Items: " + ", ".join(parts)
            loot_line = fit_text(loot_line, max_line_w)
            self.r.text_small(view, loot_line, (x + pad_x, footer_y - text_h - 4))
        # No explicit continue prompt; any key still returns to the labyrinth

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
        # Trait selection animation/update is self-contained and blocks other updates
        if self.mode == MODE_TRAIT:
            try:
                self.update_trait()
            except Exception:
                pass
            return
        if self.mode == MODE_PROLOGUE:
            try:
                self.update_prologue()
            except Exception:
                pass
            return
        if self.mode == MODE_ENDING_TRANSITION:
            try:
                self.update_end_transition()
            except Exception:
                pass
            return
        if self.mode == MODE_ENDING:
            try:
                self.update_ending()
            except Exception:
                pass
            return
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
                # Move elites one step after player steps
                try:
                    self._move_elites_after_player()
                except Exception:
                    pass
                # Status ticks per step for party (poison/bleed/regen)
                try:
                    for gi, m in enumerate(self.party.members):
                        if not (m.alive and m.hp > 0):
                            continue
                        # Poison tick and possible expiry
                        p_stacks = int(m.statuses.get('poison', 0))
                        if p_stacks > 0:
                            m.hp = max(0, m.hp - p_stacks)
                            newp = p_stacks - 1
                            if newp > 0:
                                m.statuses['poison'] = newp
                            else:
                                m.statuses.pop('poison', None)
                                self.log.add(f"Poison on {m.name} expires.")
                        # Bleed tick (no expiry here)
                        if int(m.statuses.get('bleed', 0)) > 0:
                            m.hp = max(0, m.hp - 1)
                        # Regen tick and possible expiry
                        r = int(m.statuses.get('regen', 0))
                        if r > 0:
                            m.hp = min(m.max_hp, m.hp + r)
                            newr = r - 1
                            if newr > 0:
                                m.statuses['regen'] = newr
                            else:
                                m.statuses.pop('regen', None)
                                self.log.add(f"Regen on {m.name} expires.")
                except Exception:
                    pass
                # Treasure chest pickup (step onto a chest tile)
                try:
                    lvl = self.dun.levels[self.level_ix]
                    if hasattr(lvl, 'chests') and isinstance(lvl.chests, list):
                        cx, cy = self.pos
                        idx = None
                        for i, c in enumerate(lvl.chests):
                            if int(c.get('x', -1)) == cx and int(c.get('y', -1)) == cy:
                                idx = i; break
                        if idx is not None:
                            chest = lvl.chests.pop(idx)
                            iid = str(chest.get('iid'))
                            it = ITEMS_BY_ID.get(iid, {'name': iid})
                            self.party.inventory.append(iid)
                            # Persist remaining chests for this level
                            self.chests_state[self.level_ix] = list(lvl.chests)
                            # Popup
                            self.treasure_item_name = it.get('name', iid)
                            self.treasure_popup_active = True
                            self.treasure_t0 = pygame.time.get_ticks()
                except Exception:
                    pass
                # NPC interaction when stepping onto an NPC node
                try:
                    lvl = self.dun.levels[self.level_ix]
                    if hasattr(lvl, 'npcs') and isinstance(lvl.npcs, list):
                        cx, cy = self.pos
                        node = next((n for n in lvl.npcs if int(n.get('x', -1)) == cx and int(n.get('y', -1)) == cy), None)
                        if node:
                            self.start_dialog(str(node.get('id', '')))
                            return
                except Exception:
                    pass
                # Threat mechanic: increase per step based on party level vs floor, then maybe trigger
                if self.mode == MODE_MAZE and not special:
                    # Determine scaling based on average party level relative to floor number (level index)
                    try:
                        avg_lvl = self.party_average_level()
                    except Exception:
                        avg_lvl = 1.0
                    # Floors are 1-based for scaling: level 0 => floor 1
                    floor_num = int(self.level_ix) + 1
                    diff = avg_lvl - floor_num
                    # Compute per-step increment
                    if diff <= 0:
                        inc = int(self.threat_step_inc)
                        encounters_disabled = False
                    elif 0 < diff < 2:
                        inc = max(0, int(self.threat_step_inc // 2))
                        encounters_disabled = False
                    else:
                        inc = 0
                        encounters_disabled = True
                    # Apply increment
                    try:
                        prev = self.threat
                        self.threat = min(self.threat_max, self.threat + inc)
                    except Exception:
                        pass
                    # If encounters are disabled at this floor, skip triggering entirely
                    if encounters_disabled:
                        self.threat_full_steps = 0
                    else:
                        if self.threat >= self.threat_max:
                            # trigger a brief red flash each step while full
                            try:
                                self.trigger_threat_flash()
                            except Exception:
                                pass
                            if self.threat_full_steps == 0:
                                # First time reaching full (or first step while full): do not trigger yet
                                self.threat_full_steps = 1
                            else:
                                # Already spent at least 1 step while full — 50% chance to trigger now
                                if random.random() < 0.5:
                                    self.start_battle()
                                    self.threat = 0
                                    self.threat_full_steps = 0
                        else:
                            # Not full: reset full-steps tracker
                            self.threat_full_steps = 0
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
                    # Capture victory results for display (per-character EXP awards were computed in battle)
                    gold = getattr(self.in_battle, 'victory_gold', 0)
                    loot = getattr(self.in_battle, 'victory_loot', {}) or {}
                    self.victory_info = {
                        'gold': gold,
                        'loot': loot,
                        'awards': getattr(self.in_battle, 'victory_exp_awards', {}),
                        'before': getattr(self.in_battle, 'victory_exp_before', {}),
                        'after': getattr(self.in_battle, 'victory_exp_after', {}),
                    }
                    # Reset threat after combat
                    self.threat = 0
                    self.threat_full_steps = 0
                    # Init bar animation
                    self.victory_anim_t0 = pygame.time.get_ticks()
                    self.victory_anim_dur = 1200
                    self.victory_done = False
                    # If this was an elite battle, remove the elite node and persist
                    if self.elite_battle_ctx:
                        try:
                            lvl_ix = int(self.elite_battle_ctx.get('level', self.level_ix))
                            idx = int(self.elite_battle_ctx.get('index', -1))
                            lvl = self.dun.levels[lvl_ix]
                            if 0 <= idx < len(lvl.elites):
                                lvl.elites.pop(idx)
                                # Persist current elites for this level
                                self.elites_state[lvl_ix] = list(lvl.elites)
                        except Exception:
                            pass
                        self.elite_battle_ctx = None
                    self.mode = MODE_VICTORY
                elif self.in_battle.result == 'fled':
                    # Reset threat after combat
                    self.threat = 0
                    self.threat_full_steps = 0
                    # If flee from elite, bounce player away one cell from elite node
                    if self.elite_battle_ctx:
                        try:
                            ex, ey = self.elite_battle_ctx.get('pos', (self.pos[0], self.pos[1]))
                            px, py = self.pos
                            dx = px - ex; dy = py - ey
                            if abs(dx) >= abs(dy):
                                step = (1 if dx >= 0 else -1, 0)
                            else:
                                step = (0, 1 if dy >= 0 else -1)
                            nx, ny = px + step[0], py + step[1]
                            if self.in_bounds(nx, ny) and self.is_open(nx, ny):
                                self.pos = (nx, ny)
                        except Exception:
                            pass
                        self.elite_battle_ctx = None
                    self.mode = MODE_MAZE
                else:
                    # defeat: also reset threat (new run starts safe)
                    self.threat = 0
                    self.threat_full_steps = 0
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
                    # Ignore inputs during save/load overlays
                    if getattr(self, 'save_feedback_active', False) or getattr(self, 'load_feedback_active', False):
                        continue
                    if self.mode == MODE_TITLE:
                        self.title_input(event)
                    elif self.mode == MODE_PROLOGUE:
                        self.prologue_input(event)
                    elif self.mode == MODE_ENDING_TRANSITION:
                        pass
                    elif self.mode == MODE_ENDING:
                        self.ending_input(event)
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
                    elif self.mode == MODE_WAYPOINT:
                        self.waypoint_input(event)
                    elif self.mode == MODE_DEFEAT:
                        self.defeat_input(event)
                    elif self.mode == MODE_VICTORY:
                        self.victory_input(event)
                    elif self.mode == MODE_BATTLE:
                        self.battle_input(event)
                    elif self.mode == MODE_DIALOG:
                        self.dialog_input(event)
                    elif self.mode == MODE_QUESTS:
                        self.quests_input(event)
                    elif self.mode == MODE_TRAIT:
                        self.trait_input(event)

            self.update()

            # Detect and react to mode changes for music control
            if self._last_mode != self.mode:
                self.on_mode_changed(self._last_mode, self.mode)
                self._last_mode = self.mode

            if self.mode == MODE_TITLE:
                # Title renders fullscreen and hides log
                self.draw_title()
            elif self.mode == MODE_PROLOGUE:
                self.draw_prologue()
            elif self.mode == MODE_ENDING:
                self.draw_ending()
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
                elif self.mode == MODE_ENDING_TRANSITION:
                    self.draw_maze()
                    self.draw_end_transition()
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
                elif self.mode == MODE_WAYPOINT:
                    self.draw_waypoint_select()
                elif self.mode == MODE_DEFEAT:
                    self.draw_defeat()
                elif self.mode == MODE_VICTORY:
                    self.draw_victory()
                elif self.mode == MODE_BATTLE:
                    self.draw_battle()
                elif self.mode == MODE_DIALOG:
                    self.draw_dialog()
                elif self.mode == MODE_QUESTS:
                    self.draw_quests()
                elif self.mode == MODE_TRAIT:
                    self.draw_trait()

                # Overlays that can appear on top
                self.draw_save_feedback()
                self.draw_load_feedback()
                # Draw message log for non-title scenes (with typewriter effect)
                self.r.draw_log(self.log.render_lines())
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
