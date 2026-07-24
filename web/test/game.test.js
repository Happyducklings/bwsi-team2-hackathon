import assert from "node:assert/strict";
import test from "node:test";
import { TOPICS, publicTopic } from "../game-server/topics.js";
import { Game, MAP } from "../game-server/game.js";
import { MATCH_PHASES, PLAYER_STATES } from "../shared/protocol.js";

function fixture() {
  let time = 1_000;
  let nextId = 1;
  const game = new Game({
    now: () => time,
    idFactory: () => `player-${nextId++}`,
  });
  return {
    game,
    advance(milliseconds) {
      time += milliseconds;
      game.updatePhase();
    },
  };
}

// Self-contained BFS over the map so terminal placement can be validated
// without exporting the server's private movement helpers.
function isWall(point) {
  return MAP.walls.some(
    (wall) =>
      point.x >= wall.x &&
      point.x < wall.x + wall.w &&
      point.y >= wall.y &&
      point.y < wall.y + wall.h,
  );
}

function reachableFromSpawn() {
  const seen = new Set([`${MAP.spawn.x},${MAP.spawn.y}`]);
  const queue = [MAP.spawn];
  while (queue.length) {
    const current = queue.shift();
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const next = { x: current.x + dx, y: current.y + dy };
      const key = `${next.x},${next.y}`;
      if (next.x < 0 || next.y < 0 || next.x >= MAP.width || next.y >= MAP.height) continue;
      if (seen.has(key) || isWall(next)) continue;
      seen.add(key);
      queue.push(next);
    }
  }
  return seen;
}

test("players join a lobby with unique names and start a match", () => {
  const { game, advance } = fixture();
  const first = game.join("Ada");
  const second = game.join("Lin");
  assert.equal(game.players.size, 2);
  assert.throws(() => game.join("ada"), /already in use/);

  game.start(first);
  assert.equal(game.phase, MATCH_PHASES.STARTING);
  assert.throws(() => game.move(second, 1, 0), /unavailable/);
  advance(1_300);
  assert.equal(game.phase, MATCH_PHASES.PLAYING);
});

test("a single operative can start and play solo", () => {
  const { game, advance } = fixture();
  const id = game.join("Solo");
  assert.equal(game.players.size, 1);
  game.start(id);
  advance(1_300);
  assert.equal(game.phase, MATCH_PHASES.PLAYING);
});

test("every station and the exit are reachable from spawn", () => {
  const reachable = reachableFromSpawn();
  for (const terminal of MAP.terminals) {
    assert.equal(isWall(terminal), false, `terminal ${terminal.id} sits on a wall`);
    assert.ok(reachable.has(`${terminal.x},${terminal.y}`), `terminal ${terminal.id} is unreachable`);
  }
  assert.ok(reachable.has(`${MAP.exit.x},${MAP.exit.y}`), "exit is unreachable");
  assert.equal(MAP.terminals.length, TOPICS.length);
});

test("movement is cardinal, server-authoritative, and blocked by walls", () => {
  const { game, advance } = fixture();
  const id = game.join("Mover");
  game.start(id);
  advance(1_300);

  assert.throws(() => game.move(id, 1, 1), /Invalid movement/);
  const player = game.players.get(id);
  player.x = 5;
  player.y = 2;
  assert.deepEqual(game.move(id, 1, 0), { moved: false });
  assert.equal(player.x, 5);
  assert.deepEqual(game.move(id, 0, 1), { moved: true });
  assert.equal(player.y, 3);
});

test("interacting with a station returns its educational content and no secrets", () => {
  const { game, advance } = fixture();
  const id = game.join("Learner");
  game.start(id);
  advance(1_300);

  assert.throws(() => game.interact(id), /Move next/);
  const terminal = MAP.terminals[0];
  Object.assign(game.players.get(id), { x: terminal.x, y: terminal.y - 1 });
  const result = game.interact(id);
  assert.equal(result.kind, "terminal");
  assert.equal(result.topic.id, terminal.topicId);
  assert.ok(Array.isArray(result.topic.body) && result.topic.body.length > 0);
  assert.ok(Array.isArray(result.topic.reading) && result.topic.reading.length > 0);
  assert.equal(result.topic.studied, false);
  // Educational content is public — but there is never a flag anywhere.
  assert.equal(JSON.stringify(game.publicState(id)).toLowerCase().includes("\"flag\""), false);
});

