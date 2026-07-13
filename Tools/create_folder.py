"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        ADVANCED FILE SYSTEM + TRANSLATION TOOLKIT — LiveKit Edition         ║
║  Smart Explorer Control • Multi-API Translation • Batch Ops • File Search   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp
import pyautogui
from livekit.agents import function_tool

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fs_tools")

# ─── Constants ────────────────────────────────────────────────────────────────
MAX_BATCH_ITEMS   = 50
MAX_SEARCH_DEPTH  = 10
REQUEST_TIMEOUT   = 10   # seconds for translation APIs
EXPLORER_TIMEOUT  = 5    # seconds for PowerShell calls

# ─── File type templates ──────────────────────────────────────────────────────
FILE_TEMPLATES: Dict[str, str] = {
    ".txt":  "Created: {ts}\n\n",
    ".md":   "# {name}\n\n> Created: {ts}\n\n## Notes\n\n",
    ".py":   '"""\n{name}\nCreated: {ts}\n"""\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
    ".js":   "// {name}\n// Created: {ts}\n\n",
    ".html": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <title>{name}</title>\n</head>\n<body>\n\n</body>\n</html>\n",
    ".css":  "/* {name} | Created: {ts} */\n\n",
    ".json": '{{\n  "_created": "{ts}",\n  "_name": "{name}"\n}}\n',
    ".csv":  "column1,column2,column3\n",
    ".bat":  "@echo off\nREM {name}\nREM Created: {ts}\n\n",
    ".sh":   "#!/bin/bash\n# {name}\n# Created: {ts}\n\n",
    ".xml":  '<?xml version="1.0" encoding="UTF-8"?>\n<!-- {name} | {ts} -->\n<root>\n\n</root>\n',
    ".yaml": "# {name}\n# Created: {ts}\n\n",
    ".sql":  "-- {name}\n-- Created: {ts}\n\n",
    ".cpp":  "// {name}\n// Created: {ts}\n\n#include <iostream>\nusing namespace std;\n\nint main() {{\n    return 0;\n}}\n",
    ".java": "// {name}\n// Created: {ts}\n\npublic class {classname} {{\n    public static void main(String[] args) {{\n    }}\n}}\n",
}

# ─── Supported archive types ──────────────────────────────────────────────────
ARCHIVE_EXTS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".7z"}


# ═══════════════════════════════════════════════════════════════════════════════
#  RESULT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FSResult:
    success: bool
    message: str
    path: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


# ═══════════════════════════════════════════════════════════════════════════════
#  RETRY DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

def async_retry(attempts: int = 3, delays: List[float] = [1, 2, 4]):
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if i == attempts - 1:
                        raise
                    await asyncio.sleep(delays[min(i, len(delays) - 1)])
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
#  TRANSLATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

BASIC_DICT: Dict[str, str] = {
    # Common actions
    "लिखो": "write", "बनाओ": "make", "करो": "do", "दिखाओ": "show",
    "खोलो": "open", "बंद": "close", "भेजो": "send", "सेव": "save",
    "डिलीट": "delete", "कॉपी": "copy", "मूव": "move", "रिनेम": "rename",
    # Nouns
    "फोल्डर": "folder", "फ़ाइल": "file", "फाइल": "file", "डेस्कटॉप": "desktop",
    "दस्तावेज़": "documents", "डाउनलोड": "downloads", "चित्र": "pictures",
    "संगीत": "music", "वीडियो": "videos", "नाम": "name", "नया": "new",
    # Tech
    "कंप्यूटर": "computer", "मोबाइल": "mobile", "इंटरनेट": "internet",
    "टेक्नोलॉजी": "technology", "विज्ञान": "science", "प्रोग्राम": "program",
    # Greetings / common
    "नमस्ते": "hello", "धन्यवाद": "thank you", "कृपया": "please",
    "हाँ": "yes", "नहीं": "no", "ठीक": "ok", "अच्छा": "good",
    "मेरा": "my", "तेरा": "your", "क्या": "what", "कब": "when",
    "कहाँ": "where", "क्यों": "why", "कैसे": "how",
}

