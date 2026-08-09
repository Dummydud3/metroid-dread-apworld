const assert = require("assert");
const {
  explainClientExit,
  formatPythonCmd,
  pythonMissingError,
} = require("./client_exit");

assert.strictEqual(formatPythonCmd({ cmd: "py", prefixArgs: ["-3.11"] }), "py -3.11");
assert.ok(pythonMissingError().includes("3.11–3.13"));

// Python Install Manager: missing runtime (reported user code).
const pymanager = explainClientExit(2684354566, "");
assert.ok(pymanager.includes("0xa0000006"), pymanager);
assert.ok(/py install 3\.12/i.test(pymanager), pymanager);

// Classic Windows py launcher.
const classic = explainClientExit(103, "No suitable Python runtime found\n");
assert.ok(/Python 3\.11/.test(classic), classic);

// stderr wins for import errors; also hints at auto-install / requirements-client.txt.
const missingWs = explainClientExit(
  1,
  "ModuleNotFoundError: No module named 'websockets'"
);
assert.ok(missingWs.includes("websockets"), missingWs);
assert.ok(/requirements-client\.txt/i.test(missingWs), missingWs);

// Generic: surface stderr tail.
const generic = explainClientExit(1, "line1\nTraceback...\nImportError: boom");
assert.ok(generic.includes("ImportError: boom"), generic);

console.log("test_client_exit: ok");
