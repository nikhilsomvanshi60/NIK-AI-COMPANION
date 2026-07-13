"""
Nova AI — Universal File & Folder Finder
==========================================
Sirf naam bolo — poore system mein dhundhke khol dega.
Files, folders, dono support. Fuzzy matching, smart ranking.
"""

import os
import re
import time
import asyncio
import aiohttp
import subprocess
from pathlib import Path
from difflib import SequenceMatcher

from livekit.agents import function_tool


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSLATION  (same as your other tools)
# ─────────────────────────────────────────────────────────────────────────────

def _is_english(text: str) -> bool:
    try:
        return all(ord(c) < 128 or c.isspace() for c in text)
    except Exception:
        return True


async def _google_translate(text: str) -> str | None:
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    if data and data[0]:
                        return "".join(p[0] for p in data[0] if p[0])
    except Exception:
        pass
    return None


async def _mymemory_translate(text: str) -> str | None:
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": "auto|en"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("responseStatus") == 200:
                        return data["responseData"]["translatedText"]
    except Exception:
        pass
    return None


_FALLBACK = {
    "डाउनलोड": "downloads", "दस्तावेज़": "documents", "चित्र": "pictures",
    "फ़ोटो": "photos", "वीडियो": "videos", "संगीत": "music",
    "डेस्कटॉप": "desktop", "फ़ाइल": "file", "फोल्डर": "folder",
    "खोलो": "open", "ढूंढो": "find", "नाम": "name",
}


def _fallback_translate(text: str) -> str:
    return " ".join(_FALLBACK.get(w.strip(".,!?;:").lower(), w) for w in text.split())


