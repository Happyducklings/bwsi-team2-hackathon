import getpass
import importlib.util
import os
import random
import sys
from collections import defaultdict, deque
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
        if self.effect in {"flashlight", "sword"}:
            player_state.upgrades[self.effect] = max(
                1, player_state.upgrades[self.effect]
            )


class Consumable(Item):
    """A stackable item represented by an amount in the inventory."""

    item_type = "consumable"

    def __init__(self, name, description, amount=1, item_key=None):
        super().__init__(name, description)
        self.amount = amount
        self.item_key = item_key or name.lower().replace(" ", "_")

    def collect(self, player_state):
        player_state.add_consumable(self)

    def use(self, context):
        """Return (used, message). Subclasses define their own effect."""
        return False, f"{self.name} does not have a use behavior yet."

    def pickup_message(self):
        return (
            f"You picked up {self.name} x{self.amount}! "
            f"{self.description}"
        )


class Bomb(Consumable):
    def __init__(self, amount=1):
        super().__init__(
            "Bomb",
            "Destroys one adjacent wall in a chosen direction.",
            amount,
            item_key="bomb",
        )

    def use(self, context):
        while True:
            command = input("Bomb direction (W, A, S, D, or Q): ").strip().lower()
            if command == "q":
                return False, "Bomb use cancelled."
            if command in DIRECTIONS:
                break
            print("Enter W, A, S, D, or Q.")

        dx, dy = DIRECTIONS[command]
        px, py = context["player"]
        target = (px + dx, py + dy)
        maze = context["maze"]
        x, y = target
        if not (0 <= y < len(maze) and 0 <= x < len(maze[0])):
            return False, "The bomb cannot target outside the map."
        if maze[y][x] != WALL:
            return False, "There is no wall in that direction. The bomb was saved."

        maze[y][x] = FLOOR
        context["discovered_walls"].discard(target)
        return True, f"Bomb destroyed the wall at {target}."


class Cookie(Consumable):
    def __init__(self, amount=1):
        super().__init__(
            "Cookie",
            "Restores 5 HP.",
            amount,
            item_key="cookie",
        )

    def use(self, context):
        player_state = context["player_state"]
        if player_state.hp >= player_state.max_hp:
            return False, "You already have full HP. The cookie was saved."

        restored = min(5, player_state.max_hp - player_state.hp)
        player_state.hp += restored
        return True, f"Cookie restored {restored} HP."


# Random item spawning and the inventory menu use this registry automatically.
CONSUMABLE_TYPES = {
    "bomb": Bomb,
    "cookie": Cookie,
}


STAMINA_BONUSES = (5, 10, 10, 15)
SWORD_DAMAGE_BONUSES = (3, 5, 8, 11)
HP_BONUSES = (5, 5, 5, 5)
LAMP_DURABILITY_BY_LEVEL = (3, 5, 7, 10, 14)
SWORD_STAMINA_COST = 5
MOVEMENT_STAMINA_COST = 1
TRIVIA_DAMAGE = 3
ENEMY_MOVE_CHANCE = 0.10


