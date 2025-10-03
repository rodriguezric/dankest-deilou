#!/usr/bin/env python3
"""Utility script to spin up a battle with preset parties for quick testing."""

import argparse
import json
import random
from pathlib import Path
from typing import List

import pygame

import main


CLASS_ALIASES = {
    "fighter": "Fighter",
    "mage": "Mage",
    "priest": "Priest",
    "rogue": "Rogue",
}

try:
    import argcomplete
except ImportError:  # pragma: no cover - optional dependency
    argcomplete = None


def _load_monster_ids() -> List[str]:
    try:
        monsters_path = Path("data/monsters.json")
        data = json.loads(monsters_path.read_text())
        return sorted({m.get("id", "") for m in data if m.get("id")})
    except Exception:
        return []


def _comma_completer(choices: List[str]):
    def _complete(prefix: str, parsed_args, **_kwargs):
        base = ""
        token = prefix
        if "," in prefix:
            base, token = prefix.rsplit(",", 1)
            base += ","
        token = token.lower()
        matches = []
        for choice in choices:
            low = choice.lower()
            if low.startswith(token):
                matches.append(f"{base}{choice}")
        return matches

    return _complete


def parse_class_list(raw: str) -> List[str]:
    entries = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not entries:
        raise ValueError("party list cannot be empty")
    result = []
    for key in entries:
        if key not in CLASS_ALIASES:
            raise ValueError(f"unknown class '{key}'")
        result.append(CLASS_ALIASES[key])
    return result


def parse_enemy_ids(raw: str) -> List[str]:
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    if not ids:
        raise ValueError("enemy list cannot be empty")
    return ids


def build_party(game: "main.Game", class_names: List[str]) -> None:
    party = game.party
    party.members = []
    for idx, cls_name in enumerate(class_names, start=1):
        member = main.Character(name=f"{cls_name[:3]}#{idx}", cls=cls_name)
        party.members.append(member)
    party.active = list(range(len(party.members)))
    party.clamp_active()
    game.refresh_party_gear_bonuses()


def build_enemies(game: "main.Game", enemy_ids: List[str], floor: int) -> List[main.Enemy]:
    enemies: List[main.Enemy] = []
    for mid in enemy_ids:
        base = game.monsters_by_id.get(mid)
        if not base:
            raise ValueError(f"enemy id '{mid}' not found in data/monsters.json")
        enemies.append(main.Enemy.from_base(base, floor_num=floor))
    return enemies


def main_entry() -> None:
    parser = argparse.ArgumentParser(description="Launch a battle scene with canned parties.")
    party_arg = parser.add_argument(
        "--party",
        default="Fighter,Rogue,Priest,Mage",
        help="Comma-separated party classes (Fighter,Rogue,Priest,Mage).",
    )
    enemies_arg = parser.add_argument(
        "--enemies",
        required=True,
        help="Comma-separated monster ids drawn from data/monsters.json (e.g., kobold,goblin)",
    )
    parser.add_argument("--floor", type=int, default=1, help="Floor number to scale enemies (default: 1).")
    parser.add_argument("--seed", type=int, default=None, help="Seed the RNG for repeatable tests.")
    parser.add_argument(
        "--intro",
        action="store_true",
        help="Play the combat intro flashes instead of jumping straight into battle.",
    )
    if argcomplete:
        class_choices = sorted(set(list(CLASS_ALIASES.keys()) + list(CLASS_ALIASES.values())))
        monster_choices = _load_monster_ids()
        party_arg.completer = _comma_completer(class_choices)
        enemies_arg.completer = _comma_completer(monster_choices)
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    try:
        classes = parse_class_list(args.party)
        enemy_ids = parse_enemy_ids(args.enemies)
    except ValueError as exc:
        parser.error(str(exc))

    floor = max(1, int(args.floor))

    game = main.Game()
    build_party(game, classes)
    enemies = build_enemies(game, enemy_ids, floor)

    battle = main.Battle(game.party, game.log, game.effects, game.items_by_id, game.monsters_by_id, game.skills_config, game.sfx)
    battle.floor_num = floor
    battle.enemies = enemies
    battle.build_turn_order()
    battle.turn_pos = 0
    battle.log.add("Battle test launched.")

    game.in_battle = battle
    if args.intro:
        game.mode = main.MODE_COMBAT_INTRO
        game.combat_intro_active = True
        game.combat_intro_stage = 0
        game.combat_intro_t0 = pygame.time.get_ticks()
        game.combat_intro_done_triggered = False
    else:
        game.mode = main.MODE_BATTLE
        game.combat_intro_active = False
        game.combat_intro_stage = 3
        game.combat_intro_done_triggered = True
        battle.next_turn()

    summary_party = ", ".join(f"{m.name} ({m.cls})" for m in game.party.members)
    summary_enemies = ", ".join(f"{e.name}" for e in enemies)
    print(f"Party: {summary_party}")
    print(f"Enemies: {summary_enemies} [floor {floor}]")

    game.run()


if __name__ == "__main__":
    main_entry()
