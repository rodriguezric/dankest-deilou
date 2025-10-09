# Dankest Deilou – Functional Specification

## 1. Application Shell
### 1.1 Launch & Title Screen
- Display title logo, New Game, Load Game, Exit options.
- Keyboard navigation: ↑/↓ to move, Enter to confirm, Esc to quit.
- New Game initialises default roster, party, dungeon level, and town mode.
- Load Game reads `save.json` if present; failure returns to Title with toast message.

### 1.2 Mode Transitions
- Main mode constants (TITLE, TOWN, MAZE, BATTLE, etc.) drive rendering and input dispatch.
- `Game.on_mode_changed` handles audio crossfades, scene fades, and resets per-mode UI indices.

## 2. Town Hub
### 2.1 Tavern (Create / Dismiss)
- Create: prompts for name (typewriter entry), class selection, ability roll, trait selection (if enabled).
- Dismiss: list of roster members; confirmation prompt before removal.

### 2.2 Form Party
- Shows roster with active markers; allows toggling up to four active slots.
- Prevents duplicates and enforces alive-only selection.

### 2.3 Status Screen
- Displays detailed stats, equipment, and status effects for each member.
- Horizontal navigation between members; vertical to inspect sections (attributes, resistances, statuses).

### 2.4 Training (XP Proxy)
- Placeholder stub for future leveling; currently surfaces flavour text/UI layout.

### 2.5 Temple
- **Heal Party**: fixed gold cost (`TEMPLE_HEAL_PARTY_COST`). Restores HP to all living party members.
- **Revive Member**: list of downed characters; cost `REVIVE_BASE_COST + level * REVIVE_PER_LEVEL`. Revived members return with partial HP.

### 2.6 Trader (Shop)
- Stock pulled from `data/shop.json` by item id.
- Buy/Sell flows include confirmation menus and inventory updates.

### 2.7 Save/Load Menu
- In-town overlay lists Save, Load, Back. Save writes `save.json`; Load reloads into town mode.

### 2.8 Exit Options
- Exit to Title and quit confirmation dialogues available from town pause menu.

## 3. Maze Exploration
- Grid-based movement with smooth interpolation; arrow-key rotation and forward advance.
- Encounter triggers: random threat meter and fixed elites (from level definitions).
- UI overlays for coordinates, minimap (if unlocked), threat indicator (legacy support).
- Interaction with chests/NPCs defined per-level; collected chests removed from save state.

## 4. Battle System
### 4.1 HUD
- Top area displays enemy windows with HP, statuses, Blink flicker; bottom shows party cards mirroring active roster.
- Left-side (or overlay) indicates initiative order and highlights current actor.
- Message log at bottom with typewriter reveal, SFX integration.

### 4.2 Turn Flow
1. Build initiative queue via `Battle.build_turn_order`.
2. On actor turn, run `_start_of_turn_effects`; if returns True (stun/death), skip to next actor.
3. Party turn -> Command menu (Attack, Skill, Item, Defend, Run). Input through arrow keys/Enter; invalid options beep.
4. Enemy turn -> `enemy_choose_action` selects action dict; falls back to basic attack if None.
5. `start_animation` triggers staged animation and ultimately `resolve_action_impact`.
6. After action, apply post-delay, rebuild turn order if necessary, advance.

### 4.3 Actions & AI
- **Attack**: Standard damage roll; supports tags (`bone_bash`, `apply_vamp`).
- **Skills**: Data-driven mapping per class; includes custom timing adjustments (e.g., Backstab pre-stage longer).
- **Item Use**: Consumables read heal/MP ranges; equipping blocked mid-battle.
- **Run**: 55% success chance; on success, battle ends in defeat for encounter (player flees).
- **Enemies**: Each id may override behaviour (Goblin Chief summons, Slime Mind commands slimes, Vampire Siphon/Blink).

### 4.4 Status Management
- `_status_get/add/set/dec` utilities manage capped stacks, logging on entry/expiry.
- Start-of-turn pipeline handles Poison, Vamp, Bleed, Regen, Vulnerable, Weak, Stun.
- Blink intercepts targeted attacks, forcing MISS and consuming one stack per deflected attack.

### 4.5 Victory & Defeat
- Victory: triggers reward screen, distributes gold/drops, logs outcome, returns to town (or next maze step).
- Defeat: all party members at 0 HP -> defeat mode with fade-out and return to title or load.

## 5. Audio & Feedback
- `MusicManager` crossfades between town, labyrinth, battle, elite battle, prologue, ending tracks.
- `SfxManager` handles `enemy_hurt`, `party_hurt`, `heal`, `miss`, `step`, `typer`, etc.
- HitEffects system offsets sprites, flashes borders, and handles Blink overlay.
- Floating text queue displays damage/heals/status keywords with lifetime-based pruning.

## 6. Persistence
- Save file stores: roster (stats, equipment, statuses), inventory, gold, town indices, dungeon position, elite states, discovered chests, threat meter, music toggles.
- Loading reinstantiates character objects, rebuilds party active list, and repopulates `Game` state.

## 7. Tooling & Data Pipelines
- **Monsters**: `data/monsters.json`. Each entry includes id, name, archetype, tier, gold range, drops.
- **Items**: `data/items.json` for all gear/consumables; `data/shop.json` for trader stock order.
- **Levels**: `data/levels/*.json` describe tile grids, chests, NPCs, elites (patrol pattern).
- **Scripts**: Auxiliary tools under `scripts/` (e.g., export/import helpers, testing harness).

## 8. Extensibility Hooks
- AI and statuses built around dictionary dispatch; adding new monster behaviours requires extending `enemy_choose_action` / `resolve_action_impact`.
- Renderer exposes status colour map and stack ordering; additional statuses slot into arrays.
- Maze generator uses `generate_base_grid`; additional room patterns can be inserted there or via level files.

## 9. Error Handling & Debug
- JSON loads wrapped in try/except; on failure, fall back to defaults (empty lists/dicts).
- Battle AI guard clauses ensure dead indices are skipped.
- Missing font gracefully reverts to system font.
- `battle_test.py` enables CLI-driven combat simulations with specified monster line-ups.

