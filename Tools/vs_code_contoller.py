import os
import ssl
import glob
import asyncio
import aiohttp
import subprocess
import time
from pathlib import Path
from livekit.agents import function_tool
import logging
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SSL Fix
# ─────────────────────────────────────────────────────────────────────────────

def _make_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

_SSL_CTX = _make_ssl_context()
def _connector() -> aiohttp.TCPConnector:
    return aiohttp.TCPConnector(ssl=_SSL_CTX)


# ─────────────────────────────────────────────────────────────────────────────
# Translation
# ─────────────────────────────────────────────────────────────────────────────

def is_english(text: str) -> bool:
    try:
        return all(ord(c) < 128 or c.isspace() for c in text)
    except Exception:
        return True

async def _try_google_translate(text: str):
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text}
        async with aiohttp.ClientSession(
            connector=_connector(), timeout=aiohttp.ClientTimeout(total=8)
        ) as s:
            async with s.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if data and data[0]:
                        return "".join(p[0] for p in data[0] if p[0])
    except Exception:
        pass
    return None

async def translate_to_english_free(text: str) -> str:
    if not text.strip() or is_english(text):
        return text
    result = await _try_google_translate(text)
    return result if result else text


# ─────────────────────────────────────────────────────────────────────────────
# Windows VS Code helpers
#
# macOS used:
#   osascript AppleScript          → keyboard shortcuts
#   pbpaste / pbcopy               → clipboard
#   tell application "Code"        → activate window
#
# Windows replacement:
#   pyautogui.hotkey("ctrl", x)    → keyboard shortcuts (ctrl not cmd)
#   pygetwindow                    → find + activate VS Code window
#   pyperclip                      → clipboard read/write
# ─────────────────────────────────────────────────────────────────────────────

import pyautogui
import pyperclip

def _run_cmd(cmd: list, timeout: int = 10) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e:
        return False, str(e)


def _clipboard_read() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""

def _clipboard_write(text: str) -> None:
    try:
        pyperclip.copy(text)
    except Exception:
        pass


def _activate_vscode() -> bool:
    """
    Bring VS Code window to front on Windows.
    Uses pygetwindow to find and activate the VS Code window.
    Returns True if activated, False if VS Code not found.
    """
    try:
        import pygetwindow as gw
        # Find VS Code window — title contains "Visual Studio Code"
        windows = [
            w for w in gw.getAllWindows()
            if "visual studio code" in w.title.lower()
        ]
        if not windows:
            return False
        win = windows[0]
        # Restore if minimized
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        win.activate()
        time.sleep(0.5)
        # Verify activation
        active = gw.getActiveWindow()
        if active and "visual studio code" in active.title.lower():
            return True
        # Retry
        win.activate()
        time.sleep(0.4)
        return True
    except Exception as e:
        logger.error(f"_activate_vscode error: {e}")
        return False


def _hotkey(*keys) -> bool:
    """Send keyboard shortcut via pyautogui."""
    try:
        pyautogui.hotkey(*keys)
        return True
    except Exception as e:
        logger.error(f"_hotkey error: {e}")
        return False


def _press(key: str) -> bool:
    """Press a single key."""
    try:
        pyautogui.press(key)
        return True
    except Exception as e:
        logger.error(f"_press error: {e}")
        return False


def _type_text(text: str, clear_first: bool = False) -> None:
    """
    Type text via clipboard paste.
    Handles special chars, spaces, symbols reliably.
    """
    _clipboard_write(text)
    time.sleep(0.15)
    if clear_first:
        _hotkey("ctrl", "a")
        time.sleep(0.1)
    _hotkey("ctrl", "v")
    time.sleep(0.25)


# ─────────────────────────────────────────────────────────────────────────────
# File finder utility
# ─────────────────────────────────────────────────────────────────────────────

def _find_file(filename: str, search_dir: str = None) -> str | None:
    search_dir = search_dir or os.getcwd()
    direct = os.path.join(search_dir, filename)
    if os.path.exists(direct):
        return direct
    for ext in [".py", ".js", ".ts", ".java", ".cpp", ".c", ".cs", ".go", ".rs", ".swift"]:
        p = os.path.join(search_dir, filename + ext)
        if os.path.exists(p):
            return p
    matches = glob.glob(os.path.join(search_dir, "**", filename), recursive=True)
    return matches[0] if matches else None


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS
# ═════════════════════════════════════════════════════════════════════════════

