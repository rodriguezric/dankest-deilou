#!/usr/bin/env python3
import json, os, sys
from typing import List, Dict, Any

DATA_DIR = 'data'
LVL_DIR = os.path.join(DATA_DIR, 'levels')

T_EMPTY, T_WALL, T_TOWN, T_STAIRS_D, T_STAIRS_U = 0, 1, 2, 3, 4

SHOP_DEFAULT_CLASSES = ["Fighter", "Mage", "Priest", "Rogue"]

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
    print(f"Saved {path}")

def prompt(msg, default=None):
    s = input(f"{msg}{' ['+str(default)+']' if default is not None else ''}: ")
    return s if s.strip() else default

# -------- Monsters --------
def monsters_menu():
    path = os.path.join(DATA_DIR, 'monsters.json')
    data: List[Dict[str, Any]] = load_json(path, [])
    while True:
        print("\nMonsters:")
        for i, m in enumerate(data):
            print(f" {i+1}. {m.get('id')} — {m.get('name')}")
        print(" a) Add  e) Edit  d) Delete  q) Back")
        ch = input("> ").strip().lower()
        if ch == 'q':
            break
        elif ch == 'a':
            mid = prompt('id')
            name = prompt('name', mid)
            hp_low = int(prompt('hp_low', 6)); hp_high = int(prompt('hp_high', 10))
            ac = int(prompt('ac', 8))
            atk_low = int(prompt('atk_low', 1)); atk_high = int(prompt('atk_high', 4))
            exp = int(prompt('exp', 10))
            gold_low = int(prompt('gold_low', 1)); gold_high = int(prompt('gold_high', 8))
            agi = int(prompt('agi', 7))
            data.append({"id": mid, "name": name, "hp_low": hp_low, "hp_high": hp_high, "ac": ac,
                         "atk_low": atk_low, "atk_high": atk_high, "exp": exp, "gold_low": gold_low,
                         "gold_high": gold_high, "agi": agi})
            save_json(path, data)
        elif ch == 'e':
            i = int(prompt('index')) - 1
            if 0 <= i < len(data):
                m = data[i]
                for k in ["id","name","hp_low","hp_high","ac","atk_low","atk_high","exp","gold_low","gold_high","agi"]:
                    val = prompt(k, m.get(k))
                    m[k] = int(val) if isinstance(m.get(k), int) else val
                save_json(path, data)
        elif ch == 'd':
            i = int(prompt('index')) - 1
            if 0 <= i < len(data):
                data.pop(i)
                save_json(path, data)

