"""PyInstaller entry point for DungeonMaps.exe."""
from dungeonmaps.windows import info, main

try:
    main()
except Exception as error:
    # A windowless PyInstaller app otherwise opens an error dialog over the game.
    info("tracker stopped:", repr(error))
