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

/**
 * Parse Text Client / Hub / launcher connect strings into bare fields.
 *
 * Accepts:
 *   - Optional `ws://` / `wss://` / `archipelago://` / `http(s)://` prefix
 *   - Optional `slot:password@host:port` (password `None`/`null` → empty)
 *   - Plain `host:port`
 *
 * @returns {{
 *   server: string,
 *   slot: string|null,
 *   password: string|null,
 *   hasUserinfo: boolean,
 *   scheme: string,
 *   room: string,
 * }}
 */
function parseConnectServerString(server) {
  const result = {
    server: "",
    slot: null,
    password: null,
    hasUserinfo: false,
    scheme: "",
    room: "",
  };
  const raw = String(server || "").trim();
  if (!raw) return result;

  const roomMatch = raw.match(/\/room\/([A-Za-z0-9_-]+)/i);
  if (roomMatch) result.room = roomMatch[1];

  let forUrl = raw;
  if (/^archipelago:\/\//i.test(raw)) {
    result.scheme = "archipelago";
    forUrl = raw.replace(/^archipelago:\/\//i, "http://");
  } else if (/^wss:\/\//i.test(raw)) {
    result.scheme = "wss";
  } else if (/^ws:\/\//i.test(raw)) {
    result.scheme = "ws";
  } else if (/^https:\/\//i.test(raw)) {
    result.scheme = "https";
  } else if (/^http:\/\//i.test(raw)) {
    result.scheme = "http";
  } else if (raw.includes("@")) {
    // Text Client paste: slot:password@host:port (no scheme).
    forUrl = `ws://${raw}`;
  } else {
    // Plain host:port (or host) — keep path/query stripped.
    result.server = raw.split("?")[0].split("/")[0];
    return result;
  }

  try {
    const u = new URL(forUrl);
    if (u.hostname) {
      // Prefer host (hostname:port) without userinfo — safe for --connect.
      result.server = u.host;
    }
    const hadUserinfo =
      Boolean(u.username) ||
      Boolean(u.password) ||
      (u.host && raw.includes("@"));
    if (hadUserinfo) {
      result.hasUserinfo = true;
      result.slot = u.username ? decodeURIComponent(u.username) : "";
      result.password = normalizeUriPassword(u.password);
    }
    const room = u.searchParams.get("room");
    if (room) result.room = room;
  } catch (_) {
    // Last resort: strip scheme and take authority before path.
    let fallback = raw
      .replace(/^wss?:\/\//i, "")
      .replace(/^archipelago:\/\//i, "")
      .replace(/^https?:\/\//i, "");
    fallback = fallback.split("?")[0].split("/")[0];
    if (fallback.includes("@")) {
      const at = fallback.lastIndexOf("@");
      const userinfo = fallback.slice(0, at);
      result.server = fallback.slice(at + 1);
      result.hasUserinfo = true;
      const colon = userinfo.indexOf(":");
      if (colon >= 0) {
        try {
          result.slot = decodeURIComponent(userinfo.slice(0, colon));
        } catch (_) {
          result.slot = userinfo.slice(0, colon);
        }
        result.password = normalizeUriPassword(userinfo.slice(colon + 1));
      } else {
        try {
          result.slot = decodeURIComponent(userinfo);
        } catch (_) {
          result.slot = userinfo;
        }
        result.password = "";
      }
    } else {
      result.server = fallback;
    }
  }
  return result;
}

function hostPortFromServer(server) {
  const parsed = parseConnectServerString(server);
  return parsed.server || "";
}

/**
 * Candidate WebSocket URLs (preferred first).
 *
 * Match CommonClient / Text Client: try plain `ws://` on the game port first,
 * then `wss://`. Forcing wss-first for archipelago.gg caused Hub timeouts when
 * TLS failed/hung while Text Client's ws:// path still worked.
 *
 * Always uses bare host:port (userinfo stripped). Explicit ws/wss in the
 * input still prefers that scheme first.
 */
function buildWsCandidates(server) {
  const parsed = parseConnectServerString(server);
  const hostPort = parsed.server;
  if (!hostPort) return [];
  if (parsed.scheme === "wss") {
    return [`wss://${hostPort}`, `ws://${hostPort}`];
  }
  if (parsed.scheme === "ws") {
    return [`ws://${hostPort}`, `wss://${hostPort}`];
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
 * Electron main historically lacked a global WebSocket on older Node;
 * prefer global when present, otherwise use the `ws` package.
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
    ws.on("error", (err) =>
      onError({ message: err && err.message ? err.message : String(err || "error") })
    );
    ws.on("close", (code, reason) =>
      onClose({
        code,
        reason: reason != null ? payloadToText(reason) : "",
      })
    );
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
      attempts: [],
    });
  }

  const candidates = buildWsCandidates(server);
  if (!candidates.length) {
    return Promise.resolve({ ok: false, error: "Server address is empty.", attempts: [] });
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
        finish({ ok: false, url, error: `Timed out waiting for RoomInfo from ${url}` });
      }, timeoutMs);

      try {
        ws = new WS(url);
      } catch (err) {
        finish({
          ok: false,
          url,
          error: String(err && err.message ? err.message : err),
        });
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
        onError: (ev) => {
          const detail =
            (ev && ev.message) ||
            (ev && ev.error && ev.error.message) ||
            (ev && ev.type) ||
            "error";
          finish({ ok: false, url, error: `WebSocket error connecting to ${url}: ${detail}` });
        },
        onClose: (ev) => {
          const code = ev && ev.code != null ? ev.code : "?";
          const reason = (ev && ev.reason) || "";
          finish({
            ok: false,
            url,
            error: `Connection closed before RoomInfo from ${url} (code=${code}${
              reason ? ` reason=${reason}` : ""
            })`,
          });
        },
      });
    });

  return (async () => {
    const attempts = [];
    let last = { ok: false, error: "No WebSocket candidates.", attempts };
    for (const url of candidates) {
      last = await tryOne(url);
      attempts.push({
        url: last.url || url,
        ok: Boolean(last.ok),
        error: last.ok ? "" : last.error || "failed",
      });
      if (last.ok) {
        last.attempts = attempts;
        return last;
      }
    }
    return {
      ok: false,
      error: (last && last.error) || "All WebSocket candidates failed.",
      attempts,
    };
  })();
}

module.exports = {
  normalizeUriPassword,
  parseConnectServerString,
  hostPortFromServer,
  buildWsCandidates,
  decideConnectAfterRoomInfo,
  extractRoomInfo,
  resolveWebSocketImpl,
  probeRoomInfo,
};
