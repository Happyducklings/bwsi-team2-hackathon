#!/usr/bin/env python3
"""Merged Hidden Wall Maze game.

This entry point uses the richer gameplay implementation in
``asd/gamevfinal.py`` and adds the six-level Docker/SSH challenge progression
from ``game/game v2.py``.  Keeping the gameplay module loaded as a module also
means its classes and registries remain the single source of truth.
"""

from __future__ import annotations

import getpass
import importlib.util
import inspect
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
GAMEPLAY_PATH = HERE / "asd" / "gamevfinal.py"
LAUNCHER_PATH = HERE / "bwsi-team2-dockerfile" / "launcher.py"


def _load_module(name: str, path: Path):
    """Load a Python module from an explicit path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


game = _load_module("hidden_wall_rich_gameplay", GAMEPLAY_PATH)


# The richer branch currently stops at Level 5. Add the integrated branch's
# sixth map and definition before main() or the self-tests inspect LEVELS.
LEVEL_6_MAP = [
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
]

if len(game.LEVELS) == 5:
    game.LEVEL_MAPS.append(LEVEL_6_MAP)
    game.LEVELS.append(game.LevelDefinition("Level 6", LEVEL_6_MAP))


LEVEL_PASSWORDS = {
    1: "HWM{1927}",
    2: "HWM{R3v3rs3d_5ucc3ss}",
    3: "HWM{Simon_has_cookies?}",
    4: "HWM{Y0u_g0t_this!}",
    5: "HWM{1nv35t1g4t1v3_R3v3rs3r!}",
    6: "HWM{M@k3_1t_th3_b35t_d@y}",
}


def _load_launcher():
    """Load the Docker/SSH launcher lazily."""
    return _load_module("bwsi_team2_launcher", LAUNCHER_PATH)


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
        game.clear_screen()
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

        game.clear_screen()
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


def _install_door_challenge_hook():
    """Add the Docker gate at the richer game loop's door-completion point.

    The two source branches both own a large play_level function. Recompiling
    that one function with a narrow door hook avoids maintaining a third,
    subtly divergent copy of several hundred lines of gameplay logic.
    """
    source = inspect.getsource(game.play_level)
    old = '''        if level_complete:
            return "complete"
'''
    new = '''        if level_complete:
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
'''
    if source.count(old) != 1:
        raise RuntimeError(
            "Could not merge the Docker door hook into the richer gameplay "
            "loop: its completion block has changed."
        )

    game.run_door_challenge = run_door_challenge
    game._challenge_allows_level_completion = _challenge_allows_level_completion
    exec(compile(source.replace(old, new), str(GAMEPLAY_PATH), "exec"), game.__dict__)


_install_door_challenge_hook()


def run_self_tests():
    """Run richer gameplay tests plus merged Docker-gate sanity checks."""
    # gamevfinal's scripted combat fixtures use choice 1 as the deliberately
    # wrong answer and choice 2 as the correct answer. Its first production
    # trivia entry was later edited to make choice 1 correct, so temporarily
    # supply the fixture shape the tests were written against.
    original_first_question = game.TRIVIA_QUESTIONS[0]
    game.TRIVIA_QUESTIONS[0] = {
        "question": "Self-test question",
        "choices": ["Wrong", "Correct", "Wrong", "Wrong"],
        "answer": 2,
    }
    try:
        gameplay_ok = game.run_self_tests()
    finally:
        game.TRIVIA_QUESTIONS[0] = original_first_question

    merge_checks = [
        len(game.LEVELS) == 6,
        game.LEVELS[-1].name == "Level 6",
        _check_door_password(LEVEL_PASSWORDS[1], 1),
        not _check_door_password("wrong", 1),
        not _check_door_password("anything", 99),
        _challenge_allows_level_completion(True),
        not _challenge_allows_level_completion(1),
        LAUNCHER_PATH.exists(),
    ]
    print()
    if all(merge_checks):
        print("PASS  six-level Docker/SSH merge checks")
    else:
        print("FAIL  six-level Docker/SSH merge checks")
    return gameplay_ok and all(merge_checks)


def main():
    """Run all six rich-gameplay levels with a Docker gate at every door."""
    player_state = game.PlayerState()

    for level_number in range(1, len(game.LEVELS) + 1):
        result = game.play_level(level_number, player_state)

        if result == "quit":
            print("Game closed.")
            return

        if level_number < len(game.LEVELS):
            game.choose_end_of_level_upgrade(player_state)
            print(f"Starting level {level_number + 1}.")

    print(f"You completed all {len(game.LEVELS)} levels. You win!")


# Make gameplay classes, constants, and helpers available to importers of this
# merged module without overwriting the integration functions defined above.
for _name, _value in vars(game).items():
    if _name.startswith("__") or _name in globals():
        continue
    globals()[_name] = _value


if __name__ == "__main__":
    try:
        if "--test" in sys.argv[1:]:
            if not run_self_tests():
                raise SystemExit(1)
        else:
            main()
    except (KeyboardInterrupt, EOFError):
        print("\nGame closed.")
    except (RuntimeError, ValueError) as error:
        print(f"Game setup error: {error}")
