#!/usr/bin/env python3
"""
Hub Setup Wizard — local HTML UI when Hub cannot start.

Serves a tiny stdlib HTTP page on 127.0.0.1 and opens the default browser.
No tkinter / Tcl-Tk. Users can install managed Node 24 / Python 3.12, repair
Electron, launch Hub, or escape to Kivy.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("MetroidBread.HubSetupWizard")

LogFn = Callable[[str], None]

# Avoid re-spawning node/python probes on every browser poll (~2×/sec).
_CHECKLIST_CACHE_TTL_S = 2.0
_checklist_cache_mono: float = 0.0
_checklist_cache_rows: Optional[List[Tuple[str, bool, str]]] = None
_checklist_cache_lock = threading.Lock()


def invalidate_checklist_cache() -> None:
    global _checklist_cache_mono, _checklist_cache_rows
    with _checklist_cache_lock:
        _checklist_cache_mono = 0.0
        _checklist_cache_rows = None


def collect_checklist(*, force: bool = False) -> List[Tuple[str, bool, str]]:
    """
    Return checklist rows: (label, ok, detail).

    Uses hub_launcher / ensure_client_deps helpers (no network).
    Results are cached briefly so status polling does not flash consoles.
    """
    global _checklist_cache_mono, _checklist_cache_rows
    now = time.monotonic()
    with _checklist_cache_lock:
        if (
            not force
            and _checklist_cache_rows is not None
            and (now - _checklist_cache_mono) < _CHECKLIST_CACHE_TTL_S
        ):
            return list(_checklist_cache_rows)

    rows = _collect_checklist_uncached()
    with _checklist_cache_lock:
        _checklist_cache_mono = time.monotonic()
        _checklist_cache_rows = list(rows)
    return rows


def _collect_checklist_uncached() -> List[Tuple[str, bool, str]]:
    """Build checklist without using the short-lived cache."""
    try:
        from hub_launcher import (
            electron_is_healthy,
            find_hub_dir,
            find_node,
            find_npm,
            node_major_usable,
            node_major_version,
        )
    except ImportError:
        from worlds.metroid_bread.hub_launcher import (
            electron_is_healthy,
            find_hub_dir,
            find_node,
            find_npm,
            node_major_usable,
            node_major_version,
        )

    rows: List[Tuple[str, bool, str]] = []

    node = find_node()
    major = node_major_version(node) if node else None
    if node and node_major_usable(major):
        rows.append(("Node.js", True, f"{node} (v{major})"))
    elif node and major is not None and major < 18:
        rows.append(
            (
                "Node.js",
                False,
                f"{node} is v{major} (need ≥18; Install Node 24)",
            )
        )
    elif node:
        rows.append(("Node.js", False, f"{node} (version unknown)"))
    else:
        rows.append(("Node.js", False, "not found — Install Node 24"))

    npm = find_npm()
    if npm:
        rows.append(("npm", True, npm))
    else:
        rows.append(("npm", False, "not found (comes with Node)"))

    hub = find_hub_dir()
    if hub and (hub / "package.json").is_file() and (hub / "main.js").is_file():
        rows.append(("Hub app", True, str(hub)))
    elif hub:
        rows.append(("Hub app", False, f"incomplete at {hub}"))
    else:
        rows.append(
            (
                "Hub app",
                False,
                "dread-client-app missing — reinstall/update metroid_bread.apworld",
            )
        )

    if hub and electron_is_healthy(hub):
        rows.append(("Electron", True, "healthy path.txt / binary"))
    elif hub:
        rows.append(("Electron", False, "needs npm install / repair"))
    else:
        rows.append(("Electron", False, "Hub app missing"))

    py_ok, py_detail = _client_python_status()
    rows.append(("Client Python", py_ok, py_detail))
    return rows


_WIZARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Metroid Bread — Hub Setup</title>
<style>
  :root {
    --bg: #1a1b1e;
    --panel: #25262b;
    --text: #e8e8ea;
    --muted: #9a9aa3;
    --ok: #3d9a5f;
    --bad: #d64545;
    --accent: #4a8fd4;
    --danger: #c62828;
    --border: #3a3b42;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.45;
  }
  header {
    display: flex; justify-content: space-between; gap: 1rem;
    align-items: flex-start; padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border); background: var(--panel);
  }
  h1 { margin: 0; font-size: 1.25rem; font-weight: 650; }
  .reason { margin: 0.4rem 0 0; color: var(--muted); font-size: 0.92rem; max-width: 42rem; }
  main { padding: 1.25rem 1.5rem 2rem; max-width: 52rem; margin: 0 auto; }
  section {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem 1.1rem; margin-bottom: 1rem;
  }
  section h2 { margin: 0 0 0.75rem; font-size: 0.85rem; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--muted); font-weight: 600; }
  .row { display: flex; gap: 0.6rem; align-items: baseline; padding: 0.35rem 0;
    border-bottom: 1px solid #2e2f35; }
  .row:last-child { border-bottom: none; }
  .mark { font-weight: 700; font-size: 0.75rem; min-width: 4.2rem; }
  .mark.ok { color: var(--ok); }
  .mark.bad { color: var(--bad); }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.85rem; }
  button {
    font: inherit; cursor: pointer; border-radius: 6px; border: 1px solid var(--border);
    background: #33343a; color: var(--text); padding: 0.45rem 0.85rem;
  }
  button:hover:not(:disabled) { background: #3d3e46; }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.primary { background: var(--accent); border-color: #3a7ab8; color: #fff; }
  button.primary:hover:not(:disabled) { filter: brightness(1.08); }
  button.danger { background: var(--danger); border-color: #a01f1f; color: #fff; }
  #log {
    font-family: ui-monospace, Consolas, monospace; font-size: 0.8rem;
    white-space: pre-wrap; word-break: break-word; max-height: 16rem;
    overflow: auto; background: #121316; border-radius: 6px; padding: 0.75rem;
    color: #c8c8ce; min-height: 6rem;
  }
  footer { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem; }
  .busy { color: var(--muted); font-size: 0.85rem; margin-left: 0.5rem; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Metroid Bread Client Hub Setup</h1>
    <p class="reason" id="reason"></p>
  </div>
  <button type="button" class="danger" id="btn-kivy">Just open Kivy version</button>
</header>
<main>
  <section>
    <h2>Checklist</h2>
    <div id="checklist"></div>
    <div class="actions">
      <button type="button" data-action="install_node">Install Node 24</button>
      <button type="button" data-action="install_python">Install Python 3.12</button>
      <button type="button" data-action="fix_electron">Fix / refresh Electron</button>
      <button type="button" data-action="check_updates">Check for updates</button>
      <button type="button" data-action="refresh">Refresh</button>
      <span class="busy" id="busy" hidden>Working…</span>
    </div>
  </section>
  <section>
    <h2>Log</h2>
    <div id="log"></div>
  </section>
  <footer>
    <button type="button" class="primary" id="btn-launch" disabled>Launch Hub</button>
  </footer>
</main>
<script>
(function () {
  const checklist = document.getElementById("checklist");
  const logEl = document.getElementById("log");
  const reasonEl = document.getElementById("reason");
  const busyEl = document.getElementById("busy");
  const launchBtn = document.getElementById("btn-launch");
  let lastLog = "";

  function render(status) {
    reasonEl.textContent = status.reason || "";
    checklist.innerHTML = "";
    (status.rows || []).forEach(function (row) {
      const div = document.createElement("div");
      div.className = "row";
      const mark = document.createElement("span");
      mark.className = "mark " + (row.ok ? "ok" : "bad");
      mark.textContent = row.ok ? "[OK]" : "[MISSING]";
      const detail = document.createElement("span");
      detail.textContent = row.name + ": " + row.detail;
      div.appendChild(mark);
      div.appendChild(detail);
      checklist.appendChild(div);
    });
    if (status.log_tail !== lastLog) {
      lastLog = status.log_tail || "";
      logEl.textContent = lastLog;
      logEl.scrollTop = logEl.scrollHeight;
    }
    const busy = !!status.busy;
    busyEl.hidden = !busy;
    document.querySelectorAll("[data-action], #btn-kivy, #btn-launch").forEach(function (btn) {
      if (btn.id === "btn-launch") {
        btn.disabled = busy || !status.can_launch;
      } else if (btn.id === "btn-kivy") {
        btn.disabled = busy;
      } else {
        btn.disabled = busy;
      }
    });
    if (status.done) {
      closeWizard(status.choice === "hub" ? "Hub launched." : "Opening Kivy client.");
      return;
    }
  }

  function closeWizard(message) {
    try { window.close(); } catch (e) {}
    setTimeout(function () {
      try { window.open("", "_self"); window.close(); } catch (e2) {}
      if (!window.closed) {
        document.body.innerHTML =
          "<main style='font-family:Segoe UI,sans-serif;padding:2rem;text-align:center'>" +
          "<p>" + (message || "Done.") + "</p>" +
          "<p style='color:#888'>You can close this tab.</p></main>";
      }
    }, 200);
  }

  let statusBusy = false;

  async function poll() {
    try {
      const r = await fetch("/api/status");
      if (!r.ok) return;
      const status = await r.json();
      statusBusy = !!status.busy;
      render(status);
      if (status.done) return;
    } catch (e) { /* server shutting down — try close anyway */ }
    setTimeout(poll, statusBusy ? 800 : 1500);
  }

  async function postAction(action) {
    try {
      const r = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action }),
      });
      if (!r.ok) return;
      const body = await r.json();
      if (body.done) {
        closeWizard(
          body.choice === "hub" ? "Hub launched." : "Opening Kivy client."
        );
        return;
      }
      if (action === "launch_hub" || action === "kivy") {
        for (let i = 0; i < 90; i++) {
          await new Promise(function (res) { setTimeout(res, 200); });
          try {
            const s = await (await fetch("/api/status")).json();
            statusBusy = !!s.busy;
            render(s);
            if (s.done) {
              closeWizard(
                s.choice === "hub" ? "Hub launched." : "Opening Kivy client."
              );
              return;
            }
          } catch (e) {
            closeWizard("Done.");
            return;
          }
        }
      }
    } catch (e) {
      console.error(e);
    }
  }

  document.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      postAction(btn.getAttribute("data-action"));
    });
  });
  document.getElementById("btn-kivy").addEventListener("click", function () {
    postAction("kivy");
  });
  launchBtn.addEventListener("click", function () {
    postAction("launch_hub");
  });

  poll();
})();
</script>
</body>
</html>
"""


