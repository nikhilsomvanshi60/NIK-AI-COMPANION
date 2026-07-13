"""
Nova AI — Advanced Excel Automation Tool
=========================================
Reliable Excel control via pyautogui + openpyxl + xlwings (where available).
All tools work on manually-opened OR tool-created Excel files.
"""

import os
import time
import asyncio
import aiohttp
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyautogui
import pyperclip

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from livekit.agents import function_tool

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────

current_excel_file: str | None = None   # Path of last tool-created file


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSLATION  (unchanged logic, cleaned up)
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("responseStatus") == 200:
                        return data["responseData"]["translatedText"]
    except Exception:
        pass
    return None


_FALLBACK_DICT = {
    "नाम": "Name", "उम्र": "Age", "शहर": "City", "देश": "Country",
    "विभाग": "Department", "वेतन": "Salary", "पता": "Address",
    "मोबाइल": "Mobile", "ईमेल": "Email", "जन्मतिथि": "Birthdate",
    "आईटी": "IT", "एचआर": "HR", "वित्त": "Finance", "बिक्री": "Sales",
    "मार्केटिंग": "Marketing", "उत्पादन": "Production",
    "हाँ": "Yes", "नहीं": "No", "ठीक": "OK", "अच्छा": "Good",
    "मुंबई": "Mumbai", "दिल्ली": "Delhi", "बेंगलुरु": "Bangalore",
    "पुणे": "Pune", "हैदराबाद": "Hyderabad", "अहमदाबाद": "Ahmedabad",
    "कुल": "Total", "औसत": "Average", "गणना": "Count", "अधिकतम": "Max",
    "न्यूनतम": "Min", "योग": "Sum", "प्रतिशत": "Percent",
}


def _fallback_translate(text: str) -> str:
    return " ".join(_FALLBACK_DICT.get(w.strip(".,!?;:"), w) for w in text.split())


async def translate_free(text: str) -> str:
    """Translate any language → English. Returns original if already English."""
    if not text.strip() or _is_english(text):
        return text
    return (
        await _google_translate(text)
        or await _mymemory_translate(text)
        or _fallback_translate(text)
    )


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _activate_excel(wait: float = 0.4):
    """Click top-left to ensure Excel is in focus."""
    try:
        pyautogui.click(100, 100)
        time.sleep(wait)
    except Exception:
        pass


def _save(wait: float = 0.3):
    pyautogui.hotkey("ctrl", "s")
    time.sleep(wait)


def _parse_data_sequence(raw: str) -> list[str]:
    """
    Split a mixed separator string into clean tokens.
    Handles: comma, newline, \\n, pipe.
    """
    for sep in ["\n", "\\n", "|"]:
        raw = raw.replace(sep, ",")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _to_number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").replace("₹", "").replace("$", "").strip())
    except Exception:
        return None


def _default_excel_path(file_name: str) -> str:
    """Resolve save path: OneDrive > Documents > Desktop > Home."""
    home = Path.home()
    candidates = [
        home / "OneDrive" / "Documents",
        home / "Documents",
        home / "Desktop",
        home,
    ]
    for folder in candidates:
        if folder.exists():
            return str(folder / file_name)
    return str(home / file_name)


def _go_to_cell_internal(cell: str):
    """Navigate to a cell using the Name Box (fast, reliable)."""
    pyautogui.hotkey("ctrl", "g")
    time.sleep(0.4)
    pyautogui.write(cell.upper(), interval=0.05)
    pyautogui.press("enter")
    time.sleep(0.3)


