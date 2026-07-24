# Hidden Wall Maze: Game and Developer Guide

## Run and test

```bash
python3 "game v2.py"
python3 "game v2.py" --test
```

The self-test simulates maps, upgrades, lighting, combat turns, enemy pursuit,
inventory stacking, item effects, death/reset behavior, and debug tools.

## Controls

| Input | Action |
|---|---|
| `W A S D` | Move one tile for 1 stamina |
| Multiple directions | Use unlocked Speed movement |
| `R` | Refill stamina, then give enemies a turn |
| `I` | Open the consumable inventory |
| `L` | Toggle the lamp after it is unlocked |
| `M` | Toggle persistent light-based map memory |
| `T` | Use the sword after finding it |
| `Q` | Quit or close the item menu |

Using a consumable costs zero stamina. Successfully using one still counts as
the player's action, so enemies receive their turn. Opening and closing the
item menu without using anything does not advance the turn.

## Turn order and combat

One normal round is:

1. The player moves, attacks, rests, or uses an item.
2. Every enemy outside attack range moves one shortest-path tile toward the
   player.
3. Every enemy now in range attacks.
4. Each enemy attack displays a trivia question.
5. A correct defensive answer blocks all damage from that attack. A wrong
   answer applies the enemy's configured damage, reduced by armor when present.
6. The next player turn begins. The player may attack or try to escape.

Contacting an enemy is the player's contact-trivia attack; it does not create a
separate contact-damage hit. A correct answer deals 3 trivia damage. The enemy
attacks only in the following enemy phase, preventing double attacks.

Sword attacks require a correct trivia answer, cost 5 stamina, and report the
enemy's remaining HP. Sword range and damage come from separate upgrade tracks.
Enemy ranged attacks require a clear cardinal line and cannot pass through
walls.

Death restores player HP and stamina and restores every living enemy's HP.
Discovered walls, enemies, items, and map memory remain.

## Player resources

- Base HP: 5
- Base stamina: 30
- Base damage: 0 until the sword is found
- Movement: 1 stamina per normal step
- Rest: refills stamina completely but advances the enemy turn
- Armor: separate durability that absorbs 80% of a hit

Speed uses stamina instead of charges. Its levels increase the maximum command
length and add command-level stamina discounts.

## Lighting

- The flashlight is directly north of the level-one start.
- It is permanent and always active after collection.
- Its rays stop at walls.
- The lamp is not available initially; it is a random end-level upgrade.
- Lamp durability and diagonal visibility are separate dependent upgrades.
- Map memory starts enabled, retaining anything revealed by light.

## Items and inventory

Every level receives one or two random consumables on empty floor tiles.
Currently registered consumables:

- Bomb: destroys one adjacent wall in a selected direction.
- Cookie: restores up to 5 HP.

All map items display as `*`; identity is revealed only on pickup. Consumables
stack by `item_key`. Picking up an existing type increases its quantity and
moves it to the top of the most-recently-collected inventory ordering.

The flashlight and sword are fixed power-up pickups:

- Level 1 `(1, 7)`: Flashlight
- Level 2 `(1, 9)`: Sword

## Map symbols

| Symbol | Meaning |
|---|---|
| `#` | Wall |
| `.` | Empty floor |
| `@` | Player start |
| `!` | Enemy spawn |
| `K` | Key |
| `D` | Exit |
| `*` | Hidden-identity item |

Each map requires exactly one player, key, and door. It may have any number of
enemies and items.

## Add a level

Levels are `LevelDefinition` objects. Each definition owns its rows, fixed
items, optional enemy pool, and coordinate-specific enemy overrides:

```python
new_map = [
    list("#######"),
    list("#@...!D"),
    list("#..*K.#"),
    list("#######"),
]

LEVELS.append(
    LevelDefinition(
        "Vault",
        new_map,
        items={
            (3, 2): Cookie(),
        },
        enemy_pool=("brute", "quizmaster"),
        enemy_types={(5, 1): "warden"},
    )
)
```

If `enemy_pool` is omitted, `DEFAULT_ENEMY_POOLS` supplies scaling based on
level number. A coordinate in `enemy_types` overrides the pool for that `!`.
One or two random registered consumables are added automatically.

## Add an enemy

Enemy types are data entries in `ENEMY_ARCHETYPES`:

```python
ENEMY_ARCHETYPES["archer"] = {
    "name": "Archer",
    "max_hp": 15,
    "attack_damage": 4,
    "armor": 1,
    "attack_range": 3,
}
```

Reference `"archer"` from a level's `enemy_pool` or `enemy_types`. Add it to a
tuple in `DEFAULT_ENEMY_POOLS` to include it in automatic difficulty scaling.

## Add a consumable

Create a `Consumable` subclass and register it in `CONSUMABLE_TYPES`:

```python
class EnergyDrink(Consumable):
    def __init__(self, amount=1):
        super().__init__(
            "Energy Drink",
            "Restores 10 stamina.",
            amount,
            item_key="energy_drink",
        )

    def use(self, context):
        state = context["player_state"]
        restored = min(10, state.max_stamina - state.stamina)
        if restored == 0:
            return False, "Stamina is already full."
        state.stamina += restored
        return True, f"Restored {restored} stamina."


CONSUMABLE_TYPES["energy_drink"] = EnergyDrink
```

The random spawner and inventory menu discover the new class from the registry.
Returning `False` from `use` preserves the item and does not advance the turn.

## Add a fixed power-up

Use `PowerUp` in a level's `items` dictionary and put `*` at the same map
coordinate:

```python
(3, 2): PowerUp(
    "Grappling Hook",
    "Unlocks gap crossing.",
    "grappling_hook",
)
```

Permanent data belongs in `PlayerState`. Add special collection behavior to
`PowerUp.collect` only when the power-up needs to initialize an upgrade track.

## Add an upgrade

Every upgrade is one self-contained `UpgradeDefinition` in `UPGRADE_SPECS`:

```python
UPGRADE_SPECS["critical_hit"] = UpgradeDefinition(
    "Critical Hit",
    max_level=4,
    describe=lambda level, state: (
        f"Gain a {level * 10}% critical-hit chance."
    ),
    is_available=lambda state: state.upgrades["sword"] > 0,
    on_apply=lambda state, level: None,
)
```

Registered upgrades automatically appear in eligible random choices and in the
`powerduck` debug console. Use `is_available` for prerequisites and `on_apply`
for side effects such as refilling armor.

## Add trivia

Append to `TRIVIA_QUESTIONS`:

```python
TRIVIA_QUESTIONS.append(
    {
        "question": "What is 2 + 2?",
        "choices": ["3", "4", "5", "6"],
        "answer": 2,
    }
)
```

Answers are one-based to match displayed choice numbers.

## Debugging

Enter `powerduck` during play to set any registered upgrade level. The console
enforces maximum levels and initializes flashlight/sword prerequisites.

For any new mechanic:

1. Keep persistent values in `PlayerState`.
2. Keep level-only values inside `play_level` or a dedicated context.
3. Put reusable rules in a named function.
4. Register data-driven content in the relevant dictionary.
5. Add a deterministic group to `run_self_tests`.
6. Run `python3 "game v2.py" --test`.