# ─── 1. Open folder ──────────────────────────────────────────────────────────

@function_tool()
async def vscode_open_folder_new_window(folder_path: str) -> str:
    """Open a folder in a new VS Code window."""
    p = Path(folder_path).expanduser()
    if not p.exists():
        return f"❌ Folder not found: {folder_path}"
    if not p.is_dir():
        return "❌ Path is not a folder."
    ok, err = _run_cmd(["code", "-n", str(p)])
    return f"✅ Opened in new VS Code window: {p}" if ok else f"❌ Error: {err}"


# ─── 2. Open file quick (Ctrl+P) ─────────────────────────────────────────────

@function_tool()
async def vscode_open_file_quick(file_name: str) -> str:
    """Open a file inside current VS Code workspace using quick open (Ctrl+P)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    file_name = await translate_to_english_free(file_name)
    _hotkey("ctrl", "p")              # Ctrl+P = Quick Open
    time.sleep(0.6)
    _hotkey("ctrl", "a")              # Clear existing text
    time.sleep(0.1)
    _type_text(file_name)
    time.sleep(0.5)
    _press("enter")
    time.sleep(0.3)
    return f"✅ Opened file: {file_name}"


# ─── 3. Get current file code ────────────────────────────────────────────────

@function_tool()
async def vscode_explain_current_code() -> str:
    """Read and return all code from the currently active VS Code file."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    original = _clipboard_read()
    _hotkey("ctrl", "a")              # Select All
    time.sleep(0.3)
    _hotkey("ctrl", "c")              # Copy
    time.sleep(0.5)
    code = _clipboard_read()
    _clipboard_write(original)        # Restore clipboard
    if not code.strip():
        return "❌ Could not read code from active file."
    return code


# ─── 4. Get current file path ────────────────────────────────────────────────

@function_tool()
async def vscode_get_current_file_path() -> str:
    """Get the full path of the currently open file in VS Code."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    # Ctrl+K then Ctrl+P = Copy Path of active file
    _hotkey("ctrl", "k")
    time.sleep(0.2)
    _hotkey("ctrl", "p")
    time.sleep(0.5)
    path = _clipboard_read().strip()
    if not path:
        return "❌ Could not detect file path."
    return path


# ─── 5. Replace entire file code ─────────────────────────────────────────────

@function_tool()
async def vscode_replace_code(file_path: str, new_code: str) -> str:
    """Replace the entire content of a file with new code."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"❌ File not found: {file_path}"
    p.write_text(new_code, encoding="utf-8")
    return f"✅ Code replaced in {file_path}"


# ─── 6. Append code to file ──────────────────────────────────────────────────

@function_tool()
async def vscode_append_code(file_path: str, code_to_add: str) -> str:
    """Append code to the end of a file."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"❌ File not found: {file_path}"
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n" + code_to_add)
    return f"✅ Code appended to {file_path}"


# ─── 7. Search project (Ctrl+Shift+F) ────────────────────────────────────────

@function_tool()
async def vscode_search_project(text: str) -> str:
    """Search text across entire VS Code project (Ctrl+Shift+F)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    text = await translate_to_english_free(text)
    _hotkey("ctrl", "shift", "f")     # Ctrl+Shift+F = Global Search
    time.sleep(0.7)
    _hotkey("ctrl", "a")
    time.sleep(0.1)
    _type_text(text)
    time.sleep(0.3)
    return f"✅ Searching '{text}' in project"


# ─── 8. Go to symbol (Ctrl+Shift+O) ──────────────────────────────────────────

@function_tool()
async def vscode_go_to_symbol(symbol_name: str) -> str:
    """Jump to a function/class/symbol in current VS Code file (Ctrl+Shift+O)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    symbol_name = await translate_to_english_free(symbol_name)
    _hotkey("ctrl", "shift", "o")     # Ctrl+Shift+O = Go to Symbol
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    time.sleep(0.1)
    _type_text(symbol_name)
    time.sleep(0.4)
    _press("enter")
    time.sleep(0.3)
    return f"✅ Jumped to symbol: {symbol_name}"


# ─── 9. Format document ──────────────────────────────────────────────────────

@function_tool()
async def vscode_format_code() -> str:
    """Format the current file in VS Code (Ctrl+Shift+P → Format Document)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")     # Ctrl+Shift+P = Command Palette
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    time.sleep(0.1)
    _type_text("Format Document")
    time.sleep(0.5)
    _press("enter")
    return "✅ Formatting current document"