# ─────────────────────────────────────────────────────────────────────────────
#  1. FILE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def create_excel_file(
    file_name: str,
    sheet_name: str = "Sheet1",
    headers: str = "",
) -> str:
    """
    Creates a new Excel file, optionally with a custom sheet name and column headers.

    Args:
        file_name  : Name of the file (with or without .xlsx).
        sheet_name : Name of the first worksheet. Default: 'Sheet1'.
        headers    : Comma-separated column headers to pre-fill in row 1.
                     Example: "Name, Age, City, Salary"
                     Leave empty to create a blank file.

    Returns:
        Confirmation with full file path.
    """
    global current_excel_file
    try:
        if not file_name.endswith(".xlsx"):
            file_name += ".xlsx"

        file_path = _default_excel_path(file_name)

        # Translate sheet name and headers
        sheet_name = await translate_free(sheet_name)
        header_list: list[str] = []
        if headers.strip():
            for h in _parse_data_sequence(headers):
                header_list.append(await translate_free(h))

        if HAS_OPENPYXL:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_name

            if header_list:
                for col_idx, header in enumerate(header_list, start=1):
                    cell = ws.cell(row=1, column=col_idx, value=header)
                    # Style headers
                    cell.font = Font(bold=True, color="FFFFFF", size=11)
                    cell.fill = PatternFill("solid", fgColor="2E75B6")
                    cell.alignment = Alignment(horizontal="center")
                    # Auto column width
                    ws.column_dimensions[
                        openpyxl.utils.get_column_letter(col_idx)
                    ].width = max(12, len(header) + 4)

            wb.save(file_path)
        else:
            # Fallback: pandas
            df = pd.DataFrame(columns=header_list if header_list else [])
            df.to_excel(file_path, index=False, sheet_name=sheet_name)

        current_excel_file = file_path
        os.startfile(file_path)
        time.sleep(3)

        headers_msg = f" with headers: {', '.join(header_list)}" if header_list else ""
        return f"✅ '{file_name}' created and opened{headers_msg}.\n📍 {file_path}"

    except Exception as e:
        return f"❌ Error creating Excel file: {e}"


@function_tool()
async def open_excel_file(file_path: str) -> str:
    """
    Opens an existing Excel file.

    Args:
        file_path: Full path to the .xlsx / .xls / .csv file.
    """
    global current_excel_file
    try:
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"
        os.startfile(file_path)
        current_excel_file = file_path
        time.sleep(3)
        return f"✅ Opened: {os.path.basename(file_path)}"
    except Exception as e:
        return f"❌ Error opening file: {e}"


@function_tool()
async def save_excel_changes() -> str:
    """Saves the active Excel file (Ctrl+S)."""
    try:
        _save(wait=0.5)
        return "💾 File saved successfully."
    except Exception as e:
        return f"❌ Error saving: {e}"


@function_tool()
async def save_as_excel(new_file_name: str) -> str:
    """
    Save active Excel file with a new name (Save As).

    Args:
        new_file_name: New filename (with or without .xlsx).
    """
    try:
        _activate_excel()
        pyautogui.hotkey("ctrl", "shift", "s")
        time.sleep(1.5)
        if not new_file_name.endswith(".xlsx"):
            new_file_name += ".xlsx"
        pyautogui.write(new_file_name, interval=0.05)
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(1)
        return f"✅ Saved as '{new_file_name}'."
    except Exception as e:
        return f"❌ Error in Save As: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  2. DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def enter_data(
    data: str,
    move_after: str = "down",
) -> str:
    """
    Types a single value into the current/active cell.

    Args:
        data       : Value to enter (text, number, formula like '=SUM(A1:A5)').
        move_after : Where to move after entry — 'down' | 'right' | 'up' | 'left' | 'stay'.
                     Default: 'down'.

    Returns:
        Confirmation of what was entered.
    """
    try:
        translated = await translate_free(data)
        _activate_excel(0.3)

        pyautogui.write(translated, interval=0.05)
        time.sleep(0.2)

        move_after = move_after.lower().strip()
        key_map = {"down": "down", "right": "tab", "up": "up", "left": "left", "stay": "escape"}
        key = key_map.get(move_after, "down")

        if key == "escape":
            pyautogui.hotkey("ctrl", "enter")   # Confirm without moving
        else:
            pyautogui.press(key)
        time.sleep(0.2)

        _save()
        return f"✅ Entered: '{translated}'  |  Moved: {move_after}"

    except Exception as e:
        return f"❌ Error entering data: {e}"