def _client_python_status() -> Tuple[bool, str]:
    try:
        try:
            from ensure_client_deps import (
                describe_missing_client_python,
                find_client_python,
                format_cmd,
            )
        except ImportError:
            from worlds.metroid_bread.ensure_client_deps import (
                describe_missing_client_python,
                find_client_python,
                format_cmd,
            )
        cmd = find_client_python()
        if cmd:
            return True, format_cmd(cmd)
        return False, describe_missing_client_python()
    except Exception as exc:
        return False, f"check failed: {exc}"


def hub_ready_for_launch(rows: Optional[List[Tuple[str, bool, str]]] = None) -> bool:
    """Node + npm + Hub + Electron green (Python can finish after Hub opens)."""
    rows = rows if rows is not None else collect_checklist()
    by_name = {name: ok for name, ok, _ in rows}
    return all(by_name.get(k) for k in ("Node.js", "npm", "Hub app", "Electron"))


class _WizardState:
    """Shared mutable state for the HTTP wizard session."""

    def __init__(self, reason: str, args: Sequence[str]) -> None:
        self.reason = (reason or "Hub prerequisites are missing or launch failed.").strip()
        self.args = list(args)
        self.lock = threading.Lock()
        self.log_lines: List[str] = []
        self.busy = False
        self.choice: Optional[str] = None
        self.done_event = threading.Event()

    def append_log(self, msg: str) -> None:
        line = (msg or "").rstrip()
        if not line:
            return
        with self.lock:
            self.log_lines.append(line)
            # Cap log size for status payload.
            if len(self.log_lines) > 400:
                self.log_lines = self.log_lines[-300:]

    def log_tail(self) -> str:
        with self.lock:
            return "\n".join(self.log_lines)

    def set_busy(self, flag: bool) -> None:
        with self.lock:
            self.busy = flag

    def is_busy(self) -> bool:
        with self.lock:
            return self.busy

    def finish(self, choice: str) -> None:
        with self.lock:
            if self.choice is not None:
                return
            self.choice = choice
            self.busy = False
        self.done_event.set()

    def status_dict(self) -> Dict[str, Any]:
        rows = collect_checklist()
        with self.lock:
            busy = self.busy
            choice = self.choice
            log_tail = "\n".join(self.log_lines)
        return {
            "reason": self.reason,
            "rows": [{"name": n, "ok": ok, "detail": d} for n, ok, d in rows],
            "busy": busy,
            "log_tail": log_tail,
            "can_launch": (not busy) and hub_ready_for_launch(rows),
            "done": choice is not None,
            "choice": choice,
        }


