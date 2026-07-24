# Blacksite // CTF

A dependency-free multiplayer browser prototype where Survivors solve existing
CTFs while an authoritative server controls a hunting Beast.

## Run it

Requirements: Node.js 20 or newer.

```sh
cd web
npm start
```

Open <http://localhost:3000> in two or more browser windows, choose different
names, and start the match. Use WASD/arrow keys to move and E beside a computer
or exit to interact.

Run the automated game-logic tests with:

```sh
npm test
```

No install step is needed because the prototype uses only Node and browser
built-ins. Multiplayer updates use Server-Sent Events; player actions use JSON
HTTP requests.

## Current full game loop

1. Players join one shared lobby.
2. Any connected player starts the match.
3. Survivors move around a wall-collision map.
4. The Beast patrols and chases the nearest Survivor in detection range.
5. A Beast collision permanently eliminates that player, who then spectates.
6. Survivors press E near a computer, use its SSH details externally, and
   submit a flag.
7. The server validates flags and shares completion with the whole team.
8. Two of three completed CTFs unlock the extraction gate.
9. The first living Survivor to physically enter the open gate wins.
10. If no living connected Survivors remain, the team loses.

## Project structure

```text
web
├── client             browser UI, input, canvas renderer
├── game-server        authoritative match, Beast, flags, HTTP/SSE server
├── ctf-environments   CTF isolation and configuration boundary
├── shared             client/server phases, states, controls, limits
└── test               server game-logic tests
```

The server is authoritative: the browser asks to move, interact, and submit a
flag, but never decides collision, elimination, progress, or victory. Correct
flags remain in `game-server/challenges.js` or the `CTF_FLAGS` environment
variable and are stripped from all public state.

## Connect the real CTFs

Update the environment variables documented in
[`ctf-environments/README.md`](ctf-environments/README.md). The checked-in
fallback commands and flags are development placeholders.

To add a challenge:

1. Add its private record in `game-server/challenges.js`.
2. Add a matching terminal with the same `challengeId` in `game-server/game.js`.
3. Adjust `requiredChallenges` if necessary.
4. Add a test covering its station-to-challenge mapping.

## Prototype constraints

This branch intentionally has one in-memory lobby and no database. Restarting
the Node process clears the room, and it is designed for trusted local/LAN
play. Before internet deployment, add authenticated room membership, request
rate limiting, TLS, durable sessions, host-only start/restart controls, and a
real CTF provisioning/reset adapter.
