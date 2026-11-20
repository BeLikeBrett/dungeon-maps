"""Permission UI shown only when the user opens the Windows tracker, never at OS startup."""
import asyncio
import ctypes
import os
import sys

CAPTURE_TITLE = "Dungeon Maps — capture permission"
BORDER_TITLE = "Dungeon Maps — screenshot borders"


def ask_capture(log):
    """Authorize this run before reading any game-window pixels."""
    user32 = ctypes.windll.user32
    user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    answer = user32.MessageBoxW(None,
        "Allow Dungeon Maps to read the World of Warcraft window while it runs?\n\n"
        "This updates your map position even when another window covers the game.\n"
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
    # Desktop applications can be denied by the system-wide Screenshot borders switch.
    # Offer the documented Settings page; the user makes the permission change themselves.
    answer = ctypes.windll.user32.MessageBoxW(None,
        "Windows has not allowed capture without its yellow border.\n\n"
        "Open Screenshot borders in Windows Settings to allow apps to turn it off?\n\n"
        "Choosing No continues with the border.", BORDER_TITLE, 0x4 | 0x20 | 0x100)
    if answer == 6:
        try:
            os.startfile("ms-settings:privacy-graphicscapturewithoutborder")
        except OSError as error:
            log("could not open Screenshot borders settings:", repr(error))
    return False
