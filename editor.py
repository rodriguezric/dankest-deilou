#!/usr/bin/env python3
import json, os, sys
from typing import List, Dict, Any

DATA_DIR = 'data'
LVL_DIR = os.path.join(DATA_DIR, 'levels')

T_EMPTY, T_WALL, T_TOWN, T_STAIRS_D, T_STAIRS_U = 0, 1, 2, 3, 4

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
    shop_ids: List[str] = load_json(spath, [it.get('id') for it in items])
    def save_all():
        save_json(ipath, items)
        save_json(spath, shop_ids)
    while True:
        print("\nItems:")
        for i, it in enumerate(items):
            stock = ' [shop]' if it.get('id') in shop_ids else ''
            print(f" {i+1}. {it.get('id')} — {it.get('name')} ({it.get('type')}){stock}")
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
                if iid in shop_ids: shop_ids.remove(iid)
                save_all()
        elif ch == 's':
            i = int(prompt('index')) - 1
            if 0 <= i < len(items):
                iid = items[i].get('id')
                if iid in shop_ids: shop_ids.remove(iid)
                else: shop_ids.append(iid)
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
def base_grid(w=24,h=24):
    g=[[1]*w for _ in range(h)]
    for y in range(1,h-1):
        for x in range(1,w-1):
            g[y][x]=0
    return g

def print_grid(grid):
    ch={0:' ',1:'#',2:'T',3:'D',4:'U'}
    for y,row in enumerate(grid):
        print(''.join(ch.get(v,'?') for v in row))

def level_menu():
    os.makedirs(LVL_DIR, exist_ok=True)
    while True:
        print("\nLevel editor: enter level index (number) or q to return")
        s= input("> ").strip().lower()
        if s=='q': break
        try:
            ix=int(s)
        except:
            continue
        path=os.path.join(LVL_DIR, f'level{ix}.json')
        data=load_json(path, {})
        grid=data.get('grid') or base_grid()
        enc=data.get('encounters') or {"monsters": [], "group": [1,3]}
        stairs_down=data.get('stairs_down')
        stairs_up=data.get('stairs_up')
        town=data.get('town_portal')
        while True:
            print(f"\nEditing level {ix}. Commands: show, set x y tile(0..4), rect x1 y1 x2 y2 tile, stairsdown x y targetLevel, stairsup x y, town x y, monsters, save, back")
            cmd=input("> ").strip().lower().split()
            if not cmd: continue
            if cmd[0]=='back': break
            if cmd[0]=='show':
                print_grid(grid)
                print(f"stairs_down={stairs_down} stairs_up={stairs_up} town_portal={town}")
                print(f"encounters: {enc}")
            elif cmd[0]=='set' and len(cmd)==4:
                x,y,t=map(int,cmd[1:])
                if 0<=y<len(grid) and 0<=x<len(grid[0]):
                    grid[y][x]=t
            elif cmd[0]=='rect' and len(cmd)==6:
                x1,y1,x2,y2,t=map(int,cmd[1:])
                for y in range(min(y1,y2), max(y1,y2)+1):
                    for x in range(min(x1,x2), max(x1,x2)+1):
                        if 0<=y<len(grid) and 0<=x<len(grid[0]): grid[y][x]=t
            elif cmd[0]=='stairsdown' and len(cmd)==4:
                x,y,tgt=map(int,cmd[1:])
                stairs_down=[x,y]; grid[y][x]=T_STAIRS_D
                # set backlink in target level as stairs_up at same coords by default
                tpath=os.path.join(LVL_DIR, f'level{tgt}.json')
                tdata=load_json(tpath,{})
                tgrid=tdata.get('grid') or base_grid()
                tdata['grid']=tgrid
                tdata['stairs_up']=[x,y]
                if 0<=y<len(tgrid) and 0<=x<len(tgrid[0]): tgrid[y][x]=T_STAIRS_U
                save_json(tpath,tdata)
            elif cmd[0]=='stairsup' and len(cmd)==3:
                x,y=map(int,cmd[1:]); stairs_up=[x,y]; grid[y][x]=T_STAIRS_U
            elif cmd[0]=='town' and len(cmd)==3:
                if ix!=0:
                    print('Town link only allowed on level 0'); continue
                x,y=map(int,cmd[1:]); town=[x,y]; grid[y][x]=T_TOWN
            elif cmd[0]=='monsters':
                print(f"Current allowed monsters: {enc.get('monsters', [])} group={enc.get('group',[1,3])}")
                ids = prompt('ids (comma-separated)', ','.join(enc.get('monsters', [])))
                group = prompt('group (min,max)', '1,3')
                try:
                    mins,maxs=map(int,group.split(',')); enc['group']=[mins,maxs]
                except:
                    pass
                enc['monsters']=[i.strip() for i in ids.split(',') if i.strip()]
            elif cmd[0]=='save':
                data={'grid': grid, 'encounters': enc}
                if stairs_down: data['stairs_down']=stairs_down
                if stairs_up: data['stairs_up']=stairs_up
                if town and ix==0: data['town_portal']=town
                save_json(path,data)

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