# ─── 10. Install Python packages ─────────────────────────────────────────────

@function_tool()
async def vscode_install_python_packages(packages: str) -> str:
    """Install Python packages in VS Code integrated terminal."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "`")              # Ctrl+` = Toggle Terminal
    time.sleep(1)
    _type_text(f"pip install {packages}")
    _press("enter")
    return f"✅ Installing: {packages}"


# ─── 11. Create virtual environment ──────────────────────────────────────────

@function_tool()
async def vscode_create_venv(env_name: str = "venv") -> str:
    """
    Create and activate a Python venv in VS Code terminal.
    Windows activation uses Scripts\\activate.
    """
    if not _activate_vscode():
        return "❌ VS Code is not running."
    env_name = await translate_to_english_free(env_name)
    _hotkey("ctrl", "`")
    time.sleep(1)
    _type_text(f"python -m venv {env_name}")
    _press("enter")
    time.sleep(2)
    # Windows: Scripts\activate  (NOT bin/activate like macOS)
    _type_text(f"{env_name}\\Scripts\\activate")
    _press("enter")
    return f"✅ venv '{env_name}' created and activated"


# ─── 12. Comment lines ───────────────────────────────────────────────────────

@function_tool()
async def vscode_comment_lines(start_line: int, end_line: int, filename: str) -> str:
    """Comment lines start_line to end_line in given file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    ext = os.path.splitext(file_path)[1].lower()
    prefix = {
        ".py": "#", ".rb": "#", ".sh": "#",
        ".js": "//", ".ts": "//", ".jsx": "//", ".tsx": "//",
        ".java": "//", ".c": "//", ".cpp": "//", ".cs": "//",
        ".go": "//", ".rs": "//", ".swift": "//",
    }.get(ext, "#")
    for i in range(start_line - 1, end_line):
        line     = lines[i]
        stripped = line.lstrip()
        indent   = line[:len(line) - len(stripped)]
        if stripped and not stripped.startswith(prefix):
            lines[i] = f"{indent}{prefix} {stripped}"
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"✅ Lines {start_line}–{end_line} commented in '{filename}'"


# ─── 13. Uncomment lines ─────────────────────────────────────────────────────

@function_tool()
async def vscode_uncomment_lines(start_line: int, end_line: int, filename: str) -> str:
    """Remove comment prefix from lines start_line to end_line."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    import re
    for i in range(start_line - 1, end_line):
        lines[i] = re.sub(r"^(\s*)(#\s?|//\s?)", r"\1", lines[i])
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"✅ Lines {start_line}–{end_line} uncommented in '{filename}'"


# ─── 14. Delete lines ────────────────────────────────────────────────────────

@function_tool()
async def vscode_delete_lines(start_line: int, end_line: int, filename: str) -> str:
    """Delete lines start_line to end_line in given file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    del lines[start_line - 1:end_line]
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"✅ Lines {start_line}–{end_line} deleted from '{filename}'"


# ─── 15. Copy lines ──────────────────────────────────────────────────────────

@function_tool()
async def vscode_copy_lines(start_line: int, end_line: int, filename: str) -> str:
    """Copy lines to clipboard from given file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    _clipboard_write("".join(lines[start_line - 1:end_line]))
    return f"✅ Lines {start_line}–{end_line} copied from '{filename}'"


# ─── 16. Duplicate lines ─────────────────────────────────────────────────────

@function_tool()
async def vscode_duplicate_lines(start_line: int, end_line: int, filename: str) -> str:
    """Duplicate lines start_line to end_line in given file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    duped = lines[start_line - 1:end_line]
    lines[end_line:end_line] = duped
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"✅ Lines {start_line}–{end_line} duplicated in '{filename}'"


# ─── 17. Find & replace ──────────────────────────────────────────────────────

