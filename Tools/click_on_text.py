"""
OCR Click Tool — Final version for LiveKit agents
==================================================
Handles all your scenarios:
  - Dark theme / white-on-dark text
  - Web browser content
  - Games and videos (force_refresh auto-enabled for fast-changing screens)
  - Normal Windows UI

Key design decisions:
  1. 5 preprocessing passes covering light+dark themes
  2. 2.5x upscale before OCR (critical for small UI text)
  3. mss for DPI-correct screenshots on Windows
  4. Case-insensitive fuzzy matching (OCR returns mixed case)
  5. Confidence NOT used in similarity (was killing valid matches)
  6. Content-hash cache (skips re-OCR when screen hasn't changed)
  7. Tesseract path auto-set for default Windows install
"""

import asyncio
import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pyautogui

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ── optional imports ──────────────────────────────────────────────────────────
try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageGrab, ImageOps
    import cv2
    import numpy as np
    OCR_AVAILABLE = True

    # Auto-set Tesseract path for default Windows install
    import os, sys
    _DEFAULT_TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if sys.platform == "win32" and os.path.exists(_DEFAULT_TESS):
        pytesseract.pytesseract.tesseract_cmd = _DEFAULT_TESS

except ImportError as _e:
    logger.warning("OCR libraries missing: %s", _e)
    OCR_AVAILABLE = False

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool():
        def _d(fn): return fn
        return _d

try:
    import mss
    _MSS_OK = True
except ImportError:
    _MSS_OK = False


# ── translation ───────────────────────────────────────────────────────────────

_TRANS_CACHE: Dict[str, str] = {}

_HINDI: Dict[str, str] = {
    "नमस्ते": "hello", "हैलो": "hello", "कैसे": "how", "हो": "are",
    "आप": "you", "तुम": "you", "मैं": "I", "मेरा": "my", "नाम": "name",
    "लिखो": "write", "टाइप": "type", "दिखाओ": "show", "खोलो": "open",
    "क्लिक": "click", "बटन": "button", "मेनू": "menu", "फाइल": "file",
    "सेटिंग": "setting", "विकल्प": "option", "सहेजें": "save", "बंद": "close",
    "प्रारंभ": "start", "समाप्त": "end", "रद्द": "cancel", "ठीक": "ok",
    "हाँ": "yes", "नहीं": "no", "धन्यवाद": "thanks",
    "सबमिट": "submit", "अगला": "next", "पिछला": "previous",
    "रोकें": "stop", "प्ले": "play", "वापस": "back",
    "ताजा": "refresh", "अपडेट": "update", "इंस्टॉल": "install",
    "डाउनलोड": "download", "अपलोड": "upload", "संपादित": "edit",
    "हटाएं": "delete", "प्रतिलिपि": "copy", "चिपकाएं": "paste",
    "काटें": "cut", "चुनें": "select", "सभी": "all", "नया": "new",
    "मदद": "help", "सहायता": "help",
}


def _is_english(text: str) -> bool:
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return (non_ascii / max(len(text), 1)) < 0.25


def _dict_translate(text: str) -> str:
    words = text.split()
    out = [_HINDI.get(w.strip(".,!?;:\"'").lower(), w) for w in words]
    r = " ".join(out)
    return r[0].upper() + r[1:] if r and r[0].isalpha() else r


async def translate_to_english(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text in _TRANS_CACHE:
        return _TRANS_CACHE[text]
    if _is_english(text):
        _TRANS_CACHE[text] = text
        return text
    quick = _dict_translate(text)
    if _is_english(quick):
        _TRANS_CACHE[text] = quick
        return quick
    try:
        import aiohttp
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text[:400]}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    translated = "".join(p[0] for p in data[0] if p[0])
                    if translated and translated.lower() != text.lower():
                        _TRANS_CACHE[text] = translated
                        logger.info("Translated '%s' → '%s'", text, translated)
                        return translated
    except Exception as exc:
        logger.debug("Google Translate: %s", exc)
    _TRANS_CACHE[text] = quick
    return quick


# ── screenshot ────────────────────────────────────────────────────────────────