def _is_english(text: str) -> bool:
    """Return True if text contains only ASCII + spaces."""
    return all(ord(c) < 128 or c.isspace() for c in text)

def _basic_fallback(text: str) -> str:
    words = text.split()
    out = [BASIC_DICT.get(w.strip(".,!?;:").lower(), w) for w in words]
    result = " ".join(out)
    return result[0].upper() + result[1:] if result else result

async def _try_google(text: str, session: aiohttp.ClientSession) -> Optional[str]:
    try:
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text}
        async with session.get("https://translate.googleapis.com/translate_a/single", params=params) as r:
            if r.status == 200:
                data = await r.json()
                parts = [p[0] for p in data[0] if p[0]]
                return "".join(parts)
    except Exception as e:
        logger.debug(f"Google translate error: {e}")
    return None

async def _try_mymemory(text: str, session: aiohttp.ClientSession) -> Optional[str]:
    try:
        params = {"q": text, "langpair": "auto|en"}
        async with session.get("https://api.mymemory.translated.net/get", params=params) as r:
            if r.status == 200:
                data = await r.json()
                if data.get("responseStatus") == 200:
                    return data["responseData"]["translatedText"]
    except Exception as e:
        logger.debug(f"MyMemory error: {e}")
    return None

async def _try_libretranslate(text: str, session: aiohttp.ClientSession) -> Optional[str]:
    instances = [
        "https://libretranslate.de/translate",
        "https://translate.argosopentech.com/translate",
    ]
    payload = {"q": text, "source": "auto", "target": "en", "format": "text"}
    headers = {"Content-Type": "application/json"}
    for url in instances:
        try:
            async with session.post(url, data=json.dumps(payload), headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    t = data.get("translatedText")
                    if t:
                        return t
        except Exception as e:
            logger.debug(f"LibreTranslate {url} error: {e}")
    return None

async def translate_to_english(text: str) -> str:
    """
    Translate any language to English.
    Pipeline: Google → MyMemory → LibreTranslate → basic dict fallback.
    Returns original text unchanged if it is already English.
    """
    if not text.strip() or _is_english(text):
        return text

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for fn in (_try_google, _try_mymemory, _try_libretranslate):
            result = await fn(text, session)
            if result and result.strip():
                logger.info(f"🌐 Translated: '{text[:30]}' → '{result[:30]}'")
                return result.strip()

    logger.warning("All translation APIs failed, using basic dict fallback")
    return _basic_fallback(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  WINDOWS FILE EXPLORER CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

# ── PowerShell helpers ────────────────────────────────────────────────────────
_PS_GET_ALL_EXPLORER_PATHS = """
$shell = New-Object -ComObject Shell.Application
$shell.Windows() | Where-Object {
    $_.FullName -like '*explorer.exe*' -and $_.LocationURL -like 'file:*'
} | ForEach-Object {
    try { $_.Document.Folder.Self.Path } catch {}
}
"""

_PS_GET_ACTIVE_EXPLORER_PATH = """
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@
$hwnd = [Win32]::GetForegroundWindow()
$shell = New-Object -ComObject Shell.Application
$win = $shell.Windows() | Where-Object { $_.HWND -eq $hwnd } | Select-Object -First 1
if ($win) {
    try { $win.Document.Folder.Self.Path } catch {}
} else {
    # fallback: first open explorer
    $first = $shell.Windows() | Where-Object { $_.LocationURL -like 'file:*' } | Select-Object -First 1
    if ($first) { try { $first.Document.Folder.Self.Path } catch {} }
}
"""

_PS_REFRESH_EXPLORER = """
$shell = New-Object -ComObject Shell.Application
foreach ($w in $shell.Windows()) {
    try { if ($w.FullName -like '*explorer.exe*') { $w.Refresh() } } catch {}
}
"""

_PS_OPEN_PATH = """
param([string]$p)
Start-Process explorer.exe -ArgumentList $p
"""

_PS_SELECT_FILE = """
param([string]$p)
$shell = New-Object -ComObject Shell.Application
$dir   = Split-Path $p -Parent
$name  = Split-Path $p -Leaf
foreach ($w in $shell.Windows()) {
    try {
        if ($w.Document.Folder.Self.Path -eq $dir) {
            $item = $w.Document.Folder.Items() | Where-Object { $_.Name -eq $name }
            if ($item) { $w.Document.SelectItem($item, 1) }
        }
    } catch {}
}
"""

def _run_ps(script: str, args: List[str] = [], timeout: int = EXPLORER_TIMEOUT) -> Optional[str]:
    """Run a PowerShell inline script synchronously. Returns stdout or None."""
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script] + args
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        return out if out else None
    except Exception as e:
        logger.debug(f"PowerShell error: {e}")
        return None

async def _run_ps_async(script: str, args: List[str] = [], timeout: int = EXPLORER_TIMEOUT) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _run_ps(script, args, timeout))