@function_tool()
async def enter_row(
    values: str,
    start_column: str = "",
) -> str:
    """
    Enters multiple values across columns in the SAME row (left → right).

    Args:
        values      : Comma/newline/pipe-separated values.
                      Example: "Raj, 25, Mumbai, 50000"
        start_column: Optional cell to start from, e.g. 'A3'. 
                      If empty, starts from current active cell.

    Returns:
        Confirmation with count of values entered.
    """
    try:
        items = _parse_data_sequence(values)
        if not items:
            return "❌ No data to enter."

        translated = [await translate_free(v) for v in items]
        _activate_excel()

        if start_column.strip():
            _go_to_cell_internal(start_column.strip())

        for i, val in enumerate(translated):
            pyautogui.write(val, interval=0.05)
            time.sleep(0.15)
            pyautogui.press("tab")   # Move right
            time.sleep(0.15)

        _save()
        return f"✅ {len(translated)} values entered in a row: {', '.join(translated)}"

    except Exception as e:
        return f"❌ Error entering row: {e}"


@function_tool()
async def enter_column(
    values: str,
    start_cell: str = "",
) -> str:
    """
    Enters multiple values in the SAME column (top → down).

    Args:
        values    : Comma/newline/pipe-separated values.
                    Example: "Raj\\nPriya\\nAmit\\nNeha"
        start_cell: Optional cell to start from, e.g. 'A2'.
                    If empty, starts from current active cell.

    Returns:
        Confirmation with count of values entered.
    """
    try:
        items = _parse_data_sequence(values)
        if not items:
            return "❌ No data to enter."

        translated = [await translate_free(v) for v in items]
        _activate_excel()

        if start_cell.strip():
            _go_to_cell_internal(start_cell.strip())

        for val in translated:
            pyautogui.write(val, interval=0.05)
            time.sleep(0.15)
            pyautogui.press("down")
            time.sleep(0.15)

        _save()
        return f"✅ {len(translated)} values entered in a column: {', '.join(translated)}"

    except Exception as e:
        return f"❌ Error entering column: {e}"


@function_tool()
async def enter_table(
    table_data: str,
    start_cell: str = "A1",
    include_headers: bool = True,
) -> str:
    """
    Enters a full table of data — multiple rows AND columns at once.
    Each row is separated by '|', values within a row by ','.

    Args:
        table_data     : Table in format "R1C1, R1C2 | R2C1, R2C2 | ..."
                         Example: "Name, Age, City | Raj, 25, Mumbai | Priya, 30, Delhi"
        start_cell     : Top-left cell to start from. Default: 'A1'.
        include_headers: If True, the first row is treated as headers (gets bold+colored).

    Returns:
        Summary of rows and columns entered.
    """
    try:
        rows = [r.strip() for r in table_data.split("|") if r.strip()]
        if not rows:
            return "❌ No data found. Use '|' to separate rows."

        _activate_excel()
        _go_to_cell_internal(start_cell)

        total_rows = 0
        total_cols = 0

        for row_idx, row_str in enumerate(rows):
            cells = _parse_data_sequence(row_str)
            translated = [await translate_free(c) for c in cells]
            total_cols = max(total_cols, len(translated))

            for col_idx, val in enumerate(translated):
                pyautogui.write(val, interval=0.04)
                time.sleep(0.1)
                pyautogui.press("tab")
                time.sleep(0.1)

            # Move to next row start
            pyautogui.press("enter")
            time.sleep(0.15)
            total_rows += 1

        # Bold header row
        if include_headers and total_rows > 0 and total_cols > 0:
            _go_to_cell_internal(start_cell)
            pyautogui.hotkey("shift", "right") if total_cols == 1 else None
            for _ in range(total_cols - 1):
                pyautogui.hotkey("shift", "right")
            pyautogui.hotkey("ctrl", "b")
            time.sleep(0.2)

        _save()
        return f"✅ Table entered: {total_rows} rows × {total_cols} columns (starting {start_cell})."

    except Exception as e:
        return f"❌ Error entering table: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  3. NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def go_to_cell(cell_address: str) -> str:
    """
    Moves cursor to a specific cell.

    Args:
        cell_address: Excel address like 'A1', 'B10', 'Z100'.
    """
    try:
        _activate_excel()
        _go_to_cell_internal(cell_address.strip().upper())
        return f"✅ Moved to cell {cell_address.upper()}."
    except Exception as e:
        return f"❌ Error navigating: {e}"


