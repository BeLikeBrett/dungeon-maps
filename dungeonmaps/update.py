"""Self-update from the GitHub releases: the Windows exe, and the add-on in WoW: Forever's AddOns.

Each start of DungeonMaps.exe (before anything else) asks GitHub for the latest release:
  * a newer exe is downloaded next to the running one, checked against GitHub's SHA-256 digest,
    swapped in (a running exe can be renamed, not overwritten), and started; this copy exits;
  * the add-on in <WoW>/_forever_/Interface/AddOns/DungeonMaps is replaced by the release's add-on
    when its "## Version" is older (or installed when the folder is missing but WoW: Forever is there).
    The swap goes through a temporary folder, so a failed download never leaves a half add-on.
Any failure (offline, GitHub down, no permission) is logged and the tracker just carries on.
DUNGEONMAPS_UPDATE=off turns it off.
"""

import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile

from . import __version__
from .data import user_dir

REPO = "BeLikeBrett/dungeon-maps"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
EXE_ASSET, ADDON_ASSET = "DungeonMaps.exe", "DungeonMaps-addon.zip"
SETTINGS = os.path.join(user_dir("state"), "update.json")
last_release = None


def version_tuple(text):
    """'v1.0.3' / '1.0.3' -> (1, 0, 3); unreadable -> ()."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "DungeonMaps/%s" % __version__,
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_release(timeout=5):
    """{"version": (1, 0, 3), "tag": "v1.0.3", "assets": {name: {"url", "sha256"}}} or None."""
    rel = json.loads(_get(API, timeout))
    assets = {}
    for a in rel.get("assets", []):
        digest = a.get("digest") or ""
        assets[a["name"]] = {"url": a["browser_download_url"],
                             "sha256": digest[7:] if digest.startswith("sha256:") else None}
    return {"version": version_tuple(rel.get("tag_name")), "tag": rel.get("tag_name"), "assets": assets}


def download(asset, timeout=60):
    """The asset's bytes, checked against GitHub's SHA-256 (refused when it doesn't match)."""
    data = _get(asset["url"], timeout)
    if asset.get("sha256") and hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError("download doesn't match its SHA-256")
    return data


# -- the add-on ---------------------------------------------------------------------------------------

def addon_version(addons_dir):
    try:
        with open(os.path.join(addons_dir, "DungeonMaps", "DungeonMaps.toc"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("## Version:"):
                    return version_tuple(line)
    except OSError:
        return None
    return ()


def install_addon(addons_dir, zip_bytes):
    """Replace AddOns/DungeonMaps with the zip's DungeonMaps folder, all or nothing."""
    tmp = os.path.join(addons_dir, "DungeonMaps.update")
    old = os.path.join(addons_dir, "DungeonMaps.previous")
    dest = os.path.join(addons_dir, "DungeonMaps")
    for d in (tmp, old):
        shutil.rmtree(d, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not any(n.replace("\\", "/") == "DungeonMaps/DungeonMaps.toc" for n in names):
            raise ValueError("the add-on zip has no DungeonMaps/DungeonMaps.toc")
        for n in names:
            parts = n.replace("\\", "/").split("/")
            if parts[0] != "DungeonMaps" or ".." in parts or n.endswith("/"):
                continue
            target = os.path.join(tmp, *parts[1:])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(z.read(n))
    if os.path.isdir(dest):
        os.replace(dest, old)
    try:
        os.replace(tmp, dest)
    except OSError:
        if os.path.isdir(old) and not os.path.exists(dest):
            os.replace(old, dest)
        raise
    shutil.rmtree(old, ignore_errors=True)


def find_addons_dirs():
    """WoW: Forever AddOns folders: the one seen last time, the usual install places, the registry's."""
    found = []
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            found.append(json.load(fh).get("addons"))
    except (OSError, ValueError):
        pass
    roots = []
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(env):
            roots.append(os.path.join(os.environ[env], "World of Warcraft"))
    try:
        import winreg
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft",
                                    0, winreg.KEY_READ | view) as k:
                    path = winreg.QueryValueEx(k, "InstallPath")[0]
                    roots.append(os.path.dirname(os.path.normpath(path)))
            except OSError:
                pass
    except ImportError:
        pass
    for root in roots:
        found.append(os.path.join(root, "_forever_", "Interface", "AddOns"))
    out = []
    for d in found:
        if d and os.path.isdir(os.path.dirname(d)) and d not in out:  # (the Interface folder exists)
            out.append(d)
    return out


def remember_addons_dir(wow_exe):
    """Called with Wow.exe's path once the game is seen: next time the add-on is found at once."""
    d = os.path.join(os.path.dirname(wow_exe), "Interface", "AddOns")
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            json.dump({"addons": d}, fh)
    except OSError:
        pass
    return d


def update_addon(rel, log, addons_dirs=None):
    """Bring the add-on up to the release. Returns a short note for the user, or None."""
    asset = rel["assets"].get(ADDON_ASSET)
    if not asset:
        return None
    note = None
    for d in addons_dirs if addons_dirs is not None else find_addons_dirs():
        have = addon_version(d)
        if have is not None and have >= rel["version"]:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            install_addon(d, download(asset))
            log("add-on %s: %s -> %s" % (d, ".".join(map(str, have)) if have else "none", rel["tag"]))
            note = "The Dungeon Maps add-on was updated to %s. If WoW is open, type /reload." % rel["tag"]
        except Exception as e:
            log("add-on update failed in %s: %r" % (d, e))
    return note


# -- the exe ------------------------------------------------------------------------------------------

def cleanup_old_exe():
    if getattr(sys, "frozen", False):
        old = sys.executable + ".old"
        for _ in range(20):  # (the previous copy may take a moment to exit)
            try:
                if os.path.exists(old):
                    os.remove(old)
                return
            except OSError:
                time.sleep(0.25)


def update_exe(rel, log):
    """Swap in the release's exe and start it. Returns True when this copy should exit."""
    if not getattr(sys, "frozen", False) or rel["version"] <= version_tuple(__version__):
        return False
    asset = rel["assets"].get(EXE_ASSET)
    if not asset:
        return False
    exe = sys.executable
    new, old = exe + ".new", exe + ".old"
    try:
        with open(new, "wb") as fh:
            fh.write(download(asset, timeout=120))
        if os.path.exists(old):
            os.remove(old)
        os.replace(exe, old)          # a running exe can be renamed...
        os.replace(new, exe)          # ...and the new one put in its place
    except Exception as e:
        log("exe update failed: %r" % e)
        try:
            if not os.path.exists(exe) and os.path.exists(old):
                os.replace(old, exe)
            if os.path.exists(new):
                os.remove(new)
        except OSError:
            pass
        return False
    import subprocess
    args = [a for a in sys.argv[1:] if not a.startswith("--updated-from=")]
    try:
        subprocess.Popen([exe] + args + ["--updated-from=%d" % os.getpid()], close_fds=True)
    except OSError as e:
        log("updated exe could not start; restoring previous copy: %r" % e)
        os.replace(exe, new)
        os.replace(old, exe)
        os.remove(new)
        return False
    log("updated %s -> %s; restarting" % (__version__, rel["tag"]))
    return True


def wait_for_previous():
    """The copy that just updated us: wait until it has exited (it holds the single-instance lock)."""
    for a in sys.argv:
        if a.startswith("--updated-from="):
            try:
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.windll.kernel32
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                h = kernel.OpenProcess(0x00100000, False, int(a.split("=", 1)[1]))  # SYNCHRONIZE
                if h:
                    ctypes.windll.kernel32.WaitForSingleObject(h, 15000)
                    ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                time.sleep(2)


def run(log):
    """At start: returns (exit_now, note for the user or None)."""
    if os.environ.get("DUNGEONMAPS_UPDATE", "").lower() in ("off", "0", "no"):
        return False, None
    wait_for_previous()
    cleanup_old_exe()
    try:
        rel = latest_release()
    except Exception as e:
        log("update check failed: %r" % e)
        return False, None
    if not rel["version"]:
        return False, None
    global last_release
    last_release = rel
    log("latest release %s (this is %s)" % (rel["tag"], __version__))
    note = update_addon(rel, log)
    if update_exe(rel, log):
        return True, None
    return False, note