# -------- Items --------
def items_menu():
    ipath = os.path.join(DATA_DIR, 'items.json')
    spath = os.path.join(DATA_DIR, 'shop.json')
    items: List[Dict[str, Any]] = load_json(ipath, [])
    default_ids = [it.get('id') for it in items if it.get('id')]
    shop_raw = load_json(spath, None)

    def dedupe(seq: List[str]) -> List[str]:
        seen = set(); out: List[str] = []
        for iid in seq:
            if not iid or iid in seen:
                continue
            seen.add(iid)
            out.append(iid)
        return out

    shop_general: List[str]
    shop_classes: Dict[str, List[str]]
    if isinstance(shop_raw, dict):
        raw_general = shop_raw.get('general')
        shop_general = dedupe(list(raw_general)) if isinstance(raw_general, list) else []
        class_data = shop_raw.get('class_gear')
        if class_data is None:
            class_data = shop_raw.get('classes', {})
        shop_classes = {}
        if isinstance(class_data, dict):
            for cname, ids in class_data.items():
                if isinstance(ids, list):
                    shop_classes[cname] = dedupe(list(ids))
    elif isinstance(shop_raw, list):
        shop_general = dedupe(list(shop_raw))
        shop_classes = {}
    else:
        shop_general = dedupe(list(default_ids))
        shop_classes = {}

    def ordered_class_payload() -> Dict[str, List[str]]:
        payload: Dict[str, List[str]] = {}
        for cname in SHOP_DEFAULT_CLASSES:
            ids = shop_classes.get(cname)
            if ids:
                payload[cname] = ids
        for cname, ids in shop_classes.items():
            if cname not in payload and ids:
                payload[cname] = ids
        return payload

    def drop_from_classes(iid: str):
        for cname in list(shop_classes.keys()):
            ids = shop_classes.get(cname, [])
            if iid in ids:
                while iid in ids:
                    ids.remove(iid)
                if not ids:
                    shop_classes.pop(cname, None)

    def remove_from_general(iid: str):
        while iid in shop_general:
            shop_general.remove(iid)

    def save_all():
        save_json(ipath, items)
        payload = {"general": shop_general, "class_gear": ordered_class_payload()}
        save_json(spath, payload)
    while True:
        print("\nItems:")
        for i, it in enumerate(items):
            iid = it.get('id')
            tags: List[str] = []
            if iid in shop_general:
                tags.append('general')
            for cname, ids in shop_classes.items():
                if iid in ids:
                    tags.append(cname)
            stock = f" [{' / '.join(tags)}]" if tags else ''
            print(f" {i+1}. {iid} — {it.get('name')} ({it.get('type')}){stock}")
        print(" a) Add  e) Edit  d) Delete  s) Toggle shop stock  q) Back")
        ch = input("> ").strip().lower()
        if ch == 'q': break
        elif ch == 'a':
            iid = prompt('id')
            name = prompt('name', iid)
            typ = prompt('type [consumable|weapon|armor|accessory]', 'consumable')
            price = int(prompt('price', 10))
            it = {"id": iid, "name": name, "type": typ, "price": price}
            if typ == 'consumable':
                it['heal'] = int(prompt('heal', 10))
            elif typ == 'weapon':
                it['atk'] = int(prompt('atk', 1))
            elif typ == 'armor':
                it['ac'] = int(prompt('ac', -1))
            elif typ == 'accessory':
                stat = prompt('stat [agi/ac]', 'agi')
                it[stat] = int(prompt(stat, 1))
            items.append(it); save_all()
        elif ch == 'e':
            i = int(prompt('index')) - 1
            if 0 <= i < len(items):
                it = items[i]
                for k in list(it.keys()):
                    val = prompt(k, it.get(k)); it[k] = int(val) if isinstance(it.get(k), int) else val
                save_all()
        elif ch == 'd':
            i = int(prompt('index')) - 1
            if 0 <= i < len(items):
                iid = items[i].get('id'); items.pop(i)
                if iid:
                    remove_from_general(iid)
                    drop_from_classes(iid)
                save_all()
        elif ch == 's':
            i = int(prompt('index')) - 1
            if 0 <= i < len(items):
                iid = items[i].get('id')
                if not iid:
                    continue
                bucket = prompt('stock group (general / class name)', 'general')
                if not bucket:
                    continue
                bucket = bucket.strip()
                if bucket.lower().startswith('g'):
                    if iid in shop_general:
                        remove_from_general(iid)
                        print(f"Removed {iid} from general stock.")
                    else:
                        drop_from_classes(iid)
                        shop_general.append(iid)
                        print(f"Added {iid} to general stock.")
                else:
                    cname = None
                    for name in list(shop_classes.keys()) + SHOP_DEFAULT_CLASSES:
                        if name.lower() == bucket.lower():
                            cname = name
                            break
                    if cname is None:
                        cname = bucket
                    lst = shop_classes.setdefault(cname, [])
                    if iid in lst:
                        while iid in lst:
                            lst.remove(iid)
                        if not lst:
                            shop_classes.pop(cname, None)
                        print(f"Removed {iid} from {cname} gear.")
                    else:
                        remove_from_general(iid)
                        drop_from_classes(iid)
                        lst.append(iid)
                        print(f"Added {iid} to {cname} gear.")
                save_all()

