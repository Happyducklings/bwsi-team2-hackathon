import { DIRECTIONS, MATCH_PHASES } from "/shared/protocol.js";

const elements = {
  joinScreen: document.querySelector("#join-screen"),
  gameScreen: document.querySelector("#game-screen"),
  joinForm: document.querySelector("#join-form"),
  displayName: document.querySelector("#display-name"),
  phaseChip: document.querySelector("#phase-chip"),
  objective: document.querySelector("#objective"),
  progress: document.querySelector("#progress"),
  playerStatus: document.querySelector("#player-status"),
  roster: document.querySelector("#roster"),
  terminalStatus: document.querySelector("#terminal-status"),
  startButton: document.querySelector("#start-button"),
  restartButton: document.querySelector("#restart-button"),
  canvas: document.querySelector("#map"),
  centerMessage: document.querySelector("#center-message"),
  dialog: document.querySelector("#terminal-dialog"),
  dialogClose: document.querySelector(".dialog-close"),
  challengeTitle: document.querySelector("#challenge-title"),
  challengeState: document.querySelector("#challenge-state"),
  sshCommand: document.querySelector("#ssh-command"),
  copySsh: document.querySelector("#copy-ssh"),
  flagForm: document.querySelector("#flag-form"),
  flagInput: document.querySelector("#flag-input"),
  toast: document.querySelector("#toast"),
};

const context = elements.canvas.getContext("2d");
let playerId = sessionStorage.getItem("beast-player-id");
let state = null;
let events = null;
let activeChallenge = null;
let moving = false;
let toastTimer = null;

async function request(path, data = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed.");
  return result;
}

function showToast(message, tone = "info") {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `visible ${tone}`;
  toastTimer = setTimeout(() => {
    elements.toast.className = "";
  }, 2_800);
}

function connect() {
  events?.close();
  events = new EventSource(`/api/events?playerId=${encodeURIComponent(playerId)}`);
  events.addEventListener("state", (event) => {
    state = JSON.parse(event.data);
    showGame();
    render();
  });
  events.addEventListener("notice", (event) => {
    const notice = JSON.parse(event.data);
    showToast(notice.message, notice.tone);
  });
  events.onerror = () => {
    if (events.readyState === EventSource.CLOSED) {
      sessionStorage.removeItem("beast-player-id");
      playerId = null;
      state = null;
      showJoin();
      showToast("Connection expired. Rejoin the lobby.", "danger");
    }
  };
}

function showJoin() {
  elements.joinScreen.classList.remove("hidden");
  elements.gameScreen.classList.add("hidden");
  elements.phaseChip.textContent = "OFFLINE";
}

function showGame() {
  elements.joinScreen.classList.add("hidden");
  elements.gameScreen.classList.remove("hidden");
}

function currentPlayer() {
  return state?.players.find((player) => player.id === playerId);
}

function phaseLabel(phase) {
  return {
    [MATCH_PHASES.LOBBY]: "LOBBY",
    [MATCH_PHASES.STARTING]: "DEPLOYING",
    [MATCH_PHASES.PLAYING]: "INFILTRATION",
    [MATCH_PHASES.EXIT_UNLOCKED]: "EXTRACTION OPEN",
    [MATCH_PHASES.FINISHED]: "MISSION ENDED",
    [MATCH_PHASES.RESETTING]: "RESETTING",
  }[phase] || phase.toUpperCase();
}

function objectiveText() {
  if (state.phase === "lobby") return "Assemble the team and start";
  if (state.phase === "starting") return "Prepare for deployment";
  if (state.phase === "playing") return "Complete CTF nodes and avoid the Beast";
  if (state.phase === "exit-unlocked") return "Reach the extraction gate";
  if (state.finishReason === "escaped") return "A survivor escaped — team victory";
  return "All survivors eliminated — mission failed";
}