async def _translate(text: str) -> str:
    if not text.strip() or _is_english(text):
        return text
    return (
        await _google_translate(text)
        or await _mymemory_translate(text)
        or _fallback_translate(text)
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SMART FOLDER SHORTCUTS
# ─────────────────────────────────────────────────────────────────────────────

HOME = Path.home()

QUICK_FOLDERS: dict[str, Path] = {
    "desktop":   HOME / "Desktop",
    "downloads": HOME / "Downloads",
    "documents": HOME / "Documents",
    "pictures":  HOME / "Pictures",
    "photos":    HOME / "Pictures",
    "images":    HOME / "Pictures",
    "videos":    HOME / "Videos",
    "music":     HOME / "Music",
    "onedrive":  HOME / "OneDrive",
    "appdata":   Path(os.environ.get("APPDATA", HOME / "AppData/Roaming")),
    "temp":      Path(os.environ.get("TEMP", "C:/Windows/Temp")),
    "program files": Path("C:/Program Files"),
    "windows":   Path("C:/Windows"),
}

# Drives to search (Windows)
def _get_search_drives() -> list[Path]:
    drives = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{letter}:/")
        if p.exists():
            drives.append(p)
    return drives if drives else [HOME]


# ─────────────────────────────────────────────────────────────────────────────
#  EXTENSION GROUPS
# ─────────────────────────────────────────────────────────────────────────────

EXT_GROUPS: dict[str, list[str]] = {
    "pdf":    [".pdf"],
    "word":   [".doc", ".docx"],
    "excel":  [".xls", ".xlsx", ".csv"],
    "ppt":    [".ppt", ".pptx"],
    "image":  [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "video":  [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"],
    "audio":  [".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"],
    "code":   [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp",
               ".c", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".json",
               ".xml", ".yaml", ".yml", ".sql"],
    "text":   [".txt", ".md", ".log", ".ini", ".cfg", ".conf"],
    "zip":    [".zip", ".rar", ".7z", ".tar", ".gz"],
    "exe":    [".exe", ".msi", ".bat", ".cmd"],
    "any":    [],
}

# Folders to skip (they're slow/useless to search)
SKIP_DIRS = {
    "$recycle.bin", "system volume information", "windows",
    "program files (x86)", "programdata", "perflogs",
    "node_modules", "__pycache__", ".git", "appdata",
}


# ─────────────────────────────────────────────────────────────────────────────
#  FUZZY MATCH SCORER
# ─────────────────────────────────────────────────────────────────────────────

def _score(query: str, name: str) -> float:
    """
    Returns 0.0–1.0 relevance score.
    Exact match = 1.0, starts-with = 0.9, contains = 0.7, fuzzy = ratio.
    """
    q = query.lower().strip()
    n = name.lower()
    stem = Path(n).stem   # filename without extension

    if q == n or q == stem:
        return 1.0
    if stem.startswith(q) or n.startswith(q):
        return 0.9
    if q in stem or q in n:
        return 0.75
    # Word-level: all query words present in name?
    words = q.split()
    if len(words) > 1 and all(w in n for w in words):
        return 0.70
    # Fuzzy
    ratio = SequenceMatcher(None, q, stem).ratio()
    return ratio if ratio > 0.45 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  CORE SEARCH ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _search(
    query: str,
    search_root: Path | None,
    find_type: str,          # "file" | "folder" | "any"
    file_type: str,          # key from EXT_GROUPS
    max_results: int,
    max_depth: int,
) -> list[tuple[float, Path]]:
    """
    Recursive search. Returns sorted list of (score, path).
    """
    allowed_ext = EXT_GROUPS.get(file_type, [])
    roots = [search_root] if search_root else _get_search_drives()
    results: list[tuple[float, Path]] = []

    for root in roots:
        _walk(root, query, find_type, allowed_ext, results, max_results, max_depth, 0)
        if len(results) >= max_results:
            break

    # Sort by score desc, then path length asc (prefer shallower)
    results.sort(key=lambda x: (-x[0], len(str(x[1]))))
    return results[:max_results]


def _walk(
    current: Path,
    query: str,
    find_type: str,
    allowed_ext: list[str],
    results: list,
    max_results: int,
    max_depth: int,
    depth: int,
):
    if depth > max_depth or len(results) >= max_results:
        return
    try:
        for item in current.iterdir():
            if len(results) >= max_results:
                return

            name_lower = item.name.lower()

            # Skip system/hidden dirs
            if item.is_dir() and name_lower in SKIP_DIRS:
                continue
            if item.name.startswith("."):
                continue

            # Score this item
            score = _score(query, item.name)

            if score > 0:
                # Apply type filter
                if find_type == "folder" and not item.is_dir():
                    pass  # don't add
                elif find_type == "file" and not item.is_file():
                    pass
                else:
                    # Apply extension filter
                    if allowed_ext and item.is_file():
                        if item.suffix.lower() not in allowed_ext:
                            score = 0
                    if score > 0:
                        results.append((score, item))

            # Recurse into directories
            if item.is_dir():
                _walk(item, query, find_type, allowed_ext,
                      results, max_results, max_depth, depth + 1)

    except (PermissionError, OSError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  OPEN HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _open_path(path: Path):
    """Open file or folder in the default app / Explorer."""
    try:
        os.startfile(str(path))
    except Exception:
        try:
            subprocess.Popen(["explorer", str(path)])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN TOOL
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def find_and_open(
    name: str,
    search_in: str = "",
    find_type: str = "any",
    file_type: str = "any",
    open_result: bool = True,
    max_results: int = 5,
    deep_search: bool = False,
) -> str:
    """
    Poore system mein koi bhi file ya folder dhundhke khol deta hai.
    Sirf naam bolo — baaki sab sambhal lega.

    Args:
        name        : Jo dhundhna hai uska naam ya part of naam.
                      Hindi mein bhi bol sakte ho.
                      Examples: "resume", "project report", "मेरी फ़ोटो", "budget 2024"

        search_in   : Kahan dhundhna hai (optional — khali chodo to poora system).
                      Smart shortcuts: "downloads", "documents", "desktop",
                                       "pictures", "videos", "music", "onedrive"
                      Ya full path: "C:/Users/Raj/Projects"
                      Khali chodo → poore system mein dhundhega.

        find_type   : Kya dhundhna hai:
                      "any"    → file aur folder dono (default)
                      "file"   → sirf files
                      "folder" → sirf folders

        file_type   : File ka type filter (optional):
                      "any" | "pdf" | "word" | "excel" | "ppt" |
                      "image" | "video" | "audio" | "code" | "text" | "zip" | "exe"

        open_result : True → best match automatically khul jaayega (default).
                      False → sirf list dikhayega, khelga nahi.

        max_results : Kitne results dikhane hain (1–20). Default: 5.

        deep_search : False → fast search, common folders + 4 levels deep (default).
                      True  → slow but thorough, 8 levels deep, poore drives scan.

    Returns:
        Best match opened + list of all matches found.

    Examples (agent ke liye):
        find_and_open("resume")
        find_and_open("budget", search_in="documents", file_type="excel")
        find_and_open("project alpha", find_type="folder")
        find_and_open("family trip", search_in="pictures", file_type="image")
        find_and_open("मेरी रिपोर्ट", file_type="pdf")
    """
    # ── 0. Translate query ────────────────────────────────────────────────────
    query_raw = name.strip()
    query = await _translate(query_raw)
    query = query.strip().lower()

    if not query:
        return "❌ Kuch toh naam batao dhundhne ke liye."

    # ── 1. Resolve search root ────────────────────────────────────────────────
    search_root: Path | None = None

    if search_in.strip():
        si = (await _translate(search_in)).strip().lower()

        if si in QUICK_FOLDERS:
            search_root = QUICK_FOLDERS[si]
        else:
            p = Path(search_in).expanduser().resolve()
            if p.exists() and p.is_dir():
                search_root = p
            else:
                return f"❌ Search folder nahi mila: '{search_in}'"

    # ── 2. Set depth ──────────────────────────────────────────────────────────
    max_depth = 8 if deep_search else 4

    # For quick folders (Downloads, Desktop etc.) always go deeper
    if search_root and search_root in QUICK_FOLDERS.values():
        max_depth = max(max_depth, 5)

    # ── 3. Run search ─────────────────────────────────────────────────────────
    max_results = max(1, min(max_results, 20))

    # Run in executor to keep async loop free
    loop = asyncio.get_event_loop()
    results: list[tuple[float, Path]] = await loop.run_in_executor(
        None,
        _search,
        query,
        search_root,
        find_type.lower(),
        file_type.lower(),
        max_results,
        max_depth,
    )

    # ── 4. Handle no results ──────────────────────────────────────────────────
    if not results:
        scope = f"'{search_root}'" if search_root else "poore system"
        suggestion = "\n💡 Tip: deep_search=True se aur jagah dhundhega." if not deep_search else ""
        return (
            f"❌ '{query_raw}' naam ki koi bhi "
            f"{'file' if find_type == 'file' else 'folder' if find_type == 'folder' else 'file/folder'} "
            f"nahi mili {scope} mein.{suggestion}"
        )

    # ── 5. Open best match ────────────────────────────────────────────────────
    best_score, best_path = results[0]

    if open_result:
        _open_path(best_path)

    # ── 6. Build response ─────────────────────────────────────────────────────
    item_type = "📁 Folder" if best_path.is_dir() else "📄 File"
    opened_msg = "khol diya ✅" if open_result else "mila ✅"

    lines = [
        f"🔍 '{query_raw}' dhundhne par {len(results)} result(s) mile:\n",
        f"{item_type} {opened_msg}: {best_path.name}",
        f"📍 Location: {best_path.parent}",
        f"📊 Match score: {round(best_score * 100)}%",
    ]

    if len(results) > 1:
        lines.append(f"\n{'─'*40}")
        lines.append(f"Baaki {len(results)-1} match(es):")
        for score, path in results[1:]:
            icon = "📁" if path.is_dir() else "📄"
            lines.append(f"  {icon} {path.name}  ({round(score*100)}%)  →  {path.parent}")

    if not open_result:
        lines.append("\n💡 open_result=True karoge to best match automatically khulega.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  BONUS: LIST FOLDER CONTENTS
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def list_folder(
    folder: str = "desktop",
    show_hidden: bool = False,
) -> str:
    """
    Kisi bhi folder ka content dikhata hai (files + subfolders list).

    Args:
        folder     : Folder naam ya path. Smart shortcuts: desktop/downloads/documents/pictures/videos/music
        show_hidden: Hidden files bhi dikhane hain? Default: False.

    Returns:
        Folder contents with file sizes and types.
    """
    # Resolve
    si = (await _translate(folder.strip())).strip().lower()
    if si in QUICK_FOLDERS:
        target = QUICK_FOLDERS[si]
    else:
        target = Path(folder).expanduser().resolve()

    if not target.exists():
        return f"❌ Folder nahi mila: '{folder}'"
    if not target.is_dir():
        return f"❌ Yeh file hai, folder nahi: '{folder}'"

    try:
        items = list(target.iterdir())
    except PermissionError:
        return f"❌ Permission nahi hai: {target}"

    if not show_hidden:
        items = [i for i in items if not i.name.startswith(".")]

    folders = sorted([i for i in items if i.is_dir()], key=lambda x: x.name.lower())
    files   = sorted([i for i in items if i.is_file()], key=lambda x: x.name.lower())

    def _size(path: Path) -> str:
        try:
            b = path.stat().st_size
            for unit in ["B", "KB", "MB", "GB"]:
                if b < 1024:
                    return f"{b:.1f} {unit}"
                b /= 1024
            return f"{b:.1f} TB"
        except Exception:
            return "?"

    lines = [f"📂 {target}\n{'─'*50}"]
    lines.append(f"📁 Folders ({len(folders)}):")
    for f in folders:
        lines.append(f"   📁 {f.name}/")

    lines.append(f"\n📄 Files ({len(files)}):")
    for f in files:
        lines.append(f"   📄 {f.name}  [{_size(f)}]")

    lines.append(f"\n{'─'*50}")
    lines.append(f"Total: {len(folders)} folders, {len(files)} files")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  BONUS: OPEN SPECIFIC FOLDER DIRECTLY
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def open_folder(folder: str) -> str:
    """
    Kisi bhi folder ko File Explorer mein seedha khol deta hai.

    Args:
        folder: Folder naam ya path.
                Smart shortcuts: desktop, downloads, documents, pictures, videos, music, onedrive
                Ya full path: "C:/Users/Raj/Projects/MyApp"

    Returns:
        Confirmation with opened path.
    """
    si = (await _translate(folder.strip())).strip().lower()

    if si in QUICK_FOLDERS:
        target = QUICK_FOLDERS[si]
    else:
        target = Path(folder).expanduser().resolve()

    if not target.exists():
        # Try searching for the folder name
        return await find_and_open(folder, find_type="folder", open_result=True)

    if not target.is_dir():
        return f"❌ Yeh folder nahi, file hai: {target}"

    try:
        subprocess.Popen(["explorer", str(target)])
        return f"✅ Folder khul gaya:\n📁 {target}"
    except Exception as e:
        try:
            os.startfile(str(target))
            return f"✅ Folder khul gaya:\n📁 {target}"
        except Exception as e2:
            return f"❌ Folder nahi khula: {e2}"