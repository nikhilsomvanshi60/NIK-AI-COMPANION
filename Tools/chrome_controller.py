import asyncio
import subprocess
import platform
import os
import sqlite3
import shutil
import time
from datetime import datetime
from livekit.agents import function_tool


# ─── Chrome Action Registry ───────────────────────────────────────────────────────
_CHROME_ACTIONS = {
    # Window / Tab
    "new_window":           "Opens a new Chrome browser window",
    "new_tab":              "Opens a new tab (Ctrl+T)",
    "close_tab":            "Closes the current tab (Ctrl+W)",
    "reopen_tab":           "Reopens the last closed tab (Ctrl+Shift+T)",
    "next_tab":             "Switches to the next tab",
    "prev_tab":             "Switches to the previous tab",
    "tab_1":                "Switches to tab 1",
    "tab_2":                "Switches to tab 2",
    "tab_3":                "Switches to tab 3",
    "tab_4":                "Switches to tab 4",
    "tab_5":                "Switches to tab 5",
    "tab_6":                "Switches to tab 6",
    "tab_7":                "Switches to tab 7",
    "tab_8":                "Switches to tab 8",
    "last_tab":             "Switches to the last tab",
    "duplicate_tab":        "Duplicates the current tab",
    "pin_tab":              "Pins/unpins current tab via context menu",
    "mute_tab":             "Mutes/unmutes the current tab via context menu",
    "close_window":         "Closes the current Chrome window (Ctrl+Shift+W)",
    "incognito":            "Opens a new incognito window",
    "fullscreen":           "Toggles fullscreen mode (F11)",
    "minimize":             "Minimizes the Chrome window",
    "maximize":             "Maximizes the Chrome window",
    # Navigation
    "navigate":             "Navigates to any URL given in the 'query' parameter",
    "go_back":              "Goes back to the previous page",
    "go_forward":           "Goes forward to the next page",
    "reload":               "Reloads the current page",
    "hard_reload":          "Hard reloads (cache cleared) the current page",
    "stop":                 "Stops page loading (Escape)",
    "home":                 "Goes to the home page",
    "focus_addressbar":     "Focuses the address bar",
    # Search
    "search":               "Opens a Google search with the given query",
    "search_youtube":       "Opens a YouTube search with the given query",
    "search_maps":          "Opens Google Maps search with the given query",
    "search_images":        "Opens Google Images search with the given query",
    "search_news":          "Opens Google News search with the given query",
    "search_translate":     "Opens Google Translate for the given text",
    "search_wikipedia":     "Opens Wikipedia search for the given query",
    "search_reddit":        "Opens Reddit search for the given query",
    "search_github":        "Opens GitHub search for the given query",
    "find_in_page":         "Opens in-page search bar with optional query",
    "find_next":            "Finds the next match in page",
    "find_prev":            "Finds the previous match in page",
    # Zoom / View
    "zoom_in":              "Zooms in on the current page",
    "zoom_out":             "Zooms out on the current page",
    "zoom_reset":           "Resets zoom to 100%",
    "view_source":          "Opens page source code",
    "print_page":           "Opens print dialog",
    "save_page":            "Saves current page to disk",
    "reading_mode":         "Toggles Chrome Reading List side panel",
    # Scrolling
    "scroll_down":          "Scrolls the page down",
    "scroll_up":            "Scrolls the page up",
    "scroll_top":           "Scrolls to the very top",
    "scroll_bottom":        "Scrolls to the very bottom",
    # Bookmarks
    "bookmark_page":        "Bookmarks the current page",
    "bookmark_all_tabs":    "Bookmarks all open tabs into a folder",
    "toggle_bookmarks_bar": "Shows/hides the bookmarks bar",
    # Developer Tools
    "devtools":             "Opens Chrome DevTools panel",
    "devtools_console":     "Opens DevTools Console tab",
    "devtools_inspector":   "Opens DevTools Element Inspector",
    "devtools_network":     "Opens DevTools Network tab",
    "task_manager":         "Opens Chrome built-in Task Manager",
    "clear_data":           "Opens Clear Browsing Data dialog",
    # Screenshot
    "screenshot":           "Takes a screenshot and saves to ~/ChromeScreenshots/",
    # Chrome Internal Pages
    "settings":             "Opens chrome://settings",
    "downloads":            "Opens chrome://downloads",
    "extensions":           "Opens chrome://extensions",
    "history":              "Opens chrome://history",
    "bookmarks_page":       "Opens chrome://bookmarks",
    "flags":                "Opens chrome://flags",
    "passwords":            "Opens chrome://password-manager/passwords",
    "newtab":               "Opens chrome://newtab",
    "about":                "Opens chrome://settings/help",
    "version":              "Opens chrome://version",
    "gpu":                  "Opens chrome://gpu",
    "net_internals":        "Opens chrome://net-internals",
    "crashes":              "Opens chrome://crashes",
    "memory":               "Opens chrome://memory-internals",
    "performance":          "Opens chrome://performance",
    "site_settings":        "Opens chrome://settings/content",
    "accessibility":        "Opens chrome://accessibility",
    "sync":                 "Opens chrome://settings/syncSetup",
    "privacy":              "Opens chrome://settings/privacy",
    "appearance":           "Opens chrome://settings/appearance",
    "search_engines":       "Opens chrome://settings/searchEngines",
    "startup":              "Opens chrome://settings/onStartup",
    "languages":            "Opens chrome://settings/languages",
    "system":               "Opens chrome://settings/system",
    "reset_settings":       "Opens chrome://settings/reset",
    "safety_check":         "Opens chrome://settings/safetyCheck",
    "payment_methods":      "Opens chrome://settings/payments",
    "addresses":            "Opens chrome://settings/addresses",
    # Local Data Read
    "recent_history":       "Reads local Chrome history DB — recent visited URLs",
    "top_sites":            "Reads local Chrome history DB — most visited sites",
}

