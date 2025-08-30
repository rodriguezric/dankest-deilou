#!/usr/bin/env python3
import os, sys, json
from typing import List, Dict, Any, Optional, Tuple

import pygame

# Tile constants (match main.py)
T_EMPTY, T_WALL, T_TOWN, T_STAIRS_D, T_STAIRS_U = 0, 1, 2, 3, 4

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
        self.size: Tuple[int, int] = (W, H)
        self.load()

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
        self.encounters = self.data.get('encounters', self.encounters)

        # ensure markers reflected in grid
        if self.town_portal:
            x,y = self.town_portal; self.grid[y][x] = T_TOWN
        if self.stairs_down:
            x,y = self.stairs_down; self.grid[y][x] = T_STAIRS_D
        if self.stairs_up:
            x,y = self.stairs_up; self.grid[y][x] = T_STAIRS_U

    def save(self):
        d: Dict[str, Any] = {
            'grid': self.grid,
            'encounters': self.encounters,
            'size': [W, H],
        }
        if self.stairs_down: d['stairs_down'] = list(self.stairs_down)
        if self.stairs_up: d['stairs_up'] = list(self.stairs_up)
        if self.index == 0 and self.town_portal:
            d['town_portal'] = list(self.town_portal)
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
        # UI state
        self.tool_rects: List[Tuple[pygame.Rect, int]] = []
        self.btn_file_rect = pygame.Rect(0,0,0,0)
        self.btn_enc_rect = pygame.Rect(0,0,0,0)
        self.file_menu = False
        self.enc_menu = False
        self.file_opt_rects: List[Tuple[pygame.Rect, str]] = []
        self.enc_opt_rects: List[Tuple[pygame.Rect, str]] = []
        self.enc_btn_rects: List[Tuple[pygame.Rect, str]] = []
        # Monsters list for encounters UI
        self.monsters: List[Dict[str, Any]] = load_json(os.path.join(DATA_DIR, 'monsters.json'), [])

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
        elif prev == T_STAIRS_D and self.doc.stairs_down == (x, y):
            self.doc.stairs_down = None
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

    def prompt_input(self, prompt_text: str):
        self.input_active = True
        self.input_prompt = prompt_text
        self.input_text = ''

    def handle_link_stairs_down(self, x, y):
        # prompt for target level index and target pos
        self.prompt_input('Target level index:')
        target_level = self.read_blocking_input()
        if target_level is None: return
        try:
            tgt_ix = int(target_level)
        except:
            self.status = 'Invalid level index'
            return
        self.prompt_input('Target position x,y:')
        pos_str = self.read_blocking_input()
        if pos_str is None: return
        try:
            tx, ty = map(int, pos_str.replace(' ', '').split(','))
        except:
            self.status = 'Invalid position'
            return
        # Ensure target level exists and has an upstairs backlink
        tgt_path = os.path.join(LEVEL_DIR, f'level{tgt_ix}.json')
        tgt = LevelDoc(tgt_ix)
        tgt.grid[ty][tx] = T_STAIRS_U
        tgt.stairs_up = (tx, ty)
        tgt.save()
        # Set current stairs down and save
        self.doc.grid[y][x] = T_STAIRS_D
        self.doc.stairs_down = (x, y)
        self.doc.save()
        self.status = f'Linked down to level {tgt_ix} at {tx},{ty}'

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
        self.text_small('S: Save   ,/.: Prev/Next level', (px, py)); py += 18
        self.text_small('0..4: Select tool   R: Reset', (px, py)); py += 18
        self.text_small('Right-click stairs-down: link', (px, py)); py += 18
        py += 6
        tools = [
            (T_EMPTY, 'Empty'),
            (T_WALL, 'Wall'),
            (T_TOWN, 'Town (L0)'),
            (T_STAIRS_D, 'Stairs Down'),
            (T_STAIRS_U, 'Stairs Up'),
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
            mons_set=set(self.doc.encounters.get('monsters', []))
            self.enc_opt_rects=[]
            for i,m in enumerate(self.monsters):
                r=pygame.Rect(x,y, box.w-32, 22)
                on = m.get('id') in mons_set
                pygame.draw.rect(self.screen, (60,60,72) if on else (40,40,48), r); pygame.draw.rect(self.screen, WHITE, r,1)
                self.text_small(f"{m.get('id')} - {m.get('name')}", (r.x+8,r.y+4), YELLOW if on else WHITE)
                self.enc_opt_rects.append((r,m.get('id'))); y+=24
                if y> box.bottom-100: break
            y=box.bottom-100
            g=self.doc.encounters.get('group',[1,3])
            self.text_small(f"Group min: {g[0]}  max: {g[1]}", (x,y), WHITE); y+=24
            btns=[('Min -','min-'),('Min +','min+'),('Max -','max-'),('Max +','max+'),('Close','close')]
            self.enc_btn_rects=[]
            bx=x
            for label,_id in btns:
                r=pygame.Rect(bx,y, 74,24)
                pygame.draw.rect(self.screen,(40,40,48), r); pygame.draw.rect(self.screen, WHITE, r,1)
                self.text_small(label,(r.x+6,r.y+4)); self.enc_btn_rects.append((r,_id)); bx+= 78

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
                    if self.enc_menu:
                        for r, mid in self.enc_opt_rects:
                            if r.collidepoint(mx,my):
                                mons=self.doc.encounters.get('monsters', [])
                                if mid in mons: mons.remove(mid)
                                else: mons.append(mid)
                                self.doc.encounters['monsters']=mons
                                break
                        for r,_id in self.enc_btn_rects:
                            if r.collidepoint(mx,my):
                                g=self.doc.encounters.get('group',[1,3])
                                if _id=='min-': g[0]=max(1,g[0]-1)
                                elif _id=='min+': g[0]=min(g[1], g[0]+1)
                                elif _id=='max-': g[1]=max(g[0], g[1]-1)
                                elif _id=='max+': g[1]=min(9, g[1]+1)
                                elif _id=='close': self.enc_menu=False
                                self.doc.encounters['group']=g
                                break
                        # Skip any further processing while encounters UI is open
                        continue

                    # No overlays open: normal painting + palette/buttons
                    if self.btn_file_rect.collidepoint(mx,my):
                        self.file_menu=True; self.enc_menu=False
                    elif self.btn_enc_rect.collidepoint(mx,my):
                        self.enc_menu=True; self.file_menu=False
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
                                    self.set_tile(x, y, self.tool)
                            elif event.button == 3:
                                if gp:
                                    x, y = gp
                                    if self.doc.grid[y][x] == T_STAIRS_D:
                                        self.handle_link_stairs_down(x, y)
                elif event.type == pygame.KEYDOWN and not self.input_active:
                    if event.key == pygame.K_s:
                        self.doc.save(); self.status = f'Saved level {self.doc.index}'
                    elif event.key == pygame.K_r:
                        self.doc.grid = base_grid(); self.doc.stairs_down = self.doc.stairs_up = None
                        if self.doc.index == 0: self.doc.town_portal = (2, 2)
                    elif event.key in (pygame.K_COMMA,):
                        self.doc = LevelDoc(max(0, self.doc.index - 1))
                    elif event.key in (pygame.K_PERIOD,):
                        self.doc = LevelDoc(self.doc.index + 1)
                    elif pygame.K_0 <= event.key <= pygame.K_4:
                        self.tool = event.key - pygame.K_0

            self.draw()
            clock.tick(60)
        pygame.quit()

if __name__ == '__main__':
    idx = 0
    if len(sys.argv) >= 2:
        try:
            idx = int(sys.argv[1])
        except: pass
    Editor(idx).run()