@function_tool()
async def vscode_find_replace(find_text: str, replace_text: str, filename: str) -> str:
    """Find and replace all occurrences in a file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    find_text = await translate_to_english_free(find_text)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(find_text)
    if count == 0:
        return f"❌ '{find_text}' not found in file."
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.replace(find_text, replace_text))
    return f"✅ Replaced '{find_text}' → '{replace_text}' ({count} times) in '{filename}'"


# ─── 18. Git commit & push ───────────────────────────────────────────────────

@function_tool()
async def vscode_git_commit_push(message: str) -> str:
    """git add . → commit → push in VS Code terminal."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    message = await translate_to_english_free(message)
    _hotkey("ctrl", "`")
    time.sleep(1.2)
    cmds = [
        ("git add .", 1.0),
        (f'git commit -m "{message}"', 1.5),
        ("git push", 3.0),
    ]
    for cmd_text, wait in cmds:
        _type_text(cmd_text)
        _press("enter")
        time.sleep(wait)
    return f"✅ Git commit & push done: '{message}'"


# ─── 19. Open recent (Ctrl+R) ────────────────────────────────────────────────

@function_tool()
async def vscode_open_recent() -> str:
    """Open recent files/projects list in VS Code (Ctrl+R)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "r")
    return "✅ Opened recent files/projects"


# ─── 20. Go to line (Ctrl+G) ─────────────────────────────────────────────────

@function_tool()
async def vscode_go_to_line(line_number: int) -> str:
    """Jump to a specific line number in VS Code (Ctrl+G)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "g")
    time.sleep(0.5)
    _hotkey("ctrl", "a")
    time.sleep(0.1)
    _type_text(str(line_number))
    time.sleep(0.2)
    _press("enter")
    return f"✅ Jumped to line {line_number}"


# ─── 21. Save file ───────────────────────────────────────────────────────────

@function_tool()
async def vscode_save_file() -> str:
    """Save the current file in VS Code (Ctrl+S)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "s")
    return "✅ File saved"


# ─── 22. Save all files ──────────────────────────────────────────────────────

@function_tool()
async def vscode_save_all() -> str:
    """Save all open files in VS Code (Ctrl+K S)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "k")
    time.sleep(0.1)
    pyautogui.press("s")
    return "✅ All files saved"


# ─── 23. Close current tab ───────────────────────────────────────────────────

@function_tool()
async def vscode_close_tab() -> str:
    """Close current editor tab in VS Code (Ctrl+W)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "w")
    return "✅ Tab closed"


# ─── 24. Split editor ────────────────────────────────────────────────────────

@function_tool()
async def vscode_split_editor() -> str:
    """Split the editor into two panels (Ctrl+\\)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "\\")
    return "✅ Editor split"


# ─── 25. Toggle sidebar ──────────────────────────────────────────────────────

@function_tool()
async def vscode_toggle_sidebar() -> str:
    """Show/hide the VS Code sidebar (Ctrl+B)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "b")
    return "✅ Sidebar toggled"


# ─── 26. Toggle terminal ─────────────────────────────────────────────────────

@function_tool()
async def vscode_toggle_terminal() -> str:
    """Show/hide the integrated terminal (Ctrl+`)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "`")
    return "✅ Terminal toggled"


# ─── 27. Run file ────────────────────────────────────────────────────────────

@function_tool()
async def vscode_run_file() -> str:
    """Run the current file using VS Code Run button (Ctrl+F5)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "f5")
    return "✅ Running current file"


# ─── 28. Debug file ──────────────────────────────────────────────────────────

@function_tool()
async def vscode_debug_file() -> str:
    """Start debugging current file (F5)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _press("f5")
    return "✅ Debug started"


# ─── 29. Open extensions panel ───────────────────────────────────────────────

@function_tool()
async def vscode_open_extensions() -> str:
    """Open Extensions panel in VS Code (Ctrl+Shift+X)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "x")
    return "✅ Extensions panel opened"


# ─── 30. Install VS Code extension ───────────────────────────────────────────

@function_tool()
async def vscode_install_extension(extension_id: str) -> str:
    """Install a VS Code extension by ID."""
    ok, out = _run_cmd(["code", "--install-extension", extension_id], timeout=60)
    if ok:
        return f"✅ Extension installed: {extension_id}"
    return f"❌ Install failed: {out}"


# ─── 31. List installed extensions ───────────────────────────────────────────

@function_tool()
async def vscode_list_extensions() -> str:
    """List all installed VS Code extensions."""
    ok, out = _run_cmd(["code", "--list-extensions"])
    if ok and out:
        lines = out.strip().split("\n")
        return f"📦 {len(lines)} extensions installed:\n" + "\n".join(f"  • {l}" for l in lines)
    return "❌ Could not list extensions."


# ─── 32. Open settings ───────────────────────────────────────────────────────

@function_tool()
async def vscode_open_settings() -> str:
    """Open VS Code Settings (Ctrl+,)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", ",")
    return "✅ Settings opened"


# ─── 33. Open keyboard shortcuts ─────────────────────────────────────────────

@function_tool()
async def vscode_open_keybindings() -> str:
    """Open VS Code Keyboard Shortcuts (Ctrl+K Ctrl+S)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "k")
    time.sleep(0.2)
    _hotkey("ctrl", "s")
    return "✅ Keyboard shortcuts opened"


# ─── 34. Zen mode ────────────────────────────────────────────────────────────

@function_tool()
async def vscode_zen_mode() -> str:
    """Toggle Zen Mode in VS Code (Ctrl+K Z)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "k")
    time.sleep(0.2)
    pyautogui.press("z")
    return "✅ Zen mode toggled"


