# Blacksite // CTF — Learning Edition

A dependency-free browser game that teaches the core ideas behind our CTF
challenges. Players (solo or as a team) explore a map, study computer stations
that each explain a cybersecurity skill, dodge an authoritative hunting Beast,
and reach the extraction gate. When they're ready for the real puzzles, they
grab the terminal CTF game from GitHub.

The web game is the **on-ramp**; the actual hands-on challenges live in the
separate terminal game.

## Run it

Requirements: Node.js 20 or newer.

```sh
cd web
npm start
```

Open <http://localhost:3000>. You can play alone, or open two or more browser
windows with different names for co-op. Use WASD/arrow keys to move and E beside
a station or the exit to interact.

Run the automated game-logic tests with:

```sh
npm test
```

No install step is needed — the app uses only Node and browser built-ins.
Multiplayer updates use Server-Sent Events; player actions use JSON HTTP
requests.

## Full game loop

1. Players join one shared lobby (one player is enough to start; teams welcome).
2. Any connected player starts the match.
3. Players move around a wall-collision map.
4. The Beast patrols and chases the nearest player in detection range.
5. A Beast collision permanently eliminates that player, who then spectates.
6. Players press E at a station to read its topic, then press **Mark reviewed**.
7. Reviewing a station is shared with the whole team.
8. Studying the required number of stations (3 of 5) unlocks the extraction gate.
9. The first living player to physically enter the open gate wins.
10. If no living connected players remain, the team loses.

## Educational stations

Each station on the map teaches one topic, with a short explanation and
external further-reading links (picoCTF Primer, GeeksforGeeks, Wireshark docs,
OSINT Framework, CyberSeek, and more):

| Station | Topic |
| --- | --- |
| Alpha | Cryptography & Steganography |
| Beta | Reverse Engineering & Binary Exploitation |
| Gamma | Network Analysis |
| Delta | Open-Source Intelligence (OSINT) |
| Epsilon | Careers in Cybersecurity |

All station content lives in `game-server/topics.js`. There are **no flags or
secrets in the web game** — the real challenges are only in the terminal game.

## Project structure

```text
web
├── client        browser UI, input, canvas renderer
├── game-server   authoritative match, Beast, topics, HTTP/SSE server
├── shared        client/server phases, states, controls, limits
└── test          server game-logic tests
```

The server is authoritative: the browser asks to move, interact, and review a
station, but never decides collision, elimination, progress, or victory.

## The terminal CTF game

The "Get the terminal CTF game" links point to the GitHub repository's `main`
branch. Update the URL in `client/index.html` (two links) if that ever changes.

## Edit or add a station

1. Add a topic — `terminalId`, `category`, `title`, `summary`, `body`
   (array of paragraphs), and `reading` (array of `{label, url}`) — in
   `game-server/topics.js`.
2. Add a matching terminal with the same `topicId` and an on-map `{x, y}` in
   `game-server/game.js` (place it on an open floor tile).
3. Adjust `requiredTopics` in `game.js` if needed.
4. `npm test` — the suite checks every station is reachable from spawn and that
   station count matches topic count.

## Deploy on Railway

The server binds `process.env.PORT` on `0.0.0.0` and needs no build step, so it
runs on Railway as-is. Key setting:

- **Set the service root directory to `web/`.** This repo's root has no
  `package.json`; the Node app lives in `web/`. In Railway, set the root
  directory (or a `RAILWAY_DOCKERFILE_PATH`/watch path) to `web` so Nixpacks
  detects `web/package.json` and runs `npm start`.
- Node 20+ is requested via `engines` in `package.json`.
- No environment variables are required (the web game has no secrets). `PORT`
  is provided by Railway automatically.

## Prototype constraints

One in-memory lobby, no database. Restarting the Node process clears the room,
and it is designed for trusted local/LAN or a single shared deployment. Before
hardening for untrusted internet use, add authenticated room membership,
request rate limiting, durable sessions, and host-only start/restart controls.
