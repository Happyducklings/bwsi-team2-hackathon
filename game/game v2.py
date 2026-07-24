import os
import random

WALL = "#"
FLOOR = "."
PLAYER = "@"
DOOR = "D"
KEY = "K"
NPC = "!"

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

# Edit these 2D arrays to design each level manually.
# Use # for walls, . for floors, @ for the player, ! for NPCs, K for the key, and D for the door.
# Every row in one level must have the same number of cells.
LEVELS = [
    [
        list("##########"),
        list("#.!......D"),
        list("#....!...#"),
        list("#..##...!#"),
        list("#..#..#..#"),
        list("#.#.#.#..#"),
        list("#.!..#...#"),
        list("#...##!K.#"),
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

# Add or edit trivia questions here. The answer is the number of the correct choice.
TRIVIA_QUESTIONS = [
    {
        "question": "What does the "S" in HTTPS stand for?",
        "choices": ["Secure", "Server", "Simple", "Standard"],
        "answer": 1,
    },
    {
        "question": "If a security measure or control fails, the system is not rendered to an insecure state." Which NSA design principle does this statement describe?",
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



def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def build_level(level_number):
    """Copy and validate one manually designed 2D level array."""
    source = LEVELS[level_number - 1]
    maze = [row[:] for row in source]

    if not maze or not maze[0]:
        raise ValueError(f"Level {level_number} is empty.")

    width = len(maze[0])
    if any(len(row) != width for row in maze):
        raise ValueError(f"Every row in level {level_number} must have the same length.")

    allowed_tiles = {WALL, FLOOR, PLAYER, DOOR, KEY, NPC}
    positions = {PLAYER: [], DOOR: [], KEY: [], NPC: []}

    for y, row in enumerate(maze):
        for x, tile in enumerate(row):
            if tile not in allowed_tiles:
                raise ValueError(
                    f"Invalid tile {tile!r} at ({x}, {y}) in level {level_number}."
                )
            if tile in positions:
                positions[tile].append((x, y))

    for tile, name in ((PLAYER, "player"), (DOOR, "door"), (KEY, "key")):
        if len(positions[tile]) != 1:
            raise ValueError(
                f"Level {level_number} must contain exactly one {name} tile."
            )

    if len(positions[NPC]) != 5:
        raise ValueError(
            f"Level {level_number} must contain exactly five NPC tiles (!)."
        )

    player = positions[PLAYER][0]
    door = positions[DOOR][0]
    key = positions[KEY][0]

    # The player is tracked separately while the game runs.
    maze[player[1]][player[0]] = FLOOR

    return maze, player, player, (0, -1), door, key


def draw(
    maze,
    player,
    facing,
    discovered_walls,
    discovered_npcs,
    reveal_map,
    flashlight_on,
    message,
    level_number,
    has_key,
):
    clear_screen()

    height = len(maze)
    width = len(maze[0])

    print("HIDDEN WALL MAZE")
    print(f"Level {level_number} of {len(LEVELS)}    Map size: {width} x {height}")
    print("W A S D to move    F flashlight    Q to quit")
    print(f"Facing: {FACING_NAMES[facing]}")
    print(f"Key: {'collected' if has_key else 'not collected'}")
    print("@ you    ! trivia NPC    K key    D door    # discovered wall")
    print()

    px, py = player
    flashlight_cells = {
        (px, py - 1),
        (px, py + 1),
        (px - 1, py),
        (px + 1, py),
    }

    for y in range(height):
        line = []

        for x in range(width):
            position = (x, y)
            tile = maze[y][x]

            if position == player:
                line.append(PLAYER)
            elif tile == WALL:
                if reveal_map or position in discovered_walls:
                    line.append(WALL)
                elif flashlight_on and position in flashlight_cells:
                    line.append(WALL)
                else:
                    line.append(FLOOR)
            elif tile == NPC:
                if reveal_map or position in discovered_npcs:
                    line.append(NPC)
                elif flashlight_on and position in flashlight_cells:
                    line.append(NPC)
                else:
                    line.append(FLOOR)
            elif tile == KEY:
                line.append(KEY)
            elif tile == DOOR:
                line.append(DOOR)
            else:
                line.append(FLOOR)

        print(" ".join(line))

    print()
    print(message)


def ask_trivia_question():
    """Ask one random question. Return True if answered correctly within two tries."""
    question = random.choice(TRIVIA_QUESTIONS)

    print("\nA trivia NPC blocks your path!")
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
            print("Correct! The NPC lets you pass.")
            input("Press Enter to continue...")
            return True

        if attempt == 1:
            print("Incorrect. You have one try left.")

    correct_choice = question["choices"][question["answer"] - 1]
    print(f"Incorrect. The correct answer was: {correct_choice}")
    print("You are sent back to the beginning of the level.")
    input("Press Enter to continue...")
    return False


def play_level(level_number):
    maze, player, start_position, facing, door, key_position = build_level(level_number)
    discovered_walls = set()
    discovered_npcs = set()
    reveal_map = False
    flashlight_on = False
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
            flashlight_on,
            message,
            level_number,
            has_key,
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

        if command == "f":
            flashlight_on = not flashlight_on
            state = "on" if flashlight_on else "off"
            message = f"Flashlight turned {state}."
            continue

        if command not in DIRECTIONS:
            message = "Enter W, A, S, D, F, or Q."
            continue

        facing = DIRECTIONS[command]
        dx, dy = facing
        px, py = player
        nx, ny = px + dx, py + dy

        if ny < 0 or ny >= len(maze) or nx < 0 or nx >= len(maze[0]):
            message = "You cannot move outside the map."
            continue

        tile = maze[ny][nx]

        if tile == WALL:
            discovered_walls.add((nx, ny))
            message = "Bump! You discovered a wall."
            continue

        if tile == NPC:
            # Reveal the NPC on the map as soon as the player bumps into it.
            # The player stays on the current square while answering.
            discovered_npcs.add((nx, ny))
            message = "Bump! You discovered a trivia NPC."
            draw(
                maze,
                player,
                facing,
                discovered_walls,
                discovered_npcs,
                reveal_map,
                flashlight_on,
                message,
                level_number,
                has_key,
            )

            if ask_trivia_question():
                # Correct answer: remove the NPC and move onto its square.
                maze[ny][nx] = FLOOR
                player = (nx, ny)
                message = "Correct! The NPC disappeared and you moved forward."
            else:
                # Two wrong answers: return to the original starting square.
                player = start_position
                message = "Two wrong answers sent you back to the beginning."
            continue

        if (nx, ny) == door and not has_key:
            message = "The door is locked. Find the key first!"
            continue

        player = (nx, ny)

        if player == key_position and not has_key:
            has_key = True
            maze[key_position[1]][key_position[0]] = FLOOR
            message = "You collected the key! Now find the door."
            continue

        if player == door:
            return "complete"

        message = "You moved."


def main():
    for level_number in range(1, len(LEVELS) + 1):
        result = play_level(level_number)

        if result == "quit":
            print("Game closed.")
            return

        if level_number < len(LEVELS):
            print(f"Level {level_number} complete! Starting level {level_number + 1}.")
            input("Press Enter to continue...")

    print("You completed all five levels. You win!")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGame closed.")
    except ValueError as error:
        print(f"Level setup error: {error}")