# ─── 35. New terminal ────────────────────────────────────────────────────────

@function_tool()
async def vscode_new_terminal() -> str:
    """Create a new integrated terminal in VS Code (Ctrl+Shift+`)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "`")
    return "✅ New terminal created"


# ─── 36. Run terminal command ────────────────────────────────────────────────

@function_tool()
async def vscode_run_terminal_command(command: str) -> str:
    """Run any shell command in VS Code integrated terminal."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    command = await translate_to_english_free(command)
    _hotkey("ctrl", "`")
    time.sleep(0.8)
    _type_text(command)
    _press("enter")
    return f"✅ Ran: {command}"


# ─── 37. Reveal in explorer ──────────────────────────────────────────────────

@function_tool()
async def vscode_reveal_in_explorer() -> str:
    """Reveal current file in VS Code Explorer sidebar."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")
    time.sleep(0.5)
    _type_text("Reveal in Explorer View")
    _press("enter")
    return "✅ File revealed in Explorer"


# ─── 38. Rename symbol ───────────────────────────────────────────────────────

@function_tool()
async def vscode_rename_symbol(new_name: str) -> str:
    """Rename the symbol under cursor in VS Code (F2)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    new_name = await translate_to_english_free(new_name)
    _press("f2")
    time.sleep(0.4)
    _type_text(new_name)
    _press("enter")
    return f"✅ Symbol renamed to '{new_name}'"


# ─── 39. Insert line ─────────────────────────────────────────────────────────

@function_tool()
async def vscode_insert_line(direction: str = "below") -> str:
    """Insert blank line above (Ctrl+Shift+Enter) or below (Ctrl+Enter)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    if direction == "above":
        _hotkey("ctrl", "shift", "enter")
    else:
        _hotkey("ctrl", "enter")
    return f"✅ New line inserted {direction}"


# ─── 40. Move line ───────────────────────────────────────────────────────────

@function_tool()
async def vscode_move_line(direction: str = "down") -> str:
    """Move current line up (Alt+Up) or down (Alt+Down)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    if direction == "up":
        _hotkey("alt", "up")
    else:
        _hotkey("alt", "down")
    return f"✅ Line moved {direction}"


# ─── 41. Select all occurrences ──────────────────────────────────────────────

@function_tool()
async def vscode_select_all_occurrences() -> str:
    """Select all occurrences of current selection (Ctrl+Shift+L)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "l")
    return "✅ All occurrences selected"


# ─── 42. Fold/unfold code ────────────────────────────────────────────────────

@function_tool()
async def vscode_fold_code(action: str = "fold") -> str:
    """Fold (Ctrl+Shift+[) or unfold (Ctrl+Shift+]) code blocks."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    if action == "fold":
        _hotkey("ctrl", "shift", "[")
    else:
        _hotkey("ctrl", "shift", "]")
    return f"✅ Code {action}ed"


# ─── 43. Toggle line comment ─────────────────────────────────────────────────

@function_tool()
async def vscode_toggle_line_comment() -> str:
    """Toggle line comment on selected lines (Ctrl+/)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "/")
    return "✅ Line comment toggled"


# ─── 44. Toggle block comment ────────────────────────────────────────────────

@function_tool()
async def vscode_toggle_block_comment() -> str:
    """Toggle block comment (Ctrl+Shift+A)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "a")
    return "✅ Block comment toggled"