# -------- Skills --------
def skills_menu():
    path = os.path.join(DATA_DIR, 'skills.json')
    data = load_json(path, {"classes": {}})
    classes: Dict[str, List[Dict[str, Any]]] = data.setdefault('classes', {})
    while True:
        print("\nClasses:")
        for cname, skills in classes.items():
            print(f" - {cname}: {[s.get('name') for s in skills]}")
        print(" a) Add class  e) Edit class  d) Delete class  q) Back")
        ch = input("> ").strip().lower()
        if ch == 'q': break
        elif ch == 'a':
            cname = prompt('class name')
            classes.setdefault(cname, []); save_json(path, data)
        elif ch == 'd':
            cname = prompt('class name')
            classes.pop(cname, None); save_json(path, data)
        elif ch == 'e':
            cname = prompt('class name')
            skills = classes.setdefault(cname, [])
            while True:
                print(f"\nSkills for {cname}:")
                for i, s in enumerate(skills):
                    print(f" {i+1}. {s.get('id')} — {s.get('name')} (mp {s.get('mp_cost',0)})")
                print(" a) Add  e) Edit  d) Delete  b) Back")
                c2 = input("> ").strip().lower()
                if c2 == 'b': break
                elif c2 == 'a':
                    sid = prompt('id'); name = prompt('name', sid); mp = int(prompt('mp_cost', 1))
                    skills.append({"id": sid, "name": name, "mp_cost": mp}); save_json(path, data)
                elif c2 == 'e':
                    i = int(prompt('index')) - 1
                    if 0 <= i < len(skills):
                        s = skills[i]
                        for k in ["id","name","mp_cost"]:
                            v = prompt(k, s.get(k)); s[k] = int(v) if k=='mp_cost' else v
                        save_json(path, data)
                elif c2 == 'd':
                    i = int(prompt('index')) - 1
                    if 0 <= i < len(skills):
                        skills.pop(i); save_json(path, data)

