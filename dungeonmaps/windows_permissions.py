"""Permission UI shown only when the user opens the Windows tracker, never at OS startup."""
import asyncio
import ctypes
import sys

CAPTURE_TITLE = "Dungeon Maps — capture permission"
BORDER_TITLE = "Dungeon Maps — screenshot borders"


def ask_capture(log):
    """Authorize this run before reading any game-window pixels."""
    user32 = ctypes.windll.user32
    user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    answer = user32.MessageBoxW(None,
        "Allow Dungeon Maps to read the World of Warcraft window while it runs?\n\n"
        "It reads the minimap and the dungeon map to place your arrow, and nothing else.\n"
        "You can close the tracker at any time from its tray icon.",
        CAPTURE_TITLE, 0x4 | 0x20 | 0x100)  # Yes/No, question, default No
    if answer != 6:  # IDYES
        log("capture permission declined")
        return False
    log("capture permission granted for this run")
    return True


def request_borderless(log):
    """Ask Windows for its actual borderless-capture permission; never change policy ourselves."""
    if sys.getwindowsversion().build < 20348:
        log("borderless capture permission is unavailable on this Windows version")
        return False
    try:
        from winrt.windows.graphics.capture import GraphicsCaptureAccess, GraphicsCaptureAccessKind
        from winrt.windows.security.authorization.appcapabilityaccess import AppCapabilityAccessStatus

        async def request():
            return await GraphicsCaptureAccess.request_access_async(GraphicsCaptureAccessKind.BORDERLESS)

        status = asyncio.run(request())
        log("borderless capture access:", status.name)
        if status == AppCapabilityAccessStatus.ALLOWED:
            return True
    except Exception as error:
        log("borderless capture access unavailable:", repr(error))
        return False
    # Denied (the system-wide Screenshot borders switch): no dialog; the tracker reads the screen
    # instead, which never shows a border.
    return False