class PlayerState:
    """Stats, inventory, and permanent upgrades shared between levels."""

    def __init__(self):
        self.base_hp = 5
        self.upgrades = defaultdict(int)
        self.powerups = set()
        self.consumables = defaultdict(int)
        self.consumable_items = {}
        self.item_recency = []
        self.hp = self.max_hp
        self.armor_durability = 0
        self.stamina = self.max_stamina
        self.lamp_uses = self.lamp_capacity

    @property
    def max_hp(self):
        level = self.upgrades["hp"]
        return self.base_hp + sum(HP_BONUSES[:level])

    @property
    def max_stamina(self):
        level = self.upgrades["stamina"]
        return 30 + sum(STAMINA_BONUSES[:level])

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
    def speed_max_steps(self):
        level = self.upgrades["speed"]
        if level == 0:
            return 1
        return 3 if level >= 3 else 2

    @property
    def speed_stamina_discount(self):
        return (0, 0, 1, 1, 2)[self.upgrades["speed"]]

    def movement_stamina_cost(self, step_count):
        return max(
            1,
            step_count * MOVEMENT_STAMINA_COST - self.speed_stamina_discount,
        )

    def start_level(self):
        self.hp = self.max_hp
        self.stamina = self.max_stamina
        self.lamp_uses = self.lamp_capacity

    def respawn(self):
        self.hp = self.max_hp
        self.stamina = self.max_stamina

    def add_consumable(self, item):
        self.consumables[item.item_key] += item.amount
        self.consumable_items[item.item_key] = item
        if item.item_key in self.item_recency:
            self.item_recency.remove(item.item_key)
        self.item_recency.insert(0, item.item_key)

    def consume_item(self, item_key):
        self.consumables[item_key] -= 1
        if self.consumables[item_key] <= 0:
            del self.consumables[item_key]
            self.consumable_items.pop(item_key, None)
            if item_key in self.item_recency:
                self.item_recency.remove(item_key)

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
        attack_damage=3,
        armor=0,
        attack_range=1,
    ):
        self.name = name
        self.max_hp = max_hp
        self.hp = max_hp
        self.attack_damage = attack_damage
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
        "max_hp": 3,
        "attack_damage": 3,
        "armor": 0,
        "attack_range": 1,
    },
    "brute": {
        "name": "Brute",
        "max_hp": 14,
        "attack_damage": 4,
        "armor": 0,
        "attack_range": 1,
    },
    "quizmaster": {
        "name": "Quizmaster",
        "max_hp": 10,
        "attack_damage": 3,
        "armor": 0,
        "attack_range": 2,
    },
    "sentinel": {
        "name": "Sentinel",
        "max_hp": 18,
        "attack_damage": 5,
        "armor": 1,
        "attack_range": 1,
    },
    "warden": {
        "name": "Warden",
        "max_hp": 25,
        "attack_damage": 5,
        "armor": 1,
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
    "lamp": UpgradeDefinition(
        "Lamp",
        1,
        lambda level, state: (
            "Unlock the lamp with 3 illuminated movement uses per level."
        ),
    ),
    "lamp_duration": UpgradeDefinition(
        "Lamp Durability",
        4,
        lambda level, state: (
            f"Increase lamp durability to "
            f"{LAMP_DURABILITY_BY_LEVEL[level]} uses per level."
        ),
        is_available=lambda state: state.upgrades["lamp"] > 0,
    ),
    "lamp_diagonal": UpgradeDefinition(
        "Wide Lamp",
        1,
        lambda level, state: (
            "The lamp also reveals all four adjacent diagonal tiles."
        ),
        is_available=lambda state: state.upgrades["lamp"] > 0,
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
            f"with a {((0, 0, 1, 1, 2)[level])}-stamina discount per command."
        ),
    ),
    "sword": UpgradeDefinition(
        "Sword Area",
        4,
        describe_sword,
        is_available=lambda state: "sword" in state.powerups,
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
        list("#!!......D"),
        list("#....!...#"),
        list("#..##...!#"),
        list("#..#..#..#"),
        list("#.#.#.#..#"),
        list("#....#...#"),
        list("#*..##!K.#"),
        list("#@.......#"),
        list("##########"),
    ],
    [
        list("############"),
        list("#..!.......D"),
        list("#.......!..#"),
        list("#...##..#..#"),
        list("#.#.#.....!#"),
        list("#..#.##.#..#"),
        list("#.#....##..#"),
        list("#.#.!..#.#.#"),
        list("#...##.....#"),
        list("#*..#...#K.#"),
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
    [
        list("####################"),
        list("#..K...............D"),
        list("#..#..#..#.....#...#"),
        list("#..#.....#..#..#...#"),
        list("#..#..!..#.!.......#"),
        list("#........#.........#"),
        list("#..................#"),
        list("#..###..#..#..#..#.#"),
        list("#..........#..#....#"),
        list("#.....!............#"),
        list("#..#..#..#..#..#...#"),
        list("#..#.....#..#......#"),
        list("#..........!.......#"),
        list("#..................#"),
        list("#..#..#..#..#..#...#"),
        list("#..#.....#.....#...#"),
        list("#.....!............#"),
        list("#@.................#"),
        list("####################"),
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
    LevelDefinition(
        "Level 2",
        LEVEL_MAPS[1],
        items={
            (1, 9): PowerUp(
                "Sword",
                "Unlocks trivia-gated sword attacks.",
                "sword",
            ),
        },
    ),
    LevelDefinition("Level 3", LEVEL_MAPS[2]),
    LevelDefinition("Level 4", LEVEL_MAPS[3]),
    LevelDefinition("Level 5", LEVEL_MAPS[4]),
    LevelDefinition("Level 6", LEVEL_MAPS[5]),
]

# Add or edit trivia questions here. The answer is the number of the correct choice.
TRIVIA_QUESTIONS = [
    {
        "question": "What does the 'S' in HTTPS stand for?",
        "choices": ["Secure", "Server", "Simple", "Standard"],
        "answer": 1,
    },
    {
        "question": "If a security measure or control fails, the system is not rendered to an insecure state. Which NSA design principle does this statement describe?",
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


LEVEL_PASSWORDS = {
    1: "HWM{1927}",
    2: "HWM{R3v3rs3d_5ucc3ss}",
    3: "HWM{Simon_has_cookies?}",
    4: "HWM{Y0u_g0t_this!}",
    5: "HWM{1nv35t1g4t1v3_R3v3rs3r!}",
    6: "HWM{M@k3_1t_th3_b35t_d@y}",
}

LAUNCHER_PATH = (
    Path(__file__).resolve().parent
    / "bwsi-team2-dockerfile"
    / "launcher.py"
)


def _load_launcher():
    """Load the Docker/SSH launcher lazily from the project directory."""
    spec = importlib.util.spec_from_file_location(
        "bwsi_team2_launcher",
        LAUNCHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load launcher spec from {LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_door_password(entered, level_number):
    """Return whether an entered flag exactly unlocks a known level."""
    expected = LEVEL_PASSWORDS.get(level_number)
    return expected is not None and entered == expected


def _challenge_allows_level_completion(result):
    """Fail closed: only a literal True completes the challenge."""
    return result is True


def _read_door_password(level_number):
    """Read a hidden password when possible, with a non-TTY fallback."""
    prompt = f"Enter the Level {level_number} password to proceed: "
    try:
        return getpass.getpass(prompt).strip()
    except (ValueError, getpass.GetPassWarning):
        print(
            "[launcher] (No TTY available — password will be visible.)",
            file=sys.stderr,
        )
        return input(prompt).strip()


def run_door_challenge(level_number, player_state, *, first_attempt=True):
    """Run a level's Docker/SSH challenge and require its recovered flag."""
    del player_state  # Reserved for future challenge rewards/state.

    try:
        launcher = _load_launcher()
    except (FileNotFoundError, ImportError) as error:
        print(
            f"[launcher] Could not load the Docker launcher from "
            f"{LAUNCHER_PATH}: {error}",
            file=sys.stderr,
        )
        print(
            "[launcher] The challenge cannot start, so this level remains "
            "locked.",
            file=sys.stderr,
        )
        return False

    first_time = first_attempt
    while True:
        clear_screen()
        if first_time:
            launcher.wait_for_keypress(level=level_number)
        first_time = False

        if launcher.build_image(level=level_number) != 0:
            return False
        if launcher.start_container(level=level_number) != 0:
            return False
        if not launcher.wait_for_ssh():
            print(
                f"[launcher] SSH port never came up for level {level_number}.",
                file=sys.stderr,
            )
            return False

        try:
            ssh_rc = launcher.launch_ssh_in_place(level=level_number)
        except KeyboardInterrupt:
            print(
                "\n[launcher] SSH challenge canceled; the level remains locked."
            )
            return False

        if ssh_rc < 0:
            print(
                f"[launcher] SSH challenge was interrupted (exit code "
                f"{ssh_rc}). The level remains locked.",
                file=sys.stderr,
            )
            return False

        clear_screen()
        print("=" * 60)
        print("  You have left the challenge container.")
        print(f"  Enter the Level {level_number} password to proceed.")
        print("=" * 60)

        try:
            entered = _read_door_password(level_number)
        except (EOFError, KeyboardInterrupt):
            print(
                "\n[launcher] Challenge canceled; the level remains locked."
            )
            return False

        if _check_door_password(entered, level_number):
            return True

        print("Incorrect password. Reconnecting to the challenge...")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def spawn_random_consumables(
    maze,
    items,
    excluded_positions=None,
    minimum=1,
    maximum=2,
):
    """Place registry-backed consumables on currently empty floor tiles."""
    excluded_positions = excluded_positions or set()
    empty_positions = [
        (x, y)
        for y, row in enumerate(maze)
        for x, tile in enumerate(row)
        if tile == FLOOR and (x, y) not in excluded_positions
    ]
    if not empty_positions or not CONSUMABLE_TYPES:
        return

    count = min(random.randint(minimum, maximum), len(empty_positions))
    for position in random.sample(empty_positions, count):
        item_class = random.choice(tuple(CONSUMABLE_TYPES.values()))
        item = item_class()
        items[position] = item
        maze[position[1]][position[0]] = ITEM_TILE


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
    spawn_random_consumables(maze, items, excluded_positions={player})

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
    controls = "W A S D move    R rest    I items    M memory    Q quit"
    if player_state.upgrades["lamp"]:
        controls += "    L lamp"
    print(controls)
    print(f"Facing: {FACING_NAMES[facing]}")
    print(
        f"HP: {player_state.hp}/{player_state.max_hp}    "
        f"Stamina: {player_state.stamina}/{player_state.max_stamina}    "
        f"Damage: {player_state.damage}"
    )
    status = (
        f"Key: {'collected' if has_key else 'not collected'}    "
        f"Memory: {'on' if memory_mode else 'off'}"
    )
    if player_state.upgrades["lamp"]:
        status += (
            f"    Lamp: {'on' if lamp_on else 'off'} "
            f"({player_state.lamp_uses}/{player_state.lamp_capacity} uses)"
        )
    print(status)

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
            f"Speed Lv{player_state.upgrades['speed']} "
            f"(up to {player_state.speed_max_steps} moves, "
            f"-{player_state.speed_stamina_discount} stamina)"
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
    """Make a contact-trivia attack. Return correct or missed."""
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
            print(
                f"Correct! You deal {TRIVIA_DAMAGE} trivia damage "
                f"to the {enemy.name}."
            )
            input("Press Enter to continue...")
            return "correct"

        print("Incorrect! Your contact attack missed.")

    correct_choice = question["choices"][question["answer"] - 1]
    print(f"The correct answer was: {correct_choice}")
    print(f"The {enemy.name} remains in place.")
    input("Press Enter to continue...")
    return "missed"


def resolve_enemy_attack(enemy, player_state):
    """Gate one enemy attack behind a single defensive trivia answer."""
    question = random.choice(TRIVIA_QUESTIONS)
    print(
        f"\nThe {enemy.name} attacks for {enemy.attack_damage} damage! "
        "Answer correctly to defend:"
    )
    print(question["question"])
    for number, choice in enumerate(question["choices"], start=1):
        print(f"{number}. {choice}")

    while True:
        answer = input("Enter 1 to 4: ").strip()
        if answer in {"1", "2", "3", "4"}:
            break
        print("Please enter 1, 2, 3, or 4.")

    if int(answer) == question["answer"]:
        return False, f"Correct! You blocked the {enemy.name}'s attack."
    

    died, damage_message = player_state.take_damage(enemy.attack_damage)
    return died, f"Incorrect. {damage_message}"


def apply_trivia_hit(enemy):
    """Deal contact-trivia damage and return whether the enemy was defeated."""
    enemy.hp -= TRIVIA_DAMAGE
    return enemy.hp <= 0


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


def use_item_menu(player_state, context):
    """Open the recency-sorted inventory. Return (used_item, message)."""
    available_keys = [
        key
        for key in player_state.item_recency
        if player_state.consumables.get(key, 0) > 0
    ]
    if not available_keys:
        return False, "You do not have any consumable items."

    print("\nITEMS - most recently collected first")
    for number, key in enumerate(available_keys, start=1):
        item = player_state.consumable_items[key]
        amount = player_state.consumables[key]
        print(f"{number}. {item.name} x{amount} - {item.description}")
    print("Q. Close item menu")

    while True:
        answer = input("Choose an item: ").strip().lower()
        if answer == "q":
            return False, "Item menu closed."
        if answer.isdigit() and 1 <= int(answer) <= len(available_keys):
            break
        print(f"Enter 1 to {len(available_keys)}, or Q.")

    item_key = available_keys[int(answer) - 1]
    item = player_state.consumable_items[item_key]
    used, message = item.use(context)
    if used:
        player_state.consume_item(item_key)
    return used, message


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

    if key in {"flashlight", "sword"}:
        player_state.powerups.add(key)
    if key == "sword_damage":
        player_state.powerups.add("sword")
        player_state.upgrades["sword"] = max(
            1, player_state.upgrades["sword"]
        )

    player_state.upgrades[key] = level
    spec.on_apply(player_state, level)
    if key == "stamina":
        player_state.stamina = player_state.max_stamina
    elif key == "lamp_duration":
        player_state.lamp_uses = player_state.lamp_capacity
    return (
        f"Debug granted {spec.name} Level {level}."
    )


def reset_enemy_health(enemies):
    for enemy in enemies.values():
        enemy.hp = enemy.max_hp


def enemy_can_attack(maze, enemy_position, player, attack_range):
    """Check cardinal attack range without allowing attacks through walls."""
    dx = player[0] - enemy_position[0]
    dy = player[1] - enemy_position[1]
    distance = abs(dx) + abs(dy)
    effective_range = max(1, attack_range)
    if distance > effective_range:
        return False
    if distance == 1:
        return True
    if dx != 0 and dy != 0:
        return False

    step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
    step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
    x, y = enemy_position
    for _ in range(1, distance):
        x += step_x
        y += step_y
        if maze[y][x] == WALL:
            return False
    return True


def enemies_attack_in_range(
    maze,
    enemies,
    player,
    discovered_npcs,
    player_state,
    before_attack=None,
):
    """Resolve in-range attacks, then return control after a counterattack."""
    messages = []
    for position, enemy in list(enemies.items()):
        if not enemy_can_attack(maze, position, player, enemy.attack_range):
            continue

        discovered_npcs.add(position)
        if before_attack is not None:
            before_attack(position, enemy)
        died, attack_message = resolve_enemy_attack(enemy, player_state)
        messages.append(
            f"The {enemy.name} at {position} attacked. {attack_message}"
        )
        if died:
            return True, messages

        if attack_message.startswith("Correct!"):
            actual_damage = enemy.take_damage(TRIVIA_DAMAGE)
            if enemy.hp <= 0:
                del enemies[position]
                maze[position[1]][position[0]] = FLOOR
                messages.append(
                    f"You automatically counterattack for {actual_damage} damage "
                    f"and defeat the {enemy.name}."
                )
            else:
                messages.append(
                    f"You automatically counterattack for {actual_damage} damage. "
                    f"The {enemy.name} has {enemy.hp}/{enemy.max_hp} HP left. "
                    "Player Turn, consider using sword if u have :D"
                )

            # A successful defense and counterattack ends the enemy phase.
            return False, messages

    return False, messages


def next_enemy_step(maze, start, player, occupied_positions):
    """Find one shortest-path step toward the player."""
    height = len(maze)
    width = len(maze[0])
    queue = deque([(start, None)])
    visited = {start}

    while queue:
        position, first_step = queue.popleft()
        if position == player:
            return first_step

        for dx, dy in DIRECTIONS.values():
            neighbor = (position[0] + dx, position[1] + dy)
            x, y = neighbor
            if not (0 <= x < width and 0 <= y < height):
                continue
            if neighbor in visited:
                continue
            if neighbor in occupied_positions and neighbor != start:
                continue
            if neighbor != player and maze[y][x] != FLOOR:
                continue

            visited.add(neighbor)
            queue.append((neighbor, neighbor if first_step is None else first_step))

    return None


def move_enemies_toward_player(
    maze,
    enemies,
    player,
    discovered_npcs,
    player_state,
    before_attack=None,
):
    """Move out-of-range enemies once, then give in-range enemies one attack."""
    messages = []
    occupied_positions = set(enemies)

    for old_position, enemy in list(enemies.items()):
        if old_position not in enemies:
            continue
        if enemy_can_attack(
            maze,
            old_position,
            player,
            enemy.attack_range,
        ):
            continue

        # Each out-of-range enemy moves on only 10% of enemy turns.
        if random.random() >= ENEMY_MOVE_CHANCE:
            continue

        step = next_enemy_step(
            maze,
            old_position,
            player,
            occupied_positions,
        )
        if step is None:
            continue

        if step == player:
            continue

        was_discovered = old_position in discovered_npcs
        del enemies[old_position]
        occupied_positions.remove(old_position)
        maze[old_position[1]][old_position[0]] = FLOOR

        enemies[step] = enemy
        occupied_positions.add(step)
        maze[step[1]][step[0]] = NPC
        discovered_npcs.discard(old_position)
        if was_discovered:
            discovered_npcs.add(step)

    died, attack_messages = enemies_attack_in_range(
        maze,
        enemies,
        player,
        discovered_npcs,
        player_state,
        before_attack=before_attack,
    )
    messages.extend(attack_messages)
    return died, messages


def choose_end_of_level_upgrade(player_state):
    choices = available_upgrades(player_state)
    if not choices:
        return

    choice_count = 3 + player_state.upgrades["extra_choice"]
    choices = random.sample(choices, min(choice_count, len(choices)))

    clear_screen()
    print("LEVEL COMPLETE - CHOOSE ONE UPGRADE")
    print("Remember, enemies can move towards you!")
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

    def show_attacking_enemy(position, enemy):
        """Reveal and redraw an enemy before its trivia attack begins."""
        discovered_npcs.add(position)
        draw(
            maze,
            player,
            facing,
            discovered_walls,
            discovered_npcs,
            reveal_map,
            lamp_on,
            f"The {enemy.name} appears and prepares to attack!",
            level_number,
            has_key,
            player_state,
            remembered_tiles,
            memory_mode,
        )

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
            clear_screen()
            print(
                f"Debug shortcut: opening Level {level_number}'s challenge..."
            )
            challenge_complete = run_door_challenge(
                level_number,
                player_state,
                first_attempt=True,
            )
            if _challenge_allows_level_completion(challenge_complete):
                return "complete"
            message = (
                "The challenge was not completed. The level remains locked."
            )
            continue

        if command == "l":
            if player_state.upgrades["lamp"] == 0:
                message = "You have not unlocked the lamp."
            elif lamp_on:
                lamp_on = False
                message = "Lamp turned off."
            elif player_state.lamp_uses == 0:
                message = "The lamp has no durability left this level."
            else:
                lamp_on = True
                message = "Lamp turned on."
            continue

        if command == "i":
            item_context = {
                "maze": maze,
                "player": player,
                "player_state": player_state,
                "discovered_walls": discovered_walls,
            }
            used_item, message = use_item_menu(player_state, item_context)
            if used_item:
                died, enemy_messages = move_enemies_toward_player(
                    maze,
                    enemies,
                    player,
                    discovered_npcs,
                    player_state,
                    before_attack=show_attacking_enemy,
                )
                if enemy_messages:
                    message += " " + " ".join(enemy_messages)
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
            recovered = player_state.max_stamina - player_state.stamina
            player_state.stamina = player_state.max_stamina
            died, enemy_messages = move_enemies_toward_player(
                maze,
                enemies,
                player,
                discovered_npcs,
                player_state,
                before_attack=show_attacking_enemy,
            )
            messages = [
                f"You rested to full stamina and recovered {recovered}."
            ]
            messages.extend(enemy_messages)
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
            else:
                died, enemy_messages = move_enemies_toward_player(
                    maze,
                    enemies,
                    player,
                    discovered_npcs,
                    player_state,
                    before_attack=show_attacking_enemy,
                )
                if enemy_messages:
                    message += " " + " ".join(enemy_messages)
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
            controls = "W, A, S, D, R, I, M, or Q"
            if player_state.upgrades["lamp"]:
                controls += ", or L"
            if player_state.upgrades["sword"]:
                controls += ", or T"
            message = f"Enter {controls}."
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

        required_stamina = player_state.movement_stamina_cost(len(command))
        if player_state.stamina < required_stamina:
            message = (
                f"You need {required_stamina} stamina for that movement "
                f"but only have {player_state.stamina}."
            )
            continue
        player_state.stamina -= required_stamina

        action_messages = []
        level_complete = False
        stop_moving = False
        player_was_defeated = False

        for step in command:
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
                action_messages.append(
                    f"You engage the {enemy.name} with a contact-trivia attack."
                )

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

                if outcome == "correct":
                    if apply_trivia_hit(enemy):
                        del enemies[(nx, ny)]
                        maze[ny][nx] = FLOOR
                        player = (nx, ny)
                        action_messages.append(
                            f"The {enemy.name} was defeated and you moved forward."
                        )
                    else:
                        action_messages.append(
                            f"The {enemy.name} has "
                            f"{enemy.hp}/{enemy.max_hp} HP left."
                        )
                else:
                    action_messages.append(
                        f"Your attack missed. The {enemy.name} still blocks that tile."
                    )
                stop_moving = True
                break

            if (nx, ny) == door and not has_key:
                action_messages.append("The door is locked. Find the key first!")
                break

            player = (nx, ny)

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
            print(
                f"You step through the door into Level "
                f"{level_number}'s challenge..."
            )
            challenge_complete = run_door_challenge(
                level_number,
                player_state,
                first_attempt=True,
            )
            if _challenge_allows_level_completion(challenge_complete):
                return "complete"
            message = (
                "The challenge was not completed. The door remains locked; "
                "step away and return when you are ready to try again."
            )
            continue

        if not player_was_defeated:
            died, enemy_messages = move_enemies_toward_player(
                maze,
                enemies,
                player,
                discovered_npcs,
                player_state,
                before_attack=show_attacking_enemy,
            )
            action_messages.extend(enemy_messages)
            if died:
                player_state.respawn()
                reset_enemy_health(enemies)
                player = start_position
                lamp_on = False
                player_was_defeated = True
                action_messages.append(
                    "You respawned at the start with full HP and stamina; "
                    "all living enemies returned to full HP."
                )

        if not action_messages and not stop_moving:
            action_messages.append("You moved.")
        elif len(command) > 1 and not stop_moving:
            action_messages.append(f"Speed moved you {len(command)} tiles.")
        message = " ".join(action_messages)


def run_self_tests():
    """Run deterministic checks for game systems and scripted gameplay."""
    import contextlib
    import io
    from unittest.mock import MagicMock, patch

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
        enemy_names = set()
        assert len(LEVELS) == 6

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
            assert player not in items
            random_consumables = [
                item for item in items.values() if isinstance(item, Consumable)
            ]
            assert 1 <= len(random_consumables) <= 2
            enemy_names.update(enemy.name for enemy in enemies.values())

        assert {"Trivia Guard", "Brute", "Quizmaster", "Sentinel", "Warden"} <= (
            enemy_names
        )
        first_level = build_level(1)
        assert first_level[6][(1, 7)].name == "Flashlight"
        second_level = build_level(2)
        assert second_level[6][(1, 9)].name == "Sword"

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
            assert built[6][(3, 1)].name == "Extension Token"
            assert 2 <= len(built[6]) <= 3
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
        assert player_state.max_stamina == 30
        assert player_state.damage == 0
        initial_choices = available_upgrades(player_state)
        assert "lamp" in initial_choices
        assert "lamp_duration" not in initial_choices
        assert "lamp_diagonal" not in initial_choices
        assert "sword" not in initial_choices

        consumable = Consumable("Test Charge", "Used by the self-test.", amount=3)
        consumable.collect(player_state)
        assert player_state.consumables["test_charge"] == 3

        flashlight = build_level(1)[6][(1, 7)]
        flashlight.collect(player_state)
        assert "flashlight" in player_state.powerups
        assert player_state.upgrades["flashlight"] == 1

        apply_upgrade("hp", player_state)
        apply_upgrade("stamina", player_state)
        PowerUp("Sword", "Self-test sword.", "sword").collect(player_state)
        apply_upgrade("sword_damage", player_state)
        apply_upgrade("speed", player_state)
        apply_upgrade("armor", player_state)

        assert player_state.max_hp == 10
        assert player_state.max_stamina == 35
        assert player_state.damage == 8
        assert player_state.speed_max_steps == 2
        assert player_state.movement_stamina_cost(2) == 2
        apply_upgrade("speed", player_state)
        assert player_state.movement_stamina_cost(2) == 1
        assert player_state.armor_durability == 1

    def test_consumable_menu_and_effects():
        player_state = PlayerState()
        player_state.hp = 1
        player_state.stamina = 7
        Bomb().collect(player_state)
        Cookie().collect(player_state)
        Bomb().collect(player_state)

        assert player_state.item_recency == ["bomb", "cookie"]
        assert player_state.consumables["bomb"] == 2
        assert player_state.consumables["cookie"] == 1

        maze = [
            list("#####"),
            list("#...#"),
            list("#####"),
        ]
        context = {
            "maze": maze,
            "player": (2, 1),
            "player_state": player_state,
            "discovered_walls": {(2, 0)},
        }

        with patch(
            "builtins.input",
            side_effect=["2"],
        ), contextlib.redirect_stdout(io.StringIO()):
            used, message = use_item_menu(player_state, context)
        assert used and "restored" in message
        assert player_state.hp == 5
        assert "cookie" not in player_state.consumables

        with patch(
            "builtins.input",
            side_effect=["1", "w"],
        ), contextlib.redirect_stdout(io.StringIO()):
            used, message = use_item_menu(player_state, context)
        assert used and "destroyed" in message
        assert maze[0][2] == FLOOR
        assert player_state.consumables["bomb"] == 1
        assert (2, 0) not in context["discovered_walls"]
        assert player_state.stamina == 7

        with patch(
            "builtins.input",
            side_effect=["q"],
        ), contextlib.redirect_stdout(io.StringIO()):
            used, message = use_item_menu(player_state, context)
        assert not used and message == "Item menu closed."

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

        attack_maze = [
            list("#######"),
            list("#..#..#"),
            list("#######"),
        ]
        assert not enemy_can_attack(attack_maze, (1, 1), (5, 1), 5)
        attack_maze[1][3] = FLOOR
        assert enemy_can_attack(attack_maze, (1, 1), (5, 1), 5)

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
        apply_upgrade("hp", ranged_state)
        ranged_enemy = Enemy("Test Sentinel", 12, 5, 2, 1)
        discovered = set()
        attack_maze = [
            list("#####"),
            list("#.!.#"),
            list("#####"),
        ]
        question = {
            "question": "Self-test question",
            "choices": ["Wrong", "Correct", "Wrong", "Wrong"],
            "answer": 2,
        }
        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["1"]
        ), contextlib.redirect_stdout(io.StringIO()):
            died, messages = enemies_attack_in_range(
                attack_maze,
                {(2, 1): ranged_enemy},
                (1, 1),
                discovered,
                ranged_state,
            )
        assert not died
        assert ranged_state.hp == 5
        assert (2, 1) in discovered
        assert "Incorrect" in messages[0]

        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["2"]
        ), contextlib.redirect_stdout(io.StringIO()):
            died, messages = enemies_attack_in_range(
                attack_maze,
                {(2, 1): ranged_enemy},
                (1, 1),
                discovered,
                ranged_state,
            )
        assert not died
        assert messages and "blocked" in messages[0]
        assert ranged_state.hp == 5

        pursuit_maze = [
            list("######"),
            list("#!...#"),
            list("######"),
        ]
        pursuing_enemy = Enemy("Pursuer", 8, 3)
        pursuit_enemies = {(1, 1): pursuing_enemy}
        pursuit_state = PlayerState()
        with patch.object(random, "random", return_value=0.0):
            died, messages = move_enemies_toward_player(
                pursuit_maze,
                pursuit_enemies,
                (4, 1),
                set(),
                pursuit_state,
            )
        assert not died and not messages
        assert (2, 1) in pursuit_enemies

        reveal_maze = [
            list("#####"),
            list("#.!.#"),
            list("#####"),
        ]
        reveal_enemy = Enemy("Reveal Guard", 8, 3)
        reveal_enemies = {(2, 1): reveal_enemy}
        reveal_state = PlayerState()
        reveal_discovered = set()
        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["1"]
        ), contextlib.redirect_stdout(io.StringIO()):
            died, messages = move_enemies_toward_player(
                reveal_maze,
                reveal_enemies,
                (3, 1),
                reveal_discovered,
                reveal_state,
            )
        assert not died and reveal_state.hp == 2
        assert messages
        with patch.object(random, "choice", return_value=question), patch(
            "builtins.input", side_effect=["2"]
        ), contextlib.redirect_stdout(io.StringIO()):
            died, messages = move_enemies_toward_player(
                reveal_maze,
                reveal_enemies,
                (3, 1),
                reveal_discovered,
                reveal_state,
            )
        assert not died and messages and reveal_state.hp == 2

        enemies = {
            (1, 1): Enemy("Damaged Guard", 5),
            (2, 1): Enemy("Damaged Brute", 9),
        }
        enemies[(1, 1)].hp = 1
        enemies[(2, 1)].hp = 2
        reset_enemy_health(enemies)
        assert [enemy.hp for enemy in enemies.values()] == [5, 9]

        trivia_enemy = Enemy("Trivia Target", 8)
        assert not apply_trivia_hit(trivia_enemy)
        assert trivia_enemy.hp == 5
        assert not apply_trivia_hit(trivia_enemy)
        assert trivia_enemy.hp == 2
        assert apply_trivia_hit(trivia_enemy)

    def test_sword_trivia_gate():
        question = {
            "question": "Self-test question",
            "choices": ["Wrong", "Correct", "Wrong", "Wrong"],
            "answer": 2,
        }
        player_state = PlayerState()
        PowerUp("Sword", "Self-test sword.", "sword").collect(player_state)
        player_state.start_level()
        maze = [
            list("#####"),
            list("#...#"),
            list("#####"),
        ]
        enemies = {(2, 1): Enemy("Test Guard", 8)}

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
        assert player_state.stamina == 30
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
        assert player_state.stamina == 25
        assert enemies[(2, 1)].hp == 3
        assert "3/8 HP left" in message

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
        assert player_state.stamina == 20
        assert not enemies
        assert "defeated" in message

    def test_movement_rest_speed_and_lamp():
        original_attack = globals()["resolve_enemy_attack"]
        original_random = random.random
        random.random = lambda: 0.0
        globals()["resolve_enemy_attack"] = (
            lambda enemy, state: (False, "Self-test blocked the attack.")
        )
        try:
            player_state = PlayerState()
            output = io.StringIO()
            with patch(
                "builtins.input",
                side_effect=["w", "r", "m", "m", "q"],
            ), contextlib.redirect_stdout(output):
                result = play_level(1, player_state)

            assert result == "quit"
            assert player_state.stamina == 30
            assert player_state.upgrades["flashlight"] == 1
            assert "Map memory turned off" in output.getvalue()
            assert "Map memory turned on" in output.getvalue()
            # Player actions resolve before enemy attack checks, so this
            # short movement sequence can safely move away without a pre-move hit.
            assert output.getvalue().count("Self-test blocked") == 0

            speed_state = PlayerState()
            apply_upgrade("speed", speed_state)
            with patch(
                "builtins.input", side_effect=["ww", "q"]
            ), contextlib.redirect_stdout(io.StringIO()):
                result = play_level(1, speed_state)

            assert result == "quit"
            assert speed_state.stamina == 28

            lamp_state = PlayerState()
            apply_upgrade("lamp", lamp_state)
            with patch(
                "builtins.input", side_effect=["l", "w", "q"]
            ), contextlib.redirect_stdout(io.StringIO()):
                result = play_level(1, lamp_state)

            assert result == "quit"
            assert lamp_state.lamp_uses == 2

            item_state = PlayerState()
            Bomb().collect(item_state)
            item_output = io.StringIO()
            with patch(
                "builtins.input", side_effect=["i", "1", "a", "q"]
            ), contextlib.redirect_stdout(item_output):
                result = play_level(1, item_state)

            assert result == "quit"
            assert "bomb" not in item_state.consumables
            assert item_state.stamina == item_state.max_stamina
            assert "Bomb destroyed" in item_output.getvalue()
        finally:
            globals()["resolve_enemy_attack"] = original_attack
            random.random = original_random

    def test_death_reset_and_discovery():
        player_state = PlayerState()
        player_state.hp = 2
        discovered_walls = {(1, 1)}
        discovered_npcs = {(2, 1)}
        remembered_tiles = {(3, 1)}
        enemy = Enemy("Reset Target", 14)
        enemy.hp = 2
        enemies = {(2, 1): enemy}

        died, _ = player_state.take_damage(2)
        assert died
        player_state.respawn()
        reset_enemy_health(enemies)

        assert player_state.hp == player_state.max_hp == 5
        assert enemy.hp == enemy.max_hp == 14
        assert discovered_walls == {(1, 1)}
        assert discovered_npcs == {(2, 1)}
        assert remembered_tiles == {(3, 1)}

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

        assert choice_state.upgrades["lamp"] == 1
        assert sum(choice_state.upgrades.values()) == 2

    def test_docker_challenge_gate():
        launcher = MagicMock()
        launcher.build_image.return_value = 0
        launcher.start_container.return_value = 0
        launcher.wait_for_ssh.return_value = True
        launcher.launch_ssh_in_place.return_value = 0

        with patch(
            "builtins.input",
            return_value="",
        ), patch.object(
            sys.modules[__name__],
            "_load_launcher",
            return_value=launcher,
        ), patch.object(
            sys.modules[__name__],
            "_read_door_password",
            side_effect=["wrong", LEVEL_PASSWORDS[1]],
        ), contextlib.redirect_stdout(io.StringIO()):
            result = run_door_challenge(1, PlayerState())

        assert result is True
        assert launcher.launch_ssh_in_place.call_count == 2
        assert _check_door_password(LEVEL_PASSWORDS[6], 6)
        assert not _check_door_password("wrong", 6)
        assert not _check_door_password("anything", 99)
        assert _challenge_allows_level_completion(True)
        for rejected in (False, None, "complete", 1):
            assert not _challenge_allows_level_completion(rejected)
        assert LAUNCHER_PATH.exists()

    tests = [
        ("level validation, items, and enemy types", test_levels_items_and_enemies),
        ("content extension registries", test_content_extension_points),
        ("items and progression math", test_items_and_progression),
        ("consumable stacking, menu, and effects", test_consumable_menu_and_effects),
        ("light and sword wall blocking", test_light_and_sword_wall_blocking),
        ("persistent map memory", test_memory_mode),
        ("armor, HP, ranged attacks, and reset", test_armor_hp_and_ranged_enemies),
        ("sword trivia gate", test_sword_trivia_gate),
        ("movement, rest, Speed, and lamp", test_movement_rest_speed_and_lamp),
        ("death reset and retained discovery", test_death_reset_and_discovery),
        ("debug console and upgrade choices", test_debug_console_and_upgrade_choice),
        ("Docker/SSH challenge gate", test_docker_challenge_gate),
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

    print(f"You completed all {len(LEVELS)} levels. You win!")


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