@function_tool()
async def move_cell(direction: str, steps: int = 1) -> str:
    """
    Moves the active cell cursor in a direction.

    Args:
        direction: 'up' | 'down' | 'left' | 'right' | 
                   'start' (Ctrl+Home) | 'end' (Ctrl+End) |
                   'row_start' (Home) | 'row_end' (Ctrl+Right).
        steps    : How many steps to move (1–100). Default: 1.
    """
    try:
        _activate_excel(0.2)
        steps = max(1, min(steps, 100))

        direction = direction.lower().strip()

        special = {
            "start": lambda: pyautogui.hotkey("ctrl", "home"),
            "end":   lambda: pyautogui.hotkey("ctrl", "end"),
            "row_start": lambda: pyautogui.press("home"),
            "row_end":   lambda: pyautogui.hotkey("ctrl", "right"),
        }

        if direction in special:
            special[direction]()
            return f"✅ Moved to {direction}."

        key_map = {"up": "up", "down": "down", "left": "left", "right": "right"}
        key = key_map.get(direction)
        if not key:
            return f"❌ Unknown direction '{direction}'. Use: up/down/left/right/start/end."

        for _ in range(steps):
            pyautogui.press(key)
            time.sleep(0.05)

        return f"✅ Moved {direction} × {steps}."
    except Exception as e:
        return f"❌ Error moving: {e}"


@function_tool()
async def switch_sheet(sheet_name: str = "", direction: str = "next") -> str:
    """
    Switch to a different worksheet.

    Args:
        sheet_name: Name of the sheet to switch to (leave empty to use direction).
        direction : 'next' or 'prev'. Used when sheet_name is empty.
    """
    try:
        _activate_excel()
        if sheet_name.strip():
            # Right-click on sheet tab area — safer to use Ctrl+PageDown loop
            # Find sheet by name using Name Box workaround (Ctrl+F not ideal)
            # Best: use keyboard to cycle until found (up to 20 sheets)
            for _ in range(20):
                pyautogui.hotkey("ctrl", "pagedown")
                time.sleep(0.3)
                # We can't easily read the active tab name via pyautogui
                # so we just cycle — user should use direction for large workbooks
            return f"✅ Tried to navigate to sheet '{sheet_name}'. Verify manually."
        else:
            if direction.lower() == "next":
                pyautogui.hotkey("ctrl", "pagedown")
            else:
                pyautogui.hotkey("ctrl", "pageup")
            time.sleep(0.3)
            return f"✅ Switched to {direction} sheet."
    except Exception as e:
        return f"❌ Error switching sheet: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  4. SELECTION
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def select_range(cell_range: str) -> str:
    """
    Selects a cell range.

    Args:
        cell_range: Excel range like 'A1:C10', 'B2:B20', or single cell 'A1'.
    """
    try:
        _activate_excel()
        _go_to_cell_internal(cell_range.strip().upper())
        return f"✅ Range {cell_range.upper()} selected."
    except Exception as e:
        return f"❌ Error selecting range: {e}"