# -------- Levels --------
def base_grid(w: int = 24, h: int = 24):
    w = max(8, w)
    h = max(8, h)
    g = [[T_WALL] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            g[y][x] = T_EMPTY
    return g

def print_grid(grid):
    ch={0:' ',1:'#',2:'T',3:'D',4:'U'}
    for y,row in enumerate(grid):
        print(''.join(ch.get(v,'?') for v in row))

def level_menu():
    os.makedirs(LVL_DIR, exist_ok=True)
    while True:
        print("\nLevel editor: enter level index (number) or q to return")
        s = input("> ").strip().lower()
        if s == 'q':
            break
        try:
            ix = int(s)
        except Exception:
            continue
        path = os.path.join(LVL_DIR, f'level{ix}.json')
        data = load_json(path, {})
        size = data.get('size')
        width = height = None
        if isinstance(size, list) and len(size) == 2:
            try:
                width, height = int(size[0]), int(size[1])
            except Exception:
                width = height = None
        grid_data = data.get('grid')
        if isinstance(grid_data, list) and grid_data and isinstance(grid_data[0], list):
            if width is None or height is None:
                height = len(grid_data)
                width = len(grid_data[0]) if grid_data[0] else 24
            grid = base_grid(width, height)
            for y in range(min(height, len(grid_data))):
                row = grid_data[y]
                for x in range(min(width, len(row))):
                    try:
                        grid[y][x] = int(row[x])
                    except Exception:
                        pass
        else:
            width = width or 24
            height = height or 24
            grid = base_grid(width, height)
        enc = data.get('encounters') or {"monsters": [], "group": [1, 3]}
        stairs_down = data.get('stairs_down')
        stairs_up = data.get('stairs_up')
        town = data.get('town_portal')
        while True:
            print(f"\nEditing level {ix}. Commands: show, set x y tile(0..4), rect x1 y1 x2 y2 tile, stairsdown x y targetLevel, stairsup x y, town x y, monsters, save, back")
            cmd = input("> ").strip().lower().split()
            if not cmd:
                continue
            if cmd[0] == 'back':
                break
            if cmd[0] == 'show':
                print_grid(grid)
                print(f"size=({len(grid[0])}x{len(grid)}) stairs_down={stairs_down} stairs_up={stairs_up} town_portal={town}")
                print(f"encounters: {enc}")
            elif cmd[0] == 'set' and len(cmd) == 4:
                x, y, t = map(int, cmd[1:])
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    grid[y][x] = t
            elif cmd[0] == 'rect' and len(cmd) == 6:
                x1, y1, x2, y2, t = map(int, cmd[1:])
                for y in range(min(y1, y2), max(y1, y2) + 1):
                    for x in range(min(x1, x2), max(x1, x2) + 1):
                        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                            grid[y][x] = t
            elif cmd[0] == 'stairsdown' and len(cmd) == 4:
                x, y, tgt = map(int, cmd[1:])
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    stairs_down = [x, y]
                    grid[y][x] = T_STAIRS_D
                # set backlink in target level as stairs_up at same coords by default
                tpath = os.path.join(LVL_DIR, f'level{tgt}.json')
                tdata = load_json(tpath, {})
                tsize = tdata.get('size')
                tw = th = None
                if isinstance(tsize, list) and len(tsize) == 2:
                    try:
                        tw, th = int(tsize[0]), int(tsize[1])
                    except Exception:
                        pass
                tgrid_data = tdata.get('grid')
                if isinstance(tgrid_data, list) and tgrid_data and isinstance(tgrid_data[0], list):
                    if tw is None or th is None:
                        th = len(tgrid_data)
                        tw = len(tgrid_data[0]) if tgrid_data[0] else len(grid[0])
                    tgrid = base_grid(tw, th)
                    for yy in range(min(th, len(tgrid_data))):
                        row = tgrid_data[yy]
                        for xx in range(min(tw, len(row))):
                            try:
                                tgrid[yy][xx] = int(row[xx])
                            except Exception:
                                pass
                else:
                    tw = tw or len(grid[0])
                    th = th or len(grid)
                    tgrid = base_grid(tw, th)
                if 0 <= y < len(tgrid) and 0 <= x < len(tgrid[0]):
                    tgrid[y][x] = T_STAIRS_U
                tdata['grid'] = tgrid
                tdata['stairs_up'] = [x, y]
                tdata['size'] = [len(tgrid[0]), len(tgrid)]
                save_json(tpath, tdata)
            elif cmd[0] == 'stairsup' and len(cmd) == 3:
                x, y = map(int, cmd[1:])
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    stairs_up = [x, y]
                    grid[y][x] = T_STAIRS_U
            elif cmd[0] == 'town' and len(cmd) == 3:
                x, y = map(int, cmd[1:])
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    town = [x, y]
                    grid[y][x] = T_TOWN
            elif cmd[0] == 'monsters':
                print(f"Current allowed monsters: {enc.get('monsters', [])} group={enc.get('group',[1,3])}")
                ids = prompt('ids (comma-separated)', ','.join(enc.get('monsters', [])))
                group = prompt('group (min,max)', '1,3')
                try:
                    mins, maxs = map(int, group.split(','))
                    enc['group'] = [mins, maxs]
                except Exception:
                    pass
                enc['monsters'] = [i.strip() for i in ids.split(',') if i.strip()]
            elif cmd[0] == 'save':
                data = {
                    'grid': grid,
                    'encounters': enc,
                    'size': [len(grid[0]), len(grid)]
                }
                if stairs_down:
                    data['stairs_down'] = stairs_down
                if stairs_up:
                    data['stairs_up'] = stairs_up
                if town:
                    data['town_portal'] = town
                save_json(path, data)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    while True:
        print("\nData Editor")
        print(" 1) Monsters\n 2) Items + Shop\n 3) Skills\n 4) Levels\n q) Quit")
        ch = input("> ").strip().lower()
        if ch == '1': monsters_menu()
        elif ch == '2': items_menu()
        elif ch == '3': skills_menu()
        elif ch == '4': level_menu()
        elif ch == 'q': break

if __name__ == '__main__':
    main()
