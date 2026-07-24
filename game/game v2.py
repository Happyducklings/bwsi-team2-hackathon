import importlib.util
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

WALL = "#"
FLOOR = "."
PLAYER = "@"
DOOR = "D"
KEY = "K"
NPC = "!"
ITEM_TILE = "*"

DIRECTIONS = {
    "w": (0, -1),
    "s": (0, 1),
    "a": (-1, 0),
    "d": (1, 0),
}

FACING_NAMES = {
    (0, -1): "north",
    (0, 1): "south",
    (-1, 0): "west",
    (1, 0): "east",
}


class Item:
    """Base class for every item that can appear as * on the map."""

    item_type = "item"

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def collect(self, player_state):
        """Apply the item to the player's persistent state."""
        raise NotImplementedError

    def pickup_message(self):
        return f"You picked up {self.name}! {self.description}"


class PowerUp(Item):
    """A permanent upgrade that stays active after it is collected."""

    item_type = "power-up"

    def __init__(self, name, description, effect):
        super().__init__(name, description)
        self.effect = effect

    def collect(self, player_state):
        player_state.powerups.add(self.effect)
        if self.effect == "flashlight":
            player_state.upgrades["flashlight"] = max(
                1, player_state.upgrades["flashlight"]
            )


class Consumable(Item):
    """A stackable item represented by an amount in the inventory."""

    item_type = "consumable"

    def __init__(self, name, description, amount=1):
        super().__init__(name, description)
        self.amount = amount

    def collect(self, player_state):
        player_state.consumables[self.name] += self.amount

    def pickup_message(self):
        return (
            f"You picked up {self.name} x{self.amount}! "
            f"{self.description}"
        )


STAMINA_BONUSES = (5, 10, 10, 15)
SWORD_DAMAGE_BONUSES = (3, 5, 8, 11)
HP_BONUSES = (5, 5, 5, 5)
LAMP_DURABILITY_BY_LEVEL = (3, 5, 7, 10, 14)
SWORD_STAMINA_COST = 5
MOVEMENT_STAMINA_COST = 1


