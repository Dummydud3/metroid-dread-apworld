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

// World-scan noise (bsdiff4) must not mask pkg_resources hang.
const pkgHang = explainClientExit(
  null,
  "ModuleNotFoundError: No module named 'bsdiff4'\npkg_resources not found, press enter to install it\n"
);
assert.ok(/pkg_resources/i.test(pkgHang), pkgHang);
assert.ok(!/bsdiff4/i.test(pkgHang), pkgHang);

const reqHang = explainClientExit(
  null,
  "Requirement bsdiff4>=1.2.2 is not satisfied, press enter to install it\n"
);
assert.ok(/ModuleUpdate/i.test(reqHang), reqHang);

const urlArg = explainClientExit(
  1,
  "ImportError: cannot import name 'handle_url_arg' from 'CommonClient'\n"
);
assert.ok(/handle_url_arg/i.test(urlArg), urlArg);

// Generic: surface stderr tail.
const generic = explainClientExit(1, "line1\nTraceback...\nImportError: boom");
assert.ok(generic.includes("ImportError: boom"), generic);

console.log("test_client_exit: ok");