# ─── 45. Undo / Redo ─────────────────────────────────────────────────────────

@function_tool()
async def vscode_undo() -> str:
    """Undo last action (Ctrl+Z)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "z")
    return "✅ Undone"

@function_tool()
async def vscode_redo() -> str:
    """Redo last undone action (Ctrl+Y)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "y")              # Windows: Ctrl+Y (not Ctrl+Shift+Z)
    return "✅ Redone"


# ─── 46. Git operations ──────────────────────────────────────────────────────

@function_tool()
async def vscode_git_status() -> str:
    """Run git status in VS Code terminal."""
    return await vscode_run_terminal_command("git status")

@function_tool()
async def vscode_git_pull() -> str:
    """Run git pull in VS Code terminal."""
    return await vscode_run_terminal_command("git pull")

@function_tool()
async def vscode_git_log() -> str:
    """Show last 10 git commits in VS Code terminal."""
    return await vscode_run_terminal_command("git log --oneline -10")


# ─── 47. New file ────────────────────────────────────────────────────────────

@function_tool()
async def vscode_new_file() -> str:
    """Create a new untitled file in VS Code (Ctrl+N)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "n")
    return "✅ New file created"


# ─── 48. Open file by path ───────────────────────────────────────────────────

@function_tool()
async def vscode_open_file_by_path(file_path: str) -> str:
    """Open a specific file in VS Code by its full or relative path."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"❌ File not found: {file_path}"
    ok, err = _run_cmd(["code", str(p)])
    return f"✅ Opened: {p}" if ok else f"❌ Error: {err}"


# ═════════════════════════════════════════════════════════════════════════════
# ADVANCED TOOLS  (filesystem-based — same on Windows & macOS)
# ═════════════════════════════════════════════════════════════════════════════

@function_tool()
async def vscode_read_lines(start_line: int, end_line: int, filename: str) -> str:
    """Read and return specific lines from a file."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if not (1 <= start_line <= end_line <= total):
        return f"❌ Invalid range. File has {total} lines."
    return f"📄 Lines {start_line}–{end_line}:\n\n{''.join(lines[start_line-1:end_line])}"


@function_tool()
async def vscode_insert_code_at_line(filename: str, line_number: int, code: str) -> str:
    """Insert code at a specific line number. Existing content shifts down."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not (1 <= line_number <= len(lines) + 1):
        return f"❌ Invalid line {line_number}. File has {len(lines)} lines."
    lines.insert(line_number - 1, code if code.endswith("\n") else code + "\n")
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"✅ Code inserted at line {line_number} in '{filename}'"


@function_tool()
async def vscode_file_stats(filename: str) -> str:
    """Get line count, word count, functions, classes, imports for a file."""
    
    import os
    import re as _re

    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # ---- Basic Stats ----
    lines = content.splitlines()
    empty_lines = sum(1 for l in lines if not l.strip())
    ext = os.path.splitext(file_path)[1]
    size_kb = os.path.getsize(file_path) / 1024

    # ---- Regex Patterns (OUTSIDE f-string) ----
    func_pattern = r'^\s*def\s+\w+'
    class_pattern = r'^\s*class\s+\w+'
    import_pattern = r'^\s*(import|from)\s+'

    # ---- Counts ----
    func_count = len(_re.findall(func_pattern, content, _re.MULTILINE))
    class_count = len(_re.findall(class_pattern, content, _re.MULTILINE))
    import_count = len(_re.findall(import_pattern, content, _re.MULTILINE))

    # ---- Final Output ----
    return (
        f"📊 File Stats: {filename}\n"
        f"─────────────────────\n"
        f"📁 Path       : {file_path}\n"
        f"📐 Size       : {size_kb:.1f} KB\n"
        f"📝 Lines      : {len(lines)} ({empty_lines} empty)\n"
        f"💬 Words      : {len(content.split())}\n"
        f"🔤 Characters : {len(content)}\n"
        f"🔧 Functions  : {func_count}\n"
        f"🏗️  Classes    : {class_count}\n"
        f"📦 Imports    : {import_count}\n"
        f"🔖 Extension  : {ext}"
    )


