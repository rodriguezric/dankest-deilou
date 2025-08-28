# Dankest Deilou

Wizardry‑style dungeon RPG prototype built with Python and Pygame. It’s a single‑file game featuring a top‑down maze, a 4‑member party, town hub menus, and simple turn‑based battles with lightweight animations.

## Features
- Party management: create/dismiss characters; form up to 4 active.
- Town hub: Tavern, Form Party, Status, Training, Temple (heal/revive), Trader (shop).
- Exploration: top‑down dungeon with stairs and a town portal.
- Combat: turn‑based actions (Attack, Spell, Heal, Run) with simple hit effects.
- Items: small potion, basic weapon/armor; basic inventory use.
- Save/Load: JSON save file (`save.json`) in repo root.

## Requirements
- Python 3.10+
- Pygame 2.5+

## Setup
```bash
# (Optional) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install pygame
```

## Run
```bash
python main.py
```

## Controls
- Menus: Arrow keys (↑/↓), Enter/Space to confirm, Esc to go back.
- Maze: ←/→ to turn, ↑ to move forward, Esc opens the pause menu.

## Game Flow
- Title: New Game, Load, Exit.
- Town: Navigate to Tavern (create/dismiss), Form Party (choose active up to 4),
  Status, Training, Temple (heal/revive), Trader (shop), Enter the Labyrinth, Save/Load.
- Exploration: Walk the maze; random encounters may trigger battles.
- Battle: Choose actions per active member; defeat enemies to earn EXP and gold.
- Items: Use consumables and equip basics from the Trader.
- Save/Load: Accessible in‑game; data is stored in `save.json`.

## Project Structure
- `main.py`: Entire game (rendering, input, game states, battle system, etc.).
- `save.json`: Created/updated by the game when you save.
- `fonts/prstart.ttf`: Pixel font used by the UI (loaded at runtime).

## Notes
- Window size: 960×600; the top area shows the view/HUD and the bottom area is the log.
- If the font fails to load, the game falls back to a system font.
- Encounters, damage, and stats are intentionally simple/randomized for a prototype feel.

## Troubleshooting
- If the window fails to open or Pygame cannot initialize, ensure platform SDL dependencies are installed and that you’re using a recent Python and Pygame version.
- On headless/remote environments, a desktop session is required for Pygame display.

## License / Assets
This repository includes a bitmap‑style font at `fonts/prstart.ttf` for UI rendering. If you redistribute the project, ensure the font’s license terms are compatible with your use.

