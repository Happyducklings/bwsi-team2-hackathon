export const MATCH_PHASES = Object.freeze({
  LOBBY: "lobby",
  STARTING: "starting",
  PLAYING: "playing",
  EXIT_UNLOCKED: "exit-unlocked",
  FINISHED: "finished",
  RESETTING: "resetting",
});

export const PLAYER_STATES = Object.freeze({
  ALIVE: "alive",
  ELIMINATED: "eliminated",
  ESCAPED: "escaped",
});

export const EVENTS = Object.freeze({
  STATE: "state",
  NOTICE: "notice",
});

export const DIRECTIONS = Object.freeze({
  ArrowUp: { dx: 0, dy: -1 },
  KeyW: { dx: 0, dy: -1 },
  ArrowDown: { dx: 0, dy: 1 },
  KeyS: { dx: 0, dy: 1 },
  ArrowLeft: { dx: -1, dy: 0 },
  KeyA: { dx: -1, dy: 0 },
  ArrowRight: { dx: 1, dy: 0 },
  KeyD: { dx: 1, dy: 0 },
});

export const LIMITS = Object.freeze({
  MAX_NAME_LENGTH: 20,
  INTERACTION_DISTANCE: 1,
});
