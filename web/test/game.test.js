import assert from "node:assert/strict";
import test from "node:test";
import { CHALLENGES } from "../game-server/challenges.js";
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

test("terminal interaction requires proximity and public state never contains flags", () => {
  const { game, advance } = fixture();
  const id = game.join("Cipher");
  game.start(id);
  advance(1_300);

  assert.throws(() => game.interact(id), /Move next/);
  const terminal = MAP.terminals[0];
  Object.assign(game.players.get(id), { x: terminal.x, y: terminal.y - 1 });
  const result = game.interact(id);
  assert.equal(result.kind, "terminal");
  assert.equal(result.challenge.id, terminal.challengeId);
  assert.equal("flag" in result.challenge, false);
  assert.equal(JSON.stringify(game.publicState(id)).includes(CHALLENGES[0].flag), false);
});

test("correct flags are shared, unlock the exit, and wrong flags do not progress", () => {
  const { game, advance } = fixture();
  const first = game.join("One");
  const second = game.join("Two");
  game.start(first);
  advance(1_300);

  for (let index = 0; index < 2; index += 1) {
    const terminal = MAP.terminals[index];
    const actor = index ? second : first;
    Object.assign(game.players.get(actor), { x: terminal.x, y: terminal.y - 1 });
    const wrong = game.submitFlag(actor, terminal.challengeId, "wrong");
    assert.equal(wrong.correct, false);
    assert.equal(game.completedChallenges.size, index);
    const correct = game.submitFlag(actor, terminal.challengeId, CHALLENGES[index].flag);
    assert.equal(correct.correct, true);
  }

  assert.equal(game.phase, MATCH_PHASES.EXIT_UNLOCKED);
  assert.equal(game.publicState(first).completedChallenges.length, 2);
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
  game.completedChallenges.add("linux-basics");
  game.players.get(id).state = PLAYER_STATES.ELIMINATED;

  game.restart(id);
  assert.equal(game.phase, MATCH_PHASES.LOBBY);
  assert.equal(game.completedChallenges.size, 0);
  assert.equal(game.players.get(id).state, PLAYER_STATES.ALIVE);
  assert.deepEqual(
    { x: game.players.get(id).x, y: game.players.get(id).y },
    MAP.spawn,
  );
});