# ─── chrome:// URL Map ────────────────────────────────────────────────────────────
_CHROME_URL_MAP = {
    "settings":         "chrome://settings",
    "downloads":        "chrome://downloads",
    "extensions":       "chrome://extensions",
    "history":          "chrome://history",
    "bookmarks_page":   "chrome://bookmarks",
    "flags":            "chrome://flags",
    "passwords":        "chrome://password-manager/passwords",
    "newtab":           "chrome://newtab",
    "about":            "chrome://settings/help",
    "version":          "chrome://version",
    "gpu":              "chrome://gpu",
    "net_internals":    "chrome://net-internals/#general",
    "crashes":          "chrome://crashes",
    "memory":           "chrome://memory-internals",
    "performance":      "chrome://performance",
    "site_settings":    "chrome://settings/content",
    "accessibility":    "chrome://accessibility",
    "sync":             "chrome://settings/syncSetup",
    "privacy":          "chrome://settings/privacy",
    "appearance":       "chrome://settings/appearance",
    "search_engines":   "chrome://settings/searchEngines",
    "startup":          "chrome://settings/onStartup",
    "languages":        "chrome://settings/languages",
    "system":           "chrome://settings/system",
    "reset_settings":   "chrome://settings/reset",
    "safety_check":     "chrome://settings/safetyCheck",
    "payment_methods":  "chrome://settings/payments",
    "addresses":        "chrome://settings/addresses",
}

