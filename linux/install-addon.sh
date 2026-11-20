#!/bin/sh
# Copies the Dungeon Maps addon into WoW: Forever's AddOns folder (replacing an older copy).
#   linux/install-addon.sh "<path to World of Warcraft/_forever_>"
# Without a path it looks in the usual Wine/Faugus/Lutris places.
set -e
ROOT=$(dirname "$(dirname "$(readlink -f "$0")")")
GAME="$1"
if [ -z "$GAME" ]; then
	for d in "$HOME"/Faugus/*/drive_c "$HOME"/Games/*/drive_c "$HOME"/.wine/drive_c "$HOME"/Games/*/*/drive_c; do
		c="$d/Program Files (x86)/World of Warcraft/_forever_"
		[ -d "$c/Interface" ] && GAME="$c" && break
	done
fi
[ -d "$GAME" ] || { echo "WoW: Forever folder not found; pass it: $0 \"<.../World of Warcraft/_forever_>\""; exit 1; }
ADDONS="$GAME/Interface/AddOns"
mkdir -p "$ADDONS"
rm -rf "$ADDONS/DungeonMaps.new"
cp -r "$ROOT/addon/DungeonMaps" "$ADDONS/DungeonMaps.new"
rm -rf "$ADDONS/DungeonMaps"
mv "$ADDONS/DungeonMaps.new" "$ADDONS/DungeonMaps"
echo "installed: $ADDONS/DungeonMaps"
[ -d "$ADDONS/ForeverDungeonRoutes/maps" ] || echo "note: install Forever Dungeon Routes too, for the 17 picture maps (it can stay disabled)"
