#!/usr/bin/env bash
# BWSI Team 2 — Maze Wargame SSH launcher
# Connect to the running maze container as the requested level user.
#
# Usage:
#   ./connect.sh [level] [host] [port]
# Examples:
#   ./connect.sh                # connect to level1 @ localhost:2222
#   ./connect.sh 1              # connect to level1 @ localhost:2222
#   ./connect.sh 1 localhost 2222

set -euo pipefail

LEVEL="${1:-1}"
HOST="${2:-localhost}"
PORT="${3:-2222}"

USERNAME="level${LEVEL}"
PASSWORD="maze2024"
CONNECT_TIMEOUT="${MAZE_CONNECT_TIMEOUT:-5}"

# These options keep initial connection races short and predictable. The
# Python launcher retries exit code 255, while keepalives detect a genuinely
# dead session instead of leaving the terminal stuck.
SSH_OPTIONS=(
    -tt
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o LogLevel=ERROR
    -o "ConnectTimeout=${CONNECT_TIMEOUT}"
    -o ConnectionAttempts=3
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=3
    -o PreferredAuthentications=password
    -o PubkeyAuthentication=no
    -p "$PORT"
)

if ! command -v ssh >/dev/null 2>&1; then
    echo "ssh is not installed; cannot open the challenge session." >&2
    exit 255
fi

# Prefer sshpass if installed; otherwise use SSH's normal password prompt.
if command -v sshpass >/dev/null 2>&1; then
    exec sshpass -p "$PASSWORD" \
        ssh "${SSH_OPTIONS[@]}" "${USERNAME}@${HOST}"
else
    echo "sshpass not found — falling back to a manual password prompt."
    echo "Install sshpass (e.g. 'sudo apt install sshpass') for a seamless flow."
    exec ssh "${SSH_OPTIONS[@]}" "${USERNAME}@${HOST}"
fi
