# PyInstaller: one-file, windowless DungeonMaps.exe (built on GitHub Actions, windows-latest)
# pyinstaller packaging/DungeonMaps.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "packaging", "windows_entry.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "dungeonmaps", "data"), os.path.join("dungeonmaps", "data"))],
    hiddenimports=["windows_capture", "websockets.sync.client"],
    excludes=["gi", "matplotlib", "scipy", "pandas"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="DungeonMaps",
    console=False,
    upx=False,
    icon=os.path.join(ROOT, "packaging", "icon.ico") if os.path.exists(os.path.join(ROOT, "packaging", "icon.ico")) else None,
)
