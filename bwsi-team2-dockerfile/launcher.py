#!/usr/bin/env python3
"""BWSI Team 2 — Maze Wargame launcher.

When the player reaches a door in the maze, the orchestrator invokes this
script. It:

    1. Waits for any keypress ("press any key to load the docker terminal").
    2. Ensures the per-level Docker image is built (building only when needed).
    3. Starts a container for the level and publishes SSH to the host.
    4. Opens an SSH session into that container in a new (or current) terminal.

For now only Level 1 is wired up; the remaining levels are placeholders that
the team will fill in later.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCKERFILE = HERE / "Dockerfile"
CONNECT_SCRIPT = HERE / "connect.sh"

# The level the player is about to enter. Today this is hard-coded to 1;
# the maze orchestrator will eventually set this dynamically.
CURRENT_LEVEL = 1

# Image / container naming. Keep these stable so we can detect an existing
# image and skip rebuilding.
IMAGE_NAME = os.environ.get("MAZE_IMAGE", "maze-wargame")
CONTAINER_NAME = os.environ.get("MAZE_CONTAINER", f"maze-level{CURRENT_LEVEL}")

# Host port that gets mapped to container port 22.
HOST_PORT = os.environ.get("CONNECT_PORT", "2222")
DEFAULT_HOST = os.environ.get("CONNECT_HOST", "localhost")

# Set MAZE_FORCE_REBUILD=1 to always rebuild, even if the image exists.
FORCE_REBUILD = os.environ.get("MAZE_FORCE_REBUILD", "0") == "1"


def wait_for_keypress() -> None:
    """Block until the user presses Enter, then return."""
    print()
    print("==============================================")
    print("  A door lies before you...")
    print("  Press ENTER to build & open the Level "
          f"{CURRENT_LEVEL} docker terminal.")
    print("==============================================")
    try:
        input()
    except EOFError:
        # No TTY available (e.g. piped input) — just continue.
        pass


def run(cmd: list[str], **kwargs) -> int:
    """Run a command, echoing it first, and stream output."""
    print(f"[launcher] $ {' '.join(cmd)}")
    return subprocess.call(cmd, **kwargs)


def image_exists() -> bool:
    """Return True if the Docker image is already built locally."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE_NAME],
        capture_output=True,
    )
    return result.returncode == 0


def build_image() -> int:
    """Build the Docker image, unless it already exists and rebuild isn't forced."""
    if not FORCE_REBUILD and image_exists():
        print(f"[launcher] Image '{IMAGE_NAME}' already exists — skipping build.")
        print("[launcher] (set MAZE_FORCE_REBUILD=1 to force a rebuild.)")
        return 0

    if FORCE_REBUILD:
        print(f"[launcher] MAZE_FORCE_REBUILD=1 — rebuilding '{IMAGE_NAME}'.")
    else:
        print(f"[launcher] Image '{IMAGE_NAME}' missing — building it now.")

    if not DOCKERFILE.exists():
        print(f"[launcher] Dockerfile not found at {DOCKERFILE}", file=sys.stderr)
        return 1

    return run(
        ["docker", "build", "-t", IMAGE_NAME, "-f", str(DOCKERFILE), str(HERE)]
    )


def start_container() -> int:
    """Start the per-level container, recreating it if one is already running.

    ``docker run --rm`` would be simpler, but we want a stable name so the SSH
    script (and the player) can reach it predictably across doors.
    """
    # If a previous container with this name exists, remove it so we can
    # re-publish the port cleanly.
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )

    return run(
        [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "-p", f"{HOST_PORT}:22",
            IMAGE_NAME,
        ]
    )


def wait_for_ssh(timeout_seconds: int = 30) -> bool:
    """Block until the container's SSH port is accepting connections."""
    import socket
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((DEFAULT_HOST, int(HOST_PORT)))
                return True
            except OSError:
                time.sleep(0.5)
    return False


def launch_ssh_in_place() -> int:
    """Replace this Python process with the SSH session in the current terminal.

    We use ``os.execvp`` rather than ``subprocess.call`` so the SSH client
    inherits the controlling TTY directly. That keeps resize/line-editing/
    Ctrl-C working normally inside the same window the player already has.
    """
    if not CONNECT_SCRIPT.exists():
        print(f"[launcher] connect.sh not found at {CONNECT_SCRIPT}", file=sys.stderr)
        return 1

    if not wait_for_ssh():
        print(f"[launcher] SSH port {HOST_PORT} never came up. Check 'docker logs "
              f"{CONTAINER_NAME}'.", file=sys.stderr)
        return 1

    print(f"[launcher] Connecting to {DEFAULT_HOST}:{HOST_PORT} as level{CURRENT_LEVEL} "
          "in this terminal...")
    print("[launcher] (type 'exit' to leave the maze and return to the launcher.)")
    print()

    # execvp replaces the launcher process with connect.sh, which in turn
    # execs ssh. The terminal stays put; only the foreground process changes.
    try:
        os.execvp(
            str(CONNECT_SCRIPT),
            [str(CONNECT_SCRIPT), str(CURRENT_LEVEL), DEFAULT_HOST, HOST_PORT],
        )
    except OSError as exc:
        print(f"[launcher] Failed to exec connect.sh: {exc}", file=sys.stderr)
        return 1
    # execvp only returns on failure.
    return 1


def main() -> int:
    wait_for_keypress()

    rc = build_image()
    if rc != 0:
        return rc

    rc = start_container()
    if rc != 0:
        return rc

    return launch_ssh_in_place()


if __name__ == "__main__":
    sys.exit(main())
