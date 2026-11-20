"""python -m dungeonmaps: the live tracker for this system (Linux: feeds the Quickshell overlay on
stdout; Windows: draws its own overlay)."""
import sys

if sys.platform == "win32":
    from .windows import main
else:
    from .linux import main

main()
