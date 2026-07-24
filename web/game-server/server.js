import { createReadStream, existsSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { Game } from "./game.js";
import { EVENTS } from "../shared/protocol.js";

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || "0.0.0.0";
const CLIENT_DIR = fileURLToPath(new URL("../client/", import.meta.url));
const game = new Game();
const streams = new Map();
const disconnectTimers = new Map();

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
};

function json(response, status, value) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(value));
}

async function body(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 16_384) throw new Error("Request body is too large.");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new Error("Request body must be valid JSON.");
  }
}

function sendEvent(response, event, value) {
  response.write(`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`);
}

function broadcast() {
  for (const [playerId, response] of streams) {
    sendEvent(response, EVENTS.STATE, game.publicState(playerId));
  }
}

function notice(playerId, message, tone = "info") {
  const response = streams.get(playerId);
  if (response) sendEvent(response, EVENTS.NOTICE, { message, tone });
}

function openEvents(request, response, url) {
  const playerId = url.searchParams.get("playerId");
  if (!playerId || !game.reconnect(playerId)) {
    json(response, 404, { error: "Unknown player." });
    return;
  }
  clearTimeout(disconnectTimers.get(playerId));
  streams.get(playerId)?.end();
  response.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    connection: "keep-alive",
  });
  response.write("retry: 1500\n\n");
  streams.set(playerId, response);
  sendEvent(response, EVENTS.STATE, game.publicState(playerId));

  request.on("close", () => {
    if (streams.get(playerId) !== response) return;
    streams.delete(playerId);
    const timer = setTimeout(() => {
      game.disconnect(playerId);
      disconnectTimers.delete(playerId);
      broadcast();
    }, 5_000);
    disconnectTimers.set(playerId, timer);
  });
}

async function api(request, response, url) {
  if (request.method === "GET" && url.pathname === "/api/events") {
    openEvents(request, response, url);
    return;
  }
  if (request.method !== "POST") {
    json(response, 405, { error: "Method not allowed." });
    return;
  }

  const data = await body(request);
  let result = {};
  switch (url.pathname) {
    case "/api/join": {
      const playerId = game.join(data.name);
      result = { playerId, state: game.publicState(playerId) };
      break;
    }
    case "/api/start":
      game.start(data.playerId);
      result = { ok: true };
      break;
    case "/api/move":
      result = game.move(data.playerId, data.dx, data.dy);
      break;
    case "/api/interact":
      result = game.interact(data.playerId);
      break;
    case "/api/study": {
      result = game.studyTopic(data.playerId, data.topicId);
      notice(
        data.playerId,
        result.alreadyStudied
          ? "Station already reviewed by the team."
          : "Station reviewed! Team progress updated.",
        "success",
      );
      break;
    }
    case "/api/restart":
      game.restart(data.playerId);
      result = { ok: true };
      break;
    default:
      json(response, 404, { error: "Unknown endpoint." });
      return;
  }
  json(response, 200, result);
  broadcast();
}

function staticFile(response, url) {
  const sharedRequest = url.pathname.startsWith("/shared/");
  const root = sharedRequest ? fileURLToPath(new URL("../shared/", import.meta.url)) : CLIENT_DIR;
  const requested =
    url.pathname === "/"
      ? "index.html"
      : sharedRequest
        ? url.pathname.slice("/shared/".length)
        : url.pathname.slice(1);
  const safePath = normalize(requested).replace(/^(\.\.(\/|\\|$))+/, "");
  const filePath = join(root, safePath);
  if (!filePath.startsWith(root) || !existsSync(filePath)) {
    json(response, 404, { error: "Not found." });
    return;
  }
  response.writeHead(200, {
    "content-type": MIME_TYPES[extname(filePath)] || "application/octet-stream",
    "cache-control": "no-cache",
  });
  createReadStream(filePath).pipe(response);
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);
  try {
    if (url.pathname.startsWith("/api/")) await api(request, response, url);
    else staticFile(response, url);
  } catch (error) {
    json(response, 400, { error: error.message || "Request failed." });
  }
});

const beastTimer = setInterval(() => {
  const phaseChanged = game.updatePhase();
  const eliminated = game.tickBeast();
  if (phaseChanged || eliminated.length) broadcast();
  else if (["playing", "exit-unlocked"].includes(game.phase)) broadcast();
}, 700);

const heartbeat = setInterval(() => {
  for (const response of streams.values()) response.write(": heartbeat\n\n");
}, 15_000);

server.listen(PORT, HOST, () => {
  console.log(`Beast CTF is running at http://localhost:${PORT}`);
});

function shutdown() {
  clearInterval(beastTimer);
  clearInterval(heartbeat);
  for (const timer of disconnectTimers.values()) clearTimeout(timer);
  server.close();
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
