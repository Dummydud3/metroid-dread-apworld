"""
Metroid Dread Launcher Component
Registers the Metroid Dread client in the Archipelago Launcher
"""

from worlds.LauncherComponents import Component, components, Type, launch_subprocess

# Register icon
from .icon_setup import *


def run_client(*args):
    """Client entry point. Must stay at module level for multiprocessing spawn."""
    from MetroidDreadClient import main, get_base_parser
    import asyncio

    parser = get_base_parser(description="Metroid Dread Client for Archipelago")
    parser.add_argument('--dread-ip', default='127.0.0.1',
                      help='IP address of Ryujinx running Dread')

    parsed_args = parser.parse_args(args)
    asyncio.run(main(parsed_args))


def launch_metroid_dread_client(*args):
    """Launch the Metroid Dread client"""
    launch_subprocess(run_client, name="Metroid Dread Client", args=args)


# Register the Metroid Dread client component
components.append(
    Component(
        display_name="Metroid Dread Client",
        script_name="MetroidDreadClient",
        frozen_name="ArchipelagoMetroidDreadClient",
        func=launch_metroid_dread_client,
        component_type=Type.CLIENT,
        icon="metroid_dread",
        game_name="Metroid Dread",
        supports_uri=True,
        cli=False,
        description="Connect to Metroid Dread running in Ryujinx and sync items/locations with the multiworld."
    )
)
