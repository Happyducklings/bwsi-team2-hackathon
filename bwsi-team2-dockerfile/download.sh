#!/usr/bin/env bash
# BWSI Team 2 — Maze Wargame file downloader
# Pull every challenge file for a level out of its running container and onto
# the player's machine, so files that can't be viewed in the SSH terminal
# (images, pcaps, binaries) can be opened locally.
#
# Usage:
#   ./download.sh [level] [host] [port]
# Examples:
#   ./download.sh              # download Level 1 files @ localhost:2222
#   ./download.sh 2            # download Level 2 files @ localhost:2223
#   ./download.sh 6 localhost 2227
#
# Files land in downloads/level<N>/ next to this script. The level's own
# login can only read its own (non-secret) files, so gated files like
# Level 4's flag.txt are intentionally skipped with a "Permission denied".

set -uo pipefail

LEVEL="${1:-1}"
HOST="${2:-localhost}"
# Port defaults to the launcher's scheme: 2222 + (level - 1).
DEFAULT_PORT=$(( 2222 + LEVEL - 1 ))
PORT="${3:-$DEFAULT_PORT}"

USERNAME="level${LEVEL}"
PASSWORD="maze2024"
CONNECT_TIMEOUT="${MAZE_CONNECT_TIMEOUT:-5}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/downloads/level${LEVEL}"

# Match connect.sh's options so host-key prompts and slow races don't block a
# non-interactive copy.
SSH_OPTIONS=(
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o LogLevel=ERROR
    -o "ConnectTimeout=${CONNECT_TIMEOUT}"
    -o ConnectionAttempts=3
    -o PreferredAuthentications=password
    -o PubkeyAuthentication=no
    -P "$PORT"
)

if ! command -v scp >/dev/null 2>&1; then
    echo "scp is not installed; cannot download the challenge files." >&2
    exit 1
fi

mkdir -p "$DEST"

echo "Downloading Level ${LEVEL} files from ${USERNAME}@${HOST}:${PORT} -> ${DEST}"

# Copy every non-hidden file in the level's home directory. The remote glob
# is expanded by the level's login shell, so skeleton dotfiles (.bashrc, etc.)
# are left behind and only the challenge files come across. -r tolerates any
# directory a challenge might add later.
if command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$PASSWORD" \
        scp "${SSH_OPTIONS[@]}" -r "${USERNAME}@${HOST}:*" "$DEST"/
    rc=$?
else
    echo "sshpass not found — you'll be prompted for the password (${PASSWORD})."
    echo "Install sshpass (e.g. 'brew install sshpass') for a promptless copy."
    scp "${SSH_OPTIONS[@]}" -r "${USERNAME}@${HOST}:*" "$DEST"/
    rc=$?
fi

# A gated file (e.g. Level 4's flag.txt) makes scp exit non-zero even though
# the readable files copied fine, so report what actually landed instead of
# treating that as a hard failure.
echo
if [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    echo "Files downloaded to ${DEST}:"
    ls -la "$DEST"
    if [ "$rc" -ne 0 ]; then
        echo
        echo "(Some files were skipped — that's expected for gated files like"
        echo " Level 4's flag.txt, which only the exploit can read.)"
    fi
    exit 0
else
    echo "No files were downloaded. Is the Level ${LEVEL} container running on" >&2
    echo "port ${PORT}? Enter the level in the game first, then re-run this." >&2
    exit 1
fi