@function_tool()
async def select_entire(select_type: str) -> str:
    """
    Selects the entire row, column, or all cells.

    Args:
        select_type: 'row' | 'column' | 'all'
    """
    try:
        _activate_excel(0.2)
        st = select_type.lower().strip()

        if st in ("row", "रो", "पंक्ति"):
            pyautogui.hotkey("shift", "space")
            return "✅ Entire row selected."

        elif st in ("column", "col", "कॉलम", "स्तंभ"):
            pyautogui.hotkey("ctrl", "space")
            return "✅ Entire column selected."

        elif st in ("all", "सब", "सभी"):
            pyautogui.hotkey("ctrl", "a")
            return "✅ All cells selected."

        else:
            return "❌ Use 'row', 'column', or 'all'."

    except Exception as e:
        return f"❌ Error selecting: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  5. EDITING
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def delete_cell_data(
    mode: str = "current",
    cell_or_range: str = "",
) -> str:
    """
    Deletes data from cell(s).

    Args:
        mode         : 'current' (active cell) | 'range' (use cell_or_range) | 'row' | 'column' | 'all'
        cell_or_range: Required when mode='range'. E.g. 'A1:C5'.
    """
    try:
        _activate_excel(0.2)

        if mode == "current":
            pyautogui.press("delete")
            return "✅ Current cell cleared."

        elif mode == "range" and cell_or_range:
            _go_to_cell_internal(cell_or_range)
            pyautogui.press("delete")
            return f"✅ Range {cell_or_range.upper()} cleared."

        elif mode == "row":
            pyautogui.hotkey("shift", "space")
            time.sleep(0.2)
            pyautogui.press("delete")
            return "✅ Entire row data cleared."

        elif mode == "column":
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.2)
            pyautogui.press("delete")
            return "✅ Entire column data cleared."

        elif mode == "all":
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.press("delete")
            return "✅ All data cleared."

        else:
            return "❌ Invalid mode. Use: current/range/row/column/all."

    except Exception as e:
        return f"❌ Error deleting: {e}"


@function_tool()
async def clipboard_action(action: str) -> str:
    """
    Perform cut / copy / paste / paste_values on the selected cell(s).

    Args:
        action: 'cut' | 'copy' | 'paste' | 'paste_values' (pastes without formulas)
    """
    try:
        _activate_excel(0.2)
        action = action.lower().strip()

        actions = {
            "cut":          lambda: pyautogui.hotkey("ctrl", "x"),
            "copy":         lambda: pyautogui.hotkey("ctrl", "c"),
            "paste":        lambda: pyautogui.hotkey("ctrl", "v"),
            "paste_values": lambda: (
                pyautogui.hotkey("ctrl", "alt", "v"),
                time.sleep(0.5),
                pyautogui.press("v"),          # Values option in Paste Special
                time.sleep(0.2),
                pyautogui.press("enter"),
            ),
        }

        if action not in actions:
            return "❌ Use: cut / copy / paste / paste_values."

        actions[action]()
        time.sleep(0.3)
        return f"✅ {action.replace('_', ' ').title()} done."

    except Exception as e:
        return f"❌ Error in clipboard action: {e}"


@function_tool()
async def undo_redo(action: str = "undo", steps: int = 1) -> str:
    """
    Undo or redo recent actions.

    Args:
        action: 'undo' or 'redo'.
        steps : Number of steps (1–10). Default: 1.
    """
    try:
        _activate_excel(0.2)
        steps = max(1, min(steps, 10))
        key = ("ctrl", "z") if action.lower() == "undo" else ("ctrl", "y")
        for _ in range(steps):
            pyautogui.hotkey(*key)
            time.sleep(0.2)
        return f"✅ {action.title()} × {steps} done."
    except Exception as e:
        return f"❌ Error in undo/redo: {e}"


