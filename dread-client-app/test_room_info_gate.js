/**
 * Unit tests for RoomInfo password gate (no live network).
 *
 * Run from this directory:
 *   node test_room_info_gate.js
 */

"use strict";

const assert = require("assert");
const {
  normalizeUriPassword,
  hostPortFromServer,
  buildWsCandidates,
  decideConnectAfterRoomInfo,
  extractRoomInfo,
  probeRoomInfo,
} = require("./room_info_gate");

function test(name, fn) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    throw err;
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    throw err;
  }
}

console.log("room_info_gate");

test("normalizeUriPassword maps None/null/empty", () => {
  assert.strictEqual(normalizeUriPassword("None"), "");
  assert.strictEqual(normalizeUriPassword("null"), "");
  assert.strictEqual(normalizeUriPassword(""), "");
  assert.strictEqual(normalizeUriPassword(null), "");
  assert.strictEqual(normalizeUriPassword(undefined), "");
  assert.strictEqual(normalizeUriPassword(" secret "), "secret");
  assert.strictEqual(normalizeUriPassword("sec%20ret"), "sec ret");
});

test("hostPortFromServer strips schemes and paths", () => {
  assert.strictEqual(
    hostPortFromServer("archipelago://orangeonionMD:None@archipelago.gg:34841?game=x"),
    "archipelago.gg:34841"
  );
  assert.strictEqual(hostPortFromServer("wss://archipelago.gg:34841"), "archipelago.gg:34841");
  assert.strictEqual(hostPortFromServer("127.0.0.1:38281"), "127.0.0.1:38281");
});

test("buildWsCandidates prefers wss for archipelago.gg", () => {
  const c = buildWsCandidates("archipelago.gg:34841");
  assert.deepStrictEqual(c, [
    "wss://archipelago.gg:34841",
    "ws://archipelago.gg:34841",
  ]);
  const local = buildWsCandidates("127.0.0.1:38281");
  assert.deepStrictEqual(local, ["ws://127.0.0.1:38281", "wss://127.0.0.1:38281"]);
});

test("decideConnectAfterRoomInfo open room ignores empty URI password", () => {
  const d = decideConnectAfterRoomInfo(false, "None");
  assert.strictEqual(d.action, "connect");
  assert.strictEqual(d.password, "");
});

test("decideConnectAfterRoomInfo passworded room gates without password", () => {
  const d = decideConnectAfterRoomInfo(true, "None");
  assert.strictEqual(d.action, "need_password");
  assert.strictEqual(d.password, "");
});

test("decideConnectAfterRoomInfo passworded room connects with real password", () => {
  const d = decideConnectAfterRoomInfo(true, "hunter");
  assert.strictEqual(d.action, "connect");
  assert.strictEqual(d.password, "hunter");
});

test("extractRoomInfo parses AP message list", () => {
  const payload = JSON.stringify([
    { cmd: "RoomInfo", password: true, seed_name: "SeedA" },
  ]);
  const info = extractRoomInfo(payload);
  assert.ok(info);
  assert.strictEqual(info.password, true);
  assert.strictEqual(info.seed_name, "SeedA");
});

(async () => {
  await testAsync("probeRoomInfo returns RoomInfo.password via mock WebSocket", async () => {
    class MockWS {
      constructor(url) {
        this.url = url;
        this.readyState = 0;
        setImmediate(() => {
          this.readyState = 1;
          if (this.onmessage) {
            this.onmessage({
              data: JSON.stringify([
                { cmd: "RoomInfo", password: true, seed_name: "MockSeed" },
              ]),
            });
          }
        });
      }
      close() {
        this.readyState = 3;
      }
    }

    const result = await probeRoomInfo("127.0.0.1:38281", {
      WebSocketImpl: MockWS,
      timeoutMs: 2000,
    });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.password, true);
    assert.strictEqual(result.seed_name, "MockSeed");

    const decision = decideConnectAfterRoomInfo(result.password, "None");
    assert.strictEqual(decision.action, "need_password");
  });

  await testAsync("probeRoomInfo open room → connect decision", async () => {
    class MockWS {
      constructor() {
        this.readyState = 0;
        setImmediate(() => {
          this.readyState = 1;
          this.onmessage &&
            this.onmessage({
              data: JSON.stringify([{ cmd: "RoomInfo", password: false }]),
            });
        });
      }
      close() {
        this.readyState = 3;
      }
    }
    const result = await probeRoomInfo("archipelago.gg:34841", {
      WebSocketImpl: MockWS,
      timeoutMs: 2000,
    });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.password, false);
    assert.strictEqual(decideConnectAfterRoomInfo(result.password, "").action, "connect");
  });

  console.log("\nAll room_info_gate tests passed.");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
