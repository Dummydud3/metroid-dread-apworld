/**
 * Decode Hub child-process exits (MetroidBreadClient / patcher) into UI text.
 */

function formatPythonCmd(launcher) {
  if (!launcher) return "(none)";
  return [launcher.cmd, ...(launcher.prefixArgs || [])].filter(Boolean).join(" ");
}

/** User-facing help when Hub cannot find a system Python 3.11–3.13. */
function pythonMissingError() {
  return (
    "No usable Python 3.11–3.13 found for the Hub client.\n" +
    "Archipelago Text Client uses its own bundled Python — Hub needs a system install.\n\n" +
    "Fix:\n" +
    "  1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/\n" +
    "     (check \"Add python.exe to PATH\")\n" +
    "  2. Or with the new Python install manager:  py install 3.12\n" +
    "  3. Confirm with:  py -0\n" +
    "  4. Restart the Hub and Connect again."
  );
}

/**
 * Explain a non-zero client exit. Maps Windows py-launcher codes and surfaces
 * the last stderr lines so users see a real error, not only a bare number.
 */
function explainClientExit(code, stderrBuf) {
  const blob = String(stderrBuf || "");
  const unsigned = code == null ? null : code >>> 0;

  if (/No module named 'CommonClient'/i.test(blob)) {
    return "Python could not import CommonClient (wrong Archipelago root).";
  }
  if (/partially initialized module 'Options'/i.test(blob)) {
    return "Options.py import clash — Archipelago root / PYTHONPATH is wrong.";
  }
  // ModuleUpdate interactive hang under Hub (no stdin) — not a random world import.
  if (/pkg_resources not found/i.test(blob)) {
    return (
      "Client blocked on missing pkg_resources (setuptools).\n" +
      "Hub should auto-install setuptools into the MetroidBread venv on Connect.\n" +
      "Update the Hub/apworld, then Connect again (or: pip install \"setuptools>=75,<81\")."
    );
  }
  if (/Requirement .+ is not satisfied,\s*press enter/i.test(blob)) {
    return (
      "Client blocked on Archipelago ModuleUpdate (full requirements.txt check).\n" +
      "Hub should skip that under --electron; update the Hub/apworld and Connect again.\n" +
      "Do not install every AP world dependency into the MetroidBread venv."
    );
  }
  if (/cannot import name 'handle_url_arg'/i.test(blob)) {
    return (
      "Archipelago CommonClient is too old (missing handle_url_arg).\n" +
      "Hub should import from bundled ap_core — update the Hub/apworld and Connect again."
    );
  }

  // Prefer client-critical missing modules; ignore AP world-scan noise (bsdiff4, etc.).
  const worldScanNoise = new Set([
    "bsdiff4",
    "zilliandomizer",
    "pyevermizer",
    "maseya",
    "ORAS",
  ]);
  const allMods = [
    ...blob.matchAll(/ModuleNotFoundError: No module named '([^']+)'/gi),
  ].map((m) => m[1]);
  const critical = allMods.find((name) => !worldScanNoise.has(name));
  if (critical) {
    return (
      `Missing Python module: ${critical}\n` +
      "Hub normally auto-installs client packages (websockets, etc.) on Connect.\n" +
      "Try Connect again, or run:\n" +
      "  py -3.12 -m pip install -r requirements-client.txt\n" +
      "(from the metroid_bread world folder / _metroid_bread_runtime)"
    );
  }

  // Classic py.exe → 103; Python Install Manager (pymanager) → 0xA0000006.
  const pyMissing =
    unsigned === 0xa0000006 ||
    unsigned === 103 ||
    /No suitable Python runtime found/i.test(blob) ||
    /No runtime installed that matches/i.test(blob) ||
    /Requested Python version .* is not installed/i.test(blob);
  if (pyMissing) {
    return (
      "Windows py launcher could not start Python 3.11–3.13 " +
      `(exit code ${code}${unsigned != null ? ` / 0x${unsigned.toString(16)}` : ""}).\n` +
      "Install Python 3.12 from python.org (add to PATH), or run: py install 3.12"
    );
  }

  const tail = blob
    .trim()
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter(Boolean)
    .slice(-8)
    .join("\n");
  if (tail) {
    return `Client exited (code ${code}).\n${tail}`;
  }
  return code ? `Client exited (code ${code})` : "";
}

module.exports = {
  formatPythonCmd,
  pythonMissingError,
  explainClientExit,
};