function render() {
  if (!state) return;
  const player = currentPlayer();
  elements.phaseChip.textContent = phaseLabel(state.phase);
  elements.objective.textContent = objectiveText();
  elements.progress.textContent =
    `${state.completedChallenges.length} / ${state.requiredChallenges}`;
  elements.playerStatus.textContent = (player?.state || "disconnected").toUpperCase();
  elements.playerStatus.style.color =
    player?.state === "alive" ? "var(--green)" : player?.state === "escaped" ? "var(--cyan)" : "var(--red)";

  elements.startButton.classList.toggle("hidden", state.phase !== "lobby");
  elements.restartButton.classList.toggle("hidden", state.phase !== "finished");

  elements.roster.replaceChildren(
    ...state.players.map((member) => {
      const row = document.createElement("div");
      row.className = "player-row";
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = member.color;
      const name = document.createElement("span");
      name.textContent = member.id === playerId ? `${member.name} (YOU)` : member.name;
      const status = document.createElement("span");
      status.className = "row-meta";
      status.textContent = member.connected ? member.state.toUpperCase() : "OFFLINE";
      row.append(dot, name, status);
      return row;
    }),
  );

  elements.terminalStatus.replaceChildren(
    ...state.map.terminals.map((terminal) => {
      const row = document.createElement("div");
      row.className = `terminal-row ${terminal.completed ? "complete" : terminal.workerName ? "active" : ""}`;
      const challenge = state.challenges.find((item) => item.id === terminal.challengeId);
      const icon = document.createElement("span");
      icon.textContent = terminal.completed ? "✓" : terminal.workerName ? "◉" : "◇";
      const title = document.createElement("span");
      title.textContent = challenge?.title || terminal.challengeId;
      const meta = document.createElement("span");
      meta.className = "row-meta";
      meta.textContent = terminal.completed ? "DONE" : terminal.workerName || "IDLE";
      row.append(icon, title, meta);
      return row;
    }),
  );

  renderMap();
  renderOverlay();

  if (activeChallenge) {
    const latest = state.challenges.find((challenge) => challenge.id === activeChallenge.id);
    if (latest?.completed) {
      elements.challengeState.textContent = "Challenge completed by the team.";
      elements.flagInput.disabled = true;
    }
  }
}

function renderMap() {
  const { map } = state;
  const cell = elements.canvas.width / map.width;
  context.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
  context.fillStyle = "#070b13";
  context.fillRect(0, 0, elements.canvas.width, elements.canvas.height);

  context.strokeStyle = "rgba(68, 91, 120, .18)";
  context.lineWidth = 1;
  for (let x = 0; x <= map.width; x += 1) {
    context.beginPath();
    context.moveTo(x * cell, 0);
    context.lineTo(x * cell, map.height * cell);
    context.stroke();
  }
  for (let y = 0; y <= map.height; y += 1) {
    context.beginPath();
    context.moveTo(0, y * cell);
    context.lineTo(map.width * cell, y * cell);
    context.stroke();
  }

  for (const wall of map.walls) {
    context.fillStyle = "#202b3c";
    context.fillRect(wall.x * cell, wall.y * cell, wall.w * cell, wall.h * cell);
    context.strokeStyle = "#344761";
    context.strokeRect(wall.x * cell + 1, wall.y * cell + 1, wall.w * cell - 2, wall.h * cell - 2);
  }

  const exitOpen = state.phase === "exit-unlocked";
  context.fillStyle = exitOpen ? "#78f7b3" : "#ff526d";
  context.fillRect(map.exit.x * cell + 7, map.exit.y * cell + 4, cell - 14, cell - 8);
  context.fillStyle = "#081019";
  context.font = "bold 18px monospace";
  context.textAlign = "center";
  context.fillText("E", (map.exit.x + 0.5) * cell, (map.exit.y + 0.68) * cell);

  for (const terminal of map.terminals) {
    context.fillStyle = terminal.completed ? "#78f7b3" : terminal.workerName ? "#ffd166" : "#46e0ff";
    context.fillRect(terminal.x * cell + 5, terminal.y * cell + 7, cell - 10, cell - 14);
    context.fillStyle = "#07101a";
    context.fillRect(terminal.x * cell + 9, terminal.y * cell + 11, cell - 18, cell - 24);
    context.fillStyle = terminal.completed ? "#78f7b3" : "#46e0ff";
    context.fillRect(terminal.x * cell + 10, terminal.y * cell + cell - 9, cell - 20, 3);
  }

  if (state.phase !== "lobby" && state.phase !== "starting") {
    const beastX = (state.beast.x + 0.5) * cell;
    const beastY = (state.beast.y + 0.5) * cell;
    context.save();
    context.shadowColor = "#ff264e";
    context.shadowBlur = 18;
    context.fillStyle = "#ff264e";
    context.beginPath();
    context.moveTo(beastX, beastY - 15);
    context.lineTo(beastX + 14, beastY + 12);
    context.lineTo(beastX - 14, beastY + 12);
    context.closePath();
    context.fill();
    context.restore();
  }

  for (const player of state.players) {
    if (player.state !== "alive") continue;
    context.fillStyle = player.color;
    context.beginPath();
    context.arc((player.x + 0.5) * cell, (player.y + 0.5) * cell, player.id === playerId ? 12 : 9, 0, Math.PI * 2);
    context.fill();
    if (player.id === playerId) {
      context.strokeStyle = "#ffffff";
      context.lineWidth = 2;
      context.stroke();
    }
    context.fillStyle = "#dbefff";
    context.font = "11px monospace";
    context.textAlign = "center";
    context.fillText(player.name, (player.x + 0.5) * cell, (player.y + 0.5) * cell - 16);
  }
}