class ExplorerController:
    """All Windows File Explorer interactions via PowerShell COM."""

    async def get_active_path(self) -> Optional[str]:
        """Return path of the foreground (active) Explorer window."""
        raw = await _run_ps_async(_PS_GET_ACTIVE_EXPLORER_PATH)
        if raw and os.path.exists(raw):
            return raw
        return None

    async def get_all_paths(self) -> List[str]:
        """Return paths of all open Explorer windows."""
        raw = await _run_ps_async(_PS_GET_ALL_EXPLORER_PATHS)
        if not raw:
            return []
        paths = [p.strip() for p in raw.splitlines() if p.strip() and os.path.exists(p.strip())]
        return paths

    async def refresh(self):
        await _run_ps_async(_PS_REFRESH_EXPLORER)

    async def open_path(self, path: str):
        """Open a folder in File Explorer using subprocess (most reliable)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(["explorer.exe", path])
        )

    async def select_item(self, full_path: str):
        """Highlight/select a specific file or folder inside an open Explorer."""
        script = f"""
        $shell = New-Object -ComObject Shell.Application
        $dir   = '{Path(full_path).parent}'
        $name  = '{Path(full_path).name}'
        foreach ($w in $shell.Windows()) {{
            try {{
                if ($w.Document.Folder.Self.Path -eq $dir) {{
                    $item = $w.Document.Folder.Items() | Where-Object {{ $_.Name -eq $name }}
                    if ($item) {{ $w.Document.SelectItem($item, 1) }}
                }}
            }} catch {{}}
        }}
        """
        await _run_ps_async(script)


explorer_ctrl = ExplorerController()



# ═══════════════════════════════════════════════════════════════════════════════
#  SMART PATH RESOLVER — auto-finds best location without user intervention
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_LOCATIONS: List[str] = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path.home()),
]

async def _resolve_best_path(hint: Optional[str] = None) -> Tuple[str, str]:
    """
    Intelligently find the best working directory without requiring user action.

    Priority:
      1. hint path (if provided and valid)
      2. Active File Explorer window
      3. Any open File Explorer window
      4. Auto-open Desktop in Explorer, wait, then re-read
      5. Desktop path directly (no Explorer COM needed)

    Returns:
        Tuple[str, str]: (resolved_path, source_description)
    """
    # 1. Explicit hint
    if hint and os.path.isdir(hint):
        return hint, "provided path"

    # 2. Active Explorer window
    active = await explorer_ctrl.get_active_path()
    if active:
        return active, "active File Explorer window"

    # 3. Any open Explorer window
    all_paths = await explorer_ctrl.get_all_paths()
    if all_paths:
        return all_paths[0], "open File Explorer window"

    # 4. Auto-open Desktop in Explorer and wait briefly
    desktop = str(Path.home() / "Desktop")
    if not os.path.exists(desktop):
        desktop = str(Path.home())

    logger.info(f"No Explorer open — auto-launching Explorer at: {desktop}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: subprocess.Popen(["explorer.exe", desktop])
    )
    await asyncio.sleep(2.0)  # give Explorer time to open

    reopened = await explorer_ctrl.get_active_path()
    if reopened:
        return reopened, "auto-opened File Explorer (Desktop)"

    # 5. Last resort: use Desktop path directly
    return desktop, "Desktop (direct path)"


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE / FOLDER HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize_name(name: str) -> str:
    """Remove characters illegal in Windows/Linux file names."""
    illegal = r'[<>:"/\\|?*\x00-\x1f]'
    return re.sub(illegal, "_", name).strip(". ")

def _render_template(ext: str, name: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    classname = re.sub(r"[^A-Za-z0-9]", "", name.title()) or "Main"
    tpl = FILE_TEMPLATES.get(ext, "Created: {ts}\n")
    return tpl.format(ts=ts, name=name, classname=classname)

def _humansize(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def _file_info(p: Path) -> str:
    try:
        stat = p.stat()
        size = _humansize(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        kind = "📁 Folder" if p.is_dir() else f"📄 File ({p.suffix or 'no ext'})"
        return f"{kind} | {size} | Modified: {mtime}"
    except Exception:
        return "?"

def _dir_tree(path: Path, depth: int = 2, _prefix: str = "") -> List[str]:
    """Generate an ASCII directory tree up to `depth` levels."""
    if depth == 0:
        return []
    lines = []
    try:
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return [f"{_prefix}  [Permission denied]"]
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        icon = "📁" if entry.is_dir() else "📄"
        lines.append(f"{_prefix}{connector}{icon} {entry.name}")
        if entry.is_dir() and depth > 1:
            ext_prefix = _prefix + ("    " if i == len(entries) - 1 else "│   ")
            lines.extend(_dir_tree(entry, depth - 1, ext_prefix))
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
#  FUNCTION TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def create_here(
    item_name: str,
    item_type: str = "folder",
    open_after: bool = False,
) -> str:
    """
    Create a file or folder in the currently active File Explorer window.
    Supports 15+ file types with pre-filled templates. Names in any language
    are auto-translated to English before creation.

    Args:
        item_name (str):     Name of the item (any language accepted).
        item_type (str):     'folder' | 'file' | any extension like 'py','html','md'
        open_after (bool):   If True, opens the created item after creation.

    Returns:
        str: Detailed status with full path and directory tree snippet.
    """
    # Auto-resolve best path — opens Explorer automatically if needed
    explorer_path, path_source = await _resolve_best_path()

    # Translate name
    item_name_en = await translate_to_english(item_name.strip())
    item_name_en = _sanitize_name(item_name_en)
    if not item_name_en:
        return "❌ Item name is empty after sanitisation."

    base_path = Path(explorer_path)

    # ── Resolve type & extension ───────────────────────────────────────────────
    item_type = item_type.lower().strip().lstrip(".")
    is_folder = item_type in ("folder", "dir", "directory")

    if is_folder:
        target = base_path / item_name_en
        if target.exists():
            return f"ℹ️ Folder already exists:\n📍 {target}"
        target.mkdir(parents=True)
        result_msg = f"✅ Folder '{item_name_en}' created!"

    else:
        # Determine extension
        if "." in item_name_en:
            ext = Path(item_name_en).suffix.lower()
            stem = Path(item_name_en).stem
        else:
            ext = f".{item_type}" if item_type not in ("file", "text", "txt") else ".txt"
            stem = item_name_en

        filename = stem + ext
        target = base_path / filename

        if target.exists():
            return f"ℹ️ File already exists:\n📍 {target}"

        content = _render_template(ext, stem)
        target.write_text(content, encoding="utf-8")
        result_msg = f"✅ File '{filename}' created!"

    # Refresh & optionally open
    await explorer_ctrl.refresh()
    await explorer_ctrl.select_item(str(target))

    if open_after:
        loop = asyncio.get_event_loop()
        if target.is_dir():
            # Open folder in File Explorer window
            await loop.run_in_executor(
                None, lambda: subprocess.Popen(["explorer.exe", str(target)])
            )
        else:
            # Open file in its parent folder with the file highlighted
            await loop.run_in_executor(
                None, lambda: subprocess.Popen(["explorer.exe", "/select,", str(target)])
            )

    # Show mini tree
    tree_lines = _dir_tree(base_path, depth=1)
    tree_str   = "\n".join(tree_lines[:12]) + ("\n  …" if len(tree_lines) > 12 else "")

    return (
        f"{result_msg}\n"
        f"{'📁' if is_folder else '📄'} Name      : {item_name_en}"
        + (f"  (translated from '{item_name}')" if item_name != item_name_en else "") + "\n"
        f"📍 Full path  : {target}\n"
        f"📂 In folder  : {explorer_path}\n"
        f"📌 Location   : {path_source}\n\n"
        f"📋 Folder contents:\n{tree_str}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def create_batch(
    items: str,
    base_path: Optional[str] = None,
    item_type: str = "folder",
) -> str:
    """
    Create multiple files or folders at once from a comma-separated list.
    Uses the active Explorer window if base_path is not provided.

    Args:
        items (str):            Comma-separated names, e.g. "Work, Personal, Backup"
        base_path (str|None):   Target directory. Defaults to active Explorer path.
        item_type (str):        'folder' | file extension like 'py','txt','md'

    Returns:
        str: Per-item creation report.
    """
    if not base_path:
        base_path, _ = await _resolve_best_path()
    if not base_path or not os.path.exists(base_path):
        return "❌ Could not determine a valid base path."

    raw_names = [n.strip() for n in items.split(",") if n.strip()]
    if not raw_names:
        return "❌ No item names provided."
    if len(raw_names) > MAX_BATCH_ITEMS:
        return f"❌ Too many items ({len(raw_names)}). Max: {MAX_BATCH_ITEMS}."

    results: List[str] = []
    is_folder = item_type.lower() in ("folder", "dir", "directory")
    ext = "" if is_folder else ("." + item_type.lstrip("."))

    for raw in raw_names:
        name_en = await translate_to_english(raw)
        name_en = _sanitize_name(name_en)
        target  = Path(base_path) / (name_en if is_folder else name_en + ext)

        try:
            if target.exists():
                results.append(f"⚠️ Already exists : {target.name}")
                continue
            if is_folder:
                target.mkdir(parents=True)
            else:
                target.write_text(_render_template(ext, name_en), encoding="utf-8")
            results.append(f"✅ Created : {target.name}")
        except PermissionError:
            results.append(f"❌ Permission denied : {target.name}")
        except Exception as e:
            results.append(f"❌ Error ({e}) : {target.name}")

    await explorer_ctrl.refresh()

    summary = "\n".join(results)
    ok  = sum(1 for r in results if r.startswith("✅"))
    err = len(results) - ok
    return (
        f"📦 Batch creation complete!\n"
        f"✅ Created: {ok}  ⚠️/❌ Skipped/Failed: {err}\n"
        f"📂 Location: {base_path}\n\n"
        f"{summary}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def rename_item(old_name: str, new_name: str, base_path: Optional[str] = None) -> str:
    """
    Rename a file or folder. Searches active Explorer window if base_path omitted.
    New name is auto-translated to English.

    Args:
        old_name (str):          Current name of the item.
        new_name (str):          Desired new name (any language).
        base_path (str|None):    Directory containing the item.

    Returns:
        str: Status message.
    """
    if not base_path:
        base_path, _ = await _resolve_best_path()

    old_path = Path(base_path) / old_name
    if not old_path.exists():
        return f"❌ '{old_name}' not found in {base_path}"

    new_name_en = _sanitize_name(await translate_to_english(new_name.strip()))
    if not new_name_en:
        return "❌ New name is empty after sanitisation."

    # Preserve extension if renaming a file and new_name has no ext
    if old_path.is_file() and "." not in new_name_en:
        new_name_en += old_path.suffix

    new_path = Path(base_path) / new_name_en
    if new_path.exists():
        return f"❌ '{new_name_en}' already exists in {base_path}"

    old_path.rename(new_path)
    await explorer_ctrl.refresh()
    await explorer_ctrl.select_item(str(new_path))

    return (
        f"✅ Renamed successfully!\n"
        f"📝 Old : {old_name}\n"
        f"📝 New : {new_name_en}"
        + (f"  (translated from '{new_name}')" if new_name != new_name_en else "") + "\n"
        f"📍 Path: {new_path}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def move_item(
    item_name: str,
    destination: str,
    source_path: Optional[str] = None,
    copy: bool = False,
) -> str:
    """
    Move (or copy) a file or folder to a destination directory.
    Source defaults to active Explorer window.

    Args:
        item_name (str):        Name of the file/folder to move.
        destination (str):      Destination directory path.
        source_path (str|None): Source directory. Defaults to active Explorer path.
        copy (bool):            If True, copies instead of moving.

    Returns:
        str: Status with source → destination details.
    """
    if not source_path:
        source_path, _ = await _resolve_best_path()

    src = Path(source_path) / item_name
    dst_dir = Path(destination)

    if not src.exists():
        return f"❌ '{item_name}' not found in '{source_path}'"
    if not dst_dir.exists():
        try:
            dst_dir.mkdir(parents=True)
        except Exception as e:
            return f"❌ Cannot create destination: {e}"

    dst = dst_dir / src.name
    if dst.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = dst_dir / f"{src.stem}_{ts}{src.suffix}"

    action = "Copied" if copy else "Moved"
    try:
        if copy:
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
        else:
            shutil.move(str(src), str(dst))
    except PermissionError:
        return f"❌ Permission denied while {'copying' if copy else 'moving'} '{item_name}'"
    except Exception as e:
        return f"❌ Operation failed: {e}"

    await explorer_ctrl.refresh()

    size = _humansize(dst.stat().st_size) if dst.is_file() else "—"
    return (
        f"✅ {action} successfully!\n"
        f"📄 Item : {item_name}\n"
        f"📤 From : {source_path}\n"
        f"📥 To   : {dst}\n"
        f"📦 Size : {size}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def delete_item(
    item_name: str,
    base_path: Optional[str] = None,
    confirm: bool = False,
) -> str:
    """
    Delete a file or folder. Requires confirm=True as a safety gate.

    Args:
        item_name (str):        Name of item to delete.
        base_path (str|None):   Directory. Defaults to active Explorer path.
        confirm (bool):         Must be True to actually delete.

    Returns:
        str: Status or confirmation prompt.
    """
    if not confirm:
        return (
            f"⚠️ Deletion requires confirmation!\n"
            f"Call again with confirm=True to delete '{item_name}'.\n"
            f"⚠️ This action CANNOT be undone."
        )

    if not base_path:
        base_path, _ = await _resolve_best_path()

    target = Path(base_path) / item_name
    if not target.exists():
        return f"❌ '{item_name}' not found in '{base_path}'"

    kind  = "folder" if target.is_dir() else "file"
    try:
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
    except PermissionError:
        return f"❌ Permission denied deleting '{item_name}'"
    except Exception as e:
        return f"❌ Delete failed: {e}"

    await explorer_ctrl.refresh()
    return (
        f"🗑️ {kind.title()} '{item_name}' deleted.\n"
        f"📂 From: {base_path}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def search_files(
    query: str,
    search_path: Optional[str] = None,
    extensions: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """
    Recursively search for files/folders by name pattern.
    Starts from active Explorer window or a given path.

    Args:
        query (str):             Search term (any language; auto-translated).
        search_path (str|None):  Root directory to search. Defaults to active Explorer.
        extensions (str|None):   Comma-separated extensions to filter, e.g. 'py,js,txt'
        max_results (int):       Maximum number of results to return (default 20).

    Returns:
        str: Formatted list of matching paths with file info.
    """
    if not search_path:
        search_path, _ = await _resolve_best_path()
    if not search_path or not os.path.exists(search_path):
        return "❌ Could not determine a valid search directory."

    query_en = (await translate_to_english(query)).lower()
    exts: Optional[set] = None
    if extensions:
        exts = {("." + e.strip().lstrip(".")).lower() for e in extensions.split(",")}

    matches: List[Path] = []
    root = Path(search_path)

    def _search():
        for p in root.rglob("*"):
            try:
                if query_en in p.name.lower():
                    if exts is None or p.suffix.lower() in exts:
                        matches.append(p)
                        if len(matches) >= max_results:
                            return
            except PermissionError:
                continue

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _search)

    if not matches:
        return f"🔍 No results found for '{query}' in:\n{search_path}"

    rows = [f"{'📁' if m.is_dir() else '📄'} {m.name}\n   📍 {m.parent}\n   {_file_info(m)}" for m in matches]
    result_str = "\n\n".join(rows)
    return (
        f"🔍 Found {len(matches)} result(s) for '{query}' (→ '{query_en}'):\n"
        f"📂 Searched: {search_path}\n\n"
        f"{result_str}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def show_folder_tree(
    path: Optional[str] = None,
    depth: int = 3,
) -> str:
    """
    Display an ASCII directory tree for any folder.
    Defaults to the active Explorer window path.

    Args:
        path (str|None):  Root folder. Defaults to active Explorer path.
        depth (int):      Tree depth (1–6). Default 3.

    Returns:
        str: Formatted directory tree with item count summary.
    """
    if not path:
        path, _ = await _resolve_best_path()
    if not path or not os.path.exists(path):
        return "❌ Could not determine a valid folder path."

    depth = max(1, min(depth, 6))
    root  = Path(path)

    try:
        entries = list(root.iterdir())
    except PermissionError:
        return f"❌ Permission denied: {path}"

    tree_lines = _dir_tree(root, depth=depth)
    total_dirs  = sum(1 for e in entries if e.is_dir())
    total_files = sum(1 for e in entries if e.is_file())

    header = f"📂 {root.name}/\n"
    body   = "\n".join(tree_lines[:100])
    footer = "\n  …" if len(tree_lines) > 100 else ""
    stats  = f"\n\n📊 {total_dirs} folders | {total_files} files (top level)"

    return header + body + footer + stats


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def zip_items(
    items: str,
    zip_name: str,
    base_path: Optional[str] = None,
) -> str:
    """
    Compress one or more files/folders into a ZIP archive in the same directory.

    Args:
        items (str):            Comma-separated file/folder names to include.
        zip_name (str):         Name of the output ZIP (without .zip is fine).
        base_path (str|None):   Source directory. Defaults to active Explorer path.

    Returns:
        str: ZIP creation status with size info.
    """
    if not base_path:
        base_path, _ = await _resolve_best_path()

    names = [n.strip() for n in items.split(",") if n.strip()]
    if not names:
        return "❌ No items specified."

    if not zip_name.lower().endswith(".zip"):
        zip_name += ".zip"
    zip_path = Path(base_path) / _sanitize_name(zip_name)

    missing = [n for n in names if not (Path(base_path) / n).exists()]
    if missing:
        return f"❌ Items not found: {', '.join(missing)}"

    def _do_zip():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in names:
                src = Path(base_path) / name
                if src.is_file():
                    zf.write(src, src.name)
                elif src.is_dir():
                    for f in src.rglob("*"):
                        zf.write(f, f.relative_to(Path(base_path)))

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _do_zip)
    except Exception as e:
        return f"❌ ZIP creation failed: {e}"

    await explorer_ctrl.refresh()
    size = _humansize(zip_path.stat().st_size)

    return (
        f"🗜️ ZIP created successfully!\n"
        f"📦 Archive : {zip_name}\n"
        f"📁 Contents: {', '.join(names)}\n"
        f"💾 Size    : {size}\n"
        f"📍 Path    : {zip_path}"
    )


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def open_path_in_explorer(path: str) -> str:
    """
    Open any folder path in a new File Explorer window.

    Args:
        path (str): Absolute folder path to open.

    Returns:
        str: Status message.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"❌ Path does not exist: {path}"
    if not resolved.is_dir():
        resolved = resolved.parent

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: subprocess.Popen(["explorer.exe", str(resolved)])
    )
    return f"📂 Opened in File Explorer:\n{resolved}"


# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def get_explorer_info() -> str:
    """
    Report all currently open File Explorer windows and their paths.

    Returns:
        str: List of open Explorer paths with folder stats.
    """
    active = await explorer_ctrl.get_active_path()
    all_paths = await explorer_ctrl.get_all_paths()

    if not all_paths:
        return "ℹ️ No File Explorer windows are currently open."

    rows: List[str] = []
    for p in all_paths:
        flag = " ← ACTIVE" if p == active else ""
        try:
            contents = list(Path(p).iterdir())
            dirs  = sum(1 for c in contents if c.is_dir())
            files = sum(1 for c in contents if c.is_file())
            rows.append(f"📂 {p}{flag}\n   {dirs} folders | {files} files")
        except Exception:
            rows.append(f"📂 {p}{flag}")

    return "🗂️ Open Explorer Windows:\n\n" + "\n\n".join(rows)

# ──────────────────────────────────────────────────────────────────────────────

@function_tool()
async def open_folder(path: str) -> str:
    """
    Open any folder in Windows File Explorer. Works 100% — never opens Notepad.
    If the path is a file, opens its parent folder with the file highlighted.

    Args:
        path (str): Folder or file path to open in Explorer.

    Returns:
        str: Status message.
    """
    resolved = Path(path).expanduser().resolve()

    if not resolved.exists():
        return f"❌ Path does not exist: {path}"

    loop = asyncio.get_event_loop()

    if resolved.is_dir():
        # Open the folder directly in Explorer
        await loop.run_in_executor(
            None, lambda: subprocess.Popen(["explorer.exe", str(resolved)])
        )
        return f"📂 Folder opened in File Explorer:\n{resolved}"
    else:
        # Open parent folder with the file selected/highlighted
        await loop.run_in_executor(
            None, lambda: subprocess.Popen(["explorer.exe", "/select,", str(resolved)])
        )
        return f"📂 Opened in File Explorer (file highlighted):\n{resolved}"