@function_tool()
async def vscode_search_in_file(filename: str, search_text: str) -> str:
    """Search for text in a file and return matching lines with numbers."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    search_text = await translate_to_english_free(search_text)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    matches = [(i+1, l.rstrip()) for i, l in enumerate(lines) if search_text.lower() in l.lower()]
    if not matches:
        return f"❌ '{search_text}' not found in '{filename}'"
    result = f"🔍 '{search_text}' found {len(matches)} time(s):\n\n"
    for lineno, line in matches[:20]:
        result += f"  Line {lineno:4}: {line}\n"
    if len(matches) > 20:
        result += f"\n  ... and {len(matches)-20} more"
    return result


@function_tool()
async def vscode_list_symbols(filename: str) -> str:
    """List all functions and classes defined in a file."""
    import re as _re
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    ext = os.path.splitext(file_path)[1].lower()
    PATTERNS = {
        ".py":  [("class", r"^class\s+(\w+)"), ("function", r"^\s*(?:async\s+)?def\s+(\w+)")],
        ".js":  [("function", r"function\s+(\w+)"), ("class", r"^class\s+(\w+)")],
        ".ts":  [("function", r"function\s+(\w+)"), ("class", r"^(?:export\s+)?class\s+(\w+)")],
        ".java":[("class", r"class\s+(\w+)"), ("method", r"(?:public|private|protected)\s+\w+\s+(\w+)\s*\(")],
        ".go":  [("function", r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)")],
    }
    patterns = PATTERNS.get(ext, [("function", r"function\s+(\w+)")])
    results  = []
    for i, line in enumerate(lines, 1):
        for sym_type, pat in patterns:
            m = _re.search(pat, line)
            if m:
                name = next((g for g in m.groups() if g), None)
                if name:
                    results.append((i, sym_type, name))
                    break
    if not results:
        return f"❌ No symbols found in '{filename}'"
    out = f"🔍 Symbols in '{filename}' ({len(results)}):\n\n"
    for lineno, sym_type, name in results:
        out += f"  {'🏗️' if sym_type=='class' else '🔧'} Line {lineno:4}: {sym_type:10} {name}\n"
    return out


@function_tool()
async def vscode_rename_variable(filename: str, old_name: str, new_name: str) -> str:
    """Rename a variable/function across entire file (word-boundary safe)."""
    import re as _re
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r'\b' + _re.escape(old_name) + r'\b'
    count   = len(_re.findall(pattern, content))
    if count == 0:
        return f"❌ '{old_name}' not found in '{filename}'"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(_re.sub(pattern, new_name, content))
    return f"✅ Renamed '{old_name}' → '{new_name}' ({count} occurrences)"


@function_tool()
async def vscode_add_import(filename: str, import_statement: str) -> str:
    """Add an import to the top of a file (checks for duplicates)."""
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    if import_statement in content:
        return f"ℹ️ Import already exists in '{filename}'"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(import_statement + "\n" + content)
    return f"✅ Added: {import_statement}"


@function_tool()
async def vscode_diff_files(file1: str, file2: str) -> str:
    """Show diff between two files in VS Code diff editor."""
    path1, path2 = _find_file(file1), _find_file(file2)
    if not path1: return f"❌ File '{file1}' not found."
    if not path2: return f"❌ File '{file2}' not found."
    ok, err = _run_cmd(["code", "--diff", path1, path2])
    return f"✅ Diff opened: {file1} vs {file2}" if ok else f"❌ {err}"


@function_tool()
async def vscode_run_python_file(filename: str) -> str:
    """Run a Python file in VS Code terminal with python."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    file_path = _find_file(filename)
    if not file_path:
        return f"❌ File '{filename}' not found."
    return await vscode_run_terminal_command(f"python {file_path}")


@function_tool()
async def vscode_create_file_with_content(filename: str, content: str, location: str = "") -> str:
    """Create a new file with given content and open it in VS Code."""
    base = Path(location).expanduser() if location else Path(os.getcwd())
    base.mkdir(parents=True, exist_ok=True)
    if "." not in filename:
        filename += ".txt"
    file_path = base / filename
    file_path.write_text(content, encoding="utf-8")
    ok, err = _run_cmd(["code", str(file_path)])
    return f"✅ Created and opened: {file_path}" if ok else f"✅ Created: {file_path}"