# ─── Simple Hotkey Map ────────────────────────────────────────────────────────────
_HOTKEY_MAP = {
    "new_tab":              ("ctrl", "t"),
    "close_tab":            ("ctrl", "w"),
    "reopen_tab":           ("ctrl", "shift", "t"),
    "next_tab":             ("ctrl", "tab"),
    "prev_tab":             ("ctrl", "shift", "tab"),
    "tab_1":                ("ctrl", "1"),
    "tab_2":                ("ctrl", "2"),
    "tab_3":                ("ctrl", "3"),
    "tab_4":                ("ctrl", "4"),
    "tab_5":                ("ctrl", "5"),
    "tab_6":                ("ctrl", "6"),
    "tab_7":                ("ctrl", "7"),
    "tab_8":                ("ctrl", "8"),
    "last_tab":             ("ctrl", "9"),
    "close_window":         ("ctrl", "shift", "w"),
    "incognito":            ("ctrl", "shift", "n"),
    "fullscreen":           ("f11",),
    "go_back":              ("alt", "left"),
    "go_forward":           ("alt", "right"),
    "reload":               ("ctrl", "r"),
    "hard_reload":          ("ctrl", "shift", "r"),
    "stop":                 ("escape",),
    "home":                 ("alt", "home"),
    "focus_addressbar":     ("ctrl", "l"),
    "find_next":            ("ctrl", "g"),
    "find_prev":            ("ctrl", "shift", "g"),
    "zoom_in":              ("ctrl", "="),
    "zoom_out":             ("ctrl", "-"),
    "zoom_reset":           ("ctrl", "0"),
    "view_source":          ("ctrl", "u"),
    "print_page":           ("ctrl", "p"),
    "save_page":            ("ctrl", "s"),
    "reading_mode":         ("ctrl", "shift", "e"),
    "scroll_down":          ("space",),
    "scroll_up":            ("shift", "space"),
    "scroll_top":           ("ctrl", "home"),
    "scroll_bottom":        ("ctrl", "end"),
    "bookmark_page":        ("ctrl", "d"),
    "bookmark_all_tabs":    ("ctrl", "shift", "d"),
    "toggle_bookmarks_bar": ("ctrl", "shift", "b"),
    "devtools":             ("ctrl", "shift", "i"),
    "devtools_console":     ("ctrl", "shift", "j"),
    "devtools_inspector":   ("ctrl", "shift", "c"),
    "task_manager":         ("shift", "escape"),
    "clear_data":           ("ctrl", "shift", "delete"),
}

# ─── Chrome Executable Paths ──────────────────────────────────────────────────────
_CHROME_PATHS = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ],
    "Linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ],
}

_HISTORY_PATHS = {
    "Windows": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History"),
    "Darwin":  os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/History"),
    "Linux":   os.path.expanduser("~/.config/google-chrome/Default/History"),
}

_SCREENSHOT_DIR = os.path.expanduser("~/ChromeScreenshots")


# ══════════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════════

def _get_os() -> str:
    return platform.system()


def _find_chrome() -> str | None:
    os_name = _get_os()
    for path in _CHROME_PATHS.get(os_name, []):
        if os.path.isfile(path):
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _is_chrome_running() -> bool:
    """Returns True if Chrome/Chromium is already running."""
    os_name = _get_os()
    try:
        if os_name == "Windows":
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                stderr=subprocess.DEVNULL, text=True,
            )
            return "chrome.exe" in out.lower()
        elif os_name == "Darwin":
            out = subprocess.check_output(
                ["pgrep", "-x", "Google Chrome"],
                stderr=subprocess.DEVNULL, text=True,
            )
            return bool(out.strip())
        else:  # Linux
            for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
                try:
                    out = subprocess.check_output(
                        ["pgrep", "-f", name],
                        stderr=subprocess.DEVNULL, text=True,
                    )
                    if out.strip():
                        return True
                except subprocess.CalledProcessError:
                    continue
            return False
    except Exception:
        return False


