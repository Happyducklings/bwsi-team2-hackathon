# Extending Hidden Wall Maze

The game uses registries and data objects so most new content can be added
without changing the game loop.

After changing content, run:

```bash
python3 gamefinalfinal.py --test
```

## Add a map

Create the rows, then append one `LevelDefinition` to `LEVELS`:

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
            (3, 2): Consumable(
                "Potion",
                "Restores health when its use behavior is connected.",
                amount=2,
            ),
        },
        enemy_pool=("brute", "quizmaster"),
        enemy_types={(5, 1): "warden"},
    )
)
```

Required map symbols:

- `@`: exactly one starting position
- `K`: exactly one key
- `D`: exactly one exit
- `!`: zero or more enemies
- `*`: an item with a matching coordinate in `items`
- `#`: wall
- `.`: floor

The number and size of maps are not hard-coded. A level may contain any number
of enemies. If `enemy_pool` is omitted, difficulty is selected automatically.
An entry in `enemy_types` overrides one specific enemy coordinate.

## Add an enemy

Add one entry to `ENEMY_ARCHETYPES`:

```python
ENEMY_ARCHETYPES["archer"] = {
    "name": "Archer",
    "max_hp": 8,
    "contact_damage": 3,
    "wrong_answer_damage": 1,
    "armor": 0,
    "attack_range": 1,
}
```

Use `"archer"` in a level's `enemy_pool` or `enemy_types`. To include it in
automatic difficulty scaling, add it to a tuple in `DEFAULT_ENEMY_POOLS`.

## Add an item

Subclass `Item`, `PowerUp`, or `Consumable`. Implement `collect` only when the
new item needs behavior beyond the existing inventory systems:

```python
class HealingPotion(Consumable):
    def __init__(self, amount=1):
        super().__init__(
            "Healing Potion",
            "Restores HP when consumed.",
            amount,
        )
```

Put a `*` in a map and add the item at the same `(x, y)` coordinate in that
level's `items` dictionary. The map continues to hide its identity.

## Add an upgrade

Add one `UpgradeDefinition` to `UPGRADE_SPECS`:

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

The upgrade automatically becomes eligible for random end-of-level choices and
the `powerduck` debug console. Keep new persistent values in `PlayerState`.

## Add trivia

Append a dictionary to `TRIVIA_QUESTIONS`:

```python
TRIVIA_QUESTIONS.append(
    {
        "question": "What is 2 + 2?",
        "choices": ["3", "4", "5", "6"],
        "answer": 2,
    }
)
```

`answer` is one-based, matching the number displayed to the player.

## Add a new command or system

Reusable calculations belong in a small function near related systems. Player
data that must survive levels belongs in `PlayerState`; per-level state belongs
in `play_level`. Add a named self-test group to `run_self_tests` whenever a new
system changes combat, movement, visibility, inventory, or progression.
