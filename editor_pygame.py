#!/usr/bin/env python3
import os, sys, json
import random
from typing import List, Dict, Any, Optional, Tuple, Set

import pygame

# Tile constants (match main.py)
T_EMPTY, T_WALL, T_TOWN, T_STAIRS_D, T_STAIRS_U, T_LOCKED, T_END = 0, 1, 2, 3, 4, 5, 6
TOOL_CHEST = 7  # editor-only tool id for chests
TOOL_NPC = 8    # editor-only tool id for NPCs
TOOL_ELITE = 9  # editor-only tool id for Elite nodes

DATA_DIR = 'data'
LEVEL_DIR = os.path.join(DATA_DIR, 'levels')
DEFAULT_W, DEFAULT_H = 24, 24
W, H = DEFAULT_W, DEFAULT_H
TILE = 20
MARGIN = 10
PALETTE_W = 260
def window_dims():
    return (MARGIN * 2 + W * TILE + PALETTE_W, MARGIN * 2 + H * TILE)

WHITE = (240, 240, 240)
GRAY = (140, 140, 140)
DARK = (24, 24, 28)
BG = (18, 18, 24)
YELLOW = (240, 220, 80)
RED = (220, 80, 80)
GREEN = (90, 200, 120)
BLUE = (80, 160, 240)

def base_grid() -> List[List[int]]:
    g = [[T_WALL] * W for _ in range(H)]
    for y in range(1, H-1):
        for x in range(1, W-1):
            g[y][x] = T_EMPTY
    return g

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def pick_item_for_floor(editor: 'Editor') -> str:
    floor_level = max(1, int(getattr(editor.doc, 'index', 0)) + 1)
    suitable: List[str] = []
    higher: List[Tuple[int, str]] = []
    for item in getattr(editor, 'items', []) or []:
        if not isinstance(item, dict):
            continue
        iid = item.get('id')
        if not iid:
            continue
        req = item.get('req')
        req_level = 0
        if isinstance(req, dict):
            lvl = req.get('level')
            if isinstance(lvl, (int, float)):
                req_level = int(lvl)
        if req_level <= floor_level:
            suitable.append(str(iid))
        else:
            higher.append((req_level, str(iid)))
    if suitable:
        return random.choice(suitable)
    if higher:
        higher.sort(key=lambda tpl: tpl[0])
        return higher[0][1]
    return 'potion_small'

class LevelDoc:
    def __init__(self, index: int):
        self.index = index
        self.path = os.path.join(LEVEL_DIR, f'level{index}.json')
        self.data: Dict[str, Any] = {}
        self.grid: List[List[int]] = base_grid()
        self.stairs_down: Optional[Tuple[int, int]] = None
        self.stairs_up: Optional[Tuple[int, int]] = None
        self.town_portal: Optional[Tuple[int, int]] = (2, 2) if index == 0 else None
        self.encounters: Dict[str, Any] = {"monsters": [], "group": [1, 3]}
        self.chests: List[Dict[str, Any]] = []
        self.npcs: List[Dict[str, Any]] = []
        self.elites: List[Dict[str, Any]] = []
        self.end_node: Optional[Tuple[int, int]] = None
        self.quest_id: Optional[str] = None
        self.stairs_down_target: Optional[Tuple[int, int, int]] = None  # (level_index, x, y)
        self.size: Tuple[int, int] = (W, H)
        self.load()

    def _ensure_grid_capacity(self, min_w: int, min_h: int):
        cur_h = len(self.grid)
        cur_w = len(self.grid[0]) if self.grid else 0
        if min_w <= cur_w and min_h <= cur_h:
            return
        new_w = max(cur_w, min_w)
        new_h = max(cur_h, min_h)
        for row in self.grid:
            if len(row) < new_w:
                row.extend([T_WALL] * (new_w - len(row)))
        while len(self.grid) < new_h:
            self.grid.append([T_WALL] * new_w)
        global W, H
        W, H = new_w, new_h
        self.size = (new_w, new_h)

    def load(self):
        self.data = load_json(self.path, {})
        # Load size first (preserve editor canvas size)
        sz = self.data.get('size')
        if isinstance(sz, list) and len(sz) == 2:
            try:
                nw, nh = int(sz[0]), int(sz[1])
                nw = max(8, min(64, nw)); nh = max(8, min(64, nh))
                self.size = (nw, nh)
                # update globals for base_grid/grid operations
                global W, H
                W, H = nw, nh
            except Exception:
                pass
        g = self.data.get('grid')
        if isinstance(g, list) and g and isinstance(g[0], list):
            # size adjust
            self.grid = base_grid()
            for y in range(min(H, len(g))):
                for x in range(min(W, len(g[0]))):
                    try:
                        self.grid[y][x] = int(g[y][x])
                    except Exception:
                        pass
        else:
            self.grid = base_grid()
        sd = self.data.get('stairs_down'); su = self.data.get('stairs_up'); tp = self.data.get('town_portal')
        self.stairs_down = tuple(sd) if isinstance(sd, list) and len(sd)==2 else None
        self.stairs_up = tuple(su) if isinstance(su, list) and len(su)==2 else None
        self.town_portal = tuple(tp) if isinstance(tp, list) and len(tp)==2 else (self.town_portal if self.index==0 else None)
        sdt = self.data.get('stairs_down_target')
        if isinstance(sdt, list) and len(sdt) == 3:
            try:
                tgt_level = int(sdt[0]); tx = int(sdt[1]); ty = int(sdt[2])
                self.stairs_down_target = (tgt_level, tx, ty)
            except Exception:
                self.stairs_down_target = None
        else:
            self.stairs_down_target = None
        self.encounters = self.data.get('encounters', self.encounters)
        # Load chests
        ch = self.data.get('chests', [])
        if isinstance(ch, list):
            self.chests = []
            for c in ch:
                try:
                    x = int(c.get('x')); y = int(c.get('y')); iid = str(c.get('iid'))
                    self.chests.append({'x': x, 'y': y, 'iid': iid})
                except Exception:
                    continue

        # Load NPCs
        npcs = self.data.get('npcs', [])
        if isinstance(npcs, list):
            self.npcs = []
            for n in npcs:
                try:
                    x = int(n.get('x')); y = int(n.get('y')); nid = str(n.get('id'))
                    self.npcs.append({'x': x, 'y': y, 'id': nid})
                except Exception:
                    continue

        # Load NPCs
        npcs = self.data.get('npcs', [])
        if isinstance(npcs, list):
            self.npcs = []
            for n in npcs:
                try:
                    x = int(n.get('x')); y = int(n.get('y')); nid = str(n.get('id'))
                    self.npcs.append({'x': x, 'y': y, 'id': nid})
                except Exception:
                    continue

        # Load elites
        elites = self.data.get('elites', [])
        if isinstance(elites, list):
            self.elites = []
            for e in elites:
                try:
                    x = int(e.get('x')); y = int(e.get('y'))
                    mid = str(e.get('id'))
                    pat = str(e.get('pattern', 'up_down'))
                    self.elites.append({'x': x, 'y': y, 'id': mid, 'pattern': pat})
                except Exception:
                    continue

        end_node = self.data.get('end_node')
        if isinstance(end_node, list) and len(end_node) == 2:
            try:
                ex, ey = int(end_node[0]), int(end_node[1])
                self.end_node = (ex, ey)
            except Exception:
                self.end_node = None
        else:
            self.end_node = None
        self.quest_id = self.data.get('quest_id')

        # ensure markers reflected in grid
        if self.town_portal:
            x,y = self.town_portal
            if x < 0 or y < 0:
                self.town_portal = None
            else:
                if y >= len(self.grid) or x >= len(self.grid[0]):
                    self._ensure_grid_capacity(x+1, y+1)
                if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
                    self.grid[y][x] = T_TOWN
        if self.stairs_down:
            x,y = self.stairs_down
            if x < 0 or y < 0:
                self.stairs_down = None
            else:
                if y >= len(self.grid) or x >= len(self.grid[0]):
                    self._ensure_grid_capacity(x+1, y+1)
                if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
                    self.grid[y][x] = T_STAIRS_D
        if self.stairs_up:
            x,y = self.stairs_up
            if x < 0 or y < 0:
                self.stairs_up = None
            else:
                if y >= len(self.grid) or x >= len(self.grid[0]):
                    self._ensure_grid_capacity(x+1, y+1)
                if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
                    self.grid[y][x] = T_STAIRS_U
        if self.end_node:
            x, y = self.end_node
            if x < 0 or y < 0:
                self.end_node = None
            else:
                if y >= len(self.grid) or x >= len(self.grid[0]):
                    self._ensure_grid_capacity(x+1, y+1)
                if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
                    self.grid[y][x] = T_END

    def save(self):
        d: Dict[str, Any] = {
            'grid': self.grid,
            'encounters': self.encounters,
            'size': [W, H],
        }
        if self.chests:
            d['chests'] = list(self.chests)
        if self.npcs:
            d['npcs'] = list(self.npcs)
        if self.elites:
            d['elites'] = list(self.elites)
        if self.stairs_down: d['stairs_down'] = list(self.stairs_down)
        if self.stairs_up: d['stairs_up'] = list(self.stairs_up)
        if self.index == 0 and self.town_portal:
            d['town_portal'] = list(self.town_portal)
        if self.stairs_down_target:
            d['stairs_down_target'] = list(self.stairs_down_target)
        if self.end_node:
            d['end_node'] = list(self.end_node)
        if self.quest_id:
            d['quest_id'] = self.quest_id
        save_json(self.path, d)

