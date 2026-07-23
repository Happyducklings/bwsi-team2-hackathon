import os
import random
from collections import deque

WIDTH = 10
HEIGHT = 10

WALL = "#"
FLOOR = "."
PLAYER = "@"
DOOR = "D"
UNKNOWN = " "

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


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def path_exists(maze, start, goal):
    queue = deque([start])
    visited = {start}

    while queue:
        x, y = queue.popleft()

        if (x, y) == goal:
            return True

        for dx, dy in DIRECTIONS.values():
            nx, ny = x + dx, y + dy

            if not (0 <= nx < WIDTH and 0 <= ny < HEIGHT):
                continue

            if (nx, ny) in visited:
                continue

            if maze[ny][nx] == WALL:
                continue

            visited.add((nx, ny))
            queue.append((nx, ny))

    return False


def generate_maze():
    while True:
        maze = [[FLOOR for _ in range(WIDTH)] for _ in range(HEIGHT)]

        for x in range(WIDTH):
            maze[0][x] = WALL
            maze[HEIGHT - 1][x] = WALL

        for y in range(HEIGHT):
            maze[y][0] = WALL
            maze[y][WIDTH - 1] = WALL

        player = (1, HEIGHT - 2)
        door = (WIDTH - 1, 1)

        for y in range(1, HEIGHT - 1):
            for x in range(1, WIDTH - 1):
                if (x, y) == player:
                    continue

                if random.random() < 0.28:
                    maze[y][x] = WALL

        maze[door[1]][door[0]] = DOOR
        maze[1][WIDTH - 2] = FLOOR

        if path_exists(maze, player, (WIDTH - 2, 1)):
            return maze, player, (0, -1), door


def relative_position(player, facing, cell):
    px, py = player
    cx, cy = cell
    fx, fy = facing

    dx = cx - px
    dy = cy - py

    forward = dx * fx + dy * fy
    sideways = dx * (-fy) + dy * fx
    return forward, sideways


def is_visible(player, facing, cell):
    forward, sideways = relative_position(player, facing, cell)

    if forward <= 0:
        return True

    return forward <= 2 and abs(sideways) <= 2


def draw(maze, player, facing, discovered_walls, reveal_map, flashlight_on, message):
    clear_screen()

    print("HIDDEN WALL MAZE")
    print("W A S D to move    F flashlight    Q to quit")
    print(f"Facing: {FACING_NAMES[facing]}")
    print("@ you    D door    # discovered wall")
    print()

    for y in range(HEIGHT):
        line = []

        for x in range(WIDTH):
            position = (x, y)
            tile = maze[y][x]

            if position == player:
                line.append(PLAYER)
            elif tile == WALL:
                px, py = player
                flashlight_cells = {
                    (px, py - 1),
                    (px, py + 1),
                    (px - 1, py),
                    (px + 1, py),
                }

                if reveal_map or position in discovered_walls:
                    line.append(WALL)
                elif flashlight_on and position in flashlight_cells:
                    line.append(WALL)
                else:
                    line.append(FLOOR)
            elif tile == DOOR:
                line.append(DOOR)
            else:
                line.append(FLOOR)

        print(" ".join(line))

    print()
    print(message)


def main():
    maze, player, facing, door = generate_maze()
    discovered_walls = set()
    reveal_map = False
    flashlight_on = False
    message = "Walls are invisible until you walk into them. Press F for flashlight."

    while True:
        draw(
            maze,
            player,
            facing,
            discovered_walls,
            reveal_map,
            flashlight_on,
            message
        )

        command = input("> ").strip().lower()

        if command == "q":
            print("Game closed.")
            break

        if command == "duck":
            reveal_map = True
            message = "Secret code accepted. Full map revealed!"
            continue

        if command == "f":
            flashlight_on = not flashlight_on
            state = "on" if flashlight_on else "off"
            message = f"Flashlight turned {state}."
            continue

        if command not in DIRECTIONS:
            message = "Enter W, A, S, D, or Q."
            continue

        facing = DIRECTIONS[command]
        dx, dy = facing
        px, py = player
        nx, ny = px + dx, py + dy
        tile = maze[ny][nx]

        if tile == WALL:
            discovered_walls.add((nx, ny))
            message = "Bump! You discovered a wall."
            continue

        player = (nx, ny)

        if player == door:
            draw(
                maze,
                player,
                facing,
                discovered_walls,
                reveal_map,
                flashlight_on,
                "You found the door. You win!"
            )
            break

        message = "You moved."


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGame closed.")
