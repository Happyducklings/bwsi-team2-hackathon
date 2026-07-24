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

# The level the player is about to enter. The maze orchestrator passes the
# current level as a function argument; this is the default for when the
# launcher is invoked as a standalone script.
DEFAULT_LEVEL = 1

# Image / container naming. Keep these stable so we can detect an existing
# image and skip rebuilding.
IMAGE_NAME = os.environ.get("MAZE_IMAGE", "maze-wargame")
# CONTAINER_NAME is computed per level in `container_name_for` so the
# launcher can serve level1...level5 from the same image.

# Base host port that gets mapped to container port 22. Each level uses
# BASE_HOST_PORT + (level - 1) so multiple levels can coexist without a
# port collision. Override with the CONNECT_PORT env var to pin every
# level to a single port (useful for scripted tests).
BASE_HOST_PORT = int(os.environ.get("CONNECT_PORT", "2222"))
DEFAULT_HOST = os.environ.get("CONNECT_HOST", "localhost")

# Set MAZE_FORCE_REBUILD=1 to always rebuild, even if the image exists.
FORCE_REBUILD = os.environ.get("MAZE_FORCE_REBUILD", "0") == "1"


def container_name_for(level: int) -> str:
    """Return the per-level container name; honors MAZE_CONTAINER override."""
    override = os.environ.get("MAZE_CONTAINER")
    if override:
        return override
    return f"maze-level{level}"


def wait_for_keypress(level: int = DEFAULT_LEVEL) -> None:
    """Block until the user presses Enter, then return.

    The caller decides when to use this: the maze orchestrator shows it only
    the first time the door is reached, not on every retry, so a wrong
    password doesn't require an extra ENTER before reconnecting.
    """
    print()
    print("==============================================")
    print("  A door lies before you...")
    print("  Press ENTER to build & open the Level "
          f"{level} docker terminal.")
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


def build_image(level: int = DEFAULT_LEVEL) -> int:
    """Build the Docker image, unless it already exists and rebuild isn't forced.

    The level argument is accepted for symmetry with the other entry points;
    the image is the same for all levels today, so the level only affects
    logging.
    """
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


def start_container(level: int = DEFAULT_LEVEL) -> int:
    """Start the per-level container, recreating it if one is already running.

    ``docker run --rm`` would be simpler, but we want a stable name so the SSH
    script (and the player) can reach it predictably across doors.
    """
    container_name = container_name_for(level)
    # If a previous container with this name exists, remove it so we can
    # re-publish the port cleanly.
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
    )

    return run(
        [
            "docker", "run", "-d",
            "--name", container_name,
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


def launch_ssh_in_place(level: int = DEFAULT_LEVEL) -> int:
    """Run the SSH session in the current terminal as a child process.

    ``connect.sh`` itself does ``exec ssh``, so the foreground process is
    still ssh; ``subprocess.call`` adds one short-lived Python layer that
    returns to the caller the moment the player types ``exit`` inside the
    shell. That round-trip is what lets the maze orchestrator (game v2.py)
    ask for the level password after the SSH session ends.
    """
    if not CONNECT_SCRIPT.exists():
        print(f"[launcher] connect.sh not found at {CONNECT_SCRIPT}", file=sys.stderr)
        return 1

    if not wait_for_ssh():
        container_name = container_name_for(level)
        print(f"[launcher] SSH port {HOST_PORT} never came up. Check 'docker logs "
              f"{container_name}'.", file=sys.stderr)
        return 1

    print(f"[launcher] Connecting to {DEFAULT_HOST}:{HOST_PORT} as level{level} "
          "in this terminal...")
    print("[launcher] (type 'exit' to leave the challenge and return to the maze.)")
    print()

    # subprocess.call blocks until the SSH session exits. SSH inherits the
    # controlling TTY because we pass no stdin/stdout/stderr overrides, so
    # the player lands directly in the shell in this terminal.
    #
    # ``start_new_session=True`` puts the child in a new session and process
    # group. Without it, the child shares the parent's controlling TTY but
    # is NOT the foreground process group, so reading from the terminal
    # delivers SIGTTIN and SSH drops the connection immediately. This is
    # what made the remote session "open then instantly close" on the
    # first door reach.
    #
    # SSH (and the remote shell it spawns) calls ``tcsetpgrp`` to make
    # itself the foreground process group of the TTY while the player is
    # inside the challenge. When the SSH session exits, that foreground
    # process group belongs to the now-dead child session. If we don't
    # restore the foreground process group back to the launcher before
    # returning, the orchestrator's subsequent ``input()`` /
    # ``getpass.getpass()`` reads are delivered to a TTY whose foreground
    # process group is dead, so the read either returns ``EIO`` or blocks
    # forever. On the first door reach the launcher was the only reader
    # so the symptom was masked; on the second door reach the maze loop
    # needs to read input again and the broken TTY state manifests as
    # "the password prompt never appears."
    parent_pgid = os.getpgrp()
    try:
        return subprocess.call(
            [str(CONNECT_SCRIPT), str(level), DEFAULT_HOST, HOST_PORT],
            start_new_session=True,
        )
    finally:
        # Reclaim the controlling TTY so the caller can read from it again.
        # This is a no-op when stdin isn't a TTY (e.g. piped input).
        try:
            fd = sys.stdin.fileno()
        except (AttributeError, ValueError, OSError):
            fd = -1
        if fd >= 0:
            try:
                os.tcsetpgrp(fd, parent_pgid)
            except (OSError, PermissionError):
                # Not a TTY, or we don't own it — nothing to restore.
                pass


def main(level: int = DEFAULT_LEVEL) -> int:
    wait_for_keypress(level)

    rc = build_image(level)
    if rc != 0:
        return rc

    rc = start_container(level)
    if rc != 0:
        return rc

    return launch_ssh_in_place(level)


if __name__ == "__main__":
    sys.exit(main())