class PlayerState:
    """Stats, inventory, and permanent upgrades shared between levels."""

    def __init__(self):
        self.base_hp = 5
        self.upgrades = defaultdict(int)
        self.powerups = set()
        self.consumables = defaultdict(int)
        self.hp = self.max_hp
        self.armor_durability = 0
        self.stamina = self.max_stamina
        self.lamp_uses = self.lamp_capacity
        self.speed_uses = self.speed_uses_per_level

    @property
    def max_hp(self):
        level = self.upgrades["hp"]
        return self.base_hp + sum(HP_BONUSES[:level])

    @property
    def max_stamina(self):
        level = self.upgrades["stamina"]
        return 20 + sum(STAMINA_BONUSES[:level])

    @property
    def damage(self):
        if self.upgrades["sword"] == 0:
            return 0
        level = self.upgrades["sword_damage"]
        return 5 + sum(SWORD_DAMAGE_BONUSES[:level])

    @property
    def lamp_capacity(self):
        return LAMP_DURABILITY_BY_LEVEL[self.upgrades["lamp_duration"]]

    @property
    def speed_uses_per_level(self):
        level = self.upgrades["speed"]
        return 0 if level == 0 else level + 1

    @property
    def speed_max_steps(self):
        level = self.upgrades["speed"]
        if level == 0:
            return 1
        return 3 if level >= 3 else 2

    def start_level(self):
        self.hp = self.max_hp
        self.stamina = self.max_stamina
        self.lamp_uses = self.lamp_capacity
        self.speed_uses = self.speed_uses_per_level

    def respawn(self):
        self.hp = self.max_hp
        self.stamina = self.max_stamina

    def take_damage(self, amount):
        """Apply one hit. Return (died, description)."""
        if self.armor_durability > 0:
            self.armor_durability -= 1
            hp_damage = max(1, (amount + 4) // 5)
            self.hp -= hp_damage
            armor_message = (
                f"Armor absorbed 80% of the {amount}-damage hit; "
                f"{hp_damage} reached HP "
                f"({self.armor_durability} armor durability left)."
            )
            if self.hp <= 0:
                return True, armor_message + " You were defeated."
            return False, armor_message + f" HP: {self.hp}/{self.max_hp}."

        self.hp -= amount
        if self.hp <= 0:
            return True, f"You took {amount} damage and were defeated."
        return False, f"You took {amount} damage ({self.hp}/{self.max_hp} HP)."


class Enemy:
    """A trivia enemy that can also be damaged with the sword."""

    def __init__(
        self,
        name,
        max_hp,
        contact_damage=3,
        wrong_answer_damage=1,
        armor=0,
        attack_range=0,
    ):
        self.name = name
        self.max_hp = max_hp
        self.hp = max_hp
        self.contact_damage = contact_damage
        self.wrong_answer_damage = wrong_answer_damage
        self.armor = armor
        self.attack_range = attack_range

    def take_damage(self, amount):
        actual_damage = max(1, amount - self.armor)
        self.hp -= actual_damage
        return actual_damage


class LevelDefinition:
    """All configurable content for one map."""

    def __init__(
        self,
        name,
        rows,
        items=None,
        enemy_types=None,
        enemy_pool=None,
    ):
        self.name = name
        self.rows = rows
        self.items = items or {}
        self.enemy_types = enemy_types or {}
        self.enemy_pool = enemy_pool


# Add an archetype here once, then reference its key from any level.
ENEMY_ARCHETYPES = {
    "trivia_guard": {
        "name": "Trivia Guard",
        "max_hp": 5,
        "contact_damage": 3,
        "wrong_answer_damage": 1,
        "armor": 0,
        "attack_range": 0,
    },
    "brute": {
        "name": "Brute",
        "max_hp": 9,
        "contact_damage": 4,
        "wrong_answer_damage": 1,
        "armor": 0,
        "attack_range": 0,
    },
    "quizmaster": {
        "name": "Quizmaster",
        "max_hp": 7,
        "contact_damage": 3,
        "wrong_answer_damage": 2,
        "armor": 0,
        "attack_range": 1,
    },
    "sentinel": {
        "name": "Sentinel",
        "max_hp": 12,
        "contact_damage": 5,
        "wrong_answer_damage": 1,
        "armor": 2,
        "attack_range": 1,
    },
    "warden": {
        "name": "Warden",
        "max_hp": 16,
        "contact_damage": 5,
        "wrong_answer_damage": 2,
        "armor": 3,
        "attack_range": 1,
    },
}

# New levels automatically use the last pool after these difficulty bands.
DEFAULT_ENEMY_POOLS = (
    ("trivia_guard",),
    ("trivia_guard", "brute"),
    ("brute", "quizmaster"),
    ("quizmaster", "sentinel"),
    ("sentinel", "warden"),
)


def create_enemy(archetype_key):
    try:
        stats = ENEMY_ARCHETYPES[archetype_key]
    except KeyError as error:
        raise ValueError(f"Unknown enemy archetype: {archetype_key}") from error
    return Enemy(**stats)


def default_enemy_pool(level_number):
    index = min(level_number - 1, len(DEFAULT_ENEMY_POOLS) - 1)
    return DEFAULT_ENEMY_POOLS[index]


class UpgradeDefinition:
    """One self-contained progression-tree entry."""

    def __init__(
        self,
        name,
        max_level,
        describe,
        is_available=None,
        on_apply=None,
    ):
        self.name = name
        self.max_level = max_level
        self.describe = describe
        self.is_available = is_available or (lambda player_state: True)
        self.on_apply = on_apply or (lambda player_state, level: None)


def describe_sword(level, player_state):
    if level == 1:
        return (
            f"Unlock the sword: 1-tile range, 5 base damage, "
            f"{SWORD_STAMINA_COST} stamina per attack."
        )
    if level == 4:
        return "Attack the entire chosen row or column until a wall."
    return f"Increase the sword's straight attack range to {level} tiles."


def describe_flashlight(level, player_state):
    descriptions = {
        2: "Add one visible diagonal tile on each side of the beam.",
        3: "Reveal three tiles ahead and two diagonal rows.",
        4: "Reveal four tiles ahead and three diagonal rows.",
    }
    return descriptions[level]


def apply_armor_upgrade(player_state, level):
    player_state.armor_durability = level


def apply_hp_upgrade(player_state, level):
    player_state.hp = player_state.max_hp


# Adding an upgrade now requires one entry here. Its description, prerequisite,
# maximum level, and apply behavior stay together.
UPGRADE_SPECS = {
    "lamp_duration": UpgradeDefinition(
        "Lamp Durability",
        4,
        lambda level, state: (
            f"Increase lamp durability to "
            f"{LAMP_DURABILITY_BY_LEVEL[level]} uses per level."
        ),
    ),
    "lamp_diagonal": UpgradeDefinition(
        "Wide Lamp",
        1,
        lambda level, state: (
            "The lamp also reveals all four adjacent diagonal tiles."
        ),
    ),
    "flashlight": UpgradeDefinition(
        "Flashlight Beam",
        4,
        describe_flashlight,
        is_available=lambda state: "flashlight" in state.powerups,
    ),
    "armor": UpgradeDefinition(
        "Armor",
        4,
        lambda level, state: (
            f"Reduce the next {level} hits by 80%. "
            f"Upgrading fully resets armor durability."
        ),
        on_apply=apply_armor_upgrade,
    ),
    "hp": UpgradeDefinition(
        "Maximum HP",
        4,
        lambda level, state: (
            f"Gain +{HP_BONUSES[level - 1]} maximum HP "
            f"(new maximum: {state.max_hp + HP_BONUSES[level - 1]})."
        ),
        on_apply=apply_hp_upgrade,
    ),
    "speed": UpgradeDefinition(
        "Speed",
        4,
        lambda level, state: (
            f"Use up to {3 if level >= 3 else 2} movement inputs at once, "
            f"{level + 1} times per level."
        ),
    ),
    "sword": UpgradeDefinition(
        "Sword Area",
        4,
        describe_sword,
    ),
    "stamina": UpgradeDefinition(
        "Stamina",
        4,
        lambda level, state: (
            f"Gain +{STAMINA_BONUSES[level - 1]} maximum stamina "
            f"(new maximum: "
            f"{state.max_stamina + STAMINA_BONUSES[level - 1]})."
        ),
    ),
    "sword_damage": UpgradeDefinition(
        "Sword Damage",
        4,
        lambda level, state: (
            f"Gain +{SWORD_DAMAGE_BONUSES[level - 1]} sword damage "
            f"(new damage: "
            f"{state.damage + SWORD_DAMAGE_BONUSES[level - 1]})."
        ),
        is_available=lambda state: state.upgrades["sword"] > 0,
    ),
    "extra_choice": UpgradeDefinition(
        "Expanded Choices",
        1,
        lambda level, state: (
            "See four random upgrade choices instead of three after each level."
        ),
    ),
}


# Edit these 2D arrays to design each level manually.
# Use # for walls, . for floors, @ for the player, ! for NPCs, K for the key,
# D for the door, and * for an item whose identity is hidden until pickup.
# Every row in one level must have the same number of cells.
LEVEL_MAPS = [
    [
        list("##########"),
        list("#.!......D"),
        list("#....!...#"),
        list("#..##...!#"),
        list("#..#..#..#"),
        list("#.#.#.#..#"),
        list("#.!..#...#"),
        list("#*..##!K.#"),
        list("#@.......#"),
        list("##########"),
    ],
    [
        list("############"),
        list("#..!.......D"),
        list("#.......!..#"),
        list("#...##..#..#"),
        list("#.#.#......#"),
        list("#..#.##.#..#"),
        list("#.#....##..#"),
        list("#.#.!..#.#.#"),
        list("#...##.....#"),
        list("#.!.#...#K.#"),
        list("#@......!..#"),
        list("############"),
    ],
    [
        list("##############"),
        list("#...!........D"),
        list("#.........!..#"),
        list("#...#...##...#"),
        list("#..#.!..#....#"),
        list("#.##..##.....#"),
        list("#.....#......#"),
        list("#..#.#..###..#"),
        list("#...#....#...#"),
        list("#..###..#.#..#"),
        list("#.#.!..#.....#"),
        list("#.#...##..#K.#"),
        list("#@......!....#"),
        list("##############"),
    ],
    [
        list("################"),
        list("#....!.........D"),
        list("#..........!...#"),
        list("#....#....##...#"),
        list("#..##...#.#.#..#"),
        list("#..#.!..#.#....#"),
        list("#.#.....#..#...#"),
        list("#.#.#.##..#....#"),
        list("#.....#.#...#..#"),
        list("#....#.....##..#"),
        list("#...##..#.#.#..#"),
        list("#..#....!#.....#"),
        list("#.#.....#......#"),
        list("#.#...##..#..K.#"),
        list("#@.....!.......#"),
        list("################"),
    ],
    [
        list("##################"),
        list("#.....!..........D"),
        list("#............!...#"),
        list("#...##....##.....#"),
        list("#..#.....#...#...#"),
        list("#.#.....#.....#..#"),
        list("#..#...#.....#...#"),
        list("#....##....##....#"),
        list("#....##....#.....#"),
        list("#.#.#...#.#...#..#"),
        list("#..#.....#.......#"),
        list("#.#.##..#..#..#..#"),
        list("#...!..#....##...#"),
        list("#.#...###...#.#..#"),
        list("#.#..#.....#.....#"),
        list("#..!##....##...K.#"),
        list("#@......!........#"),
        list("##################"),
    ],
]

# Each level owns its map, items, and optional enemy configuration.
# `enemy_pool` may override automatic difficulty scaling for a whole level.
# `enemy_types={(x, y): "warden"}` may override one specific ! tile.
LEVELS = [
    LevelDefinition(
        "Level 1",
        LEVEL_MAPS[0],
        items={
            (1, 7): PowerUp(
                "Flashlight",
                "It permanently reveals the two tiles directly in front of you.",
                "flashlight",
            ),
        },
    ),
    LevelDefinition("Level 2", LEVEL_MAPS[1]),
    LevelDefinition("Level 3", LEVEL_MAPS[2]),
    LevelDefinition("Level 4", LEVEL_MAPS[3]),
    LevelDefinition("Level 5", LEVEL_MAPS[4]),
]

# Add or edit trivia questions here. The answer is the number of the correct choice.
TRIVIA_QUESTIONS = [
    {
        "question": "What does the 'S' in HTTPS stand for?",
        "choices": ["Secure", "Server", "Simple", "Standard"],
        "answer": 1,
    },
    {
        "question": "If a security measure or control fails, the system is not rendered to an insecure state! Which NSA design principle does this statement describe?",
        "choices": ["Least Privilege", "Separation of Duties", "Fail-Safe Default", "Defense in Depth"],
        "answer": 3,
    },
    {
        "question": "What’s the name of the first major cyber attack?",
        "choices": ["Wannacry", "The Creeper Worm", "The Morris Worm", "ILOVEYOU"],
        "answer": 3,
    },
    {
        "question": "Which of the following would be the best technology for a device to wirelessly connect to a speaker?",
        "choices": ["Wi-Fi", "NFC", "5G", "Bluetooth"],
        "answer": 4,
    },
    {
        "question": "Your boss would like you to test a new software update in a controlled environment before releasing it to the whole organization. Which Best Practice should be utilized to minimize the risk to the production system?",
        "choices": ["Virtual machine", "Cloud computing", "Sandbox", "RDP"],
        "answer": 3,
    },
    {
        "question": "What type of malicious software is designed to look like a helpful or safe program, but actually performs harmful actions once installed?",
        "choices": ["Worm", "Trojan Horse", "Ransomware", "Spyware"],
        "answer": 2,
    },
    {
        "question": "What do the initials 'DDoS' stand for in relation to cyber attacks?",
        "choices": ["Domain Detection of Suspicious Behavior", "Distributed Denial of Service", "Data Destruction on Site", "Direct Denial of Service"],
        "answer": 2,
    },
    {
        "question": "In a company, what should you do first if you suspect a phishing attack?",
        "choices": ["Check reddit", "Click the link", "Screenshot and share with friends", "Report to IT or security"],
        "answer": 4,
    },
    {
        "question": "Which type of cyber attack aims to deceive users into providing sensitive information?",
        "choices": ["DDoS", "Phishing", "Ransomware", "Malware"],
        "answer": 2,
    },
    {
        "question": "What’s a common trick in a spoof page?",
        "choices": ["Extra Buttons", "Bold text", "Bright colors", "Misspelled domain"],
        "answer": 4,
    },
]



# Per-level passwords the player must enter after leaving the SSH challenge
# container. The values match what's stashed in the per-level Dockerfile
# layouts; level 1's is the shared `maze2024` baked into the Dockerfile
# today, and levels 2-5 are placeholders until the team designs those
# challenges.
LEVEL_PASSWORDS = {
    1: "maze2024",
    2: "tbd-level-2",
    3: "tbd-level-3",
    4: "tbd-level-4",
    5: "tbd-level-5",
}


# Absolute path to the refactored launcher module, used to hand the
# terminal to the per-level Docker container when the player steps on a
# door. The launcher is imported lazily inside ``run_door_challenge`` so
# the rest of the game (and ``--test``) doesn't pay any import cost.
_LAUNCHER_PATH = (
    Path(__file__).resolve().parent.parent
    / "bwsi-team2-dockerfile"
    / "launcher.py"
)


def _load_launcher():
    """Import the launcher module by file path and return it."""
    spec = importlib.util.spec_from_file_location(
        "bwsi_team2_launcher", str(_LAUNCHER_PATH)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load launcher spec from {_LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_door_password(entered, level_number):
    """Return True if ``entered`` unlocks the given level's door.

    Pulled out as a tiny pure function so the self-tests can exercise the
    password gate without touching Docker, SSH, or the launcher module.
    """
    expected = LEVEL_PASSWORDS.get(level_number)
    if expected is None:
        return False
    return entered == expected


def _read_door_password(level_number):
    """Prompt for the level password; hide input when a TTY is available.

    Returns the entered string (whitespace-stripped), or raises EOFError
    if input is closed. ``run_door_challenge`` treats EOFError as
    'abandoned' and returns to the maze rather than crashing.
    """
    prompt = f"Enter the Level {level_number} password to proceed: "
    try:
        import getpass

        try:
            return getpass.getpass(prompt).strip()
        except (ValueError, getpass.GetPassWarning):
            # getpass raises ValueError if no TTY is attached. Fall through
            # to a visible prompt so the game still works in scripts/pipes.
            print(
                "[launcher] (No TTY available — password will be visible.)",
                file=sys.stderr,
            )
            return input(prompt).strip()
    except ImportError:  # pragma: no cover - getpass is always present
        return input(prompt).strip()


def run_door_challenge(level_number, player_state, *, first_attempt=True):
    """Hand the terminal to the per-level Docker/SSH challenge.

    Builds the image, starts the container, drops the player into the SSH
    session, then — when the player types ``exit`` — asks for the level
    password. A wrong answer relaunches the SSH session automatically. A
    right answer (or a Ctrl-C / EOF) returns control to the maze.
    """
    try:
        launcher = _load_launcher()
    except (FileNotFoundError, ImportError) as error:
        print(
            f"[launcher] Could not load the docker launcher from "
            f"{_LAUNCHER_PATH}: {error}",
            file=sys.stderr,
        )
        print(
            "[launcher] Skipping the SSH challenge for this level. "
            "The password gate is therefore disabled.",
            file=sys.stderr,
        )
        return

    first_time = first_attempt
    while True:
        clear_screen()
        if first_time:
            launcher.wait_for_keypress(level=level_number)
        first_time = False

        if launcher.build_image(level=level_number) != 0:
            return
        if launcher.start_container(level=level_number) != 0:
            return
        if not launcher.wait_for_ssh():
            print(
                f"[launcher] SSH port never came up for level {level_number}."
            )
            return

        # Blocks until the SSH session exits.
        launcher.launch_ssh_in_place(level=level_number)

        clear_screen()
        print("=" * 60)
        print("  You have left the challenge container.")
        print(f"  Enter the Level {level_number} password to proceed.")
        print("=" * 60)

        try:
            entered = _read_door_password(level_number)
        except (EOFError, KeyboardInterrupt):
            print("\n[launcher] Challenge abandoned; returning to the maze.")
            return

        if _check_door_password(entered, level_number):
            return

        print("Incorrect password. Reconnecting to the challenge...")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def build_level(level_number):
    """Build and validate one data-driven level definition."""
    if not 1 <= level_number <= len(LEVELS):
        raise ValueError(f"Unknown level number: {level_number}.")

    definition = LEVELS[level_number - 1]
    maze = [row[:] for row in definition.rows]

    if not maze or not maze[0]:
        raise ValueError(f"Level {level_number} is empty.")

    width = len(maze[0])
    if any(len(row) != width for row in maze):
        raise ValueError(f"Every row in level {level_number} must have the same length.")

    allowed_tiles = {WALL, FLOOR, PLAYER, DOOR, KEY, NPC, ITEM_TILE}
    positions = {PLAYER: [], DOOR: [], KEY: [], NPC: []}
    item_tiles = set()

    for y, row in enumerate(maze):
        for x, tile in enumerate(row):
            if tile not in allowed_tiles:
                raise ValueError(
                    f"Invalid tile {tile!r} at ({x}, {y}) in level {level_number}."
                )
            if tile in positions:
                positions[tile].append((x, y))
            if tile == ITEM_TILE:
                item_tiles.add((x, y))

    for tile, name in ((PLAYER, "player"), (DOOR, "door"), (KEY, "key")):
        if len(positions[tile]) != 1:
            raise ValueError(
                f"Level {level_number} must contain exactly one {name} tile."
            )

    items = dict(definition.items)
    configured_item_positions = set(items)
    if item_tiles != configured_item_positions:
        missing = item_tiles - configured_item_positions
        extra = configured_item_positions - item_tiles
        details = []
        if missing:
            details.append(f"missing item definitions at {sorted(missing)}")
        if extra:
            details.append(f"item definitions without * tiles at {sorted(extra)}")
        raise ValueError(f"Level {level_number} has " + " and ".join(details) + ".")

    if any(not isinstance(item, Item) for item in items.values()):
        raise ValueError(f"Every configured level {level_number} item must be an Item.")

    player = positions[PLAYER][0]
    door = positions[DOOR][0]
    key = positions[KEY][0]
    npc_positions = set(positions[NPC])
    configured_enemy_positions = set(definition.enemy_types)
    invalid_enemy_positions = configured_enemy_positions - npc_positions
    if invalid_enemy_positions:
        raise ValueError(
            f"Level {level_number} has enemy definitions without ! tiles at "
            f"{sorted(invalid_enemy_positions)}."
        )

    enemy_pool = definition.enemy_pool or default_enemy_pool(level_number)
    if positions[NPC] and not enemy_pool:
        raise ValueError(f"Level {level_number} has enemies but no enemy pool.")

    enemies = {}
    for index, position in enumerate(positions[NPC]):
        archetype = definition.enemy_types.get(
            position,
            enemy_pool[index % len(enemy_pool)],
        )
        enemies[position] = create_enemy(archetype)

    # The player is tracked separately while the game runs.
    maze[player[1]][player[0]] = FLOOR

    return maze, player, player, (0, -1), door, key, items, enemies


def add_visible_ray(maze, cells, visible_cells):
    """Add a ray to visibility, stopping after its first wall."""
    height = len(maze)
    width = len(maze[0])

    for x, y in cells:
        if not (0 <= x < width and 0 <= y < height):
            break
        visible_cells.add((x, y))
        if maze[y][x] == WALL:
            break


def flashlight_visible_cells(maze, player, facing, flashlight_level):
    """Return the flashlight cone without allowing light through walls."""
    if flashlight_level == 0:
        return set()

    px, py = player
    fx, fy = facing
    sideways = (-fy, fx)
    forward_distance = (0, 2, 2, 3, 4)[flashlight_level]
    diagonal_distance = (0, 0, 1, 2, 3)[flashlight_level]
    visible_cells = set()

    center_ray = [
        (px + fx * distance, py + fy * distance)
        for distance in range(1, forward_distance + 1)
    ]
    add_visible_ray(maze, center_ray, visible_cells)

    for side in (-1, 1):
        diagonal_ray = [
            (
                px + fx * distance + sideways[0] * side,
                py + fy * distance + sideways[1] * side,
            )
            for distance in range(1, diagonal_distance + 1)
        ]
        add_visible_ray(maze, diagonal_ray, visible_cells)

    return visible_cells


def draw(
    maze,
    player,
    facing,
    discovered_walls,
    discovered_npcs,
    reveal_map,
    lamp_on,
    message,
    level_number,
    has_key,
    player_state,
    remembered_tiles,
    memory_mode,
):
    clear_screen()

    height = len(maze)
    width = len(maze[0])

    print("HIDDEN WALL MAZE")
    print(
        f"{LEVELS[level_number - 1].name} "
        f"({level_number} of {len(LEVELS)})    Map size: {width} x {height}"
    )
    print(
        "W A S D to move (1 stamina)    R rest (+5)    "
        "L lamp    M memory    Q quit"
    )
    print(f"Facing: {FACING_NAMES[facing]}")
    print(
        f"HP: {player_state.hp}/{player_state.max_hp}    "
        f"Stamina: {player_state.stamina}/{player_state.max_stamina}    "
        f"Damage: {player_state.damage}"
    )
    print(
        f"Key: {'collected' if has_key else 'not collected'}    "
        f"Lamp: {'on' if lamp_on else 'off'} "
        f"({player_state.lamp_uses}/{player_state.lamp_capacity} uses)    "
        f"Memory: {'on' if memory_mode else 'off'}"
    )

    unlocked_tools = []
    if "flashlight" in player_state.powerups:
        unlocked_tools.append(
            f"Flashlight Lv{player_state.upgrades['flashlight']} (always on)"
        )
    if player_state.upgrades["armor"]:
        unlocked_tools.append(
            f"Armor {player_state.armor_durability} durability"
        )
    if player_state.upgrades["speed"]:
        unlocked_tools.append(
            f"Speed {player_state.speed_uses} uses "
            f"(up to {player_state.speed_max_steps} moves)"
        )
    if player_state.upgrades["sword"]:
        unlocked_tools.append(
            f"T sword Lv{player_state.upgrades['sword']} "
            f"({SWORD_STAMINA_COST} stamina)"
        )
    if unlocked_tools:
        print("    ".join(unlocked_tools))

    print("@ you    ! enemy    K key    D door    # discovered wall    * item")
    print()

    px, py = player
    lamp_cells = {
        (px, py - 1),
        (px, py + 1),
        (px - 1, py),
        (px + 1, py),
    }
    if player_state.upgrades["lamp_diagonal"]:
        lamp_cells.update(
            {
                (px - 1, py - 1),
                (px + 1, py - 1),
                (px - 1, py + 1),
                (px + 1, py + 1),
            }
        )
    flashlight_cells = flashlight_visible_cells(
        maze,
        player,
        facing,
        player_state.upgrades["flashlight"],
    )
    if memory_mode:
        if lamp_on:
            remembered_tiles.update(lamp_cells)
        remembered_tiles.update(flashlight_cells)

    for y in range(height):
        line = []

        for x in range(width):
            position = (x, y)
            tile = maze[y][x]

            if position == player:
                line.append(PLAYER)
            elif tile == WALL:
                if (
                    reveal_map
                    or position in discovered_walls
                    or position in remembered_tiles
                ):
                    line.append(WALL)
                elif lamp_on and position in lamp_cells:
                    line.append(WALL)
                elif position in flashlight_cells:
                    line.append(WALL)
                else:
                    line.append(FLOOR)
            elif tile == NPC:
                if (
                    reveal_map
                    or position in discovered_npcs
                    or position in remembered_tiles
                ):
                    line.append(NPC)
                elif lamp_on and position in lamp_cells:
                    line.append(NPC)
                elif position in flashlight_cells:
                    line.append(NPC)
                else:
                    line.append(FLOOR)
            elif tile == KEY:
                line.append(KEY)
            elif tile == DOOR:
                line.append(DOOR)
            elif tile == ITEM_TILE:
                line.append(ITEM_TILE)
            else:
                line.append(FLOOR)

        print(" ".join(line))

    print()
    print(message)


def ask_trivia_question(enemy, player_state):
    """Fight an enemy with trivia. Return defeated, survived, or dead."""
    question = random.choice(TRIVIA_QUESTIONS)

    print(
        f"\nA {enemy.name} blocks your path "
        f"({enemy.hp}/{enemy.max_hp} enemy HP)!"
    )
    print(question["question"])
    for number, choice in enumerate(question["choices"], start=1):
        print(f"{number}. {choice}")

    for attempt in range(1, 3):
        while True:
            answer = input(f"Attempt {attempt} of 2, enter 1 to 4: ").strip()
            if answer in {"1", "2", "3", "4"}:
                break
            print("Please enter 1, 2, 3, or 4.")

        if int(answer) == question["answer"]:
            print(f"Correct! The {enemy.name} is defeated.")
            input("Press Enter to continue...")
            return "defeated"

        died, damage_message = player_state.take_damage(
            enemy.wrong_answer_damage
        )
        print(f"Incorrect! {damage_message}")
        if died:
            input("Press Enter to respawn...")
            return "dead"

    correct_choice = question["choices"][question["answer"] - 1]
    print(f"The correct answer was: {correct_choice}")
    print(f"The {enemy.name} remains in place, but you are not reset.")
    input("Press Enter to continue...")
    return "survived"


def sword_attack_cells(maze, player, direction, sword_level):
    """Return the straight attack lane, stopping at the first wall."""
    px, py = player
    dx, dy = direction
    height = len(maze)
    width = len(maze[0])
    max_distance = None if sword_level == 4 else sword_level
    cells = []
    distance = 1

    while max_distance is None or distance <= max_distance:
        x = px + dx * distance
        y = py + dy * distance
        if not (0 <= x < width and 0 <= y < height):
            break
        if maze[y][x] == WALL:
            break
        cells.append((x, y))
        distance += 1

    return cells


def perform_sword_attack(maze, player, facing, enemies, discovered_npcs, player_state):
    """Prompt for an attack direction and damage every enemy in its area."""
    if player_state.upgrades["sword"] == 0:
        return facing, "You have not unlocked the sword.", False
    if player_state.stamina < SWORD_STAMINA_COST:
        return facing, "You do not have enough stamina to use the sword.", False

    question = random.choice(TRIVIA_QUESTIONS)
    print("\nAnswer correctly to use the sword:")
    print(question["question"])
    for number, choice in enumerate(question["choices"], start=1):
        print(f"{number}. {choice}")

    while True:
        answer = input("Enter 1 to 4: ").strip()
        if answer in {"1", "2", "3", "4"}:
            break
        print("Please enter 1, 2, 3, or 4.")

    if int(answer) != question["answer"]:
        died, damage_message = player_state.take_damage(1)
        return (
            facing,
            f"Incorrect. The sword did not activate. {damage_message}",
            died,
        )

    while True:
        command = input("Attack direction (W, A, S, or D): ").strip().lower()
        if command in DIRECTIONS:
            break
        print("Enter W, A, S, or D.")

    facing = DIRECTIONS[command]
    player_state.stamina -= SWORD_STAMINA_COST
    cells = sword_attack_cells(
        maze,
        player,
        facing,
        player_state.upgrades["sword"],
    )
    results = []

    for position in cells:
        enemy = enemies.get(position)
        if enemy is None:
            continue

        discovered_npcs.add(position)
        actual_damage = enemy.take_damage(player_state.damage)
        if enemy.hp <= 0:
            results.append(
                f"{enemy.name} took {actual_damage} damage and was defeated."
            )
            del enemies[position]
            maze[position[1]][position[0]] = FLOOR
        else:
            results.append(
                f"{enemy.name} took {actual_damage} damage "
                f"({enemy.hp}/{enemy.max_hp} HP left)."
            )

    if not results:
        results.append("Your sword did not hit an enemy.")

    return facing, "Correct! " + " ".join(results), False


def upgrade_description(key, next_level, player_state):
    try:
        spec = UPGRADE_SPECS[key]
    except KeyError as error:
        raise ValueError(f"Unknown upgrade: {key}") from error
    return spec.describe(next_level, player_state)


def available_upgrades(player_state):
    available = []
    for key, spec in UPGRADE_SPECS.items():
        if player_state.upgrades[key] >= spec.max_level:
            continue
        if not spec.is_available(player_state):
            continue

        available.append(key)
    return available


def apply_upgrade(key, player_state):
    if key not in UPGRADE_SPECS:
        raise ValueError(f"Unknown upgrade: {key}")

    spec = UPGRADE_SPECS[key]
    new_level = player_state.upgrades[key] + 1
    if new_level > spec.max_level:
        raise ValueError(f"{spec.name} is already at its maximum level.")
    if not spec.is_available(player_state):
        raise ValueError(f"{spec.name} has not met its prerequisite.")

    description = upgrade_description(key, new_level, player_state)
    player_state.upgrades[key] = new_level
    spec.on_apply(player_state, new_level)

    return (
        f"Unlocked {spec.name} Level {new_level}: "
        f"{description}"
    )


def debug_upgrade_console(player_state):
    """Safely set an upgrade level without bypassing required dependencies."""
    print("\nDEBUG UPGRADE CONSOLE")
    for key, spec in UPGRADE_SPECS.items():
        print(
            f"- {key}: level {player_state.upgrades[key]}/"
            f"{spec.max_level}"
        )
    print("- cancel")

    while True:
        key = input("Upgrade/item name: ").strip().lower().replace(" ", "_")
        if key == "cancel":
            return "Debug upgrade cancelled."
        if key in UPGRADE_SPECS:
            break
        print("Enter one of the listed upgrade names, or cancel.")

    spec = UPGRADE_SPECS[key]
    maximum = spec.max_level
    while True:
        answer = input(f"Set {key} to level 1-{maximum}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= maximum:
            level = int(answer)
            break
        print(f"Enter a level from 1 to {maximum}.")

    if key == "flashlight":
        player_state.powerups.add("flashlight")
    if key == "sword_damage":
        player_state.upgrades["sword"] = max(
            1, player_state.upgrades["sword"]
        )

    player_state.upgrades[key] = level
    spec.on_apply(player_state, level)
    if key == "stamina":
        player_state.stamina = player_state.max_stamina
    elif key == "lamp_duration":
        player_state.lamp_uses = player_state.lamp_capacity
    elif key == "speed":
        player_state.speed_uses = player_state.speed_uses_per_level

    return (
        f"Debug granted {spec.name} Level {level}."
    )


def reset_enemy_health(enemies):
    for enemy in enemies.values():
        enemy.hp = enemy.max_hp


def ranged_enemy_attacks(enemies, player, discovered_npcs, player_state):
    """Resolve attacks from enemies one tile away and reveal their positions."""
    messages = []
    for position, enemy in enemies.items():
        if enemy.attack_range == 0:
            continue

        distance = abs(position[0] - player[0]) + abs(position[1] - player[1])
        if distance > enemy.attack_range:
            continue

        discovered_npcs.add(position)
        died, damage_message = player_state.take_damage(enemy.contact_damage)
        messages.append(
            f"The ranged {enemy.name} at {position} revealed itself and attacked. "
            f"{damage_message}"
        )
        if died:
            return True, messages

    return False, messages


def choose_end_of_level_upgrade(player_state):
    choices = available_upgrades(player_state)
    if not choices:
        return

    choice_count = 3 + player_state.upgrades["extra_choice"]
    choices = random.sample(choices, min(choice_count, len(choices)))

    clear_screen()
    print("LEVEL COMPLETE - CHOOSE ONE UPGRADE")
    print()
    for number, key in enumerate(choices, start=1):
        spec = UPGRADE_SPECS[key]
        next_level = player_state.upgrades[key] + 1
        print(f"{number}. {spec.name} Level {next_level}")
        print(f"   {upgrade_description(key, next_level, player_state)}")

    while True:
        answer = input(f"Choose 1 to {len(choices)}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            break
        print(f"Enter a number from 1 to {len(choices)}.")

    selected = choices[int(answer) - 1]
    print()
    print(apply_upgrade(selected, player_state))
    input("Press Enter to start the next level...")


def play_level(level_number, player_state):
    (
        maze,
        player,
        start_position,
        facing,
        door,
        key_position,
        items,
        enemies,
    ) = build_level(level_number)
    player_state.start_level()
    discovered_walls = set()
    discovered_npcs = set()
    remembered_tiles = set()
    memory_mode = True
    reveal_map = False
    lamp_on = False
    has_key = False
    message = "Find the key before trying to open the door."

    while True:
        draw(
            maze,
            player,
            facing,
            discovered_walls,
            discovered_npcs,
            reveal_map,
            lamp_on,
            message,
            level_number,
            has_key,
            player_state,
            remembered_tiles,
            memory_mode,
        )

        command = input("> ").strip().lower()

        if command == "q":
            return "quit"

        if command == "duck":
            reveal_map = True
            message = "Secret code accepted. Full map revealed!"
            continue

        if command == "sheepy":
            return "complete"

        if command == "l":
            if lamp_on:
                lamp_on = False
                message = "Lamp turned off."
            elif player_state.lamp_uses == 0:
                message = "The lamp has no durability left this level."
            else:
                lamp_on = True
                message = "Lamp turned on."
            continue

        if command == "m":
            memory_mode = not memory_mode
            if not memory_mode:
                remembered_tiles.clear()
            message = (
                f"Map memory turned {'on' if memory_mode else 'off'}. "
                + (
                    "Light-revealed tiles will remain visible."
                    if memory_mode
                    else "Only bumped walls and discovered enemies stay visible."
                )
            )
            continue

        if command == "powerduck":
            message = debug_upgrade_console(player_state)
            continue

        if command == "r":
            recovered = min(5, player_state.max_stamina - player_state.stamina)
            player_state.stamina += recovered
            died, ranged_messages = ranged_enemy_attacks(
                enemies,
                player,
                discovered_npcs,
                player_state,
            )
            messages = [f"You rested and recovered {recovered} stamina."]
            messages.extend(ranged_messages)
            if died:
                player_state.respawn()
                reset_enemy_health(enemies)
                player = start_position
                lamp_on = False
                messages.append(
                    "You respawned at the start; all living enemies "
                    "returned to full HP."
                )
            message = " ".join(messages)
            continue

        if command == "t":
            facing, message, died = perform_sword_attack(
                maze,
                player,
                facing,
                enemies,
                discovered_npcs,
                player_state,
            )
            if died:
                player_state.respawn()
                reset_enemy_health(enemies)
                player = start_position
                lamp_on = False
                message += (
                    " You respawned at the start; all living enemies "
                    "returned to full HP."
                )
            continue

        if not command or any(step not in DIRECTIONS for step in command):
            controls = "W, A, S, D, R, L, M, or Q"
            if player_state.upgrades["sword"]:
                controls += ", or T"
            message = f"Enter {controls}."
            continue

        required_stamina = len(command) * MOVEMENT_STAMINA_COST
        if player_state.stamina < required_stamina:
            message = (
                f"You need {required_stamina} stamina for that movement "
                f"but only have {player_state.stamina}."
            )
            continue

        if len(command) > 1:
            if player_state.upgrades["speed"] == 0:
                message = "Unlock Speed before entering multiple moves at once."
                continue
            if len(command) > player_state.speed_max_steps:
                message = (
                    f"Speed currently allows at most "
                    f"{player_state.speed_max_steps} moves at once."
                )
                continue
            if player_state.speed_uses == 0:
                message = "You have no Speed uses left this level."
                continue
            player_state.speed_uses -= 1

        action_messages = []
        level_complete = False
        stop_moving = False

        for step in command:
            player_state.stamina -= MOVEMENT_STAMINA_COST
            facing = DIRECTIONS[step]
            dx, dy = facing
            px, py = player
            nx, ny = px + dx, py + dy

            if lamp_on:
                player_state.lamp_uses -= 1
                if player_state.lamp_uses == 0:
                    lamp_on = False
                    action_messages.append("The lamp ran out and turned off.")

            if ny < 0 or ny >= len(maze) or nx < 0 or nx >= len(maze[0]):
                action_messages.append("You cannot move outside the map.")
                break

            tile = maze[ny][nx]

            if tile == WALL:
                discovered_walls.add((nx, ny))
                action_messages.append("Bump! You discovered a wall.")
                break

            enemy = enemies.get((nx, ny))
            if enemy is not None:
                discovered_npcs.add((nx, ny))
                died, contact_message = player_state.take_damage(
                    enemy.contact_damage
                )
                action_messages.append(
                    f"The {enemy.name} attacked on contact. {contact_message}"
                )

                if died:
                    player_state.respawn()
                    reset_enemy_health(enemies)
                    player = start_position
                    lamp_on = False
                    action_messages.append(
                        "You respawned at the start with full HP and stamina; "
                        "all living enemies returned to full HP."
                    )
                    break

                draw(
                    maze,
                    player,
                    facing,
                    discovered_walls,
                    discovered_npcs,
                    reveal_map,
                    lamp_on,
                    " ".join(action_messages),
                    level_number,
                    has_key,
                    player_state,
                    remembered_tiles,
                    memory_mode,
                )
                outcome = ask_trivia_question(enemy, player_state)

                if outcome == "defeated":
                    del enemies[(nx, ny)]
                    maze[ny][nx] = FLOOR
                    player = (nx, ny)
                    action_messages.append(
                        f"The {enemy.name} disappeared and you moved forward."
                    )
                elif outcome == "dead":
                    player_state.respawn()
                    reset_enemy_health(enemies)
                    player = start_position
                    lamp_on = False
                    action_messages.append(
                        "A wrong answer defeated you. "
                        "You respawned at the start with full HP and stamina; "
                        "all living enemies returned to full HP."
                    )
                else:
                    action_messages.append(
                        f"The {enemy.name} still blocks that tile."
                    )
                stop_moving = True
                break

            if (nx, ny) == door and not has_key:
                action_messages.append("The door is locked. Find the key first!")
                break

            player = (nx, ny)

            died, ranged_messages = ranged_enemy_attacks(
                enemies,
                player,
                discovered_npcs,
                player_state,
            )
            if ranged_messages:
                action_messages.extend(ranged_messages)
                if died:
                    player_state.respawn()
                    reset_enemy_health(enemies)
                    player = start_position
                    lamp_on = False
                    action_messages.append(
                        "You respawned at the start with full HP and stamina; "
                        "all living enemies returned to full HP."
                    )
                stop_moving = True
                break

            if player in items:
                item = items.pop(player)
                item.collect(player_state)
                maze[ny][nx] = FLOOR
                action_messages.append(item.pickup_message())

            if player == key_position and not has_key:
                has_key = True
                maze[key_position[1]][key_position[0]] = FLOOR
                action_messages.append("You collected the key! Now find the door.")

            if player == door:
                level_complete = True
                break

        if level_complete:
            clear_screen()
            print(f"You step through the door into Level "
                  f"{level_number}'s challenge...")
            run_door_challenge(level_number, player_state, first_attempt=True)
            return "complete"

        if not action_messages and not stop_moving:
            action_messages.append("You moved.")
        elif len(command) > 1 and not stop_moving:
            action_messages.append(f"Speed moved you {len(command)} tiles.")
        message = " ".join(action_messages)


def run_self_tests():
    """Run deterministic checks for game systems and scripted gameplay."""
    import contextlib
    import io
    from unittest.mock import patch

    passed = 0
    failures = []
    original_clear_screen = globals()["clear_screen"]
    globals()["clear_screen"] = lambda: None

    def run_test(name, test_function):
        nonlocal passed
        try:
            test_function()
        except Exception as error:
            failures.append((name, error))
            print(f"FAIL  {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print(f"PASS  {name}")

    def test_levels_items_and_enemies():
        item_count = 0
        enemy_names = set()

        for level_number in range(1, len(LEVELS) + 1):
            (
                maze,
                player,
                start,
                facing,
                door,
                key,
                items,
                enemies,
            ) = build_level(level_number)
            assert maze and player == start
            assert facing == (0, -1)
            assert door != key
            assert len(enemies) == 5
            assert all(isinstance(enemy, Enemy) for enemy in enemies.values())
            item_count += len(items)
            enemy_names.update(enemy.name for enemy in enemies.values())

        assert item_count == 1
        assert {"Trivia Guard", "Brute", "Quizmaster", "Sentinel", "Warden"} <= (
            enemy_names
        )
        first_level = build_level(1)
        assert first_level[6][(1, 7)].name == "Flashlight"

    def test_content_extension_points():
        extra_level = LevelDefinition(
            "Self-Test Extension Level",
            [
                list("#######"),
                list("#@.*K.D"),
                list("#.!.!.#"),
                list("#######"),
            ],
            items={
                (3, 1): Consumable(
                    "Extension Token",
                    "Proves a level can own new item content.",
                    amount=2,
                ),
            },
            enemy_types={(2, 2): "trivia_guard"},
        )

        LEVELS.append(extra_level)
        try:
            built = build_level(len(LEVELS))
            assert built[0][1][3] == ITEM_TILE
            assert len(built[6]) == 1
            assert len(built[7]) == 2
            assert built[7][(2, 2)].name == "Trivia Guard"
            assert built[7][(4, 2)].name == "Warden"
        finally:
            LEVELS.pop()

        key = "self_test_upgrade"
        UPGRADE_SPECS[key] = UpgradeDefinition(
            "Self-Test Upgrade",
            2,
            lambda level, state: f"Extension level {level}.",
            on_apply=lambda state, level: state.consumables.__setitem__(
                "Extension Token",
                level,
            ),
        )
        try:
            player_state = PlayerState()
            message = apply_upgrade(key, player_state)
            assert player_state.upgrades[key] == 1
            assert player_state.consumables["Extension Token"] == 1
            assert "Self-Test Upgrade Level 1" in message
        finally:
            del UPGRADE_SPECS[key]

    def test_items_and_progression():
        player_state = PlayerState()
        assert player_state.max_hp == 5
        assert player_state.max_stamina == 20
        assert player_state.damage == 0

        consumable = Consumable("Test Charge", "Used by the self-test.", amount=3)
        consumable.collect(player_state)
        assert player_state.consumables["Test Charge"] == 3

        flashlight = build_level(1)[6][(1, 7)]
        flashlight.collect(player_state)
        assert "flashlight" in player_state.powerups
        assert player_state.upgrades["flashlight"] == 1

        apply_upgrade("hp", player_state)
        apply_upgrade("stamina", player_state)
        apply_upgrade("sword", player_state)
        apply_upgrade("sword_damage", player_state)
        apply_upgrade("speed", player_state)
        apply_upgrade("armor", player_state)

        assert player_state.max_hp == 10
        assert player_state.max_stamina == 25
        assert player_state.damage == 8
        assert player_state.speed_max_steps == 2
        assert player_state.speed_uses_per_level == 2
        assert player_state.armor_durability == 1

    def test_light_and_sword_wall_blocking():
        maze = [list(".....") for _ in range(5)]
        maze[2][2] = WALL
        visible = flashlight_visible_cells(maze, (2, 3), (0, -1), 4)
        assert (2, 2) in visible
        assert (2, 1) not in visible

        maze = [list(".....") for _ in range(5)]
        maze[2][1] = WALL
        visible = flashlight_visible_cells(maze, (2, 3), (0, -1), 3)
        assert (1, 2) in visible
        assert (1, 1) not in visible

        sword_maze = [
            list("#######"),
            list("#..#..#"),
            list("#######"),
        ]
        cells = sword_attack_cells(sword_maze, (1, 1), (1, 0), 4)
        assert cells == [(2, 1)]

    def test_memory_mode():
        player_state = PlayerState()
        player_state.powerups.add("flashlight")
        player_state.upgrades["flashlight"] = 1
        remembered_tiles = set()
        maze = [
            list("#####"),
            list("#...#"),
            list("#...#"),
            list("#####"),
        ]

        with contextlib.redirect_stdout(io.StringIO()):
            draw(
                maze,
                (2, 2),
                (0, -1),
                set(),
                set(),
                False,
                True,
                "test",
                1,
                False,
                player_state,
                remembered_tiles,
                True,
            )

        assert (2, 1) in remembered_tiles
        assert (1, 2) in remembered_tiles

    def test_armor_hp_and_ranged_enemies():
        player_state = PlayerState()
        apply_upgrade("armor", player_state)
        died, message = player_state.take_damage(5)
        assert not died
        assert player_state.hp == 4
        assert player_state.armor_durability == 0
        assert "80%" in message

        ranged_state = PlayerState()
        ranged_enemy = Enemy("Test Sentinel", 12, 5, 1, 2, 1)
        discovered = set()
        died, messages = ranged_enemy_attacks(
            {(2, 1): ranged_enemy},
            (1, 1),
            discovered,
            ranged_state,
        )
        assert died
        assert (2, 1) in discovered
        assert "revealed itself" in messages[0]

        enemies = {
            (1, 1): Enemy("Damaged Guard", 5),
            (2, 1): Enemy("Damaged Brute", 9),
        }
        enemies[(1, 1)].hp = 1
        enemies[(2, 1)].hp = 2
        reset_enemy_health(enemies)
        assert [enemy.hp for enemy in enemies.values()] == [5, 9]

    def test_sword_trivia_gate():
        question = TRIVIA_QUESTIONS[0]
        player_state = PlayerState()
        apply_upgrade("sword", player_state)
        player_state.start_level()
        maze = [
            list("#####"),
            list("#...#"),
            list("#####"),
        ]
        enemies = {(2, 1): Enemy("Test Guard", 5)}

        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["1"]
        ), contextlib.redirect_stdout(io.StringIO()):
            _, message, died = perform_sword_attack(
                maze,
                (1, 1),
                (1, 0),
                enemies,
                set(),
                player_state,
            )

        assert not died
        assert player_state.hp == 4
        assert player_state.stamina == 20
        assert enemies
        assert "did not activate" in message

        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["2", "d"]
        ), contextlib.redirect_stdout(io.StringIO()):
            _, message, died = perform_sword_attack(
                maze,
                (1, 1),
                (1, 0),
                enemies,
                set(),
                player_state,
            )

        assert not died
        assert player_state.stamina == 15
        assert not enemies
        assert "defeated" in message

    def test_movement_rest_speed_and_lamp():
        player_state = PlayerState()
        output = io.StringIO()
        with patch(
            "builtins.input",
            side_effect=["w", "r", "m", "m", "q"],
        ), contextlib.redirect_stdout(output):
            result = play_level(1, player_state)

        assert result == "quit"
        assert player_state.stamina == 20
        assert player_state.upgrades["flashlight"] == 1
        assert "Map memory turned off" in output.getvalue()
        assert "Map memory turned on" in output.getvalue()

        speed_state = PlayerState()
        apply_upgrade("speed", speed_state)
        with patch(
            "builtins.input", side_effect=["ww", "q"]
        ), contextlib.redirect_stdout(io.StringIO()):
            result = play_level(1, speed_state)

        assert result == "quit"
        assert speed_state.stamina == 18
        assert speed_state.speed_uses == 1

        lamp_state = PlayerState()
        with patch(
            "builtins.input", side_effect=["l", "w", "q"]
        ), contextlib.redirect_stdout(io.StringIO()):
            result = play_level(1, lamp_state)

        assert result == "quit"
        assert lamp_state.lamp_uses == 2

    def test_death_reset_and_discovery():
        question = TRIVIA_QUESTIONS[0]
        player_state = PlayerState()
        output = io.StringIO()

        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input",
            side_effect=["w", "w", "d", "1", "1", "", "q"],
        ), contextlib.redirect_stdout(output):
            result = play_level(1, player_state)

        text = output.getvalue()
        assert result == "quit"
        assert player_state.hp == player_state.max_hp == 5
        assert "all living enemies returned to full HP" in text
        assert "! . . . . . . ." in text

    def test_debug_console_and_upgrade_choice():
        player_state = PlayerState()
        with patch(
            "builtins.input", side_effect=["flashlight", "4"]
        ), contextlib.redirect_stdout(io.StringIO()):
            debug_upgrade_console(player_state)

        assert "flashlight" in player_state.powerups
        assert player_state.upgrades["flashlight"] == 4

        with patch(
            "builtins.input", side_effect=["sword_damage", "3"]
        ), contextlib.redirect_stdout(io.StringIO()):
            debug_upgrade_console(player_state)

        assert player_state.upgrades["sword"] == 1
        assert player_state.upgrades["sword_damage"] == 3

        choice_state = PlayerState()
        choice_state.powerups.add("flashlight")
        choice_state.upgrades["flashlight"] = 1
        with patch.object(
            random,
            "sample",
            side_effect=lambda choices, count: choices[:count],
        ), patch(
            "builtins.input", side_effect=["1", ""]
        ), contextlib.redirect_stdout(io.StringIO()):
            choose_end_of_level_upgrade(choice_state)

        assert choice_state.upgrades["lamp_duration"] == 1
        assert sum(choice_state.upgrades.values()) == 2

    def test_door_password_gate():
        # The gate accepts the password registered in LEVEL_PASSWORDS.
        assert _check_door_password(LEVEL_PASSWORDS[1], 1) is True
        # A wrong password keeps the player locked out.
        assert _check_door_password("not-the-password", 1) is False
        # An unknown level (e.g. 99) has no registered password, so the
        # gate must reject anything rather than silently open.
        assert _check_door_password("anything", 99) is False
        # Whitespace matters: stripping happens in _read_door_password,
        # so a padded input that doesn't match exactly is rejected.
        assert _check_door_password(f" {LEVEL_PASSWORDS[1]} ", 1) is False
        # The launcher path resolves to a real file on disk so the door
        # challenge can import it at runtime. The exact filename is
        # checked so a future rename breaks this test loudly.
        assert _LAUNCHER_PATH.name == "launcher.py"
        assert _LAUNCHER_PATH.exists()

    tests = [
        ("level validation, items, and enemy types", test_levels_items_and_enemies),
        ("content extension registries", test_content_extension_points),
        ("items and progression math", test_items_and_progression),
        ("light and sword wall blocking", test_light_and_sword_wall_blocking),
        ("persistent map memory", test_memory_mode),
        ("armor, HP, ranged attacks, and reset", test_armor_hp_and_ranged_enemies),
        ("sword trivia gate", test_sword_trivia_gate),
        ("movement, rest, Speed, and lamp", test_movement_rest_speed_and_lamp),
        ("death reset and retained discovery", test_death_reset_and_discovery),
        ("debug console and upgrade choices", test_debug_console_and_upgrade_choice),
        ("door password gate", test_door_password_gate),
    ]

    print("HIDDEN WALL MAZE - SELF TEST")
    print()
    try:
        for name, test_function in tests:
            run_test(name, test_function)
    finally:
        globals()["clear_screen"] = original_clear_screen

    print()
    print(f"Result: {passed}/{len(tests)} test groups passed.")
    if failures:
        print("Self-test failed.")
        return False

    print("All game systems passed.")
    return True


def main():
    player_state = PlayerState()

    for level_number in range(1, len(LEVELS) + 1):
        result = play_level(level_number, player_state)

        if result == "quit":
            print("Game closed.")
            return

        if level_number < len(LEVELS):
            choose_end_of_level_upgrade(player_state)
            print(f"Starting level {level_number + 1}.")
            continue

    print("You completed all five levels. You win!")


if __name__ == "__main__":
    try:
        if "--test" in sys.argv[1:]:
            if not run_self_tests():
                raise SystemExit(1)
        else:
            main()
    except (KeyboardInterrupt, EOFError):
        print("\nGame closed.")
    except ValueError as error:
        print(f"Level setup error: {error}")