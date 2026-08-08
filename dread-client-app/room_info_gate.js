/**
 * Pre-Connect RoomInfo helpers for the Dread Hub.
 *
 * Archipelago sends RoomInfo (with boolean `password`) immediately after the
 * WebSocket opens — before any slot Connect. URI ":None@" means "no password
 * in the link", not "room has no password".
 */

"use strict";

function normalizeUriPassword(password) {
  // WebHost encodes empty passwords as the literal string "None".
  if (password == null) return "";
  let text;
  try {
    text = decodeURIComponent(String(password)).trim();
  } catch (_) {
    text = String(password).trim();
  }
  if (!text || text.toLowerCase() === "none" || text.toLowerCase() === "null") {
    return "";
  }
  return text;
}

function hostPortFromServer(server) {
  let raw = String(server || "").trim();
  if (!raw) return "";
  if (/^archipelago:\/\//i.test(raw) || /^wss?:\/\//i.test(raw) || /^https?:\/\//i.test(raw)) {
    try {
      const u = new URL(raw.replace(/^archipelago:\/\//i, "http://"));
      return u.port ? `${u.hostname}:${u.port}` : u.hostname;
    } catch (_) {
      /* fall through */
    }
  }
  return raw.split("/")[0];
}

/**
 * Candidate WebSocket URLs (preferred first). Mirrors CommonClient's
 * ws→wss retry and Hub's archipelago.gg → wss preference.
 */
function buildWsCandidates(server) {
  const raw = String(server || "").trim();
  if (!raw) return [];
  if (/^wss?:\/\//i.test(raw)) {
    const primary = raw;
    const alt = primary.toLowerCase().startsWith("wss://")
      ? `ws://${primary.slice(6)}`
      : `wss://${primary.slice(5)}`;
    return [primary, alt];
  }
  const hostPort = hostPortFromServer(raw);
  if (!hostPort) return [];
  const lower = hostPort.toLowerCase();
  if (lower.startsWith("archipelago.gg") || lower.includes(".archipelago.gg")) {
    return [`wss://${hostPort}`, `ws://${hostPort}`];
  }
  return [`ws://${hostPort}`, `wss://${hostPort}`];
}

/**
 * @param {boolean} roomPasswordRequired  RoomInfo.password
 * @param {string|null|undefined} password  URI/field password (may be "None")
 * @returns {{ action: "connect"|"need_password", password: string }}
 */
function decideConnectAfterRoomInfo(roomPasswordRequired, password) {
  const normalized = normalizeUriPassword(password);
  if (roomPasswordRequired && !normalized) {
    return { action: "need_password", password: "" };
  }
  return { action: "connect", password: normalized };
}

function extractRoomInfo(payload) {
  let msgs;
  try {
    msgs = typeof payload === "string" ? JSON.parse(payload) : payload;
  } catch (_) {
    return null;
  }
  if (!Array.isArray(msgs)) {
    msgs = [msgs];
  }
  for (const msg of msgs) {
    if (msg && msg.cmd === "RoomInfo") {
      return msg;
    }
  }
  return null;
}

/**
 * Electron main uses Node 20 (no global WebSocket). Prefer global when present
 * (Node 22+ / browsers), else the `ws` package.
 */
function resolveWebSocketImpl(explicit) {
  if (explicit) return explicit;
  if (typeof WebSocket !== "undefined") return WebSocket;
  try {
    const mod = require("ws");
    return mod.WebSocket || mod;
  } catch (_) {
    return null;
  }
}

function payloadToText(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  if (Buffer.isBuffer(data)) return data.toString("utf8");
  if (data instanceof ArrayBuffer) return Buffer.from(data).toString("utf8");
  if (ArrayBuffer.isView(data)) {
    return Buffer.from(data.buffer, data.byteOffset, data.byteLength).toString("utf8");
  }
  return String(data);
}

function attachSocketHandlers(ws, { onMessage, onError, onClose }) {
  // `ws` package: EventEmitter (.on). Browsers / undici: onmessage properties.
  if (typeof ws.on === "function") {
    ws.on("message", (data) => onMessage({ data: payloadToText(data) }));
    ws.on("error", () => onError());
    ws.on("close", () => onClose());
    return;
  }
  ws.onmessage = onMessage;
  ws.onerror = onError;
  ws.onclose = onClose;
}

/**
 * Open a temporary WebSocket, read RoomInfo, close without Connect.
 *
 * @param {string} server  host:port or ws(s) URL
 * @param {{ timeoutMs?: number, WebSocketImpl?: typeof WebSocket }} [opts]
 */
function probeRoomInfo(server, opts = {}) {
  const timeoutMs = opts.timeoutMs != null ? opts.timeoutMs : 8000;
  const WS = resolveWebSocketImpl(opts.WebSocketImpl);
  if (!WS) {
    return Promise.resolve({
      ok: false,
      error:
        "WebSocket is not available (install the Hub `ws` dependency or use Node 22+).",
    });
  }

  const candidates = buildWsCandidates(server);
  if (!candidates.length) {
    return Promise.resolve({ ok: false, error: "Server address is empty." });
  }

  const tryOne = (url) =>
    new Promise((resolve) => {
      let settled = false;
      let ws;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try {
          if (ws && (ws.readyState === undefined || ws.readyState <= 1)) ws.close();
        } catch (_) {
          /* ignore */
        }
        resolve(result);
      };
      const timer = setTimeout(() => {
        finish({ ok: false, error: `Timed out waiting for RoomInfo from ${url}` });
      }, timeoutMs);

      try {
        ws = new WS(url);
      } catch (err) {
        finish({ ok: false, error: String(err && err.message ? err.message : err) });
        return;
      }

      attachSocketHandlers(ws, {
        onMessage: (ev) => {
          const info = extractRoomInfo(ev.data);
          if (!info) return;
          finish({
            ok: true,
            password: Boolean(info.password),
            seed_name: info.seed_name || "",
            url,
          });
        },
        onError: () => {
          finish({ ok: false, error: `WebSocket error connecting to ${url}` });
        },
        onClose: () => {
          finish({ ok: false, error: `Connection closed before RoomInfo from ${url}` });
        },
      });
    });

  return (async () => {
    let last = { ok: false, error: "No WebSocket candidates." };
    for (const url of candidates) {
      last = await tryOne(url);
      if (last.ok) return last;
    }
    return last;
  })();
}

module.exports = {
  normalizeUriPassword,
  hostPortFromServer,
  buildWsCandidates,
  decideConnectAfterRoomInfo,
  extractRoomInfo,
  resolveWebSocketImpl,
  probeRoomInfo,
};