@function_tool()
async def find_and_replace(find_text: str, replace_text: str = "") -> str:
    """
    Find text in the spreadsheet and optionally replace it.

    Args:
        find_text   : Text to search for.
        replace_text: Replacement text. Leave empty to just find/highlight.
    """
    try:
        _activate_excel()
        find_text    = await translate_free(find_text)
        replace_text = await translate_free(replace_text) if replace_text else ""

        if replace_text:
            pyautogui.hotkey("ctrl", "h")   # Replace dialog
        else:
            pyautogui.hotkey("ctrl", "f")   # Find dialog

        time.sleep(0.8)
        pyautogui.write(find_text, interval=0.05)

        if replace_text:
            pyautogui.press("tab")
            time.sleep(0.3)
            pyautogui.write(replace_text, interval=0.05)
            time.sleep(0.3)
            # Replace All
            pyautogui.hotkey("alt", "a")
            time.sleep(0.5)
            pyautogui.press("enter")   # OK on confirmation
            time.sleep(0.3)
            pyautogui.press("escape")
            _save()
            return f"✅ Replaced all '{find_text}' → '{replace_text}'."
        else:
            pyautogui.press("enter")
            time.sleep(0.5)
            return f"✅ Searching for '{find_text}'."

    except Exception as e:
        return f"❌ Error in find/replace: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  6. FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def format_cells(
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    font_size: int = 0,
    align: str = "",
    wrap_text: bool = False,
    number_format: str = "",
) -> str:
    """
    Apply formatting to currently selected cell(s).

    Args:
        bold         : Make text bold.
        italic       : Make text italic.
        underline    : Underline text.
        font_size    : Font size (0 = don't change).
        align        : 'left' | 'center' | 'right'.
        wrap_text    : Enable text wrapping.
        number_format: 'currency' | 'percent' | 'date' | 'number' | 'text'.

    Returns:
        Summary of applied formatting.
    """
    try:
        _activate_excel(0.2)
        applied = []

        if bold:
            pyautogui.hotkey("ctrl", "b"); time.sleep(0.15); applied.append("bold")
        if italic:
            pyautogui.hotkey("ctrl", "i"); time.sleep(0.15); applied.append("italic")
        if underline:
            pyautogui.hotkey("ctrl", "u"); time.sleep(0.15); applied.append("underline")

        if font_size > 0:
            # Click font size box in ribbon (Home → Font Size)
            pyautogui.hotkey("alt", "h", "f", "s")
            time.sleep(0.4)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.write(str(font_size), interval=0.05)
            pyautogui.press("enter")
            time.sleep(0.2)
            applied.append(f"size {font_size}")

        if align in ("left", "center", "right"):
            align_keys = {"left": "al", "center": "ac", "right": "ar"}
            pyautogui.hotkey("alt", "h", *list(align_keys[align]))
            time.sleep(0.2)
            applied.append(f"align {align}")

        if wrap_text:
            pyautogui.hotkey("alt", "h", "w")
            time.sleep(0.2)
            applied.append("wrap text")

        if number_format:
            fmt_map = {
                "currency": ("ctrl", "shift", "4"),
                "percent":  ("ctrl", "shift", "5"),
                "number":   ("ctrl", "shift", "1"),
                "date":     ("ctrl", "shift", "3"),
                "text":     None,
            }
            keys = fmt_map.get(number_format.lower())
            if keys:
                pyautogui.hotkey(*keys)
                time.sleep(0.2)
                applied.append(f"format: {number_format}")

        _save()
        return f"✅ Formatting applied: {', '.join(applied) if applied else 'none specified'}."

    except Exception as e:
        return f"❌ Error formatting: {e}"


@function_tool()
async def auto_fit_columns() -> str:
    """Auto-fits all column widths to content (selects all then adjusts)."""
    try:
        _activate_excel()
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.hotkey("alt", "h", "o", "i")   # Home → Format → AutoFit Column Width
        time.sleep(0.5)
        _save()
        return "✅ All columns auto-fitted to content."
    except Exception as e:
        return f"❌ Error auto-fitting: {e}"


