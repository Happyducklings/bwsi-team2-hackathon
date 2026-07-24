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
import time
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
# port collision. CONNECT_PORT changes the base port.
BASE_HOST_PORT = int(os.environ.get("CONNECT_PORT", "2222"))
DEFAULT_HOST = os.environ.get("CONNECT_HOST", "localhost")

# Set MAZE_FORCE_REBUILD=1 to always rebuild, even if the image exists.
FORCE_REBUILD = os.environ.get("MAZE_FORCE_REBUILD", "0") == "1"
SSH_ATTEMPTS = max(1, int(os.environ.get("MAZE_SSH_ATTEMPTS", "3")))

# Avoid rebuilding once per level or password retry in the same game process.
# We still build once per process so Docker can refresh a stale named image.
_IMAGE_READY = False
_ACTIVE_LEVEL = DEFAULT_LEVEL


def container_name_for(level: int) -> str:
    """Return the per-level container name; honors MAZE_CONTAINER override."""
    override = os.environ.get("MAZE_CONTAINER")
    if override:
        return override
    return f"maze-level{level}"


def port_for(level: int) -> int:
    """Return the host SSH port assigned to a level."""
    if level < 1:
        raise ValueError(f"Level must be positive, got {level}.")
    port = BASE_HOST_PORT + level - 1
    if port > 65535:
        raise ValueError(f"SSH port for level {level} is out of range: {port}.")
    return port


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
    try:
        return subprocess.call(cmd, **kwargs)
    except FileNotFoundError:
        print(f"[launcher] Command not found: {cmd[0]}", file=sys.stderr)
        return 127
    except OSError as error:
        print(f"[launcher] Could not run {cmd[0]}: {error}", file=sys.stderr)
        return 1


def build_image(level: int = DEFAULT_LEVEL) -> int:
    """Build or refresh the Docker image once per game process.

    Docker's layer cache makes an unchanged build quick while still ensuring
    Dockerfile edits are not hidden by an old image with the same name.
    """
    global _IMAGE_READY

    if _IMAGE_READY and not FORCE_REBUILD:
        print(f"[launcher] Image '{IMAGE_NAME}' is ready — skipping rebuild.")
        return 0

    if FORCE_REBUILD:
        print(f"[launcher] MAZE_FORCE_REBUILD=1 — rebuilding '{IMAGE_NAME}' "
              "without the Docker cache.")
    else:
        print(f"[launcher] Building or refreshing image '{IMAGE_NAME}'.")

    if not DOCKERFILE.exists():
        print(f"[launcher] Dockerfile not found at {DOCKERFILE}", file=sys.stderr)
        return 1

    command = ["docker", "build"]
    if FORCE_REBUILD:
        command.append("--no-cache")
    command.extend(["-t", IMAGE_NAME, "-f", str(DOCKERFILE), str(HERE)])
    rc = run(command)
    if rc == 0:
        _IMAGE_READY = True
    return rc


def start_container(level: int = DEFAULT_LEVEL) -> int:
    """Start the per-level container, recreating it if one is already running.

    ``docker run --rm`` would be simpler, but we want a stable name so the SSH
    script (and the player) can reach it predictably across doors.
    """
    global _ACTIVE_LEVEL

    container_name = container_name_for(level)
    host_port = port_for(level)
    # If a previous container with this name exists, remove it so we can
    # re-publish the port cleanly.
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
        )
    except FileNotFoundError:
        print("[launcher] Command not found: docker", file=sys.stderr)
        return 127
    except OSError as error:
        print(f"[launcher] Could not run docker: {error}", file=sys.stderr)
        return 1

    rc = run(
        [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"127.0.0.1:{host_port}:22",
            IMAGE_NAME,
        ]
    )
    if rc == 0:
        _ACTIVE_LEVEL = level
    return rc


def wait_for_ssh(
    level: int | None = None,
    timeout_seconds: float = 30,
) -> bool:
    """Block until the requested (or most recently started) SSH port is ready."""
    import socket

    if level is None:
        level = _ACTIVE_LEVEL
    host_port = port_for(level)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((DEFAULT_HOST, host_port))
                # A successful TCP connect alone can race with sshd startup.
                # Wait for an actual SSH identification banner before handing
                # the terminal to the client.
                if sock.recv(64).startswith(b"SSH-"):
                    return True
                time.sleep(0.5)
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

    host_port = port_for(level)
    if not wait_for_ssh(level):
        container_name = container_name_for(level)
        print(f"[launcher] SSH port {host_port} never came up. Check 'docker logs "
              f"{container_name}'.", file=sys.stderr)
        return 1

    print(f"[launcher] Connecting to {DEFAULT_HOST}:{host_port} as level{level} "
          "in this terminal...")
    print("[launcher] (type 'exit' to leave the challenge and return to the maze.)")
    print()
    sys.stdout.flush()

    # Keep SSH in the launcher's existing session and foreground process
    # group. Creating a new session here can make SSH receive SIGTTIN as soon
    # as it reads the terminal, which looks like a session that flashes open
    # and immediately closes.
    #
    # Save the terminal attributes as an extra safeguard. SSH normally
    # restores them, but an early disconnect or signal can otherwise leave
    # input echo/canonical mode altered and hide the next password prompt.
    terminal_fd = None
    terminal_state = None
    try:
        if sys.stdin.isatty():
            import termios

            terminal_fd = sys.stdin.fileno()
            terminal_state = termios.tcgetattr(terminal_fd)
    except (AttributeError, ImportError, OSError, ValueError):
        terminal_fd = None
        terminal_state = None

    command = [
        str(CONNECT_SCRIPT),
        str(level),
        DEFAULT_HOST,
        str(host_port),
    ]
    try:
        for attempt in range(1, SSH_ATTEMPTS + 1):
            rc = run(command)
            # OpenSSH uses 255 for connection/authentication failures.
            # Retry those briefly; a normal `exit` returns 0 and must return
            # control to the game's password screen immediately.
            if rc != 255 or attempt == SSH_ATTEMPTS:
                return rc
            print(
                f"[launcher] SSH ended before the session was established "
                f"(attempt {attempt}/{SSH_ATTEMPTS}); retrying...",
                file=sys.stderr,
            )
            time.sleep(0.5)
            wait_for_ssh(level, timeout_seconds=5)
    finally:
        if terminal_fd is not None and terminal_state is not None:
            try:
                import termios

                termios.tcsetattr(
                    terminal_fd,
                    termios.TCSADRAIN,
                    terminal_state,
                )
            except (ImportError, OSError):
                pass
        # Keep the next prompt from being stuck behind buffered launcher text.
        sys.stdout.flush()
        sys.stderr.flush()


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
