import { randomUUID } from "node:crypto";
import { TOPICS, publicTopic } from "./topics.js";
import { LIMITS, MATCH_PHASES, PLAYER_STATES } from "../shared/protocol.js";

export const MAP = Object.freeze({
  width: 24,
  height: 15,
  spawn: { x: 2, y: 2 },
  beastSpawn: { x: 20, y: 12 },
  exit: { x: 22, y: 7 },
  terminals: [
    { id: "terminal-alpha", topicId: "crypto-stego", x: 4, y: 12 },
    { id: "terminal-beta", topicId: "re-binexp", x: 12, y: 2 },
    { id: "terminal-gamma", topicId: "network-analysis", x: 18, y: 10 },
    { id: "terminal-delta", topicId: "osint", x: 21, y: 2 },
    { id: "terminal-epsilon", topicId: "cyber-careers", x: 2, y: 7 },
  ],
  patrol: [
    { x: 20, y: 12 },
    { x: 20, y: 3 },
    { x: 14, y: 3 },
    { x: 14, y: 12 },
  ],
  walls: [
    { x: 0, y: 0, w: 24, h: 1 },
    { x: 0, y: 14, w: 24, h: 1 },
    { x: 0, y: 0, w: 1, h: 15 },
    { x: 23, y: 0, w: 1, h: 15 },
    { x: 6, y: 1, w: 1, h: 5 },
    { x: 6, y: 8, w: 1, h: 6 },
    { x: 10, y: 4, w: 8, h: 1 },
    { x: 10, y: 4, w: 1, h: 5 },
    { x: 10, y: 11, w: 1, h: 3 },
    { x: 14, y: 7, w: 6, h: 1 },
    { x: 19, y: 7, w: 1, h: 4 },
  ],
});

const COLORS = ["#64d8ff", "#ffd166", "#9bff8a", "#f58cff", "#ff9f68", "#a7b4ff"];
const START_COUNTDOWN_MS = 1_200;
const BEAST_DETECTION_DISTANCE = 7;

function pointKey({ x, y }) {
  return `${x},${y}`;
}