def _get_pyautogui():
    """Import pyautogui or raise RuntimeError with fix instructions."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        return pyautogui
    except ImportError:
        raise RuntimeError(
            "pyautogui install nahi hai.\n"
            "  Fix: pip install pyautogui\n"
            "  Linux: sudo apt-get install python3-xlib"
        )


def _paste_url_to_addressbar(pya, url: str, new_tab: bool = True) -> None:
    """
    Paste a URL into Chrome's address bar using the best available method.

    Strategy (in order of reliability):
      1. pyperclip  — clipboard paste, works for all URLs including chrome://
      2. typewrite  — fallback if pyperclip not installed; slower, may drop chars
                      but we type char-by-char with longer interval as safety net

    This function is SYNCHRONOUS — always run it via asyncio.to_thread().
    """
    # ── Try pyperclip first (most reliable) ──────────────────────────────────────
    try:
        import pyperclip
        pyperclip.copy(url)
        _method = "clipboard"
    except ImportError:
        pyperclip = None
        _method = "typewrite"

    # ── Open new tab if requested ─────────────────────────────────────────────────
    if new_tab:
        pya.hotkey("ctrl", "t")
        time.sleep(0.5)

    # ── Focus address bar ─────────────────────────────────────────────────────────
    pya.hotkey("ctrl", "l")
    time.sleep(0.4)

    # ── Select all existing text ──────────────────────────────────────────────────
    pya.hotkey("ctrl", "a")
    time.sleep(0.15)

    # ── Paste URL ─────────────────────────────────────────────────────────────────
    if _method == "clipboard":
        pya.hotkey("ctrl", "v")          # atomic paste — reliable for chrome://
        time.sleep(0.25)
    else:
        # Fallback: type character by character with generous interval
        # Note: pyautogui.typewrite skips non-ASCII; use write() for safety
        pya.write(url, interval=0.05)
        time.sleep(0.2)

    # ── Navigate ──────────────────────────────────────────────────────────────────
    pya.press("enter")
    print(f"   [URL via {_method}]: {url}")


async def _ensure_chrome_open() -> tuple[bool, str]:
    """
    Launch Chrome only when not already running.
    Returns (success, status_tag).
    status_tag == 'chrome_already_running' means no launch was needed.
    """
    if _is_chrome_running():
        return True, "chrome_already_running"

    chrome_path = _find_chrome()
    if not chrome_path:
        return False, "Chrome nahi mila. Google Chrome install karein."

    try:
        subprocess.Popen(
            [chrome_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(2.5)   # fresh launch needs time
        return True, chrome_path
    except Exception as e:
        return False, f"Chrome launch fail: {e}"


async def _run_hotkey(*keys: str) -> tuple[bool, str]:
    """Send any keyboard shortcut to Chrome."""
    try:
        pya = _get_pyautogui()
    except RuntimeError as e:
        return False, str(e)

    ok, tag = await _ensure_chrome_open()
    if not ok:
        return False, tag

    # Brief pause — less if Chrome was already open
    await asyncio.sleep(0.3 if tag == "chrome_already_running" else 0.6)

    if len(keys) == 1:
        await asyncio.to_thread(pya.press, keys[0])
    else:
        await asyncio.to_thread(pya.hotkey, *keys)

    return True, f"Hotkey: {' + '.join(keys)}"


async def _open_url(url: str, new_tab: bool = True) -> tuple[bool, str]:
    """Navigate Chrome to any URL using clipboard paste (with typewrite fallback)."""
    try:
        pya = _get_pyautogui()
    except RuntimeError as e:
        return False, str(e)

    ok, tag = await _ensure_chrome_open()
    if not ok:
        return False, tag

    await asyncio.sleep(0.3 if tag == "chrome_already_running" else 0.6)

    try:
        await asyncio.to_thread(_paste_url_to_addressbar, pya, url, new_tab)
        return True, f"Navigated → {url}"
    except Exception as e:
        return False, f"Navigation fail: {e}"


def _read_history_db(sql: str, params: tuple = ()) -> list[tuple]:
    """Read Chrome's SQLite history DB via a temp copy (safe while Chrome is open)."""
    db_path = _HISTORY_PATHS.get(_get_os(), "")
    if not db_path or not os.path.isfile(db_path):
        return []
    tmp = f"/tmp/chrome_hist_{int(time.time())}.db"
    try:
        shutil.copy2(db_path, tmp)
        conn = sqlite3.connect(tmp)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows
    except Exception:
        return []
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _build_report(
    action: str, success: bool, detail: str,
    items: list[dict] | None, elapsed: float, note: str = "",
) -> str:
    icon = "✅" if success else "❌"
    lines = [
        f"{icon} CHROME CONTROLLER — {action.upper()}",
        f"   ⏱ {round(elapsed, 3)}s  |  🖥 {_get_os()}  |  "
        f"🗓 {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        "─" * 60,
        f"\n📌 {detail}",
    ]
    if note:
        lines.append(f"   ℹ️  {note}")
    if items:
        lines.append(f"\n📋 {len(items)} result(s):")
        lines.append("─" * 60)
        for i, it in enumerate(items, 1):
            lines.append(f"\n{i}. {it.get('title', 'No Title')}")
            lines.append(f"   🔗 {it.get('url', '')}")
            if "last_visit" in it:
                lines.append(
                    f"   📅 {it['last_visit']}  |  "
                    f"👁 Visits: {it.get('visit_count', '?')}"
                )
    lines += ["\n" + "─" * 60, f"ℹ️  {len(_CHROME_ACTIONS)} actions available."]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════