@function_tool()
async def vscode_zoom(direction: str = "in") -> str:
    """Zoom VS Code in (Ctrl+=), out (Ctrl+-), or reset (Ctrl+0)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    key = {"in": "=", "out": "-", "reset": "0"}.get(direction, "=")
    _hotkey("ctrl", key)
    return f"✅ Zoomed {direction}"


@function_tool()
async def vscode_toggle_word_wrap() -> str:
    """Toggle word wrap in VS Code editor (Alt+Z)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("alt", "z")              # Windows: Alt+Z (macOS: Option+Z)
    return "✅ Word wrap toggled"


@function_tool()
async def vscode_run_tests(test_command: str = "pytest") -> str:
    """Run tests in VS Code terminal (pytest / npm test / etc.)."""
    return await vscode_run_terminal_command(test_command)


@function_tool()
async def vscode_show_problems() -> str:
    """Open Problems panel (Ctrl+Shift+M)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "m")
    return "✅ Problems panel opened"


@function_tool()
async def vscode_show_output() -> str:
    """Open Output panel (Ctrl+Shift+U)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "u")
    return "✅ Output panel opened"


@function_tool()
async def vscode_add_cursor_above() -> str:
    """Add cursor above current line (Ctrl+Alt+Up)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "alt", "up")     # Windows: Ctrl+Alt+Up (macOS: Cmd+Option+Up)
    return "✅ Cursor added above"


@function_tool()
async def vscode_add_cursor_below() -> str:
    """Add cursor below current line (Ctrl+Alt+Down)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "alt", "down")   # Windows: Ctrl+Alt+Down
    return "✅ Cursor added below"


@function_tool()
async def vscode_git_new_branch(branch_name: str) -> str:
    """Create and switch to a new git branch."""
    branch_name = await translate_to_english_free(branch_name)
    return await vscode_run_terminal_command(f"git checkout -b {branch_name}")


@function_tool()
async def vscode_git_switch_branch(branch_name: str) -> str:
    """Switch to an existing git branch."""
    branch_name = await translate_to_english_free(branch_name)
    return await vscode_run_terminal_command(f"git checkout {branch_name}")


@function_tool()
async def vscode_git_branches() -> str:
    """List all git branches."""
    return await vscode_run_terminal_command("git branch -a")


@function_tool()
async def vscode_insert_snippet(language: str, snippet_type: str) -> str:
    """Insert a code snippet via command palette."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    _type_text("Insert Snippet")
    time.sleep(0.5)
    _press("enter")
    time.sleep(0.5)
    _type_text(snippet_type)
    time.sleep(0.4)
    return f"✅ Snippet picker opened for: {snippet_type}"


@function_tool()
async def vscode_open_live_server() -> str:
    """Start Live Server for current HTML file (requires Live Server extension)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    _type_text("Live Server: Open with Live Server")
    time.sleep(0.5)
    _press("enter")
    return "✅ Live Server started"


@function_tool()
async def vscode_peek_definition() -> str:
    """Peek definition of symbol under cursor (Alt+F12)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("alt", "f12")            # Windows: Alt+F12 (macOS: Option+F12)
    return "✅ Peek definition opened"


@function_tool()
async def vscode_go_to_definition() -> str:
    """Go to definition of symbol under cursor (F12)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _press("f12")
    return "✅ Jumped to definition"


@function_tool()
async def vscode_trigger_intellisense() -> str:
    """Trigger IntelliSense/autocomplete (Ctrl+Space)."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "space")
    return "✅ IntelliSense triggered"


@function_tool()
async def vscode_toggle_minimap() -> str:
    """Toggle the minimap via command palette."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    _type_text("View: Toggle Minimap")
    time.sleep(0.5)
    _press("enter")
    return "✅ Minimap toggled"


@function_tool()
async def vscode_change_language(language: str) -> str:
    """Change language mode of current file."""
    if not _activate_vscode():
        return "❌ VS Code is not running."
    _hotkey("ctrl", "shift", "p")
    time.sleep(0.6)
    _hotkey("ctrl", "a")
    _type_text("Change Language Mode")
    time.sleep(0.5)
    _press("enter")
    time.sleep(0.5)
    _hotkey("ctrl", "a")
    _type_text(language)
    time.sleep(0.4)
    _press("enter")
    return f"✅ Language changed to {language}"