function distance(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function isWall(point) {
  return MAP.walls.some(
    (wall) =>
      point.x >= wall.x &&
      point.x < wall.x + wall.w &&
      point.y >= wall.y &&
      point.y < wall.y + wall.h,
  );
}

function validTile(point) {
  return (
    Number.isInteger(point.x) &&
    Number.isInteger(point.y) &&
    point.x >= 0 &&
    point.y >= 0 &&
    point.x < MAP.width &&
    point.y < MAP.height &&
    !isWall(point)
  );
}

function nextStep(start, goal) {
  if (pointKey(start) === pointKey(goal)) return start;
  const queue = [start];
  const seen = new Set([pointKey(start)]);
  const previous = new Map();
  const directions = [
    { x: 1, y: 0 },
    { x: -1, y: 0 },
    { x: 0, y: 1 },
    { x: 0, y: -1 },
  ];

  while (queue.length) {
    const current = queue.shift();
    for (const direction of directions) {
      const candidate = { x: current.x + direction.x, y: current.y + direction.y };
      const key = pointKey(candidate);
      if (!validTile(candidate) || seen.has(key)) continue;
      seen.add(key);
      previous.set(key, current);
      if (key === pointKey(goal)) {
        let step = candidate;
        while (previous.get(pointKey(step)) && pointKey(previous.get(pointKey(step))) !== pointKey(start)) {
          step = previous.get(pointKey(step));
        }
        return step;
      }
      queue.push(candidate);
    }
  }
  return start;
}

export class Game {
  constructor({ now = () => Date.now(), idFactory = randomUUID } = {}) {
    this.now = now;
    this.idFactory = idFactory;
    this.reset();
  }

  reset() {
    this.phase = MATCH_PHASES.LOBBY;
    this.players = new Map();
    this.studiedTopics = new Set();
    // Require a majority of stations so both solo and team play stay winnable.
    this.requiredTopics = 3;
    this.winner = null;
    this.startedAt = null;
    this.finishReason = null;
    this.beast = {
      ...MAP.beastSpawn,
      mode: "patrol",
      targetId: null,
      patrolIndex: 0,
    };
  }

  join(rawName) {
    if (this.phase !== MATCH_PHASES.LOBBY) {
      throw new Error("This match has already started.");
    }
    const name = String(rawName || "").trim().slice(0, LIMITS.MAX_NAME_LENGTH);
    if (!name) throw new Error("Enter a display name.");
    const duplicate = [...this.players.values()].some(
      (player) => player.name.toLowerCase() === name.toLowerCase(),
    );
    if (duplicate) throw new Error("That display name is already in use.");

    const id = this.idFactory();
    const offset = this.players.size % 4;
    this.players.set(id, {
      id,
      name,
      x: MAP.spawn.x + (offset % 2),
      y: MAP.spawn.y + Math.floor(offset / 2),
      color: COLORS[this.players.size % COLORS.length],
      state: PLAYER_STATES.ALIVE,
      connected: true,
    });
    return id;
  }

  disconnect(playerId) {
    const player = this.players.get(playerId);
    if (!player) return;
    if (this.phase === MATCH_PHASES.LOBBY) {
      this.players.delete(playerId);
      return;
    }
    player.connected = false;
    if (player.state === PLAYER_STATES.ALIVE) player.state = PLAYER_STATES.ELIMINATED;
    this.checkDefeat();
  }

  reconnect(playerId) {
    const player = this.players.get(playerId);
    if (!player) return false;
    if (player.state === PLAYER_STATES.ALIVE) player.connected = true;
    return true;
  }

  start(playerId) {
    this.requirePlayer(playerId);
    if (this.phase !== MATCH_PHASES.LOBBY) throw new Error("The match is not in the lobby.");
    // A single operative may run the mission solo; teams are supported too.
    if (this.players.size < 1) throw new Error("At least one player is required.");
    this.phase = MATCH_PHASES.STARTING;
    this.startedAt = this.now() + START_COUNTDOWN_MS;
  }

  updatePhase() {
    if (this.phase === MATCH_PHASES.STARTING && this.now() >= this.startedAt) {
      this.phase = MATCH_PHASES.PLAYING;
      return true;
    }
    return false;
  }

  move(playerId, dx, dy) {
    this.updatePhase();
    const player = this.requireLivingPlayer(playerId);
    if (![MATCH_PHASES.PLAYING, MATCH_PHASES.EXIT_UNLOCKED].includes(this.phase)) {
      throw new Error("Movement is unavailable right now.");
    }
    if (!Number.isInteger(dx) || !Number.isInteger(dy) || Math.abs(dx) + Math.abs(dy) !== 1) {
      throw new Error("Invalid movement.");
    }
    const destination = { x: player.x + dx, y: player.y + dy };
    if (!validTile(destination)) return { moved: false };
    player.x = destination.x;
    player.y = destination.y;

    if (
      this.phase === MATCH_PHASES.EXIT_UNLOCKED &&
      player.x === MAP.exit.x &&
      player.y === MAP.exit.y
    ) {
      player.state = PLAYER_STATES.ESCAPED;
      this.phase = MATCH_PHASES.FINISHED;
      this.winner = player.id;
      this.finishReason = "escaped";
    }
    return { moved: true };
  }

  interact(playerId) {
    const player = this.requireLivingPlayer(playerId);
    if (![MATCH_PHASES.PLAYING, MATCH_PHASES.EXIT_UNLOCKED].includes(this.phase)) {
      throw new Error("Nothing can be used right now.");
    }
    const terminal = MAP.terminals.find(
      (candidate) => distance(player, candidate) <= LIMITS.INTERACTION_DISTANCE,
    );
    if (terminal) {
      const topic = TOPICS.find((candidate) => candidate.id === terminal.topicId);
      return {
        kind: "terminal",
        topic: {
          ...publicTopic(topic),
          studied: this.studiedTopics.has(topic.id),
        },
      };
    }
    if (distance(player, MAP.exit) <= LIMITS.INTERACTION_DISTANCE) {
      return {
        kind: "exit",
        unlocked: this.phase === MATCH_PHASES.EXIT_UNLOCKED,
      };
    }
    throw new Error("Move next to a computer or the exit first.");
  }

  studyTopic(playerId, topicId) {
    const player = this.requireLivingPlayer(playerId);
    if (![MATCH_PHASES.PLAYING, MATCH_PHASES.EXIT_UNLOCKED].includes(this.phase)) {
      throw new Error("Stations cannot be reviewed right now.");
    }
    const terminal = MAP.terminals.find((candidate) => candidate.topicId === topicId);
    if (!terminal || distance(player, terminal) > LIMITS.INTERACTION_DISTANCE) {
      throw new Error("Stay beside that computer to review it.");
    }
    const topic = TOPICS.find((candidate) => candidate.id === topicId);
    if (!topic) throw new Error("Unknown station.");
    if (this.studiedTopics.has(topicId)) {
      return { studied: true, alreadyStudied: true };
    }

    this.studiedTopics.add(topicId);
    if (this.studiedTopics.size >= this.requiredTopics && this.phase === MATCH_PHASES.PLAYING) {
      this.phase = MATCH_PHASES.EXIT_UNLOCKED;
    }
    return { studied: true, alreadyStudied: false };
  }

  tickBeast() {
    this.updatePhase();
    if (![MATCH_PHASES.PLAYING, MATCH_PHASES.EXIT_UNLOCKED].includes(this.phase)) return [];
    const living = [...this.players.values()].filter(
      (player) => player.state === PLAYER_STATES.ALIVE && player.connected,
    );
    if (!living.length) {
      this.checkDefeat();
      return [];
    }

    const nearest = living
      .map((player) => ({ player, range: distance(this.beast, player) }))
      .sort((a, b) => a.range - b.range)[0];
    let goal;
    if (nearest.range <= BEAST_DETECTION_DISTANCE) {
      this.beast.mode = "chase";
      this.beast.targetId = nearest.player.id;
      goal = nearest.player;
    } else {
      this.beast.mode = "patrol";
      this.beast.targetId = null;
      goal = MAP.patrol[this.beast.patrolIndex];
      if (pointKey(this.beast) === pointKey(goal)) {
        this.beast.patrolIndex = (this.beast.patrolIndex + 1) % MAP.patrol.length;
        goal = MAP.patrol[this.beast.patrolIndex];
      }
    }

    const step = nextStep(this.beast, goal);
    this.beast.x = step.x;
    this.beast.y = step.y;
    const eliminated = living.filter(
      (player) => player.x === this.beast.x && player.y === this.beast.y,
    );
    for (const player of eliminated) {
      player.state = PLAYER_STATES.ELIMINATED;
    }
    this.checkDefeat();
    return eliminated.map((player) => player.id);
  }

  checkDefeat() {
    if (![MATCH_PHASES.PLAYING, MATCH_PHASES.EXIT_UNLOCKED].includes(this.phase)) return;
    const living = [...this.players.values()].some(
      (player) => player.state === PLAYER_STATES.ALIVE && player.connected,
    );
    if (!living) {
      this.phase = MATCH_PHASES.FINISHED;
      this.finishReason = "eliminated";
    }
  }

  restart(playerId) {
    this.requirePlayer(playerId);
    if (this.phase !== MATCH_PHASES.FINISHED) throw new Error("The match has not finished.");
    const players = [...this.players.values()].filter((player) => player.connected);
    this.players = new Map(players.map((player) => [player.id, player]));
    this.phase = MATCH_PHASES.LOBBY;
    this.studiedTopics.clear();
    this.winner = null;
    this.startedAt = null;
    this.finishReason = null;
    this.beast = {
      ...MAP.beastSpawn,
      mode: "patrol",
      targetId: null,
      patrolIndex: 0,
    };
    players.forEach((player, index) => {
      player.x = MAP.spawn.x + (index % 2);
      player.y = MAP.spawn.y + Math.floor((index % 4) / 2);
      player.state = PLAYER_STATES.ALIVE;
    });
  }

  requirePlayer(playerId) {
    const player = this.players.get(playerId);
    if (!player) throw new Error("Unknown player. Rejoin the lobby.");
    return player;
  }

  requireLivingPlayer(playerId) {
    const player = this.requirePlayer(playerId);
    if (!player.connected || player.state !== PLAYER_STATES.ALIVE) {
      throw new Error("Eliminated players can only spectate.");
    }
    return player;
  }

  publicState(viewerId) {
    const viewer = this.players.get(viewerId);
    return {
      phase: this.phase,
      requiredTopics: this.requiredTopics,
      studiedTopics: [...this.studiedTopics],
      winner: this.winner,
      finishReason: this.finishReason,
      viewerId,
      viewerState: viewer?.state || null,
      map: {
        ...MAP,
        terminals: MAP.terminals.map((terminal) => ({
          ...terminal,
          studied: this.studiedTopics.has(terminal.topicId),
        })),
      },
      players: [...this.players.values()].map((player) => ({ ...player })),
      beast: { ...this.beast },
      topics: TOPICS.map((topic) => ({
        id: topic.id,
        category: topic.category,
        title: topic.title,
        studied: this.studiedTopics.has(topic.id),
      })),
    };
  }
}
