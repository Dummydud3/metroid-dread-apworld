"""Metroid Bread Launcher Component"""

from worlds.LauncherComponents import Component, components, Type, launch_subprocess

# Register the app icon.
from worlds.metroid_bread.hub.icon_setup import *


def run_hub_or_client(*args):
    """Entry point for multiprocessing spawn — must stay at module level (picklable)."""
    try:
        from worlds.metroid_bread.hub.hub_launcher import launch_hub_or_fallback

        launch_hub_or_fallback(args, wait=True)
    except Exception as exc:
        # Show unexpected errors not already handled by the Hub launcher.
        try:
            from worlds.metroid_bread.hub.hub_launcher import LAUNCH_NEED_DEPS_HINT, show_user_error

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


# Register the Metroid Bread client with the launcher.
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