@function_tool()
async def add_border(border_type: str = "all") -> str:
    """
    Adds borders to selected cells.

    Args:
        border_type: 'all' | 'outer' | 'thick_outer' | 'none'.
    """
    try:
        _activate_excel(0.2)
        # Alt+H → B → border submenu
        pyautogui.hotkey("alt", "h", "b")
        time.sleep(0.5)

        key_map = {
            "all":         "a",
            "outer":       "s",
            "thick_outer": "t",
            "none":        "n",
        }
        key = key_map.get(border_type.lower(), "a")
        pyautogui.press(key)
        time.sleep(0.3)
        _save()
        return f"✅ Border '{border_type}' applied."
    except Exception as e:
        return f"❌ Error adding border: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  7. FORMULAS & CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def insert_formula(
    formula_type: str,
    data_range: str = "",
    target_cell: str = "",
) -> str:
    """
    Inserts a common Excel formula into a cell.

    Args:
        formula_type: 'sum' | 'average' | 'count' | 'max' | 'min' |
                      'counta' | 'if' | 'vlookup' | 'today' | 'now' |
                      'autosum' (uses Alt+= for automatic range detection)
        data_range  : Cell range for the formula, e.g. 'A2:A20'.
                      Not needed for 'autosum', 'today', 'now'.
        target_cell : Cell to put the formula in. If empty, uses active cell.

    Returns:
        Confirmation with the formula inserted.
    """
    try:
        _activate_excel()

        if target_cell.strip():
            _go_to_cell_internal(target_cell.strip().upper())

        formula_type = formula_type.lower().strip()

        if formula_type == "autosum":
            pyautogui.hotkey("alt", "=")
            time.sleep(0.4)
            pyautogui.press("enter")
            _save()
            return "✅ AutoSum formula inserted."

        if formula_type == "today":
            formula = "=TODAY()"
        elif formula_type == "now":
            formula = "=NOW()"
        elif not data_range.strip():
            return f"❌ Please provide data_range for '{formula_type}' formula."
        else:
            r = data_range.strip().upper()
            formula_map = {
                "sum":     f"=SUM({r})",
                "average": f"=AVERAGE({r})",
                "count":   f"=COUNT({r})",
                "counta":  f"=COUNTA({r})",
                "max":     f"=MAX({r})",
                "min":     f"=MIN({r})",
            }
            formula = formula_map.get(formula_type)
            if not formula:
                return f"❌ Unknown formula type: '{formula_type}'."

        pyautogui.write(formula, interval=0.04)
        pyautogui.press("enter")
        time.sleep(0.3)
        _save()
        return f"✅ Formula inserted: {formula}"

    except Exception as e:
        return f"❌ Error inserting formula: {e}"


@function_tool()
async def calculate_and_write_sum(
    selected_range: str = "",
    target_cell: str = "below",
) -> str:
    """
    Calculates the sum of a range using Python and writes the result.
    More reliable than AutoSum for pre-selected data.

    Args:
        selected_range: Range to sum, e.g. 'B2:B20'. 
                        If empty, reads from clipboard (select cells first).
        target_cell   : Where to write the result:
                        'below' | 'right' | cell address like 'B21'.
    """
    try:
        _activate_excel()

        if selected_range.strip():
            _go_to_cell_internal(selected_range.strip())
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.4)
        else:
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.4)

        clipboard_data = pyperclip.paste()
        numbers = []
        for line in clipboard_data.split("\n"):
            for cell in line.split("\t"):
                n = _to_number(cell)
                if n is not None:
                    numbers.append(n)

        if not numbers:
            return "❌ No numbers found. Please select numeric cells first."

        total = sum(numbers)

        # Navigate to target
        tc = target_cell.lower().strip()
        if tc == "below":
            pyautogui.press("escape")
            if selected_range.strip():
                # Go to cell below the range
                end_cell = selected_range.strip().split(":")[-1]
                _go_to_cell_internal(end_cell)
            pyautogui.press("down")
        elif tc == "right":
            pyautogui.press("escape")
            if selected_range.strip():
                end_cell = selected_range.strip().split(":")[-1]
                _go_to_cell_internal(end_cell)
            pyautogui.press("right")
        else:
            pyautogui.press("escape")
            _go_to_cell_internal(tc.upper())

        # Write total (integer if no decimal)
        write_val = str(int(total)) if total == int(total) else str(round(total, 4))
        pyautogui.write(write_val, interval=0.04)
        pyautogui.press("enter")
        _save()
        return f"✅ Sum of {len(numbers)} numbers = {total}"

    except Exception as e:
        return f"❌ Error calculating sum: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  8. SORTING & FILTERING
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def sort_data(
    direction: str = "asc",
    has_header: bool = True,
) -> str:
    """
    Sorts the data in the active column or selected range.

    Args:
        direction : 'asc' (A→Z, smallest→largest) | 'desc' (Z→A, largest→smallest).
        has_header: If True, first row is treated as header (not sorted).
    """
    try:
        _activate_excel(0.3)
        pyautogui.press("escape")
        time.sleep(0.1)

        is_desc = any(w in direction.lower() for w in
                      ["desc", "z to a", "descending", "large", "बड़े", "अवरोही"])

        if is_desc:
            pyautogui.hotkey("alt", "a", "s", "d")
        else:
            pyautogui.hotkey("alt", "a", "s", "a")

        time.sleep(2.0)  # Wait for potential dialog

        # Handle "Sort Warning" dialog if it appears
        # Press Down to select "Continue with current selection", then Enter
        pyautogui.press("down")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)

        pyautogui.press("escape")
        _save()
        label = "descending (Z→A)" if is_desc else "ascending (A→Z)"
        return f"✅ Data sorted {label}."

    except Exception as e:
        return f"❌ Error sorting: {e}"