def _import_hub_helpers():
    try:
        from hub_launcher import (
            ensure_hub_packages,
            ensure_portable_node24,
            ensure_portable_python312,
            ensure_system_client_python_deps,
            find_hub_dir,
            find_world_dir_for_hub,
            hub_env_from_connect,
            launch_hub_with_repair,
            parse_launcher_connect_args,
            show_user_error,
            show_user_notice,
        )
    except ImportError:
        from worlds.metroid_bread.hub_launcher import (
            ensure_hub_packages,
            ensure_portable_node24,
            ensure_portable_python312,
            ensure_system_client_python_deps,
            find_hub_dir,
            find_world_dir_for_hub,
            hub_env_from_connect,
            launch_hub_with_repair,
            parse_launcher_connect_args,
            show_user_error,
            show_user_notice,
        )
    return {
        "ensure_hub_packages": ensure_hub_packages,
        "ensure_portable_node24": ensure_portable_node24,
        "ensure_portable_python312": ensure_portable_python312,
        "ensure_system_client_python_deps": ensure_system_client_python_deps,
        "find_hub_dir": find_hub_dir,
        "find_world_dir_for_hub": find_world_dir_for_hub,
        "hub_env_from_connect": hub_env_from_connect,
        "launch_hub_with_repair": launch_hub_with_repair,
        "parse_launcher_connect_args": parse_launcher_connect_args,
        "show_user_error": show_user_error,
        "show_user_notice": show_user_notice,
    }


