"""
Tools/__init__.py — NIK Windows Tool Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Naya tool add karna ho:
  1. Tools/<naam>.py banao
  2. Step A mein import karo
  3. Step B REGISTRY mein add karo
"""

# ══════════════════════════════════════════════════════════════════════════════
#  STEP A — IMPORTS
# ══════════════════════════════════════════════════════════════════════════════
from . import desktop_control as desktop
from . import search_web as search
from . import app_lock as lock
from . import open_app as app_open
from . import code_handler as code_fix
from . import time_volume_bright as volume
from . import screen_short as screenshot
from . import image_analysis as vision
from . import create_folder as file_op
from . import spotify as spotify
# from . import briefing # Not found
from . import reminder as reminder
# from . import google_form # Not found

# ── add karo neeche ──────────────────────────────────────────────────────────
from . import time_volume_bright as brightness
from . import system_power_action as power
from . import process_manager as process
from . import network_diagnostics as network
from . import youtube_videos as media
from . import type_user_message_auto as type_tool
from . import schedule_task as scheduler
from . import send_whatsapp_message as whatsapp
from . import click_on_text as click
from . import read_screen_text as read_screen
from . import set_wallpaper as set_wallpaper
from . import youtube_videos as youtube
from . import write_in_notepad as write_in_notepad
from . import scan_system_for_viruses as virus_scan
from . import pdf_reader as pdf_reader
from . import excel_data_entery as excel
from . import send_email as email
from . import word_to_pdf as converter
from . import website_maker as website_maker
from . import webScrping as web_scraper
from . import generate_ai_image as image_generator
from . import scroll_content as scroll
from . import press_key as press_key
from . import vs_code_contoller as vscode
from . import user_choice as user_choice
# ─────────────────────────────────────────────────────────────────────────────

# --- AUTO-PATCH LEGACY ATTRIBUTES ---
# Because LiveKit tools use @function_tool instead of TOOL_PREFIX and .run()
for mod in [desktop, search, lock, app_open, code_fix, volume, screenshot, vision, file_op, spotify, reminder, brightness, power, process, network, media, type_tool, scheduler, whatsapp, click, read_screen, set_wallpaper, youtube, write_in_notepad, virus_scan, pdf_reader, excel, email, converter, website_maker, web_scraper, image_generator, scroll, press_key, vscode, user_choice]:
    if not hasattr(mod, 'TOOL_PREFIX'):
        mod.TOOL_PREFIX = mod.__name__.split('.')[-1] + ":"
    if not hasattr(mod, 'TOOL_NAME'):
        mod.TOOL_NAME = mod.__name__.split('.')[-1]
    if not hasattr(mod, 'run'):
        mod.run = lambda *args, **kwargs: "Tool triggered natively via LiveKit AI Engine."

# ══════════════════════════════════════════════════════════════════════════════
#  STEP B — REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
REGISTRY = [

    {"match": "exact",  "key": desktop.TOOL_NAME,    "module": desktop,   "query": False},
    {"match": "prefix", "key": desktop.TOOL_PREFIX,  "module": desktop,   "query": True },
    {"match": "prefix", "key": search.TOOL_PREFIX,   "module": search,    "query": True },
    {"match": "exact",  "key": lock.TOOL_NAME,        "module": lock,      "query": False},
    {"match": "prefix", "key": app_open.TOOL_PREFIX,  "module": app_open,  "query": True },
    {"match": "prefix", "key": code_fix.TOOL_PREFIX,  "module": code_fix,  "query": True },
    {"match": "prefix", "key": volume.TOOL_PREFIX,    "module": volume,    "query": True },
    {"match": "exact",  "key": screenshot.TOOL_NAME,  "module": screenshot, "query": False},
    {"match": "prefix", "key": vision.TOOL_PREFIX,      "module": vision,     "query": True },
    {"match": "prefix", "key": file_op.TOOL_PREFIX,    "module": file_op,    "query": True },
    {"match": "prefix", "key": spotify.TOOL_PREFIX,    "module": spotify,    "query": True },
    {"match": "prefix", "key": reminder.TOOL_PREFIX,    "module": reminder,   "query": True },

    # ── add karo neeche ──────────────────────────────────────────────────────
    {"match": "prefix", "key": brightness.TOOL_PREFIX,  "module": brightness, "query": True },
    {"match": "prefix", "key": power.TOOL_PREFIX,       "module": power,      "query": True },
    {"match": "prefix", "key": process.TOOL_PREFIX,     "module": process,    "query": True },
    {"match": "prefix", "key": network.TOOL_PREFIX,     "module": network,    "query": True },
    {"match": "prefix", "key": media.TOOL_PREFIX,       "module": media,      "query": True },
    {"match": "prefix", "key": type_tool.TOOL_PREFIX,   "module": type_tool,  "query": True },
    {"match": "prefix", "key": scheduler.TOOL_PREFIX,   "module": scheduler,  "query": True },
    {"match": "prefix", "key": whatsapp.TOOL_PREFIX,    "module": whatsapp,   "query": True },
    {"match": "prefix", "key": click.TOOL_PREFIX,       "module": click,      "query": True },
    {"match": "prefix", "key": read_screen.TOOL_PREFIX, "module": read_screen, "query": True },
    {"match": "prefix", "key": set_wallpaper.TOOL_PREFIX, "module": set_wallpaper, "query": True },
    {"match": "prefix", "key": youtube.TOOL_PREFIX,     "module": youtube,    "query": True },
    {"match": "prefix", "key": write_in_notepad.TOOL_PREFIX, "module": write_in_notepad, "query": True },
    {"match": "prefix", "key": virus_scan.TOOL_PREFIX,   "module": virus_scan, "query": True },
    {"match": "prefix", "key": pdf_reader.TOOL_PREFIX,   "module": pdf_reader, "query": True },
    {"match": "prefix", "key": excel.TOOL_PREFIX,        "module": excel,      "query": True },
    {"match": "prefix", "key": email.TOOL_PREFIX,        "module": email,      "query": True },
    {"match": "prefix", "key": converter.TOOL_PREFIX,    "module": converter,  "query": True },
    {"match": "prefix", "key": website_maker.TOOL_PREFIX,"module": website_maker,"query": True },
    {"match": "prefix", "key": web_scraper.TOOL_PREFIX,   "module": web_scraper,   "query": True },
    {"match": "prefix", "key": image_generator.TOOL_PREFIX,"module": image_generator,"query": True },
    {"match": "prefix", "key": scroll.TOOL_PREFIX,        "module": scroll,        "query": True },
    {"match": "prefix", "key": press_key.TOOL_PREFIX,     "module": press_key,     "query": True },
    {"match": "prefix", "key": vscode.TOOL_PREFIX,          "module": vscode,          "query": True },
    {"match": "prefix", "key": user_choice.TOOL_PREFIX,     "module": user_choice,     "query": True },
    # ─────────────────────────────────────────────────────────────────────────
]

