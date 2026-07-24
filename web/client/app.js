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
  topicCategory: document.querySelector("#topic-category"),
  topicTitle: document.querySelector("#topic-title"),
  topicSummary: document.querySelector("#topic-summary"),
  topicBody: document.querySelector("#topic-body"),
  topicReading: document.querySelector("#topic-reading"),
  studyButton: document.querySelector("#study-button"),
  completeDialog: document.querySelector("#complete-dialog"),
  completeClose: document.querySelector("#complete-close"),
  toast: document.querySelector("#toast"),
};

const context = elements.canvas.getContext("2d");
let playerId = sessionStorage.getItem("beast-player-id");
let state = null;
let events = null;
let activeTopic = null;
let moving = false;
let toastTimer = null;
let completionShown = false;

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
  if (state.phase === "lobby") return "Enter the map alone or with a team";
  if (state.phase === "starting") return "Prepare for deployment";
  if (state.phase === "playing") return "Study stations and avoid the Beast";
  if (state.phase === "exit-unlocked") return "Reach the extraction gate";
  if (state.finishReason === "escaped") return "A survivor escaped — mission complete";
  return "All survivors eliminated — mission failed";
}

function render() {
  if (!state) return;
  const player = currentPlayer();
  elements.phaseChip.textContent = phaseLabel(state.phase);
  elements.objective.textContent = objectiveText();
  elements.progress.textContent =
    `${state.studiedTopics.length} / ${state.requiredTopics}`;
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
      row.className = `terminal-row ${terminal.studied ? "complete" : ""}`;
      const topic = state.topics.find((item) => item.id === terminal.topicId);
      const icon = document.createElement("span");
      icon.textContent = terminal.studied ? "✓" : "◇";
      const title = document.createElement("span");
      title.textContent = topic?.category || terminal.topicId;
      const meta = document.createElement("span");
      meta.className = "row-meta";
      meta.textContent = terminal.studied ? "STUDIED" : "UNREAD";
      row.append(icon, title, meta);
      return row;
    }),
  );

  renderMap();
  renderOverlay();

  if (activeTopic) {
    const latest = state.topics.find((topic) => topic.id === activeTopic.id);
    if (latest?.studied) markTopicStudiedInDialog();
  }

  maybeShowCompletion();
}

function maybeShowCompletion() {
  // Reset the one-shot when a new match returns to the lobby.
  if (state.phase === "lobby") {
    completionShown = false;
    if (elements.completeDialog.open) elements.completeDialog.close();
    return;
  }
  const escaped = state.phase === "finished" && state.finishReason === "escaped";
  if (escaped && !completionShown) {
    completionShown = true;
    if (elements.dialog.open) elements.dialog.close();
    if (!elements.completeDialog.open) elements.completeDialog.showModal();
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
    context.fillStyle = terminal.studied ? "#78f7b3" : "#46e0ff";
    context.fillRect(terminal.x * cell + 5, terminal.y * cell + 7, cell - 10, cell - 14);
    context.fillStyle = "#07101a";
    context.fillRect(terminal.x * cell + 9, terminal.y * cell + 11, cell - 18, cell - 24);
    context.fillStyle = terminal.studied ? "#78f7b3" : "#46e0ff";
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

function markTopicStudiedInDialog() {
  elements.studyButton.disabled = true;
  elements.studyButton.textContent = "REVIEWED ✓";
}

async function interact() {
  try {
    const result = await request("/api/interact", { playerId });
    if (result.kind === "exit") {
      showToast(
        result.unlocked ? "Exit open. Step onto the gate." : "Exit locked. Study more stations.",
      );
      return;
    }
    const topic = result.topic;
    activeTopic = topic;
    elements.topicCategory.textContent = topic.category;
    elements.topicTitle.textContent = topic.title;
    elements.topicSummary.textContent = topic.summary;
    elements.topicBody.replaceChildren(
      ...topic.body.map((paragraph) => {
        const p = document.createElement("p");
        p.textContent = paragraph;
        return p;
      }),
    );
    elements.topicReading.replaceChildren(
      ...topic.reading.map((link) => {
        const item = document.createElement("li");
        const anchor = document.createElement("a");
        anchor.href = link.url;
        anchor.textContent = link.label;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        item.append(anchor);
        return item;
      }),
    );
    elements.studyButton.disabled = false;
    elements.studyButton.textContent = "MARK REVIEWED";
    if (topic.studied) markTopicStudiedInDialog();
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
elements.dialog.addEventListener("close", () => { activeTopic = null; });
elements.completeClose.addEventListener("click", () => elements.completeDialog.close());

elements.studyButton.addEventListener("click", async () => {
  if (!activeTopic) return;
  try {
    await request("/api/study", { playerId, topicId: activeTopic.id });
    markTopicStudiedInDialog();
  } catch (error) {
    showToast(error.message, "danger");
  }
});

window.addEventListener("keydown", (event) => {
  if (elements.dialog.open || elements.completeDialog.open || event.target.matches("input")) return;
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