def _make_handler(state: _WizardState, helpers: Dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            logger.debug("wizard http: " + fmt, *args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: Any) -> None:
            data = json.dumps(payload).encode("utf-8")
            self._send(code, data, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(
                    200,
                    _WIZARD_HTML.encode("utf-8"),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/api/status":
                self._json(200, state.status_dict())
                return
            if path == "/api/log":
                self._json(200, {"log": state.log_tail()})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/action":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid json"})
                return
            action = str((body or {}).get("action") or "").strip()
            if not action:
                self._json(400, {"error": "missing action"})
                return
            ok, err, extra = _dispatch_action(state, helpers, action)
            if not ok:
                self._json(409 if err == "busy" else 400, {"error": err or "failed"})
                return
            payload = {"ok": True, "action": action}
            if extra:
                payload.update(extra)
            self._json(200, payload)

    return Handler


def _dispatch_action(
    state: _WizardState,
    helpers: Dict[str, Any],
    action: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    if state.choice is not None:
        return False, "done", {}

    if action == "kivy":
        state.append_log("Opening Kivy client…")
        state.finish("python")
        return True, "", {"done": True, "choice": "python"}

    if action == "refresh":
        invalidate_checklist_cache()
        state.append_log("Refreshing checklist…")
        return True, "", {}

    if state.is_busy() and action != "refresh":
        return False, "busy", {}

    if action == "install_node":

        def work() -> None:
            state.append_log("Installing portable Node 24…")
            ok, msg = helpers["ensure_portable_node24"](log=state.append_log)
            state.append_log(msg if ok else f"FAILED: {msg}")

        _run_bg(state, work)
        return True, "", {}

    if action == "install_python":

        def work() -> None:
            state.append_log("Installing portable Python 3.12…")
            ok, msg = helpers["ensure_portable_python312"](log=state.append_log)
            state.append_log(msg if ok else f"FAILED: {msg}")
            if ok:
                hub = helpers["find_hub_dir"]()
                world = helpers["find_world_dir_for_hub"](hub) if hub else None
                try:
                    state.append_log("Ensuring client Python packages…")
                    helpers["ensure_system_client_python_deps"](world)
                    state.append_log("Client Python packages OK.")
                except RuntimeError as dep_exc:
                    state.append_log(f"Client deps warning:\n{dep_exc}")

        _run_bg(state, work)
        return True, "", {}

    if action == "fix_electron":

        def work() -> None:
            hub = helpers["find_hub_dir"]()
            if not hub:
                state.append_log("Hub app not found; cannot repair Electron.")
                return
            state.append_log(f"Repairing Hub npm / Electron at {hub} …")
            helpers["ensure_hub_packages"](hub, force_reinstall_electron=True)
            state.append_log("Electron repair finished.")

        _run_bg(state, work)
        return True, "", {}

    if action == "check_updates":

        def work() -> None:
            try:
                try:
                    from apworld_updater import (
                        RELEASES_PAGE_URL,
                        check_for_update,
                        download_and_install,
                    )
                except ImportError:
                    from worlds.metroid_bread.apworld_updater import (
                        RELEASES_PAGE_URL,
                        check_for_update,
                        download_and_install,
                    )
                hub = helpers["find_hub_dir"]()
                world = helpers["find_world_dir_for_hub"](hub) if hub else None
                state.append_log(
                    "Checking GitHub Releases for a newer metroid_bread.apworld…"
                )
                result = check_for_update(world_dir=world)
                state.append_log(result.message)
                if not result.ok or not result.update_available:
                    return
                state.append_log(
                    f"Update available ({result.remote_version}). Downloading…"
                )
                ok, msg = download_and_install(
                    result.download_url,
                    expected_version=result.remote_version,
                    log=state.append_log,
                )
                state.append_log(msg)
                if not ok:
                    state.append_log(
                        f"Manual download: {result.releases_url or RELEASES_PAGE_URL}"
                    )
            except Exception as exc:
                state.append_log(f"Update check failed: {exc}")
                state.append_log(traceback.format_exc())

        _run_bg(state, work)
        return True, "", {}

    if action == "launch_hub":
        if not hub_ready_for_launch():
            return False, "not_ready", {}

        # Run in this request so the POST can return done+choice and the
        # browser page can close before the server shuts down.
        state.set_busy(True)
        try:
            hub = helpers["find_hub_dir"]()
            if not hub:
                state.append_log("Hub app not found.")
                return False, "no_hub", {}
            connect = helpers["parse_launcher_connect_args"](state.args)
            world = helpers["find_world_dir_for_hub"](hub)
            try:
                helpers["ensure_system_client_python_deps"](world)
            except RuntimeError as dep_exc:
                state.append_log(
                    f"Client Python deps warning (Hub may still open):\n{dep_exc}"
                )
            env = helpers["hub_env_from_connect"](connect, hub_dir=hub)
            state.append_log(f"Launching Hub from {hub} …")
            try:
                helpers["launch_hub_with_repair"](hub, env=env, wait=False)
            except Exception as exc:
                state.append_log(f"Hub launch failed: {exc}")
                state.append_log(traceback.format_exc())
                return False, "launch_failed", {}
            state.append_log("Hub started; closing setup wizard.")
            state.finish("hub")
            return True, "", {"done": True, "choice": "hub"}
        finally:
            invalidate_checklist_cache()
            if state.choice is None:
                state.set_busy(False)

    return False, "unknown_action", {}


def _run_bg(state: _WizardState, work: Callable[[], None]) -> None:
    if state.is_busy():
        state.append_log("Already running a task…")
        return

    def _target() -> None:
        state.set_busy(True)
        try:
            work()
        except Exception as exc:
            state.append_log(f"Error: {exc}")
            state.append_log(traceback.format_exc())
        finally:
            invalidate_checklist_cache()
            if state.choice is None:
                state.set_busy(False)

    threading.Thread(target=_target, daemon=True).start()


def run_setup_wizard(
    *,
    reason: str = "",
    args: Sequence[str] = (),
    wait: bool = True,
) -> str:
    """
    Modal Hub Setup Wizard (local HTML page in the default browser).

    Returns ``\"hub\"`` after a successful Hub launch from this page, or
    ``\"python\"`` when the user chooses the Kivy escape hatch.

    Hub is always spawned with ``wait=False``. The ``wait`` argument is retained
    for call-site compatibility and is unused for Launch Hub.
    """
    _ = wait
    helpers = _import_hub_helpers()
    state = _WizardState(reason=reason, args=args)
    state.append_log("Hub Setup Wizard ready (local browser UI).")
    if state.reason:
        state.append_log(f"Reason: {state.reason}")

    handler = _make_handler(state, helpers)
    # Bind localhost only; port 0 = ephemeral.
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    logger.info("Hub Setup Wizard listening at %s", url)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    opened = False
    try:
        # Prefer a new window so window.close() is more likely to work.
        opened = bool(webbrowser.open(url, new=1))
    except Exception as exc:
        logger.warning("webbrowser.open failed: %s", exc)
        opened = False

    if not opened:
        helpers["show_user_notice"](
            "Metroid Bread — Hub Setup",
            f"Open this URL in your browser to continue setup:\n\n{url}",
        )
    else:
        # Also print so console users see the link.
        print(f"Metroid Bread Hub Setup Wizard: {url}", file=sys.stderr, flush=True)

    # Block until user finishes (Launch Hub / Kivy) or process is killed.
    state.done_event.wait()
    choice = state.choice or "python"
    # Give the browser a moment to receive done + run window.close().
    time.sleep(1.5)

    def _shutdown() -> None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    # Shutdown from another thread so waiters unblock cleanly.
    threading.Thread(target=_shutdown, daemon=True).start()
    thread.join(timeout=5.0)
    return choice


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_setup_wizard(reason="Manual wizard test.")
    print("choice:", result)
    raise SystemExit(0 if result == "hub" else 1)