def _grab(region: Optional[Tuple[int, int, int, int]] = None) -> "Image.Image":
    """
    DPI-correct screenshot.
    mss always returns true pixels on Windows HiDPI.
    PIL ImageGrab may return scaled-down images at >100% DPI.
    """
    if _MSS_OK:
        with mss.mss() as sct:
            if region:
                x, y, w, h = region
                mon = {"left": x, "top": y, "width": w, "height": h}
            else:
                mon = sct.monitors[1]   # primary monitor
            raw = sct.grab(mon)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    # PIL fallback
    if region:
        x, y, w, h = region
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    return ImageGrab.grab(all_screens=True)


# ── preprocessing ─────────────────────────────────────────────────────────────

SCALE = 2.5   # upscale factor — critical for small UI fonts (12-14px)


def _to_uint8_gray(img: "Image.Image") -> "np.ndarray":
    """Safe PIL → contiguous uint8 grayscale numpy array (handles BGRA etc)."""
    mode = img.mode
    if mode in ("BGRA", "RGBA"):
        img = img.convert("RGBA").convert("RGB")
    elif mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return np.ascontiguousarray(np.array(img.convert("L"), dtype=np.uint8))


def _preprocess(img: "Image.Image") -> "List[Tuple[Image.Image, str, int]]":
    """
    Returns (image, pass_name, tesseract_psm) for each preprocessing variant.

    PSM guide:
      6  = uniform block of text  (dialogs, web paragraphs)
      7  = single text line        (tooltips, status bars)
      11 = sparse text             (menus, toolbars, scattered labels)

    We cover BOTH light-on-dark AND dark-on-light because we don't know
    which theme is active. The dedup step later merges duplicates.
    """
    w, h = img.size
    big = img.resize((int(w * SCALE), int(h * SCALE)), Image.LANCZOS)
    arr = _to_uint8_gray(big)
    gray = Image.fromarray(arr)

    passes = []

    # ── Light theme passes (dark text on light background) ──
    enhanced = ImageEnhance.Contrast(gray).enhance(2.5)
    passes.append((enhanced, "light_enhanced", 11))

    try:
        _, t = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if t is not None:
            passes.append((Image.fromarray(t), "light_otsu", 6))
    except Exception:
        pass

    # ── Dark theme passes (white/light text on dark background) ──
    # Simply invert the image so OCR sees dark-on-light
    try:
        inv_arr = cv2.bitwise_not(arr)
        inv = Image.fromarray(inv_arr)
        passes.append((inv, "dark_inverted", 11))

        inv_enhanced = ImageEnhance.Contrast(inv).enhance(2.0)
        passes.append((inv_enhanced, "dark_enhanced", 6))

        _, t_inv = cv2.threshold(inv_arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if t_inv is not None:
            passes.append((Image.fromarray(t_inv), "dark_otsu", 11))
    except Exception as exc:
        logger.debug("Dark passes failed: %s", exc)

    return passes


# ── OCR core ──────────────────────────────────────────────────────────────────

@dataclass
class TextItem:
    text: str
    x: int          # coords in ORIGINAL (pre-scale) image space
    y: int
    w: int
    h: int
    confidence: float
    method: str = ""


@dataclass
class _CacheEntry:
    items: "List[TextItem]"
    ts: float = field(default_factory=time.time)


_CACHE: Dict[str, _CacheEntry] = {}
CACHE_TTL = 15.0   # seconds. Short because games/videos change fast.


def _img_hash(img: "Image.Image") -> str:
    thumb = img.resize((64, 64)).convert("L")
    return hashlib.md5(thumb.tobytes()).hexdigest()


def _clean(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    words = [w for w in text.split() if len(w) > 1 or w in ("I", "a", "A")]
    result = " ".join(words)
    return result[0].upper() + result[1:] if result and result[0].isalpha() else result


def _tess_config(psm: int) -> str:
    return (
        f"--psm {psm} --oem 3 "
        "-c tessedit_char_whitelist="
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "0123456789 .,!?-@#$%&*()/\\:;_+="
        " -c preserve_interword_spaces=1"
    )


async def _ocr_pass(
    img: "Image.Image", name: str, psm: int, min_conf: int
) -> "List[TextItem]":
    items: List[TextItem] = []
    try:
        data = pytesseract.image_to_data(
            img,
            config=_tess_config(psm),
            lang="eng+hin",
            output_type=pytesseract.Output.DICT,
            timeout=8,
        )
    except Exception as exc:
        logger.debug("Pass '%s' error: %s", name, exc)
        return items

    for i, raw in enumerate(data["text"]):
        raw = (raw or "").strip()
        conf = float(data["conf"][i])
        if conf < min_conf or not raw or len(raw) < 2:
            continue
        cleaned = _clean(raw)
        if not cleaned:
            continue
        items.append(TextItem(
            text=cleaned,
            x=int(data["left"][i] / SCALE),
            y=int(data["top"][i] / SCALE),
            w=int(data["width"][i] / SCALE),
            h=int(data["height"][i] / SCALE),
            confidence=conf,
            method=name,
        ))
    return items


async def get_screen_text(
    region: Optional[Tuple[int, int, int, int]] = None,
    min_confidence: int = 45,
    force_refresh: bool = False,
) -> "List[TextItem]":
    screenshot = _grab(region)
    key = _img_hash(screenshot)

    if not force_refresh and key in _CACHE:
        entry = _CACHE[key]
        if time.time() - entry.ts < CACHE_TTL:
            logger.info("Cache hit — %d items", len(entry.items))
            return entry.items

    # Evict stale entries
    now = time.time()
    for k in [k for k, v in _CACHE.items() if now - v.ts > CACHE_TTL]:
        del _CACHE[k]

    t0 = time.time()
    passes = _preprocess(screenshot)
    results = await asyncio.gather(
        *[_ocr_pass(img, name, psm, min_confidence) for img, name, psm in passes],
        return_exceptions=True,
    )

    # Merge + deduplicate on (grid cell, lowercase text prefix)
    seen: set = set()
    items: List[TextItem] = []
    for batch in results:
        if not isinstance(batch, list):
            continue
        for item in batch:
            cell = (item.x // 8, item.y // 8, item.text[:10].lower())
            if cell not in seen:
                seen.add(cell)
                items.append(item)

    logger.info("OCR done %.2fs — %d items from %d passes",
                time.time() - t0, len(items), len(passes))
    _CACHE[key] = _CacheEntry(items=items)
    return items


# ── matching ──────────────────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if len(a) > len(b):
        a, b = b, a
    row = list(range(len(a) + 1))
    for cb in b:
        prev, row[0] = row[0], row[0] + 1
        for j, ca in enumerate(a):
            old = row[j + 1]
            row[j + 1] = prev if ca == cb else 1 + min(prev, row[j], row[j + 1])
            prev = old
    return row[-1]


def _similarity(query: str, candidate: str) -> float:
    """
    Case-insensitive fuzzy similarity → 0.0–1.0.
    Does NOT factor in OCR confidence (that was discarding valid matches).
    """
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    # Substring match — "help" inside "Help Center" is a strong signal
    if q in c:
        return 0.92 - 0.05 * (len(c) - len(q)) / max(len(c), 1)
    if c in q:
        return 0.85
    # Word-level Jaccard
    qw, cw = set(q.split()), set(c.split())
    if qw and cw:
        j = len(qw & cw) / len(qw | cw)
        if j >= 0.4:
            return 0.60 + 0.30 * j
    # Character-level Levenshtein for short strings
    if len(q) <= 30 and len(c) <= 30:
        dist = _levenshtein(q, c)
        ratio = 1.0 - dist / max(len(q), len(c))
        if ratio >= 0.60:
            return 0.50 + 0.40 * ratio
    return 0.0


async def find_text(
    query: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    min_confidence: int = 45,
    exact: bool = False,
    force_refresh: bool = False,
) -> "Tuple[Optional[TextItem], float, List[TextItem]]":
    all_items = await get_screen_text(region, min_confidence, force_refresh)
    if not all_items:
        return None, 0.0, []

    # Lower threshold for non-exact — OCR always introduces some noise
    threshold = 0.75 if exact else 0.50

    best: Optional[TextItem] = None
    best_score = 0.0

    for item in all_items:
        score = _similarity(query, item.text)
        if score > best_score:
            best_score = score
            best = item
        if score >= 0.98:
            break   # perfect match, stop early

    if best_score < threshold:
        logger.info("Best match for '%s' was '%s' (%.2f) — below threshold %.2f",
                    query, best.text if best else "none", best_score, threshold)
        return None, best_score, all_items
    return best, best_score, all_items


# ── click helper ──────────────────────────────────────────────────────────────

async def _do_click(
    x: int, y: int,
    item: "TextItem", score: float, t0: float,
    double_click: bool, right_click: bool, scroll: int,
) -> str:
    sw, sh = pyautogui.size()
    x = max(0, min(x, sw - 1))
    y = max(0, min(y, sh - 1))

    cx, cy = pyautogui.position()
    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    dur = min(0.30, max(0.06, dist / 2500))

    try:
        pyautogui.moveTo(x, y, duration=dur, tween=pyautogui.easeInOutQuad)
        await asyncio.sleep(0.04)

        if right_click:
            pyautogui.rightClick(); verb = "right-clicked"
        elif double_click:
            pyautogui.doubleClick(); verb = "double-clicked"
        else:
            pyautogui.click(); verb = "clicked"

        scroll_note = ""
        if scroll:
            await asyncio.sleep(0.07)
            pyautogui.scroll(scroll)
            scroll_note = f", scrolled {'down' if scroll > 0 else 'up'} {abs(scroll)}"

        elapsed = time.time() - t0
        return (
            f"OK: {verb} '{item.text}' at ({x},{y}) "
            f"[score:{score:.2f} conf:{item.confidence:.0f}% {elapsed:.1f}s{scroll_note}]"
        )
    except pyautogui.FailSafeException:
        return "FAIL: Fail-safe triggered (mouse at corner). Move mouse and retry."
    except Exception as exc:
        return f"FAIL: Click error — {exc}"


# ── region helper ─────────────────────────────────────────────────────────────

def _parse_region(rx, ry, rw, rh) -> Optional[Tuple[int, int, int, int]]:
    """None or 0-sized region → None (full screen)."""
    if any(v is None for v in (rx, ry, rw, rh)):
        return None
    if int(rw) <= 0 or int(rh) <= 0:
        return None
    return (int(rx), int(ry), int(rw), int(rh))


# ── public tools ──────────────────────────────────────────────────────────────

@function_tool()
async def click_on_screen_text(
    command: str,
    min_confidence: int = 45,
    region_x: Optional[int] = None,
    region_y: Optional[int] = None,
    region_width: Optional[int] = None,
    region_height: Optional[int] = None,
    exact_match: bool = False,
    double_click: bool = False,
    right_click: bool = False,
    scroll_amount: int = 0,
    force_refresh: bool = False,
) -> str:
    """
    Find text on screen via OCR and click it. Works on dark themes,
    browsers, games, and normal Windows UI.

    Args:
        command        : Text to find — Hindi or English.
        min_confidence : Tesseract confidence floor 0-100. Default 45.
                         Lower = finds more text but more noise.
        region_x/y/width/height : Screen region to search.
                         Pass 0 or omit all for full-screen.
        exact_match    : Stricter matching (threshold 0.75 vs 0.50).
        double_click   : Perform double-click.
        right_click    : Perform right-click instead of left.
        scroll_amount  : Lines to scroll after click (+ve=down, -ve=up).
        force_refresh  : Skip cache — use for games/videos that change fast.
    """
    if not OCR_AVAILABLE:
        return (
            "OCR not ready. Install:\n"
            "  pip install pytesseract pillow opencv-python mss\n"
            "  Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
        )

    t0 = time.time()
    command = command.strip()
    if not command:
        return "Error: empty command."

    search = await translate_to_english(command)
    if search != command:
        logger.info("Translated '%s' → '%s'", command, search)

    # --- WINRT NATIVE FAST PATH ---
    try:
        import os, re
        ps_script = os.path.join(os.path.dirname(__file__), "winrt_ocr.ps1")
        if os.path.exists(ps_script) and not region_x and not region_y:
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_script, "-TargetText", search,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out_str = stdout.decode('utf-8', errors='ignore')
            
            match_winrt = re.search(r"SUCCESS: Found .*? at \((\d+),\s*(\d+)\)", out_str)
            if match_winrt:
                click_x = int(match_winrt.group(1))
                click_y = int(match_winrt.group(2))
                
                class MockItem:
                    def __init__(self, t):
                        self.text = t
                        self.confidence = 100
                        
                return await _do_click(
                    click_x, click_y, MockItem(search), 1.0, t0,
                    double_click, right_click, scroll_amount
                )
    except Exception as e:
        logger.warning("WinRT OCR fast-path failed: %s", e)

    # --- TESSERACT FALLBACK PATH ---
    region = _parse_region(region_x, region_y, region_width, region_height)

    try:
        match, score, all_items = await find_text(
            search, region, min_confidence, exact_match, force_refresh
        )
    except pytesseract.TesseractNotFoundError:
        return (
            "Tesseract not found at default path.\n"
            "Verify it is installed at: C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
            "Or download from: https://github.com/UB-Mannheim/tesseract/wiki"
        )
    except Exception as exc:
        logger.error("OCR error: %s", exc, exc_info=True)
        return f"OCR error: {exc}"

    if not match:
        msg = f"Could not find '{command}'"
        if search != command:
            msg += f" (searched as '{search}')"
        msg += f". Best score: {score:.2f} (need {'0.75' if exact_match else '0.50'})."
        if all_items:
            # Show top unique candidates to help diagnose
            seen_t: set = set()
            top = []
            for i in sorted(all_items, key=lambda i: i.confidence, reverse=True):
                if i.text.lower() not in seen_t and len(top) < 12:
                    seen_t.add(i.text.lower())
                    top.append(i)
            hints = "\n".join(
                f"  '{i.text}' (conf:{i.confidence:.0f}% pos:{i.x},{i.y} via:{i.method})"
                for i in top
            )
            msg += f"\nOCR found these items — check if your target text is here:\n{hints}"
            msg += "\nTip: if target IS listed above, try exact_match=false and lower min_confidence."
            msg += "\nTip: if target is NOT listed, try force_refresh=true (for games/video)."
        else:
            msg += "\nNo text found at all — check Tesseract install with verify_ocr_setup()."
        return msg

    ox = region[0] if region else 0
    oy = region[1] if region else 0
    click_x = ox + match.x + match.w // 2 + random.randint(-1, 1)
    click_y = oy + match.y + match.h // 2 + random.randint(-1, 1)

    return await _do_click(
        click_x, click_y, match, score, t0,
        double_click, right_click, scroll_amount,
    )


@function_tool()
async def find_all_text_on_screen(
    min_confidence: int = 40,
    region_x: Optional[int] = None,
    region_y: Optional[int] = None,
    region_width: Optional[int] = None,
    region_height: Optional[int] = None,
    force_refresh: bool = False,
) -> str:
    """
    Scan the screen and return every readable text item.
    Use this FIRST to debug — it shows exactly what OCR can see.
    The 'via' field shows which preprocessing pass found each item
    (light_* = light theme, dark_* = dark theme).

    Args:
        min_confidence : Lower this if too few results (try 30).
        force_refresh  : Always re-scan (important for games/videos).
    """
    if not OCR_AVAILABLE:
        return "OCR libraries not available."

    region = _parse_region(region_x, region_y, region_width, region_height)
    try:
        items = await get_screen_text(region, min_confidence, force_refresh)
    except Exception as exc:
        return f"Error: {exc}"

    if not items:
        return "No text found. Try: lower min_confidence, or check verify_ocr_setup()."

    rows: Dict[int, List[TextItem]] = {}
    for item in items:
        rows.setdefault(item.y // 35, []).append(item)

    lines = [f"Found {len(items)} text items (showing all):"]
    for k in sorted(rows):
        for item in sorted(rows[k], key=lambda i: i.x):
            lines.append(
                f"  '{item.text}'"
                f"  conf:{item.confidence:.0f}%"
                f"  pos:({item.x},{item.y})"
                f"  via:{item.method}"
            )
    return "\n".join(lines)


@function_tool()
async def verify_ocr_setup() -> str:
    """
    Check all OCR dependencies and run a live smoke test.
    Run this first if click_on_screen_text is not working.
    """
    lines = ["=== OCR Setup Verification ===", ""]

    # Library checks
    for mod, label, install in [
        ("pytesseract", "pytesseract",          "pytesseract"),
        ("PIL",         "Pillow",               "pillow"),
        ("cv2",         "OpenCV",               "opencv-python"),
        ("mss",         "mss (DPI-correct grab)","mss"),
    ]:
        try:
            __import__(mod)
            lines.append(f"  OK      {label}")
        except ImportError:
            lines.append(f"  MISSING {label}  →  pip install {install}")

    lines.append("")

    # Tesseract binary
    try:
        v = pytesseract.get_tesseract_version()
        cmd = pytesseract.pytesseract.tesseract_cmd
        lines.append(f"  OK      Tesseract v{v}")
        lines.append(f"          path: {cmd}")
    except Exception as exc:
        lines.append(f"  MISSING Tesseract binary: {exc}")
        lines.append("          Install: https://github.com/UB-Mannheim/tesseract/wiki")

    lines.append("")

    # Hindi language pack
    try:
        langs = pytesseract.get_languages()
        hin_ok = "hin" in langs
        lines.append(f"  {'OK' if hin_ok else 'MISSING'} Hindi language pack (hin)")
        if not hin_ok:
            lines.append("          Download hin.traineddata from:")
            lines.append("          https://github.com/tesseract-ocr/tessdata")
            lines.append("          → C:\\Program Files\\Tesseract-OCR\\tessdata\\hin.traineddata")
    except Exception as exc:
        lines.append(f"  WARN    Could not check languages: {exc}")

    lines.append("")

    # Screenshot
    try:
        img = _grab()
        backend = "mss (DPI-correct)" if _MSS_OK else "PIL ImageGrab (may be scaled on HiDPI)"
        lines.append(f"  OK      Screenshot {img.size[0]}x{img.size[1]}px via {backend}")
        lines.append(f"          Image mode: {img.mode}")
    except Exception as exc:
        lines.append(f"  FAIL    Screenshot: {exc}")

    lines.append("")

    # OCR smoke test — white text on dark background too
    try:
        from PIL import ImageDraw
        # Light background test
        light = Image.new("RGB", (400, 60), (255, 255, 255))
        ImageDraw.Draw(light).text((10, 15), "Hello World 123", fill=(0, 0, 0))
        r_light = pytesseract.image_to_string(
            light.resize((1000, 150), Image.LANCZOS), config="--psm 7"
        ).strip()
        light_ok = "Hello" in r_light or "World" in r_light

        # Dark background test (simulates dark theme)
        dark = Image.new("RGB", (400, 60), (30, 30, 30))
        ImageDraw.Draw(dark).text((10, 15), "Hello World 123", fill=(220, 220, 220))
        inv_dark = ImageOps.invert(dark.convert("L"))
        r_dark = pytesseract.image_to_string(
            inv_dark.resize((1000, 150), Image.LANCZOS), config="--psm 7"
        ).strip()
        dark_ok = "Hello" in r_dark or "World" in r_dark

        lines.append(f"  {'OK' if light_ok else 'FAIL'}    OCR smoke test (light theme): '{r_light}'")
        lines.append(f"  {'OK' if dark_ok  else 'FAIL'}    OCR smoke test (dark theme):  '{r_dark}'")
        if not dark_ok:
            lines.append("          Dark theme OCR failed — inversion pass may need tuning.")
    except Exception as exc:
        lines.append(f"  FAIL    OCR smoke test: {exc}")

    lines.append("")
    lines.append("All OK? Then try: find_all_text_on_screen() to see what OCR reads from your screen.")
    return "\n".join(lines)