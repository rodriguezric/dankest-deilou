# Dankest Deilou – Game Mechanics & Formulas

## Characters & Classes
| Class   | Base HP | Base MP | Key Notes |
|---------|---------|---------|-----------|
| Fighter | 12      | 0       | High STR/VIT; front-line defender. |
| Mage    | 6       | 8       | Access to Spark-style offensive spells. |
| Priest  | 8       | 6       | Party healer; Temple-style support. |
| Rogue   | 8       | 0       | High AGI, accuracy bonuses, skills like Backstab. |

- **Level & Stats**: Characters gain STR, IQ, PIE, VIT, AGI, LCK. Ability modifiers follow D&D-style `(stat - 10) // 2` conventions inside helper functions (`ability_mod`).
- **Derived Values**: Attack bonus, AC, hit points, and MP are recalculated from base class data plus equipment.

## Party Structure
- Active party limited to **four** members, drawn from a roster of up to **ten**.
- Active indices drive battle turn order and maze rendering.
- Defend action halves incoming damage (rounded up) until the character’s next turn.

## Enemy Scaling
- Enemies are defined in `data/monsters.json` by `archetype` and `tier`.
- Archetypes (`bruiser`, `skirmisher`, `acolyte`, `adept`) determine base HP, AC, AGI, and damage band.
- Tier modifiers:
  - **Mob**: baseline archetype values.
  - **Elite**: HP scaled to approx. total HP of a four-member party at current floor; AC +1; damage +10–15%.
  - **Boss**: HP ×2, AC +2, damage +25–35%.
- Floor number drives level-based scaling using helper `Enemy.from_base(base, floor_num)`.

## Exploration
- Maze: 24×24 grid, integer coordinates; player movement interpolated over 320 ms with optional footstep SFX.
- Elites may patrol via simple pattern descriptors (e.g., `up_down`).
- Random encounters triggered via threat meter (legacy system largely stubbed but hooks remain).

## Initiative & Turn Order
1. Collect tokens for alive active party members and living enemies.
2. Sort by descending AGI; ties resolved party-first, then index ascending.
3. Maintain `turn_order` list; rebuild whenever actors die or join mid-battle.

## Combat Resolution
### Player Basic Attack (`make_attack_action`)
- **Hit Chance**: `0.75 + ability_mod(agi) * 0.025 - (10 - enemy_ac) * 0.02`. Higher base accuracy and AGI scaling make nimble heroes land strikes more reliably.
- **Damage**: `randint(1, 6) + atk_bonus`, minimum 1.
- **Vulnerable** on target: ×1.5 (ceil). **Weak** on attacker: ×0.5 (ceil).

### Spells & Skills
- Most skills cost **1 MP** (deducted on use). Spark-style spells auto-hit.
- Custom skill entries map to bespoke action dicts (e.g., `sunder`, `combo`, `backstab`).

### Enemy Attacks
- Randomised via `enemy_choose_action` per monster id.
- Core enemies perform standard attacks: `hit = random() < base` (typically 0.6–0.7); damage from archetype attack band.
- Special behaviours scripted per id (e.g., Kobold Pack Yip, Goblin Chief summons).

### Vampire-Specific Mechanics
- **Vamp Stacks**: Applied to party members via Bite/Siphon. On start-of-turn they deal damage equal to current stack count, then decrement by 1. Total damage heals every living Vampire for the same amount (`_vampire_heal_from_vamp`).
- **Siphon**: One-time elite trigger at ≤25% HP. Applies 2 Vamp stacks to all party members, grants 3 Blink stacks to the Vampire.
- **Blink**: 100% evade against targeted attacks. Each MISS caused by Blink reduces stacks by 1; overlay flickers the enemy window while active.
- **Suck Blood**: Prefers targets already carrying Vamp stacks; damage heals the Vampire directly for the amount dealt.

### Status Effects
| Status      | Effect |
|-------------|--------|
| Bleed       | 1 damage at start of turn (no auto-expiry). |
| Vamp        | Stack-based damage equal to remaining stacks; decays by 1; heals Vampires. |
| Poison      | Deals `stacks` damage at start of turn; decays by 1. |
| Regen       | Heals for `stacks` each turn; decays by 1. |
| Blind       | Attacker’s next attack auto-misses and consumes one Blind stack. |
| Vulnerable  | Incoming damage ×1.5 (ceil); decrements when applied by certain skills. |
| Weak        | Outgoing damage ×0.5 (ceil). |
| Stun        | Skip turn and remove all stun stacks. |
| Blink       | See Vampire mechanics. |
| Reassemble  | Skeleton/Bone Pile transformation countdown. |

Status stacks cap at **9**. Messages logged on first application and expiry.

### Damage & Death
- HP never drops below 0. When a party member hits 0 HP they are flagged `alive = False`, added to `downed_party` for animation, and lose their turn.
- Enemies trigger `_on_enemy_defeated` hooks (e.g., Slime Mind regen, Skeleton bone piles) and fade out.
- Start-of-turn processing now checks for deaths caused by poison/vamp/bleed and immediately skips the turn if the actor is dead.

## Rewards & Economy
- Gold: Random within `[gold_low, gold_high]`, aggregated per enemy after victory.
- Drops: Each entry in `drops` evaluated via `random() < chance`.
- Experience currently abstracted; party power balanced primarily via equipment and consumables.

## Items & Inventory
- Data-driven from `data/items.json`.
- Consumables specify fixed or range heals/MP restoration (applied via `make_item_use_action`).
- Equipment modifies attack bonus and AC; recalculated when equipping.
- Trader inventory defined in `data/shop.json` order; Temple and other services use hard-coded pricing constants.

## Saving & Loading
- `save.json` stores party roster, inventory, gold, dungeon position, discovered chests/elite states, and threat meters.
- On load, `Game.load_data()` repopulates item and monster dictionaries, then merges save state.

## Randomness & Determinism
- Python’s `random` module used globally; no explicit seeding on load.
- Battle AI uses multiple `random.random()`/`randint()` calls; results are inherently non-deterministic across runs.

## Audio & Feedback
- Music crossfades on mode changes; elite battles trigger `MUSIC_ELITE_BATTLE`.
- SFX triggered for hits, heals, misses, footsteps, typewriter log.
- Floating text uses duration-based pruning (`floaters`) to keep HUD clean.