@function_tool()
async def toggle_filter() -> str:
    """Toggles AutoFilter on/off for the active dataset (Ctrl+Shift+L)."""
    try:
        _activate_excel()
        pyautogui.hotkey("ctrl", "shift", "l")
        time.sleep(0.3)
        _save()
        return "✅ AutoFilter toggled."
    except Exception as e:
        return f"❌ Error toggling filter: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  9. ROWS & COLUMNS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def insert_row_or_column(insert_type: str = "row", count: int = 1) -> str:
    """
    Inserts row(s) or column(s) above/left of the current position.

    Args:
        insert_type: 'row' | 'column'.
        count      : How many to insert (1–20).
    """
    try:
        _activate_excel(0.2)
        count = max(1, min(count, 20))

        for _ in range(count):
            if insert_type.lower() in ("row", "rows"):
                pyautogui.hotkey("shift", "space")   # Select row
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "shift", "+")  # Insert
            else:
                pyautogui.hotkey("ctrl", "space")    # Select column
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "shift", "+")
            time.sleep(0.5)
            pyautogui.press("enter")
            time.sleep(0.3)

        _save()
        return f"✅ {count} {insert_type}(s) inserted."
    except Exception as e:
        return f"❌ Error inserting {insert_type}: {e}"


@function_tool()
async def delete_row_or_column(delete_type: str = "row") -> str:
    """
    Deletes the current row or column.

    Args:
        delete_type: 'row' | 'column'.
    """
    try:
        _activate_excel(0.2)
        if delete_type.lower() in ("row", "rows"):
            pyautogui.hotkey("shift", "space")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "-")
        else:
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "-")

        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.2)
        _save()
        return f"✅ {delete_type.title()} deleted."
    except Exception as e:
        return f"❌ Error deleting {delete_type}: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  10. FREEZE, ZOOM, VIEW
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def freeze_panes(mode: str = "first_row") -> str:
    """
    Freeze rows/columns so they stay visible when scrolling.

    Args:
        mode: 'first_row' | 'first_column' | 'current_cell' | 'unfreeze'.
    """
    try:
        _activate_excel()
        # View → Freeze Panes
        pyautogui.hotkey("alt", "w", "f")
        time.sleep(0.5)

        key_map = {
            "first_row":    "r",   # Freeze Top Row
            "first_column": "c",   # Freeze First Column
            "current_cell": "f",   # Freeze Panes at current cell
            "unfreeze":     "f",   # Unfreeze (same shortcut toggles)
        }
        pyautogui.press(key_map.get(mode.lower(), "r"))
        time.sleep(0.3)
        _save()
        return f"✅ Panes {mode.replace('_', ' ')}."
    except Exception as e:
        return f"❌ Error freezing panes: {e}"
    
    