@function_tool()
async def open_common_folder(location: str) -> str:
    """
    Quickly open common Windows folders in File Explorer by name.

    Args:
        location (str): One of — desktop, documents, downloads, pictures,
                        music, videos, home, appdata, temp, system

    Returns:
        str: Status message with the opened path.
    """
    loc = location.lower().strip()

    known: Dict[str, Path] = {
        "desktop":   Path.home() / "Desktop",
        "documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "pictures":  Path.home() / "Pictures",
        "music":     Path.home() / "Music",
        "videos":    Path.home() / "Videos",
        "home":      Path.home(),
        "appdata":   Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")),
        "temp":      Path(os.environ.get("TEMP", Path.home() / "AppData" / "Local" / "Temp")),
        "system":    Path("C:/Windows/System32"),
    }

    # Also handle Hindi/translated names
    aliases: Dict[str, str] = {
        "डेस्कटॉप": "desktop", "दस्तावेज़": "documents", "डाउनलोड": "downloads",
        "चित्र": "pictures", "संगीत": "music", "वीडियो": "videos",
    }
    if loc in aliases:
        loc = aliases[loc]

    target = known.get(loc)
    if not target:
        options = ", ".join(known.keys())
        return f"❌ Unknown location '{location}'.\nAvailable: {options}"

    if not target.exists():
        return f"❌ Folder does not exist on this system: {target}"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: subprocess.Popen(["explorer.exe", str(target)])
    )
    return f"📂 Opened '{loc}' in File Explorer:\n{target}"