TOOL_TAG = "[TOOL:"
TOOL_END = "]"


# ══════════════════════════════════════════════════════════════════════════════
#  CORE — kabhi mat badlo
# ══════════════════════════════════════════════════════════════════════════════
def handle_tool(name: str) -> str:
    import os
    import re
    raw, lower = name.strip(), name.strip().lower()
    result = None
    for entry in REGISTRY:
        mod = entry["module"]
        if entry["match"] == "exact" and lower == entry["key"]:
            result = mod.run()
            break
        if entry["match"] == "prefix" and lower.startswith(entry["key"]):
            query = raw[len(entry["key"]):] if entry["query"] else ""
            result = mod.run(query) if entry["query"] else mod.run()
            break
            
    if result is None:
        result = f"Tool samajh nahi aaya: {name}"
        
    # Dynamically format result for Nova (male pronouns, "Sir" instead of "Boss")
    agent_name = os.getenv("AGENT_NAME", "NIK").strip().lower()
    if agent_name == "nova":
        # Replace Boss/boss with Sir/sir
        result = re.sub(r'\bBoss\b', 'Sir', result)
        result = re.sub(r'\bboss\b', 'sir', result)
        # Handle verbs
        replacements = [
            (r'\brahi\b', 'raha'),
            (r'\bdeti\b', 'deta'),
            (r'\bkarti\b', 'karta'),
            (r'\bkarungi\b', 'karunga'),
            (r'\bbanaungi\b', 'banaunga'),
            (r'\blagati\b', 'lagata'),
            (r'\bdekhti\b', 'dekhta'),
            (r'\bnikali\b', 'nikala'),
            (r'\bbheji\b', 'bheja'),
            (r'\bmili hain\b', 'mile hain'),
            (r'\bmili\b', 'mila'),
            (r'\bgayi hain\b', 'gaye hain'),
            (r'\bgayi\b', 'gaya'),
            (r'\baayi hain\b', 'aaye hain'),
            (r'\baayi\b', 'aaya'),
            (r'\bpayi\b', 'paya'),
            (r'\bkholi\b', 'khola'),
            (r'\bsunati\b', 'sunata'),
            (r'\bbatati\b', 'batata'),
        ]
        for pattern, repl in replacements:
            result = re.sub(pattern, repl, result)
            
    return result


def is_silent(name: str) -> bool:
    lower = name.strip().lower()
    for entry in REGISTRY:
        mod = entry["module"]
        if entry["match"] == "exact" and lower == entry["key"]:
            return getattr(mod, "IS_SILENT", True)
        if entry["match"] == "prefix" and lower.startswith(entry["key"]):
            return getattr(mod, "IS_SILENT", True)
    return True


def extract_tool(text: str):
    s = text.find(TOOL_TAG)
    if s == -1: return None
    
    depth = 0
    for i in range(s, len(text)):
        char = text[i]
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                # Found the matching closing bracket for the outer [TOOL:...
                return text[s + len(TOOL_TAG): i].strip()
    return None


def list_tools() -> None:
    print(f"\n{'─'*48}")
    print(f"  NIK Tools — {len(REGISTRY)} registered")
    print(f"{'─'*48}")
    for e in REGISTRY:
        silent = "🔇" if getattr(e["module"], "IS_SILENT", True) else "🔊"
        q      = "+query" if e["query"] else "      "
        print(f"  [{e['match']:6}]  {e['key']:<26} {q}  {silent}")
    print(f"{'─'*48}\n")