function renderOverlay() {
  let message = "";
  if (state.phase === "lobby") message = "LOBBY OPEN\nStart when your team is ready";
  if (state.phase === "starting") message = "DEPLOYING...";
  if (state.viewerState === "eliminated" && state.phase !== "finished") {
    message = "YOU WERE ELIMINATED\nSpectating surviving teammates";
  }
  if (state.phase === "finished") {
    message =
      state.finishReason === "escaped"
        ? "MISSION COMPLETE\nA survivor reached extraction"
        : "MISSION FAILED\nNo survivors remain";
  }
  elements.centerMessage.textContent = message;
  elements.centerMessage.classList.toggle("hidden", !message);
}

async function interact() {
  try {
    const result = await request("/api/interact", { playerId });
    if (result.kind === "exit") {
      showToast(result.unlocked ? "Exit open. Step onto the gate." : "Exit locked. Complete more CTFs.");
      return;
    }
    activeChallenge = result.challenge;
    elements.challengeTitle.textContent = result.challenge.title;
    elements.challengeState.textContent = result.challenge.completed
      ? "Challenge completed by the team."
      : "Open a local terminal, connect over SSH, and recover the flag.";
    elements.sshCommand.textContent = result.challenge.ssh;
    elements.flagInput.value = "";
    elements.flagInput.disabled = result.challenge.completed;
    elements.dialog.showModal();
  } catch (error) {
    showToast(error.message, "danger");
  }
}

async function move(direction) {
  if (moving || !state || currentPlayer()?.state !== "alive") return;
  moving = true;
  try {
    await request("/api/move", { playerId, ...direction });
  } catch (error) {
    showToast(error.message, "danger");
  } finally {
    setTimeout(() => { moving = false; }, 60);
  }
}

elements.joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await request("/api/join", { name: elements.displayName.value });
    playerId = result.playerId;
    state = result.state;
    sessionStorage.setItem("beast-player-id", playerId);
    showGame();
    render();
    connect();
  } catch (error) {
    showToast(error.message, "danger");
  }
});

elements.startButton.addEventListener("click", async () => {
  try {
    await request("/api/start", { playerId });
  } catch (error) {
    showToast(error.message, "danger");
  }
});

elements.restartButton.addEventListener("click", async () => {
  try {
    await request("/api/restart", { playerId });
  } catch (error) {
    showToast(error.message, "danger");
  }
});

elements.dialogClose.addEventListener("click", () => elements.dialog.close());
elements.dialog.addEventListener("close", () => { activeChallenge = null; });

elements.copySsh.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(elements.sshCommand.textContent);
    showToast("SSH command copied.", "success");
  } catch {
    showToast("Copy unavailable. Select the command manually.", "danger");
  }
});

elements.flagForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeChallenge) return;
  try {
    const result = await request("/api/flag", {
      playerId,
      challengeId: activeChallenge.id,
      flag: elements.flagInput.value,
    });
    if (result.correct) {
      elements.challengeState.textContent = "Challenge completed by the team.";
      elements.flagInput.disabled = true;
    } else {
      elements.flagInput.select();
    }
  } catch (error) {
    showToast(error.message, "danger");
  }
});

window.addEventListener("keydown", (event) => {
  if (elements.dialog.open || event.target.matches("input")) return;
  if (DIRECTIONS[event.code]) {
    event.preventDefault();
    move(DIRECTIONS[event.code]);
  } else if (event.code === "KeyE") {
    event.preventDefault();
    interact();
  }
});

if (playerId) connect();
else showJoin();
