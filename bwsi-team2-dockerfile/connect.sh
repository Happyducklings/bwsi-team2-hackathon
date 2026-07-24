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

# Prefer sshpass if installed; fall back to a here-doc + ssh approach.
if command -v sshpass >/dev/null 2>&1; then
    exec sshpass -p "$PASSWORD" \
        ssh \
            -tt \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -o LogLevel=ERROR \
            -p "$PORT" \
            "${USERNAME}@${HOST}"
else
    echo "sshpass not found — falling back to a manual password prompt."
    echo "Install sshpass (e.g. 'sudo apt install sshpass') for a seamless flow."
    exec ssh \
        -tt \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$PORT" \
        "${USERNAME}@${HOST}"
fi