test("publicTopic exposes only presentational fields", () => {
  for (const topic of TOPICS) {
    const safe = publicTopic(topic);
    assert.deepEqual(
      Object.keys(safe).sort(),
      ["body", "category", "id", "reading", "summary", "title"],
    );
    assert.equal("terminalId" in safe, false);
  }
});

test("studying the required number of stations unlocks the exit", () => {
  const { game, advance } = fixture();
  const first = game.join("One");
  const second = game.join("Two");
  game.start(first);
  advance(1_300);

  assert.equal(game.requiredTopics, 3);
  for (let index = 0; index < game.requiredTopics; index += 1) {
    const terminal = MAP.terminals[index];
    const actor = index % 2 === 0 ? first : second;
    const other = actor === first ? second : first;
    Object.assign(game.players.get(actor), { x: terminal.x, y: terminal.y - 1 });
    assert.throws(
      () => game.studyTopic(other, terminal.topicId),
      /Stay beside/,
      "a player far from the station should not be able to review it",
    );
    const result = game.studyTopic(actor, terminal.topicId);
    assert.equal(result.studied, true);
    assert.equal(game.studiedTopics.size, index + 1);
  }

  assert.equal(game.phase, MATCH_PHASES.EXIT_UNLOCKED);
  assert.equal(game.publicState(first).studiedTopics.length, 3);
});

test("re-reviewing an already-studied station is idempotent", () => {
  const { game, advance } = fixture();
  const id = game.join("Repeat");
  game.start(id);
  advance(1_300);
  const terminal = MAP.terminals[0];
  Object.assign(game.players.get(id), { x: terminal.x, y: terminal.y - 1 });

  assert.equal(game.studyTopic(id, terminal.topicId).alreadyStudied, false);
  assert.equal(game.studyTopic(id, terminal.topicId).alreadyStudied, true);
  assert.equal(game.studiedTopics.size, 1);
});

test("an alive player must physically enter the unlocked exit to win", () => {
  const { game, advance } = fixture();
  const id = game.join("Runner");
  game.start(id);
  advance(1_300);
  game.phase = MATCH_PHASES.EXIT_UNLOCKED;
  Object.assign(game.players.get(id), { x: MAP.exit.x - 1, y: MAP.exit.y });

  game.move(id, 1, 0);
  assert.equal(game.phase, MATCH_PHASES.FINISHED);
  assert.equal(game.finishReason, "escaped");
  assert.equal(game.players.get(id).state, PLAYER_STATES.ESCAPED);
});

test("the Beast chases, permanently eliminates, and can cause defeat", () => {
  const { game, advance } = fixture();
  const id = game.join("Target");
  game.start(id);
  advance(1_300);
  Object.assign(game.players.get(id), { x: 20, y: 11 });
  Object.assign(game.beast, { x: 20, y: 12 });

  const eliminated = game.tickBeast();
  assert.deepEqual(eliminated, [id]);
  assert.equal(game.players.get(id).state, PLAYER_STATES.ELIMINATED);
  assert.equal(game.phase, MATCH_PHASES.FINISHED);
  assert.equal(game.finishReason, "eliminated");
  assert.throws(() => game.move(id, 1, 0), /spectate/);
});

test("restart preserves connected player identities and clears match state", () => {
  const { game } = fixture();
  const id = game.join("Again");
  game.phase = MATCH_PHASES.FINISHED;
  game.finishReason = "eliminated";
  game.studiedTopics.add("crypto-stego");
  game.players.get(id).state = PLAYER_STATES.ELIMINATED;

  game.restart(id);
  assert.equal(game.phase, MATCH_PHASES.LOBBY);
  assert.equal(game.studiedTopics.size, 0);
  assert.equal(game.players.get(id).state, PLAYER_STATES.ALIVE);
  assert.deepEqual(
    { x: game.players.get(id).x, y: game.players.get(id).y },
    MAP.spawn,
  );
});