class Editor:
    def __init__(self, level_index: int = 0):
        pygame.init()
        pygame.display.set_caption('Level Editor (Pygame)')
        self.screen = pygame.display.set_mode(window_dims())
        self.font = pygame.font.SysFont(None, 18)
        self.font_small = pygame.font.SysFont(None, 14)
        os.makedirs(LEVEL_DIR, exist_ok=True)
        self.doc = LevelDoc(level_index)
        # Ensure window reflects loaded size
        self.screen = pygame.display.set_mode(window_dims())
        self.running = True
        self.tool = T_WALL  # default draw tool
        self.status = ''
        self.input_active = False
        self.input_prompt = ''
        self.input_text = ''
        self.input_mode = 'text'  # 'text' or 'monster'
        self.input_suggestions: List[Tuple[str, str]] = []  # (id, display)
        self.suggestion_index: int = -1
        self.suggestion_rects: List[pygame.Rect] = []
        # UI state
        self.tool_rects: List[Tuple[pygame.Rect, int]] = []
        self.btn_file_rect = pygame.Rect(0,0,0,0)
        self.btn_enc_rect = pygame.Rect(0,0,0,0)
        self.btn_gen_rect = pygame.Rect(0,0,0,0)
        self.file_menu = False
        self.enc_menu = False
        self.gen_menu = False
        self.file_opt_rects: List[Tuple[pygame.Rect, str]] = []
        self.enc_opt_rects: List[Tuple[pygame.Rect, str]] = []
        self.enc_btn_rects: List[Tuple[pygame.Rect, str]] = []
        self.gen_opt_rects: List[Tuple[pygame.Rect, str]] = []
        # Monsters list for encounters UI
        self.monsters: List[Dict[str, Any]] = load_json(os.path.join(DATA_DIR, 'monsters.json'), [])
        # Items list for chest assignment UI
        self.items: List[Dict[str, Any]] = load_json(os.path.join(DATA_DIR, 'items.json'), [])
        # NPC and quest definitions for higher-level features
        self.npc_defs: List[Dict[str, Any]] = load_json(os.path.join(DATA_DIR, 'npcs.json'), [])
        self.quests: List[Dict[str, Any]] = load_json(os.path.join(DATA_DIR, 'quests.json'), [])

    def grid_pos_from_mouse(self, mx, my):
        gx = (mx - MARGIN) // TILE
        gy = (my - MARGIN) // TILE
        if 0 <= gx < W and 0 <= gy < H:
            return int(gx), int(gy)
        return None

    def set_tile(self, x, y, t):
        prev = self.doc.grid[y][x]
        self.doc.grid[y][x] = t
        # Update markers
        if t == T_STAIRS_D:
            self.doc.stairs_down = (x, y)
            self.doc.stairs_down_target = None
        elif prev == T_STAIRS_D and self.doc.stairs_down == (x, y):
            self.doc.stairs_down = None
            self.doc.stairs_down_target = None
        if t == T_STAIRS_U:
            self.doc.stairs_up = (x, y)
        elif prev == T_STAIRS_U and self.doc.stairs_up == (x, y):
            self.doc.stairs_up = None
        if t == T_TOWN:
            if self.doc.index != 0:
                self.status = 'Town only allowed on level 0'
            else:
                self.doc.town_portal = (x, y)
        elif prev == T_TOWN and self.doc.town_portal == (x, y):
            self.doc.town_portal = None
        if t == T_END:
            prev_end = getattr(self.doc, 'end_node', None)
            if prev_end and prev_end != (x, y):
                px, py = prev_end
                if 0 <= py < len(self.doc.grid) and 0 <= px < len(self.doc.grid[0]):
                    self.doc.grid[py][px] = T_EMPTY
            self.doc.end_node = (x, y)
        elif prev == T_END and getattr(self.doc, 'end_node', None) == (x, y):
            self.doc.end_node = None

    def prompt_input(self, prompt_text: str, initial_text: str = ''):
        self.input_active = True
        self.input_prompt = prompt_text
        self.input_text = initial_text or ''

    def handle_link_stairs_down(self, x, y):
        # prompt for target level index and target pos
        global W, H
        existing = getattr(self.doc, 'stairs_down_target', None)
        initial_level = ''
        initial_pos = ''
        if existing:
            try:
                lvl, px, py = existing
                initial_level = str(lvl)
                initial_pos = f"{px},{py}"
            except Exception:
                pass
        self.prompt_input('Target level index:', initial_level)
        target_level = self.read_blocking_input()
        if target_level is None: return
        try:
            tgt_ix = int(target_level)
        except:
            self.status = 'Invalid level index'
            return
        self.prompt_input('Target position x,y:', initial_pos)
        pos_str = self.read_blocking_input()
        if pos_str is None: return
        try:
            tx, ty = map(int, pos_str.replace(' ', '').split(','))
        except:
            self.status = 'Invalid position'
            return
        # Ensure target level exists and has an upstairs backlink
        tgt_path = os.path.join(LEVEL_DIR, f'level{tgt_ix}.json')
        # Preserve current editor canvas size while we touch the target level
        prev_size = (W, H)
        tgt = LevelDoc(tgt_ix)
        if 0 <= ty < len(tgt.grid) and 0 <= tx < len(tgt.grid[0]):
            tgt.grid[ty][tx] = T_STAIRS_U
            tgt.stairs_up = (tx, ty)
        else:
            # Expand target grid (and size metadata) so the new stairs fits
            new_h = max(len(tgt.grid), ty + 1)
            new_w = max(len(tgt.grid[0]), tx + 1)
            for row in tgt.grid:
                row.extend([T_WALL] * (new_w - len(row)))
            while len(tgt.grid) < new_h:
                tgt.grid.append([T_WALL] * new_w)
            tgt.grid[ty][tx] = T_STAIRS_U
            tgt.stairs_up = (tx, ty)
            tgt.size = (new_w, new_h)
        tgt.save()
        # Restore the original dimensions for the current document
        W, H = prev_size
        # Set current stairs down and save
        self.doc.grid[y][x] = T_STAIRS_D
        self.doc.stairs_down = (x, y)
        self.doc.stairs_down_target = (tgt_ix, tx, ty)
        self.doc.save()
        self.status = f'Linked down to level {tgt_ix} at {tx},{ty}'

    def handle_adjust_stairs_up(self, x, y):
        global W, H
        if self.doc.index <= 0:
            self.status = 'No previous level to update'
            return
        prev_ix = self.doc.index - 1
        prev_size = (W, H)
        prev = LevelDoc(prev_ix)
        target = getattr(prev, 'stairs_down_target', None)
        if target and isinstance(target, (list, tuple)) and len(target) == 3 and target[0] == self.doc.index:
            prev.stairs_down_target = (self.doc.index, x, y)
        elif not target or not isinstance(target, (list, tuple)) or len(target) != 3 or target[0] in (None, -1):
            if getattr(prev, 'stairs_down', None):
                prev.stairs_down_target = (self.doc.index, x, y)
            else:
                self.status = 'Previous level has stairs-up but no stairs-down to link'
                return
        else:
            self.status = 'Previous level targets a different floor; adjust manually'
            return
        prev.save()
        # restore current grid dimensions
        W, H = prev_size
        self.doc.grid[y][x] = T_STAIRS_U
        self.doc.stairs_up = (x, y)
        self.doc.save()
        self.status = f'Updated level {prev_ix} stairs-down target to {x},{y}'

    def draw(self):
        self.screen.fill(BG)
        # Grid
        ox, oy = MARGIN, MARGIN
        grid_w, grid_h = (W * TILE, H * TILE)
        for y in range(H):
            for x in range(W):
                r = pygame.Rect(ox + x*TILE, oy + y*TILE, TILE-1, TILE-1)
                t = self.doc.grid[y][x]
                if t == T_WALL:
                    pygame.draw.rect(self.screen, GRAY, r)
                elif t == T_EMPTY:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                elif t == T_TOWN:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                    pygame.draw.circle(self.screen, BLUE, r.center, max(3, TILE//4))
                elif t == T_STAIRS_D:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                    pygame.draw.polygon(self.screen, YELLOW, [(r.left+3, r.top+3), (r.right-3, r.top+3), (r.centerx, r.bottom-3)])
                elif t == T_STAIRS_U:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                    pygame.draw.polygon(self.screen, GREEN, [(r.left+3, r.bottom-3), (r.right-3, r.bottom-3), (r.centerx, r.top+3)])
                elif t == T_LOCKED:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                    # draw door bar
                    bar = r.inflate(-2, -TILE//2)
                    bar.centery = r.centery
                    pygame.draw.rect(self.screen, (36, 28, 22), bar)
                    pygame.draw.rect(self.screen, (120, 100, 60), bar, 1)
                    # small lock
                    lock = pygame.Rect(0,0, 8,8)
                    lock.center = (r.centerx, r.centery)
                    pygame.draw.rect(self.screen, (200,180,90), lock, 1)
                elif t == T_END:
                    pygame.draw.rect(self.screen, (30,30,34), r)
                    center = r.center
                    pygame.draw.circle(self.screen, (200, 160, 255), center, max(3, TILE//4))
                    pygame.draw.circle(self.screen, (150, 90, 220), center, max(4, TILE//3), 2)
        # Draw chests as overlays
        for c in self.doc.chests:
            x, y = int(c.get('x', -1)), int(c.get('y', -1))
            if 0 <= x < W and 0 <= y < H:
                r = pygame.Rect(ox + x*TILE, oy + y*TILE, TILE-1, TILE-1)
                cr = r.inflate(-8, -10)
                cr.y = r.y + (TILE//2)
                pygame.draw.rect(self.screen, (140, 100, 40), cr)
                pygame.draw.rect(self.screen, (90, 70, 30), cr, 1)
        # Draw NPCs as cyan dots
        for n in self.doc.npcs:
            x, y = int(n.get('x', -1)), int(n.get('y', -1))
            if 0 <= x < W and 0 <= y < H:
                r = pygame.Rect(ox + x*TILE, oy + y*TILE, TILE-1, TILE-1)
                pygame.draw.circle(self.screen, (60, 200, 200), r.center, max(3, TILE//4))
        # Draw elites as orange diamonds (always on top of tiles)
        for e in getattr(self.doc, 'elites', []) or []:
            try:
                x, y = int(e.get('x', -1)), int(e.get('y', -1))
            except Exception:
                continue
            if 0 <= x < W and 0 <= y < H:
                r = pygame.Rect(ox + x*TILE, oy + y*TILE, TILE-1, TILE-1)
                pts = [
                    (r.centerx, r.top + 4),
                    (r.right - 4, r.centery),
                    (r.centerx, r.bottom - 4),
                    (r.left + 4, r.centery),
                ]
                pygame.draw.polygon(self.screen, (220, 140, 40), pts)
                pygame.draw.polygon(self.screen, (240, 220, 80), pts, 1)
        # Grid border
        pygame.draw.rect(self.screen, YELLOW, (ox-1, oy-1, grid_w+2, grid_h+2), 1)

        # Palette
        px = MARGIN + grid_w + 20
        py = MARGIN
        self.text(f'Level {self.doc.index}', (px, py), YELLOW); py += 22
        # Buttons for File and Encounters
        self.btn_file_rect = pygame.Rect(px, py, 80, 22)
        pygame.draw.rect(self.screen, (40,40,48), self.btn_file_rect)
        pygame.draw.rect(self.screen, YELLOW, self.btn_file_rect, 1)
        self.text_small('File', (px+8, py+4))
        self.btn_enc_rect = pygame.Rect(px+90, py, 120, 22)
        pygame.draw.rect(self.screen, (40,40,48), self.btn_enc_rect)
        pygame.draw.rect(self.screen, YELLOW, self.btn_enc_rect, 1)
        self.text_small('Encounters', (px+98, py+4))
        py += 30
        self.btn_gen_rect = pygame.Rect(px, py, 120, 22)
        pygame.draw.rect(self.screen, (40,40,48), self.btn_gen_rect)
        pygame.draw.rect(self.screen, YELLOW, self.btn_gen_rect, 1)
        self.text_small('Generate', (px+8, py+4))
        py += 30
        self.text_small('S: Save   ,/.: Prev/Next level', (px, py)); py += 18
        self.text_small('0..9: Select tool   R: Reset', (px, py)); py += 18
        self.text_small('Right-click stairs-down: link', (px, py)); py += 18
        py += 6
        tools = [
            (T_EMPTY, 'Empty'),
            (T_WALL, 'Wall'),
            (T_TOWN, 'Town (L0)'),
            (T_STAIRS_D, 'Stairs Down'),
            (T_STAIRS_U, 'Stairs Up'),
            (T_LOCKED, 'Locked Door'),
            (T_END, 'The End Node'),
            (TOOL_CHEST, 'Chest'),
            (TOOL_NPC, 'NPC'),
            (TOOL_ELITE, 'Elite'),
        ]
        self.tool_rects = []
        for tid, label in tools:
            r = pygame.Rect(px, py, 28, 28)
            color = (60,60,80) if self.tool != tid else (100,100,120)
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, YELLOW if self.tool==tid else WHITE, r, 1)
            self.text_small(label, (px+36, py+7))
            # sample tile icon
            if tid == T_WALL:
                pygame.draw.rect(self.screen, GRAY, r.inflate(-6,-6))
            elif tid == T_TOWN:
                pygame.draw.circle(self.screen, BLUE, r.center, 8)
            elif tid == T_STAIRS_D:
                pygame.draw.polygon(self.screen, YELLOW, [(r.left+6, r.top+6), (r.right-6, r.top+6), (r.centerx, r.bottom-6)])
            elif tid == T_STAIRS_U:
                pygame.draw.polygon(self.screen, GREEN, [(r.left+6, r.bottom-6), (r.right-6, r.bottom-6), (r.centerx, r.top+6)])
            elif tid == T_END:
                pygame.draw.circle(self.screen, (200, 160, 255), r.center, 8)
                pygame.draw.circle(self.screen, (150, 90, 220), r.center, 10, 1)
            self.tool_rects.append((r, tid))
            py += 36

        # Status
        win_w, win_h = window_dims()
        self.text_small(self.status, (px, win_h - 22), YELLOW)

        # Input popup
        if self.input_active:
            overlay = pygame.Surface(window_dims(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            box_w, box_h = 480, 120
            rx = win_w//2 - box_w//2; ry = win_h//2 - box_h//2
            rect = pygame.Rect(rx, ry, box_w, box_h)
            pygame.draw.rect(self.screen, (20,20,26), rect)
            pygame.draw.rect(self.screen, YELLOW, rect, 2)
            self.text(self.input_prompt, (rx+16, ry+18))
            self.text(self.input_text + '_', (rx+16, ry+58), YELLOW)
        # If in suggestion modes, show suggestions below
        if self.input_mode in ('monster','elite_monster','item','npc','pattern') and self.input_suggestions:
            sy = ry + 84
            self.suggestion_rects = []
            for i, (_id, disp) in enumerate(self.input_suggestions[:6]):
                r = pygame.Rect(rx+16, sy, box_w-32, 22)
                sel = (i == self.suggestion_index)
                pygame.draw.rect(self.screen, (60,60,80) if sel else (40,40,48), r)
                pygame.draw.rect(self.screen, YELLOW if sel else WHITE, r, 1)
                self.text_small(disp, (r.x+8, r.y+4), YELLOW if sel else WHITE)
                self.suggestion_rects.append(r)
                sy += 24

        # File menu overlay
        if self.file_menu and not self.input_active:
            overlay = pygame.Surface(window_dims(), pygame.SRCALPHA)
            overlay.fill((0,0,0,160)); self.screen.blit(overlay,(0,0))
            box = pygame.Rect(0,0,360,220); win_w,win_h = window_dims(); box.center=(win_w//2, win_h//2)
            pygame.draw.rect(self.screen, (20,20,26), box); pygame.draw.rect(self.screen, YELLOW, box, 2)
            x,y=box.x+16, box.y+16
            self.text('File', (x,y), YELLOW); y+=28
            opts=[('New (clear)','new'), ('Open level...','open'), ('Save','save'), ('Save As...','saveas'), ('Set level size...','size'), ('Close','close')]
            self.file_opt_rects=[]
            for label,_id in opts:
                r=pygame.Rect(x,y, box.w-32, 26)
                pygame.draw.rect(self.screen, (40,40,48), r); pygame.draw.rect(self.screen, WHITE, r,1)
                self.text_small(label, (r.x+8,r.y+6))
                self.file_opt_rects.append((r,_id)); y+=32

        # Encounters overlay
        if self.enc_menu and not self.input_active:
            overlay = pygame.Surface(window_dims(), pygame.SRCALPHA)
            overlay.fill((0,0,0,160)); self.screen.blit(overlay,(0,0))
            box = pygame.Rect(0,0,420,380); win_w,win_h = window_dims(); box.center=(win_w//2, win_h//2)
            pygame.draw.rect(self.screen, (20,20,26), box); pygame.draw.rect(self.screen, YELLOW, box, 2)
            x,y=box.x+16, box.y+16
            self.text('Encounters', (x,y), YELLOW); y+=26
            # Only list monsters currently available on the level
            curr = self.doc.encounters.get('monsters', [])
            id_to_name = {m.get('id'): m.get('name') for m in self.monsters if isinstance(m, dict)}
            self.enc_opt_rects=[]
            self.text_small('Available monsters on this level:', (x, y), WHITE); y += 20
            for mid in curr:
                r=pygame.Rect(x,y, box.w-32, 22)
                pygame.draw.rect(self.screen, (60,60,72), r); pygame.draw.rect(self.screen, WHITE, r,1)
                name = id_to_name.get(mid, mid)
                self.text_small(f"{mid} - {name} (click to remove)", (r.x+8,r.y+4), YELLOW)
                self.enc_opt_rects.append((r, mid)); y+=24
                if y> box.bottom-140: break
            y=box.bottom-100
            g=self.doc.encounters.get('group',[1,3])
            self.text_small(f"Group min: {g[0]}  max: {g[1]}", (x,y), WHITE); y+=24
            btns=[('Min -','min-'),('Min +','min+'),('Max -','max-'),('Max +','max+'),('Add...','add'),('Close','close')]
            self.enc_btn_rects=[]
            bx=x
            for label,_id in btns:
                r=pygame.Rect(bx,y, 74,24)
                pygame.draw.rect(self.screen,(40,40,48), r); pygame.draw.rect(self.screen, WHITE, r,1)
                self.text_small(label,(r.x+6,r.y+4)); self.enc_btn_rects.append((r,_id)); bx+= 78

        # Generate menu overlay
        if self.gen_menu and not self.input_active:
            overlay = pygame.Surface(window_dims(), pygame.SRCALPHA)
            overlay.fill((0,0,0,160)); self.screen.blit(overlay,(0,0))
            box = pygame.Rect(0,0,360,180); win_w,win_h = window_dims(); box.center=(win_w//2, win_h//2)
            pygame.draw.rect(self.screen, (20,20,26), box); pygame.draw.rect(self.screen, YELLOW, box, 2)
            x,y=box.x+16, box.y+16
            self.text('Generate', (x,y), YELLOW); y+=28
            opts=[('Level','level'), ('Treasure','treasure'), ('Theme','theme'), ('Close','close')]
            self.gen_opt_rects=[]
            for label,_id in opts:
                r=pygame.Rect(x,y, box.w-32, 30)
                pygame.draw.rect(self.screen, (40,40,48), r); pygame.draw.rect(self.screen, WHITE, r,1)
                self.text_small(label,(r.x+10,r.y+7)); self.gen_opt_rects.append((r,_id))
                y+= 36

        pygame.display.flip()

    def text(self, s, pos, color=WHITE):
        self.screen.blit(self.font.render(s, True, color), pos)

    def text_small(self, s, pos, color=WHITE):
        self.screen.blit(self.font_small.render(s, True, color), pos)

    def read_blocking_input(self) -> Optional[str]:
        # Runs a small loop to collect text input into self.input_text
        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        return None
                    elif event.key == pygame.K_RETURN:
                        self.input_active = False
                        return self.input_text.strip()
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
            self.draw()
        return None

    def handle_add_monster(self):
        mid = self.read_monster_id_input()
        if mid:
            # Validate against known monsters
            ids = [m.get('id') for m in self.monsters if isinstance(m, dict)]
            if mid not in ids:
                # Try unique prefix resolution
                matches = [i for i in ids if str(i).lower().startswith(mid.lower())]
                if len(matches) == 1:
                    mid = matches[0]
                else:
                    self.status = 'Unknown or ambiguous monster id'
                    return
            mons = self.doc.encounters.get('monsters', [])
            if mid not in mons:
                mons.append(mid)
                self.doc.encounters['monsters'] = mons
                self.status = f'Added monster {mid}'

    def read_monster_id_input(self) -> Optional[str]:
        # Prompt user with tab-completion and selection list
        self.input_active = True
        self.input_prompt = 'Add monster id:'
        self.input_text = ''
        self.input_mode = 'monster'
        self.input_suggestions = []
        self.suggestion_index = -1

        def all_ids():
            return [str(m.get('id')) for m in self.monsters if isinstance(m, dict) and m.get('id')]

        def find_matches(prefix: str) -> List[Tuple[str, str]]:
            ids = all_ids()
            pref = prefix.lower()
            matches = [i for i in ids if i.lower().startswith(pref)] if pref else ids
            # Pair with name for display
            id_to_name = {m.get('id'): m.get('name') for m in self.monsters if isinstance(m, dict)}
            return [(i, f"{i} - {id_to_name.get(i, '')}") for i in matches]

        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.input_mode == 'monster' and self.input_suggestions and event.button == 1:
                        mx, my = event.pos
                        for idx, r in enumerate(self.suggestion_rects):
                            if r.collidepoint(mx, my):
                                sel_id = self.input_suggestions[idx][0]
                                self.input_active = False
                                self.input_mode = 'text'
                                self.input_suggestions = []
                                self.suggestion_index = -1
                                return sel_id
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return None
                    elif event.key == pygame.K_RETURN:
                        text = self.input_text.strip()
                        if self.input_suggestions and 0 <= self.suggestion_index < len(self.input_suggestions):
                            text = self.input_suggestions[self.suggestion_index][0]
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return text if text else None
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                        # Update suggestions if visible
                        if self.input_mode == 'monster':
                            self.input_suggestions = find_matches(self.input_text)
                            self.suggestion_index = 0 if self.input_suggestions else -1
                    elif event.key == pygame.K_TAB:
                        # Show suggestions by prefix
                        matches = find_matches(self.input_text)
                        if len(matches) == 1:
                            self.input_text = matches[0][0]
                            self.input_suggestions = []
                            self.suggestion_index = -1
                        elif len(matches) > 1:
                            self.input_suggestions = matches
                            self.suggestion_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.input_suggestions:
                            if event.key == pygame.K_UP:
                                self.suggestion_index = (self.suggestion_index - 1) % len(self.input_suggestions)
                            else:
                                self.suggestion_index = (self.suggestion_index + 1) % len(self.input_suggestions)
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
                            # If suggestions are currently shown, refresh them
                            if self.input_mode == 'monster':
                                self.input_suggestions = find_matches(self.input_text)
                                self.suggestion_index = 0 if self.input_suggestions else -1
            self.draw()
        return None

    def read_elite_monster_id_input(self, initial: Optional[str] = None) -> Optional[str]:
        # Prompt user with tab-completion and selection list filtered to elite-tier monsters
        self.input_active = True
        self.input_prompt = 'Elite monster id:'
        self.input_text = str(initial) if initial is not None else ''
        self.input_mode = 'elite_monster'
        self.input_suggestions = []
        self.suggestion_index = -1

        def all_elite_ids():
            ids = []
            for m in self.monsters:
                if isinstance(m, dict) and m.get('id') and str(m.get('tier','')).lower() == 'elite':
                    ids.append(str(m.get('id')))
            return ids

        def find_matches(prefix: str) -> List[Tuple[str, str]]:
            ids = all_elite_ids()
            pref = (prefix or '').lower()
            matches = [i for i in ids if i.lower().startswith(pref)] if pref else ids
            id_to_name = {m.get('id'): m.get('name') for m in self.monsters if isinstance(m, dict)}
            return [(i, f"{i} - {id_to_name.get(i, '')}") for i in matches]

        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.input_mode == 'elite_monster' and self.input_suggestions and event.button == 1:
                        mx, my = event.pos
                        for idx, r in enumerate(self.suggestion_rects):
                            if r.collidepoint(mx, my):
                                sel_id = self.input_suggestions[idx][0]
                                self.input_active = False
                                self.input_mode = 'text'
                                self.input_suggestions = []
                                self.suggestion_index = -1
                                return sel_id
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return None
                    elif event.key == pygame.K_RETURN:
                        text = self.input_text.strip()
                        if self.input_suggestions and 0 <= self.suggestion_index < len(self.input_suggestions):
                            text = self.input_suggestions[self.suggestion_index][0]
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        # accept only elite ids
                        return text if text in all_elite_ids() else None
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                        if self.input_mode == 'elite_monster':
                            self.input_suggestions = find_matches(self.input_text)
                            self.suggestion_index = 0 if self.input_suggestions else -1
                    elif event.key == pygame.K_TAB:
                        matches = find_matches(self.input_text)
                        if len(matches) == 1:
                            self.input_text = matches[0][0]
                            self.input_suggestions = []
                            self.suggestion_index = -1
                        elif len(matches) > 1:
                            self.input_suggestions = matches
                            self.suggestion_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.input_suggestions:
                            if event.key == pygame.K_UP:
                                self.suggestion_index = (self.suggestion_index - 1) % len(self.input_suggestions)
                            else:
                                self.suggestion_index = (self.suggestion_index + 1) % len(self.input_suggestions)
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
                            if self.input_mode == 'elite_monster':
                                self.input_suggestions = find_matches(self.input_text)
                                self.suggestion_index = 0 if self.input_suggestions else -1
            self.draw()
        return None

    def read_pattern_input(self, initial: Optional[str] = None) -> Optional[str]:
        # Prompt with tab-completion for elite movement pattern
        self.input_active = True
        self.input_prompt = 'Pattern (up_down/left_right):'
        self.input_text = str(initial) if initial is not None else ''
        self.input_mode = 'pattern'
        self.input_suggestions = []
        self.suggestion_index = -1

        patterns = ['up_down', 'left_right']

        def find_matches(prefix: str) -> List[Tuple[str, str]]:
            pref = (prefix or '').lower()
            matches = [p for p in patterns if p.startswith(pref)] if pref else patterns
            return [(m, m) for m in matches]

        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.input_mode == 'pattern' and self.input_suggestions and event.button == 1:
                        mx, my = event.pos
                        for idx, r in enumerate(self.suggestion_rects):
                            if r.collidepoint(mx, my):
                                sel = self.input_suggestions[idx][0]
                                self.input_active = False
                                self.input_mode = 'text'
                                self.input_suggestions = []
                                self.suggestion_index = -1
                                return sel
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return None
                    elif event.key == pygame.K_RETURN:
                        text = self.input_text.strip()
                        if self.input_suggestions and 0 <= self.suggestion_index < len(self.input_suggestions):
                            text = self.input_suggestions[self.suggestion_index][0]
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return text if text in patterns else None
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                        if self.input_mode == 'pattern':
                            self.input_suggestions = find_matches(self.input_text)
                            self.suggestion_index = 0 if self.input_suggestions else -1
                    elif event.key == pygame.K_TAB:
                        matches = find_matches(self.input_text)
                        if len(matches) == 1:
                            self.input_text = matches[0][0]
                            self.input_suggestions = []
                            self.suggestion_index = -1
                        elif len(matches) > 1:
                            self.input_suggestions = matches
                            self.suggestion_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.input_suggestions:
                            if event.key == pygame.K_UP:
                                self.suggestion_index = (self.suggestion_index - 1) % len(self.input_suggestions)
                            else:
                                self.suggestion_index = (self.suggestion_index + 1) % len(self.input_suggestions)
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
                            if self.input_mode == 'pattern':
                                self.input_suggestions = find_matches(self.input_text)
                                self.suggestion_index = 0 if self.input_suggestions else -1
            self.draw()
        return None

    def read_npc_id_input(self, initial: Optional[str] = None) -> Optional[str]:
        # Prompt user with tab-completion and selection list for NPC IDs
        self.input_active = True
        self.input_prompt = 'Enter NPC id:'
        self.input_text = str(initial) if initial is not None else ''
        self.input_mode = 'npc'
        self.input_suggestions = []
        self.suggestion_index = -1

        def all_ids():
            return [str(n.get('id')) for n in self.npc_defs if isinstance(n, dict) and n.get('id')]

        def find_matches(prefix: str) -> List[Tuple[str, str]]:
            ids = all_ids()
            pref = prefix.lower()
            matches = [i for i in ids if i.lower().startswith(pref)] if pref else ids
            id_to_name = {n.get('id'): n.get('name') for n in self.npc_defs if isinstance(n, dict)}
            return [(i, f"{i} - {id_to_name.get(i, '')}") for i in matches]

        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.input_mode == 'npc' and self.input_suggestions and event.button == 1:
                        mx, my = event.pos
                        for idx, r in enumerate(self.suggestion_rects):
                            if r.collidepoint(mx, my):
                                sel_id = self.input_suggestions[idx][0]
                                self.input_active = False
                                self.input_mode = 'text'
                                self.input_suggestions = []
                                self.suggestion_index = -1
                                return sel_id
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return None
                    elif event.key == pygame.K_RETURN:
                        text = self.input_text.strip()
                        if self.input_suggestions and 0 <= self.suggestion_index < len(self.input_suggestions):
                            text = self.input_suggestions[self.suggestion_index][0]
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return text if text else None
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                        if self.input_mode == 'npc':
                            self.input_suggestions = find_matches(self.input_text)
                            self.suggestion_index = 0 if self.input_suggestions else -1
                    elif event.key == pygame.K_TAB:
                        matches = find_matches(self.input_text)
                        if len(matches) == 1:
                            self.input_text = matches[0][0]
                            self.input_suggestions = []
                            self.suggestion_index = -1
                        elif len(matches) > 1:
                            self.input_suggestions = matches
                            self.suggestion_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.input_suggestions:
                            if event.key == pygame.K_UP:
                                self.suggestion_index = (self.suggestion_index - 1) % len(self.input_suggestions)
                            else:
                                self.suggestion_index = (self.suggestion_index + 1) % len(self.input_suggestions)
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
                            if self.input_mode == 'npc':
                                self.input_suggestions = find_matches(self.input_text)
                                self.suggestion_index = 0 if self.input_suggestions else -1
            self.draw()
        return None

    def read_item_id_input(self, initial: Optional[str] = None) -> Optional[str]:
        # Prompt user to enter an item id with suggestions
        self.input_active = True
        self.input_prompt = 'Chest item id:'
        self.input_text = str(initial) if initial is not None else ''
        self.input_mode = 'item'
        self.input_suggestions = []
        self.suggestion_index = -1

        def all_item_ids():
            return [str(it.get('id')) for it in self.items if isinstance(it, dict) and it.get('id')]

        def find_item_matches(prefix: str) -> List[Tuple[str, str]]:
            ids = all_item_ids()
            pref = prefix.lower()
            matches = [i for i in ids if i.lower().startswith(pref)] if pref else ids
            id_to_name = {it.get('id'): it.get('name') for it in self.items if isinstance(it, dict)}
            return [(i, f"{i} - {id_to_name.get(i, '')}") for i in matches]

        while self.input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.input_mode == 'item' and self.input_suggestions and event.button == 1:
                        mx, my = event.pos
                        for idx, r in enumerate(self.suggestion_rects):
                            if r.collidepoint(mx, my):
                                sel_id = self.input_suggestions[idx][0]
                                self.input_active = False
                                self.input_mode = 'text'
                                self.input_suggestions = []
                                self.suggestion_index = -1
                                return sel_id
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return None
                    elif event.key == pygame.K_RETURN:
                        text = self.input_text.strip()
                        if self.input_suggestions and 0 <= self.suggestion_index < len(self.input_suggestions):
                            text = self.input_suggestions[self.suggestion_index][0]
                        self.input_active = False
                        self.input_mode = 'text'
                        self.input_suggestions = []
                        self.suggestion_index = -1
                        return text if text else None
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                        if self.input_mode == 'item':
                            self.input_suggestions = find_item_matches(self.input_text)
                            self.suggestion_index = 0 if self.input_suggestions else -1
                    elif event.key == pygame.K_TAB:
                        matches = find_item_matches(self.input_text)
                        if len(matches) == 1:
                            self.input_text = matches[0][0]
                            self.input_suggestions = []
                            self.suggestion_index = -1
                        elif len(matches) > 1:
                            self.input_suggestions = matches
                            self.suggestion_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.input_suggestions:
                            if event.key == pygame.K_UP:
                                self.suggestion_index = (self.suggestion_index - 1) % len(self.input_suggestions)
                            else:
                                self.suggestion_index = (self.suggestion_index + 1) % len(self.input_suggestions)
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            self.input_text += ch
                            if self.input_mode == 'item':
                                self.input_suggestions = find_item_matches(self.input_text)
                                self.suggestion_index = 0 if self.input_suggestions else -1
            self.draw()
        return None

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.input_active:
                    mx, my = event.pos
                    # If an overlay is open, only process that overlay's clicks (no painting)
                    if self.file_menu:
                        for r,_id in self.file_opt_rects:
                            if r.collidepoint(mx,my):
                                if _id=='new':
                                    self.doc.grid = base_grid(); self.doc.stairs_down=self.doc.stairs_up=None
                                    if self.doc.index==0: self.doc.town_portal=(2,2)
                                    self.file_menu=False
                                elif _id=='open':
                                    self.prompt_input('Open level index:'); s=self.read_blocking_input()
                                    if s is not None:
                                        try:
                                            self.doc = LevelDoc(int(s))
                                            self.screen = pygame.display.set_mode(window_dims())
                                        except: pass
                                    self.file_menu=False
                                elif _id=='save':
                                    self.doc.save(); self.file_menu=False
                                elif _id=='saveas':
                                    self.prompt_input('Save as level index:'); s=self.read_blocking_input()
                                    if s is not None:
                                        try:
                                            ni=int(s); self.doc.index=ni; self.doc.path=os.path.join(LEVEL_DIR,f'level{ni}.json'); self.doc.save()
                                        except: pass
                                    self.file_menu=False
                                elif _id=='size':
                                    self.prompt_input('Size width,height:'); s=self.read_blocking_input()
                                    if s:
                                        try:
                                            nw,nh=map(int,s.replace(' ','').split(','))
                                            nw=max(8,min(64,nw)); nh=max(8,min(64,nh))
                                            global W,H
                                            W, H = nw, nh
                                            # resize grid preserving content
                                            newg=[[T_WALL]*W for _ in range(H)]
                                            oy=len(self.doc.grid); ox=len(self.doc.grid[0]) if self.doc.grid else 0
                                            for y in range(min(H,oy)):
                                                for x in range(min(W,ox)):
                                                    newg[y][x]=self.doc.grid[y][x]
                                            self.doc.grid=newg
                                            self.screen = pygame.display.set_mode(window_dims())
                                        except: pass
                                    self.file_menu=False
                                elif _id=='close':
                                    self.file_menu=False
                                break
                        # Skip any further processing while menu is open
                        continue
                    if self.gen_menu:
                        for r,_id in self.gen_opt_rects:
                            if r.collidepoint(mx,my):
                                if _id=='level':
                                    generate_rooms_level(self)
                                    self.gen_menu=False
                                elif _id=='treasure':
                                    self.prompt_input('Number of treasures to create:')
                                    count_input = self.read_blocking_input()
                                    if count_input:
                                        try:
                                            count = max(0, int(count_input))
                                            generate_treasure(self, count)
                                        except Exception:
                                            self.status = 'Treasure generation cancelled'
                                    self.gen_menu=False
                                elif _id=='theme':
                                    generate_theme(self)
                                    self.gen_menu=False
                                elif _id=='close':
                                    self.gen_menu=False
                                break
                        continue
                    if self.enc_menu:
                        for r, mid in self.enc_opt_rects:
                            if r.collidepoint(mx,my):
                                mons=self.doc.encounters.get('monsters', [])
                                if mid in mons:
                                    mons.remove(mid)
                                self.doc.encounters['monsters']=mons
                                break
                        for r,_id in self.enc_btn_rects:
                            if r.collidepoint(mx,my):
                                g=self.doc.encounters.get('group',[1,3])
                                if _id=='min-': g[0]=max(1,g[0]-1)
                                elif _id=='min+': g[0]=min(g[1], g[0]+1)
                                elif _id=='max-': g[1]=max(g[0], g[1]-1)
                                elif _id=='max+': g[1]=min(9, g[1]+1)
                                elif _id=='add':
                                    self.handle_add_monster()
                                elif _id=='close': self.enc_menu=False
                                self.doc.encounters['group']=g
                                break
                        # Skip any further processing while encounters UI is open
                        continue

                    # No overlays open: normal painting + palette/buttons
                    if self.btn_file_rect.collidepoint(mx,my):
                        self.file_menu=True; self.enc_menu=False; self.gen_menu=False
                    elif self.btn_enc_rect.collidepoint(mx,my):
                        self.enc_menu=True; self.file_menu=False; self.gen_menu=False
                    elif self.btn_gen_rect.collidepoint(mx,my):
                        self.gen_menu=True; self.file_menu=False; self.enc_menu=False
                    else:
                        # palette tool buttons
                        hit_tool=False
                        for r,tid in self.tool_rects:
                            if r.collidepoint(mx,my):
                                self.tool = tid; hit_tool=True; break
                        if not hit_tool:
                            gp = self.grid_pos_from_mouse(mx, my)
                            if event.button == 1:
                                if gp:
                                    x, y = gp
                                    if self.tool == TOOL_CHEST:
                                        # toggle chest on left click
                                        found = next((i for i,c in enumerate(self.doc.chests) if c.get('x')==x and c.get('y')==y), None)
                                        if found is not None:
                                            self.doc.chests.pop(found)
                                        else:
                                            self.doc.chests.append({'x': x, 'y': y, 'iid': 'potion_small'})
                                    elif self.tool == TOOL_NPC:
                                        found = next((i for i,n in enumerate(self.doc.npcs) if n.get('x')==x and n.get('y')==y), None)
                                        if found is not None:
                                            self.doc.npcs.pop(found)
                                        else:
                                            self.doc.npcs.append({'x': x, 'y': y, 'id': 'guide'})
                                    elif self.tool == TOOL_ELITE:
                                        found = next((i for i,e in enumerate(self.doc.elites) if e.get('x')==x and e.get('y')==y), None)
                                        if found is not None:
                                            self.doc.elites.pop(found)
                                        else:
                                            self.doc.elites.append({'x': x, 'y': y, 'id': 'goblin_chief', 'pattern': 'up_down'})
                                    else:
                                        self.set_tile(x, y, self.tool)
                            elif event.button == 3:
                                if gp:
                                    x, y = gp
                    if self.doc.grid[y][x] == T_STAIRS_D:
                        self.handle_link_stairs_down(x, y)
                    elif self.doc.grid[y][x] == T_STAIRS_U:
                        self.handle_adjust_stairs_up(x, y)
                    else:
                        # Right-click a chest to set item id
                                        idx = next((i for i,c in enumerate(self.doc.chests) if c.get('x')==x and c.get('y')==y), None)
                                        if idx is not None:
                                            current_iid = self.doc.chests[idx].get('iid')
                                            iid = self.read_item_id_input(current_iid)
                                            if iid:
                                                self.doc.chests[idx]['iid'] = iid
                                        # Right-click an NPC to set NPC id (with tab completion)
                                        idx = next((i for i,n in enumerate(self.doc.npcs) if n.get('x')==x and n.get('y')==y), None)
                                        if idx is not None:
                                            current_nid = self.doc.npcs[idx].get('id')
                                            nid = self.read_npc_id_input(current_nid)
                                            if nid:
                                                self.doc.npcs[idx]['id'] = nid
                                        # Right-click an Elite to set monster id and pattern (with tab completion)
                                        idx = next((i for i,e in enumerate(self.doc.elites) if e.get('x')==x and e.get('y')==y), None)
                                        if idx is not None:
                                            current_mid = self.doc.elites[idx].get('id')
                                            mid = self.read_elite_monster_id_input(current_mid)
                                            if mid:
                                                self.doc.elites[idx]['id'] = mid
                                            current_pat = self.doc.elites[idx].get('pattern')
                                            pat = self.read_pattern_input(current_pat)
                                            if pat:
                                                self.doc.elites[idx]['pattern'] = pat
                elif event.type == pygame.KEYDOWN and not self.input_active:
                    if event.key == pygame.K_s:
                        self.doc.save(); self.status = f'Saved level {self.doc.index}'
                    elif event.key == pygame.K_r:
                        self.doc.grid = base_grid(); self.doc.stairs_down = self.doc.stairs_up = None
                        self.doc.stairs_down_target = None
                        if self.doc.index == 0: self.doc.town_portal = (2, 2)
                    elif event.key == pygame.K_g:
                        self.gen_menu=True; self.file_menu=False; self.enc_menu=False
                    elif event.key == pygame.K_m:
                        generate_rooms_level(self)
                    elif event.key in (pygame.K_COMMA,):
                        self.doc = LevelDoc(max(0, self.doc.index - 1))
                        # Rebuild the window so it matches the loaded level's dimensions
                        self.screen = pygame.display.set_mode(window_dims())
                    elif event.key in (pygame.K_PERIOD,):
                        self.doc = LevelDoc(self.doc.index + 1)
                        # Rebuild the window so it matches the loaded level's dimensions
                        self.screen = pygame.display.set_mode(window_dims())
                    elif pygame.K_0 <= event.key <= pygame.K_9:
                        self.tool = event.key - pygame.K_0
                    elif event.key == pygame.K_DELETE:
                        # Delete whatever node is under the mouse and leave floor
                        mx, my = pygame.mouse.get_pos()
                        gp = self.grid_pos_from_mouse(mx, my)
                        if gp:
                            x, y = gp
                        # Clear tile to floor
                        self.doc.grid[y][x] = T_EMPTY
                        # Clear stair markers if present
                        if self.doc.stairs_down == (x, y):
                            self.doc.stairs_down = None
                            self.doc.stairs_down_target = None
                        if self.doc.stairs_up == (x, y):
                            self.doc.stairs_up = None
                        if self.doc.town_portal == (x, y):
                            self.doc.town_portal = None
                        if getattr(self.doc, 'end_node', None) == (x, y):
                            self.doc.end_node = None
                        # Remove chest at cell
                        ci = next((i for i,c in enumerate(self.doc.chests) if int(c.get('x',-1))==x and int(c.get('y',-1))==y), None)
                        if ci is not None:
                            try:
                                self.doc.chests.pop(ci)
                            except Exception:
                                pass
                        # Remove NPC at cell
                        ni = next((i for i,n in enumerate(self.doc.npcs) if int(n.get('x',-1))==x and int(n.get('y',-1))==y), None)
                        if ni is not None:
                            try:
                                self.doc.npcs.pop(ni)
                            except Exception:
                                pass
                        # Remove Elite at cell
                        ei = next((i for i,e in enumerate(getattr(self.doc,'elites',[]) or []) if int(e.get('x',-1))==x and int(e.get('y',-1))==y), None)
                        if ei is not None:
                            try:
                                self.doc.elites.pop(ei)
                            except Exception:
                                pass
                        self.status = f'Deleted nodes at {x},{y}'

            self.draw()
            clock.tick(60)
        pygame.quit()

# ------------------------- Generation helpers -------------------------

def _in_bounds_xy(x: int, y: int) -> bool:
    return 0 <= x < W and 0 <= y < H

def _is_marker(tile: int) -> bool:
    return tile in (T_TOWN, T_STAIRS_D, T_STAIRS_U)

def _reapply_markers(doc: LevelDoc, grid: List[List[int]]):
    if doc.town_portal:
        x, y = doc.town_portal
        if _in_bounds_xy(x, y):
            grid[y][x] = T_TOWN
    if doc.stairs_up:
        x, y = doc.stairs_up
        if _in_bounds_xy(x, y):
            grid[y][x] = T_STAIRS_U
    if doc.stairs_down:
        x, y = doc.stairs_down
        if _in_bounds_xy(x, y):
            grid[y][x] = T_STAIRS_D

def _all_markers(doc: LevelDoc) -> List[Tuple[int,int,int]]:
    res: List[Tuple[int,int,int]] = []
    if doc.town_portal:
        x,y = doc.town_portal; res.append((x,y,T_TOWN))
    if doc.stairs_up:
        x,y = doc.stairs_up; res.append((x,y,T_STAIRS_U))
    if doc.stairs_down:
        x,y = doc.stairs_down; res.append((x,y,T_STAIRS_D))
    return res

def _clamp_center(x: int, y: int) -> Tuple[int,int]:
    return max(1, min(W-2, x)), max(1, min(H-2, y))

def _neighbors2(x: int, y: int) -> List[Tuple[int,int,int,int]]:
    dirs = [(2,0),(-2,0),(0,2),(0,-2)]
    res=[]
    for dx,dy in dirs:
        nx,ny=x+dx,y+dy
        wx,wy=x+dx//2, y+dy//2
        if 1 <= nx < W-1 and 1 <= ny < H-1:
            res.append((nx,ny,wx,wy))
    random.shuffle(res)
    return res

def _carve_room(grid: List[List[int]], left: int, top: int, w: int, h: int):
    for yy in range(top, top+h):
        for xx in range(left, left+w):
            if 0 <= xx < W and 0 <= yy < H and not _is_marker(grid[yy][xx]):
                grid[yy][xx] = T_EMPTY

def _carve_line(grid: List[List[int]], x0: int, y0: int, x1: int, y1: int):
    x,y=x0,y0
    dx = 1 if x1> x0 else -1
    while x != x1:
        if _in_bounds_xy(x,y) and not _is_marker(grid[y][x]):
            grid[y][x]=T_EMPTY
        x += dx
    dy = 1 if y1> y0 else -1
    while y != y1:
        if _in_bounds_xy(x,y) and not _is_marker(grid[y][x]):
            grid[y][x]=T_EMPTY
        y += dy
    if _in_bounds_xy(x,y) and not _is_marker(grid[y][x]):
        grid[y][x]=T_EMPTY

def _ensure_borders(grid: List[List[int]]):
    for x in range(W):
        grid[0][x]=T_WALL; grid[H-1][x]=T_WALL
    for y in range(H):
        grid[y][0]=T_WALL; grid[y][W-1]=T_WALL

def generate_maze_level(self: 'Editor'):
    # Preserve markers by never overwriting those tiles.
    grid = [[T_WALL for _ in range(W)] for _ in range(H)]
    _reapply_markers(self.doc, grid)
    # DFS backtracker on odd cells
    sx = max(1, (W//2)|1)
    sy = max(1, (H//2)|1)
    stack=[(sx,sy)]
    if not _is_marker(grid[sy][sx]):
        grid[sy][sx]=T_EMPTY
    seen={(sx,sy)}
    while stack:
        x,y=stack[-1]
        nbs=[nb for nb in _neighbors2(x,y) if (nb[0],nb[1]) not in seen]
        if not nbs:
            stack.pop(); continue
        nx,ny,wx,wy=random.choice(nbs)
        if not _is_marker(grid[wy][wx]): grid[wy][wx]=T_EMPTY
        if not _is_marker(grid[ny][nx]): grid[ny][nx]=T_EMPTY
        seen.add((nx,ny))
        stack.append((nx,ny))
    # Make sure markers have at least one adjacent empty for access
    for mx,my,_t in _all_markers(self.doc):
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nx,ny=mx+dx,my+dy
            if 1<=nx<W-1 and 1<=ny<H-1 and not _is_marker(grid[ny][nx]):
                grid[ny][nx]=T_EMPTY
                break
    _ensure_borders(grid)
    self.doc.grid = grid
    _reapply_markers(self.doc, self.doc.grid)
    self.status = 'Generated maze'

def generate_rooms_level(self: 'Editor'):
    # Bob Nystrom style BSP-less random rooms + tunnels
    grid = [[T_WALL for _ in range(W)] for _ in range(H)]

    room_sizes = [(3, 3), (4, 3), (3, 4)]
    max_rooms = max(12, (W * H) // 32)
    max_attempts = max_rooms * 5

    rooms: List[pygame.Rect] = []
    centers: List[Tuple[int, int]] = []

    for _ in range(max_attempts):
        if len(rooms) >= max_rooms:
            break
        w, h = random.choice(room_sizes)
        if W - w - 2 <= 0 or H - h - 2 <= 0:
            continue
        x = random.randint(1, max(1, W - w - 2))
        y = random.randint(1, max(1, H - h - 2))
        room = pygame.Rect(x, y, w, h)
        padded = room.inflate(2, 2)
        if any(padded.colliderect(r.inflate(2, 2)) for r in rooms):
            continue
        rooms.append(room)
        for yy in range(room.top, room.bottom):
            for xx in range(room.left, room.right):
                if 0 <= yy < H and 0 <= xx < W:
                    grid[yy][xx] = T_EMPTY
        cx = room.left + room.width // 2
        cy = room.top + room.height // 2
        centers.append((cx, cy))

    if not rooms:
        w, h = random.choice(room_sizes)
        w = min(w, max(3, W - 2))
        h = min(h, max(3, H - 2))
        x = max(1, (W // 2) - w // 2)
        y = max(1, (H // 2) - h // 2)
        x = min(x, W - w - 1)
        y = min(y, H - h - 1)
        room = pygame.Rect(x, y, w, h)
        rooms.append(room)
        for yy in range(room.top, room.bottom):
            for xx in range(room.left, room.right):
                if 0 <= yy < H and 0 <= xx < W:
                    grid[yy][xx] = T_EMPTY
        centers.append((room.left + room.width // 2, room.top + room.height // 2))

    def carve_horiz(y: int, x1: int, x2: int):
        if x1 > x2:
            x1, x2 = x2, x1
        for x in range(x1, x2 + 1):
            if 0 <= y < H and 0 <= x < W and not _is_marker(grid[y][x]):
                grid[y][x] = T_EMPTY

    def carve_vert(x: int, y1: int, y2: int):
        if y1 > y2:
            y1, y2 = y2, y1
        for y in range(y1, y2 + 1):
            if 0 <= y < H and 0 <= x < W and not _is_marker(grid[y][x]):
                grid[y][x] = T_EMPTY

    centers.sort(key=lambda c: (c[0], c[1]))
    for i in range(1, len(centers)):
        (x1, y1) = centers[i - 1]
        (x2, y2) = centers[i]
        if random.random() < 0.5:
            carve_horiz(y1, x1, x2)
            carve_vert(x2, y1, y2)
        else:
            carve_vert(x1, y1, y2)
            carve_horiz(y2, x1, x2)

    extra_connections = max(0, len(centers) // 3)
    for _ in range(extra_connections):
        if len(centers) < 2:
            break
        a, b = random.sample(centers, 2)
        carve_horiz(a[1], a[0], b[0])
        carve_vert(b[0], a[1], b[1])

    _ensure_borders(grid)

    self.doc.grid = grid
    _reapply_markers(self.doc, self.doc.grid)
    self.doc.chests = []
    self.doc.elites = []
    self.doc.stairs_down = None
    self.doc.stairs_down_target = None

    self.status = 'Generated level layout'


def _find_3x3_room_centers(grid: List[List[int]]) -> List[Tuple[int, int]]:
    results: List[Tuple[int, int]] = []
    h = len(grid)
    w = len(grid[0]) if h else 0
    for y in range(2, h - 2):
        for x in range(2, w - 2):
            # All tiles in the 3x3 core must be floor
            core_ok = True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if grid[y + dy][x + dx] != T_EMPTY:
                        core_ok = False
                        break
                if not core_ok:
                    break
            if not core_ok:
                continue
            # Require the ring two tiles out to mostly be walls, allowing at most one opening (door/corridor)
            openings = 0
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                nx, ny = x + dx, y + dy
                if not _in_bounds_xy(nx, ny):
                    core_ok = False
                    break
                if grid[ny][nx] == T_EMPTY:
                    openings += 1
            if not core_ok or openings > 1:
                continue
            results.append((x, y))
    return results


def generate_treasure(self: 'Editor', desired: int):
    if desired <= 0:
        self.status = 'Treasure generation cancelled'
        return
    centers = _find_3x3_room_centers(self.doc.grid)
    if not centers:
        self.status = 'No 3x3 rooms available'
        return
    random.shuffle(centers)
    center_set = set(centers)
    self.doc.chests = [c for c in self.doc.chests if (int(c.get('x', -999)), int(c.get('y', -999))) not in center_set]
    existing = {(int(c.get('x', -999)), int(c.get('y', -999))) for c in self.doc.chests}
    limit = min(desired, len(centers))
    placed = 0
    for cx, cy in centers:
        if (cx, cy) in existing:
            continue
        iid = pick_item_for_floor(self)
        self.doc.chests.append({'x': cx, 'y': cy, 'iid': iid})
        existing.add((cx, cy))
        placed += 1
        if placed >= limit:
            break
    if placed:
        self.status = f'Placed {placed} treasure(s)'
    else:
        self.status = 'No new treasure placed'


def generate_theme(self: 'Editor'):
    monsters = getattr(self, 'monsters', []) or []
    themes: Dict[str, Dict[str, Any]] = {}
    for m in monsters:
        if not isinstance(m, dict):
            continue
        theme_id = str(m.get('theme', m.get('archetype', 'general'))).lower()
        themes.setdefault(theme_id, {'monsters': []})['monsters'].append(m)
    if not themes:
        self.status = 'No monster data available for theming'
        return
    theme_id, theme_data = random.choice(list(themes.items()))

    quest_id = None
    npc_id = None
    quest_map = {str(q.get('id')): q for q in getattr(self, 'quests', []) if isinstance(q, dict) and q.get('id')}
    npc_pool = [npc for npc in getattr(self, 'npc_defs', []) if isinstance(npc, dict) and npc.get('quest_id') and npc.get('quest_id') in quest_map]
    themed_npcs = [npc for npc in npc_pool if str(npc.get('quest_id', '')).lower().startswith(theme_id)]
    pick_pool = themed_npcs or npc_pool
    if pick_pool:
        pick = random.choice(pick_pool)
        npc_id = str(pick.get('id'))
        quest_id = str(pick.get('quest_id'))

    themed_monster_ids = [str(m.get('id')) for m in theme_data['monsters'] if m.get('id')]
    if themed_monster_ids:
        self.doc.encounters['monsters'] = themed_monster_ids
        max_group = max(1, min(4, len(themed_monster_ids)))
        self.doc.encounters['group'] = [1, max_group]
    else:
        self.doc.encounters['monsters'] = []
        self.doc.encounters['group'] = [1, 1]

    grid = self.doc.grid
    empty_slots = [(x, y) for y in range(1, H - 1) for x in range(1, W - 1) if grid[y][x] == T_EMPTY]

    self.doc.elites = []
    self.doc.npcs = []
    self.doc.quest_id = None

    elite_spot = None
    npc_spot = None
    def has_open_square(cx: int, cy: int) -> bool:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    return False
                if grid[ny][nx] != T_EMPTY:
                    return False
        return True

    random.shuffle(empty_slots)
    for x, y in empty_slots:
        if has_open_square(x, y):
            elite_spot = (x, y)
            break
    if elite_spot is None and empty_slots:
        elite_spot = empty_slots[0]
    if elite_spot:
        ex, ey = elite_spot
        elite_candidates = [m for m in theme_data['monsters'] if str(m.get('tier', '')).lower() == 'elite']
        elite = random.choice(elite_candidates) if elite_candidates else random.choice(theme_data['monsters']) if theme_data['monsters'] else None
        if elite:
            self.doc.elites = [{'x': ex, 'y': ey, 'id': elite.get('id'), 'pattern': 'up_down'}]

    for x, y in empty_slots:
        if (x, y) == elite_spot:
            continue
        if has_open_square(x, y):
            npc_spot = (x, y)
            break
    if npc_spot is None and empty_slots:
        for x, y in empty_slots:
            if (x, y) != elite_spot:
                npc_spot = (x, y)
                break
    if npc_spot and npc_id:
        nx, ny = npc_spot
        self.doc.npcs = [{'x': nx, 'y': ny, 'id': npc_id}]
    else:
        self.doc.npcs = []

    if quest_id:
        self.doc.quest_id = quest_id

    self.status = f"Applied theme '{theme_id}'"

if __name__ == '__main__':
    idx = 0
    if len(sys.argv) >= 2:
        try:
            idx = int(sys.argv[1])
        except Exception:
            pass
    Editor(idx).run()
