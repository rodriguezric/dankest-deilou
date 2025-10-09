# Dankest Deilou – High-Level Specification

## Vision & Goals
- Deliver a nostalgic, Wizardry-style crawler that fits inside a single Python file while still feeling lively.
- Provide a full end-to-end loop: recruit a party, explore a dungeon, fight battles, return to town, and persist progress.
- Emphasise clarity over complexity so new content (monsters, items, rooms) can be added quickly.

## Target Audience
- Indie RPG fans who enjoy lightweight, turn-based dungeon crawlers.
- Developers looking for a compact reference project that demonstrates structuring a complete game in Python/Pygame.

## Platforms & Technology
- Runtime: Python 3.10+ with Pygame 2.5+.
- Windowed 960×600 display with pixel-font UI.
- Data-driven content via JSON (`data/`), single save file (`save.json`).

## Core Loop
1. **Town Hub** – manage the roster, heal, shop, and prepare.
2. **Party Formation** – choose up to four active adventurers.
3. **Labyrinth Exploration** – navigate a grid-based maze, encountering elites and random fights.
4. **Battle** – resolve AGI-based turn order combats with status effects, loot, and XP proxy rewards.
5. **Return to Town / Continue Deeper** – spend earnings, recruit replacements, and re-enter.

## Pillars
- **Snappy Turn-Based Combat** – concise actions, readable HUD, floating combat text.
- **Data-Driven Extensibility** – archetype-based monster scaling, JSON-configured encounters.
- **Approachable Presentation** – consistent font, simple colour coding, animated feedback (hits, heals, blink flicker).
- **Single-File Simplicity** – the entire runtime in `main.py` for ease of study and modification.

## Major Systems
- **State Machine** – manages title, town, battles, menus, and transitions.
- **Party & Character Model** – stats, inventory, statuses, and defend state.
- **Battle Engine** – initiative queue, AI, action execution, status ticks, floating text, blink/heal effects.
- **Maze Renderer** – top-down tile rendering, movement interpolation, elite patrol logic.
- **Audio Layer** – music manager for mode-based tracks, SFX manager for hits, heals, UI typing.
- **Persistence** – JSON save/load of party roster, inventory, dungeon position, and discovered chests.

## Content Overview
- **Classes**: Fighter, Mage, Priest, Rogue with base HP/MP tables and ability modifiers.
- **Monsters**: Archetype/tier-based scaling (e.g., skirmisher mobs, elite Vampire with Vamp stacks and Blink).
- **Items**: Consumables and equippables loaded from JSON, stock curated by `data/shop.json`.
- **Statuses**: Bleed, Vamp, Poison, Regen, Blind, Vulnerable, Weak, Stun, Blink, Reassemble.

## Out of Scope (Current Prototype)
- Multiplayer or network play.
- Procedural maze generation beyond static level templates.
- Deep narrative scripting or quest branching.
- High-fidelity animation beyond sprite cards and simple transforms.

## Key Risks & Mitigations
- **Single-file complexity** – mitigated by strong section headers, helper classes, and data-driven design.
- **Balance drift** – formulas kept simple; monsters scale via archetype heuristics to stay in a manageable band.
- **Content brittleness** – JSON loaders provide defaults so missing data fails gracefully; elite behaviours guarded by try/except.

## Future Opportunities
- Expand class skills and progression, introduce equipment bonuses.
- Add additional status types and combo interactions.
- Modularise `main.py` into packages for larger-scale development without losing the learning aspect.