#  MAIN FUNCTION TOOL
# ══════════════════════════════════════════════════════════════════════════════════

@function_tool()
async def control_chrome(
    action: str = "new_tab",
    query: str = "",
    top_n: int = 10,
) -> str:
    """
    Controls Google Chrome with 90+ actions:
    tabs, windows, navigation, zoom, scrolling, bookmarks, search,
    find-in-page, developer tools, screenshots, all chrome:// pages,
    and local history / top-sites reading.

    Args:
        action : Action to perform. Key categories:
                 Tabs/Win  → new_tab, close_tab, reopen_tab, next_tab, prev_tab,
                             tab_1..tab_8, last_tab, duplicate_tab, pin_tab,
                             mute_tab, close_window, incognito, fullscreen,
                             minimize, maximize, new_window
                 Navigate  → navigate(*), go_back, go_forward, reload,
                             hard_reload, stop, home, focus_addressbar
                 Search    → search(*), search_youtube(*), search_maps(*),
                             search_images(*), search_news(*),
                             search_translate(*), search_wikipedia(*),
                             search_reddit(*), search_github(*),
                             find_in_page, find_next, find_prev
                 Zoom/View → zoom_in, zoom_out, zoom_reset, view_source,
                             print_page, save_page, reading_mode
                 Scroll    → scroll_down, scroll_up, scroll_top, scroll_bottom
                 Bookmarks → bookmark_page, bookmark_all_tabs,
                             toggle_bookmarks_bar
                 DevTools  → devtools, devtools_console, devtools_inspector,
                             devtools_network, task_manager, clear_data
                 Screenshot→ screenshot
                 Pages     → settings, downloads, extensions, history,
                             bookmarks_page, flags, passwords, newtab, about,
                             version, gpu, net_internals, crashes, memory,
                             performance, site_settings, accessibility, sync,
                             privacy, appearance, search_engines, startup,
                             languages, system, reset_settings, safety_check,
                             payment_methods, addresses
                 Data      → recent_history, top_sites
                 (* needs query parameter)
        query  : URL for navigate; search term for search_* actions;
                 optional text for find_in_page.
        top_n  : Result count for recent_history/top_sites (1-50, default 10).

    Requirements:
        pip install pyautogui          (required)
        pip install pyperclip          (recommended — more reliable URL paste)
        Linux: sudo apt-get install python3-xlib xclip scrot
    """
    print(f"🔍 Chrome → action='{action}' | query='{query}' | top_n={top_n}")

    action_lower = action.lower().strip()

    if action_lower not in _CHROME_ACTIONS:
        all_actions = "\n   ".join(sorted(_CHROME_ACTIONS.keys()))
        return (
            f"❌ Unknown action: '{action}'\n\n"
            f"✅ Available ({len(_CHROME_ACTIONS)}):\n   {all_actions}"
        )

    top_n = max(1, min(top_n, 50))
    t0 = time.perf_counter()
    success = False
    detail = ""
    items: list[dict] | None = None
    note = ""

    try:
        # ── 1. SIMPLE HOTKEY ACTIONS ──────────────────────────────────────────────
        if action_lower in _HOTKEY_MAP:
            keys = _HOTKEY_MAP[action_lower]
            ok, msg = await _run_hotkey(*keys)
            success = ok
            detail = _CHROME_ACTIONS[action_lower] if ok else msg

        # ── 2. CHROME INTERNAL PAGES (chrome:// URLs) ─────────────────────────────
        elif action_lower in _CHROME_URL_MAP:
            url = _CHROME_URL_MAP[action_lower]
            ok, msg = await _open_url(url, new_tab=True)
            success = ok
            detail = f"Opened {url}" if ok else msg

        # ── 3. NEW WINDOW ─────────────────────────────────────────────────────────
        elif action_lower == "new_window":
            cp = _find_chrome()
            if not cp:
                detail = "Chrome nahi mila. Google Chrome install karein."
            else:
                subprocess.Popen(
                    [cp, "--new-window"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                success = True
                detail = "New Chrome window opened."

        # ── 4. DUPLICATE TAB ──────────────────────────────────────────────────────
        elif action_lower == "duplicate_tab":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                def _dup():
                    pya.hotkey("ctrl", "l")
                    time.sleep(0.3)
                    pya.hotkey("alt", "return")
                await asyncio.to_thread(_dup)
                success = True
                detail = "Tab duplicated (Ctrl+L → Alt+Enter)."

        # ── 5. PIN TAB ────────────────────────────────────────────────────────────
        elif action_lower == "pin_tab":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                def _pin():
                    pya.hotkey("shift", "f10")
                    time.sleep(0.4)
                    pya.press("p")
                await asyncio.to_thread(_pin)
                success = True
                detail = "Pin/unpin via Shift+F10 → P."
                note = "Tab bar focus hona chahiye."

        # ── 6. MUTE TAB ───────────────────────────────────────────────────────────
        elif action_lower == "mute_tab":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                def _mute():
                    pya.hotkey("shift", "f10")
                    time.sleep(0.4)
                    pya.press("m")
                await asyncio.to_thread(_mute)
                success = True
                detail = "Mute/unmute via Shift+F10 → M."

        # ── 7. MINIMIZE ───────────────────────────────────────────────────────────
        elif action_lower == "minimize":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                os_name = _get_os()
                if os_name == "Windows":
                    await asyncio.to_thread(lambda: pya.hotkey("win", "down"))
                elif os_name == "Darwin":
                    await asyncio.to_thread(lambda: pya.hotkey("command", "m"))
                else:
                    await asyncio.to_thread(lambda: pya.hotkey("super", "h"))
                success = True
                detail = "Chrome window minimized."

        # ── 8. MAXIMIZE ───────────────────────────────────────────────────────────
        elif action_lower == "maximize":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                os_name = _get_os()
                if os_name == "Windows":
                    await asyncio.to_thread(lambda: pya.hotkey("win", "up"))
                elif os_name == "Darwin":
                    await asyncio.to_thread(lambda: pya.hotkey("ctrl", "command", "f"))
                else:
                    await asyncio.to_thread(lambda: pya.hotkey("super", "up"))
                success = True
                detail = "Chrome window maximized."

        # ── 9. NAVIGATE (any URL) ─────────────────────────────────────────────────
        elif action_lower == "navigate":
            if not query.strip():
                return "❌ 'navigate' ke liye query mein URL dena zaroori hai.\n   Example: query='https://example.com'"
            url = query.strip()
            if not url.startswith(("http://", "https://", "chrome://", "file://")):
                url = "https://" + url
            ok, msg = await _open_url(url, new_tab=True)
            success = ok
            detail = f"Navigated → {url}" if ok else msg

        # ── 10. ALL SEARCH ACTIONS ────────────────────────────────────────────────
        elif action_lower in (
            "search", "search_youtube", "search_maps", "search_images",
            "search_news", "search_translate", "search_wikipedia",
            "search_reddit", "search_github",
        ):
            if not query.strip():
                return f"❌ '{action_lower}' ke liye 'query' parameter required hai."
            q = query.replace(" ", "+")
            qe = query.replace(" ", "%20")
            url_map = {
                "search":           f"https://www.google.com/search?q={q}",
                "search_youtube":   f"https://www.youtube.com/results?search_query={q}",
                "search_maps":      f"https://www.google.com/maps/search/{q}",
                "search_images":    f"https://www.google.com/search?tbm=isch&q={q}",
                "search_news":      f"https://news.google.com/search?q={q}",
                "search_translate": f"https://translate.google.com/?text={qe}",
                "search_wikipedia": f"https://en.wikipedia.org/wiki/Special:Search?search={q}",
                "search_reddit":    f"https://www.reddit.com/search/?q={q}",
                "search_github":    f"https://github.com/search?q={q}",
            }
            ok, msg = await _open_url(url_map[action_lower], new_tab=True)
            success = ok
            detail = f"{action_lower}: \"{query}\"" if ok else msg

        # ── 11. FIND IN PAGE ──────────────────────────────────────────────────────
        elif action_lower == "find_in_page":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                def _find():
                    pya.hotkey("ctrl", "f")
                    time.sleep(0.4)
                    if query.strip():
                        _paste_url_to_addressbar.__globals__  # side-effect free
                        try:
                            import pyperclip
                            pyperclip.copy(query.strip())
                            pya.hotkey("ctrl", "v")
                        except ImportError:
                            pya.write(query.strip(), interval=0.05)
                        time.sleep(0.2)
                        pya.press("enter")
                await asyncio.to_thread(_find)
                success = True
                detail = f"Find-in-page" + (f": \"{query}\"" if query else " (empty).")

        # ── 12. DEVTOOLS NETWORK ──────────────────────────────────────────────────
        elif action_lower == "devtools_network":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.3)
                def _net():
                    pya.hotkey("ctrl", "shift", "i")
                    time.sleep(0.8)
                    pya.hotkey("ctrl", "shift", "p")
                    time.sleep(0.4)
                    pya.write("network", interval=0.06)
                    time.sleep(0.25)
                    pya.press("enter")
                await asyncio.to_thread(_net)
                success = True
                detail = "DevTools → Network panel (via Command Palette)."

        # ── 13. SCREENSHOT ────────────────────────────────────────────────────────
        elif action_lower == "screenshot":
            pya = _get_pyautogui()
            ok, tag = await _ensure_chrome_open()
            if not ok:
                detail = tag
            else:
                await asyncio.sleep(0.4)
                os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(_SCREENSHOT_DIR, f"chrome_{ts}.png")
                def _snap():
                    img = pya.screenshot()
                    img.save(filepath)
                await asyncio.to_thread(_snap)
                success = True
                detail = f"Screenshot saved → {filepath}"
                note = f"Folder: {_SCREENSHOT_DIR}"

        # ── 14. RECENT HISTORY ────────────────────────────────────────────────────
        elif action_lower == "recent_history":
            sql = """
                SELECT url, title, visit_count,
                       datetime(last_visit_time/1000000 - 11644473600,
                                'unixepoch','localtime') AS last_visit
                FROM   urls
                ORDER  BY last_visit_time DESC
                LIMIT  ?
            """
            rows = await asyncio.to_thread(_read_history_db, sql, (top_n,))
            if rows:
                success = True
                detail = f"Recent history: {len(rows)} entries."
                items = [
                    {"title": r[1] or "No Title", "url": r[0],
                     "visit_count": r[2], "last_visit": r[3] or "?"}
                    for r in rows
                ]
            else:
                detail = (
                    "History read nahi ho saka.\n"
                    "   • Chrome open ho toh DB lock rahega\n"
                    "   • Chrome band karke dobara try karein"
                )

        # ── 15. TOP SITES ─────────────────────────────────────────────────────────
        elif action_lower == "top_sites":
            sql = """
                SELECT url, title, visit_count,
                       datetime(last_visit_time/1000000 - 11644473600,
                                'unixepoch','localtime') AS last_visit
                FROM   urls
                ORDER  BY visit_count DESC
                LIMIT  ?
            """
            rows = await asyncio.to_thread(_read_history_db, sql, (top_n,))
            if rows:
                success = True
                detail = f"Top {len(rows)} most visited sites."
                items = [
                    {"title": r[1] or "No Title", "url": r[0],
                     "visit_count": r[2], "last_visit": r[3] or "?"}
                    for r in rows
                ]
            else:
                detail = "Top sites read nahi ho saka. Chrome band karke try karein."

    except RuntimeError as e:
        # pyautogui or pyperclip missing
        success = False
        detail = str(e)
    except Exception as e:
        success = False
        detail = f"Unexpected error: {type(e).__name__}: {e}"

    elapsed = time.perf_counter() - t0
    print(f"{'✅' if success else '❌'} '{action_lower}' → {round(elapsed, 3)}s")
    return _build_report(action_lower, success, detail, items, elapsed, note)