

"use strict";

function normalizeUriPassword(password) {
  // WebHost uses the text None for empty passwords.
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
    // Accept slot:password@host:port without a URL scheme.
    forUrl = `ws://${raw}`;
  } else {
    // Keep only the host and port from a plain server address.
    result.server = raw.split("?")[0].split("/")[0];
    return result;
  }

  try {
    const u = new URL(forUrl);
    if (u.hostname) {
      // Use host and port without account details for --connect.
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
    // Remove the URL scheme and path as a last resort.
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
  // Use .on for ws; use onmessage for browser WebSockets.
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
          /* Ignore this optional close error. */
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
