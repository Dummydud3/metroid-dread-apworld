"""
Metroid Bread Launcher Component
Registers the Metroid Bread Client Hub in the Archipelago Launcher.

Launch path:
  1. Prefer our Electron Metroid Bread Client Hub (dread-client-app)
  2. Download npm packages when missing; auto-repair incomplete Electron installs
  3. Fall back to the Python MetroidBreadClient when Hub cannot start
"""

from worlds.LauncherComponents import Component, components, Type, launch_subprocess

# Register icon
from .icon_setup import *


def run_hub_or_client(*args):
    """
    Entry point for multiprocessing spawn — must stay at module level (picklable).
    Starts our Hub with package install/repair, or the Python client fallback.

    Any failure must show a MessageBox / wizard — never a silent no-op.
    """
    try:
        from .hub_launcher import launch_hub_or_fallback

        launch_hub_or_fallback(args, wait=True)
    except Exception as exc:
        # launch_hub_or_fallback already MessageBoxes most paths; this catches
        # import failures or anything that escaped without UI.
        try:
            from .hub_launcher import LAUNCH_NEED_DEPS_HINT, show_user_error

            show_user_error(
                "Metroid Bread Client",
                f"Could not start Metroid Bread Client:\n\n{exc}\n\n"
                f"{LAUNCH_NEED_DEPS_HINT}",
            )
        except Exception:
            import sys

            print(f"Metroid Bread Client failed: {exc}", file=sys.stderr, flush=True)


def launch_metroid_bread_client(*args):
    """Launch our Metroid Bread Client Hub (or Python fallback)."""
    launch_subprocess(run_hub_or_client, name="Metroid Bread Client Hub", args=args)


# Register the Metroid Bread client component
components.append(
    Component(
        display_name="Metroid Bread Client",
        script_name="MetroidBreadClient",
        frozen_name="ArchipelagoMetroidBreadClient",
        func=launch_metroid_bread_client,
        component_type=Type.CLIENT,
        icon="metroid_bread",
        game_name="Metroid Bread",
        supports_uri=True,
        cli=False,
        description=(
            "Launch the Metroid Bread Client Hub (patcher + tracker + connect UI). "
        ),
    )
)
