#!/usr/bin/env python3
"""
Hub Setup Wizard — tkinter UI when Hub cannot start.

Shown before falling back to the Kivy MetroidBreadClient. Users can install
managed Node 24 / Python 3.12, repair Electron, launch Hub, or escape to Kivy.
"""

from __future__ import annotations

import logging
import threading
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("MetroidBread.HubSetupWizard")

LogFn = Callable[[str], None]


def collect_checklist() -> List[Tuple[str, bool, str]]:
    """
    Return checklist rows: (label, ok, detail).

    Uses hub_launcher / ensure_client_deps helpers (no network).
    """
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
    elif node and major is not None and major >= 25:
        rows.append(
            (
                "Node.js",
                False,
                f"{node} is v{major} (need 18–24; Install Node 24)",
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


def _client_python_status() -> Tuple[bool, str]:
    try:
        try:
            from ensure_client_deps import find_client_python, format_cmd
        except ImportError:
            from worlds.metroid_bread.ensure_client_deps import (
                find_client_python,
                format_cmd,
            )
        cmd = find_client_python()
        if cmd:
            return True, format_cmd(cmd)
        return False, "no usable 3.11–3.13 — Install Python 3.12"
    except Exception as exc:
        return False, f"check failed: {exc}"


def hub_ready_for_launch(rows: Optional[List[Tuple[str, bool, str]]] = None) -> bool:
    """Node + npm + Hub + Electron green (Python can finish after Hub opens)."""
    rows = rows if rows is not None else collect_checklist()
    by_name = {name: ok for name, ok, _ in rows}
    return all(by_name.get(k) for k in ("Node.js", "npm", "Hub app", "Electron"))


def run_setup_wizard(
    *,
    reason: str = "",
    args: Sequence[str] = (),
    wait: bool = True,
) -> str:
    """
    Modal Hub Setup Wizard.

    Returns ``\"hub\"`` after a successful Hub launch from this window, or
    ``\"python\"`` when the user chooses the Kivy escape hatch.

    Hub is always spawned with ``wait=False`` so this window can close while
    the client keeps running. The ``wait`` argument is retained for call-site
    compatibility and is unused for Launch Hub.

    Raises ImportError if tkinter is unavailable (caller falls back to Kivy).
    """
    _ = wait  # API compat; Launch Hub always detaches.    try:
        import tkinter as tk
        from tkinter import scrolledtext, ttk
    except ImportError as exc:
        raise ImportError("tkinter is required for the Hub Setup Wizard") from exc

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
        )

    result: Dict[str, str] = {"choice": "python"}
    busy = {"flag": False}

    root = tk.Tk()
    root.title("Metroid Bread — Hub Setup")
    root.minsize(640, 480)
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    # Header: title + red Kivy escape (top-right)
    header = ttk.Frame(root, padding=(12, 10, 12, 4))
    header.pack(fill=tk.X)
    title_col = ttk.Frame(header)
    title_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(title_col, text="Metroid Bread Client Hub Setup", font=("Segoe UI", 14, "bold")).pack(
        anchor=tk.W
    )
    reason_text = (reason or "Hub prerequisites are missing or launch failed.").strip()
    ttk.Label(
        title_col,
        text=reason_text[:500],
        wraplength=480,
        foreground="#444",
    ).pack(anchor=tk.W, pady=(4, 0))

    kivy_btn = tk.Button(
        header,
        text="Just open Kivy version",
        fg="white",
        bg="#c62828",
        activebackground="#b71c1c",
        activeforeground="white",
        relief=tk.RAISED,
        padx=10,
        pady=6,
        cursor="hand2",
    )
    kivy_btn.pack(side=tk.RIGHT, anchor=tk.NE)

    # Checklist
    check_frame = ttk.LabelFrame(root, text="Checklist", padding=10)
    check_frame.pack(fill=tk.X, padx=12, pady=6)
    check_vars: Dict[str, ttk.Label] = {}
    action_row = ttk.Frame(check_frame)
    action_row.pack(fill=tk.X, pady=(8, 0))

    status_labels_frame = ttk.Frame(check_frame)
    status_labels_frame.pack(fill=tk.X)

    def refresh_checklist() -> None:
        for child in status_labels_frame.winfo_children():
            child.destroy()
        check_vars.clear()
        for name, ok, detail in collect_checklist():
            mark = "OK" if ok else "MISSING"
            color = "#2e7d32" if ok else "#c62828"
            line = ttk.Frame(status_labels_frame)
            line.pack(fill=tk.X, pady=1)
            ttk.Label(line, text=f"[{mark}]", foreground=color, width=10).pack(side=tk.LEFT)
            ttk.Label(line, text=f"{name}: {detail}", wraplength=560).pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
            check_vars[name] = line
        launch_btn.configure(state=tk.NORMAL if hub_ready_for_launch() else tk.DISABLED)

    # Log pane
    log_frame = ttk.LabelFrame(root, text="Log", padding=6)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
    log_widget = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
    log_widget.pack(fill=tk.BOTH, expand=True)

    def append_log(msg: str) -> None:
        def _do() -> None:
            log_widget.configure(state=tk.NORMAL)
            log_widget.insert(tk.END, msg.rstrip() + "\n")
            log_widget.see(tk.END)
            log_widget.configure(state=tk.DISABLED)

        root.after(0, _do)

    def set_busy(flag: bool) -> None:
        busy["flag"] = flag
        state = tk.DISABLED if flag else tk.NORMAL

        def _do() -> None:
            for btn in action_buttons:
                try:
                    btn.configure(state=state)
                except tk.TclError:
                    pass
            # Launch Hub still gated by checklist when not busy
            if not flag:
                refresh_checklist()
            else:
                launch_btn.configure(state=tk.DISABLED)

        root.after(0, _do)

    def run_bg(work: Callable[[], None], *, done_msg: str = "") -> None:
        if busy["flag"]:
            append_log("Already running a task…")
            return

        def _target() -> None:
            set_busy(True)
            try:
                work()
                if done_msg:
                    append_log(done_msg)
            except Exception as exc:
                append_log(f"Error: {exc}")
                append_log(traceback.format_exc())
            finally:
                # Hub launch destroys the wizard; skip UI updates on a dead root.
                if result.get("choice") == "hub":
                    return
                set_busy(False)
                try:
                    root.after(0, refresh_checklist)
                except tk.TclError:
                    pass

        threading.Thread(target=_target, daemon=True).start()

    def do_install_node() -> None:
        def work() -> None:
            append_log("Installing portable Node 24…")
            ok, msg = ensure_portable_node24(log=append_log)
            append_log(msg if ok else f"FAILED: {msg}")

        run_bg(work)

    def do_install_python() -> None:
        def work() -> None:
            append_log("Installing portable Python 3.12…")
            ok, msg = ensure_portable_python312(log=append_log)
            append_log(msg if ok else f"FAILED: {msg}")
            if ok:
                hub = find_hub_dir()
                world = find_world_dir_for_hub(hub) if hub else None
                try:
                    append_log("Ensuring client Python packages…")
                    ensure_system_client_python_deps(world)
                    append_log("Client Python packages OK.")
                except RuntimeError as dep_exc:
                    append_log(f"Client deps warning:\n{dep_exc}")

        run_bg(work)

    def do_fix_electron() -> None:
        def work() -> None:
            hub = find_hub_dir()
            if not hub:
                append_log("Hub app not found; cannot repair Electron.")
                return
            append_log(f"Repairing Hub npm / Electron at {hub} …")
            ensure_hub_packages(hub, force_reinstall_electron=True)
            append_log("Electron repair finished.")

        run_bg(work)

    def do_refresh() -> None:
        append_log("Refreshing checklist…")
        refresh_checklist()

    def do_check_updates() -> None:
        if busy["flag"]:
            append_log("Already running a task…")
            return

        def work() -> None:
            set_busy(True)
            try:
                try:
                    from apworld_updater import (
                        check_for_update,
                        download_and_install,
                        RELEASES_PAGE_URL,
                    )
                except ImportError:
                    from worlds.metroid_bread.apworld_updater import (
                        check_for_update,
                        download_and_install,
                        RELEASES_PAGE_URL,
                    )
                hub = find_hub_dir()
                world = find_world_dir_for_hub(hub) if hub else None
                append_log("Checking GitHub Releases for a newer metroid_bread.apworld…")
                result = check_for_update(world_dir=world)
                append_log(result.message)

                def after_check() -> None:
                    from tkinter import messagebox

                    if not result.ok or not result.update_available:
                        if not result.ok:
                            messagebox.showinfo(
                                "Apworld update check",
                                result.message,
                                parent=root,
                            )
                        else:
                            messagebox.showinfo(
                                "Apworld update",
                                result.message,
                                parent=root,
                            )
                        set_busy(False)
                        refresh_checklist()
                        return

                    choice = messagebox.askyesnocancel(
                        "Metroid Bread apworld update",
                        f"{result.message}\n\nDownload and install metroid_bread.apworld?\n\n"
                        f"Yes = download\nNo = not now\nCancel = open releases page",
                        parent=root,
                    )
                    if choice is True:

                        def do_install() -> None:
                            try:
                                ok, msg = download_and_install(
                                    result.download_url,
                                    expected_version=result.remote_version,
                                    log=append_log,
                                )
                                append_log(msg)

                                def done() -> None:
                                    if ok:
                                        messagebox.showinfo(
                                            "Update installed", msg, parent=root
                                        )
                                    else:
                                        messagebox.showerror(
                                            "Update failed", msg, parent=root
                                        )
                                    set_busy(False)
                                    refresh_checklist()

                                root.after(0, done)
                            except Exception as exc:
                                append_log(f"Update install failed: {exc}")
                                append_log(traceback.format_exc())
                                root.after(0, lambda: set_busy(False))

                        threading.Thread(target=do_install, daemon=True).start()
                        return
                    if choice is None:
                        try:
                            import webbrowser

                            webbrowser.open(result.releases_url or RELEASES_PAGE_URL)
                        except Exception as exc:
                            append_log(f"Could not open browser: {exc}")
                    set_busy(False)
                    refresh_checklist()

                root.after(0, after_check)
            except Exception as exc:
                append_log(f"Update check failed: {exc}")
                append_log(traceback.format_exc())
                set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def do_launch_hub() -> None:
        if busy["flag"]:
            return

        def work() -> None:
            hub = find_hub_dir()
            if not hub:
                append_log("Hub app not found.")
                return
            connect = parse_launcher_connect_args(args)
            world = find_world_dir_for_hub(hub)
            try:
                ensure_system_client_python_deps(world)
            except RuntimeError as dep_exc:
                append_log(f"Client Python deps warning (Hub may still open):\n{dep_exc}")
            env = hub_env_from_connect(connect, hub_dir=hub)
            append_log(f"Launching Hub from {hub} …")
            # Always detach: wizard must close immediately; Hub lives on its own.
            # Ignore run_setup_wizard(wait=…); parent does not re-launch when we
            # return "hub".
            try:
                launch_hub_with_repair(hub, env=env, wait=False)
            except Exception as exc:
                append_log(f"Hub launch failed: {exc}")
                append_log(traceback.format_exc())
                return
            result["choice"] = "hub"
            append_log("Hub started; closing setup wizard.")
            root.after(0, root.destroy)

        run_bg(work)

    def do_kivy() -> None:
        result["choice"] = "python"
        root.destroy()

    kivy_btn.configure(command=do_kivy)

    ttk.Button(action_row, text="Install Node 24", command=do_install_node).pack(
        side=tk.LEFT, padx=(0, 6)
    )
    ttk.Button(action_row, text="Install Python 3.12", command=do_install_python).pack(
        side=tk.LEFT, padx=(0, 6)
    )
    ttk.Button(action_row, text="Fix / refresh Electron", command=do_fix_electron).pack(
        side=tk.LEFT, padx=(0, 6)
    )
    ttk.Button(action_row, text="Check for updates", command=do_check_updates).pack(
        side=tk.LEFT, padx=(0, 6)
    )
    ttk.Button(action_row, text="Refresh", command=do_refresh).pack(side=tk.LEFT, padx=(0, 6))

    footer = ttk.Frame(root, padding=(12, 4, 12, 12))
    footer.pack(fill=tk.X)
    launch_btn = ttk.Button(footer, text="Launch Hub", command=do_launch_hub)
    launch_btn.pack(side=tk.RIGHT)

    action_buttons = list(action_row.winfo_children()) + [launch_btn, kivy_btn]

    append_log("Hub Setup Wizard ready.")
    if reason_text:
        append_log(f"Reason: {reason_text}")
    refresh_checklist()

    # Center roughly
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

    root.protocol("WM_DELETE_WINDOW", do_kivy)
    root.mainloop()
    return result["choice"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    choice = run_setup_wizard(reason="Manual wizard test.")
    print("choice:", choice)
